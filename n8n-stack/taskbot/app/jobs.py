"""Scheduled messages: a morning plan and an evening review that rolls tasks over."""

from __future__ import annotations

from datetime import timedelta

from . import clock, db, gcal, telegram
from .config import settings


def _line(row: dict) -> str:
    start = row.get("scheduled_start")
    if start:
        # timestamptz comes back aware (usually UTC) — show the user's wall clock.
        if start.tzinfo is not None:
            start = start.astimezone(clock.zone())
        return f"{start.strftime('%H:%M')} {row['title']}"
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
    anytime = db.anytime_tasks()
    if anytime:
        parts.append("\n📌 anytime (stays until done):")
        parts += [f"• {r['title']}" for r in anytime]
    if clock.is_utc():
        parts.append("\n⏰ timezone is UTC — set TASKBOT_TZ in .env")
    text = "\n".join(parts)
    telegram.send_message(text)
    return text


def evening_review() -> str:
    today = clock.now_local().date()
    pending = db.tasks_for_day(today)  # already filtered to status='pending'
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
    """LEGACY — no longer scheduled. Unfinished tasks now carry over on their own
    (db.carried_over) and keep their date. Kept only for manual use/tests.
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


def prune_message_log() -> int:
    """Nightly: drop message_log rows past the retention window."""
    return db.prune_message_log(settings.taskbot_log_retention_days)
