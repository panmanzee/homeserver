"""Journal vs data check: python journal_check.py SQLITE [DATA_DIR] [--move-offsession]  (env BOT=forex|stocks)"""
import os, sqlite3, sys
from datetime import datetime
import pandas as pd
import core

args = [a for a in sys.argv[1:] if not a.startswith("--")]
move = "--move-offsession" in sys.argv
bot = os.environ.get("BOT", "forex")
db = args[0]
names = core.FX if bot == "forex" else core.STOCKS
ddir = args[1] if len(args) > 1 else os.path.join(os.path.dirname(db), "data-" + bot)
data, _ = core.load(ddir, names)
have = set().union(*(set(d.index) for d in data.values()))
con = sqlite3.connect(db)
COLS = {"decisions": "bar_date TEXT PRIMARY KEY, strategy TEXT, weights TEXT, decided_at TEXT, note TEXT",
        "equity": "bar_date TEXT PRIMARY KEY, equity REAL, recorded_at TEXT"}
bad = 0
for t in COLS:
    dates = [r[0] for r in con.execute(f"SELECT bar_date FROM {t} ORDER BY bar_date")]
    missing = [b for b in dates if pd.Timestamp(b) not in have]
    print(f"{t}: {len(dates)} rows, dates not in data: {missing}")
    bad += len(missing)
    off = [b for b in dates if pd.Timestamp(b).dayofweek >= 5]
    if move and off:
        with con:
            con.execute(f"CREATE TABLE IF NOT EXISTS {t}_offsession ({COLS[t]}, moved_at TEXT)")
            con.executemany(f"INSERT OR IGNORE INTO {t}_offsession SELECT *, ? FROM {t} WHERE bar_date=?",
                            [(datetime.now().isoformat(timespec="seconds"), b) for b in off])
            con.executemany(f"DELETE FROM {t} WHERE bar_date=?", [(b,) for b in off])
        print(f"  moved to {t}_offsession: {off}")
    elif off:
        print(f"  dry-run, would move to {t}_offsession (use --move-offsession): {off}")
if move:
    bad = sum(1 for t in COLS for (b,) in con.execute(f"SELECT bar_date FROM {t}") if pd.Timestamp(b) not in have)
sys.exit(1 if bad else 0)
