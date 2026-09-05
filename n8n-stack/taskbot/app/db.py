"""Data-access layer: pool + typed helpers. Each helper owns a short transaction."""

from __future__ import annotations

import pathlib
from datetime import date, datetime
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .config import settings

pool = ConnectionPool(
    settings.database_url,
    min_size=0,
    max_size=5,
    open=False,
    kwargs={"row_factory": dict_row},
)

_SCHEMA = (pathlib.Path(__file__).parent.parent / "schema.sql").read_text()


def ping() -> bool:
    with pool.connection() as conn:
        conn.execute("SELECT 1")
    return True


def apply_schema() -> None:
    with pool.connection() as conn:
        conn.execute(_SCHEMA)


# --- bot_state --------------------------------------------------------------
def get_offset() -> int:
    with pool.connection() as conn:
        row = conn.execute("SELECT tg_offset FROM bot_state WHERE id = 1").fetchone()
    return int(row["tg_offset"]) if row else 0


def set_offset(value: int) -> None:
    with pool.connection() as conn:
        conn.execute(
            "UPDATE bot_state SET tg_offset = %s, updated_at = now() WHERE id = 1",
            (value,),
        )


# --- message_log -----------------------------------------------------------
def log_message(direction: str, text: str, *, tg_message_id: int | None = None,
                intent: dict[str, Any] | None = None) -> None:
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO message_log (direction, tg_message_id, text, intent) "
            "VALUES (%s, %s, %s, %s)",
            (direction, tg_message_id, text, Jsonb(intent) if intent is not None else None),
        )


# --- tasks ----------------------------------------------------------------
def create_task(*, title: str, due_date: date | None = None,
                scheduled_start: datetime | None = None,
                scheduled_end: datetime | None = None,
                estimate_minutes: int | None = None,
                notes: str | None = None) -> dict[str, Any]:
    with pool.connection() as conn:
        row = conn.execute(
            "INSERT INTO tasks (title, notes, due_date, scheduled_start, scheduled_end, estimate_minutes) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING *",
            (title, notes, due_date, scheduled_start, scheduled_end, estimate_minutes),
        ).fetchone()
    return row


def get_task(task_id: int) -> dict[str, Any] | None:
    with pool.connection() as conn:
        return conn.execute("SELECT * FROM tasks WHERE id = %s", (task_id,)).fetchone()


def open_tasks() -> list[dict[str, Any]]:
    with pool.connection() as conn:
        return conn.execute(
            "SELECT id, title, due_date, scheduled_start FROM tasks "
            "WHERE status = 'pending' ORDER BY due_date NULLS LAST, scheduled_start NULLS LAST, id"
        ).fetchall()


def tasks_for_day(day: date) -> list[dict[str, Any]]:
    with pool.connection() as conn:
        return conn.execute(
            "SELECT * FROM tasks WHERE status = 'pending' AND "
            "(due_date = %s OR scheduled_start::date = %s) "
            "ORDER BY scheduled_start NULLS LAST, id",
            (day, day),
        ).fetchall()


def overdue_tasks(today: date) -> list[dict[str, Any]]:
    with pool.connection() as conn:
        return conn.execute(
            "SELECT * FROM tasks WHERE status = 'pending' AND due_date < %s ORDER BY due_date, id",
            (today,),
        ).fetchall()


def set_status(task_id: int, status: str) -> dict[str, Any] | None:
    completed = "completed_at = now()" if status == "done" else "completed_at = completed_at"
    with pool.connection() as conn:
        return conn.execute(
            f"UPDATE tasks SET status = %s, {completed}, updated_at = now() "
            "WHERE id = %s RETURNING *",
            (status, task_id),
        ).fetchone()


def reschedule_task(task_id: int, *, due_date: date | None = None,
                    scheduled_start: datetime | None = None,
                    scheduled_end: datetime | None = None) -> dict[str, Any] | None:
    with pool.connection() as conn:
        return conn.execute(
            "UPDATE tasks SET due_date = COALESCE(%s, due_date), "
            "scheduled_start = %s, scheduled_end = %s, updated_at = now() "
            "WHERE id = %s RETURNING *",
            (due_date, scheduled_start, scheduled_end, task_id),
        ).fetchone()


def set_gcal_event_id(task_id: int, event_id: str | None) -> None:
    with pool.connection() as conn:
        conn.execute(
            "UPDATE tasks SET gcal_event_id = %s, updated_at = now() WHERE id = %s",
            (event_id, task_id),
        )


# --- google_oauth --------------------------------------------------------
def get_google_oauth() -> dict[str, Any] | None:
    with pool.connection() as conn:
        return conn.execute("SELECT * FROM google_oauth WHERE id = 1").fetchone()


def upsert_google_oauth(refresh_token: str, calendar_id: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO google_oauth (id, refresh_token, calendar_id) VALUES (1, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET refresh_token = EXCLUDED.refresh_token, "
            "calendar_id = EXCLUDED.calendar_id, updated_at = now()",
            (refresh_token, calendar_id),
        )
