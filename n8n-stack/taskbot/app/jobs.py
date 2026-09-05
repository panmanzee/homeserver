"""Scheduled messages: a morning plan and an evening review that rolls tasks over."""

from __future__ import annotations

import logging
from datetime import timedelta

from . import clock, db, gcal, telegram

log = logging.getLogger("taskbot.jobs")


def _line(row: dict) -> str:
    if row.get("scheduled_start"):
        return f"{row['scheduled_start'].strftime('%H:%M')} {row['title']}"
    return f"• {row['title']}"


def morning_plan() -> str:
    today = clock.now_local().date()
    todays = db.tasks_for_day(today)
    overdue = db.overdue_tasks(today)
    parts = [f"☀️ Plan for {today.isoformat()}"]
    if todays:
        parts += [_line(r) for r in todays]
    else:
        parts.append("(nothing scheduled — text me what you want to do)")
    if overdue:
        parts.append("\n⏮️ still open from before:")
        parts += [f"• {r['title']}" for r in overdue]
    if clock.is_utc():
        parts.append("\n⏰ timezone is UTC — set TASKBOT_TZ in .env")
    text = "\n".join(parts)
    telegram.send_message(text)
    return text


def evening_review() -> str:
    today = clock.now_local().date()
    tomorrow = today + timedelta(days=1)
    todays = db.tasks_for_day(today)
    pending = [r for r in todays if r["status"] == "pending"]
    if not pending:
        text = "🌙 Everything for today is done. Nice."
        telegram.send_message(text)
        return text
    parts = ["🌙 Evening check — what got done? (reply e.g. \"did the homework, skip the rest\")"]
    parts += [_line(r) for r in pending]
    text = "\n".join(parts)
    telegram.send_message(text)
    return text


def rollover_unfinished() -> int:
    """Called by evening_review's follow-up, and safe to run standalone.
    Moves still-pending untimed tasks due today to tomorrow."""
    today = clock.now_local().date()
    tomorrow = today + timedelta(days=1)
    moved = 0
    for r in db.tasks_for_day(today):
        if r["status"] == "pending" and r["due_date"] == today and not r["scheduled_start"]:
            row = db.reschedule_task(r["id"], due_date=tomorrow)
            gcal.sync_rescheduled(row)
            moved += 1
    return moved
