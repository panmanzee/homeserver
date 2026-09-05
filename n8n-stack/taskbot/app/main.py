"""FastAPI composition root: opens the pool, applies schema, starts poller + scheduler."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException

from . import db, intent, telegram
from .config import settings

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("taskbot")


async def _echo_handler(text: str, msg_id: int) -> str | None:
    # Task 4 stepping stone: reply with the parsed intent as JSON. Task 5 replaces
    # this with the real handler that acts on the intent.
    now = datetime.now(ZoneInfo(settings.taskbot_tz))
    parsed = await asyncio.to_thread(intent.parse, text, now=now, tz=settings.taskbot_tz)
    return json.dumps(parsed.model_dump())


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.pool.open()
    db.apply_schema()
    log.info("taskbot up (tz=%s, calendar=%s)", settings.taskbot_tz,
             "configured" if settings.google_refresh_token else "not configured")
    # Task 3 adds the poller and Task 7 the scheduler here, both guarded by
    # `if settings.taskbot_run_workers:` so tests (TASKBOT_RUN_WORKERS=false) skip them.
    poller = None
    if settings.taskbot_run_workers:
        poller = asyncio.create_task(telegram.poll_forever(_echo_handler))
    try:
        yield
    finally:
        if poller:
            poller.cancel()
            try:
                await poller
            except asyncio.CancelledError:
                pass
        db.pool.close()


app = FastAPI(title="taskbot", version="1.0", lifespan=lifespan)


def require_api_key(x_api_key: str = Header(default="")) -> None:
    if not secrets.compare_digest(x_api_key, settings.service_api_key):
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")


AuthDep = Depends(require_api_key)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    db.ping()
    return {"status": "ok"}
