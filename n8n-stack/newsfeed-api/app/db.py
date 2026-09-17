"""Data-access layer: connection pool + typed helper functions.

Every helper opens its own short transaction. Business logic lives in the route
handlers (app/main.py); this module only reads and writes rows.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .config import settings

pool = ConnectionPool(
    settings.database_url,
    min_size=0,
    max_size=5,
    open=False,
    kwargs={"row_factory": dict_row},
)


def ping() -> bool:
    with pool.connection() as conn:
        conn.execute("SELECT 1")
    return True


# --------------------------------------------------------------------------- #
# Feeds / ingest
# --------------------------------------------------------------------------- #
def list_feeds(active_only: bool = True, feed_ids: list[int] | None = None) -> list[dict[str, Any]]:
    sql = "SELECT id, name, url, category FROM feeds"
    clauses, params = [], []
    if active_only:
        clauses.append("active = true")
    if feed_ids:
        clauses.append("id = ANY(%s)")
        params.append(feed_ids)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY id"
    with pool.connection() as conn:
        return conn.execute(sql, params).fetchall()


def insert_news_items(rows: list[dict[str, Any]]) -> list[int]:
    """Insert candidate items, skipping duplicates. Returns the new ids."""
    if not rows:
        return []
    new_ids: list[int] = []
    with pool.connection() as conn, conn.transaction():
        with conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    """
                    INSERT INTO news_items
                        (feed_id, guid, url, title, author, summary_rss, published_at)
                    VALUES
                        (%(feed_id)s, %(guid)s, %(url)s, %(title)s, %(author)s,
                         %(summary_rss)s, %(published_at)s)
                    ON CONFLICT DO NOTHING
                    RETURNING id
                    """,
                    r,
                )
                got = cur.fetchone()
                if got:
                    new_ids.append(got["id"])
    return new_ids


def set_feed_status(feed_id: int, status: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            "UPDATE feeds SET last_fetched_at = now(), last_status = %s WHERE id = %s",
            (status[:500], feed_id),
        )


# --------------------------------------------------------------------------- #
# Enrichment
# --------------------------------------------------------------------------- #
def select_unenriched(limit: int, news_ids: list[int] | None = None) -> list[dict[str, Any]]:
    """Items to enrich for the next digest.

    Enrichment exists to feed Telegram, so by default only items still pending a
    push (`tg_notified_at IS NULL`) are considered — an article already marked
    as sent/skipped is not worth spending a Claude call on. Passing `news_ids`
    overrides that and force-enriches exactly those ids.
    """
    sql = """
        SELECT ni.id, ni.url, ni.title, ni.author, ni.summary_rss, ni.published_at,
               f.name AS feed_name
        FROM news_items ni
        JOIN feeds f ON f.id = ni.feed_id
        WHERE NOT EXISTS (
            SELECT 1 FROM enrichments e
            WHERE e.news_item_id = ni.id AND e.status = 'ok'
        )
    """
    params: list[Any] = []
    if news_ids:
        sql += " AND ni.id = ANY(%s)"
        params.append(news_ids)
    else:
        sql += " AND ni.tg_notified_at IS NULL"
    sql += " ORDER BY ni.published_at DESC NULLS LAST, ni.id DESC LIMIT %s"
    params.append(limit)
    with pool.connection() as conn:
        return conn.execute(sql, params).fetchall()


def expire_stale_unenriched(hours: int) -> int:
    """Give up on articles older than `hours` that were never enriched — mark
    them notified so they get neither an LLM call nor a digest slot. Keeps the
    digest current when the pipeline falls behind."""
    with pool.connection() as conn:
        cur = conn.execute(
            """
            UPDATE news_items ni SET tg_notified_at = now()
            WHERE ni.tg_notified_at IS NULL
              AND ni.fetched_at < now() - make_interval(hours => %s)
              AND NOT EXISTS (
                  SELECT 1 FROM enrichments e
                  WHERE e.news_item_id = ni.id AND e.status = 'ok'
              )
            """,
            (hours,),
        )
        return cur.rowcount


def save_article_content(news_item_id: int, content: str | None, content_source: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            "UPDATE news_items SET content = %s, content_source = %s WHERE id = %s",
            (content, content_source, news_item_id),
        )


def save_enrichment(
    news_item_id: int,
    *,
    model: str,
    prompt_version: str,
    summary: str,
    sentiment: str,
    sentiment_rationale: str,
    event_type: str,
    importance: str | None,
    raw_response: dict[str, Any],
    input_tokens: int | None,
    output_tokens: int | None,
    tickers: list[dict[str, str]],
    tags: list[str],
) -> None:
    """Persist a successful enrichment and its ticker/tag links atomically.

    `tickers` items look like {"symbol": "AAPL", "name": "Apple Inc.",
    "price_symbol": "AAPL"}.
    """
    with pool.connection() as conn, conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO enrichments
                    (news_item_id, model, prompt_version, summary, sentiment,
                     sentiment_rationale, event_type, importance, raw_response,
                     input_tokens, output_tokens, status, error)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ok', NULL)
                ON CONFLICT (news_item_id) DO UPDATE SET
                    model = EXCLUDED.model,
                    prompt_version = EXCLUDED.prompt_version,
                    summary = EXCLUDED.summary,
                    sentiment = EXCLUDED.sentiment,
                    sentiment_rationale = EXCLUDED.sentiment_rationale,
                    event_type = EXCLUDED.event_type,
                    importance = EXCLUDED.importance,
                    raw_response = EXCLUDED.raw_response,
                    input_tokens = EXCLUDED.input_tokens,
                    output_tokens = EXCLUDED.output_tokens,
                    status = 'ok',
                    error = NULL,
                    created_at = now()
                """,
                (
                    news_item_id, model, prompt_version, summary, sentiment,
                    sentiment_rationale, event_type, importance, Jsonb(raw_response),
                    input_tokens, output_tokens,
                ),
            )

            # Re-runs: clear prior links for this item, then re-insert.
            cur.execute("DELETE FROM news_tickers WHERE news_item_id = %s", (news_item_id,))
            cur.execute("DELETE FROM news_tags WHERE news_item_id = %s", (news_item_id,))

            for t in tickers:
                cur.execute(
                    """
                    INSERT INTO tickers (symbol, name, price_symbol)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (symbol) DO UPDATE
                        SET name = COALESCE(tickers.name, EXCLUDED.name)
                    """,
                    (t["symbol"], t.get("name"), t.get("price_symbol")),
                )
                cur.execute(
                    """
                    INSERT INTO news_tickers (news_item_id, symbol)
                    VALUES (%s, %s) ON CONFLICT DO NOTHING
                    """,
                    (news_item_id, t["symbol"]),
                )

            for tag in tags:
                cur.execute(
                    """
                    INSERT INTO news_tags (news_item_id, tag)
                    VALUES (%s, %s) ON CONFLICT DO NOTHING
                    """,
                    (news_item_id, tag),
                )


