-- Migration 048: Durable Memory Forest
-- Issue #1117 — append-only memory leaf store with evidence provenance chains.
-- Supports pgvector for semantic retrieval; HNSW index commented out for late-build.

BEGIN;

-- Core leaf table (append-only; superseded leaves are kept with new evidence_class row)
CREATE TABLE IF NOT EXISTS memory_forest_leaves (
    id                      BIGSERIAL PRIMARY KEY,
    leaf_id                 TEXT        NOT NULL UNIQUE,
    schema_version          TEXT        NOT NULL,
    owner                   TEXT        NOT NULL,
    repo                    TEXT        NOT NULL,
    source_class            TEXT        NOT NULL,
    evidence_class          TEXT        NOT NULL,
    content_hash            CHAR(64)    NOT NULL,
    content_summary         TEXT        NOT NULL,
    revision                CHAR(40),
    predecessor_leaf_id     TEXT,
    predecessor_hash        TEXT,
    provenance_hash         TEXT        NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Semantic embedding store (late-build — embedding backfill applied separately)
CREATE TABLE IF NOT EXISTS memory_forest_embeddings (
    id              BIGSERIAL PRIMARY KEY,
    leaf_id         TEXT        NOT NULL REFERENCES memory_forest_leaves(leaf_id) ON DELETE CASCADE,
    embedding       vector(1536),
    model_id        TEXT        NOT NULL DEFAULT 'text-embedding-3-small',
    embedded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- HNSW index (activate when pgvector ≥ 0.5 confirmed in production):
-- CREATE INDEX IF NOT EXISTS idx_mfl_embedding_hnsw
--     ON memory_forest_embeddings USING hnsw (embedding vector_cosine_ops)
--     WITH (m = 16, ef_construction = 64);

-- Conflict log: tracks content hash conflicts across evidence classes
CREATE TABLE IF NOT EXISTS memory_forest_conflicts (
    id              BIGSERIAL PRIMARY KEY,
    content_hash    CHAR(64)    NOT NULL,
    leaf_ids        TEXT[]      NOT NULL,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_mfl_owner_repo
    ON memory_forest_leaves (owner, repo);

CREATE INDEX IF NOT EXISTS idx_mfl_evidence_class
    ON memory_forest_leaves (evidence_class);

CREATE INDEX IF NOT EXISTS idx_mfl_revision
    ON memory_forest_leaves (revision);

CREATE INDEX IF NOT EXISTS idx_mfl_content_hash
    ON memory_forest_leaves (content_hash);

CREATE INDEX IF NOT EXISTS idx_mfl_predecessor
    ON memory_forest_leaves (predecessor_leaf_id);

-- Row-level security
ALTER TABLE memory_forest_leaves ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_forest_embeddings ENABLE ROW LEVEL SECURITY;

COMMIT;
