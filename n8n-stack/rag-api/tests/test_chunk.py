from app.chunk import Chunk, chunk_pages
from app.extract import Page


def test_respects_size_and_is_contiguous():
    text = ("para one.\n\n" + "x" * 400 + "\n\n" + "y" * 400 + "\n\n" + "z" * 400)
    chunks = chunk_pages([Page(1, text)], chars=500, overlap=50)
    assert len(chunks) >= 2
    assert all(len(c.text) <= 500 for c in chunks)
    assert [c.ord for c in chunks] == list(range(len(chunks)))


def test_overlap_present():
    text = "\n".join(f"line {i} " + "w" * 40 for i in range(60))
    chunks = chunk_pages([Page(1, text)], chars=300, overlap=80)
    # the tail of chunk n reappears at the head of chunk n+1
    assert chunks[0].text[-40:] in chunks[1].text


def test_page_is_where_the_chunk_starts():
    p1 = Page(1, "a" * 300)
    p2 = Page(2, "b" * 300)
    chunks = chunk_pages([p1, p2], chars=250, overlap=0)
    assert chunks[0].page == 1
    assert chunks[-1].page == 2


def test_drops_whitespace_only_and_keeps_page_alignment():
    chunks = chunk_pages([Page(1, "   \n\n  "), Page(2, "real content here")],
                         chars=500, overlap=0)
    assert len(chunks) == 1 and chunks[0].page == 2 and chunks[0].text.strip()


def test_hard_split_only_when_a_single_run_exceeds_target():
    chunks = chunk_pages([Page(1, "q" * 1200)], chars=500, overlap=0)
    assert len(chunks) == 3 and all(len(c.text) <= 500 for c in chunks)
