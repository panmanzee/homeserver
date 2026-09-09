from __future__ import annotations

from dataclasses import dataclass

from .config import settings
from .extract import Page

_SEPARATORS = ("\n\n", "\n", ". ", " ")


@dataclass(frozen=True)
class Chunk:
    text: str
    page: int
    ord: int


def _flatten(pages: list[Page]) -> tuple[str, list[int]]:
    """Return the concatenated text and, per character, the page it came from."""
    buf: list[str] = []
    page_of: list[int] = []
    for pg in pages:
        t = pg.text
        if buf and t:
            buf.append("\n\n")
            page_of.extend([pg.number, pg.number])
        buf.append(t)
        page_of.extend([pg.number] * len(t))
    return "".join(buf), page_of


def _split_point(s: str, limit: int) -> int:
    """Index to cut `s` at, ≤ limit, preferring a natural boundary."""
    if len(s) <= limit:
        return len(s)
    window = s[:limit]
    for sep in _SEPARATORS:
        idx = window.rfind(sep)
        if idx > 0:
            return idx + len(sep)
    return limit  # hard cut — a single unbroken run longer than the limit


def chunk_pages(pages: list[Page], *, chars: int | None = None,
                overlap: int | None = None) -> list[Chunk]:
    chars = chars if chars is not None else settings.rag_chunk_chars
    overlap = overlap if overlap is not None else settings.rag_chunk_overlap
    text, page_of = _flatten(pages)

    chunks: list[Chunk] = []
    start = 0
    ordn = 0
    n = len(text)
    while start < n:
        cut = start + _split_point(text[start:], chars)
        piece = text[start:cut]
        stripped_piece = piece.strip()
        if stripped_piece:
            # Find where the stripped text starts in the original piece
            stripped_start = piece.find(stripped_piece)
            page = page_of[start + stripped_start] if start + stripped_start < len(page_of) else (pages[-1].number if pages else 1)
            chunks.append(Chunk(stripped_piece, page, ordn))
            ordn += 1
        if cut >= n:
            break
        start = max(cut - overlap, start + 1)
    return chunks
