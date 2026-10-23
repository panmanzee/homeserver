"""
weekly_report.py - paper-trading weekly report (markdown to stdout).
Run on the Proxmox host (cron) via:
  pct exec 101 -- docker exec freqtrade python /freqtrade/user_data/scripts/weekly_report.py
Reads both dry-run sqlite DBs (A = TrendSimple, B = TrendSimpleJev), live prices from Binance
public ticker (no key), and compares with BTC buy-and-hold since the paper start.
Read-only: never writes to the bot DBs.
"""
import json
import sqlite3
import urllib.request
from datetime import datetime, timezone

UD = "/freqtrade/user_data"
START_BAL = 3000.0
PAPER_START = "2026-10-23"          # v2 bot D (BTC only, full size) started 2026-10-23 09:36 UTC
BTC_AT_START = None                 # filled from Binance daily kline of PAPER_START
BOTS = {"D BTC trend, full size (v2)": f"{UD}/tradesv3.dryrun-btc.sqlite"}
# old A/B/C (BTC+ETH, 1% risk) stopped 2026-10-23 with 0 trades; DBs kept for history.


def get_json(url):
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.load(r)


def price(pair):
    try:
        return float(get_json(f"https://api.binance.com/api/v3/ticker/price?symbol={pair.replace('/', '')}")["price"])
    except Exception:
        return None


def btc_open_on(day):
    try:
        ts = int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
        k = get_json(f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d&startTime={ts}&limit=1")
        return float(k[0][1])
    except Exception:
        return None


def bot_stats(db):
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    rows = [dict(r) for r in c.execute("select * from trades order by open_date")]
    c.close()
    closed = [r for r in rows if not r["is_open"]]
    opened = [r for r in rows if r["is_open"]]
    realized = sum(r["close_profit_abs"] or 0 for r in closed)
    unreal = 0.0
    for r in opened:
        p = price(r["pair"])
        if p:
            unreal += r["amount"] * p * (1 - (r["fee_close"] or 0.001)) - r["open_trade_value"]
    eq = START_BAL + realized + unreal
    wins = sum(1 for r in closed if (r["close_profit_abs"] or 0) > 0)
    return {"trades_closed": len(closed), "trades_open": len(opened), "wins": wins,
            "realized": realized, "unrealized": unreal, "equity": eq,
            "return_pct": (eq / START_BAL - 1) * 100, "rows": rows}


def signal_now():
    """Plain-words state of the strategy rules on the last closed daily candle."""
    try:
        k = get_json("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d&limit=230")[:-1]
        cl = [float(x[4]) for x in k]; hi = [float(x[2]) for x in k]
        sma100 = sum(cl[-100:]) / 100; sma50 = sum(cl[-50:]) / 50; hh = max(hi[-21:-1])
        return (f"BTC close {cl[-1]:,.0f} | 100-day avg {sma100:,.0f} ({'above' if cl[-1] > sma100 else 'below'}) | "
                f"20-day high {hh:,.0f} ({'broken' if cl[-1] > hh else 'not broken'}) | 50-day avg {sma50:,.0f}")
    except Exception as e:
        return f"signal check failed: {type(e).__name__}"


def main():
    now = datetime.now(timezone.utc)
    btc_now, btc_start = price("BTC/USDT"), btc_open_on(PAPER_START)
    bh = (btc_now / btc_start - 1) * 100 if btc_now and btc_start else None
    out = [f"---\ntype: report\nproject: trading-bot\ndate: {now:%Y-%m-%d}\n---",
           f"# Paper trading weekly report - {now:%Y-%m-%d}", "",
           f"Paper since {PAPER_START}. Fake money {START_BAL:.0f} USDT per bot. Dry-run only.", "",
           "| Bot | Equity USDT | Return % | Closed | Open | Wins |", "|---|---|---|---|---|---|"]
    stats = {}
    for name, db in BOTS.items():
        try:
            s = bot_stats(db)
            stats[name] = s
            out.append(f"| {name} | {s['equity']:.2f} | {s['return_pct']:+.2f} | {s['trades_closed']} | "
                       f"{s['trades_open']} | {s['wins']} |")
        except Exception as e:
            out.append(f"| {name} | ERROR {type(e).__name__}: {e} | | | | |")
    out.append(f"| BTC buy & hold | | {bh:+.2f} | | | |" if bh is not None else "| BTC buy & hold | n/a (price fetch failed) | | | | |")
    out += ["", "## Trades"]
    for name, s in stats.items():
        out.append(f"**{name}**")
        if not s["rows"]:
            out.append("- no trades yet (normal: slow daily trend strategy)")
        for r in s["rows"]:
            res = "open" if r["is_open"] else f"{(r['close_profit'] or 0) * 100:+.2f}% ({r['exit_reason']})"
            out.append(f"- {r['pair']} in {str(r['open_date'])[:10]} @ {r['open_rate']:.2f}, "
                       f"stake {r['stake_amount']:.0f} -> {res}")
    out += ["", "## Strategy state", "- " + signal_now(),
            "- Buy rule: close above 100-day avg AND above 20-day high. Sell: close under 50-day avg or trailing stop (3x ATR).",
            "", "## Gate check (needs 4+ weeks of paper)",
            "- keeps >= 60% of BTC hold return with <= half its drop; worst drop <= 40%; no crash / missed stop."]
    d = stats.get("D BTC trend, full size (v2)")
    tg = (f"BTC bot weekly: equity {d['equity']:.0f} USDT ({d['return_pct']:+.1f}%), open {d['trades_open']}, "
          f"closed {d['trades_closed']}" if d else "BTC bot weekly: stats error") + (f" | BTC hold {bh:+.1f}%" if bh is not None else "")
    out.append(f"\n%% TG: {tg} %%")
    print("\n".join(out))


if __name__ == "__main__":
    main()
