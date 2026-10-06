"""FastAPI composition root: opens the pool, applies schema, starts poller + scheduler."""

from __future__ import annotations

import asyncio
import logging
import secrets
from contextlib import asynccontextmanager

from datetime import date as _date

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from . import actions, clock, db, handler, jobs, telegram, web
from .config import settings
from .planner import Action, Plan

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
# httpx/httpcore log every request at INFO — that puts the bot token (it's in the
# Telegram API URL path) into the container logs every ~30s. Quiet them.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("taskbot")


def _cron(hhmm: str) -> CronTrigger:
    h, m = hhmm.split(":")
    return CronTrigger(hour=int(h), minute=int(m), timezone=clock.tz_name())


def _cron_plus(hhmm: str, minutes: int) -> CronTrigger:
    h, m = (int(x) for x in hhmm.split(":"))
    total = h * 60 + m + minutes
    if total >= 24 * 60:
        total = 23 * 60 + 59  # personal bot, not a rocket — just cap at end of day
    return CronTrigger(hour=(total // 60) % 24, minute=total % 60,
                       timezone=clock.tz_name())


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.pool.open()
    db.apply_schema()
    log.info("taskbot up (tz=%s, calendar=%s)", settings.taskbot_tz,
             "configured" if settings.google_refresh_token else "not configured")
    # The poller (Task 3) and scheduler (Task 7) both run only when
    # `settings.taskbot_run_workers` is set, so tests (TASKBOT_RUN_WORKERS=false)
    # skip them.
    poller = None
    scheduler = None
    if settings.taskbot_run_workers:
        poller = asyncio.create_task(telegram.poll_forever(handler.handle))
        scheduler = AsyncIOScheduler()
        scheduler.add_job(jobs.morning_plan,
                          _cron(settings.taskbot_morning_time), id="morning")
        scheduler.add_job(jobs.evening_review,
                          _cron(settings.taskbot_evening_time), id="evening")
        # No nightly rollover any more: unfinished tasks carry over on their own
        # (db.carried_over) and keep their original date until ticked or removed.
        scheduler.add_job(jobs.prune_message_log, _cron("03:30"), id="prune_log")
        scheduler.start()
    try:
        yield
    finally:
        if poller:
            poller.cancel()
            try:
                await poller
            except asyncio.CancelledError:
                pass
        if scheduler:
            scheduler.shutdown(wait=False)
        db.pool.close()


app = FastAPI(title="taskbot", version="1.0", lifespan=lifespan)


def require_api_key(x_api_key: str = Header(default="")) -> None:
    if not secrets.compare_digest(x_api_key, settings.service_api_key):
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")


AuthDep = Depends(require_api_key)


class MessageIn(BaseModel):
    text: str


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return web.PAGE


@app.get("/healthz")
def healthz() -> dict[str, str]:
    db.ping()
    return {"status": "ok"}


@app.post("/jobs/morning-plan", dependencies=[AuthDep])
def _job_morning() -> dict[str, str]:
    return {"sent": jobs.morning_plan()}


@app.post("/jobs/evening-review", dependencies=[AuthDep])
def _job_evening() -> dict[str, str]:
    return {"sent": jobs.evening_review()}


def _task_json(row: dict) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "status": row["status"],
        "due_date": row["due_date"].isoformat() if row.get("due_date") else None,
        "scheduled_start": row["scheduled_start"].isoformat() if row.get("scheduled_start") else None,
        "scheduled_end": row["scheduled_end"].isoformat() if row.get("scheduled_end") else None,
        "synced": bool(row.get("gcal_event_id")),
    }


@app.get("/api/tasks")
def api_tasks(day: str | None = None) -> list[dict]:
    from datetime import date as _date
    d = _date.fromisoformat(day) if day else clock.now_local().date()
    return [_task_json(r) for r in db.tasks_for_day(d)]


@app.post("/api/message")
async def api_message(body: MessageIn) -> dict:
    reply = await handler.handle(body.text, 0)
    if reply:
        await asyncio.to_thread(db.log_message, "out", reply)
    return {"reply": reply}


