"""End-of-day price client.

`fetch_prices(symbol, days)` is the stable interface; the actual source is
chosen by `PRICE_PROVIDER` (default `twelvedata`, needs `TWELVEDATA_API_KEY`).
A `yahoo` fallback is included but is unauthenticated and rate-limited — treat
it as best-effort only.

To add another provider, implement `_provider(symbol, days) -> list[dict]`
returning rows shaped like {"date": date, "open": float|None, "high": ...,
"low": ..., "close": float|None, "volume": int|None} and register it in
`_PROVIDERS`.
"""

from __future__ import annotations

import threading
import time
from datetime import date, datetime, timezone
from typing import Any, Callable

import httpx

from .config import settings

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


class PriceProviderError(RuntimeError):
    """A provider returned an error or unusable payload for one symbol."""


def _num(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Twelve Data (default)
# --------------------------------------------------------------------------- #
_TD_URL = "https://api.twelvedata.com/time_series"
_td_lock = threading.Lock()
_td_last_call = 0.0
_TD_MIN_INTERVAL = 60.0 / 7  # free tier allows 8 requests/minute; stay under


def _td_throttle() -> None:
    global _td_last_call
    with _td_lock:
        wait = _TD_MIN_INTERVAL - (time.monotonic() - _td_last_call)
        if wait > 0:
            time.sleep(wait)
        _td_last_call = time.monotonic()


def _td_outputsize(days: int) -> int:
    # a little headroom over `days` so weekends/holidays still leave enough bars
    return max(5, min(days * 2 + 10, 5000))


def parse_twelvedata_json(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse a Twelve Data time_series payload into price rows."""
    if payload.get("status") == "error":
        raise PriceProviderError(str(payload.get("message") or "twelvedata error"))
    rows: list[dict[str, Any]] = []
    for value in payload.get("values") or []:
        stamp = (value.get("datetime") or "")[:10]
        try:
            row_date = date.fromisoformat(stamp)
        except ValueError:
            continue
        rows.append(
            {
                "date": row_date,
                "open": _num(value.get("open")),
                "high": _num(value.get("high")),
                "low": _num(value.get("low")),
                "close": _num(value.get("close")),
                "volume": _int(value.get("volume")),
            }
        )
    return rows


def _twelvedata(symbol: str, days: int) -> list[dict[str, Any]]:
    if not settings.twelvedata_api_key:
        raise PriceProviderError("TWELVEDATA_API_KEY is not set")
    params = {
        "symbol": symbol,
        "interval": "1day",
        "outputsize": _td_outputsize(days),
        "apikey": settings.twelvedata_api_key,
        "timezone": "UTC",
    }
    for attempt in (1, 2):
        _td_throttle()
        with httpx.Client(timeout=settings.http_timeout) as client:
            resp = client.get(_TD_URL, params=params)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("status") == "error" and payload.get("code") == 429 and attempt == 1:
            time.sleep(61)
            continue
        return parse_twelvedata_json(payload)
    return parse_twelvedata_json(payload)


# --------------------------------------------------------------------------- #
# Yahoo Finance (default as of 2026-09-30 — unauthenticated, unofficial, but
# free with no hard daily cap; needed at 680-symbol 5-region scale where
# TwelveData's 800 credits/day would be exhausted almost immediately).
# Throttled defensively even though Yahoo publishes no official limit.
# --------------------------------------------------------------------------- #
_YF_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_yf_session: httpx.Client | None = None
_yf_lock = threading.Lock()
_yf_rate_lock = threading.Lock()
_yf_last_call = 0.0
_YF_MIN_INTERVAL = 0.35  # ~170/min ceiling, well under typical unofficial limits


def _yf_throttle() -> None:
    global _yf_last_call
    with _yf_rate_lock:
        wait = _YF_MIN_INTERVAL - (time.monotonic() - _yf_last_call)
        if wait > 0:
            time.sleep(wait)
        _yf_last_call = time.monotonic()


def _yf_get_session() -> httpx.Client:
    global _yf_session
    with _yf_lock:
        if _yf_session is None:
            client = httpx.Client(
                headers={"User-Agent": _BROWSER_UA},
                follow_redirects=True,
                timeout=settings.http_timeout,
            )
            try:
                client.get("https://fc.yahoo.com/")  # sets the consent cookie
            except httpx.HTTPError:
                pass
            _yf_session = client
        return _yf_session


def _yf_reset_session() -> None:
    global _yf_session
    with _yf_lock:
        if _yf_session is not None:
            _yf_session.close()
        _yf_session = None


def _yf_range(days: int) -> str:
    for limit, label in ((5, "5d"), (30, "1mo"), (90, "3mo"), (180, "6mo")):
        if days <= limit:
            return label
    return "1y"


def parse_yahoo_chart_json(payload: dict[str, Any]) -> list[dict[str, Any]]:
    chart = payload.get("chart") or {}
    if chart.get("error"):
        raise PriceProviderError(str(chart["error"]))
    results = chart.get("result") or []
    if not results:
        return []
    result = results[0]
    stamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    def at(seq: list[Any], i: int) -> Any:
        return seq[i] if i < len(seq) else None

    rows: list[dict[str, Any]] = []
    for i, stamp in enumerate(stamps):
        close = at(closes, i)
        if close is None:
            continue
        rows.append(
            {
                "date": datetime.fromtimestamp(stamp, tz=timezone.utc).date(),
                "open": _num(at(opens, i)),
                "high": _num(at(highs, i)),
                "low": _num(at(lows, i)),
                "close": _num(close),
                "volume": _int(at(volumes, i)),
            }
        )
    return rows


def _yahoo(symbol: str, days: int) -> list[dict[str, Any]]:
    params = {"range": _yf_range(days), "interval": "1d"}
    for attempt in (1, 2):
        _yf_throttle()
        client = _yf_get_session()
        resp = client.get(_YF_URL.format(symbol=symbol), params=params)
        if resp.status_code in (401, 403, 429) and attempt == 1:
            _yf_reset_session()
            time.sleep(2)
            continue
        resp.raise_for_status()
        return parse_yahoo_chart_json(resp.json())
    resp.raise_for_status()
    return parse_yahoo_chart_json(resp.json())


_PROVIDERS: dict[str, Callable[[str, int], list[dict[str, Any]]]] = {
    "twelvedata": _twelvedata,
    "yahoo": _yahoo,
}


def fetch_prices(symbol: str, days: int) -> list[dict[str, Any]]:
    try:
        provider = _PROVIDERS[settings.price_provider]
    except KeyError:
        raise PriceProviderError(f"unknown PRICE_PROVIDER: {settings.price_provider!r}")
    return provider(symbol, days)


# --------------------------------------------------------------------------- #
# Fundamentals (P/E, market cap, analyst consensus) — Today's Picks + Trading
# tab context.
#
# TwelveData's /statistics endpoint is the primary source (confirmed live and
# working on this account's plan — the earlier "paywalled" note was stale).
# Yahoo's unauthenticated quoteSummary is kept as a fallback for any symbol
# TwelveData doesn't have. `fetch_fundamentals` NEVER raises — it returns
# `None` on any failure from both sources. Callers must treat a `None` as
# "not available right now," not as an error to surface.
# --------------------------------------------------------------------------- #
_TD_STATISTICS_URL = "https://api.twelvedata.com/statistics"
_YF_FUNDAMENTALS_URL = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"


def _raw(section: dict[str, Any], key: str) -> Any:
    value = section.get(key)
    return value.get("raw") if isinstance(value, dict) else None


def _pct(value: float | None) -> float | None:
    return round(value * 100, 2) if value is not None else None


def parse_twelvedata_statistics_json(payload: dict[str, Any]) -> dict[str, Any] | None:
    if payload.get("status") == "error" or "statistics" not in payload:
        return None
    stats = payload["statistics"]
    val = stats.get("valuations_metrics") or {}
    fin = stats.get("financials") or {}
    return {
        "trailing_pe": val.get("trailing_pe"),
        "forward_pe": val.get("forward_pe"),
        "price_to_book": val.get("price_to_book_mrq"),
        "market_cap": val.get("market_capitalization"),
        "profit_margin_pct": _pct(fin.get("profit_margin")),
        "revenue_growth_pct": _pct(fin.get("income_statement", {}).get("quarterly_revenue_growth")),
        "analyst_target_price": None,
        "analyst_rating": None,  # TwelveData's /statistics has no recommendation string
    }


def _fetch_fundamentals_twelvedata(symbol: str) -> dict[str, Any] | None:
    if not settings.twelvedata_api_key:
        return None
    try:
        _td_throttle()
        with httpx.Client(timeout=settings.http_timeout) as client:
            resp = client.get(
                _TD_STATISTICS_URL,
                params={"symbol": symbol, "apikey": settings.twelvedata_api_key},
            )
        if resp.status_code != 200:
            return None
        return parse_twelvedata_statistics_json(resp.json())
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None


def parse_yahoo_fundamentals_json(payload: dict[str, Any]) -> dict[str, Any] | None:
    qs = payload.get("quoteSummary") or {}
    if qs.get("error"):
        return None
    results = qs.get("result") or []
    if not results:
        return None
    result = results[0]
    stats = result.get("defaultKeyStatistics") or {}
    summary = result.get("summaryDetail") or {}
    fin = result.get("financialData") or {}
    return {
        "trailing_pe": _raw(summary, "trailingPE"),
        "forward_pe": _raw(stats, "forwardPE"),
        "price_to_book": _raw(stats, "priceToBook"),
        "market_cap": _raw(summary, "marketCap"),
        "profit_margin_pct": _pct(_raw(fin, "profitMargins")),
        "revenue_growth_pct": _pct(_raw(fin, "revenueGrowth")),
        "analyst_target_price": _raw(fin, "targetMeanPrice"),
        "analyst_rating": fin.get("recommendationKey"),
    }


def _fetch_fundamentals_yahoo(symbol: str) -> dict[str, Any] | None:
    try:
        _yf_throttle()
        client = _yf_get_session()
        resp = client.get(
            _YF_FUNDAMENTALS_URL.format(symbol=symbol),
            params={"modules": "defaultKeyStatistics,summaryDetail,financialData"},
        )
        if resp.status_code != 200:
            return None
        return parse_yahoo_fundamentals_json(resp.json())
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None


def fetch_fundamentals(symbol: str) -> dict[str, Any] | None:
    """Best-effort P/E + valuation snapshot. Tries Yahoo first (primary as of
    2026-09-30 — no hard daily cap, needed for the 680-symbol 5-region
    universe), falls back to TwelveData (rate-capped at 800 credits/day, so
    only used as backup for symbols Yahoo doesn't have). Returns `None` on
    total failure — non-200, timeout, malformed payload — never raises."""
    result = _fetch_fundamentals_yahoo(symbol)
    if result is not None:
        return result
    return _fetch_fundamentals_twelvedata(symbol)
