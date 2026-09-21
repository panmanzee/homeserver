import os
from datetime import datetime, timedelta, timezone

import pytest

psycopg = pytest.importorskip("psycopg")
DB_URL = os.environ.get("NEWSFEED_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="set NEWSFEED_TEST_DB_URL to run db tests")


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    import importlib

    from app import config as cfg_mod

    importlib.reload(cfg_mod)  # rebuild the Settings singleton with the scratch URL
    from app import db as db_mod

    importlib.reload(db_mod)  # db.py re-runs `from .config import settings` -> fresh
    db_mod.pool.open()
    with db_mod.pool.connection() as c:
        c.execute(
            "TRUNCATE feeds, news_items, enrichments, tickers, news_tickers, fundamentals, "
            "news_tags, stock_prices RESTART IDENTITY CASCADE"
        )
    yield db_mod
    db_mod.pool.close()
    importlib.reload(cfg_mod)  # restore for any later test
    importlib.reload(db_mod)


def _seed_article(
    db,
    *,
    title: str,
    feed_category: str = "finance",
    tags: list[str] | None = None,
    tickers: list[str] | None = None,
    sentiment: str = "neutral",
    importance: str | None = "routine",
    published_at: datetime | None = None,
    enriched: bool = True,
) -> int:
    tags = tags or []
    tickers = tickers or []
    published_at = published_at or datetime.now(timezone.utc)

    with db.pool.connection() as conn:
        row = conn.execute(
            "INSERT INTO feeds (name, url, category) VALUES (%s, %s, %s) "
            "ON CONFLICT (url) DO UPDATE SET category = EXCLUDED.category "
            "RETURNING id",
            (f"feed-{feed_category}", f"https://example.com/{feed_category}", feed_category),
        ).fetchone()
        feed_id = row["id"]

    [news_id] = db.insert_news_items(
        [
            {
                "feed_id": feed_id,
                "guid": title,
                "url": f"https://example.com/{title.replace(' ', '-')}",
                "title": title,
                "author": None,
                "summary_rss": None,
                "published_at": published_at,
            }
        ]
    )

    if enriched:
        db.save_enrichment(
            news_id,
            model="test-model",
            prompt_version="v4",
            summary="สรุปทดสอบ",
            sentiment=sentiment,
            sentiment_rationale="test",
            event_type="other",
            importance=importance,
            raw_response={},
            input_tokens=1,
            output_tokens=1,
            tickers=[{"symbol": s, "name": s, "price_symbol": s} for s in tickers],
            tags=tags,
        )
    return news_id


# --------------------------------------------------------------------------- #
# query_articles
# --------------------------------------------------------------------------- #
def test_query_articles_default_is_newest_first(db):
    old = _seed_article(db, title="old one", published_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    new = _seed_article(db, title="new one", published_at=datetime(2026, 2, 1, tzinfo=timezone.utc))
    ids = [r["id"] for r in db.query_articles()]
    assert ids == [new, old]


def test_query_articles_excludes_unenriched(db):
    _seed_article(db, title="not enriched", enriched=False)
    ok = _seed_article(db, title="enriched")
    ids = [r["id"] for r in db.query_articles()]
    assert ids == [ok]


def test_query_articles_q_matches_title_substring(db):
    hit = _seed_article(db, title="Thailand tourism rebounds")
    _seed_article(db, title="Fed holds rates")
    ids = [r["id"] for r in db.query_articles(q="thailand")]
    assert ids == [hit]


def test_query_articles_q_matches_tag_substring(db):
    hit = _seed_article(db, title="Regional roundup", tags=["thailand-investment"])
    _seed_article(db, title="Other roundup", tags=["china-economy"])
    ids = [r["id"] for r in db.query_articles(q="thailand")]
    assert ids == [hit]


def test_query_articles_category_filter(db):
    fin = _seed_article(db, title="finance piece", feed_category="finance")
    _seed_article(db, title="tech piece", feed_category="tech")
    ids = [r["id"] for r in db.query_articles(category="finance")]
    assert ids == [fin]


def test_query_articles_importance_and_sentiment_filters(db):
    breaking = _seed_article(db, title="big news", importance="breaking", sentiment="negative")
    _seed_article(db, title="small news", importance="routine", sentiment="neutral")
    assert [r["id"] for r in db.query_articles(importance="breaking")] == [breaking]
    assert [r["id"] for r in db.query_articles(sentiment="negative")] == [breaking]


def test_query_articles_ticker_filter_case_insensitive(db):
    hit = _seed_article(db, title="Apple earnings", tickers=["AAPL"])
    _seed_article(db, title="Other earnings", tickers=["MSFT"])
    assert [r["id"] for r in db.query_articles(ticker="aapl")] == [hit]


def test_query_articles_tag_filter_is_exact(db):
    hit = _seed_article(db, title="exact tag", tags=["ai-chips"])
    _seed_article(db, title="prefix tag", tags=["ai-chips-market"])
    assert [r["id"] for r in db.query_articles(tag="ai-chips")] == [hit]


def test_query_articles_since_until_bounds(db):
    early = _seed_article(db, title="early", published_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    mid = _seed_article(db, title="mid", published_at=datetime(2026, 2, 1, tzinfo=timezone.utc))
    _seed_article(db, title="late", published_at=datetime(2026, 3, 1, tzinfo=timezone.utc))
    ids = {
        r["id"]
        for r in db.query_articles(
            since=datetime(2026, 1, 15, tzinfo=timezone.utc),
            until=datetime(2026, 2, 15, tzinfo=timezone.utc),
        )
    }
    assert ids == {mid}
    assert early not in ids


def test_query_articles_fetches_one_extra_row_for_has_more(db):
    # db.query_articles returns up to limit+1 rows — the route layer trims
    # the extra row to derive `has_more` without a separate COUNT(*).
    for i in range(5):
        _seed_article(
            db, title=f"item {i}",
            published_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
        )
    page1 = db.query_articles(limit=2, offset=0)  # 3 rows: 2 + the "more" signal
    page2 = db.query_articles(limit=2, offset=2)  # 3 rows
    page3 = db.query_articles(limit=2, offset=4)  # 1 row: nothing left after it
    assert len(page1) == 3 and len(page2) == 3 and len(page3) == 1
    trimmed_ids = [r["id"] for r in page1[:2] + page2[:2] + page3[:2]]
    assert len(trimmed_ids) == len(set(trimmed_ids)) == 5


# --------------------------------------------------------------------------- #
# list_facets
# --------------------------------------------------------------------------- #
def test_list_facets_shape_and_counts(db):
    _seed_article(db, title="a", feed_category="finance", tags=["ai-chips"], tickers=["AAPL"])
    _seed_article(db, title="b", feed_category="tech", tags=["ai-chips"], tickers=["AAPL"])
    _seed_article(db, title="c", feed_category="tech", tags=["china-economy"])

    facets = db.list_facets()
    assert set(facets["categories"]) == {"finance", "tech"}
    assert set(facets["importances"]) == {"breaking", "notable", "routine"}
    assert set(facets["sentiments"]) == {"positive", "negative", "neutral"}

    top_tags = {t["tag"]: t["count"] for t in facets["top_tags"]}
    assert top_tags["ai-chips"] == 2
    assert top_tags["china-economy"] == 1

    tickers = {t["symbol"]: t["count"] for t in facets["tickers"]}
    assert tickers["AAPL"] == 2


def test_list_facets_excludes_unenriched_tags(db):
    _seed_article(db, title="not enriched", enriched=False, tags=[])
    facets = db.list_facets()
    assert facets["top_tags"] == []


# --------------------------------------------------------------------------- #
# recent_price_changes / recent_ticker_news (Today's Picks)
# --------------------------------------------------------------------------- #
def _seed_ticker(db, symbol, name="Some Co"):
    with db.pool.connection() as conn:
        conn.execute(
            "INSERT INTO tickers (symbol, name) VALUES (%s, %s) "
            "ON CONFLICT (symbol) DO UPDATE SET name = EXCLUDED.name",
            (symbol, name),
        )


def _seed_price(db, symbol, date, close):
    with db.pool.connection() as conn:
        conn.execute(
            "INSERT INTO stock_prices (symbol, date, close) VALUES (%s, %s, %s) "
            "ON CONFLICT (symbol, date) DO UPDATE SET close = EXCLUDED.close",
            (symbol, date, close),
        )


def test_recent_price_changes_returns_latest_and_prev_close(db):
    _seed_ticker(db, "NVDA", "NVIDIA Corporation")
    _seed_price(db, "NVDA", "2026-09-17", 100)
    _seed_price(db, "NVDA", "2026-09-18", 110)
    rows = {r["symbol"]: r for r in db.recent_price_changes()}
    assert rows["NVDA"]["latest_close"] == 110
    assert rows["NVDA"]["prev_close"] == 100
    assert rows["NVDA"]["name"] == "NVIDIA Corporation"


def test_recent_price_changes_excludes_single_day_history(db):
    _seed_ticker(db, "ONLYONE")
    _seed_price(db, "ONLYONE", "2026-09-18", 50)
    symbols = {r["symbol"] for r in db.recent_price_changes()}
    assert "ONLYONE" not in symbols


def test_recent_ticker_news_respects_days_window(db):
    recent = _seed_article(
        db, title="recent", tickers=["AAPL"],
        published_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    old = _seed_article(
        db, title="old", tickers=["AAPL"],
        published_at=datetime.now(timezone.utc) - timedelta(days=30),
    )
    rows = db.recent_ticker_news(days=7)
    assert any(r["symbol"] == "AAPL" for r in rows)
    # only the recent article's ticker link should show up in a 7-day window
    assert len(rows) == 1


def test_recent_ticker_news_excludes_failed_enrichment(db):
    # A ticker link can outlive a re-enrichment that later failed (save_enrichment_error
    # doesn't touch news_tickers) — the query must still filter on status='ok'.
    news_id = _seed_article(db, title="will fail", tickers=["AAPL"])
    db.save_enrichment_error(news_id, model="test", prompt_version="v4", error="boom")
    rows = db.recent_ticker_news(days=7)
    assert rows == []


def test_recent_ticker_news_includes_event_type(db):
    _seed_article(db, title="partnership news", tickers=["AAPL"])
    rows = db.recent_ticker_news(days=7)
    assert rows[0]["event_type"] == "other"  # _seed_article's default


def test_recent_price_changes_as_of_excludes_later_dates(db):
    # Backtest replay: as_of=2026-09-01 must not see the 09-05 close at all,
    # so a symbol whose only 2 rows straddle that cutoff has no "as of" pair.
    _seed_ticker(db, "NVDA")
    _seed_price(db, "NVDA", "2026-08-30", 90)
    _seed_price(db, "NVDA", "2026-09-01", 100)
    _seed_price(db, "NVDA", "2026-09-05", 110)

    as_of_rows = {r["symbol"]: r for r in db.recent_price_changes(as_of="2026-09-01")}
    assert as_of_rows["NVDA"]["latest_close"] == 100
    assert as_of_rows["NVDA"]["prev_close"] == 90

    today_rows = {r["symbol"]: r for r in db.recent_price_changes()}
    assert today_rows["NVDA"]["latest_close"] == 110
    assert today_rows["NVDA"]["prev_close"] == 100


def test_recent_ticker_news_as_of_excludes_later_articles(db):
    _seed_article(
        db, title="before cutoff", tickers=["AAPL"],
        published_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    _seed_article(
        db, title="after cutoff", tickers=["AAPL"],
        published_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
    )
    rows = db.recent_ticker_news(days=30, as_of="2026-09-05")
    assert len(rows) == 1


# --------------------------------------------------------------------------- #
# fundamentals cache
# --------------------------------------------------------------------------- #
def test_get_cached_fundamentals_empty_when_no_rows(db):
    _seed_ticker(db, "NVDA")
    assert db.get_cached_fundamentals(["NVDA"]) == {}


def test_upsert_then_get_cached_fundamentals_roundtrip(db):
    _seed_ticker(db, "NVDA")
    db.upsert_fundamentals("NVDA", {
        "trailing_pe": 30.2, "forward_pe": 25.3, "price_to_book": 12.1,
        "market_cap": 123456789, "profit_margin_pct": 35.1,
        "revenue_growth_pct": 12.2, "analyst_target_price": 250.0,
        "analyst_rating": "buy",
    })
    cached = db.get_cached_fundamentals(["NVDA"])
    assert cached["NVDA"]["trailing_pe"] == 30.2
    assert cached["NVDA"]["analyst_rating"] == "buy"
    assert "fetched_at" in cached["NVDA"]


def test_upsert_fundamentals_with_none_values_still_caches(db):
    # A symbol Yahoo has nothing on is still worth caching as "checked,
    # nothing found" so it isn't refetched every request.
    _seed_ticker(db, "NOINFO")
    db.upsert_fundamentals("NOINFO", {
        "trailing_pe": None, "forward_pe": None, "price_to_book": None,
        "market_cap": None, "profit_margin_pct": None,
        "revenue_growth_pct": None, "analyst_target_price": None,
        "analyst_rating": None,
    })
    cached = db.get_cached_fundamentals(["NOINFO"])
    assert "NOINFO" in cached
    assert cached["NOINFO"]["trailing_pe"] is None


def test_upsert_fundamentals_overwrites_on_refresh(db):
    _seed_ticker(db, "NVDA")
    db.upsert_fundamentals("NVDA", {"trailing_pe": 30.0, "forward_pe": None,
        "price_to_book": None, "market_cap": None, "profit_margin_pct": None,
        "revenue_growth_pct": None, "analyst_target_price": None, "analyst_rating": None})
    db.upsert_fundamentals("NVDA", {"trailing_pe": 32.5, "forward_pe": None,
        "price_to_book": None, "market_cap": None, "profit_margin_pct": None,
        "revenue_growth_pct": None, "analyst_target_price": None, "analyst_rating": None})
    cached = db.get_cached_fundamentals(["NVDA"])
    assert cached["NVDA"]["trailing_pe"] == 32.5


def test_get_cached_fundamentals_filters_by_symbol_list(db):
    _seed_ticker(db, "A")
    _seed_ticker(db, "B")
    db.upsert_fundamentals("A", {"trailing_pe": 1, "forward_pe": None, "price_to_book": None,
        "market_cap": None, "profit_margin_pct": None, "revenue_growth_pct": None,
        "analyst_target_price": None, "analyst_rating": None})
    db.upsert_fundamentals("B", {"trailing_pe": 2, "forward_pe": None, "price_to_book": None,
        "market_cap": None, "profit_margin_pct": None, "revenue_growth_pct": None,
        "analyst_target_price": None, "analyst_rating": None})
    cached = db.get_cached_fundamentals(["A"])
    assert set(cached.keys()) == {"A"}
