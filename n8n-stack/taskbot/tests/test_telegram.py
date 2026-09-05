import pytest

from app import telegram


@pytest.mark.asyncio
async def test_chat_gate_and_offset(monkeypatch):
    seen, offset = [], {"v": 0}
    monkeypatch.setattr(telegram.db, "get_offset", lambda: offset["v"])
    monkeypatch.setattr(telegram.db, "set_offset", lambda v: offset.__setitem__("v", v))
    monkeypatch.setattr(telegram.db, "log_message", lambda *a, **k: None)
    monkeypatch.setattr(telegram, "send_message", lambda text: seen.append(("out", text)))

    async def handle(text, mid):
        seen.append(("in", text))
        return "ok"

    updates = [
        {"update_id": 10, "message": {"message_id": 1, "chat": {"id": 648810}, "text": "hello"}},
        {"update_id": 11, "message": {"message_id": 2, "chat": {"id": 999}, "text": "spam"}},
    ]
    nxt = await telegram.run_once(updates, handle)
    assert ("in", "hello") in seen
    assert ("in", "spam") not in seen
    assert ("out", "ok") in seen
    assert nxt == 12 and offset["v"] == 12


@pytest.mark.asyncio
async def test_handler_exception_becomes_polite_reply(monkeypatch):
    out = []
    monkeypatch.setattr(telegram.db, "get_offset", lambda: 0)
    monkeypatch.setattr(telegram.db, "set_offset", lambda v: None)
    monkeypatch.setattr(telegram.db, "log_message", lambda *a, **k: None)
    monkeypatch.setattr(telegram, "send_message", lambda text: out.append(text))

    async def boom(text, mid):
        raise ValueError("nope")

    await telegram.run_once(
        [{"update_id": 1, "message": {"message_id": 1, "chat": {"id": 648810}, "text": "x"}}],
        boom,
    )
    assert out and "something went wrong" in out[0]
