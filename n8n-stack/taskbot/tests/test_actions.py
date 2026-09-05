from datetime import date, datetime
import pytest

from app import actions
from app.intent import Intent


@pytest.fixture(autouse=True)
def frozen(monkeypatch):
    monkeypatch.setattr(actions.clock, "now_local", lambda: datetime(2026, 9, 6, 9, 0))


def test_add_task_defaults_today(monkeypatch):
    captured = {}
    monkeypatch.setattr(actions.db, "create_task",
                        lambda **kw: captured.update(kw) or {"id": 1, "title": kw["title"]})
    msg, _ = actions.dispatch(Intent(action="add_task", title="math homework"))
    assert captured["due_date"] == date(2026, 9, 6)
    assert "math homework" in msg and "today" in msg


def test_add_event_sets_times(monkeypatch):
    captured = {}
    monkeypatch.setattr(actions.db, "create_task",
                        lambda **kw: captured.update(kw) or {"id": 2, "title": kw["title"]})
    msg, _ = actions.dispatch(Intent(action="add_event", title="gym", start="2026-09-06T23:00"))
    assert captured["scheduled_start"] == datetime(2026, 9, 6, 23, 0)
    assert captured["scheduled_end"] == datetime(2026, 9, 7, 0, 0)
    assert "23:00" in msg


def test_complete_unknown_target_asks(monkeypatch):
    monkeypatch.setattr(actions.db, "get_task", lambda tid: None)
    msg, row = actions.dispatch(Intent(action="complete_task", target_task_id=None))
    assert row is None and "which task" in msg.lower()


def test_complete_marks_done(monkeypatch):
    monkeypatch.setattr(actions.db, "get_task", lambda tid: {"id": 5, "title": "hw"})
    monkeypatch.setattr(actions.db, "set_status", lambda tid, s: {"id": 5, "title": "hw", "status": s})
    msg, row = actions.dispatch(Intent(action="complete_task", target_task_id=5))
    assert row["status"] == "done" and "done: hw" in msg


def test_unknown_action(monkeypatch):
    msg, row = actions.dispatch(Intent(action="unknown", note="huh?"))
    assert row is None and msg == "huh?"
