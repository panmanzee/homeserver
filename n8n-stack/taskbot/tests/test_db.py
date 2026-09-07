import os
import pytest

psycopg = pytest.importorskip("psycopg")
DB_URL = os.environ.get("TASKBOT_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="set TASKBOT_TEST_DB_URL to run db tests")


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    import importlib
    from app import config as cfg_mod
    importlib.reload(cfg_mod)           # rebuild the Settings singleton with the scratch URL
    from app import db as db_mod
    importlib.reload(db_mod)            # db.py re-runs `from .config import settings` -> fresh
    db_mod.pool.open()
    with db_mod.pool.connection() as c:
        c.execute("DROP TABLE IF EXISTS tasks, bot_state, google_oauth, message_log CASCADE")
    db_mod.apply_schema()
    yield db_mod
    db_mod.pool.close()
    importlib.reload(cfg_mod)           # restore for any later test
    importlib.reload(db_mod)


def test_offset_roundtrip(db):
    assert db.get_offset() == 0
    db.set_offset(42)
    assert db.get_offset() == 42


def test_create_and_complete_task(db):
    t = db.create_task(title="math homework")
    assert t["status"] == "pending" and t["id"]
    done = db.set_status(t["id"], "done")
    assert done["status"] == "done" and done["completed_at"] is not None


def test_open_tasks_excludes_done(db):
    a = db.create_task(title="a")
    db.create_task(title="b")
    db.set_status(a["id"], "done")
    titles = [r["title"] for r in db.open_tasks()]
    assert titles == ["b"]


def test_overdue(db):
    from datetime import date, timedelta
    db.create_task(title="old", due_date=date.today() - timedelta(days=2))
    db.create_task(title="today", due_date=date.today())
    assert [r["title"] for r in db.overdue_tasks(date.today())] == ["old"]


def test_google_oauth_upsert(db):
    assert db.get_google_oauth() is None
    db.upsert_google_oauth("rt-1", "cal-1")
    db.upsert_google_oauth("rt-2", "cal-1")
    row = db.get_google_oauth()
    assert row["refresh_token"] == "rt-2"


def test_reschedule_date_only_keeps_time(db):
    from datetime import datetime, timedelta, timezone
    start = datetime(2026, 9, 6, 23, 0, tzinfo=timezone.utc)
    t = db.create_task(title="gym", scheduled_start=start,
                       scheduled_end=start + timedelta(hours=1))
    from datetime import date
    moved = db.reschedule_task(t["id"], due_date=date(2026, 9, 11))
    assert moved["due_date"] == date(2026, 9, 11)
    assert moved["scheduled_start"] == start          # F6: time not nulled
    assert moved["scheduled_end"] == start + timedelta(hours=1)


def test_prune_message_log(db):
    with db.pool.connection() as c:
        c.execute("INSERT INTO message_log (direction, text, created_at) "
                  "VALUES ('in', 'old', now() - interval '40 days'), "
                  "('in', 'fresh', now())")
    removed = db.prune_message_log(30)
    assert removed == 1
    with db.pool.connection() as c:
        left = [r["text"] for r in c.execute("SELECT text FROM message_log ORDER BY id").fetchall()]
    assert left == ["fresh"]


def test_recent_turns_oldest_first_and_limited(db):
    with db.pool.connection() as c:
        c.execute("INSERT INTO message_log (direction, text) VALUES "
                  "('in','m1'),('out','m2'),('in','m3'),('out','m4'),('in','m5')")
    turns = db.recent_turns(limit=3)
    assert [t["text"] for t in turns] == ["m3", "m4", "m5"]
    assert [t["direction"] for t in turns] == ["in", "out", "in"]


def test_rename_task(db):
    t = db.create_task(title="ml homwork")
    r = db.rename_task(t["id"], "ML homework")
    assert r["title"] == "ML homework"


def test_set_task_timing_clears_time_for_all_day(db):
    from datetime import datetime, timezone, date
    start = datetime(2026, 9, 7, 19, 0, tzinfo=timezone.utc)
    t = db.create_task(title="ml homework", scheduled_start=start,
                       scheduled_end=start.replace(hour=20))
    r = db.set_task_timing(t["id"], due_date=date(2026, 9, 7),
                           scheduled_start=None, scheduled_end=None)
    assert r["scheduled_start"] is None and r["scheduled_end"] is None
    assert r["due_date"] == date(2026, 9, 7)


def test_set_task_timing_sets_time_from_all_day(db):
    from datetime import datetime, timezone
    t = db.create_task(title="call", due_date=None)
    start = datetime(2026, 9, 8, 9, 0, tzinfo=timezone.utc)
    r = db.set_task_timing(t["id"], due_date=None, scheduled_start=start,
                           scheduled_end=start.replace(hour=10))
    assert r["scheduled_start"] == start and r["due_date"] is None
