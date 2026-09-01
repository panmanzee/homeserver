from datetime import timezone

from app import feeds

SAMPLE_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>Example</title>
  <item>
    <title>Chipmaker &amp; rival announce deal</title>
    <link>https://example.com/a</link>
    <guid>https://example.com/a</guid>
    <description>&lt;p&gt;Some &lt;b&gt;summary&lt;/b&gt; text.&lt;/p&gt;</description>
    <pubDate>Wed, 02 Jan 2024 12:00:00 GMT</pubDate>
    <author>jane@example.com</author>
  </item>
  <item>
    <title>No link item</title>
    <description>ignored</description>
  </item>
</channel></rss>
"""


def test_parse_feed_extracts_items_and_skips_linkless():
    rows = feeds.parse_feed(SAMPLE_RSS, feed_id=7)
    assert len(rows) == 1
    row = rows[0]
    assert row["feed_id"] == 7
    assert row["url"] == "https://example.com/a"
    assert row["guid"] == "https://example.com/a"
    assert row["title"] == "Chipmaker & rival announce deal"
    assert row["summary_rss"] == "Some summary text."
    assert row["published_at"].tzinfo == timezone.utc
    assert row["published_at"].year == 2024


def test_clean_html_strips_markup():
    assert feeds._clean_html("<p>hi <span>there</span></p>") == "hi there"
    assert feeds._clean_html("") is None
    assert feeds._clean_html(None) is None


def test_resolve_body_prefers_fulltext_when_substantial():
    long_text = "word " * 200  # ~1000 chars
    body, source = feeds.resolve_body("short rss", long_text)
    assert source == "fulltext"
    assert body.startswith("word")


def test_resolve_body_falls_back_to_rss_summary():
    body, source = feeds.resolve_body("the rss summary", None)
    assert source == "rss_summary"
    assert body == "the rss summary"

    body, source = feeds.resolve_body("the rss summary", "too short")
    assert source == "rss_summary"


def test_resolve_body_truncates_fulltext():
    from app.config import settings

    huge = "x" * (settings.fulltext_max_chars + 5000)
    body, source = feeds.resolve_body(None, huge)
    assert source == "fulltext"
    assert len(body) == settings.fulltext_max_chars
