from types import SimpleNamespace

import pytest

from app import embed


class _FakeClient:
    def __init__(self, dims=768, fail_times=0):
        self.dims, self.fail_times, self.calls = dims, fail_times, []

    class _Models:
        def __init__(self, outer): self.outer = outer
        def embed_content(self, *, model, contents, config=None):
            o = self.outer
            o.calls.append(list(contents))
            if len(o.calls) <= o.fail_times:
                raise RuntimeError("503 backend error")
            embs = [SimpleNamespace(values=[float(len(c))] * o.dims) for c in contents]
            return SimpleNamespace(embeddings=embs)

    @property
    def models(self): return _FakeClient._Models(self)


def test_batches(monkeypatch):
    monkeypatch.setattr(embed.settings, "rag_embed_batch", 2)
    fc = _FakeClient()
    out = embed.embed_documents(["a", "bb", "ccc", "dddd", "e"], client=fc)
    assert len(out) == 5 and len(out[0]) == 768
    assert [len(b) for b in fc.calls] == [2, 2, 1]   # 5 items, batch 2


def test_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda *_: None)
    fc = _FakeClient(fail_times=2)
    out = embed.embed_documents(["x"], client=fc)
    assert len(out) == 1 and len(fc.calls) == 3


def test_gives_up(monkeypatch):
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda *_: None)
    with pytest.raises(embed.EmbedError):
        embed.embed_documents(["x"], client=_FakeClient(fail_times=99))


def test_query_one_call():
    fc = _FakeClient()
    v = embed.embed_query("what is ospf", client=fc)
    assert len(v) == 768 and len(fc.calls) == 1
