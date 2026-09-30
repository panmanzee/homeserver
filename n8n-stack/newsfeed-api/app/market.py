"""Market hours / status + region-aware news tagging helpers.

Deliberately dependency-light: `exchange_calendars` is not installed in this
container (it pulls in pandas/numpy, a heavy addition for what's fundamentally
open/close time math over 5 known exchanges). Instead this uses stdlib
`zoneinfo` + a small manually-maintained holiday table per exchange.

Known limitation (documented per spec Rule 11 - flag instead of silently
skip): holiday tables below are hand-maintained and must be refreshed each
year; a wrong/missing holiday will show OPEN/CLOSED incorrectly for that one
day. This is deliberately simpler than a full exchange-calendar library
because the added weight (pandas/numpy) isn't justified for 5 markets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo

from .regions import REGIONS, Region

# --------------------------------------------------------------------------- #
# Per-exchange trading sessions (local time), including lunch breaks.
# Format: list of (start, end) tuples in local exchange time.
# --------------------------------------------------------------------------- #
_SESSIONS: dict[str, list[tuple[dt_time, dt_time]]] = {
    "XNYS": [(dt_time(9, 30), dt_time(16, 0))],
    "XETR": [(dt_time(9, 0), dt_time(17, 30))],
    "XTKS": [(dt_time(9, 0), dt_time(11, 30)), (dt_time(12, 30), dt_time(15, 30))],
    "XHKG": [(dt_time(9, 30), dt_time(12, 0)), (dt_time(13, 0), dt_time(16, 0))],
    "XBKK": [(dt_time(10, 0), dt_time(12, 30)), (dt_time(14, 30), dt_time(16, 30))],
}

# Hand-maintained market holidays (2026) per exchange calendar code.
# Refresh this table annually - see module docstring.
_HOLIDAYS_2026: dict[str, set[date]] = {
    "XNYS": {
        date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
        date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
        date(2026, 11, 26), date(2026, 12, 25),
    },
    "XETR": {
        date(2026, 1, 1), date(2026, 4, 3), date(2026, 4, 6), date(2026, 5, 1),
        date(2026, 12, 24), date(2026, 12, 25), date(2026, 12, 31),
    },
    "XTKS": {
        date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 12), date(2026, 2, 11),
        date(2026, 2, 23), date(2026, 3, 20), date(2026, 4, 29), date(2026, 5, 4),
        date(2026, 5, 5), date(2026, 5, 6), date(2026, 7, 20), date(2026, 8, 11),
        date(2026, 9, 21), date(2026, 9, 22), date(2026, 10, 12), date(2026, 11, 3),
        date(2026, 11, 23), date(2026, 12, 31),
    },
    "XHKG": {
        date(2026, 1, 1), date(2026, 2, 17), date(2026, 2, 18), date(2026, 2, 19),
        date(2026, 4, 3), date(2026, 4, 4), date(2026, 4, 6), date(2026, 5, 1),
        date(2026, 5, 25), date(2026, 7, 1), date(2026, 10, 1), date(2026, 12, 25),
    },
    "XBKK": {
        date(2026, 1, 1), date(2026, 3, 3), date(2026, 4, 6), date(2026, 4, 13),
        date(2026, 4, 14), date(2026, 4, 15), date(2026, 5, 1), date(2026, 5, 4),
        date(2026, 6, 3), date(2026, 7, 30), date(2026, 8, 12), date(2026, 10, 13),
        date(2026, 10, 23), date(2026, 12, 5), date(2026, 12, 10), date(2026, 12, 31),
    },
}


@dataclass
class MarketStatus:
    status: str  # OPEN | CLOSED | LUNCH_BREAK | HOLIDAY | WEEKEND
    local_time: str  # "09:31 New York"-style, no city name (caller adds it)
    local_time_iso: str
    next_change: str | None  # "opens in 3h 12m" / "closes in 45m", best-effort


def _holidays_for(calendar: str, year: int) -> set[date]:
    if year == 2026:
        return _HOLIDAYS_2026.get(calendar, set())
    return set()  # unknown year - be honest, don't guess


def get_market_status(region_id: str, *, now: datetime | None = None) -> MarketStatus:
    region: Region = REGIONS[region_id]
    tz = ZoneInfo(region.timezone)
    now_local = (now or datetime.now(ZoneInfo("UTC"))).astimezone(tz)
    today = now_local.date()
    sessions = _SESSIONS.get(region.exchange_calendar, [(dt_time(9, 0), dt_time(17, 0))])
    holidays = _holidays_for(region.exchange_calendar, today.year)

    is_weekend = now_local.weekday() >= 5
    is_holiday = today in holidays

    if is_weekend or is_holiday:
        status = "HOLIDAY" if is_holiday else "WEEKEND"
        return MarketStatus(
            status=status,
            local_time=now_local.strftime("%H:%M"),
            local_time_iso=now_local.isoformat(),
            next_change=None,
        )

    t = now_local.time()
    in_session = any(start <= t <= end for start, end in sessions)
    if in_session:
        # find the end of the current session
        current_end = next(end for start, end in sessions if start <= t <= end)
        end_dt = datetime.combine(today, current_end, tzinfo=tz)
        delta = end_dt - now_local
        next_change = f"closes in {_fmt_delta(delta)}"
        return MarketStatus(
            status="OPEN",
            local_time=now_local.strftime("%H:%M"),
            local_time_iso=now_local.isoformat(),
            next_change=next_change,
        )

    # between sessions (lunch) or before/after hours
    if len(sessions) > 1 and sessions[0][1] < t < sessions[1][0]:
        next_start = datetime.combine(today, sessions[1][0], tzinfo=tz)
        delta = next_start - now_local
        return MarketStatus(
            status="LUNCH_BREAK",
            local_time=now_local.strftime("%H:%M"),
            local_time_iso=now_local.isoformat(),
            next_change=f"resumes in {_fmt_delta(delta)}",
        )

    # closed - find next open (today if before first session, else next trading day)
    if t < sessions[0][0]:
        next_open = datetime.combine(today, sessions[0][0], tzinfo=tz)
    else:
        next_day = today + timedelta(days=1)
        skip = 0
        while (next_day.weekday() >= 5 or next_day in holidays) and skip < 10:
            next_day += timedelta(days=1)
            skip += 1
        next_open = datetime.combine(next_day, sessions[0][0], tzinfo=tz)
    delta = next_open - now_local
    return MarketStatus(
        status="CLOSED",
        local_time=now_local.strftime("%H:%M"),
        local_time_iso=now_local.isoformat(),
        next_change=f"opens in {_fmt_delta(delta)}",
    )


def _fmt_delta(delta: timedelta) -> str:
    total_minutes = max(0, int(delta.total_seconds() // 60))
    hours, minutes = divmod(total_minutes, 60)
    if hours == 0:
        return f"{minutes}m"
    return f"{hours}h {minutes}m"


# --------------------------------------------------------------------------- #
# Region tagging for news articles.
#
# An article is tagged with a region if:
#   1. any of its linked tickers belong to that region (authoritative), OR
#   2. its feed has a default region (existing feeds default to 'us'), OR
#   3. keyword fallback against the title (best-effort, only used when 1/2
#      find nothing) - e.g. "Nikkei", "Hang Seng", "SET Index", "Bangkok".
# An article can carry multiple region tags.
# --------------------------------------------------------------------------- #
_KEYWORD_REGIONS: dict[str, list[str]] = {
    "jp": ["nikkei", "tokyo stock", "bank of japan", "boj ", "japan's economy", "yen "],
    "cn": ["hang seng", "hong kong stock", "alibaba", "tencent", "china's economy",
           "beijing", "shanghai composite", "yuan "],
    "eu": ["euro stoxx", "european central bank", "ecb ", "eurozone", "dax ",
           "cac 40", "frankfurt", "brussels"],
    "th": ["set index", "bangkok", "bank of thailand", "baht ", "thailand's economy"],
    "us": ["wall street", "federal reserve", "fed ", "s&p 500", "nasdaq", "dow jones"],
}


def infer_regions(title: str, tickers: list[str], feed_category: str | None) -> list[str]:
    """Best-effort region tagging - ticker region is authoritative when present."""
    from .regions import REGIONS as _R  # local import to avoid cycle at module load

    regions: set[str] = set()

    # 1. Ticker-derived (authoritative) - infer from suffix since we don't
    #    have a live DB handle here; caller (db layer) can also pass ticker
    #    region directly when available - see news_regions upsert helper.
    for sym in tickers:
        if sym.endswith(".T"):
            regions.add("jp")
        elif sym.endswith(".HK"):
            regions.add("cn")
        elif sym.endswith(".BK"):
            regions.add("th")
        elif any(sym.endswith(suf) for suf in (".DE", ".PA", ".AS", ".MI", ".MC", ".BR", ".HE")):
            regions.add("eu")
        elif "." not in sym:
            regions.add("us")

    # 2. Keyword fallback on title, only adds regions not already found via tickers
    title_lower = title.lower()
    for region_id, keywords in _KEYWORD_REGIONS.items():
        if any(kw in title_lower for kw in keywords):
            regions.add(region_id)

    if not regions:
        regions.add("us")  # existing feeds are US/global finance+tech by default
    return sorted(regions)
