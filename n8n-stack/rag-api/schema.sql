CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id           bigserial PRIMARY KEY,
    filename     text NOT NULL UNIQUE,
    sha256       text NOT NULL,
    pages        integer NOT NULL,
    chunk_count  integer NOT NULL DEFAULT 0,
    ingested_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id           bigserial PRIMARY KEY,
    document_id  bigint NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page         integer NOT NULL,
    ord          integer NOT NULL,
    text         text NOT NULL,
    embedding    vector(768) NOT NULL,
    tsv          tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
    UNIQUE (document_id, ord)
);

CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_tsv_gin ON chunks USING gin (tsv);

CREATE TABLE IF NOT EXISTS usage (
    day  date PRIMARY KEY,
    n    integer NOT NULL DEFAULT 0
);
