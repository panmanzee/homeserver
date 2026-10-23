"""papertrader live engine (PAPER MONEY ONLY - no broker, no keys, no real orders).

Each run (daily 08:00 Asia/Bangkok, when the US close and the previous FX day bar are both complete):
  1. download daily bars from Yahoo (yfinance), clean them with core.clean
  2. drop an unfinished bar (today's date in the market's own clock)
  3. if the newest complete bar has no decision yet: run the strategy on data up to that bar
     and JOURNAL the target weights (sqlite table `decisions`; rows are never rewritten)
  4. equity = replay of journaled decisions through core.simulate: each decision fills at the
     next bar's OPEN with core.COST per side. Same simulator as the research, so paper == backtest rules.
  5. write state/<bot>-status.json for the weekly report

Env: BOT=stocks|forex, STRATEGY=<key of core.STOCK_STRATS / core.FX_STRATS>, START_CASH (default 3000),
     STATE_DIR (default /app/state), RUN_AT (default 08:00, Asia/Bangkok).
Usage: python engine.py --once | --loop | --report
"""
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

import core

BOT = os.environ.get("BOT", "stocks")
STRATEGY = os.environ.get("STRATEGY", "")
START_CASH = float(os.environ.get("START_CASH", "3000"))
STATE = os.environ.get("STATE_DIR", "/app/state")
RUN_AT = os.environ.get("RUN_AT", "08:00")
BKK = ZoneInfo("Asia/Bangkok")

TICKERS = {"SPY": "SPY", "QQQ": "QQQ", "IEF": "IEF", "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X",
           "USDJPY": "USDJPY=X", "AUDUSD": "AUDUSD=X", "XAUUSD": "GC=F"}
if BOT == "stocks":
    NAMES, STRATS, MARKET_TZ, CLOSE_AT, SPIKE = core.STOCKS, core.STOCK_STRATS, "America/New_York", "16:30", 0.12
    BENCH = "SPY"
else:
    NAMES, STRATS, MARKET_TZ, CLOSE_AT, SPIKE = core.FX, core.FX_STRATS, "UTC", "23:59", 0.06
    BENCH = None
DATA = f"{STATE}/data-{BOT}"


def _next_session_stocks(d):
    import exchange_calendars as xc
    cal = xc.get_calendar("XNYS")
    return cal.next_session(pd.Timestamp(d.date())).tz_localize(None) if cal.is_session(pd.Timestamp(d.date()))         else cal.date_to_session(pd.Timestamp(d.date()), direction="next").tz_localize(None)


def _next_session_fx(d):
    return pd.Timestamp(d.date()) + pd.offsets.BDay(1)


core.NEXT_SESSION = _next_session_stocks if BOT == "stocks" else _next_session_fx


def log(*a):
    print(datetime.now(BKK).strftime("%Y-%m-%d %H:%M"), f"[{BOT}]", *a, flush=True)


def db():
    con = sqlite3.connect(f"{STATE}/{BOT}.sqlite")
    con.execute("CREATE TABLE IF NOT EXISTS decisions (bar_date TEXT PRIMARY KEY, strategy TEXT, "
                "weights TEXT, decided_at TEXT, note TEXT)")
    return con


def fetch():
    import yfinance as yf
    os.makedirs(DATA, exist_ok=True)
    for n in NAMES:
        df = yf.download(TICKERS[n], start="2000-01-01", auto_adjust=True, progress=False, multi_level_index=False)
        df = df[["Open", "High", "Low", "Close"]].dropna()
        if len(df) < 500:
            raise RuntimeError(f"too little data for {n}: {len(df)} rows")
        df.index.name = "date"
        df.to_csv(f"{DATA}/{n}.csv")


def complete_bars(data):
    """Drop a bar dated 'today' in the market clock if the market day is not over yet."""
    now = datetime.now(ZoneInfo(MARKET_TZ))
    today = pd.Timestamp(now.date())
    hh, mm = map(int, CLOSE_AT.split(":"))
    done = (now.hour, now.minute) >= (hh, mm)
    for n, d in data.items():
        if len(d) and d.index[-1] >= today and not (d.index[-1] == today and done):
            data[n] = d[d.index < today]
    return data


def journal():
    con = db()
    rows = con.execute("SELECT bar_date, weights FROM decisions ORDER BY bar_date").fetchall()
    con.close()
    if not rows:
        return None
    w = pd.DataFrame([json.loads(x) for _, x in rows], index=pd.to_datetime([b for b, _ in rows]))
    return w[NAMES]


