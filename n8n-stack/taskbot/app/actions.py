"""Apply a Plan's ordered actions to the tasks table.

``execute_plan`` runs each action in order and returns ``(reply_lines,
gcal_ops)`` — the human-readable lines to send back, plus the ``(kind, row)``
pairs the handler mirrors to Google Calendar. No calendar or Telegram I/O here.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from . import clock, db
from .planner import Action, Plan

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

_ALL_DAY_HINT = "which task should I make all-day? tell me the name"


def _add_task(a: Action) -> tuple[str, dict | None]:
    due = _parse_date(a.date) or clock.now_local().date()
    row = db.create_task(title=a.title or "untitled", due_date=due,
                         estimate_minutes=a.estimate_minutes)
    return f'✅ added "{row["title"]}" for {_fmt_day(due)}', row


def _add_event(a: Action) -> tuple[str, dict | None]:
    start = _parse_dt(a.start)
    if start is None:
        return _WHEN_HINT, None
    end = _parse_dt(a.end) or (start + timedelta(minutes=a.estimate_minutes or 60))
    row = db.create_task(title=a.title or "untitled", scheduled_start=start,
                         scheduled_end=end, estimate_minutes=a.estimate_minutes)
    return f'✅ {row["title"]} at {_hhmm(start)} {_fmt_day(start.date())}', row


def _target(a: Action) -> dict | None:
    return db.get_task(a.target_id) if a.target_id else None


def _complete(a: Action) -> tuple[str, dict | None]:
    row = _target(a)
    if not row:
        return (a.note or f"which task? {_HINT}"), None
    if row["status"] != "pending":
        return f'that task is already {row["status"]}', None
    return f'✔️ done: {row["title"]}', db.set_status(a.target_id, "done")


def _delete(a: Action) -> tuple[str, dict | None]:
    row = _target(a)
    if not row:
        return (a.note or f"which task? {_HINT}"), None
    if row["status"] != "pending":
        return f'that task is already {row["status"]}', None
    return f'🗑️ removed: {row["title"]}', db.set_status(a.target_id, "cancelled")


def _reschedule(a: Action) -> tuple[str, dict | None]:
    before = _target(a)
    if not before:
        return (a.note or f"which task? {_HINT}"), None
    due, start, end = _parse_date(a.date), _parse_dt(a.start), _parse_dt(a.end)
    if due is None and start is None:
        return _WHEN_HINT, None
    if start is not None and end is None:
        # db.reschedule_task COALESCEs a None end onto the OLD end, which would
        # leave the event zero/negative length once the start moves. Rebuild the
        # end from the original duration (or a 60-min fallback).
        old_s, old_e = before.get("scheduled_start"), before.get("scheduled_end")
        dur = (old_e - old_s) if (old_s and old_e and old_e > old_s) \
            else timedelta(minutes=a.estimate_minutes or 60)
        end = start + dur
    row = db.reschedule_task(a.target_id, due_date=due, scheduled_start=start, scheduled_end=end)
    when = _fmt_day(row["due_date"]) or _hhmm(row["scheduled_start"])
    return f'📅 moved: {row["title"]} → {when}', row


def _convert(a: Action) -> tuple[str, dict | None]:
    row = _target(a)
    if not row:
        return (a.note or _ALL_DAY_HINT), None
    if a.to_all_day is False:
        # convert with to_all_day:false means "give it a time" — but the planner
        # should have emitted a reschedule. Ask rather than null the times.
        return (a.note or "tell me the new time — e.g. 'gym at 7pm'"), None
    if row["status"] != "pending":
        return f'that task is already {row["status"]}', None
    # v1 supports only timed -> all-day (to_all_day truthy or unset with a timed task)
    d = _parse_date(a.date) or (row["scheduled_start"].date() if row.get("scheduled_start")
                                else clock.now_local().date())
    new = db.set_task_timing(a.target_id, due_date=d, scheduled_start=None, scheduled_end=None)
    return f'🔁 {new["title"]} is now an all-day task for {_fmt_day(d)}', new


def _rename(a: Action) -> tuple[str, dict | None]:
    row = _target(a)
    if not row or not a.title:
        return (a.note or f"rename which task, to what? {_HINT}"), None
    if row["status"] != "pending":
        return f'that task is already {row["status"]}', None
    new = db.rename_task(a.target_id, a.title)
    return f'✏️ renamed to "{new["title"]}"', new


def _list_day(a: Action) -> tuple[str, None]:
    day = _parse_date(a.date) or clock.now_local().date()
    rows = db.tasks_for_day(day)
    if not rows:
        return f"nothing for {_fmt_day(day)} yet.", None
    lines = [f"📋 {_fmt_day(day)}:"]
    for r in rows:
        t = f"{_hhmm(r['scheduled_start'])} " if r["scheduled_start"] else "• "
        lines.append(f"{t}{r['title']}")
    return "\n".join(lines), None


_TABLE = {
    "add_task": _add_task, "add_event": _add_event, "complete": _complete,
    "delete": _delete, "reschedule": _reschedule, "convert": _convert,
    "rename": _rename, "list_day": _list_day,
}
# kinds whose resulting row must be mirrored to Google Calendar
_GCAL_KINDS = {"add_task", "add_event", "complete", "delete", "reschedule", "convert", "rename"}


def execute_plan(plan: Plan) -> tuple[list[str], list[tuple[str, dict]]]:
    lines: list[str] = []
    gcal_ops: list[tuple[str, dict]] = []
    if plan.reply:
        lines.append(plan.reply)
    for a in plan.actions:
        if a.kind == "reply":
            if a.note:
                lines.append(a.note)
            continue
        fn = _TABLE.get(a.kind)
        if fn is None:
            import logging
            logging.getLogger("taskbot.actions").warning("unknown action kind: %s", a.kind)
            lines.append(f"⚠️ couldn't do: {a.kind}")
            continue
        try:
            msg, row = fn(a)
        except ValueError:
            lines.append(_DATE_HINT)
            continue
        except Exception:  # noqa: BLE001 - one bad action must not sink the plan
            import logging
            logging.getLogger("taskbot.actions").exception("action failed: %s", a.kind)
            lines.append(f"⚠️ couldn't do: {a.kind}")
            continue
        lines.append(msg)
        if row and a.kind in _GCAL_KINDS:
            gcal_ops.append((a.kind, row))
    if not lines:
        lines.append(f"I didn't get that — {_HINT}")
    return lines, gcal_ops
