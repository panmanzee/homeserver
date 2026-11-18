"""papertrader core: data cleaning, strategies, next-open fill simulator.

Shared by the research script AND the live paper engine, so both use identical rules.
Convention (no look-ahead):
  - target weights are decided with data up to the CLOSE of day t
  - the trade fills at the OPEN of day t+1 (cost charged on the weight change)
  - day t+1 return = w_old * (open[t+1]/close[t] - 1)  (overnight gap, old position)
                     then w_new * (close[t+1]/open[t+1] - 1)  (intraday, new position)
Weights: stocks long only 0..1 total; forex -1..1 per pair, sum(|w|) <= 1 (1x, no leverage).
Strategies were declared in the design (Designs/2026-10-23-trading-bot-stocks-forex.md) BEFORE results.
"""
import numpy as np
import pandas as pd

STOCKS = ["SPY", "QQQ"]
STOCK_EXTRA = ["IEF"]           # loaded but not traded (kept for reference only)
FX = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD"]
COST = {"stocks": 0.0005, "forex": 0.0003}   # per side, fraction of traded notional


# ------------------------------------------------------------------ data
SPIKE = {"stocks": 0.12, "forex": 0.06}   # data-repair threshold per market (see clean)


def market_of(name):
    return "stocks" if name in STOCKS + STOCK_EXTRA else "forex"


def clean(df, spike=0.06, back=0.7):
    """Fix known Yahoo problems (DATA REPAIR, not a strategy rule).
    1) one-day bad prints: |r_t| > spike AND the next day moves back the other way by at least
       `back` (70%) of it -> day t's OHLC set to NaN, then forward-filled.
       v2 (2026-10-23, after review): v1 required the next day to undo the move within 1%, which missed
       EURUSD/USDJPY 2008-12-08 (+17%, then -13..-15%). Stocks use spike 12% so real crash days
       (QQQ 2020-03-12, -9%) are kept.
       NOTE: uses day t+1 to judge day t. That repairs HISTORY only; the live engine guards the
       newest bar separately (it waits a day on a move bigger than the spike).
    2) OHLC consistency: High = max(O,H,L,C), Low = min(O,H,L,C) (gold futures rows).
    3) Open missing/zero -> previous close.
    Returns (df, list of repaired dates)."""
    df = df.copy().sort_index()
    df = df[~df.index.duplicated(keep="last")]
    c = df["Close"]
    r = c.pct_change()
    nxt = r.shift(-1)
    bad = (r.abs() > spike) & (np.sign(nxt) == -np.sign(r)) & (nxt.abs() >= back * r.abs() / (1 + r.abs()))
    df.loc[bad, ["Open", "High", "Low", "Close"]] = np.nan
    df = df.ffill()
    o = df["Open"].where(df["Open"] > 0, df["Close"].shift(1))
    df["Open"] = o.fillna(df["Close"])
    hi = df[["Open", "High", "Low", "Close"]].max(axis=1)
    lo = df[["Open", "High", "Low", "Close"]].min(axis=1)
    df["High"], df["Low"] = hi, lo
    return df, [str(d.date()) for d in df.index[bad.reindex(df.index, fill_value=False).values]]


def load(path_dir, names, until=None, weekdays_only=True):
    """until: drop bars dated on/after this day (use to cut an unfinished bar in research)."""
    out, fixes = {}, {}
    for n in names:
        d = pd.read_csv(f"{path_dir}/{n}.csv", parse_dates=["date"], index_col="date")
        if d.index.tz is not None:
            d.index = d.index.tz_localize(None)
        d.index = d.index.normalize()
        if weekdays_only:   # Yahoo serves transient Sat/Sun bars it later deletes; no decision may be dated Sat/Sun
            d = d[d.index.dayofweek < 5]
        if until is not None:
            d = d[d.index < pd.Timestamp(until)]
        out[n], fixes[n] = clean(d, SPIKE[market_of(n)])
    return out, fixes


def panel(data, names, field):
    """Aligned frame of one field; dates = union, forward-filled (holidays differ per market)."""
    f = pd.concat({n: data[n][field] for n in names}, axis=1).sort_index()
    return f.ffill()


# Live engine sets this to a function(date) -> next trading session date (market calendar).
# Research leaves it None: the month's last bar is then read from the data itself.
NEXT_SESSION = None


