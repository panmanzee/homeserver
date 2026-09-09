"""FastAPI composition root."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import db

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("rag")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.apply_schema()
    db.pool.open()
    log.info("rag-api up")
    yield
    db.pool.close()


app = FastAPI(title="rag-api", lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    db.ping()
    return {"status": "ok"}
