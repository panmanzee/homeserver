from __future__ import annotations

from dataclasses import dataclass

from . import db
from .config import settings


@dataclass(frozen=True)
class RetrievedChunk:
    id: int
    filename: str
    page: int
    text: str
    score: float


def rrf(result_lists: list[list[dict]], *, k0: int, k: int) -> list[dict]:
    scored: dict[int, dict] = {}
    for rows in result_lists:
        for rank, row in enumerate(rows, 1):
            rid = row["id"]
            entry = scored.setdefault(rid, {**row, "score": 0.0})
            entry["score"] += 1.0 / (k0 + rank)
    return sorted(scored.values(), key=lambda r: r["score"], reverse=True)[:k]


def search(qvec: list[float], qtext: str, *, k: int | None = None) -> list[RetrievedChunk]:
    k = k if k is not None else settings.rag_retrieve_k
    vec = db.vector_search(qvec, settings.rag_candidates)
    kw = db.keyword_search(qtext, settings.rag_candidates)
    lists = [vec, kw] if kw else [vec]
    fused = rrf(lists, k0=settings.rag_rrf_k0, k=k)
    return [RetrievedChunk(r["id"], r["filename"], r["page"], r["text"], r["score"])
            for r in fused]
