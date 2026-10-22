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
    # start every curve at START_BAL the day before the window (review fix: B&H entry fee + day-1 move count)
    eq = pd.concat([pd.Series([START_BAL], index=[eq.index[0] - pd.Timedelta(days=1)]), eq])
    days = (eq.index[-1] - eq.index[0]).days or 1
    total = eq.iloc[-1] / eq.iloc[0] - 1
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (365.0 / days) - 1
    r = eq.pct_change().dropna()
    sharpe = float(r.mean() / r.std() * math.sqrt(365)) if r.std() > 0 else 0.0
    dd = float((eq / eq.cummax() - 1).min())
    return {"total_return": float(total), "cagr": float(cagr), "sharpe": sharpe,
            "max_dd": -dd, "days": days}


def window_idx(s, e):
    """daily candle dates inside the window; end is EXCLUSIVE like freqtrade timerange"""
    idx = PX["BTC/USDT"].loc[s:e].index
    return idx[idx < e]


def strat_equity(rec):
    s, e = tr_dates(rec["timerange"])
    fee = float(rec.get("fee", 0.0))
    idx = window_idx(s, e)
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
            # open trade value after paying entry fee and the exit fee it would pay now
            eq.loc[during] += (val * (1 - fee) - t["stake_amount"] * (1 + fee)).values
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
        px = px[px.index < e]
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


def random_entry(rec, fee, n_sims=1000, tf="1d"):
    """Random entries: same number of trades, same holding times, same stake fraction,
    same fee. Pair and entry bar random (bars of the strategy timeframe).
    Score = sum(stake_frac * net trade return)."""
    bar_min = {"1d": 1440, "4h": 240}[tf]
    s, e = tr_dates(rec["timerange"])
    eq, _, _ = strat_equity(rec)
    fr, hold, score_strat = [], [], 0.0
    for t in rec["trades"]:
        od = pd.Timestamp(t["open_date"])
        od = od if od.tzinfo else od.tz_localize("UTC")
        equity_then = float(eq.asof(od - pd.Timedelta(days=1))) if od - pd.Timedelta(days=1) >= eq.index[0] else START_BAL
        f = t["stake_amount"] / equity_then
        fr.append(f)
        hold.append(max(1, int(round(t["trade_duration"] / bar_min))))
        score_strat += f * t["profit_ratio"]
    fr, hold = np.array(fr), np.array(hold)
    if tf == "1d":
        opens = {p: PX[p].loc[s:e - pd.Timedelta(days=1), "open"].values for p in PX}
    else:
        opens = {}
        for p in PX:
            d = pd.read_feather(f"{DATA}/{p.replace('/', '_')}-{tf}.feather")
            d["date"] = pd.to_datetime(d["date"], utc=True)
            d = d.set_index("date")
            opens[p] = d.loc[(d.index >= s) & (d.index < e), "open"].values
    n = min(len(v) for v in opens.values())
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


def mc_drawdown(rec, n_sims=2000):
    """Shuffle the order of closed-trade P&L (abs USDT). Max drawdown of the closed-trade
    equity curve for each order. Report actual, median and 95th percentile."""
    pnl = np.array([t["profit_abs"] for t in rec["trades"]], dtype=float)
    if len(pnl) == 0:
        return {}

    def mdd(p):
        eq = START_BAL + np.concatenate([[0.0], np.cumsum(p)])
        return float(-(eq / np.maximum.accumulate(eq) - 1).min())
    sims = np.array([mdd(rng.permutation(pnl)) for _ in range(n_sims)])
    return {"actual": mdd(pnl), "median": float(np.median(sims)),
            "p95": float(np.percentile(sims, 95)), "worst": float(sims.max()), "n_trades": len(pnl)}


