"""Pure-function tests for app/infographic.py and app/jevscore.py (no DB, no network)."""

from datetime import datetime

import pytest

from app import infographic as ig
from app import jevscore


def row(i, jev=None, gem=None, topic="world", probs=None, conf=0.9):
    return {
        "id": i, "title": f"t{i}", "feed_name": "X", "summary_rss": "",
        "jev_importance": jev, "gemini_importance": gem, "topic": topic,
        "probabilities": probs or {}, "confidence": conf, "tg_notified_at": None,
    }


def card(**kw):
    base = dict(ids=[1], category="world", breaking=False, headline_th="หัวข้อ", why_th="→ ผลกระทบ")
    return ig.Card(**{**base, **kw})


# ---- select logic ---------------------------------------------------------- #
def test_breaking_from_jev_or_gemini_sorted_by_prob():
    rows = [
        row(1, jev="breaking", probs={"breaking": 0.6}),
        row(2, jev="notable", gem="breaking", probs={"breaking": 0.4}),
        row(3, jev="breaking", probs={"breaking": 0.95}),
        row(4, jev="routine"),
        row(5, gem="breaking"),  # not Jev-scored yet: Gemini alone counts
    ]
    out = ig.pick_stories(rows)
    assert [r["id"] for r in out["stories"]] == [3, 1, 5, 2]
    assert out["quiet_day"] is False


def test_low_prob_breaking_is_not_big():
    rows = [
        row(1, jev="breaking", probs={"breaking": 0.45}),       # below 0.5
        row(2, jev="routine", gem="breaking", probs={"breaking": 0.1}),  # opinion piece
        row(3, jev="notable", probs={"notable": 0.8}),
    ]
    out = ig.pick_stories(rows)
    assert out["quiet_day"] is True
    assert [r["id"] for r in out["stories"]] == [3]


def test_thailand_has_lower_bar():
    rows = [
        row(1, jev="notable", topic="thailand", probs={"breaking": 0.4}),
        row(2, jev="notable", topic="world", probs={"breaking": 0.4}),
    ]
    out = ig.pick_stories(rows)
    assert out["quiet_day"] is False
    assert out["stories"][0]["id"] == 1


def test_quiet_day_fills_with_notable_and_skips_other_topic():
    rows = [
        row(1, jev="notable", probs={"notable": 0.5}),
        row(2, jev="notable", probs={"notable": 0.9}, topic="other"),
        row(3, jev="notable", probs={"notable": 0.7}),
        row(4, jev="notable", probs={"notable": 0.6}),
    ]
    out = ig.pick_stories(rows)
    assert out["quiet_day"] is True
    assert [r["id"] for r in out["stories"]] == [3, 4]


def test_one_breaking_adds_one_notable_not_quiet():
    rows = [row(1, jev="breaking", probs={"breaking": 0.9}),
            row(2, jev="notable", probs={"notable": 0.8})]
    out = ig.pick_stories(rows)
    assert [r["id"] for r in out["stories"]] == [1, 2]
    assert out["quiet_day"] is False


def test_candidates_capped():
    rows = [row(i, jev="breaking", probs={"breaking": 0.5 + i / 1000}) for i in range(40)]
    assert len(ig.pick_stories(rows)["stories"]) == ig.MAX_CANDIDATES


# ---- cards ----------------------------------------------------------------- #
def test_normalize_truncates_and_adds_arrow():
    c = ig.normalize_card(card(headline_th="ก" * 80, why_th="ข" * 100))
    assert len(c.headline_th) == ig.HEADLINE_MAX and c.headline_th.endswith("…")
    assert len(c.why_th) == ig.WHY_MAX and c.why_th.startswith("→ ") and c.why_th.endswith("…")


def test_card_schema_rejects_bad_category():
    with pytest.raises(Exception):
        card(category="sports")


def test_parse_cards_drops_unknown_and_duplicate_ids():
    text = ('```json\n{"cards":[{"ids":[1,99],"category":"markets","breaking":true,'
            '"headline_th":"a","why_th":"b"},{"ids":[1],"category":"world","breaking":false,'
            '"headline_th":"c","why_th":"d"}]}\n```')
    cards = ig._parse_cards(text, {1, 2})
    assert len(cards) == 1 and cards[0].ids == [1] and cards[0].why_th == "→ b"


def test_parse_cards_empty_raises():
    with pytest.raises(ValueError):
        ig._parse_cards('{"cards": []}', {1})


def test_schema_has_no_additional_properties():
    assert "additionalProperties" not in str(ig.CARDS_SCHEMA)


# ---- html ------------------------------------------------------------------ #
def test_render_html_escapes():
    out = ig.render_html([card(headline_th="<script>x</script>", why_th="→ a & b")], "วันนี้")
    assert "<script>" not in out and "&lt;script&gt;" in out and "a &amp; b" in out


def test_render_html_badge_and_quiet():
    out = ig.render_html([card(breaking=True)], "d", quiet_day=True)
    assert "ด่วน" in out and "วันนี้ไม่มีข่าวใหญ่" in out
    assert "ด่วน" not in ig.render_html([card()], "d")


def test_build_pages_chunks_six_per_image():
    pages = ig.build_pages([card(ids=[i]) for i in range(13)], "d", False)
    assert len(pages) == 3 and "(1/3)" in pages[0] and "อ่านทั้งหมด" in pages[-1]
    assert "อ่านทั้งหมด" not in pages[0]


def test_thai_date_buddhist_year():
    assert ig.thai_date(datetime(2026, 11, 16)) == "จันทร์ 16 พ.ย. 2569"


# ---- jevscore -------------------------------------------------------------- #
def test_clean_excerpt_strips_html_and_caps():
    assert jevscore.clean_excerpt("<p>Hi&nbsp;<b>there</b> &amp; you</p>") == "Hi there & you"
    assert len(jevscore.clean_excerpt("x" * 5000)) == jevscore.EXCERPT_CHARS


def test_score_item_never_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(jevscore, "_choose", boom)
    assert jevscore.score_item({"id": 1, "title": "t"}) is None


def test_score_item_combines_calls(monkeypatch):
    def fake(client, state, question, criteria):
        if "breaking" in criteria:
            return {"choice": "breaking", "confidence": 0.8, "probabilities": {"breaking": 0.8}}
        return {"choice": "world", "confidence": 0.6}
    monkeypatch.setattr(jevscore, "_choose", fake)
    r = jevscore.score_item({"id": 7, "title": "t"})
    assert r["importance"] == "breaking" and r["topic"] == "world" and r["news_item_id"] == 7