def run_once():
    if STRATEGY not in STRATS:
        raise SystemExit(f"STRATEGY must be one of {list(STRATS)}")
    fetch()
    data, fixes = core.load(DATA, NAMES)
    data = complete_bars(data)
    idx = core.panel(data, NAMES, "Close").index
    bar = idx[-1]
    con = db()
    have = con.execute("SELECT 1 FROM decisions WHERE bar_date=?", (str(bar.date()),)).fetchone()
    if have:
        log("bar", bar.date(), "already decided")
    else:
        last_r = core.panel(data, NAMES, "Close").pct_change().iloc[-1].abs().max()
        if last_r > SPIKE:
            log(f"bar {bar.date()} moved {last_r:.1%} > {SPIKE:.0%}: possible bad tick, wait for next bar")
        else:
            w = STRATS[STRATEGY](data, idx).iloc[-1]
            con.execute("INSERT INTO decisions VALUES (?,?,?,?,?)",
                        (str(bar.date()), STRATEGY, json.dumps({k: float(w[k]) for k in NAMES}),
                         datetime.now(BKK).isoformat(timespec="minutes"), ""))
            con.commit()
            log("decided on bar", bar.date(), {k: round(float(w[k]), 3) for k in NAMES})
    con.close()
    status(data, idx)


def status(data, idx):
    w = journal()
    out = {"bot": BOT, "strategy": STRATEGY, "start_cash": START_CASH, "updated": datetime.now(BKK).isoformat(timespec="minutes"),
           "last_bar": str(idx[-1].date())}
    if w is not None:
        start = w.index[0]
        full = w.reindex(idx[idx >= start]).ffill().fillna(0.0)
        res = core.simulate(full, data, core.COST[BOT])
        eq = START_CASH * (1 + res["r"]).cumprod()
        held = full.iloc[-2] if len(full) > 1 else full.iloc[-1] * 0   # filled at the latest bar's open
        out.update({
            "paper_start_bar": str(start.date()), "equity": round(float(eq.iloc[-1]), 2),
            "return_pct": round(float(eq.iloc[-1] / START_CASH - 1) * 100, 2),
            "max_drop_pct": round(float((1 - eq / eq.cummax()).max()) * 100, 2),
            "held_now": {k: round(float(v), 3) for k, v in held.items()},
            "target_next_open": {k: round(float(v), 3) for k, v in full.iloc[-1].items()},
            "decisions": int(len(w)), "trades": int((res["turnover"] > 1e-9).sum()),
        })
        if BENCH:
            c = data[BENCH]["Close"].reindex(full.index).ffill()
            o = data[BENCH]["Open"].reindex(full.index).ffill()
            b = (c.iloc[-1] / o.iloc[1] - 1) * 100 if len(c) > 1 else 0.0
            out["bench"] = {"name": f"{BENCH} hold (bought at the open after start)", "return_pct": round(float(b), 2)}
    with open(f"{STATE}/{BOT}-status.json", "w") as f:
        json.dump(out, f, indent=1)
    log("status", json.dumps({k: out.get(k) for k in ("equity", "return_pct", "held_now", "target_next_open")}))
    return out


def report():
    """Markdown section for the weekly report + one Telegram line (printed as %% TG: ... %%)."""
    try:
        s = json.load(open(f"{STATE}/{BOT}-status.json"))
    except FileNotFoundError:
        print(f"## {BOT}: no status yet\n%% TG: {BOT}: no status yet %%")
        return
    name = {"stocks": "Stocks bot (SPY/QQQ)", "forex": "Forex bot (4 majors + gold)"}[BOT]
    print(f"## {name} - paper, strategy {s['strategy']}")
    if "equity" not in s:
        print("No decision yet.\n%% TG: " + f"{BOT}: no decision yet %%")
        return
    print(f"- Since {s['paper_start_bar']}: equity **{s['equity']:,.2f} USD** ({s['return_pct']:+.2f}%), worst drop {s['max_drop_pct']:.2f}%, trades {s['trades']}")
    if s.get("bench"):
        print(f"- {s['bench']['name']}: {s['bench']['return_pct']:+.2f}%")
    held = ", ".join(f"{k} {v:+.2f}" for k, v in s["held_now"].items() if abs(v) > 1e-6) or "cash"
    tgt = ", ".join(f"{k} {v:+.2f}" for k, v in s["target_next_open"].items() if abs(v) > 1e-6) or "cash"
    print(f"- Holding now: {held}. Target for next open: {tgt}. Last bar {s['last_bar']}, updated {s['updated']}")
    tg = f"{BOT} {s['return_pct']:+.2f}% ({held})"
    if s.get("bench"):
        tg += f" vs {BENCH} {s['bench']['return_pct']:+.2f}%"
    print(f"%% TG: {tg} %%")


def loop():
    hh, mm = map(int, RUN_AT.split(":"))
    while True:
        try:
            run_once()
        except Exception as e:  # keep the service alive; next run retries
            log("ERROR", repr(e))
        now = datetime.now(BKK)
        nxt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        log("next run", nxt.isoformat(timespec="minutes"))
        time.sleep((nxt - now).total_seconds())


if __name__ == "__main__":
    os.makedirs(STATE, exist_ok=True)
    arg = sys.argv[1] if len(sys.argv) > 1 else "--once"
    {"--once": run_once, "--loop": loop, "--report": report}[arg]()
