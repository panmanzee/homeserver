"""FastAPI app — the composition root.

Route handlers own the orchestration (fetch -> parse -> persist,
select -> enrich -> persist, resolve -> download -> upsert). The building
blocks come from app/feeds.py, app/enrich.py, app/prices.py, app/db.py.
"""

from __future__ import annotations

import logging
import secrets
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import db, enrich, notify, picks, web
from . import feeds as feeds_mod
from . import prices
from .config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("newsfeed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.pool.open()
    try:
        yield
    finally:
        db.pool.close()


app = FastAPI(title="newsfeed-api", version="1.0", lifespan=lifespan)


def require_api_key(x_api_key: str = Header(default="")) -> None:
    if not secrets.compare_digest(x_api_key, settings.service_api_key):
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")


AuthDep = Depends(require_api_key)


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class IngestRequest(BaseModel):
    feed_ids: list[int] | None = None


class EnrichRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)
    news_ids: list[int] | None = None


class PricesRequest(BaseModel):
    days: int = Field(default=settings.price_lookback_days_default, ge=1, le=90)


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.get("/health")
def health() -> dict[str, str]:
    db.ping()
    return {"status": "ok"}


@app.post("/ingest/rss", dependencies=[AuthDep])
def ingest_rss(req: IngestRequest = IngestRequest()) -> dict[str, Any]:
    feeds = db.list_feeds(feed_ids=req.feed_ids)
    if not feeds:
        return {"feeds": 0, "fetched": 0, "inserted": 0, "new_ids": []}

    def _fetch(feed: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], str | None]:
        try:
            raw = feeds_mod.fetch_feed(feed["url"])
            return feed, feeds_mod.parse_feed(raw, feed["id"]), None
        except Exception as exc:  # noqa: BLE001 - report per feed, never fail the batch
            return feed, [], str(exc)

    workers = max(1, min(settings.fetch_concurrency, len(feeds)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_fetch, feeds))

    fetched = 0
    new_ids: list[int] = []
    for feed, rows, err in results:
        if err:
            log.warning("feed %s failed: %s", feed["name"], err)
            db.set_feed_status(feed["id"], f"error: {err}")
            continue
        fetched += len(rows)
        inserted = db.insert_news_items(rows)
        new_ids.extend(inserted)
        db.set_feed_status(feed["id"], "ok")

    return {
        "feeds": len(feeds),
        "fetched": fetched,
        "inserted": len(new_ids),
        "new_ids": new_ids,
    }


@app.post("/enrich", dependencies=[AuthDep])
def enrich_items(req: EnrichRequest = EnrichRequest()) -> dict[str, Any]:
    expired = 0
    if not req.news_ids:
        expired = db.expire_stale_unenriched(settings.enrich_stale_hours)
    items = db.select_unenriched(limit=req.limit, news_ids=req.news_ids)
    ok = 0
    errors = 0

    for item in items:
        try:
            fulltext = feeds_mod.extract_fulltext(item["url"])
        except Exception as exc:  # noqa: BLE001
            log.warning("fulltext fetch failed for %s: %s", item["url"], exc)
            fulltext = None

        body_text, content_source = feeds_mod.resolve_body(item["summary_rss"], fulltext)
        db.save_article_content(item["id"], fulltext, content_source)

        try:
            result = enrich.call_llm(item, body_text)
        except enrich.EnrichmentError as exc:
            log.warning("enrichment failed for item %s: %s", item["id"], exc)
            db.save_enrichment_error(
                item["id"],
                model=enrich.current_model(),
                prompt_version=settings.prompt_version,
                error=str(exc),
            )
            errors += 1
            continue

        data = result.data
        db.save_enrichment(
            item["id"],
            model=result.model,
            prompt_version=settings.prompt_version,
            summary="\n".join(f"- {bullet}" for bullet in data.summary),
            sentiment=data.sentiment,
            sentiment_rationale=data.sentiment_rationale,
            event_type=data.event_type,
            importance=data.importance,
            raw_response=result.raw,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            tickers=enrich.ticker_rows(data),
            tags=data.topics,
        )
        ok += 1

    return {"processed": len(items), "ok": ok, "errors": errors, "expired_stale": expired}


@app.post("/prices/refresh", dependencies=[AuthDep])
def prices_refresh(req: PricesRequest = PricesRequest()) -> dict[str, Any]:
    symbols = db.resolve_price_symbols(req.days)
    if not symbols:
        return {"symbols": 0, "rows": 0, "errors": []}

    def _fetch(entry: dict[str, Any]) -> tuple[str, list[dict[str, Any]], str | None]:
        try:
            return entry["symbol"], prices.fetch_prices(entry["price_symbol"], req.days), None
        except Exception as exc:  # noqa: BLE001
            return entry["symbol"], [], str(exc)

    workers = max(1, min(settings.price_concurrency, len(symbols)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_fetch, symbols))

    total_rows = 0
    errors: list[dict[str, str]] = []
    for symbol, rows, err in results:
        if err:
            errors.append({"symbol": symbol, "error": err})
            continue
        total_rows += db.upsert_prices(symbol, rows)

    return {"symbols": len(symbols), "rows": total_rows, "errors": errors}


