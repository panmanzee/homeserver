"""Turn one Telegram message into an ordered multi-action Plan.

Supersedes the v1 single-``Intent`` parser: one message can now trigger several
task-manager actions, and recent conversation turns are given to the model so it
can resolve references and corrections.

The LLM provider is pluggable via ``LLM_PROVIDER`` (mirrors ``newsfeed-api``):
``gemini`` (default, free tier) or ``anthropic``. Both paths ask for the same
JSON shape and hand it to the same Pydantic validation before it is acted on.
Any provider failure degrades to ``Plan(actions=[], reply=<trouble>)`` so the
poller never crashes on a bad LLM call.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from .config import settings

log = logging.getLogger("taskbot.planner")

MAX_ACTIONS = 10
_TROUBLE = "I'm having trouble right now — try again in a moment."

ActionKind = Literal[
    "add_task", "add_event", "complete", "delete",
    "reschedule", "convert", "rename", "list_day", "reply",
]


class Action(BaseModel):
    kind: ActionKind
    target_id: int | None = None
    title: str | None = None
    date: str | None = None            # YYYY-MM-DD
    start: str | None = None           # YYYY-MM-DDTHH:MM local
    end: str | None = None
    estimate_minutes: int | None = None
    to_all_day: bool | None = None
    note: str | None = None


class Plan(BaseModel):
    actions: list[Action] = []
    reply: str | None = None


class PlannerError(RuntimeError):
    """The model could not produce a usable plan."""


# Single source of truth for the output shape. Anthropic wraps it as a tool
# input_schema; Gemini takes it as a response_schema.
_ACTION_PROPS = {
    "kind": {"type": "string",
             "enum": ["add_task", "add_event", "complete", "delete",
                      "reschedule", "convert", "rename", "list_day", "reply"]},
    "target_id": {"type": "integer",
                  "description": "id of an OPEN TASK for complete/delete/reschedule/convert/rename"},
    "title": {"type": "string",
              "description": "task/event title; for rename this is the NEW title"},
    "date": {"type": "string", "description": "YYYY-MM-DD"},
    "start": {"type": "string", "description": "YYYY-MM-DDTHH:MM local, 24h"},
    "end": {"type": "string", "description": "YYYY-MM-DDTHH:MM local, 24h"},
    "estimate_minutes": {"type": "integer"},
    "to_all_day": {"type": "boolean",
                   "description": "convert: true = turn a timed event into an all-day task"},
    "note": {"type": "string", "description": "used only with kind=reply"},
}
_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "actions": {
            "type": "array",
            "items": {"type": "object", "properties": _ACTION_PROPS, "required": ["kind"]},
        },
        "reply": {"type": "string",
                  "description": "optional short preamble, or a single question when unsure"},
    },
    "required": ["actions"],
}

_SYSTEM = """\
You convert the user's LATEST message into an ordered list of task-manager \
actions for a personal to-do list and daily schedule.

Context you are given: the current datetime+timezone, the user's OPEN TASKS \
(id, title, type, time), and the recent CONVERSATION (their messages and your \
past replies, oldest first).

Rules:
- One message can need SEVERAL actions. Emit them in the order they must run.
- A clock time ("gym at 11pm", "call 14:30") -> `add_event` with `start`. \
A day or no time ("math homework today", "finish the report") -> `add_task` \
with `date` (default: today). Dates as YYYY-MM-DD, datetimes as \
YYYY-MM-DDTHH:MM in the user's LOCAL time, no timezone suffix.
- Use CONVERSATION to resolve references ("that", "the 13:00 one", "keep gym \
the same") and corrections ("i mean", "no", "actually", "not X but Y"). If the \
user is fixing something you just did, edit/replace that task.
- To fix a WRONGLY MERGED task (one task that should have been two), `delete` \
it and re-add the pieces as separate actions, delete first.
- `complete` = "done/finished X". `delete` = "remove/cancel X". \
`reschedule` = "move X to <time/day>". `convert` + `to_all_day: true` = turn a \
timed event into an all-day task. `rename` = change a task's wording (put the \
new title in `title`).
- For complete/delete/reschedule/convert/rename pick `target_id` from OPEN \
TASKS by matching the user's words. "all done" after an evening review -> one \
`complete` per open task for today.
- "what's today / show my day / tomorrow" -> `list_day` (with `date`).
- If you genuinely cannot tell what the user wants, emit NO actions and put one \
short question in `reply`.
- Keep `reply` for a brief preamble ("Split that into two:") or that one \
question — never chit-chat.

Examples (NOW is 2026-09-07, tz Asia/Bangkok):
- "watch iman gadzhi all day and gym at 1pm, also buy milk" ->
  add_task(title="watch iman gadzhi", date="2026-09-07"),
  add_event(title="gym", start="2026-09-07T13:00"),
  add_task(title="buy milk", date="2026-09-07")
- OPEN TASKS has id=5 "watch iman gadzhi and go to gym" TIMED 2026-09-07 13:00;
  you just added it; user says "i mean watch is allday but gym is at 13.00" ->
  delete(target_id=5),
  add_task(title="watch iman gadzhi", date="2026-09-07"),
  add_event(title="gym", start="2026-09-07T13:00")
