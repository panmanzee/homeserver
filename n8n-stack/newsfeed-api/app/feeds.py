"""RSS fetching + parsing, and best-effort article full-text extraction.

Pure helpers: `parse_feed` turns raw feed bytes into candidate rows;
`extract_fulltext` tries to pull the readable article body. Neither touches
the database.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from html import unescape
from time import mktime
from typing import Any

import feedparser
import httpx
import trafilatura

from .config import settings

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean_html(value: str | None) -> str | None:
    if not value:
        return None
    text = _WS_RE.sub(" ", unescape(_TAG_RE.sub(" ", value))).strip()
    return text or None


def _parse_date(entry: Any) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
            except (OverflowError, ValueError, OSError):
                return None
    return None


def parse_feed(raw: bytes | str, feed_id: int) -> list[dict[str, Any]]:
    """Parse feed content into candidate `news_items` rows (dedup happens in DB)."""
    parsed = feedparser.parse(raw)
    rows: list[dict[str, Any]] = []
    for entry in parsed.entries:
        link = (entry.get("link") or "").strip()
        guid = (entry.get("id") or link).strip()
        if not link or not guid:
            continue
        title = _clean_html(entry.get("title")) or link
        rows.append(
            {
                "feed_id": feed_id,
                "guid": guid,
                "url": link,
                "title": title[:1000],
                "author": (_clean_html(entry.get("author")) or None),
                "summary_rss": _clean_html(entry.get("summary")),
                "published_at": _parse_date(entry),
            }
        )
    return rows


def fetch_feed(url: str) -> bytes:
    with httpx.Client(
        timeout=settings.http_timeout,
        headers={"User-Agent": settings.user_agent},
        follow_redirects=True,
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.content


def extract_fulltext(url: str) -> str | None:
    """Return readable article text, or None if it can't be fetched/extracted.

    Fetches the HTML ourselves (so our timeout / User-Agent apply) and hands it
    to trafilatura for extraction.
    """
    try:
        with httpx.Client(
            timeout=settings.http_timeout,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        ) as client:
            resp = client.get(url)
        if resp.status_code != 200 or not resp.text:
            return None
        html = resp.text
    except httpx.HTTPError:
        return None

    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )
    if not text:
        return None
    text = text.strip()
    return text or None


def resolve_body(summary_rss: str | None, fulltext: str | None) -> tuple[str, str]:
    """Choose the text to send to Claude. Returns (body, content_source)."""
    if fulltext and len(fulltext) >= 400:
        return fulltext[: settings.fulltext_max_chars], "fulltext"
    return (summary_rss or "").strip(), "rss_summary"
