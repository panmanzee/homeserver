#!/usr/bin/env python3
"""Backtest Today's Picks — replay the screener over the last N days and
measure picked tickers' forward return vs. an equal-weight benchmark.

This is NOT a guarantee of anything and is not treated as one: it is a
sanity check on a small sample (this box has ~38 trading days of price
history total) testing whether "price rose + news net-positive" correlates
with further gains over the next HOLD_DAYS trading days. Report the numbers
as measured — see docs/superpowers/specs/2026-09-21-picks-accuracy-
improvements-design.md §2 for why the screener's formula does not get
retuned based on this output (that would be overfitting a tiny sample, not
an improvement).

Usage: DATABASE_URL=postgresql://... python scripts/backtest_picks.py
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db, picks  # noqa: E402

HOLD_DAYS = 5
LOOKBACK_DAYS = 30


def _trading_days(conn) -> list[date]:
    rows = conn.execute("SELECT DISTINCT date FROM stock_prices ORDER BY date").fetchall()
    return [r["date"] for r in rows]


def _close_on(conn, symbol: str, target: date) -> float | None:
    row = conn.execute(
        "SELECT close FROM stock_prices WHERE symbol = %s AND date = %s",
        (symbol, target),
    ).fetchone()
    return float(row["close"]) if row and row["close"] is not None else None


def _summarize(returns: list[float]) -> str:
    if not returns:
        return "n=0"
    n = len(returns)
    mean = sum(returns) / n
    win_rate = sum(1 for r in returns if r > 0) / n * 100
    sorted_r = sorted(returns)
    median = sorted_r[n // 2] if n % 2 else (sorted_r[n // 2 - 1] + sorted_r[n // 2]) / 2
    return f"n={n}  mean={mean:+.2f}%  median={median:+.2f}%  win_rate={win_rate:.0f}%"


def main() -> None:
    db.pool.open()
    try:
        with db.pool.connection() as conn:
            all_days = _trading_days(conn)

        if len(all_days) < HOLD_DAYS + 2:
            print(f"Not enough price history ({len(all_days)} trading days) to backtest.")
            return

        cutoff = date.today() - timedelta(days=LOOKBACK_DAYS)
        candidate_days = [d for d in all_days if d >= cutoff]
        usable_days = [
            d for d in candidate_days
            if all_days.index(d) + HOLD_DAYS < len(all_days)
        ]

        pick_returns: list[float] = []
        benchmark_returns: list[float] = []
        day_reports: list[tuple[date, int, list[float]]] = []

        with db.pool.connection() as conn:
            for d in usable_days:
                forward_date = all_days[all_days.index(d) + HOLD_DAYS]

                price_rows = db.recent_price_changes(as_of=str(d))
                ticker_news = db.recent_ticker_news(days=7, as_of=str(d))
                sections = picks.build_picks(price_rows, ticker_news)
                day_picks = [p for bucket in sections.values() for p in bucket]

                day_pick_returns = []
                for p in day_picks:
                    start = _close_on(conn, p["symbol"], d)
                    end = _close_on(conn, p["symbol"], forward_date)
                    if start and end:
                        ret = (end - start) / start * 100
                        pick_returns.append(ret)
                        day_pick_returns.append(ret)

                bench_rows = conn.execute(
                    "SELECT symbol, close FROM stock_prices WHERE date = %s", (d,)
                ).fetchall()
                for r in bench_rows:
                    start = float(r["close"]) if r["close"] is not None else None
                    end = _close_on(conn, r["symbol"], forward_date)
                    if start and end:
                        benchmark_returns.append((end - start) / start * 100)

                day_reports.append((d, len(day_picks), day_pick_returns))

        print(
            f"Today's Picks backtest — {len(usable_days)} days replayed, "
            f"{HOLD_DAYS}-trading-day forward hold\n"
        )
        print("Per-day picks and their forward return:")
        for d, count, pr in day_reports:
            pr_s = _summarize(pr) if pr else "no picks with forward price data"
            print(f"  {d}  picks={count:2d}  {pr_s}")

        print("\n" + "=" * 70)
        print("PICKS                                   :", _summarize(pick_returns))
        print("BENCHMARK (equal-weight, all tickers, same windows):", _summarize(benchmark_returns))
        print("=" * 70)
        if pick_returns and benchmark_returns:
            edge = (sum(pick_returns) / len(pick_returns)) - (
                sum(benchmark_returns) / len(benchmark_returns)
            )
            print(f"\nPicks vs. benchmark mean forward return: {edge:+.2f} percentage points")

        print(
            f"\nCaveat: only {len(all_days)} trading days of price history exist on this "
            "box — this is a direction-of-effect sanity check, not a statistically "
            "powered study. See the design spec §2/§5 for why this formula does not "
            "get retuned to chase a better number here."
        )
    finally:
        db.pool.close()


if __name__ == "__main__":
    main()
