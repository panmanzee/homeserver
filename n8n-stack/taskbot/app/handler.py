"""The poller's message handler: log → gather context → plan → execute → sync → reply."""

from __future__ import annotations

import asyncio

from . import actions, clock, db, gcal, planner

_warned_utc = False

_GCAL_DISPATCH = {
    "add_task": "sync_new",
    "add_event": "sync_new",
    "complete": "sync_completed",
    "delete": "sync_deleted",
    "reschedule": "sync_rescheduled",
    "convert": "sync_rescheduled",
    "rename": "sync_rescheduled",
}


def _run(text: str, history: list[dict], tasks: list[dict]) -> tuple[str, list]:
    """Blocking: plan the message, apply it, return (reply, gcal_ops)."""
    plan = planner.make_plan(
        text, history=history, tasks=tasks,
        now=clock.now_local(), tz=clock.tz_name(),
    )
    lines, gcal_ops = actions.execute_plan(plan)
    return "\n".join(lines), gcal_ops


def _sync(gcal_ops: list) -> None:
    """Blocking: mirror each mutation to Google Calendar. Every gcal.* call is a
    no-op when Google isn't configured and swallows its own errors (gcal._guard),
    so this can't break the reply."""
    for kind, row in gcal_ops:
        fn_name = _GCAL_DISPATCH.get(kind)
        if fn_name:
            getattr(gcal, fn_name)(row)


async def handle(text: str, msg_id: int) -> str | None:
    global _warned_utc
    history = await asyncio.to_thread(db.recent_turns, 6)
    await asyncio.to_thread(db.log_message, "in", text, tg_message_id=msg_id)
    tasks = await asyncio.to_thread(db.open_tasks)
    reply, gcal_ops = await asyncio.to_thread(_run, text, history, tasks)
    await asyncio.to_thread(_sync, gcal_ops)
    if clock.is_utc() and not _warned_utc:
        reply += "\n\n⏰ timezone is UTC — set TASKBOT_TZ in .env"
        _warned_utc = True
    return reply
