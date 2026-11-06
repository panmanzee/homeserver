"""Telegram delivery: format enriched news items and send them via the Bot API.

Pure formatting helpers (`format_item_line`, `format_digest`, `format_breaking`)
plus `send_telegram` / `send_all`, which are the only functions that talk to
Telegram. One-way push only — the bot never reads incoming messages here.
"""

from __future__ import annotations

import html
from typing import Any, Iterable

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import settings

TELEGRAM_MAX_CHARS = 4096
_SEND_URL = "https://api.telegram.org/bot{token}/sendMessage"
_SAFETY_MARGIN = 24  # keep messages comfortably under the hard limit


class TelegramError(RuntimeError):
    """Telegram send failed and should not be retried (bad config, 4xx)."""


class TelegramRetryable(TelegramError):
    """Transient Telegram failure (network, 429, 5xx) — worth retrying."""


def _esc(value: str | None) -> str:
    return html.escape(value or "", quote=False)


def _summary_bullets(summary: str | None) -> list[str]:
    """Split the stored summary ('- a\\n- b') into clean bullet strings."""
    if not summary:
        return []
    out = []
    for raw in summary.splitlines():
        text = raw.strip().lstrip("-•").strip()
        if text:
            out.append(text)
    return out


def format_item_line(item: dict[str, Any], *, max_bullets: int | None = None) -> str:
    """A block: marker + linked headline + $TICKERS, then indented summary bullets.

    `max_bullets` caps how many summary bullets are shown (None = all); a "(…)"
    marker is appended when bullets are dropped.
    """
    title = _esc(item.get("title") or "(untitled)")
    url = _esc(item.get("url") or "")
    tickers = item.get("tickers") or []
    marker = "\U0001f534 " if item.get("importance") == "breaking" else "• "
    head = f'{marker}<a href="{url}">{title}</a>'
    if tickers:
        head += "  " + " ".join(f"${_esc(str(t))}" for t in tickers)
    lines = [head]
    bullets = _summary_bullets(item.get("summary"))
    shown = bullets if max_bullets is None else bullets[:max_bullets]
    for bullet in shown:
        lines.append(f"    – {_esc(bullet)}")
    if len(shown) < len(bullets):
        lines.append("    – (…)")
    return "\n".join(lines)


def _pack(header: str, blocks: list[str], sep: str = "\n\n") -> list[str]:
    """Pack blocks into messages under the char limit; header on the first only."""
    messages: list[str] = []
    cap = TELEGRAM_MAX_CHARS - _SAFETY_MARGIN
    current = [header]
    length = len(header)
    for block in blocks:
        if len(block) > cap:
            block = block[: cap - 1] + "…"
        extra = len(block) + len(sep)
        if length + extra > TELEGRAM_MAX_CHARS - _SAFETY_MARGIN and len(current) > 1:
            messages.append(sep.join(current))
            current, length = [block], len(block)
        else:
            current.append(block)
            length += extra
    if current:
        messages.append(sep.join(current))
    return messages


def format_topic_line(item: dict[str, Any]) -> str:
    """One plain line per story: '- Headline' (red dot for breaking). No links."""
    title = _esc(item.get("title") or "(untitled)")
    marker = "\U0001f534 " if item.get("importance") == "breaking" else "- "
    return marker + title


def format_digest(
    items: list[dict[str, Any]], *, web_url: str = "", date_label: str = ""
) -> list[str]:
    """Daily topic list: every headline on one line, then a link to the web app.

    Returns 0+ Telegram messages (split only if the list exceeds 4096 chars).
    """
    if not items:
        return []
    # breaking stories first, then the rest, each group keeping newest-first order
    ordered = [i for i in items if i.get("importance") == "breaking"] + [
        i for i in items if i.get("importance") != "breaking"
    ]
    header = f"\U0001f4f0 <b>News {_esc(date_label)}</b> · {len(items)} topics".replace("  ", " ")
    lines = [format_topic_line(i) for i in ordered]
    messages = _pack(header + "\n", lines, sep="\n")
    if web_url:
        footer = f'\n\n\U0001f449 Read it here: <a href="{_esc(web_url)}">{_esc(web_url)}</a>'
        if len(messages[-1]) + len(footer) <= TELEGRAM_MAX_CHARS - _SAFETY_MARGIN:
            messages[-1] += footer
        else:
            messages.append(footer.strip())
    return messages


def format_breaking(item: dict[str, Any]) -> str:
    """Single-item urgent message."""
    return "\U0001f534 <b>Breaking</b>\n" + format_item_line(item)


@retry(
    retry=retry_if_exception_type(TelegramRetryable),
    wait=wait_exponential(multiplier=2, min=2, max=20),
    stop=stop_after_attempt(3),
    reraise=True,
)
def send_telegram(text: str, *, client: httpx.Client | None = None) -> None:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        raise TelegramError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID is not set")

    owns_client = client is None
    client = client or httpx.Client(timeout=settings.http_timeout)
    try:
        resp = client.post(
            _SEND_URL.format(token=settings.telegram_bot_token),
            json={
                "chat_id": settings.telegram_chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "link_preview_options": {"is_disabled": True},
            },
        )
    except httpx.HTTPError as exc:
        raise TelegramRetryable(f"network error: {exc}") from exc
    finally:
        if owns_client:
            client.close()

    if resp.status_code == 200:
        return
    if resp.status_code == 429 or resp.status_code >= 500:
        raise TelegramRetryable(f"telegram {resp.status_code}: {resp.text[:300]}")
    raise TelegramError(f"telegram {resp.status_code}: {resp.text[:300]}")


def send_all(texts: Iterable[str]) -> int:
    """Send several messages over one HTTP client. Returns the count sent."""
    sent = 0
    with httpx.Client(timeout=settings.http_timeout) as client:
        for text in texts:
            send_telegram(text, client=client)
            sent += 1
    return sent


__all__ = [
    "TelegramError",
    "TelegramRetryable",
    "TELEGRAM_MAX_CHARS",
    "format_item_line",
    "format_digest",
    "format_topic_line",
    "format_breaking",
    "send_telegram",
    "send_all",
]
