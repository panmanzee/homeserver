"""BTC-only strategy research (v2). Daily Binance BTC/USDT candles.
No look-ahead: signal uses data up to close of day t, position is held from close t to close t+1.
Fee+slippage charged on every change of position size.
Run inside the freqtrade container: python /freqtrade/user_data/scripts/btc_research.py
"""
import json
import numpy as np
import pandas as pd

FEE = 0.0015            # 0.10% Binance spot fee + 0.05% slippage, per side
START, END = "2018-04-01", "2026-10-21"
OUT = "/freqtrade/user_data/backtest_results/btc_v2.json"
rng = np.random.default_rng(42)

d = pd.read_feather("/freqtrade/user_data/data/binance/BTC_USDT-1d.feather").set_index("date")
c = d["close"]
ret = c.pct_change().fillna(0)


def run(w, start=START, end=END):
    """w = target BTC weight decided at close of day t (0..1). Returns stats in [start, end)."""
    w = w.clip(0, 1).fillna(0)
    held = w.shift(1).fillna(0)                      # weight held during day t
    turn = w.diff().abs().fillna(w.abs())            # trade at close of t
    r = held * ret - turn * FEE
    m = (r.index >= pd.Timestamp(start, tz="UTC")) & (r.index < pd.Timestamp(end, tz="UTC"))
    r = r[m]
    eq = (1 + r).cumprod()
    yrs = len(r) / 365.25
    dd = (1 - eq / eq.cummax()).max()
    sh = r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else 0
    trades = int((w[m].diff().abs() > 1e-9).sum())
    return {"ret": eq.iloc[-1] - 1, "cagr": eq.iloc[-1] ** (1 / yrs) - 1, "dd": dd, "sharpe": sh,
            "trades": trades, "exposure": float(held[m].mean())}


def sma_rule(n, buf=0.0):
    s = c.rolling(n).mean()
    w = pd.Series(np.nan, index=c.index)
    w[c > s * (1 + buf)] = 1
    w[c < s * (1 - buf)] = 0
    return w.ffill().fillna(0)


def weekly(w):
    """only allow changes on Sunday close (weekly decision, fewer whipsaws)."""
    m = w.index.dayofweek == 6
    return w.where(m).ffill().fillna(0)


def vol_target(target=0.6, lb=30, band=0.1):
    vol = ret.rolling(lb).std() * np.sqrt(365)
    raw = (target / vol).clip(0, 1)
    out, cur = [], 0.0
    for x in raw.fillna(0):
        if abs(x - cur) > band:
            cur = x
        out.append(cur)
    return pd.Series(out, index=raw.index)


def breakout(n_sma=100, n_hi=20, n_exit=50):
    """BTC-only daily version of TrendSimple entry/exit, full position (no ATR sizing)."""
    s, hi, ex = c.rolling(n_sma).mean(), c.rolling(n_hi).max().shift(1), c.rolling(n_exit).mean()
    w, cur = [], 0
    for i in range(len(c)):
        if cur == 0 and c.iloc[i] > s.iloc[i] and c.iloc[i] > hi.iloc[i]:
            cur = 1
        elif cur == 1 and c.iloc[i] < ex.iloc[i]:
            cur = 0
        w.append(cur)
    return pd.Series(w, index=c.index, dtype=float)


# ---- candidates (declared before looking at results) ----
hold = pd.Series(1.0, index=c.index)
S = {
    "S0 hold": hold,
    "S1a SMA200 daily": sma_rule(200),
    "S1b SMA200 +-2% band": sma_rule(200, 0.02),
    "S1c SMA140 (20-week) weekly": weekly(sma_rule(140)),
    "S1d SMA200 weekly": weekly(sma_rule(200)),
    "S2 breakout 100/20/50 BTC": breakout(),
    "S3 core50 + S1a": 0.5 + 0.5 * sma_rule(200),
    "S4 vol-target 60%": vol_target(),
    "S4b vol-target 60% x SMA200": vol_target() * sma_rule(200),
}

