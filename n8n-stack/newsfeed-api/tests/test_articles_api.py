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