- "make today schedule, 1hr each: 18:00 eat, 19:00 do ML, 20:00 gym" ->
  add_event(title="eat", start="2026-09-07T18:00", end="2026-09-07T19:00"),
  add_event(title="do ML", start="2026-09-07T19:00", end="2026-09-07T20:00"),
  add_event(title="gym", start="2026-09-07T20:00", end="2026-09-07T21:00")
- After an evening review, OPEN TASKS has id=9 "ml homework" DAY 2026-09-07;
  "all done, and also tomorrow add task publish OS" ->
  complete(target_id=9),
  add_task(title="publish OS", date="2026-09-08")

Return one object matching the schema, `actions` first."""


def _fmt_task(t: dict) -> str:
    if t.get("scheduled_start"):
        s = t["scheduled_start"]
        when = f"TIMED {s.isoformat(sep=' ', timespec='minutes')}"
    elif t.get("due_date"):
        when = f"DAY {t['due_date']}"
    else:
        when = "no date"
    return f"- id={t['id']} | {t['title']} | {when} | pending"


def _build_user_content(text: str, *, history: list[dict], tasks: list[dict],
                        now: datetime, tz: str) -> str:
    task_block = "\n".join(_fmt_task(t) for t in tasks) or "(none)"
    convo = "\n".join(
        f"{'you' if h['direction'] == 'in' else 'bot'}: {h['text'][:500]}"
        for h in history
    ) or "(none)"
    return (
        f"NOW: {now.isoformat(timespec='minutes')} ({tz})\n\n"
        f"OPEN TASKS:\n{task_block}\n\n"
        f"CONVERSATION (most recent last):\n{convo}\n\n"
        f"LATEST MESSAGE:\n{text}"
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
            raise PlannerError("GEMINI_API_KEY is not set")
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
    except PlannerError:
        raise
    except Exception as exc:  # noqa: BLE001 - google.genai.errors.* + anything else
        raise PlannerError(f"gemini api error: {exc}") from exc

    text = getattr(resp, "text", None)
    if not text:
        finish = None
        try:
            finish = resp.candidates[0].finish_reason
        except (AttributeError, IndexError, TypeError):
            pass
        raise PlannerError(f"gemini returned no text (finish_reason={finish})")
    try:
        raw = json.loads(text)
    except ValueError as exc:
        raise PlannerError(f"gemini returned non-JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise PlannerError(f"gemini returned a {type(raw).__name__}, expected object")
    return raw


# --------------------------------------------------------------------------- #
# Anthropic provider
# --------------------------------------------------------------------------- #
_anthropic_client: Any | None = None

_TOOL = {
    "name": "record_plan",
    "description": "Record the ordered list of task-manager actions for the user's latest message.",
    "input_schema": {**_SCHEMA, "additionalProperties": False},
}


def _get_anthropic_client() -> Any:
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic

        if not settings.anthropic_api_key:
            raise PlannerError("ANTHROPIC_API_KEY is not set")
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
        tool_choice={"type": "tool", "name": "record_plan"},
        messages=[{"role": "user", "content": user_content}],
    )


def _anthropic_raw(user_content: str, *, client: Any | None = None) -> dict[str, Any]:
    client = client or _get_anthropic_client()
    try:
        resp = _anthropic_call(client, user_content)
    except PlannerError:
        raise
    except Exception as exc:  # noqa: BLE001 - anthropic.APIStatusError / APIConnectionError / etc
        raise PlannerError(f"anthropic api error: {exc}") from exc
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "record_plan":
            return dict(block.input)
    raise PlannerError(
        f"no record_plan tool_use in response "
        f"(stop_reason={getattr(resp, 'stop_reason', None)})"
    )


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def _validate(raw: dict) -> Plan:
    raw_actions = raw.get("actions") or []
    cleaned: list[Action] = []
    dropped = 0
    for a in raw_actions[:MAX_ACTIONS]:
        if not isinstance(a, dict):
            log.warning("dropped non-dict action: %r", a)
            dropped += 1
            continue
        a = {k: v for k, v in a.items() if v not in ("", None)}
        try:
            cleaned.append(Action.model_validate(a))
        except ValidationError as exc:
            log.warning("dropped unparseable action: %s / %s", exc, a)
            dropped += 1  # drop an unparseable action, keep the rest
    reply = raw.get("reply") or None
    if len(raw_actions) > MAX_ACTIONS:
        reply = ((reply + " ") if reply else "") + f"(only did the first {MAX_ACTIONS})"
    if dropped:
        reply = ((reply + " ") if reply else "") + "(couldn't understand one part of that)"
    return Plan(actions=cleaned, reply=reply)


def make_plan(text: str, *, history: list[dict], tasks: list[dict],
              now: datetime, tz: str, provider: str | None = None,
              client: Any | None = None) -> Plan:
    provider = provider or settings.llm_provider
    user_content = _build_user_content(text, history=history, tasks=tasks, now=now, tz=tz)
    try:
        if provider == "anthropic":
            raw = _anthropic_raw(user_content, client=client)
        else:
            raw = _gemini_raw(user_content, client=client)
    except PlannerError as exc:
        log.error("planner llm error (%s): %s", provider, exc)
        return Plan(actions=[], reply=_TROUBLE)
    if not isinstance(raw, dict):
        return Plan(actions=[], reply=_TROUBLE)
    return _validate(raw)