@app.post("/notify/urgent", dependencies=[AuthDep])
def notify_urgent() -> dict[str, Any]:
    """Push any `breaking` items not yet sent — bypasses the digest schedule."""
    items = db.select_unnotified(limit=10, breaking_only=True)
    sent_ids: list[int] = []
    for item in items:
        try:
            notify.send_telegram(notify.format_breaking(item))
        except notify.TelegramError as exc:
            log.warning("urgent telegram send failed for item %s: %s", item["id"], exc)
            break
        sent_ids.append(item["id"])
    return {"sent": db.mark_notified(sent_ids)}


@app.post("/notify/digest", dependencies=[AuthDep])
def notify_digest() -> dict[str, Any]:
    """Send one compact digest of everything not yet pushed. Run on a schedule."""
    items = db.select_unnotified(limit=settings.digest_max_items * 4)
    if not items:
        return {"messages": 0, "items": 0}

    messages = notify.format_digest(
        items,
        max_items=settings.digest_max_items,
        max_bullets=settings.digest_bullets_per_item,
    )
    try:
        sent = notify.send_all(messages)
    except notify.TelegramError as exc:
        raise HTTPException(status_code=502, detail=f"telegram send failed: {exc}")

    marked = db.mark_notified([i["id"] for i in items[: settings.digest_max_items]])
    return {"messages": sent, "items": marked}


@app.get("/news", dependencies=[AuthDep])
def news(
    since: datetime | None = Query(default=None),
    ticker: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    return db.query_news(since=since, ticker=ticker, tag=tag, limit=limit)


# --------------------------------------------------------------------------- #
# Web frontend — public within the tailnet, no API key (same trust model as
# rag-api's /ask and taskbot's /api/*: single reader, Tailscale is the
# perimeter). Separate from /news above, which stays internal/API-key-gated.
# --------------------------------------------------------------------------- #
@app.get("/api/articles")
def api_articles(
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    importance: str | None = Query(default=None),
    sentiment: str | None = Query(default=None),
    ticker: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    rows = db.query_articles(
        q=q, category=category, importance=importance, sentiment=sentiment,
        ticker=ticker, tag=tag, since=since, until=until, limit=limit, offset=offset,
    )
    return {"items": rows[:limit], "has_more": len(rows) > limit}


@app.get("/api/facets")
def api_facets() -> dict[str, Any]:
    return db.list_facets()


_FUNDAMENTALS_TTL = timedelta(hours=24)
_FUNDAMENTALS_FIELDS = (
    "trailing_pe", "forward_pe", "price_to_book", "market_cap",
    "profit_margin_pct", "revenue_growth_pct", "analyst_target_price",
    "analyst_rating",
)


def _attach_fundamentals(sections: dict[str, list[dict[str, Any]]]) -> None:
    """Best-effort, cached, and only for tickers that already cleared the
    price+news gate (a handful, not the full universe) — see the design
    spec's §3 on why fundamentals must never block or slow down a pick.
    Mutates each pick's "fundamentals" field in place."""
    all_picks = [p for bucket in sections.values() for p in bucket]
    if not all_picks:
        return
    symbols = [p["symbol"] for p in all_picks]
    cached = db.get_cached_fundamentals(symbols)
    now = datetime.now(timezone.utc)

    for symbol in symbols:
        row = cached.get(symbol)
        is_stale = row is None or (now - row["fetched_at"]) > _FUNDAMENTALS_TTL
        if is_stale:
            fresh = prices.fetch_fundamentals(symbol) or {f: None for f in _FUNDAMENTALS_FIELDS}
            db.upsert_fundamentals(symbol, fresh)
            cached[symbol] = fresh

    for p in all_picks:
        row = cached.get(p["symbol"]) or {}
        p["fundamentals"] = {f: row.get(f) for f in _FUNDAMENTALS_FIELDS}


@app.get("/api/picks")
def api_picks() -> dict[str, Any]:
    """Today's Picks — a transparent screener, not LLM advice (see
    app/picks.py's module docstring and the design spec)."""
    price_rows = db.recent_price_changes()
    ticker_news = db.recent_ticker_news(days=7)
    sections = picks.build_picks(price_rows, ticker_news)
    _attach_fundamentals(sections)
    return {"generated_at": datetime.now(timezone.utc).isoformat(), **sections}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return web.PAGE
