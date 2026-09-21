from datetime import date

import pytest

from app import prices
from app.prices import PriceProviderError

TD_OK = {
    "meta": {"symbol": "AAPL", "interval": "1day"},
    "values": [
        {"datetime": "2024-01-03", "open": "10.5", "high": "10.9", "low": "10.1", "close": "10.2", "volume": "900000"},
        {"datetime": "2024-01-02", "open": "10.0", "high": "11.0", "low": "9.5", "close": "10.5", "volume": "1000000"},
    ],
    "status": "ok",
}


def test_parse_twelvedata_ok():
    rows = prices.parse_twelvedata_json(TD_OK)
    assert len(rows) == 2
    assert rows[1] == {
        "date": date(2024, 1, 2),
        "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5,
        "volume": 1000000,
    }


def test_parse_twelvedata_error_raises():
    with pytest.raises(PriceProviderError):
        prices.parse_twelvedata_json({"code": 400, "message": "symbol not found", "status": "error"})


def test_parse_twelvedata_missing_values():
    payload = {"status": "ok", "values": [
        {"datetime": "2024-01-02", "open": "", "high": None, "low": "9.5", "close": "10.5", "volume": ""},
    ]}
    rows = prices.parse_twelvedata_json(payload)
    assert rows[0]["open"] is None
    assert rows[0]["high"] is None
    assert rows[0]["volume"] is None
    assert rows[0]["close"] == 10.5


YF_OK = {
    "chart": {
        "result": [
            {
                "timestamp": [1704153600, 1704240000],
                "indicators": {
                    "quote": [
                        {
                            "open": [10.0, 10.5],
                            "high": [11.0, 10.9],
                            "low": [9.5, 10.1],
                            "close": [10.5, None],
                            "volume": [1000000, 900000],
                        }
                    ]
                },
            }
        ],
        "error": None,
    }
}


def test_parse_yahoo_ok_skips_null_close():
    rows = prices.parse_yahoo_chart_json(YF_OK)
    assert len(rows) == 1
    assert rows[0]["close"] == 10.5
    assert rows[0]["volume"] == 1000000


def test_parse_yahoo_error_raises():
    with pytest.raises(PriceProviderError):
        prices.parse_yahoo_chart_json({"chart": {"error": {"code": "Not Found"}}})


def test_unknown_provider(monkeypatch):
    monkeypatch.setattr(prices.settings, "price_provider", "bogus")
    with pytest.raises(PriceProviderError):
        prices.fetch_prices("AAPL", 7)


def test_td_outputsize_bounds():
    assert prices._td_outputsize(7) == 24
    assert prices._td_outputsize(1) == 12
    assert prices._td_outputsize(10_000) == 5000


# --------------------------------------------------------------------------- #
# Fundamentals (P/E, valuation) — best-effort, never raises into the picks path
# --------------------------------------------------------------------------- #
YF_FUNDAMENTALS_OK = {
    "quoteSummary": {
        "result": [
            {
                "defaultKeyStatistics": {"forwardPE": {"raw": 25.3}, "priceToBook": {"raw": 12.1}},
                "summaryDetail": {"trailingPE": {"raw": 30.2}, "marketCap": {"raw": 123456789}},
                "financialData": {
                    "profitMargins": {"raw": 0.351},
                    "revenueGrowth": {"raw": 0.122},
                    "targetMeanPrice": {"raw": 250.0},
                    "recommendationKey": "buy",
                },
            }
        ],
        "error": None,
    }
}


def test_parse_yahoo_fundamentals_ok():
    data = prices.parse_yahoo_fundamentals_json(YF_FUNDAMENTALS_OK)
    assert data["trailing_pe"] == 30.2
    assert data["forward_pe"] == 25.3
    assert data["price_to_book"] == 12.1
    assert data["market_cap"] == 123456789
    assert data["profit_margin_pct"] == pytest.approx(35.1)
    assert data["revenue_growth_pct"] == pytest.approx(12.2)
    assert data["analyst_target_price"] == 250.0
    assert data["analyst_rating"] == "buy"


def test_parse_yahoo_fundamentals_error_returns_none():
    payload = {"quoteSummary": {"result": None, "error": {"code": "Not Found"}}}
    assert prices.parse_yahoo_fundamentals_json(payload) is None


def test_parse_yahoo_fundamentals_empty_result_returns_none():
    payload = {"quoteSummary": {"result": [], "error": None}}
    assert prices.parse_yahoo_fundamentals_json(payload) is None


def test_parse_yahoo_fundamentals_missing_fields_are_none():
    payload = {"quoteSummary": {"result": [{}], "error": None}}
    data = prices.parse_yahoo_fundamentals_json(payload)
    assert data == {
        "trailing_pe": None, "forward_pe": None, "price_to_book": None,
        "market_cap": None, "profit_margin_pct": None, "revenue_growth_pct": None,
        "analyst_target_price": None, "analyst_rating": None,
    }


def test_fetch_fundamentals_returns_none_on_non_200(monkeypatch):
    class FakeResp:
        status_code = 429
        text = "Too Many Requests"

    class FakeClient:
        def get(self, *a, **k):
            return FakeResp()

    monkeypatch.setattr(prices, "_yf_get_session", lambda: FakeClient())
    assert prices.fetch_fundamentals("NVDA") is None


def test_fetch_fundamentals_returns_none_on_network_error(monkeypatch):
    import httpx

    class FakeClient:
        def get(self, *a, **k):
            raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(prices, "_yf_get_session", lambda: FakeClient())
    assert prices.fetch_fundamentals("NVDA") is None


def test_fetch_fundamentals_returns_none_on_malformed_json(monkeypatch):
    class FakeResp:
        status_code = 200

        def json(self):
            raise ValueError("not json")

    class FakeClient:
        def get(self, *a, **k):
            return FakeResp()

    monkeypatch.setattr(prices, "_yf_get_session", lambda: FakeClient())
    assert prices.fetch_fundamentals("NVDA") is None


def test_fetch_fundamentals_ok(monkeypatch):
    class FakeResp:
        status_code = 200

        def json(self):
            return YF_FUNDAMENTALS_OK

    class FakeClient:
        def get(self, *a, **k):
            return FakeResp()

    monkeypatch.setattr(prices, "_yf_get_session", lambda: FakeClient())
    data = prices.fetch_fundamentals("NVDA")
    assert data["trailing_pe"] == 30.2
