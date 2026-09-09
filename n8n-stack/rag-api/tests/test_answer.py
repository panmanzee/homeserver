from types import SimpleNamespace

from app import answer
from app.retrieve import RetrievedChunk


class _FakeGen:
    def __init__(self, text="OSPF floods LSAs [a.pdf p.2].", boom=False):
        self.text, self.boom, self.prompt = text, boom, None

    class _Models:
        def __init__(self, o): self.o = o
        def generate_content(self, *, model, contents, config=None):
            self.o.prompt = contents
            if self.o.boom:
                raise RuntimeError("429 resource exhausted")
            return SimpleNamespace(text=self.o.text)

    @property
    def models(self): return _FakeGen._Models(self)


CHUNKS = [
    RetrievedChunk(1, "a.pdf", 2, "OSPF floods LSAs to all routers in an area.", 0.9),
    RetrievedChunk(2, "a.pdf", 2, "The LSDB is identical within an area.", 0.5),
    RetrievedChunk(3, "b.pdf", 7, "BGP is a path-vector protocol.", 0.4),
]


def test_no_chunks_no_call():
    a = answer.answer("what is ospf", [], client=_FakeGen())
    assert a.sources == [] and "couldn't find" in a.text.lower()


def test_prompt_has_passages_and_tags():
    fg = _FakeGen()
    answer.answer("how does ospf flood?", CHUNKS, client=fg)
    assert "a.pdf p.2" in fg.prompt and "b.pdf p.7" in fg.prompt
    assert "OSPF floods LSAs" in fg.prompt


def test_sources_deduped_by_file_page():
    a = answer.answer("q", CHUNKS, client=_FakeGen())
    assert [(s.filename, s.page) for s in a.sources] == [("a.pdf", 2), ("b.pdf", 7)]
    assert all(len(s.snippet) <= 200 for s in a.sources)


def test_model_error_is_graceful(monkeypatch):
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda *_: None)
    a = answer.answer("q", CHUNKS, client=_FakeGen(boom=True))
    assert a.text == answer.TROUBLE and a.sources == []


def test_missing_api_key_is_graceful(monkeypatch):
    monkeypatch.setattr(answer, "_client", None)
    monkeypatch.setattr(answer.settings, "gemini_api_key", "")
    a = answer.answer("q", CHUNKS)  # no injected client -> _get_client() runs
    assert a.text == answer.TROUBLE and a.sources == []


def test_not_covered_answer_drops_sources():
    a = answer.answer("q", CHUNKS, client=_FakeGen(text=answer.NOT_COVERED))
    assert a.sources == [] and "cover" in a.text.lower()
