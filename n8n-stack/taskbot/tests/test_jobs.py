from datetime import date, datetime
import pytest
from app import jobs


@pytest.fixture(autouse=True)
def wiring(monkeypatch):
    monkeypatch.setattr(jobs.clock, "now_local", lambda: datetime(2026, 9, 6, 7, 30))
    monkeypatch.setattr(jobs.clock, "is_utc", lambda: False)
    monkeypatch.setattr(jobs.telegram, "send_message", lambda t: None)


def test_morning_plan_lists_today(monkeypatch):
    monkeypatch.setattr(jobs.db, "tasks_for_day", lambda d: [
        {"title": "gym", "scheduled_start": datetime(2026, 9, 6, 23, 0), "status": "pending"},
        {"title": "math homework", "scheduled_start": None, "status": "pending"},
    ])
    monkeypatch.setattr(jobs.db, "overdue_tasks", lambda d: [])
    monkeypatch.setattr(jobs.db, "anytime_tasks", lambda: [])
    text = jobs.morning_plan()
    assert "23:00 gym" in text and "• math homework" in text


def test_evening_all_done(monkeypatch):
    monkeypatch.setattr(jobs.db, "tasks_for_day", lambda d: [])
    assert "done" in jobs.evening_review().lower()


def test_rollover_moves_untimed_pending(monkeypatch):
    moved = []
    monkeypatch.setattr(jobs.db, "tasks_for_day", lambda d: [
        {"id": 1, "title": "hw", "status": "pending", "due_date": date(2026, 9, 6), "scheduled_start": None},
        {"id": 2, "title": "gym", "status": "pending", "due_date": None,
         "scheduled_start": datetime(2026, 9, 6, 23, 0)},
    ])
    monkeypatch.setattr(jobs.db, "reschedule_task",
                        lambda tid, **kw: moved.append((tid, kw)) or {"id": tid, "gcal_event_id": None})
    monkeypatch.setattr(jobs.gcal, "sync_rescheduled", lambda row: None)
    assert jobs.rollover_unfinished() == 1
    assert moved[0][0] == 1 and moved[0][1]["due_date"] == date(2026, 9, 7)


def test_morning_plan_lists_anytime_tasks(monkeypatch):
    monkeypatch.setattr(jobs.db, "tasks_for_day", lambda d: [])
    monkeypatch.setattr(jobs.db, "overdue_tasks", lambda d: [])
    monkeypatch.setattr(jobs.db, "anytime_tasks", lambda: [{"title": "learn rust"}])
    text = jobs.morning_plan()
    assert "anytime" in text and "• learn rust" in text
