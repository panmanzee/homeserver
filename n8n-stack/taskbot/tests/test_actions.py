from datetime import date, datetime
import pytest

from app import actions
from app.planner import Action, Plan


@pytest.fixture(autouse=True)
def frozen(monkeypatch):
    monkeypatch.setattr(actions.clock, "now_local", lambda: datetime(2026, 9, 7, 9, 0))


def _plan(*actions_, reply=None):
    return Plan(actions=list(actions_), reply=reply)


def test_single_add_task(monkeypatch):
    monkeypatch.setattr(actions.db, "create_task",
                        lambda **kw: {"id": 1, "title": kw["title"], "due_date": kw.get("due_date"),
                                      "scheduled_start": None, "gcal_event_id": None})
    lines, ops = actions.execute_plan(_plan(Action(kind="add_task", title="ml homework")))
    assert any("ml homework" in l and "today" in l for l in lines)
    assert ops == [("add_task", {"id": 1, "title": "ml homework", "due_date": date(2026, 9, 7),
                                 "scheduled_start": None, "gcal_event_id": None})]


def test_multi_action_runs_all_in_order(monkeypatch):
    made = []
    monkeypatch.setattr(actions.db, "create_task",
                        lambda **kw: made.append(kw["title"]) or {"id": len(made), "title": kw["title"],
                        "due_date": kw.get("due_date"), "scheduled_start": kw.get("scheduled_start"),
                        "gcal_event_id": None})
    lines, ops = actions.execute_plan(_plan(
        Action(kind="add_task", title="watch iman gadzhi"),
        Action(kind="add_event", title="go to gym", start="2026-09-07T13:00"),
        Action(kind="add_task", title="buy milk"),
    ))
    assert made == ["watch iman gadzhi", "go to gym", "buy milk"]
    assert len(lines) == 3 and len(ops) == 3


def test_reply_preamble_is_first_line(monkeypatch):
    monkeypatch.setattr(actions.db, "create_task",
                        lambda **kw: {"id": 1, "title": kw["title"], "due_date": kw.get("due_date"),
                                      "scheduled_start": None, "gcal_event_id": None})
    lines, _ = actions.execute_plan(_plan(Action(kind="add_task", title="x"),
                                          reply="Split that into two:"))
    assert lines[0] == "Split that into two:"


def test_empty_plan_gives_hint():
    lines, ops = actions.execute_plan(_plan())
    assert ops == [] and len(lines) == 1 and "e.g." in lines[0]


def test_reply_only_plan_no_actions():
    lines, ops = actions.execute_plan(_plan(reply="Which one — gym or homework?"))
    assert ops == [] and lines == ["Which one — gym or homework?"]


def test_convert_timed_to_all_day(monkeypatch):
    monkeypatch.setattr(actions.db, "get_task",
                        lambda i: {"id": 5, "title": "watch", "status": "pending",
                                   "scheduled_start": datetime(2026, 9, 7, 13, 0)})
    captured = {}
    monkeypatch.setattr(actions.db, "set_task_timing",
                        lambda i, **kw: captured.update(kw) or {"id": 5, "title": "watch",
                        "due_date": kw["due_date"], "scheduled_start": None, "gcal_event_id": "e"})
    lines, ops = actions.execute_plan(_plan(Action(kind="convert", target_id=5, to_all_day=True)))
    assert captured["scheduled_start"] is None and captured["due_date"] == date(2026, 9, 7)
    assert ops == [("convert", {"id": 5, "title": "watch", "due_date": date(2026, 9, 7),
                                "scheduled_start": None, "gcal_event_id": "e"})]


def test_rename(monkeypatch):
    monkeypatch.setattr(actions.db, "get_task",
                        lambda i: {"id": 7, "title": "ml homwork", "status": "pending"})
    monkeypatch.setattr(actions.db, "rename_task",
                        lambda i, t: {"id": 7, "title": t, "gcal_event_id": None})
    lines, ops = actions.execute_plan(_plan(Action(kind="rename", target_id=7, title="ML homework")))
    assert any("ML homework" in l for l in lines) and ops[0][0] == "rename"


def test_edit_missing_task_is_friendly(monkeypatch):
    monkeypatch.setattr(actions.db, "get_task", lambda i: None)
    lines, ops = actions.execute_plan(_plan(Action(kind="complete", target_id=99)))
    assert ops == [] and ("already" in lines[0].lower() or "which" in lines[0].lower())


def test_action_raising_does_not_kill_siblings(monkeypatch):
    def boom(**_): raise RuntimeError("db down")
    monkeypatch.setattr(actions.db, "create_task", boom)
    monkeypatch.setattr(actions.db, "tasks_for_day", lambda d: [])
    lines, ops = actions.execute_plan(_plan(
        Action(kind="add_task", title="a"),
        Action(kind="list_day", date="2026-09-07"),
    ))
    assert any("couldn't do" in l for l in lines)


def test_bad_date_string_is_polite(monkeypatch):
    monkeypatch.setattr(actions.db, "create_task", lambda **kw: {"id": 1, "title": kw["title"]})
    lines, _ = actions.execute_plan(_plan(Action(kind="add_task", title="x", date="next tuesday")))
    assert any("couldn't read" in l for l in lines)


def test_list_day(monkeypatch):
    monkeypatch.setattr(actions.db, "tasks_for_day", lambda d: [
        {"title": "gym", "scheduled_start": datetime(2026, 9, 7, 15, 0)},
        {"title": "ml homework", "scheduled_start": None},
    ])
    lines, ops = actions.execute_plan(_plan(Action(kind="list_day", date="2026-09-07")))
    joined = "\n".join(lines)
    assert "gym" in joined and "ml homework" in joined and ops == []
