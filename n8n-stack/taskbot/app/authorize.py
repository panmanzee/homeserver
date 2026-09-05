"""Run once on a machine with a browser:  python -m app.authorize
Prints GOOGLE_REFRESH_TOKEN and GOOGLE_CALENDAR_ID to paste into the box .env."""

from __future__ import annotations

import os
import sys

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def main() -> None:
    cid = os.environ.get("GOOGLE_CLIENT_ID")
    csec = os.environ.get("GOOGLE_CLIENT_SECRET")
    if not (cid and csec):
        sys.exit("set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in the environment first")

    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    flow = InstalledAppFlow.from_client_config(
        {"installed": {"client_id": cid, "client_secret": csec,
                       "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                       "token_uri": "https://oauth2.googleapis.com/token",
                       "redirect_uris": ["http://localhost"]}},
        SCOPES,
    )
    creds = flow.run_local_server(port=0)

    svc = build("calendar", "v3", credentials=creds, cache_discovery=False)
    cal_id = None
    for c in svc.calendarList().list().execute().get("items", []):
        if c.get("summary") == "Tasks":
            cal_id = c["id"]
            break
    if not cal_id:
        cal_id = svc.calendars().insert(body={"summary": "Tasks"}).execute()["id"]

    print("\n--- paste into the box .env ---")
    print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
    print(f"GOOGLE_CALENDAR_ID={cal_id}")


if __name__ == "__main__":
    main()
