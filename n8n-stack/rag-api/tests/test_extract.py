import pathlib

import pytest

from app.extract import ExtractError, Page, extract_file


def test_txt(tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("hello notes")
    pages = extract_file(p)
    assert pages == [Page(1, "hello notes")]


def test_md(tmp_path):
    p = tmp_path / "n.md"
    p.write_text("# Heading\n\nbody")
    assert extract_file(p)[0].text == "# Heading\n\nbody"


def test_pdf(tmp_path):
    fitz = pytest.importorskip("fitz")
    p = tmp_path / "d.pdf"
    doc = fitz.open()
    for t in ("page one text", "page two text"):
        page = doc.new_page()
        page.insert_text((72, 72), t)
    doc.save(p)
    doc.close()
    pages = extract_file(p)
    assert len(pages) == 2
    assert pages[0].number == 1 and "page one" in pages[0].text
    assert pages[1].number == 2 and "page two" in pages[1].text


def test_unknown_extension(tmp_path):
    p = tmp_path / "x.docx"
    p.write_bytes(b"nope")
    with pytest.raises(ExtractError):
        extract_file(p)
