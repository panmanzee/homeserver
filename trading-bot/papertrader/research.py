"""Research run for the pre-declared stock + forex candidates (design 2026-10-23-trading-bot-stocks-forex).
No rule or parameter is changed here; everything comes from core.py.
Window convention: weights decided before the last trading day before `start` are set to 0, so every
strategy (and hold) enters at the OPEN of the first window day and pays the entry cost.
"""
import json
import os
import warnings

import numpy as np
import pandas as pd

import core

warnings.filterwarnings("ignore", category=FutureWarning)
N_SHUF, N_LA, SEED = 1000, 150, 42
UNTIL = os.environ.get("UNTIL", "2026-10-23")   # bars dated on/after this are unfinished at research time -> dropped


def window_weights(w, start):
    """Zero all decisions before the close of the last day before `start` (=> entry at first window open)."""
    pre = w.index[w.index < pd.Timestamp(start)]
    w = w.copy()
    if len(pre):
        w.loc[w.index < pre[-1]] = 0.0
    return w


def ppy(r):
    days = (r.index[-1] - r.index[0]).days + 1
    return len(r) / (days / 365.25)


def run(w, data, cost, start):
    res = core.simulate(window_weights(w, start), data, cost)
    r = res["r"][res.index >= pd.Timestamp(start)]
    st = core.stats(res, start, periods=ppy(r))
    st["yrs"] = round(len(r) / ppy(r), 2)
    # CAGR on calendar time (stats uses len/periods; periods already = actual rows per calendar year)
    return res, st


def year_table(res, start):
    r = res["r"][res.index >= pd.Timestamp(start)]
    return {int(y): float((1 + g).prod() - 1) for y, g in r.groupby(r.index.year)}


def year_dd(res, start):
    r = res["r"][res.index >= pd.Timestamp(start)]
    out = {}
    for y, g in r.groupby(r.index.year):
        eq = (1 + g).cumprod()
        out[int(y)] = float((1 - eq / eq.cummax().clip(lower=1.0)).max())
    return out


# ------------------------------------------------------------------ luck test
def runs(a):
    """Split a 2-D array (rows x cols) into runs of identical rows -> list of row-blocks."""
    ch = np.r_[True, np.any(a[1:] != a[:-1], axis=1)]
    starts = np.flatnonzero(ch)
    return np.split(a, starts[1:])


def luck(w, data, cost, start, per_column, rng):
    w = window_weights(w, start)
    pre = w.index[w.index < pd.Timestamp(start)]
    cut = w.index.get_loc(pre[-1]) if len(pre) else 0       # first decision that matters
    res0 = core.simulate(w, data, cost)
    P = ppy(res0["r"][res0.index >= pd.Timestamp(start)])
    real = core.stats(res0, start, periods=P)["sharpe"]
    head, tail = w.values[:cut], w.values[cut:]
    groups = [[j] for j in range(w.shape[1])] if per_column else [list(range(w.shape[1]))]
    blocks = [runs(tail[:, g]) for g in groups]
    sh = []
    for _ in range(N_SHUF):
        new = tail.copy()
        for g, bl in zip(groups, blocks):
            order = rng.permutation(len(bl))
            new[:, g] = np.concatenate([bl[i] for i in order], axis=0)
        ws = pd.DataFrame(np.vstack([head, new]), index=w.index, columns=w.columns)
        sh.append(core.stats(core.simulate(ws, data, cost), start, periods=P)["sharpe"])
    sh = np.array(sh)
    return {"real_sharpe": float(real), "pct_beaten": float((real > sh).mean() * 100),
            "shuffle_median": float(np.median(sh)), "n_blocks": [len(b) for b in blocks]}


# ------------------------------------------------------------------ look-ahead
def lookahead(f, data, names, idx, wfull, start, rng):
    cand = idx[(idx >= pd.Timestamp(start)) & (idx < idx[-1])]
    ts = sorted(rng.choice(cand, size=N_LA, replace=False))
    bad = []
    for t in ts:
        t = pd.Timestamp(t)
        nxt = idx[idx.get_loc(t) + 1]   # trading calendar known one day ahead (needed for month-end)
        dt = {n: data[n].loc[:t] for n in names}
        it = idx[idx <= nxt]
        wt = f(dt, it).loc[t]
        if not np.allclose(wt.values, wfull.loc[t, wt.index].values, atol=1e-12):
            bad.append(str(t.date()))
    return {"dates_checked": len(ts), "mismatches": len(bad), "mismatch_dates": bad[:10]}


def next_session(name):
    """Live calendar for TODAY's signal only (same functions as engine.py). History stays data-based."""
    if name == "stocks":
        import exchange_calendars as xc
        cal = xc.get_calendar("XNYS")
        return lambda d: cal.date_to_session(pd.Timestamp(d.date()), direction="next").tz_localize(None)             if not cal.is_session(pd.Timestamp(d.date())) else cal.next_session(pd.Timestamp(d.date())).tz_localize(None)
    return lambda d: pd.Timestamp(d.date()) + pd.offsets.BDay(1)


def today_live(f, data, idx, name):
    core.NEXT_SESSION = next_session(name)
    try:
        w = f(data, idx).iloc[-1]
    finally:
        core.NEXT_SESSION = None
    return {c: round(float(v), 4) for c, v in w.items()}


