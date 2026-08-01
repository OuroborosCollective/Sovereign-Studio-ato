-- Migration 048: Durable Memory Forest
-- Issue #1117 — deterministic, append-only memory leaves and derived embeddings.
-- This migration creates the storage contract only. RLS is intentionally enabled
-- without permissive policies until a separately reviewed owner/tenant session
-- contract and persistence adapter exist. No runtime activation is claimed here.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE EXCEPTION 'MIGRATION_048_REQUIRES_PGVECTOR';
    END IF;
END
$$;

CREATE TABLE memory_forest_leaves (
    leaf_id                    TEXT        PRIMARY KEY
        CHECK (leaf_id ~ '^leaf:[0-9a-f]{64}$'),
    schema_version             TEXT        NOT NULL
        CHECK (schema_version = 'sovereign.durable-memory-forest.v1'),
    owner                      TEXT        NOT NULL,
    tenant                     TEXT,
    repo                       TEXT,
    workspace_id               TEXT,
    revision                   CHAR(40)
        CHECK (revision IS NULL OR revision ~ '^[0-9a-f]{40}$'),
    observed_period_start      TEXT,
    observed_period_end        TEXT,
    source_class               TEXT        NOT NULL
        CHECK (source_class IN (
            'continuity', 'repository_readback', 'ci_readback',
            'runtime_readback', 'image_readback', 'deployment_readback',
            'postgres_readback', 'operator_rule', 'procedure',
            'human_reported', 'derived'
        )),
    evidence_class             TEXT        NOT NULL
        CHECK (evidence_class IN (
            'reported', 'observed', 'verified', 'contradicted', 'invalidated'
        )),
    content_hash               CHAR(64)    NOT NULL
        CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    content_summary            TEXT        NOT NULL
        CHECK (octet_length(content_summary) BETWEEN 1 AND 16384),
    validity_rules             TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],
    revalidation_gap_hint      TEXT,
    readback_links             TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],
    evidence_receipt_identity  TEXT,
    predecessor_leaf_id        TEXT REFERENCES memory_forest_leaves(leaf_id) ON DELETE RESTRICT,
    predecessor_hash           CHAR(64)
        CHECK (predecessor_hash IS NULL OR predecessor_hash ~ '^[0-9a-f]{64}$'),
    provenance_hash            CHAR(64)    NOT NULL
        CHECK (provenance_hash ~ '^[0-9a-f]{64}$'),
    CHECK (
        (predecessor_leaf_id IS NULL AND predecessor_hash IS NULL)
        OR (predecessor_leaf_id IS NOT NULL AND predecessor_hash IS NOT NULL)
    ),
    CHECK (
        evidence_class = 'reported'
        OR evidence_receipt_identity IS NOT NULL
    ),
    CHECK (cardinality(validity_rules) <= 16),
    CHECK (cardinality(readback_links) <= 32)
);

COMMENT ON TABLE memory_forest_leaves IS
    'Canonical append-only leaves. UPDATE and DELETE are rejected by trigger.';

CREATE TABLE memory_forest_embeddings (
    leaf_id                 TEXT        NOT NULL
        REFERENCES memory_forest_leaves(leaf_id) ON DELETE RESTRICT,
    model_id                TEXT        NOT NULL,
    embedding_content_hash  CHAR(64)    NOT NULL
        CHECK (embedding_content_hash ~ '^[0-9a-f]{64}$'),
    embedding               vector(1536) NOT NULL,
    PRIMARY KEY (leaf_id, model_id, embedding_content_hash)
);

COMMENT ON TABLE memory_forest_embeddings IS
    'Derived projection. Model identity and content hash are explicit; no implicit clock or provider default.';

CREATE TABLE memory_forest_conflicts (
    conflict_id               TEXT        PRIMARY KEY
        CHECK (conflict_id ~ '^conflict:[0-9a-f]{64}$'),
    owner                     TEXT        NOT NULL,
    tenant                    TEXT,
    repo                      TEXT,
    workspace_id              TEXT,
    content_hash              CHAR(64)    NOT NULL
        CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    leaf_ids                  TEXT[]      NOT NULL
        CHECK (cardinality(leaf_ids) >= 2),
    evidence_receipt_identity TEXT        NOT NULL
);

CREATE OR REPLACE FUNCTION memory_forest_reject_canonical_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'MEMORY_FOREST_APPEND_ONLY_VIOLATION:%:%', TG_TABLE_NAME, TG_OP;
END
$$;

CREATE TRIGGER memory_forest_leaves_append_only
    BEFORE UPDATE OR DELETE ON memory_forest_leaves
    FOR EACH ROW EXECUTE FUNCTION memory_forest_reject_canonical_mutation();

CREATE TRIGGER memory_forest_conflicts_append_only
    BEFORE UPDATE OR DELETE ON memory_forest_conflicts
    FOR EACH ROW EXECUTE FUNCTION memory_forest_reject_canonical_mutation();

CREATE INDEX idx_mfl_scope
    ON memory_forest_leaves (owner, tenant, repo, workspace_id);
CREATE INDEX idx_mfl_evidence_class
    ON memory_forest_leaves (evidence_class);
CREATE INDEX idx_mfl_revision
    ON memory_forest_leaves (revision);
CREATE INDEX idx_mfl_content_hash
    ON memory_forest_leaves (content_hash);
CREATE INDEX idx_mfl_predecessor
    ON memory_forest_leaves (predecessor_leaf_id);
CREATE INDEX idx_mfc_scope_hash
    ON memory_forest_conflicts (owner, tenant, repo, workspace_id, content_hash);

-- Fail closed: policy activation requires a separately verified runtime identity
-- contract. Table owners and superusers retain PostgreSQL-defined bypass behavior.
ALTER TABLE memory_forest_leaves ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_forest_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_forest_conflicts ENABLE ROW LEVEL SECURITY;

COMMIT;
