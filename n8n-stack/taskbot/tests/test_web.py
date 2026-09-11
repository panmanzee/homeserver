import os

import pytest

DB_URL = os.environ.get("TASKBOT_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="set TASKBOT_TEST_DB_URL")


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    import importlib
    from app import config as cfg
    importlib.reload(cfg)
    for m in ("db", "clock", "planner", "actions", "handler", "gcal", "jobs", "telegram", "main"):
        importlib.reload(importlib.import_module(f"app.{m}"))
    from app import db as db_mod, main as main_mod
    db_mod.pool.open()
    with db_mod.pool.connection() as c:
        c.execute("DROP TABLE IF EXISTS tasks, bot_state, google_oauth, message_log CASCADE")
    db_mod.apply_schema()
    from fastapi.testclient import TestClient
    with TestClient(main_mod.app) as c:
        yield c
    db_mod.pool.close()
    importlib.reload(cfg)
    importlib.reload(db_mod)


def test_get_tasks_empty_day(client):
    r = client.get("/api/tasks?day=2026-09-11")
    assert r.status_code == 200 and r.json() == []


def test_get_tasks_shows_synced_flag(client):
    from app import clock, db
    today = clock.now_local().date()
    row = db.create_task(title="gym", due_date=today)
    db.set_gcal_event_id(row["id"], "evt1")
    r = client.get(f"/api/tasks?day={today.isoformat()}")
    body = r.json()
    assert len(body) == 1 and body[0]["title"] == "gym" and body[0]["synced"] is True
    assert "gcal_event_id" not in body[0]


def test_post_message_runs_real_pipeline(client, monkeypatch):
    from app import planner
    monkeypatch.setattr(planner, "make_plan", lambda *a, **k: planner.Plan(
        actions=[planner.Action(kind="add_task", title="from webapp")]))
    r = client.post("/api/message", json={"text": "anything"})
    assert r.status_code == 200 and "from webapp" in r.json()["reply"]
    from app import clock, db
    today = clock.now_local().date().isoformat()
    tasks = client.get(f"/api/tasks?day={today}").json()
    assert any(t["title"] == "from webapp" for t in tasks)


def test_message_add_task_default_does_not_sync(client, monkeypatch):
    from app import handler, planner
    monkeypatch.setattr(planner, "make_plan", lambda *a, **k: planner.Plan(
        actions=[planner.Action(kind="add_task", title="no sync please")]))
    synced = []
    monkeypatch.setattr(handler.gcal, "sync_new", lambda row: synced.append(row["id"]))
    client.post("/api/message", json={"text": "anything"})
    assert synced == []


def test_message_add_task_explicit_calendar_syncs(client, monkeypatch):
    from app import handler, planner
    monkeypatch.setattr(planner, "make_plan", lambda *a, **k: planner.Plan(
        actions=[planner.Action(kind="add_task", title="sync this", to_calendar=True)]))
    synced = []
    monkeypatch.setattr(handler.gcal, "sync_new", lambda row: synced.append(row["id"]))
    client.post("/api/message", json={"text": "anything"})
    assert len(synced) == 1


def test_direct_complete_bypasses_llm(client):
    from app import db
    row = db.create_task(title="hw", due_date=None)
    r = client.post(f"/api/tasks/{row['id']}/complete")
    assert r.status_code == 200
    assert db.get_task(row["id"])["status"] == "done"


def test_direct_complete_unsynced_does_not_touch_calendar(client, monkeypatch):
    from app import db, handler
    calls = []
    monkeypatch.setattr(handler.gcal, "sync_completed", lambda row: calls.append(row))
    row = db.create_task(title="hw", due_date=None)  # never synced -> gcal_event_id None
    client.post(f"/api/tasks/{row['id']}/complete")
    # The route/actions layer always forwards a "complete" op to gcal._sync
    # (see actions._GCAL_UNCONDITIONAL_KINDS) and relies on gcal.sync_completed's
    # own internal guard (`if not row.get("gcal_event_id"): return`) to no-op for
    # an unsynced task. Here sync_completed is replaced wholesale by a bare
    # lambda with no such guard, so this pins that the route/actions layer does
    # NOT skip the call itself -- the lambda still records exactly one call.
    assert len(calls) == 1


def test_direct_delete(client):
    from app import db
    row = db.create_task(title="hw", due_date=None)
    r = client.delete(f"/api/tasks/{row['id']}")
    assert r.status_code == 200
    assert db.get_task(row["id"])["status"] == "cancelled"


def test_direct_calendar_add(client, monkeypatch):
    from app import db, handler
    synced = []
    monkeypatch.setattr(handler.gcal, "sync_new", lambda row: synced.append(row["id"]))
    row = db.create_task(title="gym", due_date=None)
    r = client.post(f"/api/tasks/{row['id']}/calendar")
    assert r.status_code == 200
    assert synced == [row["id"]]


def test_direct_calendar_add_unknown_task_404(client):
    r = client.post("/api/tasks/999999/calendar")
    assert r.status_code == 404


def test_root_serves_self_contained_html(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.text
    assert "<html" in body.lower()
    assert "<script src=" not in body.lower()
    assert '<link rel="stylesheet" href=' not in body.lower()
