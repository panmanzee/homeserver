"""Timezone resolution for all 'today'/'now' logic."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import settings

log = logging.getLogger("taskbot.clock")


def _zone() -> ZoneInfo:
    try:
        return ZoneInfo(settings.taskbot_tz)
    except (ZoneInfoNotFoundError, ValueError):
        log.warning("bad TASKBOT_TZ %r; using UTC", settings.taskbot_tz)
        return ZoneInfo("UTC")


def zone() -> ZoneInfo:
    """The user's configured IANA zone (falls back to UTC on a bad value)."""
    return _zone()


def tz_name() -> str:
    return str(_zone())


def is_utc() -> bool:
    return tz_name() == "UTC"


def now_local() -> datetime:
    return datetime.now(_zone())