def month_end_flags(idx):
    """True on the last trading day of each month.
    History: the last bar of each month in the data. The NEWEST bar is a problem in live use,
    because it is always the last bar seen so far; so when NEXT_SESSION is set, the newest bar
    counts as month end only if the next trading session falls in a new month."""
    s = pd.Series(idx, index=idx)
    flags = s.groupby(idx.to_period("M")).transform("max") == idx
    if NEXT_SESSION is not None and len(idx):
        last = idx[-1]
        flags.iloc[-1] = NEXT_SESSION(last).month != last.month
    return flags


# ------------------------------------------------------------------ helpers
def atr(d, n=14):
    pc = d["Close"].shift(1)
    tr = pd.concat([d["High"] - d["Low"], (d["High"] - pc).abs(), (d["Low"] - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


# ------------------------------------------------------------------ stock strategies (weights 0..1)
def s0_hold(data, idx):
    return pd.DataFrame({"SPY": 1.0, "QQQ": 0.0}, index=idx)


def s1_sma200(data, idx):
    c = data["SPY"]["Close"].reindex(idx).ffill()
    w = (c > c.rolling(200).mean()).astype(float)
    w[c.rolling(200).mean().isna()] = 0.0
    return pd.DataFrame({"SPY": w, "QQQ": 0.0}, index=idx)


def trend_simple(d, sma_long=100, breakout=20, sma_exit=50, atr_mult=3.0, hard_stop=0.15, cooldown=2,
                 guard_n=3, guard_days=30, guard_pause=7):
    """TrendSimple (same rules as the BTC bot, full size, TS_PROT=light), long only, one asset.
    entry : close > SMA(100) and close > highest HIGH of the previous 20 days
    exit  : close < SMA(50)  OR  close < highest close since entry - 3*ATR(14) (chandelier)
            OR close < entry_ref*(1-15%) (hard stop; entry_ref = close on signal day)
    light protections: 2-day cooldown after an exit; 3 stop exits within 30 days -> no entries for 7 days.
    All checks on daily closes (decided at close t, filled at open t+1)."""
    c, h = d["Close"], d["High"]
    sl, se = c.rolling(sma_long).mean(), c.rolling(sma_exit).mean()
    hh = h.rolling(breakout).max().shift(1)
    a = atr(d)
    w = np.zeros(len(c))
    pos, ref, peak, cool_until, stops, pause_until = 0, 0.0, 0.0, -1, [], -1
    for i in range(len(c)):
        ci = c.iloc[i]
        if pos == 0:
            if (i > cool_until and i > pause_until and np.isfinite(sl.iloc[i]) and np.isfinite(hh.iloc[i])
                    and ci > sl.iloc[i] and ci > hh.iloc[i]):
                pos, ref, peak = 1, ci, ci
        else:
            peak = max(peak, ci)
            chand = peak - atr_mult * a.iloc[i] if np.isfinite(a.iloc[i]) else -np.inf
            stop_hit = ci < chand or ci < ref * (1 - hard_stop)
            if stop_hit or ci < se.iloc[i]:
                pos, cool_until = 0, i + cooldown
                if stop_hit:
                    stops = [s for s in stops if s > i - guard_days] + [i]
                    if len(stops) >= guard_n:
                        pause_until = i + guard_pause
        w[i] = pos
    return pd.Series(w, index=c.index)


def s2_trend(data, idx):
    w = trend_simple(data["SPY"]).reindex(idx).ffill().fillna(0)
    return pd.DataFrame({"SPY": w, "QQQ": 0.0}, index=idx)


def s3_dual_momentum(data, idx, lb=252):
    """Hold whichever of SPY/QQQ rose more over 12 months (252 trading days); cash if neither is up.
    Decided on the last trading day of each month (fewer trades), held for the month."""
    c = panel(data, STOCKS, "Close").reindex(idx).ffill()
    mom = c / c.shift(lb) - 1
    best = mom.idxmax(axis=1)
    up = mom.max(axis=1) > 0
    w = pd.DataFrame(0.0, index=idx, columns=STOCKS)
    for n in STOCKS:
        w[n] = ((best == n) & up).astype(float)
    w[mom.isna().any(axis=1)] = 0.0
    month_end = month_end_flags(idx)
    w = w.where(month_end).ffill().fillna(0.0)
    return w


STOCK_STRATS = {"S0 hold SPY": s0_hold, "S1 SMA200 exit": s1_sma200, "S2 TrendSimple full": s2_trend,
                "S3 dual momentum": s3_dual_momentum}


# ------------------------------------------------------------------ forex strategies (weights -1..1, gross <= 1)
def _donchian_ls(d, entry=55, exit_=20):
    c, h, l = d["Close"], d["High"], d["Low"]
    he, le = h.rolling(entry).max().shift(1), l.rolling(entry).min().shift(1)
    hx, lx = h.rolling(exit_).max().shift(1), l.rolling(exit_).min().shift(1)
    w, pos = np.zeros(len(c)), 0
    for i in range(len(c)):
        ci = c.iloc[i]
        if not np.isfinite(he.iloc[i]):
            continue
        if pos == 1 and ci < lx.iloc[i]:
            pos = 0
        elif pos == -1 and ci > hx.iloc[i]:
            pos = 0
        if pos == 0:
            if ci > he.iloc[i]:
                pos = 1
            elif ci < le.iloc[i]:
                pos = -1
        w[i] = pos
    return pd.Series(w, index=c.index)


def f1_donchian(data, idx):
    return pd.DataFrame({n: _donchian_ls(data[n]).reindex(idx).ffill().fillna(0) / len(FX) for n in FX}, index=idx)


def f2_ma_cross(data, idx):
    out = {}
    for n in FX:
        c = data[n]["Close"]
        f, s = c.rolling(50).mean(), c.rolling(200).mean()
        w = np.sign(f - s).where(s.notna(), 0.0)
        out[n] = w.reindex(idx).ffill().fillna(0) / len(FX)
    return pd.DataFrame(out, index=idx)


def f3_momentum(data, idx, lb=252, vol_lb=60):
    """sign(12-month return) per pair, inverse-vol weights scaled so gross exposure = 1.
    Rebalanced on the last trading day of each month."""
    c = panel(data, FX, "Close").reindex(idx).ffill()
    sig = np.sign(c / c.shift(lb) - 1)
    vol = c.pct_change().rolling(vol_lb).std()
    inv = 1 / vol
    w = sig * inv.div(inv.sum(axis=1), axis=0)
    w[sig.isna().any(axis=1) | vol.isna().any(axis=1)] = 0.0
    month_end = month_end_flags(idx)
    return w.where(month_end).ffill().fillna(0.0)


FX_STRATS = {"F1 Donchian 55/20 L/S": f1_donchian, "F2 MA 50/200 L/S": f2_ma_cross,
             "F3 12m momentum risk-sized": f3_momentum}


# ------------------------------------------------------------------ simulator
def simulate(weights, data, cost):
    """Next-open fills. weights: DataFrame (dates x assets) decided at close.
    Returns DataFrame with daily net return 'r', 'turnover', 'gross' (held after the open fill)."""
    names = list(weights.columns)
    # raw (not forward-filled) prices: on a day an asset does not trade (holiday / missing row) its
    # gap and intraday return must be 0. Forward-filling Open AND Close made such a day replay the
    # previous day's open->close move, which booked a fake return whenever the weight changed.
    o_raw = pd.concat({n: data[n]["Open"] for n in names}, axis=1).reindex(weights.index)
    c_raw = pd.concat({n: data[n]["Close"] for n in names}, axis=1).reindex(weights.index)
    c = c_raw.ffill()
    traded = o_raw.notna() & c_raw.notna()
    w_old = weights.shift(1).fillna(0.0)       # filled at open t (decided at close t-1), held open->close t
    # trade decided at close t-1 fills at open t: before the open we still hold the weight from close t-2
    w_pre = weights.shift(2).fillna(0.0)
    gap = (o_raw / c.shift(1) - 1).where(traded, 0.0).fillna(0.0)
    intra = (c_raw / o_raw - 1).where(traded, 0.0).fillna(0.0)
    r_gap = (w_pre * gap).sum(axis=1)
    r_in = (w_old * intra).sum(axis=1)
    turn = (w_old - w_pre).abs().sum(axis=1)
    r = (1 + r_gap) * (1 + r_in) - 1 - turn * cost
    return pd.DataFrame({"r": r, "turnover": turn, "gross": w_old.abs().sum(axis=1)})


def stats(res, start=None, end=None, periods=252):
    r = res["r"]
    if start:
        r = r[r.index >= pd.Timestamp(start)]
    if end:
        r = r[r.index < pd.Timestamp(end)]
    eq = (1 + r).cumprod()
    yrs = len(r) / periods
    sh = r.mean() / r.std() * np.sqrt(periods) if r.std() > 0 else 0.0
    g = res["gross"].reindex(r.index)
    t = res["turnover"].reindex(r.index)
    return {"ret": float(eq.iloc[-1] - 1), "cagr": float(eq.iloc[-1] ** (1 / yrs) - 1) if yrs > 0 else 0.0,
            "dd": float((1 - eq / eq.cummax()).max()), "sharpe": float(sh), "trades": int((t > 1e-9).sum()),
            "exposure": float(g.mean()), "days": int(len(r))}