def market(name, data, names, strats, cost, start, starts_extra, per_column, gate):
    idx = core.panel(data, names, "Close").index
    rng = np.random.default_rng(SEED)
    out = {"window_start": start, "window_end": str(idx[-1].date()), "strategies": {}}
    W = {k: f(data, idx) for k, f in strats.items()}
    refs = {}
    if name == "stocks":
        for ref in ["SPY", "QQQ"]:
            w = pd.DataFrame({"SPY": 1.0 if ref == "SPY" else 0.0, "QQQ": 1.0 if ref == "QQQ" else 0.0}, index=idx)
            refs[ref] = w
    for k, w in W.items():
        res, st = run(w, data, cost, start)
        e = {"stats": st, "years": year_table(res, start), "year_dd": year_dd(res, start),
             "today_research_flag": {c: round(float(v), 4) for c, v in w.iloc[-1].items()},
             "today": today_live(strats[k], data, idx, name), "last_bar": str(idx[-1].date()),
             "next_session": str(next_session(name)(idx[-1]).date())}
        if not k.startswith("S0"):
            print("luck", k, flush=True)
            e["luck"] = luck(w, data, cost, start, per_column, rng)
            print("lookahead", k, flush=True)
            e["lookahead"] = lookahead(strats[k], data, names, idx, w, start, rng)
        e["sensitivity"] = {}
        for s in starts_extra:
            res2, st2 = run(w, data, cost, s)
            st2["years"] = year_table(res2, s)
            e["sensitivity"][s] = st2
        out["strategies"][k] = e
    for ref, w in refs.items():
        res, st = run(w, data, cost, start)
        out.setdefault("refs", {})[ref] = {"stats": st, "years": year_table(res, start), "year_dd": year_dd(res, start),
                                          "sensitivity": {s: run(w, data, cost, s)[1] for s in starts_extra}}
    gate(out)
    return out


def stock_gate(out):
    h = out["refs"]["SPY"]
    for k, e in out["strategies"].items():
        if k.startswith("S0"):
            continue
        st = e["stats"]
        g = {"ret_ratio": st["ret"] / h["stats"]["ret"], "dd_ratio": st["dd"] / h["stats"]["dd"]}
        g["ret_ok"] = g["ret_ratio"] >= 0.6
        g["dd_ok"] = g["dd_ratio"] <= 0.5
        g["luck_ok"] = e["luck"]["pct_beaten"] >= 95
        g["la_ok"] = e["lookahead"]["mismatches"] == 0
        g["pass"] = all([g["ret_ok"], g["dd_ok"], g["luck_ok"], g["la_ok"]])
        g["sens"] = {s: {"ret_ratio": v["ret"] / h["sensitivity"][s]["ret"], "dd_ratio": v["dd"] / h["sensitivity"][s]["dd"]}
                     for s, v in e["sensitivity"].items()}
        e["gate"] = g


def fx_gate(out):
    for k, e in out["strategies"].items():
        st = e["stats"]
        yrs = e["years"]
        g = {"ret_ok": st["ret"] > 0, "sharpe_ok": st["sharpe"] >= 0.5, "dd_ok": st["dd"] <= 0.20,
             "luck_ok": e["luck"]["pct_beaten"] >= 95, "la_ok": e["lookahead"]["mismatches"] == 0,
             "pos_years": sum(v > 0 for v in yrs.values()), "n_years": len(yrs)}
        g["pos_share"] = g["pos_years"] / g["n_years"]
        g["years_ok"] = g["pos_share"] >= 0.6
        g["pass"] = all(g[x] for x in ["ret_ok", "sharpe_ok", "dd_ok", "luck_ok", "la_ok", "years_ok"])
        e["gate"] = g


def main():
    data, fixes = core.load("data", core.STOCKS + core.STOCK_EXTRA + core.FX, until=UNTIL)
    print("bad-tick fixes:", fixes, "total", sum(len(v) for v in fixes.values()))
    R = {"bad_tick_fixes": fixes, "costs": core.COST, "n_shuffles": N_SHUF, "seed": SEED}
    R["stocks"] = market("stocks", data, core.STOCKS, core.STOCK_STRATS, core.COST["stocks"], "2005-01-01",
                         ["2001-01-01", "2008-01-01", "2010-01-01", "2015-01-01"], False, stock_gate)
    R["forex"] = market("forex", data, core.FX, core.FX_STRATS, core.COST["forex"], "2008-01-01",
                        ["2010-01-01", "2015-01-01"], True, fx_gate)
    os.makedirs("results", exist_ok=True)
    with open("results/research.json", "w") as fh:
        json.dump(R, fh, indent=1, default=lambda o: bool(o) if isinstance(o, np.bool_) else str(o))
    for m in ["stocks", "forex"]:
        print("\n==", m, R[m]["window_start"], "->", R[m]["window_end"])
        rows = list(R[m]["strategies"].items()) + list(R[m].get("refs", {}).items())
        for k, e in rows:
            s = e["stats"]
            line = f"{k:30s} ret {s['ret']*100:8.1f}% cagr {s['cagr']*100:5.1f}% dd {s['dd']*100:5.1f}% sh {s['sharpe']:.2f} trades {s['trades']:4d} exp {s['exposure']:.2f}"
            if "luck" in e:
                line += f" luck {e['luck']['pct_beaten']:.1f}% LA {e['lookahead']['mismatches']}"
            if "gate" in e:
                line += " gate " + str({a: (round(b, 3) if isinstance(b, float) else b) for a, b in e["gate"].items() if a != "sens"})
            print(line)
            if "today" in e:
                print("   today (live calendar, next", e["next_session"], "):", e["today"], "| data-flag version:", e["today_research_flag"])


if __name__ == "__main__":
    main()