def _run_single_action(a: Action) -> None:
    lines, gcal_ops = actions.execute_plan(Plan(actions=[a]))
    handler._sync(gcal_ops)


@app.post("/api/tasks/{task_id}/complete")
def api_complete(task_id: int) -> dict:
    _run_single_action(Action(kind="complete", target_id=task_id))
    return {"status": "ok"}


@app.delete("/api/tasks/{task_id}")
def api_delete(task_id: int) -> dict:
    _run_single_action(Action(kind="delete", target_id=task_id))
    return {"status": "ok"}


@app.post("/api/tasks/{task_id}/calendar")
def api_add_to_calendar(task_id: int) -> dict:
    if not db.get_task(task_id):
        raise HTTPException(status_code=404, detail="task not found")
    _run_single_action(Action(kind="calendar_sync", target_id=task_id))
    return {"status": "ok"}


def _board_json(row: dict, today: _date) -> dict:
    out = _task_json(row)
    if row["status"] == "pending":
        when = row.get("due_date")
        if when is None and row.get("scheduled_start"):
            when = row["scheduled_start"].astimezone(clock.zone()).date()
        out["late_days"] = (today - when).days if when and when < today else 0
    return out


@app.get("/api/board")
def api_board(day: str | None = None) -> dict:
    """Everything the UI needs for one screen. For *today* it also returns the
    carried-over (late) tasks and the day-less "anytime" tasks, so nothing a
    person hasn't ticked or removed ever disappears."""
    today = clock.now_local().date()
    d = _date.fromisoformat(day) if day else today
    is_today = d == today
    day_rows = db.tasks_for_day(d)
    done_rows = db.done_on_day(d)
    carried = db.carried_over(today) if is_today else []
    anytime = db.anytime_tasks() if is_today else []
    return {
        "day": d.isoformat(), "today": today.isoformat(), "tz": clock.tz_name(),
        "carried": [_board_json(r, today) for r in carried],
        "day_tasks": [_board_json(r, today) for r in day_rows],
        "anytime": [_board_json(r, today) for r in anytime],
        "done": [_task_json(r) for r in done_rows],
    }


class TaskIn(BaseModel):
    title: str
    due_date: str | None = None   # YYYY-MM-DD, or null = "anytime" (stays until done)


@app.post("/api/tasks")
def api_create_task(body: TaskIn) -> dict:
    """Instant add from the UI (no LLM call). due_date=null makes an 'anytime' task."""
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="title is empty")
    try:
        due = _date.fromisoformat(body.due_date) if body.due_date else None
    except ValueError:
        raise HTTPException(status_code=422, detail="due_date must be YYYY-MM-DD")
    return _task_json(db.create_task(title=title[:300], due_date=due))


class TaskPatch(BaseModel):
    title: str | None = None
    due_date: str | None = None   # only applied when the field is sent; null = anytime


@app.patch("/api/tasks/{task_id}")
def api_update_task(task_id: int, body: TaskPatch) -> dict:
    row = db.get_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="task not found")
    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"task is already {row['status']}")
    sent = body.model_fields_set
    if "due_date" in sent and row.get("scheduled_start"):
        raise HTTPException(status_code=400,
                            detail="timed tasks keep their time; reschedule them from chat")
    if "title" in sent:
        title = (body.title or "").strip()
        if not title:
            raise HTTPException(status_code=422, detail="title is empty")
        row = db.rename_task(task_id, title[:300])
    if "due_date" in sent:
        try:
            due = _date.fromisoformat(body.due_date) if body.due_date else None
        except ValueError:
            raise HTTPException(status_code=422, detail="due_date must be YYYY-MM-DD")
        row = db.set_task_timing(task_id, due_date=due, scheduled_start=None, scheduled_end=None)
    handler._sync([("reschedule", row)])  # no-op unless the task was already on the calendar
    return _task_json(row)


@app.post("/api/tasks/{task_id}/restore")
def api_restore(task_id: int) -> dict:
    row = db.restore_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="nothing to restore")
    return _task_json(row)
