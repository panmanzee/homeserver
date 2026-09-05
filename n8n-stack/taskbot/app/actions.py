"""Apply an Intent to the tasks table. Returns the reply string. No calendar here
(Task 6 wraps these); no Telegram here (handler sends)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from . import clock, db
from .intent import Intent

_HINT = ('try e.g. "math homework today", "gym at 11pm", '
         '"done with the gym", "what\'s today"')


def _parse_date(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def _parse_dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


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


def add_event(i: Intent) -> tuple[str, dict]:
    start = _parse_dt(i.start)
    end = _parse_dt(i.end) or (start + timedelta(minutes=i.estimate_minutes or 60))
    row = db.create_task(title=i.title or "untitled", scheduled_start=start,
                         scheduled_end=end, estimate_minutes=i.estimate_minutes)
    hm = start.strftime("%H:%M")
    return f'✅ {row["title"]} at {hm} {_fmt_day(start.date())}', row


def complete_task(i: Intent) -> tuple[str, dict | None]:
    if not i.target_task_id or not db.get_task(i.target_task_id):
        return (i.note or f"which task? {_HINT}"), None
    row = db.set_status(i.target_task_id, "done")
    return f'✔️ done: {row["title"]}', row


def delete_task(i: Intent) -> tuple[str, dict | None]:
    if not i.target_task_id or not db.get_task(i.target_task_id):
        return (i.note or f"which task? {_HINT}"), None
    row = db.set_status(i.target_task_id, "cancelled")
    return f'🗑️ removed: {row["title"]}', row


def reschedule(i: Intent) -> tuple[str, dict | None]:
    if not i.target_task_id or not db.get_task(i.target_task_id):
        return (i.note or f"which task? {_HINT}"), None
    row = db.reschedule_task(i.target_task_id, due_date=_parse_date(i.date),
                             scheduled_start=_parse_dt(i.start), scheduled_end=_parse_dt(i.end))
    when = _fmt_day(row["due_date"]) or (row["scheduled_start"] and row["scheduled_start"].strftime("%H:%M"))
    return f'📅 moved: {row["title"]} → {when}', row


def list_day(i: Intent) -> tuple[str, None]:
    day = _parse_date(i.date) or clock.now_local().date()
    rows = db.tasks_for_day(day)
    if not rows:
        return f"nothing for {_fmt_day(day)} yet.", None
    lines = [f"📋 {_fmt_day(day)}:"]
    for r in rows:
        t = r["scheduled_start"].strftime("%H:%M ") if r["scheduled_start"] else "• "
        lines.append(f"{t}{r['title']}")
    return "\n".join(lines), None


_TABLE = {
    "add_task": add_task, "add_event": add_event, "complete_task": complete_task,
    "delete_task": delete_task, "reschedule": reschedule, "list_day": list_day,
}


def dispatch(i: Intent) -> tuple[str, dict | None]:
    if i.action == "unknown":
        return (i.note or f"I didn't get that — {_HINT}"), None
    return _TABLE[i.action](i)
