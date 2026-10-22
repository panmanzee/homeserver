"""
analyze.py - turn backtest runs into report tables (run inside the freqtrade container).
  python /freqtrade/user_data/scripts/analyze.py
Reads  user_data/backtest_results/wf/*.jsonl  and 1d candle data.
Writes user_data/backtest_results/wf/summary.json and prints markdown tables.

Metrics are computed the SAME way for the strategy and for buy-and-hold:
daily mark-to-market equity -> CAGR, Sharpe (daily, x sqrt(365)), max drawdown.
"""
import glob
import json
import math
import os

import numpy as np
import pandas as pd

D = "/freqtrade/user_data/backtest_results/wf"
DATA = "/freqtrade/user_data/data/binance"
START_BAL = 3000.0
rng = np.random.default_rng(42)


def load_px(pair):
    df = pd.read_feather(f"{DATA}/{pair.replace('/', '_')}-1d.feather")
    df["date"] = pd.to_datetime(df["date"], utc=True)
    return df.set_index("date")


PX = {p: load_px(p) for p in ("BTC/USDT", "ETH/USDT")}


def tr_dates(tr):
    a, b = tr.split("-")
    return pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC")


def curve_metrics(eq: pd.Series):
    eq = eq.dropna()
    days = (eq.index[-1] - eq.index[0]).days or 1
    total = eq.iloc[-1] / eq.iloc[0] - 1
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (365.0 / days) - 1
    r = eq.pct_change().dropna()
    sharpe = float(r.mean() / r.std() * math.sqrt(365)) if r.std() > 0 else 0.0
    dd = float((eq / eq.cummax() - 1).min())
    return {"total_return": float(total), "cagr": float(cagr), "sharpe": sharpe,
            "max_dd": -dd, "days": days}


def strat_equity(rec):
    s, e = tr_dates(rec["timerange"])
    idx = PX["BTC/USDT"].loc[s:e].index
    eq = pd.Series(START_BAL, index=idx, dtype=float)
    expo = pd.Series(0.0, index=idx)
    for t in rec["trades"]:
        od = pd.Timestamp(t["open_date"]).tz_convert("UTC") if pd.Timestamp(t["open_date"]).tzinfo else pd.Timestamp(t["open_date"], tz="UTC")
        cd = pd.Timestamp(t["close_date"]).tz_convert("UTC") if pd.Timestamp(t["close_date"]).tzinfo else pd.Timestamp(t["close_date"], tz="UTC")
        px = PX[t["pair"]]["close"]
        # daily close marks: candle with date d closes at d+1day
        during = idx[(idx + pd.Timedelta(days=1) > od) & (idx + pd.Timedelta(days=1) <= cd)]
        if len(during):
            val = t["amount"] * px.reindex(during)
            eq.loc[during] += (val - t["stake_amount"]).values
            expo.loc[during] += val.values
        after = idx[idx + pd.Timedelta(days=1) > cd]
        eq.loc[after] += t["profit_abs"]
    # equity at close of each day; prepend start
    exposure = float((expo / eq).mean())
    time_in = float((expo > 0).mean())
    return eq, exposure, time_in


def bh_equity(timerange, fee, pairs=("BTC/USDT",)):
    s, e = tr_dates(timerange)
    parts = []
    for p in pairs:
        px = PX[p].loc[s:e]
        units = (START_BAL / len(pairs)) * (1 - fee) / px["open"].iloc[0]
        parts.append(units * px["close"])
    eq = sum(parts)
    eq.iloc[-1] *= (1 - fee)
    return eq


def summarize(rec):
    eq, expo, tin = strat_equity(rec)
    m = curve_metrics(eq)
    m.update({"trades": rec["total_trades"], "winrate": rec["winrate"], "exposure": expo,
              "time_in_market": tin, "ft_profit_total": rec["profit_total"],
              "ft_max_dd_closed": rec["max_drawdown_account"]})
    return m


