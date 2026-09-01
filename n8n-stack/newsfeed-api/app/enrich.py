"""LLM enrichment: factual Thai summary + structured tags for one news item.

`call_llm` is the only entry point. The provider is pluggable via
`LLM_PROVIDER` (default `gemini`, free tier; `anthropic` also supported). Both
paths ask for the same structured shape and hand it to the same Pydantic
validation before it reaches the database.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import anthropic
from pydantic import BaseModel, Field, ValidationError, field_validator
from tenacity import (
    retry,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import settings

EVENT_TYPES = (
    "earnings", "guidance", "product", "m&a", "regulation",
    "legal", "macro", "management", "partnership", "other",
)

SYSTEM_PROMPT = """\
You condense news articles into factual notes for a personal research database.
The reader makes their own investment decisions; your job is only to summarize.

Hard rules:
- Write `summary` and `sentiment_rationale` in **Thai** (ภาษาไทย), whatever the
  article's language. Keep company names, ticker symbols, product names, and
  financial terms with no natural Thai equivalent in their original form
  (e.g. "Fed", "EPS", "AAPL"). `topics` stay as lowercase English slugs.
- Report ONLY what the article states. Do not add outside facts or figures.
- Do NOT predict prices or price direction.
- Do NOT give buy / sell / hold advice or state or imply price targets.
- If the article is opinion or analysis, attribute its claims ("the author
  argues that...", "analysts cited say...") without endorsing them.
- `sentiment` is the factual tone of the news toward the primary company or
  asset (an earnings miss is "negative"; a beat is "positive"; a routine
  filing is "neutral"). It is never an investment recommendation.
- `importance` rates how significant this news is for a general markets / world
  reader. This is a factual editorial judgment about newsworthiness, never
  advice:
    - "breaking": front-page, market-wide news that a reader would want pushed
      to their phone within the hour. Roughly 1 in 30 articles. Examples: a
      central bank changes rates or policy; a top-10-by-value company announces
      a merger, bankruptcy, CEO exit, or major miss; a major regulatory or
      antitrust ruling; a surprise in headline macro data (CPI, jobs, GDP); a
      large geopolitical or disaster event. A single company's product launch,
      a mid-cap's earnings, or an analyst call is NOT breaking.
    - "notable": meaningful company- or sector-level news worth knowing today.
    - "routine": incremental updates, a single analyst's note, opinion / advice
      columns, explainers, minor or narrow items.
  Default to "routine". Use "notable" only if it clearly clears that bar, and
  "breaking" only if it clearly clears the bar above. When unsure, go one level
  lower.
- `tickers`: include a stock symbol only when you are confident the article is
  about that specific listed company. Use uppercase symbols. Empty list is fine.
- `topics`: 1-5 short lowercase tags (e.g. "ai-chips", "interest-rates").

Produce exactly one structured result with these fields: summary, tickers,
companies, topics, event_type, sentiment, sentiment_rationale, importance."""

PROMPT_INSTRUCTIONS_HASH = "v4"  # bump SYSTEM_PROMPT + this together

# Single source of truth for the output shape. Anthropic wraps it as a tool;
# Gemini takes it as a response_schema.
RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "array",
            "items": {"type": "string"},
            "description": "2-4 factual bullet points in Thai, each a full sentence.",
        },
        "tickers": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Uppercase stock symbols the article is clearly about.",
        },
        "companies": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Full company / organization names that are subjects.",
        },
        "topics": {
            "type": "array",
            "items": {"type": "string"},
            "description": "1-5 short lowercase english topic slugs.",
        },
        "event_type": {"type": "string", "enum": list(EVENT_TYPES)},
        "sentiment": {"type": "string", "enum": ["positive", "negative", "neutral"]},
        "sentiment_rationale": {
            "type": "string",
            "description": "One factual sentence in Thai grounded in the article.",
        },
        "importance": {"type": "string", "enum": ["breaking", "notable", "routine"]},
    },
    "required": [
        "summary", "tickers", "companies", "topics",
        "event_type", "sentiment", "sentiment_rationale", "importance",
    ],
}

ENRICHMENT_TOOL: dict[str, Any] = {
    "name": "record_enrichment",
    "description": "Record the factual summary and structured tags for the article.",
    "input_schema": {**RESPONSE_SCHEMA, "additionalProperties": False},
}


def _unwrap_scalar(v: Any) -> Any:
    """Models sometimes wrap a single-choice field in a list, or in a string
    that itself contains a JSON array (e.g. '["product"]'). Return the scalar."""
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = json.loads(s)
            except ValueError:
                return v
            if isinstance(parsed, list) and parsed:
                return parsed[0]
        return v
    if isinstance(v, (list, tuple)):
        return v[0] if v else None
    return v


class NewsEnrichment(BaseModel):
    summary: list[str] = Field(min_length=1)
    tickers: list[str] = []
    companies: list[str] = []
    topics: list[str] = []
    # The enum fields tolerate a missing / malformed model response: a usable
    # summary is never dropped over a miscategorised tag. `raw_response` keeps
    # exactly what the model said.
    event_type: Literal[EVENT_TYPES] = "other"  # type: ignore[valid-type]
    sentiment: Literal["positive", "negative", "neutral"] = "neutral"
    sentiment_rationale: str = ""
    importance: Literal["breaking", "notable", "routine"] = "routine"

    @field_validator("event_type", mode="before")
    @classmethod
    def _clean_event_type(cls, v: Any) -> Any:
        v = _unwrap_scalar(v)
        return v if v in EVENT_TYPES else "other"

    @field_validator("sentiment", mode="before")
    @classmethod
    def _clean_sentiment(cls, v: Any) -> Any:
        v = _unwrap_scalar(v)
        return v if v in ("positive", "negative", "neutral") else "neutral"

    @field_validator("importance", mode="before")
    @classmethod
    def _clean_importance(cls, v: Any) -> Any:
        v = _unwrap_scalar(v)
        return v if v in ("breaking", "notable", "routine") else "routine"


@dataclass
class EnrichmentResult:
    data: NewsEnrichment
    input_tokens: int | None
    output_tokens: int | None
    raw: dict[str, Any]
    model: str


class EnrichmentError(RuntimeError):
    """Raised when the model cannot produce a usable structured result."""


def current_model() -> str:
    if settings.llm_provider == "gemini":
        return settings.gemini_model
    if settings.llm_provider == "anthropic":
        return settings.claude_model
    return settings.llm_provider


_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def normalize_symbol(value: str) -> str | None:
    sym = value.strip().upper().lstrip("$")
    return sym if _SYMBOL_RE.match(sym) else None


def _dedupe(values: list[str], *, lower: bool = False) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        v = v.strip().lower() if lower else v.strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out


def clean_output(data: NewsEnrichment) -> NewsEnrichment:
    symbols = [s for s in (normalize_symbol(t) for t in data.tickers) if s]
    return data.model_copy(
        update={
            "summary": [s.strip() for s in data.summary if s.strip()],
            "tickers": _dedupe(symbols),
            "companies": _dedupe(data.companies),
            "topics": _dedupe(data.topics, lower=True)[:5],
        }
    )


def ticker_rows(data: NewsEnrichment) -> list[dict[str, str]]:
    """Map cleaned tickers to `tickers` upsert rows.

    `price_symbol` defaults to the plain symbol (correct for US listings on
    Twelve Data / Yahoo). Fix non-US listings by hand in the `tickers` table.
    """
    rows: list[dict[str, str]] = []
    for i, sym in enumerate(data.tickers):
        row: dict[str, str] = {"symbol": sym, "price_symbol": sym}
        if i < len(data.companies):
            row["name"] = data.companies[i]
        rows.append(row)
    return rows


def build_user_content(item: dict[str, Any], body: str) -> str:
    published = item.get("published_at")
    if isinstance(published, datetime):
        published = published.date().isoformat()
    lines = [
        f"TITLE: {item.get('title', '')}",
        f"SOURCE: {item.get('feed_name', 'unknown')}",
        f"PUBLISHED: {published or 'unknown'}",
        f"URL: {item.get('url', '')}",
        "",
        "ARTICLE:",
        body or "(no body text available)",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Anthropic provider
# --------------------------------------------------------------------------- #
_anthropic_client: anthropic.Anthropic | None = None


def _get_anthropic_client() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        if not settings.anthropic_api_key:
            raise EnrichmentError("ANTHROPIC_API_KEY is not set")
        _anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client


@retry(
    retry=retry_if_exception_type(
        (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APIConnectionError)
    ),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
def _anthropic_create(client: anthropic.Anthropic, user_content: str) -> Any:
    return client.messages.create(
        model=settings.claude_model,
        max_tokens=settings.llm_max_tokens,
        system=SYSTEM_PROMPT,
        tools=[ENRICHMENT_TOOL],
        tool_choice={"type": "tool", "name": "record_enrichment"},
        messages=[{"role": "user", "content": user_content}],
    )


def _generate_anthropic(
    user_content: str, *, client: Any | None = None
) -> tuple[dict[str, Any], int | None, int | None, str]:
    client = client or _get_anthropic_client()
    try:
        response = _anthropic_create(client, user_content)
    except anthropic.APIStatusError as exc:  # non-retryable 4xx or exhausted retries
        raise EnrichmentError(f"anthropic api error: {exc}") from exc

    if getattr(response, "stop_reason", None) == "refusal":
        raise EnrichmentError("model refused to process this article")

    tool_block = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_block is None:
        raise EnrichmentError(
            f"no tool_use in response (stop_reason={getattr(response, 'stop_reason', None)})"
        )

    usage = getattr(response, "usage", None)
    return (
        dict(tool_block.input),
        getattr(usage, "input_tokens", None),
        getattr(usage, "output_tokens", None),
        settings.claude_model,
    )


# --------------------------------------------------------------------------- #
# Gemini provider (default)
# --------------------------------------------------------------------------- #
_gemini_client: Any | None = None
_GEMINI_SAFETY_CATEGORIES = (
    "HARM_CATEGORY_HARASSMENT",
    "HARM_CATEGORY_HATE_SPEECH",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_DANGEROUS_CONTENT",
)


def _get_gemini_client() -> Any:
    global _gemini_client
    if _gemini_client is None:
        if not settings.gemini_api_key:
            raise EnrichmentError("GEMINI_API_KEY is not set")
        from google import genai

        _gemini_client = genai.Client(api_key=settings.gemini_api_key)
    return _gemini_client


def _gemini_should_retry(exc: BaseException) -> bool:
    from google.genai import errors as genai_errors

    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.ClientError) and getattr(exc, "code", None) == 429:
        return True
    return False


@retry(
    retry=retry_if_exception(_gemini_should_retry),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
def _gemini_generate(client: Any, user_content: str) -> Any:
    from google.genai import types

    return client.models.generate_content(
        model=settings.gemini_model,
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
            temperature=0.0,
            max_output_tokens=settings.llm_max_tokens,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            safety_settings=[
                types.SafetySetting(category=c, threshold="BLOCK_NONE")
                for c in _GEMINI_SAFETY_CATEGORIES
            ],
        ),
    )


def _generate_gemini(
    user_content: str, *, client: Any | None = None
) -> tuple[dict[str, Any], int | None, int | None, str]:
    client = client or _get_gemini_client()
    try:
        response = _gemini_generate(client, user_content)
    except EnrichmentError:
        raise
    except Exception as exc:  # noqa: BLE001 - google.genai.errors.* + anything else
        raise EnrichmentError(f"gemini api error: {exc}") from exc

    text = getattr(response, "text", None)
    if not text:
        finish = None
        try:
            finish = response.candidates[0].finish_reason
        except (AttributeError, IndexError, TypeError):
            pass
        raise EnrichmentError(f"gemini returned no text (finish_reason={finish})")

    try:
        raw = json.loads(text)
    except ValueError as exc:
        raise EnrichmentError(f"gemini returned non-JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise EnrichmentError(f"gemini returned a {type(raw).__name__}, expected object")

    usage = getattr(response, "usage_metadata", None)
    return (
        raw,
        getattr(usage, "prompt_token_count", None),
        getattr(usage, "candidates_token_count", None),
        settings.gemini_model,
    )


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def call_llm(
    item: dict[str, Any],
    body: str,
    *,
    client: Any | None = None,
    provider: str | None = None,
) -> EnrichmentResult:
    provider = provider or settings.llm_provider
    user_content = build_user_content(item, body)

    if provider == "gemini":
        raw, in_tok, out_tok, model = _generate_gemini(user_content, client=client)
    elif provider == "anthropic":
        raw, in_tok, out_tok, model = _generate_anthropic(user_content, client=client)
    else:
        raise EnrichmentError(f"unknown LLM_PROVIDER: {provider!r}")

    try:
        data = clean_output(NewsEnrichment.model_validate(raw))
    except ValidationError as exc:
        raise EnrichmentError(f"schema validation failed: {exc}") from exc

    return EnrichmentResult(
        data=data,
        input_tokens=in_tok,
        output_tokens=out_tok,
        raw=data.model_dump(),
        model=model,
    )
