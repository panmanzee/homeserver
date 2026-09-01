-- newsfeed-api schema
-- Apply against the dedicated `newsfeed` database (see README bootstrap).
-- Safe to re-run.

CREATE TABLE IF NOT EXISTS feeds (
    id              serial PRIMARY KEY,
    name            text NOT NULL,
    url             text NOT NULL UNIQUE,
    category        text,
    active          boolean NOT NULL DEFAULT true,
    last_fetched_at timestamptz,
    last_status     text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS news_items (
    id             bigserial PRIMARY KEY,
    feed_id        integer NOT NULL REFERENCES feeds(id) ON DELETE CASCADE,
    guid           text NOT NULL,
    url            text NOT NULL,
    title          text NOT NULL,
    author         text,
    summary_rss    text,
    content        text,
    content_source text NOT NULL DEFAULT 'rss_summary'
                   CHECK (content_source IN ('fulltext', 'rss_summary')),
    published_at   timestamptz,
    fetched_at     timestamptz NOT NULL DEFAULT now(),
    lang           text NOT NULL DEFAULT 'en',
    UNIQUE (url),
    UNIQUE (feed_id, guid)
);

-- Added later: timestamp of the Telegram push that included this item (NULL = not sent yet).
ALTER TABLE news_items ADD COLUMN IF NOT EXISTS tg_notified_at timestamptz;

CREATE INDEX IF NOT EXISTS news_items_published_at_idx ON news_items (published_at DESC);
CREATE INDEX IF NOT EXISTS news_items_feed_id_idx ON news_items (feed_id);
CREATE INDEX IF NOT EXISTS news_items_tg_unnotified_idx ON news_items (id) WHERE tg_notified_at IS NULL;

CREATE TABLE IF NOT EXISTS enrichments (
    id                  bigserial PRIMARY KEY,
    news_item_id        bigint NOT NULL UNIQUE REFERENCES news_items(id) ON DELETE CASCADE,
    model               text NOT NULL,
    prompt_version      text NOT NULL,
    summary             text,
    sentiment           text CHECK (sentiment IN ('positive', 'negative', 'neutral')),
    sentiment_rationale text,
    event_type          text,
    raw_response        jsonb,
    input_tokens        integer,
    output_tokens       integer,
    status              text NOT NULL CHECK (status IN ('ok', 'error')),
    error               text,
    created_at          timestamptz NOT NULL DEFAULT now()
);

-- Added later: factual newsworthiness rating from the enrichment step.
ALTER TABLE enrichments ADD COLUMN IF NOT EXISTS importance text
    CHECK (importance IN ('breaking', 'notable', 'routine'));

CREATE INDEX IF NOT EXISTS enrichments_status_idx ON enrichments (status);

CREATE TABLE IF NOT EXISTS tickers (
    symbol             text PRIMARY KEY,
    name               text,
    exchange           text,
    price_symbol       text,  -- symbol as the price provider expects it (default: same as symbol)
    on_watchlist       boolean NOT NULL DEFAULT false,
    watchlist_added_at timestamptz,
    created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS news_tickers (
    news_item_id bigint NOT NULL REFERENCES news_items(id) ON DELETE CASCADE,
    symbol       text NOT NULL REFERENCES tickers(symbol) ON DELETE CASCADE,
    confidence   text,
    PRIMARY KEY (news_item_id, symbol)
);

CREATE INDEX IF NOT EXISTS news_tickers_symbol_idx ON news_tickers (symbol);

CREATE TABLE IF NOT EXISTS news_tags (
    news_item_id bigint NOT NULL REFERENCES news_items(id) ON DELETE CASCADE,
    tag          text NOT NULL,
    PRIMARY KEY (news_item_id, tag)
);

CREATE INDEX IF NOT EXISTS news_tags_tag_idx ON news_tags (tag);

CREATE TABLE IF NOT EXISTS stock_prices (
    symbol     text NOT NULL REFERENCES tickers(symbol) ON DELETE CASCADE,
    date       date NOT NULL,
    open       numeric,
    high       numeric,
    low        numeric,
    close      numeric,
    volume     bigint,
    source     text NOT NULL DEFAULT 'twelvedata',
    fetched_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, date)
);

CREATE INDEX IF NOT EXISTS stock_prices_symbol_date_idx ON stock_prices (symbol, date DESC);

-- Dropped + recreated (not CREATE OR REPLACE) so column order can change on upgrade.
DROP VIEW IF EXISTS v_news_enriched;
CREATE VIEW v_news_enriched AS
SELECT
    ni.id,
    ni.url,
    ni.title,
    ni.author,
    f.name        AS feed_name,
    f.category    AS feed_category,
    ni.published_at,
    ni.fetched_at,
    ni.tg_notified_at,
    ni.content_source,
    e.status      AS enrichment_status,
    e.model,
    e.prompt_version,
    e.summary,
    e.sentiment,
    e.sentiment_rationale,
    e.event_type,
    e.importance,
    e.error       AS enrichment_error,
    COALESCE(t.symbols, ARRAY[]::text[]) AS tickers,
    COALESCE(g.tags, ARRAY[]::text[])    AS tags
FROM news_items ni
JOIN feeds f ON f.id = ni.feed_id
LEFT JOIN enrichments e ON e.news_item_id = ni.id
LEFT JOIN LATERAL (
    SELECT array_agg(nt.symbol ORDER BY nt.symbol) AS symbols
    FROM news_tickers nt WHERE nt.news_item_id = ni.id
) t ON true
LEFT JOIN LATERAL (
    SELECT array_agg(ng.tag ORDER BY ng.tag) AS tags
    FROM news_tags ng WHERE ng.news_item_id = ni.id
) g ON true;
