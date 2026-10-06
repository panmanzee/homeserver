from datetime import date, datetime, timedelta
import pytest

from app import actions
from app.planner import Action, Plan


@pytest.fixture(autouse=True)
def frozen(monkeypatch):
    monkeypatch.setattr(actions.clock, "now_local", lambda: datetime(2026, 9, 7, 9, 0))
    # "today" listings also include carried-over + anytime tasks; default to none
    monkeypatch.setattr(actions.db, "carried_over", lambda d: [])
    monkeypatch.setattr(actions.db, "anytime_tasks", lambda: [])


def _plan(*actions_, reply=None):
    return Plan(actions=list(actions_), reply=reply)


def test_single_add_task(monkeypatch):
    monkeypatch.setattr(actions.db, "create_task",
                        lambda **kw: {"id": 1, "title": kw["title"], "due_date": kw.get("due_date"),
                                      "scheduled_start": None, "gcal_event_id": None})
    lines, ops = actions.execute_plan(_plan(Action(kind="add_task", title="ml homework")))
    assert any("ml homework" in l and "today" in l for l in lines)
    # add_task is opt-in to calendar sync (Task 2) — no to_calendar means no gcal op.
    assert ops == []


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
    # add_task/add_event are opt-in to calendar sync (Task 2); none of these
    # actions set to_calendar, so no gcal ops are produced.
    assert len(lines) == 3 and len(ops) == 0


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
    # rename is an edit kind — it only keeps syncing to calendar if the task
    # was already synced (gcal_event_id set). Pin that here with "evt1".
    monkeypatch.setattr(actions.db, "get_task",
                        lambda i: {"id": 7, "title": "ml homwork", "status": "pending",
                                   "gcal_event_id": "evt1"})
    monkeypatch.setattr(actions.db, "rename_task",
                        lambda i, t: {"id": 7, "title": t, "gcal_event_id": "evt1"})
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
    # the sibling list_day still produced its own line
    assert len(lines) == 2 and any("nothing for" in l for l in lines)


def test_unknown_action_kind_tells_user(monkeypatch):
    monkeypatch.setattr(actions.db, "tasks_for_day", lambda d: [])
    bogus = Action.model_construct(kind="teleport")
    lines, ops = actions.execute_plan(_plan(bogus, Action(kind="list_day", date="2026-09-07")))
    assert any("couldn't do" in l and "teleport" in l for l in lines)
    assert any("nothing for" in l for l in lines) and ops == []


# --- reschedule -----------------------------------------------------------

def _resched_wiring(monkeypatch, before):
    captured = {}
    monkeypatch.setattr(actions.db, "get_task", lambda i: before)
    monkeypatch.setattr(
        actions.db, "reschedule_task",
        lambda i, **kw: captured.update(kw) or {
            "id": i, "title": before["title"],
            "due_date": kw.get("due_date"),
            "scheduled_start": kw.get("scheduled_start"),
            "scheduled_end": kw.get("scheduled_end"),
            "gcal_event_id": before.get("gcal_event_id"),
        },
    )
    return captured


def test_reschedule_start_move_preserves_duration(monkeypatch):
    before = {"id": 3, "title": "gym", "status": "pending",
              "scheduled_start": datetime(2026, 9, 7, 18, 0),
              "scheduled_end": datetime(2026, 9, 7, 19, 0), "gcal_event_id": "e"}
    captured = _resched_wiring(monkeypatch, before)
    lines, ops = actions.execute_plan(_plan(
        Action(kind="reschedule", target_id=3, start="2026-09-07T20:00")))
    assert captured["scheduled_end"] - captured["scheduled_start"] == timedelta(hours=1)
    assert captured["scheduled_start"].hour == 20 and captured["scheduled_end"].hour == 21
    assert ops and ops[0][0] == "reschedule"


