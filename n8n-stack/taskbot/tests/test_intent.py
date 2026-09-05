from datetime import datetime
from types import SimpleNamespace

import pytest

from app import intent as intent_mod
from app.intent import Intent, parse


class _FakeBlock:
    type = "tool_use"
    name = "record_intent"
    def __init__(self, data): self.input = data


class _FakeClient:
    def __init__(self, data): self._data = data
    class _Messages:
        def __init__(self, outer): self._outer = outer
        def create(self, **_): return SimpleNamespace(content=[_FakeBlock(self._outer._data)])
    @property
    def messages(self): return _FakeClient._Messages(self)


NOW = datetime(2026, 9, 6, 9, 0)


@pytest.mark.parametrize("data, expect", [
    ({"action": "add_task", "title": "math homework", "date": "2026-09-06"},
     {"action": "add_task", "title": "math homework"}),
    ({"action": "add_event", "title": "gym", "start": "2026-09-06T23:00"},
     {"action": "add_event", "start": "2026-09-06T23:00"}),
    ({"action": "complete_task", "target_task_id": 7},
     {"action": "complete_task", "target_task_id": 7}),
    ({"action": "delete_task", "target_task_id": 7}, {"action": "delete_task"}),
    ({"action": "list_day", "date": "2026-09-06"}, {"action": "list_day"}),
    ({"action": "unknown", "note": "which one?"}, {"action": "unknown"}),
])
def test_parse_passes_model_output(monkeypatch, data, expect):
    monkeypatch.setattr(intent_mod.db, "open_tasks", lambda: [])
    got = parse("whatever", now=NOW, tz="UTC", client=_FakeClient(data))
    for k, v in expect.items():
        assert getattr(got, k) == v


def test_bad_model_output_becomes_unknown(monkeypatch):
    monkeypatch.setattr(intent_mod.db, "open_tasks", lambda: [])
    got = parse("x", now=NOW, tz="UTC", client=_FakeClient({"action": "not-a-real-action"}))
    assert got.action == "unknown"
