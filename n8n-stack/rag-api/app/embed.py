from __future__ import annotations

import logging
from typing import Any

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from .config import settings

log = logging.getLogger("rag.embed")
_client: Any | None = None


class EmbedError(RuntimeError):
    """Embeddings could not be produced."""


def _get_client() -> Any:
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise EmbedError("GEMINI_API_KEY is not set")
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
def _embed_batch(client: Any, texts: list[str], task_type: str) -> list[list[float]]:
    resp = client.models.embed_content(
        model=settings.rag_embed_model,
        contents=texts,
        config={"task_type": task_type,
                "output_dimensionality": settings.rag_embed_dims},
    )
    return [list(e.values) for e in resp.embeddings]


def embed_documents(texts: list[str], *, client: Any | None = None) -> list[list[float]]:
    if not texts:
        return []
    client = client or _get_client()
    out: list[list[float]] = []
    b = settings.rag_embed_batch
    for i in range(0, len(texts), b):
        batch = texts[i:i + b]
        try:
            out.extend(_embed_batch(client, batch, "RETRIEVAL_DOCUMENT"))
        except Exception as exc:  # noqa: BLE001
            raise EmbedError(f"embedding failed: {exc}") from exc
    return out


def embed_query(text: str, *, client: Any | None = None) -> list[float]:
    client = client or _get_client()
    try:
        return _embed_batch(client, [text], "RETRIEVAL_QUERY")[0]
    except Exception as exc:  # noqa: BLE001
        raise EmbedError(f"embedding failed: {exc}") from exc
