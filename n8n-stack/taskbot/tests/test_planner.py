import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from app import planner
from app.planner import Plan, make_plan

NOW = datetime(2026, 9, 7, 15, 0)
TASKS = [
    {"id": 5, "title": "watch iman gadzhi and go to gym",
     "scheduled_start": datetime(2026, 9, 7, 13, 0), "due_date": None},
    {"id": 7, "title": "ml homework", "scheduled_start": None,
     "due_date": __import__("datetime").date(2026, 9, 7)},
]


class _FakeGemini:
    def __init__(self, payload, *, text=None):
        self._text = text if text is not None else json.dumps(payload)

    class _Models:
        def __init__(self, o): self._o = o
        def generate_content(self, **_): return SimpleNamespace(text=self._o._text)

    @property
    def models(self): return _FakeGemini._Models(self)


def _call(payload, *, text=None, history=None, tasks=None):
    return make_plan("msg", history=history or [], tasks=tasks or [], now=NOW,
                     tz="Asia/Bangkok", provider="gemini",
                     client=_FakeGemini(payload, text=text))


def test_multi_action_passthrough():
    p = _call({"actions": [
        {"kind": "add_task", "title": "watch iman gadzhi"},
        {"kind": "add_event", "title": "go to gym", "start": "2026-09-07T13:00"},
        {"kind": "add_task", "title": "buy milk"},
    ]})
    assert [a.kind for a in p.actions] == ["add_task", "add_event", "add_task"]
    assert p.actions[1].start == "2026-09-07T13:00"


def test_reply_only_plan():
    p = _call({"actions": [], "reply": "Which task did you mean?"})
    assert p.actions == [] and "Which task" in p.reply


def test_bad_action_dropped_rest_kept():
    p = _call({"actions": [
        {"kind": "nonsense"},
        {"kind": "delete", "target_id": 5},
    ]})
    assert [a.kind for a in p.actions] == ["delete"]


def test_truncates_at_max_actions():
    p = _call({"actions": [{"kind": "add_task", "title": f"t{i}"} for i in range(15)]})
    assert len(p.actions) == planner.MAX_ACTIONS
    assert "first 10" in p.reply


def test_blank_fields_dropped():
    p = _call({"actions": [{"kind": "add_task", "title": "x", "start": "", "date": ""}]})
    assert p.actions[0].start is None and p.actions[0].date is None


def test_llm_no_text_degrades():
    p = _call({}, text="")
    assert p.actions == [] and "trouble" in p.reply


def test_prompt_carries_history_and_tasks(monkeypatch):
    seen = {}

    class Spy(_FakeGemini):
        class _Models:
            def __init__(self, o): self._o = o
            def generate_content(self, **kw):
                seen["contents"] = kw["contents"]
                return SimpleNamespace(text='{"actions": []}')
        @property
        def models(self): return Spy._Models(self)

    make_plan("i mean watch is allday", history=[
        {"direction": "in", "text": "watch iman and gym at 13.00"},
        {"direction": "out", "text": "added watch iman gadzhi and go to gym at 13:00"},
    ], tasks=TASKS, now=NOW, tz="Asia/Bangkok", provider="gemini", client=Spy({}))
    assert "id=5" in seen["contents"] and "TIMED 2026-09-07 13:00" in seen["contents"]
    assert "watch iman and gym at 13.00" in seen["contents"]
    assert "i mean watch is allday" in seen["contents"]


def test_anthropic_path():
    class _Block:
        type = "tool_use"; name = "record_plan"
        def __init__(self, d): self.input = d

    class _FakeAnthropic:
        class _M:
            def create(self, **_):
                return SimpleNamespace(content=[_Block({"actions": [{"kind": "list_day"}]})],
                                       stop_reason="tool_use")
        @property
        def messages(self): return _FakeAnthropic._M()

    p = make_plan("what's today", history=[], tasks=[], now=NOW, tz="UTC",
                  provider="anthropic", client=_FakeAnthropic())
    assert [a.kind for a in p.actions] == ["list_day"]
