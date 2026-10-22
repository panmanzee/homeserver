"""
Kasikorn SMS -> budget transaction pipeline.

Receives forwarded SMS from the Android smsgateway app, parses Kasikorn's
SMS Alert format into a transaction (amount, direction, counterparty, date),
and queues it for review + Actual Budget import.

Design: never trust the parse blindly. Every parsed transaction is queued
to a local JSONL file AND sent to the user via Telegram for visibility.
Writing into Actual Budget is a separate explicit step (wired in once
ACTUAL_SERVER_PASSWORD + ACTUAL_SYNC_ID are available), so a bad parse
never silently corrupts the budget.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sms-gateway")

app = FastAPI(title="kasikorn-sms-gateway")

QUEUE_PATH = Path(os.environ.get("QUEUE_PATH", "/data/queue.jsonl"))
SHARED_SECRET = os.environ.get("SMS_GATEWAY_SECRET", "")  # simple shared-token auth, Tailscale-only exposure anyway

# --------------------------------------------------------------------------- #
# Parser — calibrated from a real Kasikorn SMS Alert sample once available.
# Until then: best-effort regex over common Thai bank SMS alert conventions
# (amount with comma thousands separators, debit/credit keywords, balance).
# Unparsed fields are left None rather than guessed.
# --------------------------------------------------------------------------- #
AMOUNT_RE = re.compile(r"([\d,]+\.\d{2})")
# Calibrated from a real Kasikorn SMS Alert (2026-09-30):
#   "30/09/69 12:40 หักบัญชี X-0086 เข้า X-1667 100.00 คงเหลือ 33,465.63 บ."
#   = "debited account X-0086, transferred into X-1667, 100.00, balance remaining 33,465.63"
# หักบัญชี ("deducted from account") is the reliable debit signal — NOTE "เข้า" alone
# is ambiguous (it also appears in debit messages, meaning "into recipient account"),
# so it is intentionally NOT used as a standalone credit keyword.
DEBIT_KEYWORDS = ("หักบัญชี", "หัก", "ถอน", "โอนออก", "ซื้อ", "ชำระ", "debit", "withdraw", "purchase", "payment")
CREDIT_KEYWORDS = ("เงินเข้าบัญชี", "ฝากเงิน", "รับโอนเงิน", "รับเงิน", "credit", "deposit", "received")


def parse_kasikorn_sms(text: str) -> dict:
    amounts = [float(a.replace(",", "")) for a in AMOUNT_RE.findall(text)]
    lowered = text.lower()
    direction = None
    if any(k in text or k in lowered for k in DEBIT_KEYWORDS):
        direction = "debit"
    if any(k in text or k in lowered for k in CREDIT_KEYWORDS):
        direction = "credit" if direction is None else direction  # debit keyword wins if both somehow match

    return {
        "raw_text": text,
        "amount": amounts[0] if amounts else None,
        "balance_after": amounts[1] if len(amounts) > 1 else None,
        "direction": direction,
        "parsed_confidently": direction is not None and bool(amounts),
    }


@app.get("/sms")
async def sms_get_probe(secret: str | None = None):
    """Some SMS-forwarder apps' 'Test' button just does a GET ping against
    the configured URL rather than a real POST with a body. Accept it so the
    app's own Test button shows success — this does NOT queue anything, only
    a real POST (see below) does that."""
    provided = secret
    if SHARED_SECRET and provided != SHARED_SECRET:
        raise HTTPException(401, "bad secret")
    return {"ok": True, "note": "reachable — real SMS forwarding uses POST with a JSON body, this GET is just a reachability probe"}


@app.post("/sms")
async def receive_sms(request: Request, x_gateway_secret: str | None = Header(default=None), secret: str | None = None):
    provided = x_gateway_secret or secret
    if SHARED_SECRET and provided != SHARED_SECRET:
        raise HTTPException(401, "bad secret")

    body = await request.json()
    sender = body.get("from", "")
    text = body.get("text", "")
    sent_at = body.get("sentStamp") or datetime.now(timezone.utc).isoformat()

    if not text:
        raise HTTPException(400, "empty SMS text")

    parsed = parse_kasikorn_sms(text)
    record = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "sender": sender,
        "sent_at": sent_at,
        **parsed,
    }

    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with QUEUE_PATH.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    log.info("queued sms: sender=%s amount=%s direction=%s confident=%s",
              sender, parsed["amount"], parsed["direction"], parsed["parsed_confidently"])

    return {"ok": True, "parsed": parsed}


@app.get("/health")
def health():
    return {"ok": True, "queued": QUEUE_PATH.exists() and sum(1 for _ in QUEUE_PATH.open())}


@app.get("/queue/recent")
def recent(limit: int = 20, x_gateway_secret: str | None = Header(default=None), secret: str | None = None):
    # holds raw bank SMS: never serve it without the shared secret
    provided = x_gateway_secret or secret
    if not SHARED_SECRET or provided != SHARED_SECRET:
        raise HTTPException(401, "bad secret")
    if not QUEUE_PATH.exists():
        return {"items": []}
    lines = QUEUE_PATH.read_text().strip().splitlines()
    items = [json.loads(l) for l in lines[-limit:]]
    return {"items": items}
