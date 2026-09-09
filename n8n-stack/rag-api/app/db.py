"""Data-access layer: pool + typed helpers. Each helper owns a short transaction."""

from __future__ import annotations

import atexit
import pathlib
from typing import Any

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import settings

_SCHEMA = (pathlib.Path(__file__).parent.parent / "schema.sql").read_text()


def _configure(conn: psycopg.Connection) -> None:
    register_vector(conn)


pool = ConnectionPool(
    settings.database_url,
    min_size=0,
    max_size=5,
    open=True,
    configure=_configure,
    kwargs={"row_factory": dict_row, "connect_timeout": 10},
    timeout=15,
)


def ping() -> bool:
    with pool.connection() as conn:
        conn.execute("SELECT 1")
    return True


def apply_schema() -> None:
    # `vector` must exist before `register_vector` runs on pooled connections,
    # so apply the schema on a raw connection first.
    with psycopg.connect(settings.database_url, connect_timeout=10) as conn:
        conn.execute(_SCHEMA)
        conn.commit()


_SEARCH_COLS = ("c.id, c.document_id, d.filename, c.page, c.text")


def vector_search(qvec: list[float], n: int) -> list[dict[str, Any]]:
    with pool.connection() as conn:
        rows = conn.execute(
            f"SELECT {_SEARCH_COLS} FROM chunks c JOIN documents d ON d.id = c.document_id "
            "ORDER BY c.embedding <=> %s::vector LIMIT %s",
            (qvec, n),
        ).fetchall()
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def keyword_search(qtext: str, n: int) -> list[dict[str, Any]]:
    with pool.connection() as conn:
        q = conn.execute("SELECT websearch_to_tsquery('english', %s)::text AS q",
                         (qtext,)).fetchone()
        if not q or not q["q"]:
            return []
        rows = conn.execute(
            f"SELECT {_SEARCH_COLS} FROM chunks c JOIN documents d ON d.id = c.document_id "
            "WHERE c.tsv @@ websearch_to_tsquery('english', %s) "
            "ORDER BY ts_rank_cd(c.tsv, websearch_to_tsquery('english', %s)) DESC LIMIT %s",
            (qtext, qtext, n),
        ).fetchall()
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def stats() -> dict[str, Any]:
    with pool.connection() as conn:
        d = conn.execute("SELECT count(*) n, max(ingested_at) t FROM documents").fetchone()
        c = conn.execute("SELECT count(*) n FROM chunks").fetchone()
        u = conn.execute("SELECT n FROM usage WHERE day = current_date").fetchone()
    return {"documents": d["n"], "chunks": c["n"],
            "last_ingested_at": d["t"].isoformat() if d["t"] else None,
            "questions_today": u["n"] if u else 0}


atexit.register(pool.close)
