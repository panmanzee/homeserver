from __future__ import annotations

import pathlib
from dataclasses import dataclass


class ExtractError(RuntimeError):
    """A file could not be read into pages."""


@dataclass(frozen=True)
class Page:
    number: int          # 1-based
    text: str


def extract_file(path: str | pathlib.Path) -> list[Page]:
    path = pathlib.Path(path)
    ext = path.suffix.lower()
    if ext in (".txt", ".md"):
        return [Page(1, path.read_text(encoding="utf-8", errors="replace"))]
    if ext == ".pdf":
        try:
            import fitz  # PyMuPDF
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise ExtractError("PyMuPDF not installed") from exc
        try:
            doc = fitz.open(path)
        except Exception as exc:  # noqa: BLE001 - fitz raises assorted errors
            raise ExtractError(f"could not open {path.name}: {exc}") from exc
        try:
            return [Page(i + 1, doc.load_page(i).get_text("text"))
                    for i in range(doc.page_count)]
        finally:
            doc.close()
    raise ExtractError(f"unsupported file type: {ext or '(none)'}")
