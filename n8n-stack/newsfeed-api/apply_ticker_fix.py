import sys, json
sys.path.insert(0, "/app")
from app.db import pool

with open("/app/ticker_name_lookup.json") as f:
    lookup = json.load(f)

pool.open()
with pool.connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT symbol, name FROM tickers")
        rows = cur.fetchall()
        updated, unmatched = 0, []
        for r in rows:
            sym = r["symbol"]
            correct = lookup.get(sym.upper())
            if correct and correct != r["name"]:
                cur.execute("UPDATE tickers SET name = %s WHERE symbol = %s", (correct, sym))
                updated += 1
            elif not correct:
                unmatched.append(sym)
        conn.commit()

print(f"Updated {updated} ticker names.")
print(f"{len(unmatched)} symbols had no match in the reference lookup (crypto/ETF/foreign, left as-is): {unmatched}")