def test_reschedule_bare_day_move_still_works(monkeypatch):
    before = {"id": 4, "title": "report", "status": "pending",
              "scheduled_start": None, "scheduled_end": None, "gcal_event_id": None}
    captured = _resched_wiring(monkeypatch, before)
    lines, ops = actions.execute_plan(_plan(
        Action(kind="reschedule", target_id=4, date="2026-09-11")))
    assert captured["due_date"] == date(2026, 9, 11)
    assert captured["scheduled_start"] is None and captured["scheduled_end"] is None
    assert any("report" in l for l in lines)


def test_reschedule_no_prior_end_uses_60min_fallback(monkeypatch):
    before = {"id": 5, "title": "call", "status": "pending",
              "scheduled_start": datetime(2026, 9, 7, 9, 0),
              "scheduled_end": None, "gcal_event_id": "e"}
    captured = _resched_wiring(monkeypatch, before)
    actions.execute_plan(_plan(
        Action(kind="reschedule", target_id=5, start="2026-09-07T15:00")))
    assert captured["scheduled_end"] - captured["scheduled_start"] == timedelta(minutes=60)


# --- convert -------------------------------------------------------------

def test_convert_to_all_day_false_asks_for_time(monkeypatch):
    monkeypatch.setattr(actions.db, "get_task",
                        lambda i: {"id": 5, "title": "book", "status": "pending",
                                   "scheduled_start": datetime(2026, 9, 7, 15, 0)})
    called = []
    monkeypatch.setattr(actions.db, "set_task_timing", lambda *a, **k: called.append(k))
    lines, ops = actions.execute_plan(_plan(
        Action(kind="convert", target_id=5, to_all_day=False)))
    assert ops == [] and called == []
    assert any("time" in l.lower() for l in lines)


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


def test_add_event_default_no_calendar(monkeypatch):
    monkeypatch.setattr(actions.db, "create_task",
                        lambda **kw: {"id": 1, "title": kw["title"], "due_date": None,
                                      "scheduled_start": kw.get("scheduled_start"),
                                      "gcal_event_id": None})
    lines, ops = actions.execute_plan(_plan(Action(kind="add_event", title="gym", start="2026-09-07T18:00")))
    assert ops == []


def test_add_event_explicit_calendar(monkeypatch):
    monkeypatch.setattr(actions.db, "create_task",
                        lambda **kw: {"id": 1, "title": kw["title"], "due_date": None,
                                      "scheduled_start": kw.get("scheduled_start"),
                                      "gcal_event_id": None})
    lines, ops = actions.execute_plan(_plan(Action(kind="add_event", title="gym",
                                                   start="2026-09-07T18:00", to_calendar=True)))
    assert ops == [("add_event", {"id": 1, "title": "gym", "due_date": None,
                                  "scheduled_start": ops[0][1]["scheduled_start"],
                                  "gcal_event_id": None})]


def test_add_task_default_no_calendar(monkeypatch):
    monkeypatch.setattr(actions.db, "create_task",
                        lambda **kw: {"id": 2, "title": kw["title"], "due_date": kw.get("due_date"),
                                      "scheduled_start": None, "gcal_event_id": None})
    lines, ops = actions.execute_plan(_plan(Action(kind="add_task", title="hw")))
    assert ops == []


def test_reschedule_unsynced_no_calendar_by_default(monkeypatch):
    monkeypatch.setattr(actions.db, "get_task",
                        lambda i: {"id": 5, "title": "gym", "status": "pending",
                                   "scheduled_start": datetime(2026, 9, 7, 18, 0),
                                   "scheduled_end": datetime(2026, 9, 7, 19, 0),
                                   "gcal_event_id": None})
    monkeypatch.setattr(actions.db, "reschedule_task",
                        lambda i, **kw: {"id": 5, "title": "gym", "due_date": None,
                                        "scheduled_start": kw["scheduled_start"],
                                        "scheduled_end": kw["scheduled_end"], "gcal_event_id": None})
    lines, ops = actions.execute_plan(_plan(Action(kind="reschedule", target_id=5, start="2026-09-07T19:00")))
    assert ops == []


