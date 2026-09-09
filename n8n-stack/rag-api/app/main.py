"""FastAPI composition root: /healthz, /, /ask, /ingest, /stats."""

from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, field_validator

from . import answer as answer_mod
from . import db, embed, ingest, retrieve, web
from .config import settings

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("rag")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.apply_schema()
    db.pool.open()
    log.info("rag-api up")
    yield
    db.pool.close()


app = FastAPI(title="rag-api", lifespan=lifespan)


class AskIn(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def _nonblank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("question is blank")
        return v.strip()


class IngestIn(BaseModel):
    files: list[str] | None = None


@app.get("/healthz")
def healthz() -> dict[str, str]:
    db.ping()
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return web.PAGE


@app.get("/stats")
def stats() -> dict:
    return db.stats()


@app.post("/ask")
def ask(body: AskIn) -> dict:
    if db.questions_today() >= settings.rag_max_questions_per_day:
        return {"answer": "Daily question limit reached — try again tomorrow.", "sources": []}
    try:
        qvec = embed.embed_query(body.question)
    except embed.EmbedError as exc:
        log.error("embed_query failed: %s", exc)
        return {"answer": answer_mod.TROUBLE, "sources": []}
    chunks = retrieve.search(qvec, body.question)
    ans = answer_mod.answer(body.question, chunks)
    if ans.text != answer_mod.TROUBLE and chunks:
        db.bump_usage()
    return {"answer": ans.text,
            "sources": [{"filename": s.filename, "page": s.page, "snippet": s.snippet}
                        for s in ans.sources]}


@app.post("/ingest")
def do_ingest(body: IngestIn, x_api_key: str | None = Header(default=None)) -> dict:
    if not secrets.compare_digest(x_api_key or "", settings.service_api_key):
        raise HTTPException(status_code=401, detail="bad or missing X-API-Key")
    report = ingest.ingest_path(settings.rag_corpus_dir, only=body.files)
    return {"ingested": report.ingested, "skipped": report.skipped,
            "failed": [list(f) for f in report.failed], "chunks_added": report.chunks_added}
