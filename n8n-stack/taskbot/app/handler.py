"""The poller's message handler: parse -> act -> (Task 6: sync calendar) -> reply."""

from __future__ import annotations

import asyncio
import logging

from . import actions, clock, db, intent

log = logging.getLogger("taskbot.handler")
_warned_utc = False


async def handle(text: str, msg_id: int) -> str | None:
    global _warned_utc
    parsed = await asyncio.to_thread(
        intent.parse, text, now=clock.now_local(), tz=clock.tz_name()
    )
    await asyncio.to_thread(
        db.log_message, "in", text, tg_message_id=msg_id, intent=parsed.model_dump()
    )
    reply, _row = await asyncio.to_thread(actions.dispatch, parsed)
    if clock.is_utc() and not _warned_utc:
        reply += "\n\n⏰ timezone is UTC — set TASKBOT_TZ in .env"
        _warned_utc = True
    return reply