def test_reschedule_already_synced_keeps_syncing(monkeypatch):
    monkeypatch.setattr(actions.db, "get_task",
                        lambda i: {"id": 5, "title": "gym", "status": "pending",
                                   "scheduled_start": datetime(2026, 9, 7, 18, 0),
                                   "scheduled_end": datetime(2026, 9, 7, 19, 0),
                                   "gcal_event_id": "evt1"})
    monkeypatch.setattr(actions.db, "reschedule_task",
                        lambda i, **kw: {"id": 5, "title": "gym", "due_date": None,
                                        "scheduled_start": kw["scheduled_start"],
                                        "scheduled_end": kw["scheduled_end"], "gcal_event_id": "evt1"})
    lines, ops = actions.execute_plan(_plan(Action(kind="reschedule", target_id=5, start="2026-09-07T19:00")))
    assert ops and ops[0][0] == "reschedule"


def test_complete_unsynced_no_calendar(monkeypatch):
    monkeypatch.setattr(actions.db, "get_task",
                        lambda i: {"id": 5, "title": "gym", "status": "pending", "gcal_event_id": None})
    monkeypatch.setattr(actions.db, "set_status",
                        lambda i, s: {"id": 5, "title": "gym", "status": s, "gcal_event_id": None})
    lines, ops = actions.execute_plan(_plan(Action(kind="complete", target_id=5)))
    # complete/delete are unconditionally in _GCAL_KINDS (gcal.py itself no-ops
    # without a gcal_event_id) — this pins that the ROW passed through still
    # carries gcal_event_id=None so gcal.sync_completed's own guard applies.
    assert ops == [("complete", {"id": 5, "title": "gym", "status": "done", "gcal_event_id": None})]


def test_calendar_sync_new_row(monkeypatch):
    monkeypatch.setattr(actions.db, "get_task",
                        lambda i: {"id": 6, "title": "gym", "status": "pending", "gcal_event_id": None})
    lines, ops = actions.execute_plan(_plan(Action(kind="calendar_sync", target_id=6)))
    assert "added" in lines[0].lower() and "gym" in lines[0]
    assert ops == [("calendar_sync", {"id": 6, "title": "gym", "status": "pending", "gcal_event_id": None})]


def test_calendar_sync_already_synced(monkeypatch):
    monkeypatch.setattr(actions.db, "get_task",
                        lambda i: {"id": 6, "title": "gym", "status": "pending", "gcal_event_id": "evt1"})
    lines, ops = actions.execute_plan(_plan(Action(kind="calendar_sync", target_id=6)))
    assert "already" in lines[0].lower() and ops == []


def test_calendar_sync_unknown_task(monkeypatch):
    monkeypatch.setattr(actions.db, "get_task", lambda i: None)
    lines, ops = actions.execute_plan(_plan(Action(kind="calendar_sync", target_id=99)))
    assert ops == [] and "which task" in lines[0].lower()


def test_list_today_includes_carried_over_and_anytime(monkeypatch):
    monkeypatch.setattr(actions.db, "tasks_for_day", lambda d: [{"title": "gym", "scheduled_start": None}])
    monkeypatch.setattr(actions.db, "carried_over", lambda d: [{"title": "old report"}])
    monkeypatch.setattr(actions.db, "anytime_tasks", lambda: [{"title": "learn rust"}])
    lines, _ = actions.execute_plan(_plan(Action(kind="list_day", date="2026-09-07")))
    joined = "\n".join(lines)
    assert "gym" in joined and "old report" in joined and "learn rust" in joined


def test_list_other_day_skips_carried_over(monkeypatch):
    monkeypatch.setattr(actions.db, "tasks_for_day", lambda d: [])
    monkeypatch.setattr(actions.db, "carried_over", lambda d: [{"title": "old report"}])
    monkeypatch.setattr(actions.db, "anytime_tasks", lambda: [{"title": "learn rust"}])
    lines, _ = actions.execute_plan(_plan(Action(kind="list_day", date="2026-09-08")))
    assert "old report" not in "\n".join(lines) and "nothing for" in "\n".join(lines)
