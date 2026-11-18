"""Repro: a transient Saturday bar from Yahoo must not produce a weekend-dated decision."""
import os, shutil, sqlite3, sys, tempfile
import pandas as pd
# usage: python weekend_repro.py [--old]   (--old = pre-fix loader that keeps weekend bars)
OLD = "--old" in sys.argv

tmp = tempfile.mkdtemp()
os.environ.update(BOT="forex", STRATEGY="F3 12m momentum risk-sized", STATE_DIR=tmp)
import core, engine
if OLD:
    _l = core.load
    core.load = lambda *a, **k: _l(*a, weekdays_only=False, **k)

SRC = os.environ.get("LIVE_DATA", os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "data-forex"))
os.makedirs(engine.DATA)
for n in engine.NAMES:
    d = pd.read_csv(f"{SRC}/{n}.csv", parse_dates=["date"], index_col="date")
    d[d.index <= "2026-11-06"].to_csv(f"{engine.DATA}/{n}.csv")
engine.fetch = lambda: None

def journal():
    con = sqlite3.connect(f"{tmp}/forex.sqlite")
    rows = con.execute("SELECT bar_date, weights FROM decisions ORDER BY bar_date").fetchall()
    con.close()
    return rows

data, _ = core.load(engine.DATA, engine.NAMES)
idx = core.panel(data, engine.NAMES, "Close").index
expect = engine.STRATS[engine.STRATEGY](data, idx).iloc[-1]
engine.run_once()

p = f"{engine.DATA}/USDJPY.csv"
d = pd.read_csv(p, parse_dates=["date"], index_col="date")
d.loc[pd.Timestamp("2026-11-07")] = d.iloc[-1]
d.to_csv(p)
engine.run_once()

rows = journal()
for b, w in rows[-3:]:
    print(b, pd.Timestamp(b).day_name(), w)
bad = [b for b, _ in rows if pd.Timestamp(b).dayofweek >= 5]
fri = dict(rows).get("2026-11-06")
import json
assert fri and max(abs(json.loads(fri)[k] - float(expect[k])) for k in engine.NAMES) < 1e-12, "Friday weights changed"
print("weekend decisions:", bad)
shutil.rmtree(tmp)
sys.exit(1 if bad else 0)
