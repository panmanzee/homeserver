import os

import pytest

DB_URL = os.environ.get("RAG_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="set RAG_TEST_DB_URL")


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    import importlib
    from app import config as cfg
    importlib.reload(cfg)
    from app import db as db_mod
    importlib.reload(db_mod)
    db_mod.apply_schema()
    with db_mod.pool.connection() as c:
        c.execute("TRUNCATE documents RESTART IDENTITY CASCADE")
    yield db_mod
    db_mod.pool.close()
    importlib.reload(cfg)
    importlib.reload(db_mod)


def _fake_embed(texts):
    return [[float(len(t) % 7)] + [0.1] * 767 for t in texts]


def test_ingests_then_skips_unchanged(db, tmp_path, monkeypatch):
    import importlib
    from app import ingest as ing
    importlib.reload(ing)
    f = tmp_path / "notes.md"
    f.write_text("OSPF areas and the link state database.\n\n" + "detail " * 200)

    r1 = ing.ingest_path(tmp_path, embed_fn=_fake_embed)
    assert r1.ingested == ["notes.md"] and r1.chunks_added >= 1

    r2 = ing.ingest_path(tmp_path, embed_fn=_fake_embed)
    assert r2.skipped == ["notes.md"] and r2.ingested == []


def test_changed_file_replaces_chunks(db, tmp_path):
    import importlib
    from app import ingest as ing
    importlib.reload(ing)
    f = tmp_path / "n.txt"
    f.write_text("first version " * 100)
    ing.ingest_path(tmp_path, embed_fn=_fake_embed)
    with db.pool.connection() as c:
        first = c.execute("SELECT count(*) n FROM chunks").fetchone()["n"]
    f.write_text("second much longer version " * 400)
    ing.ingest_path(tmp_path, embed_fn=_fake_embed)
    with db.pool.connection() as c:
        docs = c.execute("SELECT count(*) n FROM documents").fetchone()["n"]
        now = c.execute("SELECT count(*) n FROM chunks").fetchone()["n"]
    assert docs == 1 and now != first


def test_short_vector_list_fails_without_writing_a_row(db, tmp_path):
    import importlib
    from app import ingest as ing
    importlib.reload(ing)
    f = tmp_path / "big.txt"
    f.write_text("boundary paragraph.\n\n" + "detail " * 600)

    def short_embed(texts):
        return _fake_embed(texts)[:-1]  # one fewer vector than chunks

    r = ing.ingest_path(tmp_path, embed_fn=short_embed)
    assert r.ingested == [] and any(x[0] == "big.txt" for x in r.failed)
    with db.pool.connection() as c:
        assert c.execute("SELECT count(*) n FROM documents").fetchone()["n"] == 0
    # hash not recorded -> a later correct run still re-ingests
    r2 = ing.ingest_path(tmp_path, embed_fn=_fake_embed)
    assert r2.ingested == ["big.txt"]


def test_only_path_outside_corpus_is_rejected(db, tmp_path):
    import importlib
    from app import ingest as ing
    importlib.reload(ing)
    (tmp_path / "ok.txt").write_text("real content " * 50)
    r = ing.ingest_path(tmp_path, only=["ok.txt", "../escape.txt"], embed_fn=_fake_embed)
    assert "ok.txt" in r.ingested
    assert any(x[0] == "../escape.txt" and "outside corpus" in x[1] for x in r.failed)


def test_bad_file_reported_not_fatal(db, tmp_path):
    import importlib
    from app import ingest as ing
    importlib.reload(ing)
    (tmp_path / "good.txt").write_text("real content " * 50)
    (tmp_path / "bad.pdf").write_bytes(b"%PDF-broken")
    r = ing.ingest_path(tmp_path, embed_fn=_fake_embed)
    assert "good.txt" in r.ingested and any(f[0] == "bad.pdf" for f in r.failed)
