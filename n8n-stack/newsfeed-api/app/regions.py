"""Region config — single source of truth for the 5-region investing hub.

Every region page, job, and home tile reads from REGIONS below. Adding a
region later requires only a new entry here + a constituents CSV in
`app/constituents/`. Yahoo symbols/suffixes were verified live against
Yahoo's chart API before being committed (see docs/region_verification.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class IndexRef:
    name: str
    yahoo: str
    primary: bool = False


@dataclass(frozen=True)
class Region:
    id: str
    name: str
    short_name: str
    currency: str
    timezone: str  # IANA tz of the primary exchange
    exchange_calendar: str  # exchange_calendars code, for market-hours logic
    indexes: tuple[IndexRef, ...]
    ticker_suffix: str  # appended to bare symbols for Yahoo, "" for US
    constituents_file: str  # app/constituents/<file>.csv
    fx_pair: str | None  # Yahoo FX symbol to convert to THB, None for th itself
    map_countries: tuple[str, ...] = field(default_factory=tuple)  # ISO3 codes for map tile


REGIONS: dict[str, Region] = {
    "us": Region(
        id="us",
        name="United States",
        short_name="US",
        currency="USD",
        timezone="America/New_York",
        exchange_calendar="XNYS",
        indexes=(
            IndexRef("S&P 500", "^GSPC", primary=True),
            IndexRef("Nasdaq-100", "^NDX"),
        ),
        ticker_suffix="",
        constituents_file="us.csv",
        fx_pair="USDTHB=X",
        map_countries=("USA",),
    ),
    "eu": Region(
        id="eu",
        name="Europe",
        short_name="Europe",
        currency="EUR",
        timezone="Europe/Berlin",
        exchange_calendar="XETR",
        indexes=(IndexRef("Euro Stoxx 50", "^STOXX50E", primary=True),),
        ticker_suffix="",  # mixed suffixes per constituent row (.DE/.PA/.AS/...)
        constituents_file="eu.csv",
        fx_pair="EURTHB=X",
        map_countries=("DEU", "FRA", "NLD", "ITA", "ESP", "BEL", "FIN", "IRL"),
    ),
    "jp": Region(
        id="jp",
        name="Japan",
        short_name="Japan",
        currency="JPY",
        timezone="Asia/Tokyo",
        exchange_calendar="XTKS",
        indexes=(IndexRef("Nikkei 225", "^N225", primary=True),),
        ticker_suffix=".T",
        constituents_file="jp.csv",
        fx_pair="JPYTHB=X",
        map_countries=("JPN",),
    ),
    "cn": Region(
        id="cn",
        name="China (HK-listed)",
        short_name="China",
        currency="HKD",
        timezone="Asia/Hong_Kong",
        exchange_calendar="XHKG",
        indexes=(IndexRef("Hang Seng Index", "^HSI", primary=True),),
        ticker_suffix=".HK",
        constituents_file="cn.csv",
        fx_pair="HKDTHB=X",
        map_countries=("CHN",),
    ),
    "th": Region(
        id="th",
        name="Thailand",
        short_name="Thailand",
        currency="THB",
        timezone="Asia/Bangkok",
        exchange_calendar="XBKK",
        indexes=(IndexRef("SET Index", "^SET.BK", primary=True),),
        ticker_suffix=".BK",
        constituents_file="th.csv",
        fx_pair=None,
        map_countries=("THA",),
    ),
}

REGION_ORDER = ["us", "eu", "jp", "cn", "th"]  # desktop tile order
MOBILE_REGION_ORDER = ["us", "th", "jp", "cn", "eu"]  # user is in Thailand


def get_region(region_id: str) -> Region:
    try:
        return REGIONS[region_id]
    except KeyError:
        raise ValueError(f"unknown region: {region_id!r}") from None
