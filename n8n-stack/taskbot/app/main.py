"""FastAPI composition root: opens the pool, applies schema, starts poller + scheduler."""

from __future__ import annotations

import asyncio
import logging
import secrets
from contextlib import asynccontextmanager

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
        scheduler.add_job(jobs.rollover_unfinished,
                          _cron_plus(settings.taskbot_evening_time, 30),
                          id="rollover")
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
