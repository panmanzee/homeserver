"""Turn one Telegram message into a structured Intent via Claude Haiku (tool use)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Literal

import anthropic
from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from . import db
from .config import settings

log = logging.getLogger("taskbot.intent")

Action = Literal["add_task", "add_event", "complete_task", "delete_task",
                 "reschedule", "list_day", "unknown"]


class Intent(BaseModel):
    action: Action
    title: str | None = None
    date: str | None = None          # YYYY-MM-DD
    start: str | None = None         # YYYY-MM-DDTHH:MM
    end: str | None = None
    estimate_minutes: int | None = None
    target_task_id: int | None = None
    note: str | None = None


_TOOL = {
    "name": "record_intent",
    "description": "Record the structured intent of the user's task-manager message.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string",
                       "enum": ["add_task", "add_event", "complete_task",
                                "delete_task", "reschedule", "list_day", "unknown"]},
            "title": {"type": ["string", "null"]},
            "date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
            "start": {"type": ["string", "null"], "description": "YYYY-MM-DDTHH:MM local"},
            "end": {"type": ["string", "null"], "description": "YYYY-MM-DDTHH:MM local"},
            "estimate_minutes": {"type": ["integer", "null"]},
            "target_task_id": {"type": ["integer", "null"],
                               "description": "id of an existing open task for complete/delete/reschedule"},
            "note": {"type": ["string", "null"],
                     "description": "a clarifying question when the message is ambiguous"},
        },
        "required": ["action"],
    },
}

_SYSTEM = """\
You convert a single chat message into ONE task-manager intent. The user manages \
a personal to-do list and daily schedule.

Rules:
- "today", "tomorrow", weekday names, and clock times are relative to the \
provided current datetime and timezone. Emit dates as YYYY-MM-DD and datetimes \
as YYYY-MM-DDTHH:MM in the user's LOCAL time (no timezone suffix).
- A message with a clock time ("gym at 11pm", "call at 14:30") is `add_event` \
with `start` set. A message with only a day or no time ("math homework today", \
"finish the report") is `add_task` with `date` (default: today).
- "done"/"finished"/"completed X" -> `complete_task`. "delete"/"remove"/"cancel X" \
-> `delete_task`. "move"/"reschedule X to ..." -> `reschedule`.
- For complete/delete/reschedule, pick `target_task_id` from the OPEN TASKS list \
by matching the user's words. If none clearly match, or two+ match equally, use \
action `unknown` and put a short question in `note`.
- "what's today", "show my day", "what do i have tomorrow" -> `list_day`.
- Anything you can't map -> `unknown` with a helpful `note`.
Always call the record_intent tool exactly once."""


_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


@retry(retry=retry_if_exception_type(
    (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APIConnectionError)),
    stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=15), reraise=True)
def _call(client: anthropic.Anthropic, user_content: str) -> Any:
    return client.messages.create(
        model=settings.claude_model,
        max_tokens=settings.llm_max_tokens,
        system=_SYSTEM,
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": "record_intent"},
        messages=[{"role": "user", "content": user_content}],
    )


def parse(text: str, *, now: datetime, tz: str, client: anthropic.Anthropic | None = None) -> Intent:
    tasks = db.open_tasks()
    task_lines = "\n".join(
        f"- id={t['id']} | {t['title']} | due={t['due_date']}" for t in tasks
    ) or "(none)"
    user_content = (
        f"CURRENT DATETIME: {now.isoformat()} ({tz})\n\n"
        f"OPEN TASKS:\n{task_lines}\n\n"
        f"MESSAGE:\n{text}"
    )
    client = client or _get_client()
    try:
        resp = _call(client, user_content)
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
        # APIConnectionError also covers APITimeoutError (its subclass) — a
        # network failure after retries must land here, not as a generic crash.
        log.error("anthropic error: %s", exc)
        return Intent(action="unknown", note="I'm having trouble right now — try again in a moment.")
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "record_intent":
            try:
                return Intent.model_validate(block.input)
            except ValidationError as exc:
                log.warning("intent validation failed: %s / %s", exc, block.input)
                return Intent(action="unknown", note="I didn't quite get that.")
    return Intent(action="unknown", note="I didn't quite get that.")
