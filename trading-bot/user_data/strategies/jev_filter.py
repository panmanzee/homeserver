"""
jev_filter.py - ask Jev (jev-decision-server) "what is the market regime?" for one candle.

Rules:
  * at most ONE call per (pair, closed candle date); answers cached in a JSON file
  * prompt = numbers only (no asset names, no dates) to reduce memorised-history leakage
  * timeout; any error / low confidence / not TREND  => entry NOT allowed (fail safe)
  * a hard call budget per process (JEV_MAX_CALLS) protects the token bill
"""
import json
import logging
import os
import threading
import time
import urllib.request

logger = logging.getLogger(__name__)

JEV_URL = os.environ.get("JEV_URL", "http://jev-decision-server:8000")
CACHE_PATH = os.environ.get("JEV_CACHE", "/freqtrade/user_data/jev_cache.json")
TIMEOUT_S = float(os.environ.get("JEV_TIMEOUT", "20"))
MIN_CONF = float(os.environ.get("JEV_MIN_CONF", "0.7"))
MAX_CALLS = int(os.environ.get("JEV_MAX_CALLS", "3000"))

QUESTION = (
    "These are numeric features of one market on a daily chart, measured at the close of the "
    "last candle. Classify the current market regime."
)
CRITERIA = {
    "TREND": "a steady, orderly uptrend or downtrend that is likely to persist; "
             "price clearly away from long averages, averages sloping, ADX high, volatility moderate",
    "RANGE": "sideways, choppy movement without clear direction; price near averages, ADX low",
    "CHAOS": "disorderly, very high volatility, sharp spikes or crashes, unstable direction",
}

_lock = threading.Lock()
_cache = None
_calls = 0
_stats = {"calls": 0, "errors": 0, "input_tokens": 0, "output_tokens": 0, "cache_hits": 0}


def _load():
    global _cache
    if _cache is None:
        try:
            with open(CACHE_PATH) as f:
                _cache = json.load(f)
        except Exception:
            _cache = {}
    return _cache


def _save():
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(_cache, f, indent=0, sort_keys=True)
    os.replace(tmp, CACHE_PATH)


def stats():
    return dict(_stats)


def features(row) -> dict:
    """Small numeric feature dict from one analysed dataframe row (rounded => fewer tokens)."""
    def r(x, n=1):
        try:
            x = float(x)
            return round(x, n) if x == x else None
        except Exception:
            return None
    c = row["close"]
    return {
        "ret_5d_pct": r(row["ret5"] * 100),
        "ret_20d_pct": r(row["ret20"] * 100),
        "ret_60d_pct": r(row["ret60"] * 100),
        "dist_sma50_pct": r((c / row["sma50"] - 1) * 100),
        "dist_sma200_pct": r((c / row["sma200"] - 1) * 100),
        "sma50_slope_20d_pct": r(row["sma50_slope"] * 100),
        "atr14_pct_of_price": r(row["atr"] / c * 100, 2),
        "vol20_annual_pct": r(row["vol20"] * 100),
        "adx14": r(row["adx"]),
        "up_days_last20": int(row["up20"]) if row["up20"] == row["up20"] else None,
    }


def regime(pair: str, candle_date: str, feats: dict) -> dict:
    """Return cached/new answer dict: {choice, confidence, allow, error?}."""
    global _calls
    key = f"{pair}|{candle_date}"
    with _lock:
        cache = _load()
        if key in cache:
            _stats["cache_hits"] += 1
            return cache[key]
        if _calls >= MAX_CALLS:
            return {"choice": None, "confidence": 0.0, "allow": False, "error": "budget"}
        _calls += 1
    body = json.dumps({"state": feats, "question": QUESTION, "criteria": CRITERIA}).encode()
    req = urllib.request.Request(JEV_URL + "/decide/gated", data=body,
                                 headers={"Content-Type": "application/json"})
    ans = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                ans = json.loads(resp.read())
            break
        except Exception as e:  # noqa
            err = str(e)[:200]
            time.sleep(1)
    with _lock:
        _stats["calls"] += 1
        if ans is None:
            _stats["errors"] += 1
            logger.warning("Jev call failed for %s: %s -> no entry (fail safe)", key, err)
            # do not cache failures: a later loop may retry (still max once per success)
            return {"choice": None, "confidence": 0.0, "allow": False, "error": err}
        usage = ans.get("usage") or {}
        _stats["input_tokens"] += int(usage.get("input_tokens") or 0)
        _stats["output_tokens"] += int(usage.get("output_tokens") or 0)
        conf = float(ans.get("confidence") or 0.0)
        out = {
            "choice": ans.get("choice"),
            "confidence": round(conf, 4),
            "probabilities": ans.get("probabilities"),
            "allow": ans.get("choice") == "TREND" and conf >= MIN_CONF,
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "features": feats,
        }
        _cache[key] = out
        _save()
        return out
