-- Migration 001: multi-region investing hub foundation (Phase 1)
-- Safe to re-run.

-- Region + index-membership metadata on tickers (previously US-only implicit)
ALTER TABLE tickers ADD COLUMN IF NOT EXISTS region text NOT NULL DEFAULT 'us'
    CHECK (region IN ('us','eu','jp','cn','th'));
ALTER TABLE tickers ADD COLUMN IF NOT EXISTS sector text;
ALTER TABLE tickers ADD COLUMN IF NOT EXISTS index_membership text; -- e.g. 'sp500', 'ndx100', 'eurostoxx50', 'nikkei225', 'hangseng', 'set50'
ALTER TABLE tickers ADD COLUMN IF NOT EXISTS currency text;
ALTER TABLE tickers ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;

CREATE INDEX IF NOT EXISTS tickers_region_idx ON tickers (region);

-- Region-level index quotes (S&P 500, Euro Stoxx 50, Nikkei 225, Hang Seng, SET)
-- for home-page tiles + region headers. Cheap, ~5-15 min refresh.
CREATE TABLE IF NOT EXISTS index_quotes (
    region        text NOT NULL CHECK (region IN ('us','eu','jp','cn','th')),
    index_symbol  text NOT NULL,   -- Yahoo-style symbol, e.g. ^GSPC
    index_name    text NOT NULL,
    ts            timestamptz NOT NULL DEFAULT now(),
    level         numeric,
    change_pct    numeric,
    is_primary    boolean NOT NULL DEFAULT false,
    PRIMARY KEY (region, index_symbol, ts)
);

CREATE INDEX IF NOT EXISTS index_quotes_region_ts_idx ON index_quotes (region, ts DESC);

-- FX close rates, native currency -> THB (daily).
CREATE TABLE IF NOT EXISTS fx_rates (
    pair text NOT NULL,       -- e.g. 'USDTHB', 'EURTHB', 'JPYTHB', 'HKDTHB'
    date date NOT NULL,
    rate numeric NOT NULL,
    source text NOT NULL DEFAULT 'yfinance',
    fetched_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (pair, date)
);

-- Article <-> region/tech-cluster tagging (existing news_tickers/news_tags stay as-is).
CREATE TABLE IF NOT EXISTS news_regions (
    news_item_id bigint NOT NULL REFERENCES news_items(id) ON DELETE CASCADE,
    region       text NOT NULL CHECK (region IN ('us','eu','jp','cn','th')),
    PRIMARY KEY (news_item_id, region)
);
CREATE INDEX IF NOT EXISTS news_regions_region_idx ON news_regions (region);

CREATE TABLE IF NOT EXISTS news_tech_clusters (
    news_item_id bigint NOT NULL REFERENCES news_items(id) ON DELETE CASCADE,
    cluster      text NOT NULL CHECK (cluster IN ('ai_models_software','chips_semiconductors','cloud_datacenter','policy_export_controls')),
    PRIMARY KEY (news_item_id, cluster)
);

-- Valuation ratio history, used for percentile-vs-own-history in the value score.
CREATE TABLE IF NOT EXISTS valuation_history (
    symbol   text NOT NULL REFERENCES tickers(symbol) ON DELETE CASCADE,
    date     date NOT NULL,
    pe_ttm   numeric,
    ps       numeric,
    ev_ebitda numeric,
    fcf_yield numeric,
    approx   boolean NOT NULL DEFAULT false,  -- true = backfilled/estimated, not a live daily snapshot
    PRIMARY KEY (symbol, date)
);

CREATE TABLE IF NOT EXISTS value_scores (
    symbol             text NOT NULL REFERENCES tickers(symbol) ON DELETE CASCADE,
    date               date NOT NULL,
    score              numeric,          -- 0-100, higher = cheaper
    cheapness_sector   numeric,
    cheapness_history  numeric,
    metrics_used       jsonb,
    reasons            jsonb,
    flags              jsonb,
    PRIMARY KEY (symbol, date)
);
CREATE INDEX IF NOT EXISTS value_scores_date_idx ON value_scores (date DESC);

CREATE TABLE IF NOT EXISTS value_list_daily (
    region text NOT NULL CHECK (region IN ('us','eu','jp','cn','th')),
    date   date NOT NULL,
    symbol text NOT NULL REFERENCES tickers(symbol) ON DELETE CASCADE,
    event  text NOT NULL CHECK (event IN ('in','entered','exited')),
    reason text,
    PRIMARY KEY (region, date, symbol)
);
CREATE INDEX IF NOT EXISTS value_list_daily_region_date_idx ON value_list_daily (region, date DESC);

CREATE TABLE IF NOT EXISTS watchlist (
    symbol     text PRIMARY KEY REFERENCES tickers(symbol) ON DELETE CASCADE,
    added_at   timestamptz NOT NULL DEFAULT now(),
    note       text
);

-- Job run log — n8n workflow executions record start/end/status/counts here
-- so /api/status (the "System status" help-menu panel) can show real freshness.
CREATE TABLE IF NOT EXISTS job_runs (
    id          bigserial PRIMARY KEY,
    job         text NOT NULL,
    started_at  timestamptz NOT NULL,
    finished_at timestamptz,
    status      text NOT NULL CHECK (status IN ('running','ok','error','partial')),
    counts      jsonb,
    errors      jsonb,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS job_runs_job_started_idx ON job_runs (job, started_at DESC);