def save_enrichment_error(
    news_item_id: int, *, model: str, prompt_version: str, error: str
) -> None:
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO enrichments
                (news_item_id, model, prompt_version, status, error)
            VALUES (%s, %s, %s, 'error', %s)
            ON CONFLICT (news_item_id) DO UPDATE SET
                model = EXCLUDED.model,
                prompt_version = EXCLUDED.prompt_version,
                status = 'error',
                error = EXCLUDED.error,
                created_at = now()
            """,
            (news_item_id, model, prompt_version, error[:2000]),
        )


# --------------------------------------------------------------------------- #
# Prices
# --------------------------------------------------------------------------- #
def resolve_price_symbols(days: int) -> list[dict[str, Any]]:
    """Watchlist tickers UNION tickers tagged in news within the last `days`."""
    with pool.connection() as conn:
        return conn.execute(
            """
            SELECT DISTINCT t.symbol,
                   COALESCE(t.price_symbol, t.symbol) AS price_symbol
            FROM tickers t
            WHERE t.on_watchlist = true
            UNION
            SELECT DISTINCT t.symbol,
                   COALESCE(t.price_symbol, t.symbol) AS price_symbol
            FROM tickers t
            JOIN news_tickers nt ON nt.symbol = t.symbol
            JOIN news_items ni ON ni.id = nt.news_item_id
            WHERE ni.published_at > now() - make_interval(days => %s)
            ORDER BY symbol
            """,
            (days,),
        ).fetchall()


def upsert_prices(symbol: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    n = 0
    with pool.connection() as conn, conn.transaction():
        with conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    """
                    INSERT INTO stock_prices
                        (symbol, date, open, high, low, close, volume, source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        open = EXCLUDED.open, high = EXCLUDED.high,
                        low = EXCLUDED.low, close = EXCLUDED.close,
                        volume = EXCLUDED.volume, source = EXCLUDED.source,
                        fetched_at = now()
                    """,
                    (
                        symbol, r["date"], r.get("open"), r.get("high"),
                        r.get("low"), r.get("close"), r.get("volume"),
                        settings.price_provider,
                    ),
                )
                n += 1
    return n


# --------------------------------------------------------------------------- #
# Telegram delivery
# --------------------------------------------------------------------------- #
def select_unnotified(limit: int, *, breaking_only: bool = False) -> list[dict[str, Any]]:
    """Enriched items not yet pushed to Telegram, newest first."""
    sql = """
        SELECT id, url, title, importance, tickers, summary
        FROM v_news_enriched
        WHERE tg_notified_at IS NULL
          AND enrichment_status = 'ok'
    """
    if breaking_only:
        sql += " AND importance = 'breaking'"
    sql += " ORDER BY published_at DESC NULLS LAST, id DESC LIMIT %s"
    with pool.connection() as conn:
        return conn.execute(sql, (limit,)).fetchall()


def mark_notified(news_ids: list[int]) -> int:
    if not news_ids:
        return 0
    with pool.connection() as conn:
        cur = conn.execute(
            "UPDATE news_items SET tg_notified_at = now() "
            "WHERE id = ANY(%s) AND tg_notified_at IS NULL",
            (news_ids,),
        )
        return cur.rowcount


# --------------------------------------------------------------------------- #
# Read API
# --------------------------------------------------------------------------- #
def query_news(
    since: datetime | None = None,
    ticker: str | None = None,
    tag: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM v_news_enriched WHERE 1 = 1"
    params: list[Any] = []
    if since is not None:
        sql += " AND published_at >= %s"
        params.append(since)
    if ticker:
        sql += " AND %s = ANY(tickers)"
        params.append(ticker.upper())
    if tag:
        sql += " AND %s = ANY(tags)"
        params.append(tag.lower())
    sql += " ORDER BY published_at DESC NULLS LAST, id DESC LIMIT %s"
    params.append(min(limit, 500))
    with pool.connection() as conn:
        return conn.execute(sql, params).fetchall()


def query_articles(
    q: str | None = None,
    category: str | None = None,
    importance: str | None = None,
    sentiment: str | None = None,
    ticker: str | None = None,
    tag: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 30,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Browsable article list for the web frontend: only enriched items,
    newest first, with the fuller filter set `/api/articles` exposes.

    Fetches `limit + 1` rows so the caller can tell whether there's another
    page without a separate COUNT(*) — trim the extra row before returning
    to the client.
    """
    sql = "SELECT * FROM v_news_enriched WHERE enrichment_status = 'ok'"
    params: list[Any] = []
    if q:
        sql += (
            " AND (title ILIKE %s"
            " OR EXISTS (SELECT 1 FROM unnest(tags) t WHERE t ILIKE %s))"
        )
        needle = f"%{q}%"
        params.extend([needle, needle])
    if category:
        sql += " AND feed_category = %s"
        params.append(category)
    if importance:
        sql += " AND importance = %s"
        params.append(importance)
    if sentiment:
        sql += " AND sentiment = %s"
        params.append(sentiment)
    if ticker:
        sql += " AND %s = ANY(tickers)"
        params.append(ticker.upper())
    if tag:
        sql += " AND %s = ANY(tags)"
        params.append(tag.lower())
    if since is not None:
        sql += " AND published_at >= %s"
        params.append(since)
    if until is not None:
        sql += " AND published_at <= %s"
        params.append(until)
    sql += " ORDER BY published_at DESC NULLS LAST, id DESC LIMIT %s OFFSET %s"
    params.extend([min(limit, 100) + 1, offset])
    with pool.connection() as conn:
        return conn.execute(sql, params).fetchall()


_IMPORTANCE_VALUES = ["breaking", "notable", "routine"]
_SENTIMENT_VALUES = ["positive", "negative", "neutral"]


def list_facets(top_n: int = 40) -> dict[str, Any]:
    """Values to populate the web frontend's filter chips/dropdowns.

    `categories` comes from `feeds` (small, fixed); importance/sentiment are
    the schema's own CHECK-constrained enums (hardcoded here, not queried —
    they're closed sets); `top_tags`/`tickers` are computed live from
    enriched articles — cheap at this row count, no caching needed.
    """
    with pool.connection() as conn:
        categories = [
            r["category"]
            for r in conn.execute(
                "SELECT DISTINCT category FROM feeds WHERE category IS NOT NULL ORDER BY category"
            ).fetchall()
        ]
        top_tags = conn.execute(
            """
            SELECT nt.tag, count(*) AS count
            FROM news_tags nt
            JOIN enrichments e ON e.news_item_id = nt.news_item_id AND e.status = 'ok'
            GROUP BY nt.tag
            ORDER BY count DESC, nt.tag
            LIMIT %s
            """,
            (top_n,),
        ).fetchall()
        tickers = conn.execute(
            """
            SELECT nk.symbol, count(*) AS count
            FROM news_tickers nk
            JOIN enrichments e ON e.news_item_id = nk.news_item_id AND e.status = 'ok'
            GROUP BY nk.symbol
            ORDER BY count DESC, nk.symbol
            LIMIT %s
            """,
            (top_n,),
        ).fetchall()
    return {
        "categories": categories,
        "importances": _IMPORTANCE_VALUES,
        "sentiments": _SENTIMENT_VALUES,
        "top_tags": top_tags,
        "tickers": tickers,
    }


__all__ = [
    "pool",
    "ping",
    "list_feeds",
    "insert_news_items",
    "set_feed_status",
    "select_unenriched",
    "expire_stale_unenriched",
    "save_article_content",
    "save_enrichment",
    "save_enrichment_error",
    "resolve_price_symbols",
    "upsert_prices",
    "select_unnotified",
    "mark_notified",
    "query_news",
    "query_articles",
    "list_facets",
    "psycopg",
]
