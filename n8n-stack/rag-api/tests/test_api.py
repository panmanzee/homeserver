import os

import pytest

DB_URL = os.environ.get("RAG_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="set RAG_TEST_DB_URL")


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    import importlib
    from app import config as cfg
    importlib.reload(cfg)
    for m in ("db", "retrieve", "answer", "embed", "ingest", "web", "main"):
        importlib.reload(importlib.import_module(f"app.{m}"))
    from app import main as main_mod, answer as ans, embed as emb, retrieve as ret
    from app.retrieve import RetrievedChunk
    monkeypatch.setattr(emb, "embed_query", lambda q, **k: [0.1] * 768)
    monkeypatch.setattr(ret, "search", lambda v, q, **k: [
        RetrievedChunk(1, "a.pdf", 3, "OSPF uses areas.", 0.9)])
    monkeypatch.setattr(ans, "answer", lambda q, ch, **k: ans.Answer(
        "OSPF uses areas [a.pdf p.3].", [ans.Source("a.pdf", 3, "OSPF uses areas.")]))
    from fastapi.testclient import TestClient
    with TestClient(main_mod.app) as c:
        yield c
    from app import db as db_mod
    db_mod.pool.close()
    importlib.reload(cfg)
    importlib.reload(db_mod)


def test_ask_happy(client):
    r = client.post("/ask", json={"question": "how does ospf scale?"})
    assert r.status_code == 200
    body = r.json()
    assert "[a.pdf p.3]" in body["answer"]
    assert body["sources"][0] == {"filename": "a.pdf", "page": 3, "snippet": "OSPF uses areas."}


def test_ask_blank_422(client):
    assert client.post("/ask", json={"question": "  "}).status_code == 422


def test_ask_daily_cap(client, monkeypatch):
    from app import main as main_mod
    monkeypatch.setattr(main_mod.settings, "rag_max_questions_per_day", 0)
    body = client.post("/ask", json={"question": "anything"}).json()
    assert body["sources"] == [] and "limit" in body["answer"].lower()


def test_ingest_requires_key(client):
    assert client.post("/ingest", json={}).status_code == 401
    ok = client.post("/ingest", json={}, headers={"X-API-Key": "test-service-key"})
    assert ok.status_code == 200 and "ingested" in ok.json()


def test_stats(client):
    r = client.get("/stats")
    assert r.status_code == 200 and set(r.json()) == {
        "documents", "chunks", "last_ingested_at", "questions_today"}


def test_root_serves_html(client):
    r = client.get("/")
    assert r.status_code == 200 and "<html" in r.text.lower() and "rag" in r.text.lower()
