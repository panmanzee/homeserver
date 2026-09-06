"""Apply an Intent to the tasks table. Returns the reply string. No calendar here
(Task 6 wraps these); no Telegram here (handler sends)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from . import clock, db
from .intent import Intent

_HINT = ('try e.g. "math homework today", "gym at 11pm", '
         '"done with the gym", "what\'s today"')
_DATE_HINT = "I couldn't read that date/time — try 'tomorrow' or 2026-09-10"
_WHEN_HINT = "tell me when — e.g. 'friday' or 'tomorrow 3pm'"


def _parse_date(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def _parse_dt(s: str | None) -> datetime | None:
    # Attach the user's zone so scheduled_start (timestamptz) stores the right
    # instant and the Google Calendar event lands at the intended wall-clock.
    return datetime.fromisoformat(s).replace(tzinfo=clock.zone()) if s else None


def _hhmm(dt: datetime | None) -> str:
    """Wall-clock HH:MM in the user's zone. `scheduled_start` comes back from
    psycopg as an aware datetime (usually UTC), so it must be converted before
    formatting — otherwise a 18:00 Bangkok event renders as 11:00."""
    return dt.astimezone(clock.zone()).strftime("%H:%M") if dt else ""


def _fmt_day(d: date | None) -> str:
    if not d:
        return ""
    today = clock.now_local().date()
    if d == today:
        return "today"
    if d == today + timedelta(days=1):
        return "tomorrow"
    return d.isoformat()


def add_task(i: Intent) -> tuple[str, dict]:
    due = _parse_date(i.date) or clock.now_local().date()
    row = db.create_task(title=i.title or "untitled", due_date=due,
                         estimate_minutes=i.estimate_minutes)
    return f'✅ added "{row["title"]}" for {_fmt_day(due)}', row


def add_event(i: Intent) -> tuple[str, dict | None]:
    start = _parse_dt(i.start)
    if start is None:
        return _WHEN_HINT, None
    end = _parse_dt(i.end) or (start + timedelta(minutes=i.estimate_minutes or 60))
    row = db.create_task(title=i.title or "untitled", scheduled_start=start,
                         scheduled_end=end, estimate_minutes=i.estimate_minutes)
    return f'✅ {row["title"]} at {_hhmm(start)} {_fmt_day(start.date())}', row


def complete_task(i: Intent) -> tuple[str, dict | None]:
    existing = db.get_task(i.target_task_id) if i.target_task_id else None
    if not existing:
        return (i.note or f"which task? {_HINT}"), None
    if existing["status"] != "pending":
        return f'that task is already {existing["status"]}', None
    row = db.set_status(i.target_task_id, "done")
    return f'✔️ done: {row["title"]}', row


def delete_task(i: Intent) -> tuple[str, dict | None]:
    existing = db.get_task(i.target_task_id) if i.target_task_id else None
    if not existing:
        return (i.note or f"which task? {_HINT}"), None
    if existing["status"] != "pending":
        return f'that task is already {existing["status"]}', None
    row = db.set_status(i.target_task_id, "cancelled")
    return f'🗑️ removed: {row["title"]}', row


def reschedule(i: Intent) -> tuple[str, dict | None]:
    if not i.target_task_id or not db.get_task(i.target_task_id):
        return (i.note or f"which task? {_HINT}"), None
    due, start, end = _parse_date(i.date), _parse_dt(i.start), _parse_dt(i.end)
    if due is None and start is None:
        return _WHEN_HINT, None
    row = db.reschedule_task(i.target_task_id, due_date=due,
                             scheduled_start=start, scheduled_end=end)
    when = _fmt_day(row["due_date"]) or _hhmm(row["scheduled_start"])
    return f'📅 moved: {row["title"]} → {when}', row


def list_day(i: Intent) -> tuple[str, None]:
    day = _parse_date(i.date) or clock.now_local().date()
    rows = db.tasks_for_day(day)
    if not rows:
        return f"nothing for {_fmt_day(day)} yet.", None
    lines = [f"📋 {_fmt_day(day)}:"]
    for r in rows:
        t = f"{_hhmm(r['scheduled_start'])} " if r["scheduled_start"] else "• "
        lines.append(f"{t}{r['title']}")
    return "\n".join(lines), None


_TABLE = {
    "add_task": add_task, "add_event": add_event, "complete_task": complete_task,
    "delete_task": delete_task, "reschedule": reschedule, "list_day": list_day,
}


def dispatch(i: Intent) -> tuple[str, dict | None]:
    if i.action == "unknown":
        return (i.note or f"I didn't get that — {_HINT}"), None
    try:
        return _TABLE[i.action](i)
    except ValueError:
        # a malformed LLM date/datetime string ("next tuesday") reaching
        # date.fromisoformat / datetime.fromisoformat — reply, don't crash.
        return _DATE_HINT, None
