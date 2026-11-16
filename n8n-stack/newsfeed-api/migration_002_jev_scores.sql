-- Migration 002: Jev importance/topic scores per news item.
-- Safe to re-run. Independent of the (quota-limited) Gemini enrichment.
CREATE TABLE IF NOT EXISTS jev_scores (
    news_item_id     bigint PRIMARY KEY REFERENCES news_items(id) ON DELETE CASCADE,
    importance       text,
    confidence       real,
    probabilities    jsonb,
    topic            text,
    topic_confidence real,
    created_at       timestamptz NOT NULL DEFAULT now()
);
