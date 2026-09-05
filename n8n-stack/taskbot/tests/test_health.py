from unittest.mock import patch

from fastapi.testclient import TestClient

from app import main


def test_healthz_ok():
    with patch.object(main.db, "ping", return_value=True):
        client = TestClient(main.app)
        # lifespan runs apply_schema/pool.open; stub them out
        with patch.object(main.db.pool, "open"), patch.object(main.db, "apply_schema"), \
             patch.object(main.db.pool, "close"):
            with client:
                r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
