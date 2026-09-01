import json
from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from app import enrich
from app.enrich import NewsEnrichment


def test_normalize_symbol():
    assert enrich.normalize_symbol("aapl") == "AAPL"
    assert enrich.normalize_symbol("$NVDA") == "NVDA"
    assert enrich.normalize_symbol("BRK.B") == "BRK.B"
    assert enrich.normalize_symbol("way-too-long-symbol") is None
    assert enrich.normalize_symbol("123") is None


def _enrichment(**overrides):
    base = dict(
        summary=["Company X reported quarterly results."],
        tickers=["aapl", "AAPL", "$MSFT"],
        companies=["Apple Inc.", "Apple Inc.", "Microsoft"],
        topics=["Earnings", "earnings", "AI-Chips"],
        event_type="earnings",
        sentiment="neutral",
        sentiment_rationale="Results were in line with expectations.",
        importance="notable",
    )
    base.update(overrides)
    return NewsEnrichment.model_validate(base)


def test_clean_output_dedupes_and_normalizes():
    cleaned = enrich.clean_output(_enrichment())
    assert cleaned.tickers == ["AAPL", "MSFT"]
    assert cleaned.companies == ["Apple Inc.", "Microsoft"]
    assert cleaned.topics == ["earnings", "ai-chips"]


def test_clean_output_caps_topics_at_five():
    cleaned = enrich.clean_output(_enrichment(topics=[f"t{i}" for i in range(9)]))
    assert len(cleaned.topics) == 5


def test_ticker_rows_maps_price_symbol():
    rows = enrich.ticker_rows(enrich.clean_output(_enrichment()))
    assert rows[0]["symbol"] == "AAPL"
    assert rows[0]["price_symbol"] == "AAPL"
    assert rows[0]["name"] == "Apple Inc."


def test_unknown_enum_values_fall_back_to_safe_defaults():
    # a usable summary must never be dropped over a miscategorised tag
    e = _enrichment(event_type="rumour", sentiment="mixed", importance="urgent")
    assert e.event_type == "other"
    assert e.sentiment == "neutral"
    assert e.importance == "routine"


def test_missing_enum_fields_use_defaults():
    e = NewsEnrichment.model_validate(
        {"summary": ["สรุปข่าว"], "tickers": [], "companies": [], "topics": []}
    )
    assert (e.event_type, e.sentiment, e.importance) == ("other", "neutral", "routine")


def test_empty_summary_still_rejected():
    with pytest.raises(ValidationError):
        _enrichment(summary=[])


def test_single_choice_fields_coerce_list_to_first():
    e = _enrichment(event_type=["regulation", "legal"], importance=["breaking"])
    assert e.event_type == "regulation"
    assert e.importance == "breaking"


def test_single_choice_fields_coerce_stringified_list():
    e = _enrichment(
        event_type='["product"]', sentiment='["neutral"]', importance='["notable"]'
    )
    assert (e.event_type, e.sentiment, e.importance) == ("product", "neutral", "notable")


def test_build_user_content_includes_key_fields():
    item = {"title": "Big News", "feed_name": "CNBC", "url": "https://x/y", "published_at": None}
    content = enrich.build_user_content(item, "the article body")
    assert "TITLE: Big News" in content
    assert "SOURCE: CNBC" in content
    assert "the article body" in content


def test_system_prompt_has_guardrails():
    p = enrich.SYSTEM_PROMPT.lower()
    assert "buy / sell" in p or "buy/sell" in p
    assert "do not predict" in p
    assert "price target" in p


def test_system_prompt_asks_for_thai_summary():
    assert "ภาษาไทย" in enrich.SYSTEM_PROMPT
    assert "thai" in enrich.SYSTEM_PROMPT.lower()


_PAYLOAD = {
    "summary": ["สรุปข้อหนึ่ง", "สรุปข้อสอง"],
    "tickers": ["nvda"],
    "companies": ["NVIDIA"],
    "topics": ["ai-chips"],
    "event_type": "product",
    "sentiment": "positive",
    "sentiment_rationale": "บริษัทเปิดตัวผลิตภัณฑ์ใหม่",
    "importance": "notable",
}
_ITEM = {"title": "T", "feed_name": "F", "url": "https://x", "published_at": None}


# --- anthropic provider, fake client (no network) ------------------------- #
@dataclass
class _Block:
    type: str
    input: dict


@dataclass
class _AUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class _AResponse:
    content: list
    usage: _AUsage
    stop_reason: str = "tool_use"


class _FakeAnthropicMessages:
    def __init__(self, response):
        self._response = response
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return self._response


class _FakeAnthropicClient:
    def __init__(self, response):
        self.messages = _FakeAnthropicMessages(response)


def test_call_llm_anthropic_maps_tool_output():
    fake = _FakeAnthropicClient(_AResponse(content=[_Block("tool_use", dict(_PAYLOAD))], usage=_AUsage(1200, 210)))
    result = enrich.call_llm(_ITEM, "body text", client=fake, provider="anthropic")

    assert result.data.tickers == ["NVDA"]
    assert result.data.event_type == "product"
    assert result.data.importance == "notable"
    assert result.input_tokens == 1200
    assert result.output_tokens == 210
    assert result.model == enrich.settings.claude_model
    assert fake.messages.last_kwargs["tool_choice"] == {"type": "tool", "name": "record_enrichment"}


def test_call_llm_anthropic_raises_on_refusal():
    fake = _FakeAnthropicClient(_AResponse(content=[], usage=_AUsage(10, 0), stop_reason="refusal"))
    with pytest.raises(enrich.EnrichmentError):
        enrich.call_llm(_ITEM, "body", client=fake, provider="anthropic")


# --- gemini provider, fake client ---------------------------------------- #
@dataclass
class _GUsage:
    prompt_token_count: int
    candidates_token_count: int


class _GResponse:
    def __init__(self, text, usage):
        self.text = text
        self.usage_metadata = usage
        self.candidates = []


class _FakeGeminiModels:
    def __init__(self, response):
        self._response = response
        self.last_kwargs = None

    def generate_content(self, **kwargs):
        self.last_kwargs = kwargs
        return self._response


class _FakeGeminiClient:
    def __init__(self, response):
        self.models = _FakeGeminiModels(response)


def test_call_llm_gemini_maps_json_output():
    fake = _FakeGeminiClient(_GResponse(json.dumps(_PAYLOAD), _GUsage(900, 180)))
    result = enrich.call_llm(_ITEM, "body text", client=fake, provider="gemini")

    assert result.data.tickers == ["NVDA"]
    assert result.data.importance == "notable"
    assert result.input_tokens == 900
    assert result.output_tokens == 180
    assert result.model == enrich.settings.gemini_model


def test_call_llm_gemini_raises_on_empty_response():
    fake = _FakeGeminiClient(_GResponse("", _GUsage(10, 0)))
    with pytest.raises(enrich.EnrichmentError):
        enrich.call_llm(_ITEM, "body", client=fake, provider="gemini")


def test_call_llm_unknown_provider_raises():
    with pytest.raises(enrich.EnrichmentError):
        enrich.call_llm(_ITEM, "body", provider="whatever")
