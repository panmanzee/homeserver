from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from .config import settings
from .retrieve import RetrievedChunk

log = logging.getLogger("rag.answer")
_client: Any | None = None

TROUBLE = "I'm having trouble reaching the model right now — try again in a moment."
NOT_COVERED = "The material doesn't cover that."


class AnswerError(RuntimeError):
    """The answer could not be generated (e.g. no API key)."""


_SYSTEM = f"""You answer questions strictly from the provided passages of the \
user's own study material. Rules:
- Use ONLY the passages. Do not add outside knowledge.
- Cite every claim inline as [<filename> p.<page>], matching the passage used.
- If the passages do not contain the answer, reply with exactly \
"{NOT_COVERED}" and nothing else — do not guess.
- Be concise: a short paragraph or a few bullets."""


@dataclass(frozen=True)
class Source:
    filename: str
    page: int
    snippet: str


@dataclass(frozen=True)
class Answer:
    text: str
    sources: list[Source]


def _get_client() -> Any:
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise AnswerError("GEMINI_API_KEY is not set")
        from google import genai
        _client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options={"timeout": int(settings.http_timeout * 1000)},
        )
    return _client


def _should_retry(exc: BaseException) -> bool:
    s = str(exc).lower()
    return any(x in s for x in ("429", "resource_exhausted", "500", "503",
                                "internal", "unavailable", "backend"))


@retry(retry=retry_if_exception(_should_retry), stop=stop_after_attempt(4),
       wait=wait_exponential(min=2, max=30), reraise=True)
def _generate(client: Any, prompt: str) -> str:
    resp = client.models.generate_content(
        model=settings.rag_gen_model,
        contents=prompt,
        config={"system_instruction": _SYSTEM,
                "temperature": settings.rag_gen_temperature,
                "max_output_tokens": 800},
    )
    return (resp.text or "").strip()


def _sources(chunks: list[RetrievedChunk]) -> list[Source]:
    seen: set[tuple[str, int]] = set()
    out: list[Source] = []
    for c in chunks:
        key = (c.filename, c.page)
        if key not in seen:
            seen.add(key)
            out.append(Source(c.filename, c.page, c.text[:200]))
    return out


def answer(question: str, chunks: list[RetrievedChunk], *,
           client: Any | None = None) -> Answer:
    if not chunks:
        return Answer("I couldn't find anything in your material about that.", [])
    body = "\n\n".join(
        f"[{i}] ({c.filename} p.{c.page})\n{c.text}" for i, c in enumerate(chunks, 1)
    )
    prompt = f"PASSAGES:\n{body}\n\nQUESTION: {question}"
    try:
        client = client or _get_client()
        text = _generate(client, prompt)
    except Exception as exc:  # noqa: BLE001
        log.error("generation failed: %s", exc)
        return Answer(TROUBLE, [])
    if not text:
        return Answer(TROUBLE, [])
    if text.strip().lower().startswith(NOT_COVERED.rstrip(".").lower()):
        return Answer(text, [])
    return Answer(text, _sources(chunks))
