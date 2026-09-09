"""Data-access layer: pool + typed helpers. Each helper owns a short transaction."""

from __future__ import annotations

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
    open=False,
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
