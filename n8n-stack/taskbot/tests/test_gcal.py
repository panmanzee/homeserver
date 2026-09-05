from datetime import date, datetime
from app import gcal


def test_disabled_is_noop(monkeypatch):
    monkeypatch.setattr(gcal, "enabled", lambda: False)
    gcal.sync_new({"id": 1, "title": "x", "due_date": date(2026, 9, 6)})  # must not raise


def test_body_all_day_vs_timed():
    all_day = gcal._body({"title": "hw", "due_date": date(2026, 9, 6), "scheduled_start": None})
    assert all_day["start"] == {"date": "2026-09-06"}
    timed = gcal._body({"title": "gym", "due_date": None,
                        "scheduled_start": datetime(2026, 9, 6, 23, 0),
                        "scheduled_end": datetime(2026, 9, 7, 0, 0)})
    assert timed["start"]["dateTime"].startswith("2026-09-06T23:00")


def test_sync_new_stores_event_id(monkeypatch):
    monkeypatch.setattr(gcal, "enabled", lambda: True)
    stored = {}
    class _Ev:
        def insert(self, **_): return self
        def execute(self): return {"id": "evt-123"}
    class _Svc:
        def events(self): return _Ev()
    monkeypatch.setattr(gcal, "_svc", lambda: (_Svc(), "cal-1"))
    monkeypatch.setattr(gcal.db, "set_gcal_event_id", lambda tid, eid: stored.update(id=tid, eid=eid))
    gcal.sync_new({"id": 9, "title": "hw", "due_date": date(2026, 9, 6), "scheduled_start": None})
    assert stored == {"id": 9, "eid": "evt-123"}
