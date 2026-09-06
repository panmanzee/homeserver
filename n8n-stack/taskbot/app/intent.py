"""Turn one Telegram message into a structured Intent.

The LLM provider is pluggable via ``LLM_PROVIDER`` (mirrors ``newsfeed-api``):
``gemini`` (default, free tier) or ``anthropic``. Both paths ask for the same
JSON shape and hand it to the same Pydantic validation before it is acted on.
Any provider failure degrades to ``Intent(action="unknown", …)`` so the poller
never crashes on a bad LLM call.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from . import db
from .config import settings

log = logging.getLogger("taskbot.intent")

Action = Literal["add_task", "add_event", "complete_task", "delete_task",
                 "reschedule", "list_day", "unknown"]

_ACTIONS = ["add_task", "add_event", "complete_task", "delete_task",
           "reschedule", "list_day", "unknown"]

_TROUBLE = "I'm having trouble right now — try again in a moment."


class Intent(BaseModel):
    action: Action
    title: str | None = None
    date: str | None = None          # YYYY-MM-DD
    start: str | None = None         # YYYY-MM-DDTHH:MM
    end: str | None = None
    estimate_minutes: int | None = None
    target_task_id: int | None = None
    note: str | None = None


class IntentError(RuntimeError):
    """The model could not produce a usable structured result."""


# Single source of truth for the output shape. Anthropic wraps it as a tool
# input_schema; Gemini takes it as a response_schema.
_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": _ACTIONS},
        "title": {"type": "string", "description": "task/event title"},
        "date": {"type": "string", "description": "YYYY-MM-DD"},
        "start": {"type": "string", "description": "YYYY-MM-DDTHH:MM local"},
        "end": {"type": "string", "description": "YYYY-MM-DDTHH:MM local"},
        "estimate_minutes": {"type": "integer"},
        "target_task_id": {
            "type": "integer",
            "description": "id of an existing open task for complete/delete/reschedule",
        },
        "note": {"type": "string",
                 "description": "a clarifying question when the message is ambiguous"},
    },
    "required": ["action"],
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
- Set only the fields you need; leave the rest empty.
Return exactly one result matching the schema."""


def _build_user_content(text: str, *, now: datetime, tz: str) -> str:
    tasks = db.open_tasks()
    task_lines = "\n".join(
        f"- id={t['id']} | {t['title']} | due={t['due_date']}" for t in tasks
    ) or "(none)"
    return (
        f"CURRENT DATETIME: {now.isoformat()} ({tz})\n\n"
        f"OPEN TASKS:\n{task_lines}\n\n"
        f"MESSAGE:\n{text}"
    )


# --------------------------------------------------------------------------- #
# Gemini provider (default)
# --------------------------------------------------------------------------- #
_gemini_client: Any | None = None
_SAFETY = (
    "HARM_CATEGORY_HARASSMENT",
    "HARM_CATEGORY_HATE_SPEECH",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_DANGEROUS_CONTENT",
)


def _get_gemini_client() -> Any:
    global _gemini_client
    if _gemini_client is None:
        if not settings.gemini_api_key:
            raise IntentError("GEMINI_API_KEY is not set")
        from google import genai

        _gemini_client = genai.Client(api_key=settings.gemini_api_key)
    return _gemini_client


def _gemini_should_retry(exc: BaseException) -> bool:
    try:
        from google.genai import errors as genai_errors
    except ModuleNotFoundError:
        return False
    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.ClientError) and getattr(exc, "code", None) == 429:
        return True
    return False


def _gemini_config() -> dict[str, Any]:
    # Passed as a plain dict so the google-genai `types` module is only needed
    # inside the real SDK (tests inject a fake client and skip this path).
    return {
        "system_instruction": _SYSTEM,
        "response_mime_type": "application/json",
        "response_schema": _SCHEMA,
        "temperature": 0.0,
        "max_output_tokens": settings.llm_max_tokens,
        "thinking_config": {"thinking_budget": 0},
        "automatic_function_calling": {"disable": True},
        "safety_settings": [
            {"category": c, "threshold": "BLOCK_NONE"} for c in _SAFETY
        ],
    }