def random_entry(rec, fee, n_sims=1000):
    """Random entries: same number of trades, same holding times, same stake fraction,
    same fee. Pair and entry day random. Score = sum(stake_frac * net trade return)."""
    s, e = tr_dates(rec["timerange"])
    eq, _, _ = strat_equity(rec)
    fr, hold, score_strat = [], [], 0.0
    for t in rec["trades"]:
        od = pd.Timestamp(t["open_date"])
        od = od if od.tzinfo else od.tz_localize("UTC")
        equity_then = float(eq.asof(od - pd.Timedelta(days=1))) if od - pd.Timedelta(days=1) >= eq.index[0] else START_BAL
        f = t["stake_amount"] / equity_then
        fr.append(f)
        hold.append(max(1, int(round(t["trade_duration"] / 1440))))
        score_strat += f * t["profit_ratio"]
    fr, hold = np.array(fr), np.array(hold)
    opens = {p: PX[p].loc[s:e, "open"].values for p in PX}
    n = len(opens["BTC/USDT"])
    pairs = list(PX)
    scores = np.empty(n_sims)
    for k in range(n_sims):
        tot = 0.0
        for f, h in zip(fr, hold):
            p = pairs[rng.integers(2)]
            i = rng.integers(0, n - h - 1)
            o = opens[p]
            r = (o[i + h] * (1 - fee)) / (o[i] * (1 + fee)) - 1
            tot += f * r
        scores[k] = tot
    pct = float((scores < score_strat).mean() * 100)
    return {"strategy_score": score_strat, "random_median": float(np.median(scores)),
            "random_p95": float(np.percentile(scores, 95)), "percentile": pct,
            "n_sims": n_sims, "n_trades": len(fr), "mean_hold_days": float(hold.mean())}


def main():
    runs = {}
    for fn in glob.glob(f"{D}/*.jsonl"):
        if fn.endswith("test.jsonl"):
            continue
        for line in open(fn):
            r = json.loads(line)
            runs[(r["label"], r["timerange"], r["fee"])] = r
    out = {"full": {}, "years": {}, "walkforward": {}, "random": {}}
    FULL = "20180401-20261021"
    # --- full period
    for fee in (0.001, 0.0025, 0.003):
        rec = runs.get(("default", FULL, fee))
        if not rec:
            continue
        m = summarize(rec)
        m["bh_btc"] = curve_metrics(bh_equity(FULL, fee))
        m["bh_5050"] = curve_metrics(bh_equity(FULL, fee, ("BTC/USDT", "ETH/USDT")))
        out["full"][str(fee)] = m
        out["random"][str(fee)] = random_entry(rec, fee)
    # --- per year (default params, all fees) + buy and hold
    years = sorted({k[1] for k in runs if k[0] == "default" and k[1] != FULL})
    for fee in (0.001, 0.0025, 0.003):
        rows = []
        for y in years:
            rec = runs.get(("default", y, fee))
            if not rec:
                continue
            m = summarize(rec)
            bh = curve_metrics(bh_equity(y, fee))
            rows.append({"window": y, **{k: m[k] for k in ("total_return", "max_dd", "trades", "sharpe", "exposure")},
                         "bh_return": bh["total_return"], "bh_max_dd": bh["max_dd"]})
        out["years"][str(fee)] = rows
    # --- walk-forward with parameter choice on TRAIN windows only (fee 0.25%)
    fee = 0.0025
    labels = sorted({k[0] for k in runs if k[2] == fee and k[1] != FULL})
    yr = {lab: {y: runs[(lab, y, fee)]["profit_total"] for y in years if (lab, y, fee) in runs}
          for lab in labels}
    wf = []
    for i, y in enumerate(years):
        if i < 2:
            continue  # need >= 2 train years
        train = years[:i]
        def score(lab):
            v = [math.log1p(yr[lab][t]) for t in train if t in yr[lab]]
            return sum(v) if len(v) == len(train) else -1e9
        best = max(labels, key=score)
        rec = runs[(best, y, fee)]
        m = summarize(rec)
        bh = curve_metrics(bh_equity(y, fee))
        wf.append({"test_window": y, "chosen_params": best, "train_windows": len(train),
                   "test_return": m["total_return"], "test_max_dd": m["max_dd"],
                   "trades": m["trades"], "bh_return": bh["total_return"],
                   "default_return": yr.get("default", {}).get(y)})
    out["walkforward"]["0.0025"] = wf
    out["grid_yearly_0.0025"] = yr
    json.dump(out, open(f"{D}/summary.json", "w"), indent=1, default=str)
    print(json.dumps(out, indent=1, default=str)[:20000])


if __name__ == "__main__":
    main()
