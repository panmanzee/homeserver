import os
from datetime import datetime, timezone

import pytest

psycopg = pytest.importorskip("psycopg")
DB_URL = os.environ.get("NEWSFEED_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="set NEWSFEED_TEST_DB_URL to run db tests")


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    import importlib

    from app import config as cfg_mod

    importlib.reload(cfg_mod)
    from app import db as db_mod

    importlib.reload(db_mod)  # db.py re-runs `from .config import settings` -> fresh
    # `app.main` only ever touches `db` via attribute lookup at call time
    # (`db.query_articles(...)`), so reloading `db_mod` in place is enough —
    # importing `main` fresh/plain avoids reloading `feeds`/`enrich`/`prices`/
    # `notify`, whose classes (e.g. PriceProviderError) other test modules
    # hold direct references to; reloading those would swap in new class
    # objects and break `pytest.raises(...)` isinstance checks elsewhere.
    from app import main as main_mod

    db_mod.pool.open()
    with db_mod.pool.connection() as c:
        c.execute(
            "TRUNCATE feeds, news_items, enrichments, tickers, news_tickers, "
            "news_tags, stock_prices RESTART IDENTITY CASCADE"
        )

    from fastapi.testclient import TestClient

    with TestClient(main_mod.app) as c:
        yield c, db_mod

    db_mod.pool.close()
    importlib.reload(cfg_mod)
    importlib.reload(db_mod)


def _seed(db_mod, title="Thailand tourism rebounds", **kw):
    with db_mod.pool.connection() as conn:
        row = conn.execute(
            "INSERT INTO feeds (name, url, category) VALUES ('f', 'https://example.com/f', %s) "
            "ON CONFLICT (url) DO UPDATE SET category = EXCLUDED.category RETURNING id",
            (kw.pop("category", "finance"),),
        ).fetchone()
    [news_id] = db_mod.insert_news_items(
        [
            {
                "feed_id": row["id"],
                "guid": title,
                "url": f"https://example.com/{title.replace(' ', '-')}",
                "title": title,
                "author": None,
                "summary_rss": None,
                "published_at": kw.pop("published_at", datetime.now(timezone.utc)),
            }
        ]
    )
    db_mod.save_enrichment(
        news_id,
        model="test",
        prompt_version="v4",
        summary="สรุป",
        sentiment=kw.pop("sentiment", "neutral"),
        sentiment_rationale="t",
        event_type="other",
        importance=kw.pop("importance", "routine"),
        raw_response={},
        input_tokens=1,
        output_tokens=1,
        tickers=[],
        tags=kw.pop("tags", []),
    )
    return news_id


def test_articles_requires_no_api_key(client):
    c, db_mod = client
    r = c.get("/api/articles")
    assert r.status_code == 200


def test_articles_default_list(client):
    c, db_mod = client
    _seed(db_mod, title="one")
    r = c.get("/api/articles")
    body = r.json()
    assert body["has_more"] is False
    assert len(body["items"]) == 1
    assert body["items"][0]["title"] == "one"


def test_articles_search_filters_by_q(client):
    c, db_mod = client
    _seed(db_mod, title="Thailand tourism rebounds")
    _seed(db_mod, title="Fed holds rates")
    r = c.get("/api/articles", params={"q": "thailand"})
    items = r.json()["items"]
    assert len(items) == 1 and items[0]["title"] == "Thailand tourism rebounds"


def test_articles_facet_filters(client):
    c, db_mod = client
    _seed(db_mod, title="breaking one", importance="breaking")
    _seed(db_mod, title="routine one", importance="routine")
    r = c.get("/api/articles", params={"importance": "breaking"})
    items = r.json()["items"]
    assert len(items) == 1 and items[0]["title"] == "breaking one"


def test_articles_has_more_flag(client):
    c, db_mod = client
    for i in range(3):
        _seed(db_mod, title=f"item {i}")
    r = c.get("/api/articles", params={"limit": 2})
    body = r.json()
    assert len(body["items"]) == 2
    assert body["has_more"] is True

    r2 = c.get("/api/articles", params={"limit": 2, "offset": 2})
    body2 = r2.json()
    assert len(body2["items"]) == 1
    assert body2["has_more"] is False


def test_facets_endpoint_shape(client):
    c, db_mod = client
    _seed(db_mod, title="one", tags=["ai-chips"], category="tech")
    r = c.get("/api/facets")
    body = r.json()
    assert "tech" in body["categories"]
    assert set(body["importances"]) == {"breaking", "notable", "routine"}
    assert set(body["sentiments"]) == {"positive", "negative", "neutral"}
    assert any(t["tag"] == "ai-chips" for t in body["top_tags"])


def test_index_page_is_self_contained_html(client):
    c, db_mod = client
    r = c.get("/")
    assert r.status_code == 200
    assert "<html" in r.text
    assert "<script src=" not in r.text
    assert '<link rel="stylesheet" href=' not in r.text


def test_existing_ingest_endpoint_still_requires_api_key(client):
    c, db_mod = client
    r = c.post("/ingest/rss", json={"feed_ids": []})
    assert r.status_code == 401


def _seed_pick(db_mod, symbol, *, prev_close, latest_close, importance="breaking",
                sentiment="positive", tags=("ai-chips",), name="Some Co"):
    with db_mod.pool.connection() as conn:
        conn.execute(
            "INSERT INTO tickers (symbol, name) VALUES (%s, %s) "
            "ON CONFLICT (symbol) DO UPDATE SET name = EXCLUDED.name",
            (symbol, name),
        )
        conn.execute(
            "INSERT INTO stock_prices (symbol, date, close) VALUES (%s, CURRENT_DATE - 1, %s) "
            "ON CONFLICT (symbol, date) DO UPDATE SET close = EXCLUDED.close",
            (symbol, prev_close),
        )
        conn.execute(
            "INSERT INTO stock_prices (symbol, date, close) VALUES (%s, CURRENT_DATE, %s) "
            "ON CONFLICT (symbol, date) DO UPDATE SET close = EXCLUDED.close",
            (symbol, latest_close),
        )
    _seed(db_mod, title=f"{symbol} news", importance=importance, sentiment=sentiment, tags=list(tags))
    # link the ticker to the article we just seeded (most recent by id)
    with db_mod.pool.connection() as conn:
        news_id = conn.execute(
            "SELECT id FROM news_items ORDER BY id DESC LIMIT 1"
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO news_tickers (news_item_id, symbol) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING",
            (news_id, symbol),
        )


def test_picks_endpoint_no_api_key_and_shape(client):
    c, db_mod = client
    r = c.get("/api/picks")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"generated_at", "tech", "healthcare", "other"}


