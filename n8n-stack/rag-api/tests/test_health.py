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
    from app import db as db_mod
    importlib.reload(db_mod)
    from app import main as main_mod
    importlib.reload(main_mod)
    from fastapi.testclient import TestClient
    with TestClient(main_mod.app) as c:
        yield c
    db_mod.pool.close()
    importlib.reload(cfg)
    importlib.reload(db_mod)


def test_healthz_ok(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_schema_applied(client):
    from app import db as db_mod
    with db_mod.pool.connection() as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' ORDER BY 1"
        ).fetchall()
    names = {r["table_name"] for r in rows}
    assert {"documents", "chunks", "usage"} <= names
