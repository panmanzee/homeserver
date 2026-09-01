import pytest

from app import notify


def _item(**overrides):
    base = dict(
        id=1,
        url="https://example.com/story",
        title="Big News",
        importance="notable",
        tickers=["AAPL", "MSFT"],
        summary="- First fact about the story.\n- Second fact about the story.",
    )
    base.update(overrides)
    return base


def test_format_item_line_has_headline_link_tickers_and_summary():
    block = notify.format_item_line(_item())
    assert "Big News" in block
    assert 'href="https://example.com/story"' in block
    assert "$AAPL" in block and "$MSFT" in block
    assert block.startswith("• ")
    assert "First fact about the story." in block
    assert "Second fact about the story." in block
    # headline on line 1, bullets indented under it
    first, *rest = block.splitlines()
    assert "Big News" in first
    assert all(r.startswith("    ") for r in rest)


def test_format_item_line_without_summary_is_one_line():
    block = notify.format_item_line(_item(summary=None))
    assert "\n" not in block


def test_format_item_line_caps_bullets():
    item = _item(summary="- one\n- two\n- three\n- four")
    block = notify.format_item_line(item, max_bullets=2)
    assert "one" in block and "two" in block
    assert "three" not in block
    assert "(…)" in block  # dropped-bullets marker


def test_format_item_line_marks_breaking():
    assert notify.format_item_line(_item(importance="breaking")).startswith("\U0001f534")


def test_format_item_line_escapes_html_in_title():
    line = notify.format_item_line(_item(title="Chips <b>&</b> dips"))
    assert "<b>" not in line.split("</a>")[0].replace('<a href', '')
    assert "&lt;b&gt;" in line and "&amp;" in line


def test_format_item_line_handles_no_tickers():
    line = notify.format_item_line(_item(tickers=[]))
    assert "$" not in line


def test_format_digest_empty_returns_no_messages():
    assert notify.format_digest([], max_items=30) == []


def test_format_digest_caps_and_reports_remainder():
    items = [_item(id=i, title=f"News {i}") for i in range(40)]
    body = "\n".join(notify.format_digest(items, max_items=30))
    assert "30 item(s)" in body
    assert "and 10 more" in body


def test_format_digest_splits_when_over_char_limit():
    items = [
        _item(id=i, title="T" * 250, url="https://example.com/" + "p" * 150)
        for i in range(80)
    ]
    messages = notify.format_digest(items, max_items=80)
    assert len(messages) > 1
    assert all(len(m) <= notify.TELEGRAM_MAX_CHARS for m in messages)


def test_format_breaking_single_message():
    msg = notify.format_breaking(_item(importance="breaking"))
    assert msg.startswith("\U0001f534 <b>Breaking</b>")
    assert "Big News" in msg


def test_send_telegram_raises_without_config(monkeypatch):
    monkeypatch.setattr(notify.settings, "telegram_bot_token", "")
    monkeypatch.setattr(notify.settings, "telegram_chat_id", "")
    with pytest.raises(notify.TelegramError):
        notify.send_telegram("hello")
