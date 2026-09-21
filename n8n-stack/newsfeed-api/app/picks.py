"""Today's Picks — a transparent, deterministic stock screener.

Deliberately NOT an LLM-generated recommendation: `enrich.py`'s prompt has a
standing rule that the LLM never predicts price direction or gives buy/sell
advice. This module only combines two signals already sitting in Postgres —
recent price direction and recent news attention/sentiment — with a visible
formula. Every field on a pick is auditable; there is no hidden opinion.
"""

from __future__ import annotations

from typing import Any

IMPORTANCE_WEIGHT = {"breaking": 3, "notable": 2, "routine": 1}
SENTIMENT_SIGN = {"positive": 1, "negative": -1, "neutral": 0}

TECH_KEYWORDS = (
    "ai", "artificial-intelligence", "machine-learning", "chip",
    "semiconductor", "gpu", "data-center", "datacenter", "cloud",
    "software", "robot", "quantum", "cyber", "tech",
)
HEALTH_KEYWORDS = (
    "health", "pharma", "biotech", "medic", "drug", "clinical", "fda",
    "vaccine", "diagnos",
)


def _matches(tags: set[str], keywords: tuple[str, ...]) -> bool:
    """Hyphen-token-boundary match: a keyword must line up with a whole
    hyphen-delimited segment of a tag, not just appear as a raw substring —
    otherwise short keywords like "ai" false-positive inside unrelated
    words ("retail"), and "tech" false-positives inside "biotech"."""
    for tag in tags:
        padded = f"-{tag}-"
        if any(f"-{kw}-" in padded for kw in keywords):
            return True
    return False


def classify_sector(tags: set[str]) -> str:
    """Derive a section from a ticker's own recent article tags — no
    hand-curated, staleness-prone ticker->sector table to maintain."""
    if _matches(tags, TECH_KEYWORDS):
        return "tech"
    if _matches(tags, HEALTH_KEYWORDS):
        return "healthcare"
    return "other"


def build_picks(
    price_rows: list[dict[str, Any]],
    ticker_news: list[dict[str, Any]],
    per_section: int = 8,
) -> dict[str, list[dict[str, Any]]]:
    """`price_rows`: [{symbol, name, latest_close, prev_close}, ...] (only
    symbols with >=2 days of history — see `db.recent_price_changes`).
    `ticker_news`: one row per (article, ticker) pair in the recent window —
    [{symbol, importance, sentiment, tags}, ...] (see `db.recent_ticker_news`).

    A ticker appears only if its price rose AND its recent news is net
    positive — "good price, good with news," not a softened approximation.
    """
    news_agg: dict[str, dict[str, Any]] = {}
    for row in ticker_news:
        sym = row["symbol"]
        a = news_agg.setdefault(
            sym,
            {
                "news_score": 0,
                "tags": set(),
                "article_count": 0,
                "sentiment_counts": {"positive": 0, "negative": 0, "neutral": 0},
            },
        )
        weight = IMPORTANCE_WEIGHT.get(row.get("importance"), 1)
        sign = SENTIMENT_SIGN.get(row.get("sentiment"), 0)
        a["news_score"] += weight * sign
        a["tags"].update(row.get("tags") or [])
        a["article_count"] += 1
        sentiment = row.get("sentiment")
        if sentiment in a["sentiment_counts"]:
            a["sentiment_counts"][sentiment] += 1

    candidates: list[dict[str, Any]] = []
    for price_row in price_rows:
        sym = price_row["symbol"]
        news = news_agg.get(sym)
        if news is None:
            continue  # no recent news at all -> nothing to rank it on

        prev_close = float(price_row["prev_close"]) if price_row["prev_close"] is not None else None
        if not prev_close:
            continue
        latest_close = float(price_row["latest_close"])
        # stock_prices.close is Postgres `numeric` -> psycopg gives Decimal;
        # cast to float here so every downstream field is a plain JSON number,
        # not a Decimal (which some JSON encoders render as a string).
        price_change_pct = (latest_close - prev_close) / prev_close * 100

        if price_change_pct <= 0 or news["news_score"] <= 0:
            continue

        candidates.append(
            {
                "symbol": sym,
                "name": price_row.get("name"),
                "sector": classify_sector(news["tags"]),
                "price_change_pct": round(price_change_pct, 2),
                "news_score": news["news_score"],
                "article_count": news["article_count"],
                "sentiment_counts": news["sentiment_counts"],
                "matched_tags": sorted(news["tags"])[:6],
                "score": round(price_change_pct + news["news_score"], 2),
            }
        )

    candidates.sort(key=lambda c: c["score"], reverse=True)

    sections: dict[str, list[dict[str, Any]]] = {"tech": [], "healthcare": [], "other": []}
    for c in candidates:
        bucket = sections[c["sector"]]
        if len(bucket) < per_section:
            bucket.append(c)
    return sections


__all__ = ["classify_sector", "build_picks", "IMPORTANCE_WEIGHT", "SENTIMENT_SIGN"]