@retry(retry=retry_if_exception(_gemini_should_retry),
       stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=15), reraise=True)
def _gemini_call(client: Any, user_content: str) -> Any:
    return client.models.generate_content(
        model=settings.gemini_model,
        contents=user_content,
        config=_gemini_config(),
    )


def _gemini_raw(user_content: str, *, client: Any | None = None) -> dict[str, Any]:
    client = client or _get_gemini_client()
    try:
        resp = _gemini_call(client, user_content)
    except IntentError:
        raise
    except Exception as exc:  # noqa: BLE001 - google.genai.errors.* + anything else
        raise IntentError(f"gemini api error: {exc}") from exc

    text = getattr(resp, "text", None)
    if not text:
        finish = None
        try:
            finish = resp.candidates[0].finish_reason
        except (AttributeError, IndexError, TypeError):
            pass
        raise IntentError(f"gemini returned no text (finish_reason={finish})")
    try:
        raw = json.loads(text)
    except ValueError as exc:
        raise IntentError(f"gemini returned non-JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise IntentError(f"gemini returned a {type(raw).__name__}, expected object")
    return raw


# --------------------------------------------------------------------------- #
# Anthropic provider
# --------------------------------------------------------------------------- #
_anthropic_client: Any | None = None

_TOOL = {
    "name": "record_intent",
    "description": "Record the structured intent of the user's task-manager message.",
    "input_schema": {**_SCHEMA, "additionalProperties": False},
}


def _get_anthropic_client() -> Any:
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic

        if not settings.anthropic_api_key:
            raise IntentError("ANTHROPIC_API_KEY is not set")
        _anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client


def _anthropic_should_retry(exc: BaseException) -> bool:
    try:
        import anthropic
    except ModuleNotFoundError:
        return False
    return isinstance(exc, (anthropic.RateLimitError, anthropic.InternalServerError,
                            anthropic.APIConnectionError))


@retry(retry=retry_if_exception(_anthropic_should_retry),
       stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=15), reraise=True)
def _anthropic_call(client: Any, user_content: str) -> Any:
    return client.messages.create(
        model=settings.claude_model,
        max_tokens=settings.llm_max_tokens,
        system=_SYSTEM,
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": "record_intent"},
        messages=[{"role": "user", "content": user_content}],
    )


def _anthropic_raw(user_content: str, *, client: Any | None = None) -> dict[str, Any]:
    client = client or _get_anthropic_client()
    try:
        resp = _anthropic_call(client, user_content)
    except IntentError:
        raise
    except Exception as exc:  # noqa: BLE001 - anthropic.APIStatusError / APIConnectionError / etc
        raise IntentError(f"anthropic api error: {exc}") from exc
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "record_intent":
            return dict(block.input)
    raise IntentError(
        f"no record_intent tool_use in response "
        f"(stop_reason={getattr(resp, 'stop_reason', None)})"
    )


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def parse(
    text: str,
    *,
    now: datetime,
    tz: str,
    provider: str | None = None,
    client: Any | None = None,
) -> Intent:
    provider = provider or settings.llm_provider
    user_content = _build_user_content(text, now=now, tz=tz)
    try:
        if provider == "anthropic":
            raw = _anthropic_raw(user_content, client=client)
        else:
            raw = _gemini_raw(user_content, client=client)
    except IntentError as exc:
        log.error("intent llm error (%s): %s", provider, exc)
        return Intent(action="unknown", note=_TROUBLE)

    # Structured-output models sometimes emit "" / 0 for fields they were told to
    # leave blank; drop those so Pydantic sees a clean payload.
    cleaned = {k: v for k, v in raw.items() if v not in ("", None)}
    try:
        return Intent.model_validate(cleaned)
    except ValidationError as exc:
        log.warning("intent validation failed: %s / %s", exc, raw)
        return Intent(action="unknown", note="I didn't quite get that.")
