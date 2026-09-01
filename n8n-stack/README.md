# Personal news / stock tracker

RSS → Postgres → LLM (factual Thai summary + tickers/tags) → EOD prices →
Telegram digest, orchestrated by the existing n8n instance. Enrichment runs on
Gemini's free tier by default (Claude Haiku optional).

Design doc: [`docs/superpowers/specs/2026-08-29-newsfeed-tracker-design.md`](docs/superpowers/specs/2026-08-29-newsfeed-tracker-design.md)

The AI only condenses information. It does **not** predict prices or give
buy/sell advice.

## Components

| Service | Role |
|---|---|
| `postgres` | data store (existing) — new database `newsfeed` |
| `n8n` | scheduler / orchestrator (existing) — calls the API on a timer |
| `newsfeed-api` | FastAPI service (new) — RSS / LLM enrichment / prices / Telegram push |

## Bootstrap

### 1. Secrets

```bash
cp .env.example .env
# edit .env:
#   GEMINI_API_KEY      - free key from https://aistudio.google.com/apikey (default LLM)
#   SERVICE_API_KEY     - openssl rand -hex 32
#   TWELVEDATA_API_KEY  - free key from https://twelvedata.com/ (800 req/day)
#   TELEGRAM_BOT_TOKEN  - from @BotFather
#   TELEGRAM_CHAT_ID    - see step 5
#   POSTGRES_PASSWORD   - must equal the value your postgres volume was created with
```

### 2. Create the database + schema

```bash
docker compose up -d postgres

docker compose exec postgres psql -U n8n -d n8n -c "CREATE DATABASE newsfeed;"

docker compose exec -T postgres psql -U n8n -d newsfeed < newsfeed-api/schema.sql
docker compose exec -T postgres psql -U n8n -d newsfeed < newsfeed-api/seeds/feeds.sql
```

### 3. Build + start the API

```bash
docker compose up -d --build newsfeed-api

curl -s localhost:8001/health           # -> {"status":"ok"}
```

### 4. Add tickers to your watchlist (optional, anytime)

```bash
docker compose exec postgres psql -U n8n -d newsfeed -c \
  "INSERT INTO tickers (symbol, name, price_symbol, on_watchlist, watchlist_added_at)
   VALUES ('AAPL','Apple Inc.','AAPL',true,now())
   ON CONFLICT (symbol) DO UPDATE SET on_watchlist=true, watchlist_added_at=now();"
```

`/prices/refresh` also picks up every ticker Claude tagged in news from the last
7 days automatically. For non-US listings set `price_symbol` to the format your
price provider expects (Twelve Data, e.g. `SAP:XETR`).

### 5. Telegram delivery