def gap_stress(rec, tf="1d"):
    """Stop fills: freqtrade fills a stop at the stop price if the candle HIGH is above it, even when
    the candle OPENED below the stop (gap down). A real market stop would fill near the open.
    Re-price those exits at the candle open (idea from backtrader gap handling)."""
    fee = float(rec.get("fee", 0.0))
    px = {}
    for p in PX:
        if tf == "1d":
            px[p] = PX[p]
        else:
            d = pd.read_feather(f"{DATA}/{p.replace('/', '_')}-{tf}.feather")
            d["date"] = pd.to_datetime(d["date"], utc=True)
            px[p] = d.set_index("date")
    n_stop, n_gap, delta = 0, 0, 0.0
    for t in rec["trades"]:
        if "stop" not in str(t.get("exit_reason", "")):
            continue
        n_stop += 1
        cd = pd.Timestamp(t["close_date"])
        cd = cd if cd.tzinfo else cd.tz_localize("UTC")
        if cd not in px[t["pair"]].index:
            continue
        o = float(px[t["pair"]].loc[cd, "open"])
        if o < t["close_rate"]:
            n_gap += 1
            delta += t["amount"] * (o - t["close_rate"]) * (1 - fee)
    base = rec["profit_total_abs"]
    return {"stop_exits": n_stop, "gap_exits": n_gap, "delta_usdt": delta,
            "profit_pct_freqtrade": base / START_BAL, "profit_pct_gapfill": (base + delta) / START_BAL}


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
    labels = sorted({k[0] for k in runs if k[2] == fee and k[1] != FULL
                     and (k[0] == "default" or k[0].startswith("g_"))})  # WF candidates: param grid only
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
    # --- same walk-forward for the 4h family (tf_4h = default 100/20/3, h_* = grid)
    lab4 = sorted({k[0] for k in runs if k[2] == fee and k[1] != FULL
                   and (k[0] == "tf_4h" or k[0].startswith("h_"))})
    if len(lab4) > 1:
        yr4 = {lab: {y: runs[(lab, y, fee)]["profit_total"] for y in years if (lab, y, fee) in runs}
               for lab in lab4}
        wf4 = []
        for i, y in enumerate(years):
            if i < 2:
                continue
            train = years[:i]
            def score4(lab):
                v = [math.log1p(yr4[lab][t]) for t in train if t in yr4[lab]]
                return sum(v) if len(v) == len(train) else -1e9
            best = max(lab4, key=score4)
            if (best, y, fee) not in runs:
                continue
            m = summarize(runs[(best, y, fee)])
            wf4.append({"test_window": y, "chosen_params": best, "test_return": m["total_return"],
                        "test_max_dd": m["max_dd"], "trades": m["trades"],
                        "default_return": yr4.get("tf_4h", {}).get(y)})
        out["walkforward_4h"] = wf4
        out["grid_yearly_4h"] = yr4
    # --- Monte Carlo trade-order shuffle (idea from jesse): how bad can drawdown get by luck of order
    for fee in (0.001, 0.0025):
        rec = runs.get(("default", FULL, fee))
        if rec:
            out.setdefault("mc_dd", {})[str(fee)] = mc_drawdown(rec)
    # --- E2 regime filters (no LLM): f_none / f_turb / f_adx on 2020+ windows
    FULL2 = "20200101-20261021"
    filt = {}
    for lab in ("f_none", "f_turb", "f_adx"):
        for fee in (0.001, 0.0025):
            rec = runs.get((lab, FULL2, fee))
            if not rec:
                continue
            m = summarize(rec)
            m["random"] = random_entry(rec, fee)
            m["mc_dd"] = mc_drawdown(rec)
            m["years"] = {k[1]: runs[k]["profit_total"] for k in runs
                          if k[0] == lab and k[2] == fee and k[1] != FULL2}
            filt[f"{lab}@{fee}"] = m
    if filt:
        bh = curve_metrics(bh_equity(FULL2, 0.0025))
        filt["bh_btc@0.0025"] = bh
        out["filters"] = filt
    # --- E4 position size variants on the full period (fee 0.25%), compared with default
    var = {}
    for lab in ("default", "s_r2_c50", "s_r3_c100", "jev", "tf_4h"):
        rec = runs.get((lab, FULL, 0.0025))
        if not rec:
            continue
        m = summarize(rec)
        m["random"] = random_entry(rec, 0.0025, tf="4h" if lab == "tf_4h" else "1d")
        m["mc_dd"] = mc_drawdown(rec)
        m["years"] = {k[1]: runs[k]["profit_total"] for k in runs
                      if k[0] == lab and k[2] == 0.0025 and k[1] != FULL}
        var[lab] = m
    if var:
        out["sizing"] = var
    # --- 4h candidate at all fees, random test on 4h bars (vs daily-bar approximation)
    r4 = {}
    for fee in (0.001, 0.0025, 0.003):
        rec = runs.get(("tf_4h", FULL, fee))
        if rec:
            m = summarize(rec)
            m["random_4hbars"] = random_entry(rec, fee, tf="4h")
            m["random_dailybars"] = random_entry(rec, fee, tf="1d")
            r4[str(fee)] = m
    out["tf_4h_full"] = r4
    rec = runs.get(("tf_4h", "20200101-20261021", 0.0025))
    if rec:
        m = summarize(rec)
        m["random_4hbars"] = random_entry(rec, 0.0025, tf="4h")
        out["tf_4h_2020plus"] = m
    # --- gap-fill stress on stop exits (default daily + 4h), fee 0.25% and 0.3%
    gs = {}
    for lab, tf in (("default", "1d"), ("tf_4h", "4h")):
        for fee in (0.0025, 0.003):
            rec = runs.get((lab, FULL, fee))
            if rec:
                gs[f"{lab}@{fee}"] = gap_stress(rec, tf)
    out["gap_stress"] = gs
    json.dump(out, open(f"{D}/summary.json", "w"), indent=1, default=str)
    print(json.dumps(out, indent=1, default=str)[:20000])


if __name__ == "__main__":
    main()
