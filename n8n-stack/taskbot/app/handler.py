"""The poller's message handler: parse -> act -> sync calendar (Task 6) -> reply."""

from __future__ import annotations

import asyncio

from . import actions, clock, db, gcal, intent

_warned_utc = False


def _act(parsed) -> str:
    """Blocking: dispatch the intent, then mirror the change to Google Calendar.

    Runs in a worker thread (see ``handle``) so the network-bound ``gcal.sync_*``
    calls never stall the poll loop. Every ``gcal`` function is a no-op when
    Google isn't configured, and ``gcal._guard`` swallows its own errors, so a
    calendar failure can't break the reply.
    """
    reply, row = actions.dispatch(parsed)
    if row:
        if parsed.action in ("add_task", "add_event"):
            gcal.sync_new(row)
        elif parsed.action == "complete_task":
            gcal.sync_completed(row)
        elif parsed.action == "delete_task":
            gcal.sync_deleted(row)
        elif parsed.action == "reschedule":
            gcal.sync_rescheduled(row)
    return reply


async def handle(text: str, msg_id: int) -> str | None:
    global _warned_utc
    # Log the inbound row FIRST — before parse/act can raise — so the poller's
    # crash path never needs to (and never double-logs) this message.
    await asyncio.to_thread(db.log_message, "in", text, tg_message_id=msg_id)
    parsed = await asyncio.to_thread(
        intent.parse, text, now=clock.now_local(), tz=clock.tz_name()
    )
    reply = await asyncio.to_thread(_act, parsed)
    if clock.is_utc() and not _warned_utc:
        reply += "\n\n⏰ timezone is UTC — set TASKBOT_TZ in .env"
        _warned_utc = True
    return reply
