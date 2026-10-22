"""Run inside the newsfeed-api container. Upserts real Nasdaq-100 names into
`tickers` (fixing any wrong names from the enrichment cross-wiring bug),
then backfills price history for any symbol that's missing it."""
import sys, time
sys.path.insert(0, "/app")
from app.db import pool
from app import db, prices

NASDAQ100 = {
"NVDA":"Nvidia Corp","AAPL":"Apple Inc.","MSFT":"Microsoft Corp","AMZN":"Amazon.Com Inc",
"GOOGL":"Alphabet Inc. Class A","GOOG":"Alphabet Inc. Class C","SPCX":"Space Exploration Technologies Corp",
"META":"Meta Platforms Inc.","AVGO":"Broadcom Inc.","TSLA":"Tesla Inc.","MU":"Micron Technology Inc.",
"AMD":"Advanced Micro Devices","WMT":"Walmart Inc.","ASML":"ASML Holding NV","INTC":"Intel Corp",
"PLTR":"Palantir Technologies Inc.","CSCO":"Cisco Systems Inc.","COST":"Costco Wholesale Corp",
"LRCX":"Lam Research Corp","AMAT":"Applied Materials Inc","ARM":"Arm Holdings plc","PANW":"Palo Alto Networks Inc.",
"NFLX":"Netflix Inc","SNDK":"Sandisk Corp","CRWD":"CrowdStrike Holdings Inc.","TXN":"Texas Instruments Inc.",
"KLAC":"KLA Corp","MRVL":"Marvell Technology Inc.","AMGN":"Amgen Inc","LIN":"Linde plc","QCOM":"Qualcomm Inc",
"STX":"Seagate Technology Holdings PLC","ADI":"Analog Devices Inc.","GILD":"Gilead Sciences Inc",
"SHOP":"Shopify Inc.","TMUS":"T-Mobile US Inc.","PEP":"PepsiCo Inc.","WDC":"Western Digital Corp.",
"ISRG":"Intuitive Surgical Inc.","VRTX":"Vertex Pharmaceuticals Inc","FTNT":"Fortinet Inc.",
"BKNG":"Booking Holdings Inc.","PDD":"PDD Holdings Inc.","SBUX":"Starbucks Corp","ADP":"Automatic Data Processing",
"APP":"Applovin Corp","DDOG":"Datadog Inc.","ADBE":"Adobe Inc.","CEG":"Constellation Energy Corp",
"ABNB":"Airbnb Inc.","MAR":"Marriott International","CDNS":"Cadence Design Systems","MELI":"MercadoLibre Inc",
"CSX":"CSX Corp","LITE":"Lumentum Holdings Inc.","MNST":"Monster Beverage Corp","DASH":"DoorDash Inc.",
"SNPS":"Synopsys Inc","REGN":"Regeneron Pharmaceuticals Inc","CTAS":"Cintas Corp","CMCSA":"Comcast Corp",
"WBD":"Warner Bros. Discovery Inc.","MDLZ":"Mondelez International Inc.","ROST":"Ross Stores Inc",
"INTU":"Intuit Inc","ORLY":"O'Reilly Automotive Inc.","HON":"Honeywell International Inc.",
"MPWR":"Monolithic Power Systems Inc.","NBIS":"Nebius Group N.V.","AEP":"American Electric Power Co Inc.",
"ALAB":"Astera Labs Inc.","MSTR":"Strategy Inc","TER":"Teradyne Inc.","NXPI":"NXP Semiconductors N.V.",
"PCAR":"Paccar Inc","FAST":"Fastenal Co","BKR":"Baker Hughes Co","FANG":"Diamondback Energy Inc.",
"HONA":"Honeywell Aerospace Inc.","CRWV":"CoreWeave Inc.","RKLB":"Rocket Lab Corp","PYPL":"PayPal Holdings Inc.",
"WDAY":"Workday Inc.","CCEP":"Coca-Cola Europacific Partners plc","ADSK":"Autodesk Inc","XEL":"Xcel Energy Inc.",
"KDP":"Keurig Dr Pepper Inc.","TRI":"Thomson Reuters Corp","MCHP":"Microchip Technology Inc",
"EXC":"Exelon Corp","IDXX":"Idexx Laboratories Inc","FER":"Ferrovial N.V.","TTWO":"Take-Two Interactive Software Inc",
"PAYX":"Paychex Inc","ODFL":"Old Dominion Freight Line","ROP":"Roper Technologies Inc.","AXON":"Axon Enterprise Inc.",
"ALNY":"Alnylam Pharmaceuticals Inc.","DXCM":"DexCom Inc.","GEHC":"GE HealthCare Technologies Inc.",
"CPRT":"Copart Inc",
}

pool_ = pool
pool_.open()
with pool_.connection() as conn:
    with conn.cursor() as cur:
        for sym, name in NASDAQ100.items():
            cur.execute(
                """INSERT INTO tickers (symbol, name, exchange)
                   VALUES (%s, %s, 'NASDAQ')
                   ON CONFLICT (symbol) DO UPDATE SET name = EXCLUDED.name""",
                (sym, name),
            )
        conn.commit()
        cur.execute("SELECT count(*) FROM tickers")
        print("tickers table now has", cur.fetchone()["count"], "rows")

        cur.execute("SELECT DISTINCT symbol FROM stock_prices")
        have_prices = {r["symbol"] for r in cur.fetchall()}

missing = [s for s in NASDAQ100 if s not in have_prices]
print(f"{len(missing)} symbols missing price history, backfilling (rate-limited)...")

ok, failed = 0, []
for i, sym in enumerate(missing):
    try:
        rows = prices.fetch_prices(sym, days=90)
        if not rows:
            failed.append(sym)
            continue
        n = db.upsert_prices(sym, rows)
        ok += 1
        if (i + 1) % 10 == 0:
            print(f"  ...{i+1}/{len(missing)} done")
    except Exception as e:
        failed.append(sym)
        print(f"  FAILED {sym}: {e}")

print(f"Backfill done: {ok} ok, {len(failed)} failed: {failed}")
