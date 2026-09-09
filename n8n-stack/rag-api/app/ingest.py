from __future__ import annotations

import hashlib
import logging
import pathlib
import sys
from dataclasses import dataclass, field

from . import db, embed
from .chunk import chunk_pages
from .config import settings
from .extract import extract_file

log = logging.getLogger("rag.ingest")
_EXTS = {".pdf", ".md", ".txt"}


@dataclass
class IngestReport:
    ingested: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    chunks_added: int = 0


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def ingest_path(root: str | pathlib.Path, *, only: list[str] | None = None,
                embed_fn=embed.embed_documents) -> IngestReport:
    root = pathlib.Path(root)
    report = IngestReport()
    known = db.document_hashes()
    files = ([root / f for f in only] if only
             else sorted(p for p in root.rglob("*") if p.suffix.lower() in _EXTS))
    for path in files:
        name = path.name
        try:
            digest = _sha256(path)
            if known.get(name) == digest:
                report.skipped.append(name)
                continue
            pages = extract_file(path)
            chunks = chunk_pages(pages)
            if not chunks:
                report.failed.append((name, "no extractable text (scanned PDF?)"))
                continue
            vectors = embed_fn([c.text for c in chunks])
            rows = [(c.page, c.ord, c.text, v) for c, v in zip(chunks, vectors)]
            db.upsert_document(name, digest, len(pages), rows)
            report.ingested.append(name)
            report.chunks_added += len(rows)
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the run
            log.warning("ingest failed for %s: %s", name, exc)
            report.failed.append((name, str(exc)))
    return report


def main() -> None:
    root = sys.argv[1] if len(sys.argv) > 1 else settings.rag_corpus_dir
    db.pool.open()
    r = ingest_path(root)
    print(f"ingested {len(r.ingested)}  skipped {len(r.skipped)}  "
          f"failed {len(r.failed)}  (+{r.chunks_added} chunks)")
    for n in r.ingested:
        print(f"  + {n}")
    for n, why in r.failed:
        print(f"  ! {n}: {why}")


if __name__ == "__main__":
    main()
