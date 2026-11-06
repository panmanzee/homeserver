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
import httpx
from pydantic import BaseModel, Field

from . import db, enrich, notify, picks, web
from . import feeds as feeds_mod
from . import market, prices
from .config import settings
from .regions import REGIONS, REGION_ORDER, MOBILE_REGION_ORDER

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
        raw_with_jev = dict(result.raw)
        if result.jev_check is not None:
            raw_with_jev["_jev_check"] = result.jev_check
        ticker_rows = enrich.ticker_rows(data)
        db.save_enrichment(
            item["id"],
            model=result.model,
            prompt_version=settings.prompt_version,
            summary="\n".join(f"- {bullet}" for bullet in data.summary),
            sentiment=data.sentiment,
            sentiment_rationale=data.sentiment_rationale,
            event_type=data.event_type,
            importance=data.importance,
            raw_response=raw_with_jev,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            tickers=ticker_rows,
            tags=data.topics,
        )
        symbols = [t["symbol"] for t in ticker_rows]
        regions = market.infer_regions(item["title"], symbols, None)
        db.upsert_news_regions(item["id"], regions)
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
    """Send the daily topic list (headlines only + web link). Run once a day."""
    # every headline counts, even ones the LLM has not summarised yet
    items = db.select_unnotified(limit=settings.digest_max_items, enriched_only=False)
    if not items:
        return {"messages": 0, "items": 0}

    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo(settings.digest_tz)).strftime("%a %d %b")
    messages = notify.format_digest(
        items, web_url=settings.newsfeed_web_url, date_label=today
    )
    try:
        sent = notify.send_all(messages)
    except notify.TelegramError as exc:
        raise HTTPException(status_code=502, detail=f"telegram send failed: {exc}")

    marked = db.mark_notified([i["id"] for i in items])
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


# --------------------------------------------------------------------------- #
# Multi-region investing hub (Phase 1) — regions config + per-region
# news/stocks + system status. All reads hit our own DB only, never a live
# third-party call (Rule 8: cache aggressively, no live calls on page load).
# --------------------------------------------------------------------------- #
@app.get("/api/regions")
def api_regions() -> dict[str, Any]:
    """Region config + live-ish tile data (index level/change, market status,
    top headline, sentiment ratio) for the Today home page's 5 map tiles."""
    quotes = db.latest_index_quotes_all()
    out = []
    for region_id in REGION_ORDER:
        region = REGIONS[region_id]
        status = market.get_market_status(region_id)
        quote = quotes.get(region_id)
        headlines = db.query_region_articles(region_id, limit=1)
        top_headline = headlines[0]["title"] if headlines else None
        out.append({
            "id": region_id,
            "name": region.name,
            "short_name": region.short_name,
            "currency": region.currency,
            "primary_index": region.indexes[0].name,
            "index_level": float(quote["level"]) if quote and quote.get("level") is not None else None,
            "index_change_pct": float(quote["change_pct"]) if quote and quote.get("change_pct") is not None else None,
            "index_stale": quote is None,
            "market_status": status.status,
            "local_time": status.local_time,
            "next_change": status.next_change,
            "top_headline": top_headline,
        })
    return {"regions": out, "order": REGION_ORDER, "mobile_order": MOBILE_REGION_ORDER}