def test_picks_endpoint_qualifying_ticker_appears_in_tech(client):
    c, db_mod = client
    _seed_pick(db_mod, "NVDA", prev_close=100, latest_close=110, name="NVIDIA")
    body = c.get("/api/picks").json()
    symbols = [p["symbol"] for p in body["tech"]]
    assert "NVDA" in symbols


def test_picks_endpoint_price_change_is_a_json_number_not_a_string(client):
    # stock_prices.close is Postgres `numeric` -> psycopg hands back Decimal;
    # regression guard for it leaking through as a JSON string.
    c, db_mod = client
    _seed_pick(db_mod, "NVDA", prev_close=100, latest_close=110, name="NVIDIA")
    body = c.get("/api/picks").json()
    pick = next(p for p in body["tech"] if p["symbol"] == "NVDA")
    assert isinstance(pick["price_change_pct"], float)
    assert pick["price_change_pct"] == 10.0
    assert isinstance(pick["score"], float)


def test_picks_endpoint_excludes_falling_price(client):
    c, db_mod = client
    _seed_pick(db_mod, "DOWN", prev_close=100, latest_close=90)
    body = c.get("/api/picks").json()
    all_symbols = {p["symbol"] for bucket in (body["tech"], body["healthcare"], body["other"]) for p in bucket}
    assert "DOWN" not in all_symbols
