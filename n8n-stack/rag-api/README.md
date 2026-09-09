# rag-api — study Q&A over your own PDFs and notes

Ask plain-language questions about your own study material and get a short,
**cited** answer drawn only from the passages that were retrieved — never from
the model's general knowledge. If the material doesn't cover something, the
answer says so instead of guessing.

- **Ingest**: PDFs / `.md` / `.txt` in `corpus/` → text extraction (PyMuPDF for
  PDFs, keeping page numbers) → ~900-char overlapping chunks → Gemini embeddings
  → stored in the `rag` Postgres database (`pgvector`).
- **Retrieve**: hybrid search — pgvector cosine ANN + Postgres full-text
  (`tsvector` / `websearch_to_tsquery`) — fused with Reciprocal Rank Fusion.
- **Answer**: the top-k chunks go to `gemini-3.1-flash-lite` at temperature 0.2
  with a strict "use only these passages, cite `[file p.N]`, refuse if absent"
  system prompt.
- **Serve**: a single self-contained HTML page at `/`, no CDN, no auth. Bound to
  `127.0.0.1:8005` on the host; reachable from the tailnet at
  `https://pan-homeserver.tail9ee4c5.ts.net:8444/` via `tailscale serve`.

## The `corpus/` workflow

```
n8n-stack/rag-api/corpus/          # gitignored — copyrighted study material never leaves the box
├── ccna-official-cert-guide.pdf
├── ospf-deep-dive.pdf
└── my-handwritten-summary.md
```

1. Drop files into `corpus/` (the directory is bind-mounted read-only into the
   container at `/app/corpus`). Subdirectories are scanned recursively.
2. Trigger ingestion:
   ```bash
   cd ~/homeserver/n8n-stack
   KEY=$(grep ^SERVICE_API_KEY= .env | cut -d= -f2-)
   curl -s -XPOST http://127.0.0.1:8005/ingest \
     -H "X-API-Key: $KEY" -H 'content-type: application/json' -d '{}' | python3 -m json.tool
   ```
   Ingestion is **idempotent**: each file is hashed (SHA-256) and skipped if
   unchanged. A changed file is re-chunked and its old chunks replaced. One bad
   file (e.g. a scanned PDF with no extractable text) is reported in `failed[]`
   and does not stop the run. Pass `{"files": ["a.pdf", "b.pdf"]}` to limit the
   run to specific files.
3. Ask questions:
   ```bash
   curl -s http://127.0.0.1:8005/stats | python3 -m json.tool
   curl -s -XPOST http://127.0.0.1:8005/ask -H 'content-type: application/json' \
     -d '{"question":"what are the OSPF LSA types?"}' | python3 -m json.tool
   ```

> **`documents.filename` is UNIQUE on the basename only.** Two files named
> `notes.md` in different `corpus/` subdirectories collide — the second ingested
> silently replaces the first. Give files distinct names.

### Bulk / offline ingest

Runs the same code path without going through the HTTP API — useful for a large
first load:

```bash
docker compose exec rag-api python -m app.ingest            # ingests /app/corpus
docker compose exec rag-api python -m app.ingest /app/corpus/subset
```

## Endpoints

| Method | Path       | Auth              | Purpose |
|--------|------------|-------------------|---------|
| GET    | `/`        | none              | HTML ask page |
| GET    | `/healthz` | none              | DB ping → `{"status":"ok"}` |
| GET    | `/stats`   | none              | `{documents, chunks, last_ingested_at, questions_today}` |
| POST   | `/ask`     | none              | `{"question": "..."}` → `{answer, sources[]}` |
| POST   | `/ingest`  | `X-API-Key` header | (re)ingest `corpus/`; body `{}` or `{"files":[...]}` |

`/ask` is unauthenticated by design (tailnet-only exposure) but rate-limited by
`RAG_MAX_QUESTIONS_PER_DAY`; over the cap it returns a polite message and makes
no LLM call.

## Configuration knobs (`RAG_*` in `n8n-stack/.env`)

Reuses `GEMINI_API_KEY` and `SERVICE_API_KEY` from the shared stack `.env`.

| Variable | Default | What it does |
|----------|---------|--------------|
| `RAG_GEN_MODEL` | `gemini-3.1-flash-lite` | answer-generation model (high free-tier RPD) |
| `RAG_EMBED_MODEL` | `gemini-embedding-001` | embedding model for chunks and queries |
| `RAG_EMBED_DIMS` | `768` | embedding vector dimension (must match the `vector(N)` column) |
| `RAG_EMBED_BATCH` | `64` | chunks embedded per API call during ingest |
| `RAG_GEN_TEMPERATURE` | `0.2` | generation temperature — low, to keep answers grounded |
| `RAG_CHUNK_CHARS` | `900` | target chunk size in characters |
| `RAG_CHUNK_OVERLAP` | `150` | characters of overlap between adjacent chunks |
| `RAG_CANDIDATES` | `20` | rows pulled from *each* of vector and keyword search before fusion |
| `RAG_RETRIEVE_K` | `8` | chunks kept after RRF and sent to the model |
| `RAG_RRF_K0` | `60` | RRF damping constant — higher flattens the rank weighting |
| `RAG_MAX_QUESTIONS_PER_DAY` | `200` | per-day `/ask` cap (free-tier guard) |

Only `RAG_GEN_MODEL`, `RAG_EMBED_MODEL`, and `RAG_MAX_QUESTIONS_PER_DAY` are
wired through `docker-compose.yml`; the rest fall back to their code defaults but
can be added to the compose `environment:` block if you need to tune them.
Changing a retrieval knob (`RAG_CANDIDATES` / `RAG_RETRIEVE_K` / `RAG_RRF_K0`)
takes effect on `docker compose up -d rag-api` — **no rebuild, no re-ingest**.
Changing `RAG_EMBED_MODEL` or `RAG_EMBED_DIMS` requires a full re-ingest so
every chunk is re-embedded consistently.

## Backup / restore

The `rag` database is included in the nightly `pg_dumpall` from
`scripts/backup.sh`, so a normal restore brings back documents, chunks, and
embeddings. If the database is lost and only the SQL dump is unavailable,
nothing is truly gone: put the source files back in `corpus/` and run `/ingest`
— chunks and embeddings are rebuilt from the corpus. The `corpus/` files
themselves are **not** in git (copyright) — keep your own copy.

## Phase 2 (not built)

- Cross-encoder **reranker** between retrieval and generation.
- **Telegram** front-end (ask from your phone).
- **Conversation memory** — follow-up questions that resolve pronouns/context.
- **Classmate sharing** — multi-user corpora with per-user access.
- **OCR** for scanned PDFs (currently reported as `failed`, "no extractable text").