@app.get("/api/regions/{region_id}/news")
def api_region_news(
    region_id: str,
    q: str | None = Query(default=None),
    importance: str | None = Query(default=None),
    sentiment: str | None = Query(default=None),
    ticker: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    if region_id not in REGIONS:
        raise HTTPException(status_code=404, detail=f"unknown region: {region_id}")
    rows = db.query_region_articles(
        region_id, q=q, importance=importance, sentiment=sentiment,
        ticker=ticker, tag=tag, since=since, limit=limit, offset=offset,
    )
    return {"items": rows[:limit], "has_more": len(rows) > limit}


@app.get("/api/regions/{region_id}/stocks")
def api_region_stocks(region_id: str) -> dict[str, Any]:
    """Screener rows for one region — price/fundamentals come from our own
    cache only (Rule 8); a ticker with no cached data yet shows nulls with
    a freshness timestamp, never a live fetch triggered by page load."""
    if region_id not in REGIONS:
        raise HTTPException(status_code=404, detail=f"unknown region: {region_id}")
    tickers = db.list_region_tickers(region_id)
    symbols = [t["symbol"] for t in tickers]
    fundamentals = db.get_cached_fundamentals(symbols)
    price_changes = {r["symbol"]: r for r in db.recent_price_changes()}

    rows = []
    freshest_fund = None
    for t in tickers:
        sym = t["symbol"]
        fund = fundamentals.get(sym, {})
        chg = price_changes.get(sym)
        pct = None
        if chg and chg.get("latest_close") and chg.get("prev_close"):
            try:
                pct = round((float(chg["latest_close"]) - float(chg["prev_close"])) / float(chg["prev_close"]) * 100, 2)
            except ZeroDivisionError:
                pct = None
        rows.append({
            "symbol": sym, "name": t["name"], "sector": t["sector"],
            "price": float(chg["latest_close"]) if chg and chg.get("latest_close") is not None else None,
            "change_1d_pct": pct,
            "market_cap": fund.get("market_cap"),
            "trailing_pe": fund.get("trailing_pe"),
            "forward_pe": fund.get("forward_pe"),
            "price_to_book": fund.get("price_to_book"),
            "profit_margin_pct": fund.get("profit_margin_pct"),
            "revenue_growth_pct": fund.get("revenue_growth_pct"),
        })
        if fund.get("fetched_at") and (freshest_fund is None or fund["fetched_at"] > freshest_fund):
            freshest_fund = fund["fetched_at"]

    return {
        "region": region_id,
        "count": len(rows),
        "rows": rows,
        "fundamentals_updated": freshest_fund.isoformat() if freshest_fund else None,
    }


@app.get("/api/status")
def api_status() -> dict[str, Any]:
    """System status: last run per job + basic data freshness, for the
    help-menu "System status" panel (Rule: never a blank panel without
    an explanation of when data will arrive)."""
    return {"jobs": db.latest_job_runs()}


@app.post("/jobs/backfill_news_regions", dependencies=[AuthDep])
def job_backfill_news_regions(limit: int = Query(default=500, ge=1, le=5000)) -> dict[str, Any]:
    """One-off/catch-up job: tag already-enriched articles with regions.
    Going forward, new articles are tagged automatically in /enrich."""
    run_id = db.record_job_start("backfill_news_regions")
    try:
        count = db.backfill_news_regions(limit=limit)
        db.record_job_end(run_id, "ok", counts={"tagged": count})
        return {"tagged": count}
    except Exception as exc:  # noqa: BLE001
        db.record_job_end(run_id, "error", errors=[str(exc)])
        raise


@app.post("/jobs/refresh_index_snapshot", dependencies=[AuthDep])
def job_refresh_index_snapshot() -> dict[str, Any]:
    """Cheap job (5 symbols): index level + % change per region, for the
    Today home tiles. Safe to run every 15 min during market hours."""
    run_id = db.record_job_start("refresh_index_snapshot")
    results = []
    errors = []
    for region_id, region in REGIONS.items():
        index = region.indexes[0]
        try:
            rows = prices.fetch_prices(index.yahoo, 30)
            if len(rows) >= 2:
                latest, prev = rows[-1], rows[-2]
                pct = round((latest["close"] - prev["close"]) / prev["close"] * 100, 2) if prev["close"] else None
                db.upsert_index_quote(region_id, index.yahoo, index.name, latest["close"], pct, is_primary=True)
                results.append({"region": region_id, "level": latest["close"], "change_pct": pct})
            elif len(rows) == 1:
                # Some indexes (^SET.BK observed) only ever return 1 bar from
                # Yahoo's chart API regardless of range — a real free-data-
                # source limitation, not a bug (verified: SET.BK/^SETI/
                # SET50.BK all 404, ^SET.BK is the only valid symbol and it
                # genuinely has thin history there). Fall back to comparing
                # against our own previously-stored quote instead of
                # fabricating a % change.
                latest = rows[0]
                prev_quote = db.latest_index_quote(region_id)
                pct = None
                if prev_quote and prev_quote.get("level"):
                    pct = round((float(latest["close"]) - float(prev_quote["level"])) / float(prev_quote["level"]) * 100, 2)
                db.upsert_index_quote(region_id, index.yahoo, index.name, latest["close"], pct, is_primary=True)
                results.append({"region": region_id, "level": latest["close"], "change_pct": pct,
                                 "note": "single-bar source, change vs. last stored quote" if pct is not None else "single-bar source, no prior quote to compare"})
            else:
                errors.append({"region": region_id, "error": "insufficient price history"})
        except Exception as exc:  # noqa: BLE001
            errors.append({"region": region_id, "error": str(exc)})
    db.record_job_end(run_id, "ok" if not errors else "partial", counts={"updated": len(results)}, errors=errors)
    return {"updated": results, "errors": errors}


@app.post("/jobs/refresh_region_prices", dependencies=[AuthDep])
def job_refresh_region_prices(
    region_id: str = Query(...),
    days: int = Query(default=10, ge=5, le=365),
) -> dict[str, Any]:
    """Refresh OHLCV for every ticker in one region's universe. Run this
    staggered per region (not all 5 at once) to be gentle on Yahoo's
    unofficial endpoint even though it has no documented hard cap."""
    if region_id not in REGIONS:
        raise HTTPException(status_code=404, detail=f"unknown region: {region_id}")
    run_id = db.record_job_start(f"refresh_region_prices:{region_id}")
    tickers = db.list_region_tickers(region_id)

    def _fetch(t: dict[str, Any]) -> tuple[str, list[dict[str, Any]], str | None]:
        try:
            return t["symbol"], prices.fetch_prices(t["price_symbol"], days), None
        except Exception as exc:  # noqa: BLE001
            return t["symbol"], [], str(exc)

    workers = max(1, min(settings.price_concurrency, len(tickers))) if tickers else 1
    total_rows = 0
    errors: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool_exec:
        for symbol, rows, err in pool_exec.map(_fetch, tickers):
            if err:
                errors.append({"symbol": symbol, "error": err})
                continue
            total_rows += db.upsert_prices(symbol, rows)

    status = "ok" if not errors else ("partial" if total_rows > 0 else "error")
    db.record_job_end(run_id, status, counts={"symbols": len(tickers), "rows": total_rows}, errors=errors)
    return {"region": region_id, "symbols": len(tickers), "rows": total_rows, "errors": errors}


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


@app.get("/api/chart")
def api_chart(
    symbol: str = Query(...),
    days: int = Query(default=90, ge=5, le=365),
) -> dict[str, Any]:
    """OHLCV history for the Trading tab's candlestick chart. Indicators
    (EMA/SMA/support-resistance) are computed client-side from this raw
    series — no separate indicator endpoint needed, and no LLM in the loop
    for numbers that are pure arithmetic on real price data."""
    rows = db.chart_prices(symbol, days)
    return {
        "symbol": symbol.upper(),
        "candles": [
            {
                "date": r["date"].isoformat(),
                "open": float(r["open"]) if r["open"] is not None else None,
                "high": float(r["high"]) if r["high"] is not None else None,
                "low": float(r["low"]) if r["low"] is not None else None,
                "close": float(r["close"]) if r["close"] is not None else None,
                "volume": r["volume"],
            }
            for r in rows
        ],
    }


@app.get("/api/symbols")
def api_symbols() -> dict[str, Any]:
    """Symbols with price history, for the Trading tab's search/picker."""
    rows = db.list_available_symbols()
    return {"symbols": [{"symbol": r["symbol"], "name": r["name"]} for r in rows]}


def _ema(values: list[float], period: int) -> list[float | None]:
    if len(values) < period:
        return [None] * len(values)
    k = 2 / (period + 1)
    out: list[float | None] = [None] * (period - 1)
    seed = sum(values[:period]) / period
    out.append(seed)
    prev = seed
    for v in values[period:]:
        prev = v * k + prev * (1 - k)
        out.append(prev)
    return out


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


@app.get("/api/verdict")
def api_verdict(symbol: str = Query(...)) -> dict[str, Any]:
    """AI-synthesized read on one symbol: real price trend + real
    fundamentals + real recent news, routed through Jev (jev-decision-server)
    for a structured Choice (bullish/neutral/bearish) + Score (risk level).

    This is decision support, not investment advice or automated trading —
    the user reads this and decides for themselves. See the trading-tab
    scope boundary: no broker integration, no auto-execution, ever.

    Design: all the arithmetic (trend, RSI, support/resistance) is computed
    here in plain Python from real DB data — Jev is only asked to SYNTHESIZE
    a judgment from that real state, never to invent numbers itself.
    """
    symbol = symbol.upper()
    price_rows = db.chart_prices(symbol, days=90)
    if not price_rows:
        raise HTTPException(404, f"no price history for {symbol}")

    closes = [float(r["close"]) for r in price_rows if r["close"] is not None]
    if len(closes) < 5:
        raise HTTPException(404, f"not enough price history for {symbol} to form a verdict")

    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    rsi = _rsi(closes)
    latest_close = closes[-1]
    period_high = max(closes)
    period_low = min(closes)
    trend = "unknown"
    if ema20[-1] is not None and ema50[-1] is not None:
        trend = "uptrend" if ema20[-1] > ema50[-1] else "downtrend"
    elif ema20[-1] is not None:
        trend = "uptrend" if latest_close > ema20[-1] else "downtrend"

    fundamentals_cache = db.get_cached_fundamentals([symbol])
    fund_row = fundamentals_cache.get(symbol)
    if fund_row is None:
        fresh = prices.fetch_fundamentals(symbol) or {f: None for f in _FUNDAMENTALS_FIELDS}
        db.upsert_fundamentals(symbol, fresh)
        fund_row = fresh
    fundamentals = {f: fund_row.get(f) for f in _FUNDAMENTALS_FIELDS}

    news_rows = db.symbol_news(symbol, days=14, limit=6)
    news = [
        {
            "title": r["title"],
            "sentiment": r["sentiment"],
            "importance": r["importance"],
            "published_at": r["published_at"].isoformat() if r["published_at"] else None,
        }
        for r in news_rows
    ]

    state = {
        "symbol": symbol,
        "latest_close": round(latest_close, 2),
        "period_high_90d": round(period_high, 2),
        "period_low_90d": round(period_low, 2),
        "pct_from_high": round((latest_close - period_high) / period_high * 100, 1),
        "pct_from_low": round((latest_close - period_low) / period_low * 100, 1),
        "trend_ema20_vs_ema50": trend,
        "rsi_14": rsi,
        "fundamentals": fundamentals,
        "recent_news": news,
    }

    verdict: dict[str, Any] = {"symbol": symbol, "computed": state, "jev": None, "jev_error": None}
    try:
        with httpx.Client(timeout=15.0) as client:
            choice_resp = client.post(
                f"{settings.jev_decision_url}/decide/choice",
                json={
                    "state": state,
                    "question": "Based on this real price trend, RSI, fundamentals, and recent news, what is the overall read on this stock right now?",
                    "criteria": {
                        "bullish": "Price trend, RSI, fundamentals, and news together lean positive — momentum or value case looks favorable.",
                        "neutral": "Mixed or inconclusive signals — no clear directional lean.",
                        "bearish": "Price trend, RSI, fundamentals, and news together lean negative — momentum or valuation case looks unfavorable.",
                    },
                },
            )
            choice_resp.raise_for_status()
            choice = choice_resp.json()

            score_resp = client.post(
                f"{settings.jev_decision_url}/decide/score",
                json={
                    "state": state,
                    "question": "How much near-term volatility/risk does this symbol carry right now, given RSI extremes, distance from period high/low, and news sentiment?",
                    "levels": ["low", "moderate", "elevated", "high"],
                },
            )
            score_resp.raise_for_status()
            score = score_resp.json()

        verdict["jev"] = {
            "read": choice["choice"],
            "read_confidence": choice["confidence"],
            "read_probabilities": choice["probabilities"],
            "risk_level": score["score"],
            "risk_legend": score.get("legend"),
        }
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.warning("jev verdict call failed for %s: %s", symbol, exc)
        verdict["jev_error"] = "Jev decision service unavailable right now — showing computed data only."

    return verdict


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return web.PAGE
