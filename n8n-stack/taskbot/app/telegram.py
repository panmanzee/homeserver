"""Telegram Bot API: send + a long-poll getUpdates loop for one allowed chat."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Awaitable, Callable

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from . import db
from .config import settings

log = logging.getLogger("taskbot.telegram")

_API = f"https://api.telegram.org/bot{settings.telegram_bot_token}"
Handler = Callable[[str, int], Awaitable[str | None]]

# The bot token appears in every API URL path; scrub it from anything that could
# reach a log line (exception strings, tracebacks, response bodies).
_TOKEN_RE = re.compile(re.escape(settings.telegram_bot_token)) if settings.telegram_bot_token else None


def _redact(s: str) -> str:
    return _TOKEN_RE.sub("bot<REDACTED>", s) if _TOKEN_RE else s


class TelegramTransient(RuntimeError):
    """Retryable failure (429 / 5xx / network). Message is always token-free."""


class TelegramError(RuntimeError):
    """Non-retryable failure (4xx other than 429). Message is always token-free."""


def _is_transient(status: int) -> bool:
    return status == 429 or status >= 500


def _split(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    out: list[str] = []
    cur = ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if cur:
                out.append(cur)
                cur = ""
            out.append(line[:limit])
            line = line[limit:]
        if cur and len(cur) + len(line) > limit:
            out.append(cur)
            cur = line
        else:
            cur += line
    if cur:
        out.append(cur)
    return out


@retry(retry=retry_if_exception_type(TelegramTransient),
       stop=stop_after_attempt(4), wait=wait_exponential(min=1, max=20), reraise=True)
def _post_chunk(chunk: str) -> None:
    try:
        r = httpx.post(f"{_API}/sendMessage",
                       json={"chat_id": settings.telegram_chat_id, "text": chunk},
                       timeout=settings.http_timeout)
    except httpx.HTTPError as exc:
        raise TelegramTransient(_redact(str(exc))) from None
    if _is_transient(r.status_code):
        raise TelegramTransient(f"telegram sendMessage {r.status_code}")
    if r.status_code >= 400:
        log.error("telegram sendMessage %s: %s", r.status_code, _redact(r.text))
        return
    db.log_message("out", chunk)


def send_message(text: str) -> None:
    if not text:
        return
    for chunk in _split(text, 4000):
        if chunk:
            _post_chunk(chunk)


async def _get_updates(client: httpx.AsyncClient, offset: int) -> list[dict]:
    try:
        r = await client.get(f"{_API}/getUpdates",
                             params={"offset": offset, "timeout": 30},
                             timeout=40)
    except httpx.HTTPError as exc:
        raise TelegramTransient(f"getUpdates request failed: {_redact(str(exc))}") from None
    if _is_transient(r.status_code):
        raise TelegramTransient(f"getUpdates {r.status_code}")
    if r.status_code >= 400:
        raise TelegramError(f"getUpdates {r.status_code}")
    return r.json().get("result", [])


async def run_once(updates: list[dict], handle: Handler) -> int:
    """Process a batch; return the next offset. Shared by the loop and tests."""
    next_offset = db.get_offset()
    for upd in updates:
        next_offset = max(next_offset, upd["update_id"] + 1)
        msg = upd.get("message") or {}
        chat_id = str((msg.get("chat") or {}).get("id", ""))
        text = (msg.get("text") or "").strip()
        if chat_id != settings.telegram_chat_id:
            log.info("dropping update from chat %s", chat_id)
        elif not text:
            pass
        else:
            try:
                reply = await handle(text, msg.get("message_id", 0))
            except Exception:
                log.exception("handler failed for: %s", text)
                db.log_message("in", text, tg_message_id=msg.get("message_id"))  # capture the crashed msg
                reply = "⚠️ something went wrong handling that — try rephrasing."
            if reply:
                send_message(reply)
        db.set_offset(next_offset)  # advance after each update is handled (or deliberately dropped)
    return next_offset


async def poll_forever(handle: Handler) -> None:
    async with httpx.AsyncClient() as client:
        while True:
            try:
                offset = db.get_offset()
                updates = await _get_updates(client, offset)
                if updates:
                    await run_once(updates, handle)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.exception("poll loop error; backing off 5s: %s", _redact(str(exc)))
                await asyncio.sleep(5)