1. Create a bot: DM [@BotFather](https://t.me/BotFather), `/newbot`, copy the token
   into `TELEGRAM_BOT_TOKEN`.
2. Send your new bot any message (e.g. "hi") so it can reply to you.
3. Get your chat id and put it in `TELEGRAM_CHAT_ID`:

   ```bash
   curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" \
     | grep -o '"chat":{"id":[0-9-]*' | head -1
   ```
4. `docker compose up -d newsfeed-api` to pick up the new env, then test:

   ```bash
   KEY=$(grep SERVICE_API_KEY .env | cut -d= -f2)
   curl -s -XPOST localhost:8001/notify/digest -H "X-API-Key: $KEY"
   ```

### 6. n8n workflows

The credential (`newsfeed X-API-Key`) and three workflows (**News pipeline**,
**Telegram digest**, **EOD prices**) are imported via the n8n CLI:

```bash
KEY=$(grep SERVICE_API_KEY .env | cut -d= -f2)
printf '[{"id":"newsfeedApiKey01","name":"newsfeed X-API-Key","type":"httpHeaderAuth","data":{"name":"X-API-Key","value":"%s"}}]' "$KEY" > /tmp/creds.json
docker compose cp /tmp/creds.json n8n:/tmp/creds.json
docker compose exec n8n n8n import:credentials --input=/tmp/creds.json

for f in news-pipeline telegram-digest eod-prices; do docker compose cp n8n/workflows/$f.json n8n:/tmp/$f.json; done
docker compose exec n8n n8n import:workflow --separate --input=/tmp/
```

Then in the n8n UI open each workflow and **Activate** it. They reach the API at
`http://newsfeed-api:8000` over the shared Compose network (internal port `8000`,
not the host `8001`).

Schedules: **News pipeline** every 2h (ingest → enrich → push any `breaking`
items now); **Telegram digest** 08:00 & 18:00 (everything not yet pushed);
**EOD prices** daily 18:30.

## API

All endpoints except `/health` require header `X-API-Key: <SERVICE_API_KEY>`.

| Method / path | Body | Purpose |
|---|---|---|
| `GET /health` | — | liveness + DB ping |
| `POST /ingest/rss` | `{"feed_ids":[int]}` optional | fetch active feeds, insert new articles |
| `POST /enrich` | `{"limit":50,"news_ids":[int]}` optional | summarize + tag un-enriched articles via Claude |
| `POST /prices/refresh` | `{"days":7}` optional | pull EOD prices (Twelve Data) for watchlist ∪ recent-news tickers |
| `POST /notify/urgent` | — | push `breaking`-rated items not yet sent (called after `/enrich`) |
| `POST /notify/digest` | — | send one compact Telegram digest of everything not yet pushed |
| `GET /news` | query `since,ticker,tag,limit` | read `v_news_enriched` |

Manual run:

```bash
KEY=$(grep SERVICE_API_KEY .env | cut -d= -f2)
curl -s -XPOST localhost:8001/ingest/rss  -H "X-API-Key: $KEY"
curl -s -XPOST localhost:8001/enrich      -H "X-API-Key: $KEY" -H 'content-type: application/json' -d '{"limit":10}'
curl -s -XPOST localhost:8001/prices/refresh -H "X-API-Key: $KEY"
curl -s "localhost:8001/news?limit=5"     -H "X-API-Key: $KEY" | jq
```

## Data model

`feeds`, `news_items`, `enrichments`, `tickers`, `news_tickers`, `news_tags`,
`stock_prices`, and the `v_news_enriched` view. See `newsfeed-api/schema.sql`
and the design doc §4.

Useful queries:

```sql
-- latest enriched news
SELECT published_at, feed_name, title, sentiment, event_type, tickers, tags
FROM v_news_enriched
WHERE enrichment_status = 'ok'
ORDER BY published_at DESC LIMIT 20;

-- news that failed enrichment (retried automatically on the next /enrich run)
SELECT ni.id, ni.title, e.error
FROM enrichments e JOIN news_items ni ON ni.id = e.news_item_id
WHERE e.status = 'error';

-- price history for a ticker
SELECT date, close, volume FROM stock_prices
WHERE symbol = 'AAPL' ORDER BY date DESC LIMIT 30;

-- fix a wrong price-symbol mapping (Claude guesses the plain name; e.g. XPENG -> XPEV)
UPDATE tickers SET price_symbol = 'XPEV' WHERE symbol = 'XPENG';

-- re-send something to Telegram (clear its "already pushed" mark)
UPDATE news_items SET tg_notified_at = NULL WHERE id = 123;

-- clear a digest backlog: mark everything pending as sent (also stops LLM
-- spend on it, since /enrich only processes items with tg_notified_at IS NULL)
UPDATE news_items SET tg_notified_at = now() WHERE tg_notified_at IS NULL;
```

## Development

```bash
cd newsfeed-api
docker run --rm -v "$PWD":/app -w /app python:3.12-slim \
  bash -c "pip install -q -r requirements-dev.txt && python -m pytest -q"
```

Tests cover the pure logic (feed parsing, Twelve Data / Yahoo response parsing,
symbol normalization, prompt building, Claude-output mapping with the API
stubbed).

## LLM enrichment

Default provider is **Gemini** (`LLM_PROVIDER=gemini`, `gemini-2.0-flash`) —
free tier covers this workload (~$0/month). Get a key at
<https://aistudio.google.com/apikey> and put it in `GEMINI_API_KEY`.

To use Claude instead: set `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`
(≈ $0.006/article → ~$36/mo at 200 articles/day — hence Gemini is default).

`enrich_stale_hours` (default 48) + the n8n `limit` (12/run) bound both cost and
digest freshness: articles older than 48 h that were never enriched are dropped
(marked sent, no LLM call). `enrichments.model` records which model wrote each row.

### Changing the prompt

Edit `SYSTEM_PROMPT` in `newsfeed-api/app/enrich.py`, then bump `PROMPT_VERSION`
in `.env` (currently `v4` — factual summaries in **Thai**; tickers / company
names / financial terms stay in their original form). Old rows keep their
`prompt_version`; re-run `/enrich` with specific `news_ids` to refresh them.

If `breaking` fires too often, tighten the `importance` guidance in
`SYSTEM_PROMPT` — that is the only knob for what bypasses the digest schedule.

Digest volume knobs (env, no code change): `DIGEST_MAX_ITEMS` (default 12),
`DIGEST_BULLETS_PER_ITEM` (default 2). The digest packs into as few Telegram
messages as it can; lower these if it still feels long.
