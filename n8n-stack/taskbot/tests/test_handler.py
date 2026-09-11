import pytest
from types import SimpleNamespace

from app import handler
from app.planner import Action, Plan


@pytest.fixture(autouse=True)
def wiring(monkeypatch):
    monkeypatch.setattr(handler.clock, "now_local", lambda: __import__("datetime").datetime(2026, 9, 7, 9, 0))
    monkeypatch.setattr(handler.clock, "tz_name", lambda: "Asia/Bangkok")
    monkeypatch.setattr(handler.clock, "is_utc", lambda: False)
    monkeypatch.setattr(handler.db, "recent_turns", lambda limit=6: [])
    monkeypatch.setattr(handler.db, "open_tasks", lambda: [])
    monkeypatch.setattr(handler.db, "log_message", lambda *a, **k: None)


@pytest.mark.asyncio
async def test_happy_path_joins_lines(monkeypatch):
    monkeypatch.setattr(handler.planner, "make_plan",
                        lambda *a, **k: Plan(actions=[Action(kind="add_task", title="x")]))
    monkeypatch.setattr(handler.actions, "execute_plan",
                        lambda plan: (["✅ added x", "✅ added y"], []))
    out = await handler.handle("do x and y", 1)
    assert out == "✅ added x\n✅ added y"


@pytest.mark.asyncio
async def test_inbound_logged_before_planning(monkeypatch):
    calls = []
    monkeypatch.setattr(handler.db, "log_message",
                        lambda direction, text, **k: calls.append((direction, text)))
    monkeypatch.setattr(handler.planner, "make_plan",
                        lambda *a, **k: calls.append(("plan", None)) or Plan(actions=[]))
    monkeypatch.setattr(handler.actions, "execute_plan", lambda p: (["hi"], []))
    await handler.handle("hello", 2)
    assert calls[0] == ("in", "hello") and ("plan", None) in calls
    assert calls.index(("in", "hello")) < calls.index(("plan", None))


@pytest.mark.asyncio
async def test_gcal_sync_called_per_op(monkeypatch):
    synced = []
    monkeypatch.setattr(handler.planner, "make_plan", lambda *a, **k: Plan(actions=[]))
    monkeypatch.setattr(handler.actions, "execute_plan",
                        lambda p: (["ok"], [("add_task", {"id": 1}), ("delete", {"id": 2})]))
    monkeypatch.setattr(handler.gcal, "sync_new", lambda row: synced.append(("new", row["id"])))
    monkeypatch.setattr(handler.gcal, "sync_deleted", lambda row: synced.append(("del", row["id"])))
    await handler.handle("x", 3)
    assert synced == [("new", 1), ("del", 2)]


@pytest.mark.asyncio
async def test_utc_nudge_once(monkeypatch):
    monkeypatch.setattr(handler.clock, "is_utc", lambda: True)
    monkeypatch.setattr(handler, "_warned_utc", False)
    monkeypatch.setattr(handler.planner, "make_plan", lambda *a, **k: Plan(actions=[]))
    monkeypatch.setattr(handler.actions, "execute_plan", lambda p: (["ok"], []))
    first = await handler.handle("x", 4)
    second = await handler.handle("y", 5)
    assert "TASKBOT_TZ" in first and "TASKBOT_TZ" not in second


@pytest.mark.asyncio
async def test_calendar_sync_dispatches_to_sync_new(monkeypatch):
    synced = []
    monkeypatch.setattr(handler.planner, "make_plan", lambda *a, **k: Plan(actions=[]))
    monkeypatch.setattr(handler.actions, "execute_plan",
                        lambda p: (["ok"], [("calendar_sync", {"id": 6})]))
    monkeypatch.setattr(handler.gcal, "sync_new", lambda row: synced.append(row["id"]))
    await handler.handle("x", 1)
    assert synced == [6]
