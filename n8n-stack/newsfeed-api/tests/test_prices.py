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
