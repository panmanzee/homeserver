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
