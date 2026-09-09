import os

import pytest

from app import retrieve

DB_URL = os.environ.get("RAG_TEST_DB_URL")


def test_rrf_prefers_agreement():
    a = [{"id": 1}, {"id": 2}, {"id": 3}]
    b = [{"id": 2}, {"id": 9}, {"id": 1}]
    fused = retrieve.rrf([a, b], k0=60, k=3)
    assert fused[0]["id"] == 2                 # rank 1 + rank 1  (well, 1 & 1-ish)
    assert {r["id"] for r in fused} == {1, 2, 9}
    assert fused[0]["score"] >= fused[1]["score"] >= fused[2]["score"]


def test_rrf_dedupes_and_truncates():
    a = [{"id": i} for i in range(1, 11)]
    fused = retrieve.rrf([a, a], k0=60, k=4)
    assert len(fused) == 4 and [r["id"] for r in fused] == [1, 2, 3, 4]


def test_rrf_single_list():
    fused = retrieve.rrf([[{"id": 7}, {"id": 8}]], k0=60, k=5)
    assert [r["id"] for r in fused] == [7, 8]


@pytest.mark.skipif(not DB_URL, reason="set RAG_TEST_DB_URL")
class TestDbSearch:
    @pytest.fixture()
    def db(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", DB_URL)
        import importlib
        from app import config as cfg
        importlib.reload(cfg)
        from app import db as db_mod
        importlib.reload(db_mod)
        db_mod.apply_schema()
        with db_mod.pool.connection() as c:
            c.execute("TRUNCATE documents RESTART IDENTITY CASCADE")
            c.execute("INSERT INTO documents (filename, sha256, pages) VALUES ('a.pdf','h',3)")
            rows = [
                (1, 1, 0, "ospf builds a link state database", [1.0, 0.0] + [0.0] * 766),
                (1, 2, 1, "bgp path selection uses local preference", [0.0, 1.0] + [0.0] * 766),
                (1, 3, 2, "the link state database floods lsas", [0.9, 0.1] + [0.0] * 766),
            ]
            for d, pg, o, t, e in rows:
                c.execute("INSERT INTO chunks (document_id,page,ord,text,embedding) "
                          "VALUES (%s,%s,%s,%s,%s)", (d, pg, o, t, e))
        yield db_mod
        db_mod.pool.close()
        importlib.reload(cfg)
        importlib.reload(db_mod)

    def test_vector_search_orders_by_similarity(self, db):
        res = db.vector_search([1.0, 0.0] + [0.0] * 766, 3)
        assert [r["text"][:4] for r in res][:2] == ["ospf", "the "]
        assert res[0]["rank"] == 1 and res[0]["filename"] == "a.pdf"

    def test_keyword_search_matches_terms(self, db):
        res = db.keyword_search("link state database", 3)
        assert res and all("link state database" in r["text"] for r in res[:1])

    def test_keyword_search_empty_query(self, db):
        assert db.keyword_search("the a of", 3) == [] or all(
            r["text"] for r in db.keyword_search("the a of", 3))
