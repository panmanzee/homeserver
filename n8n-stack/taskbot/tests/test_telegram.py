import pytest

from app import telegram


def test_redact_removes_token():
    token = telegram.settings.telegram_bot_token
    s = f"HTTPStatusError for https://api.telegram.org/bot{token}/getUpdates?offset=1"
    out = telegram._redact(s)
    assert token not in out
    assert "REDACTED" in out


def test_split_hard_slices_one_long_line():
    line = "z" * 9000
    chunks = telegram._split(line, 4000)
    assert len(chunks) == 3
    assert all(0 < len(c) <= 4000 for c in chunks)
    assert "".join(chunks) == line


def test_send_message_no_duplicate_chunk_on_retry(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)  # skip tenacity backoff
    monkeypatch.setattr(telegram.db, "log_message", lambda *a, **k: None)
    sent: list[str] = []
    y_attempts = {"n": 0}

    class Resp:
        def __init__(self, code: int):
            self.status_code = code
            self.text = ""

    def fake_post(url, json=None, timeout=None):
        chunk = json["text"]
        sent.append(chunk[0])
        if chunk[0] == "y":
            y_attempts["n"] += 1
            if y_attempts["n"] == 1:
                return Resp(503)
        return Resp(200)

    monkeypatch.setattr(telegram.httpx, "post", fake_post)

    telegram.send_message("x" * 3000 + "\n" + "y" * 3000)

    assert sent.count("x") == 1  # first chunk sent exactly once, not re-sent when chunk 2 retried
    assert sent.count("y") == 2  # second chunk: 503 then 200


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
async def test_offset_advances_even_when_send_always_fails(monkeypatch):
    # F1: a persistent sendMessage failure must NOT wedge the poller — the offset
    # has to advance once per update or Telegram re-serves it forever.
    offset = {"v": 0}
    monkeypatch.setattr(telegram.db, "get_offset", lambda: offset["v"])
    monkeypatch.setattr(telegram.db, "set_offset", lambda v: offset.__setitem__("v", v))
    monkeypatch.setattr(telegram.db, "log_message", lambda *a, **k: None)

    def always_fails(_text):
        raise telegram.TelegramTransient("persistent 429")

    monkeypatch.setattr(telegram, "send_message", always_fails)

    async def handle(text, mid):
        return "reply that can't be delivered"

    nxt = await telegram.run_once(
        [{"update_id": 41, "message": {"message_id": 1, "chat": {"id": 648810}, "text": "hi"}}],
        handle,
    )
    assert nxt == 42 and offset["v"] == 42


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
