-- Migration 046: Bug Evidence Lane
--
-- Implements the revision-bound Bug Evidence Lane schema from Issue #1111.
-- Stores canonical failure-family evidence cases with append-only provenance.
--
-- Design invariants:
-- - status CHECK constraint mirrors BugEvidenceStatus enum
-- - predecessor_case_id FK enables append-only invalidation/supersession chains
-- - log_evidence stored as JSONB (array of redacted strings)
-- - gate_results stored as JSONB (array of {gate, result} objects)
-- - No raw secrets, tokens, PIIs or unbounded logs stored
-- - All TEXT fields that represent SHA-256 are exactly 64 hex chars
-- - schema_version column enables future schema evolution checks
--
-- Rollback procedures are documented separately so production migration
-- classification cannot mistake comment-only examples for executable actions.

BEGIN;

CREATE TABLE IF NOT EXISTS bug_evidence_cases (
    -- Stable primary key (UUID4 string stored as TEXT for portability)
    evidence_case_id        TEXT        PRIMARY KEY,

    -- Schema version for future-proof parsing
    schema_version          TEXT        NOT NULL,

    -- Failure family and canonical normalised signature
    failure_family          TEXT        NOT NULL,
    normalized_signature    TEXT        NOT NULL,
    signature_hash          TEXT        NOT NULL,  -- SHA-256 of normalised_signature

    -- Repository and revision binding (mandatory, fail-closed)
    repo_owner              TEXT        NOT NULL,
    repo_name               TEXT        NOT NULL,
    base_revision           TEXT        NOT NULL,  -- 40-char hex SHA
    head_revision           TEXT        NOT NULL,  -- 40-char hex SHA
    merge_revision          TEXT,                  -- 40-char hex SHA, nullable

    -- CI / workflow identity (nullable; set when available)
    workflow_id             TEXT,
    run_id                  TEXT,
    job_id                  TEXT,
    step_id                 TEXT,

    -- Redacted, bounded log evidence (max 200 lines × 2048 bytes enforced in application)
    log_evidence            JSONB       NOT NULL DEFAULT '[]'::jsonb,
    log_evidence_hash       TEXT        NOT NULL,  -- SHA-256 of canonical list

    -- Affected production surfaces
    affected_surfaces       JSONB       NOT NULL DEFAULT '[]'::jsonb,

    -- Diagnostic tools and immutable params hash
    diagnostic_tools        JSONB       NOT NULL DEFAULT '[]'::jsonb,
    diagnostic_params_hash  TEXT        NOT NULL,  -- SHA-256 of canonical params

    -- Repair tracking (nulls until patched)
    patch_commit            TEXT,                  -- 40-char hex SHA
    tests_run               JSONB       NOT NULL DEFAULT '[]'::jsonb,
    gate_results            JSONB       NOT NULL DEFAULT '[]'::jsonb,

    -- Runtime readbacks (all nullable; filled by external collectors)
    artifact_digest         TEXT,
    revision_label          TEXT,
    patchmon_readback       TEXT,
    container_readback      TEXT,
    postgres_readback       TEXT,
    runtime_readback        TEXT,

    -- Status with strict lifecycle constraint
    status                  TEXT        NOT NULL
                            CHECK (status IN (
                                'candidate',
                                'diagnosed',
                                'patched',
                                'verified',
                                'invalidated'
                            )),

    -- Append-only provenance chain
    provenance_hash             TEXT        NOT NULL,  -- SHA-256 of canonical case fields
    predecessor_case_id         TEXT        REFERENCES bug_evidence_cases(evidence_case_id),
    predecessor_provenance_hash TEXT,

    -- Audit timestamp (set by DB, not application; application must not rely on this for evidence)
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Lookup by canonical signature (cross-case deduplication)
CREATE INDEX IF NOT EXISTS idx_bug_evidence_signature_hash
    ON bug_evidence_cases (signature_hash);

-- Lookup by failure family + repo (primary search path)
CREATE INDEX IF NOT EXISTS idx_bug_evidence_failure_repo
    ON bug_evidence_cases (failure_family, repo_owner, repo_name);

-- Lookup by lifecycle status
CREATE INDEX IF NOT EXISTS idx_bug_evidence_status
    ON bug_evidence_cases (status);

-- Lookup by head revision (revision-compatibility search)
CREATE INDEX IF NOT EXISTS idx_bug_evidence_head_revision
    ON bug_evidence_cases (head_revision);

-- Lookup by provenance hash (chain verification)
CREATE INDEX IF NOT EXISTS idx_bug_evidence_provenance
    ON bug_evidence_cases (provenance_hash);

-- ---------------------------------------------------------------------------
-- pgvector extension for semantic / similarity search over normalised
-- signatures.  Embedding dimension must match the embedding model in use.
-- The embedding is written by the persistence layer, not this migration.
-- ---------------------------------------------------------------------------

-- Ensure pgvector extension is available (installed by migration 008 or later)
-- CREATE EXTENSION IF NOT EXISTS vector;   -- uncomment if not already present

CREATE TABLE IF NOT EXISTS bug_evidence_embeddings (
    -- Links to the primary case; cascade on delete to avoid orphan vectors
    evidence_case_id    TEXT        PRIMARY KEY
                        REFERENCES bug_evidence_cases(evidence_case_id)
                        ON DELETE CASCADE,

    -- Embedding of normalised_signature (dimension set at insert time)
    -- 1536 is the dimension for text-embedding-3-small; adjust as needed.
    embedding           vector(1536),

    -- Cosine HNSW index for fast similarity search
    -- Created separately after first bulk insert to avoid O(n²) build cost.
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- HNSW index — build once after initial data load; skip for empty table.
-- CREATE INDEX IF NOT EXISTS idx_bug_evidence_embedding_hnsw
--     ON bug_evidence_embeddings USING hnsw (embedding vector_cosine_ops);

COMMIT;
