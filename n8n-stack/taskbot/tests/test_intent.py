import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from app import intent as intent_mod
from app.intent import Intent, parse

NOW = datetime(2026, 9, 6, 9, 0)

CASES = [
    ({"action": "add_task", "title": "math homework", "date": "2026-09-06"},
     {"action": "add_task", "title": "math homework"}),
    ({"action": "add_event", "title": "gym", "start": "2026-09-06T23:00"},
     {"action": "add_event", "start": "2026-09-06T23:00"}),
    ({"action": "complete_task", "target_task_id": 7},
     {"action": "complete_task", "target_task_id": 7}),
    ({"action": "delete_task", "target_task_id": 7}, {"action": "delete_task"}),
    ({"action": "list_day", "date": "2026-09-06"}, {"action": "list_day"}),
    ({"action": "unknown", "note": "which one?"}, {"action": "unknown", "note": "which one?"}),
]


# --------------------------------------------------------------------------- #
# Gemini path (default provider)
# --------------------------------------------------------------------------- #
class _FakeGemini:
    """Mimics google.genai Client: .models.generate_content(...) -> obj with .text"""

    def __init__(self, payload, *, text=None):
        self._text = text if text is not None else json.dumps(payload)

    class _Models:
        def __init__(self, outer): self._outer = outer
        def generate_content(self, **_): return SimpleNamespace(text=self._outer._text)

    @property
    def models(self): return _FakeGemini._Models(self)


@pytest.mark.parametrize("data, expect", CASES)
def test_gemini_parses_model_output(monkeypatch, data, expect):
    monkeypatch.setattr(intent_mod.db, "open_tasks", lambda: [])
    got = parse("whatever", now=NOW, tz="UTC", provider="gemini", client=_FakeGemini(data))
    for k, v in expect.items():
        assert getattr(got, k) == v


def test_gemini_blank_fields_are_dropped(monkeypatch):
    monkeypatch.setattr(intent_mod.db, "open_tasks", lambda: [])
    # a model that fills every property with "" except the ones it means
    payload = {"action": "add_task", "title": "call mom", "date": "", "start": "",
               "end": "", "note": ""}
    got = parse("call mom", now=NOW, tz="UTC", provider="gemini", client=_FakeGemini(payload))
    assert got.action == "add_task" and got.title == "call mom"
    assert got.start is None and got.note is None


def test_gemini_bad_action_becomes_unknown(monkeypatch):
    monkeypatch.setattr(intent_mod.db, "open_tasks", lambda: [])
    got = parse("x", now=NOW, tz="UTC", provider="gemini",
                client=_FakeGemini({"action": "not-a-real-action"}))
    assert got.action == "unknown"


def test_gemini_no_text_degrades_gracefully(monkeypatch):
    monkeypatch.setattr(intent_mod.db, "open_tasks", lambda: [])
    got = parse("x", now=NOW, tz="UTC", provider="gemini",
                client=_FakeGemini(None, text=""))
    assert got.action == "unknown" and "trouble" in got.note


def test_gemini_non_json_degrades_gracefully(monkeypatch):
    monkeypatch.setattr(intent_mod.db, "open_tasks", lambda: [])
    got = parse("x", now=NOW, tz="UTC", provider="gemini",
                client=_FakeGemini(None, text="sorry, I can't do that"))
    assert got.action == "unknown" and "trouble" in got.note


def test_default_provider_is_gemini():
    from app.config import settings
    assert settings.llm_provider == "gemini"


# --------------------------------------------------------------------------- #
# Anthropic path (still supported as a fallback provider)
# --------------------------------------------------------------------------- #
class _FakeBlock:
    type = "tool_use"
    name = "record_intent"
    def __init__(self, data): self.input = data


class _FakeAnthropic:
    def __init__(self, data): self._data = data

    class _Messages:
        def __init__(self, outer): self._outer = outer
        def create(self, **_):
            return SimpleNamespace(content=[_FakeBlock(self._outer._data)],
                                   stop_reason="tool_use")

    @property
    def messages(self): return _FakeAnthropic._Messages(self)


@pytest.mark.parametrize("data, expect", CASES)
def test_anthropic_parses_tool_output(monkeypatch, data, expect):
    monkeypatch.setattr(intent_mod.db, "open_tasks", lambda: [])
    got = parse("whatever", now=NOW, tz="UTC", provider="anthropic",
                client=_FakeAnthropic(data))
    for k, v in expect.items():
        assert getattr(got, k) == v


def test_anthropic_no_tool_use_degrades_gracefully(monkeypatch):
    monkeypatch.setattr(intent_mod.db, "open_tasks", lambda: [])

    class _NoTool:
        @property
        def messages(self):
            return SimpleNamespace(
                create=lambda **_: SimpleNamespace(content=[], stop_reason="end_turn")
            )

    got = parse("x", now=NOW, tz="UTC", provider="anthropic", client=_NoTool())
    assert got.action == "unknown" and "trouble" in got.note
