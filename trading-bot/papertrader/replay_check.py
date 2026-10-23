"""Live == backtest check: replay the live engine's decision rule day by day over the last ~2 years
(data truncated at each bar, calendar month-end for the newest bar) and compare with the full-history
research weights. Any mismatch = look-ahead or live/backtest drift."""
import sys, pandas as pd, core, engine
bot = engine.BOT
names, strats = engine.NAMES, engine.STRATS
data, _ = core.load("data", names)
idx = core.panel(data, names, "Close").index
days = idx[idx >= "2024-10-01"]
for name, f in strats.items():
    core.NEXT_SESSION = None
    full = f(data, idx)
    core.NEXT_SESSION = engine._next_session_stocks if bot == "stocks" else engine._next_session_fx
    bad = 0
    for t in days:
        dt = {n: d.loc[:t] for n, d in data.items()}
        it = idx[idx <= t]
        w = f(dt, it).iloc[-1]
        if (w - full.loc[t]).abs().max() > 1e-9:
            bad += 1
            if bad <= 3: print("  mismatch", name, t.date(), dict(w.round(3)), dict(full.loc[t].round(3)))
    print(bot, name, "days", len(days), "mismatches", bad, flush=True)
