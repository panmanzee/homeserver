"""Jev scoring: importance + topic for every news item, independent of Gemini.

Gemini's free tier (20 req/day/model) enriches only a fraction of items, so the
importance signal used for "big news" selection comes from Jev here instead.
Two cheap /decide/choice calls per item (importance, topic), run in parallel.
Nothing in this module raises: a failed item stays unscored and is retried on
the next run.
"""

from __future__ import annotations

import html
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
from psycopg.types.json import Jsonb

from . import db
from .config import settings

log = logging.getLogger("jevscore")

EXCERPT_CHARS = 1200
POOL_SIZE = 4

# Wording/base rate copied from enrich.SYSTEM_PROMPT, widened to world news
# because the morning reader also wants world + Thailand front-page stories.
IMPORTANCE_CRITERIA = {
    "breaking": (
        "Front-page, market-wide or world-level news; roughly 1 in 30 articles. "
        "Examples: a central bank changes rates or policy; a top-10-by-value "
        "company announces a merger, bankruptcy, CEO exit, or major miss; a major "
        "regulatory or antitrust ruling; a surprise in headline macro data (CPI, "
        "jobs, GDP); a war, large geopolitical shock, major election result, or "
        "large disaster; major Thailand national news. A single company's product "
        "launch, a mid-cap's earnings, or an analyst call is NOT breaking."
    ),
    "notable": (
        "Meaningful company- or sector-level news worth knowing today, but not "
        "front-page."
    ),
    "routine": (
        "Incremental updates, a single analyst's note, opinion / advice columns, "
        "explainers, reviews, deals, minor or narrow items. Default when unsure."
    ),
}

TOPIC_CRITERIA = {
    "world": "World affairs: geopolitics, wars, elections, diplomacy, disasters, health, climate.",
    "markets": "Economy and financial markets: central banks, rates, inflation, jobs data, stocks, bonds, oil, currencies, big-company earnings or deals.",
    "tech_ai": "Technology and AI: AI models and companies, chips, big tech products, cybersecurity, internet policy, science and space tech.",
    "thailand": "News about Thailand: Thai politics, economy, SET, baht, Bank of Thailand, Thai companies, events in Thailand.",
    "other": "Anything else: reviews, how-tos, lifestyle, entertainment, gaming, gadgets deals, opinion.",
}

QUESTION_IMPORTANCE = "How important is this news story for a general reader of the front page?"
QUESTION_TOPIC = "Which topic does this news story mainly belong to?"


def clean_excerpt(raw: str | None, limit: int = EXCERPT_CHARS) -> str:
    """Strip HTML tags/entities and collapse whitespace; cap at `limit` chars."""
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def build_state(item: dict[str, Any]) -> dict[str, Any]:
    published = item.get("published_at")
    return {
        "title": item.get("title") or "",
        "source": item.get("feed_name") or "",
        "feed_category": item.get("feed_category") or "",
        "excerpt": clean_excerpt(item.get("summary_rss")),
        "published": published.isoformat() if hasattr(published, "isoformat") else (published or ""),
    }


def _choose(client: httpx.Client, state: dict, question: str, criteria: dict) -> dict:
    resp = client.post(
        f"{settings.jev_decision_url}/decide/choice",
        json={"state": state, "question": question, "criteria": criteria},
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("choice") not in criteria:
        raise ValueError(f"unexpected choice {data.get('choice')!r}")
    return data


def score_item(item: dict[str, Any], client: httpx.Client | None = None) -> dict[str, Any] | None:
    """Return the jev_scores row for one item, or None if Jev failed."""
    state = build_state(item)
    owns = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_imp = ex.submit(_choose, client, state, QUESTION_IMPORTANCE, IMPORTANCE_CRITERIA)
            f_top = ex.submit(_choose, client, state, QUESTION_TOPIC, TOPIC_CRITERIA)
            imp, top = f_imp.result(), f_top.result()
    except Exception as exc:  # noqa: BLE001 - never raise; retry next run
        log.warning("jev scoring failed for item %s: %s", item.get("id"), exc)
        return None
    finally:
        if owns:
            client.close()
    return {
        "news_item_id": item["id"],
        "importance": imp["choice"],
        "confidence": imp.get("confidence"),
        "probabilities": imp.get("probabilities") or {},
        "topic": top["choice"],
        "topic_confidence": top.get("confidence"),
    }


def _unscored(hours: int, limit: int) -> list[dict[str, Any]]:
    with db.pool.connection() as conn:
        return conn.execute(
            """
            SELECT ni.id, ni.title, ni.summary_rss, ni.published_at,
                   f.name AS feed_name, f.category AS feed_category
            FROM news_items ni
            JOIN feeds f ON f.id = ni.feed_id
            WHERE COALESCE(ni.published_at, ni.fetched_at) > now() - make_interval(hours => %s)
              AND NOT EXISTS (SELECT 1 FROM jev_scores j WHERE j.news_item_id = ni.id)
            ORDER BY COALESCE(ni.published_at, ni.fetched_at) DESC
            LIMIT %s
            """,
            (hours, limit),
        ).fetchall()


def _save(row: dict[str, Any]) -> None:
    with db.pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO jev_scores
                (news_item_id, importance, confidence, probabilities, topic, topic_confidence)
            VALUES (%(news_item_id)s, %(importance)s, %(confidence)s, %(probabilities)s,
                    %(topic)s, %(topic_confidence)s)
            ON CONFLICT (news_item_id) DO NOTHING
            """,
            {**row, "probabilities": Jsonb(row["probabilities"])},
        )


def score_pending(hours: int = 48, limit: int = 200) -> dict[str, Any]:
    """Score recent items that have no jev_scores row yet. Never raises."""
    try:
        items = _unscored(hours, limit)
    except Exception as exc:  # noqa: BLE001
        log.warning("jev score_pending query failed: %s", exc)
        return {"pending": 0, "scored": 0, "failed": 0, "error": str(exc)}

    scored = 0
    with httpx.Client(timeout=30.0) as client, ThreadPoolExecutor(max_workers=POOL_SIZE) as pool:
        for row in pool.map(lambda it: score_item(it, client), items):
            if row is None:
                continue
            try:
                _save(row)
                scored += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("jev save failed for item %s: %s", row["news_item_id"], exc)
    return {"pending": len(items), "scored": scored, "failed": len(items) - scored}
