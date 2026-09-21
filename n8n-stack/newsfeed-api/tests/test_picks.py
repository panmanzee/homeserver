from app import picks


def _price_row(symbol, latest, prev, name=None):
    return {"symbol": symbol, "name": name, "latest_close": latest, "prev_close": prev}


def _news_row(symbol, importance="routine", sentiment="neutral", tags=None, event_type=None):
    return {
        "symbol": symbol, "importance": importance, "sentiment": sentiment,
        "tags": tags or [], "event_type": event_type,
    }


def test_classify_sector_tech():
    assert picks.classify_sector({"ai-chips", "semiconductors"}) == "tech"


def test_classify_sector_healthcare():
    assert picks.classify_sector({"biotech", "clinical-trials"}) == "healthcare"


def test_classify_sector_other_when_no_keyword_matches():
    assert picks.classify_sector({"retail", "sports-betting"}) == "other"


def test_classify_sector_empty_tags_is_other():
    assert picks.classify_sector(set()) == "other"


def test_inclusion_gate_drops_negative_price_change():
    price_rows = [_price_row("AAPL", latest=90, prev=100)]  # -10%
    news = [_news_row("AAPL", importance="breaking", sentiment="positive")]
    sections = picks.build_picks(price_rows, news)
    all_symbols = {c["symbol"] for bucket in sections.values() for c in bucket}
    assert "AAPL" not in all_symbols


def test_inclusion_gate_drops_net_negative_news():
    price_rows = [_price_row("AAPL", latest=110, prev=100)]  # +10%
    news = [_news_row("AAPL", importance="breaking", sentiment="negative")]
    sections = picks.build_picks(price_rows, news)
    all_symbols = {c["symbol"] for bucket in sections.values() for c in bucket}
    assert "AAPL" not in all_symbols


def test_ticker_with_no_price_data_excluded_even_with_strong_news():
    price_rows: list[dict] = []
    news = [_news_row("NEWCO", importance="breaking", sentiment="positive")]
    sections = picks.build_picks(price_rows, news)
    all_symbols = {c["symbol"] for bucket in sections.values() for c in bucket}
    assert "NEWCO" not in all_symbols


def test_qualifying_ticker_appears_with_expected_fields():
    price_rows = [_price_row("NVDA", latest=110, prev=100, name="NVIDIA Corporation")]
    news = [
        _news_row("NVDA", importance="breaking", sentiment="positive", tags=["ai-chips"], event_type="product"),
        _news_row("NVDA", importance="routine", sentiment="positive", tags=["semiconductors"], event_type="partnership"),
    ]
    sections = picks.build_picks(price_rows, news)
    assert len(sections["tech"]) == 1
    item = sections["tech"][0]
    assert item["symbol"] == "NVDA"
    assert item["name"] == "NVIDIA Corporation"
    assert item["price_change_pct"] == 10.0
    assert item["news_score"] == 3 * 1 + 1 * 1  # breaking+positive, routine+positive
    assert item["article_count"] == 2
    assert item["sentiment_counts"] == {"positive": 2, "negative": 0, "neutral": 0}
    assert item["event_type_counts"] == {"product": 1, "partnership": 1}
    assert set(item["matched_tags"]) == {"ai-chips", "semiconductors"}
    assert item["score"] == item["price_change_pct"] + item["news_score"]
    assert item["fundamentals"] is None  # main.py fills this in per-symbol, not build_picks


def test_ranking_is_by_score_descending():
    price_rows = [
        _price_row("LOW", latest=101, prev=100),  # +1%
        _price_row("HIGH", latest=120, prev=100),  # +20%
    ]
    news = [
        _news_row("LOW", importance="routine", sentiment="positive", tags=["biotech"]),
        _news_row("HIGH", importance="routine", sentiment="positive", tags=["biotech"]),
    ]
    sections = picks.build_picks(price_rows, news)
    symbols = [c["symbol"] for c in sections["healthcare"]]
    assert symbols == ["HIGH", "LOW"]


def test_per_section_cap():
    price_rows = [_price_row(f"T{i}", latest=110, prev=100) for i in range(12)]
    news = [_news_row(f"T{i}", importance="breaking", sentiment="positive", tags=["ai-chips"]) for i in range(12)]
    sections = picks.build_picks(price_rows, news, per_section=8)
    assert len(sections["tech"]) == 8


def test_sections_always_present_even_when_empty():
    sections = picks.build_picks([], [])
    assert sections == {"tech": [], "healthcare": [], "other": []}