res = {k: run(v) for k, v in S.items()}

# DCA baseline: same cash spread weekly over the whole period (money-weighted, just for reference)
idx = c[(c.index >= pd.Timestamp(START, tz="UTC")) & (c.index < pd.Timestamp(END, tz="UTC"))]
buys = idx[idx.index.dayofweek == 0]
coins = (1 / buys * (1 - FEE)).sum()
res["S0 weekly DCA"] = {"ret": coins * idx.iloc[-1] / len(buys) - 1, "note": "money-weighted, not comparable DD"}

# ---- per-year ----
years = {}
for y in range(2018, 2027):
    s0 = f"{y}-01-01" if y > 2018 else START
    e0 = f"{y + 1}-01-01" if y < 2026 else END
    years[y] = {k: round(run(v, s0, e0)["ret"] * 100, 1) for k, v in S.items()}

# ---- walk-forward over SMA length (pick on all earlier years, test next year) ----
grid = {n: sma_rule(n) for n in (100, 120, 140, 160, 200, 250)}
wf = []
for y in range(2020, 2027):
    e0 = f"{y + 1}-01-01" if y < 2026 else END
    best = max(grid, key=lambda n: run(grid[n], START, f"{y}-01-01")["sharpe"])
    wf.append({"year": y, "pick": best, "test": round(run(grid[best], f"{y}-01-01", e0)["ret"] * 100, 1),
               "sma200": round(run(grid[200], f"{y}-01-01", e0)["ret"] * 100, 1),
               "hold": round(run(hold, f"{y}-01-01", e0)["ret"] * 100, 1)})


# ---- luck test: random in/out timing with same number of switches and same exposure ----
def luck(w, n=1000):
    """shuffle the order of the strategy's own holding blocks (same exposure, same blocks), compare Sharpe."""
    m = (w.index >= pd.Timestamp(START, tz="UTC")) & (w.index < pd.Timestamp(END, tz="UTC"))
    ww = w[m].values
    runs, cur, cnt = [], ww[0], 0
    for x in ww:
        if x == cur:
            cnt += 1
        else:
            runs.append((cur, cnt)); cur, cnt = x, 1
    runs.append((cur, cnt))
    real = run(w)["sharpe"]
    beat = 0
    for _ in range(n):
        order = rng.permutation(len(runs))
        seq = np.concatenate([np.full(runs[i][1], runs[i][0]) for i in order])
        rw = w.copy()
        rw.iloc[np.where(m)[0]] = seq
        if run(rw)["sharpe"] < real:
            beat += 1
    return beat / n


lk = {k: luck(S[k]) for k in ["S1a SMA200 daily", "S1b SMA200 +-2% band", "S1d SMA200 weekly",
                              "S2 breakout 100/20/50 BTC", "S4b vol-target 60% x SMA200"]}

hold_ret, hold_dd = res["S0 hold"]["ret"], res["S0 hold"]["dd"]
for k, r in res.items():
    if "dd" in r:
        r["gate"] = bool(r["ret"] >= 0.6 * hold_ret and r["dd"] <= 0.5 * hold_dd)

out = {"stats": res, "years": years, "walk_forward": wf, "luck_sharpe_pct": lk}
json.dump(out, open(OUT, "w"), indent=1, default=float)
for k, r in res.items():
    if "dd" in r:
        print(f"{k:32s} ret {r['ret']*100:8.0f}%  cagr {r['cagr']*100:5.1f}%  dd {r['dd']*100:5.1f}%  "
              f"sh {r['sharpe']:.2f}  tr {r['trades']:4d}  exp {r['exposure']:.2f}  gate {r['gate']}")
    else:
        print(f"{k:32s} ret {r['ret']*100:8.0f}%  ({r['note']})")
print("years", json.dumps(years, indent=0))
print("wf", wf)
print("luck", lk)
