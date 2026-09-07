"""Optional one-way mirror of tasks onto a dedicated Google Calendar.
Every public function is a no-op when Google isn't configured."""

from __future__ import annotations

import functools
import logging
from datetime import date, datetime, timedelta

from . import db
from .config import settings

log = logging.getLogger("taskbot.gcal")
_SCOPES = ["https://www.googleapis.com/auth/calendar"]
_service = None
_calendar_id = None


def _creds():
    from google.oauth2.credentials import Credentials
    row = db.get_google_oauth()
    refresh = (row or {}).get("refresh_token") or settings.google_refresh_token
    if not (refresh and settings.google_client_id and settings.google_client_secret):
        return None, None
    cal = (row or {}).get("calendar_id") or settings.google_calendar_id
    creds = Credentials(
        token=None, refresh_token=refresh,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id, client_secret=settings.google_client_secret,
        scopes=_SCOPES,
    )
    return creds, cal


def enabled() -> bool:
    # Cheap gate first: no refresh token => mirror is off, so don't hit the DB
    # (get_google_oauth) or import google-auth on every task message.
    if not settings.google_refresh_token:
        return False
    creds, cal = _creds()
    return bool(creds and cal)


def _svc():
    global _service, _calendar_id
    if _service is None:
        from googleapiclient.discovery import build
        creds, cal = _creds()
        _service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        _calendar_id = cal
    return _service, _calendar_id


def _body(row: dict) -> dict:
    if row.get("scheduled_start"):
        s: datetime = row["scheduled_start"]
        e: datetime = row["scheduled_end"] or (s + timedelta(hours=1))
        # scheduled_start is timestamptz and _parse_dt now attaches the user's
        # zone, so isoformat() carries the correct RFC3339 offset — no separate
        # "timeZone" key needed (and no naive-datetime wall-clock bug).
        return {"summary": row["title"],
                "start": {"dateTime": s.isoformat()},
                "end": {"dateTime": e.isoformat()}}
    d: date = row["due_date"] or date.today()
    return {"summary": row["title"],
            "start": {"date": d.isoformat()},
            "end": {"date": (d + timedelta(days=1)).isoformat()}}


def _guard(fn):
    @functools.wraps(fn)
    def inner(row: dict):
        try:
            if not enabled():
                return
            fn(row)
        except Exception:
            log.exception("gcal sync failed (task %s); continuing", row.get("id"))
    return inner


@_guard
def sync_new(row: dict) -> None:
    svc, cal = _svc()
    ev = svc.events().insert(calendarId=cal, body=_body(row)).execute()
    db.set_gcal_event_id(row["id"], ev["id"])


@_guard
def sync_completed(row: dict) -> None:
    if not row.get("gcal_event_id"):
        return
    svc, cal = _svc()
    svc.events().patch(calendarId=cal, eventId=row["gcal_event_id"],
                       body={"summary": f"✓ {row['title']}"}).execute()


@_guard
def sync_deleted(row: dict) -> None:
    if not row.get("gcal_event_id"):
        return
    svc, cal = _svc()
    svc.events().delete(calendarId=cal, eventId=row["gcal_event_id"]).execute()
    db.set_gcal_event_id(row["id"], None)


@_guard
def sync_rescheduled(row: dict) -> None:
    if not row.get("gcal_event_id"):
        sync_new(row)
        return
    svc, cal = _svc()
    # update (full replace), not patch: patch MERGES nested objects, so pushing a
    # {"date": …} start onto an event that still holds {"dateTime": …} leaves both
    # keys set and Google 400s. _body(row) is already a complete event body.
    svc.events().update(calendarId=cal, eventId=row["gcal_event_id"], body=_body(row)).execute()
