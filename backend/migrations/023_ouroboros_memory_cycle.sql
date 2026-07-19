-- 023_ouroboros_memory_cycle.sql
-- Canonical memory remains PostgreSQL/pgvector. Reference documents become
-- provenance-bound learning candidates, while external vector indexes consume
-- an idempotent outbox instead of becoming a second source of truth.
BEGIN;

ALTER TABLE knowledge_sources
    DROP CONSTRAINT IF EXISTS knowledge_sources_source_type_check;
ALTER TABLE knowledge_sources
    ADD CONSTRAINT knowledge_sources_source_type_check
    CHECK (source_type IN ('github', 'wikipedia', 'pdf', 'document', 'text', 'code', 'markdown'));

CREATE TABLE IF NOT EXISTS knowledge_learning_candidates (
    candidate_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    source_id UUID NOT NULL REFERENCES knowledge_sources(id) ON DELETE CASCADE,
    block_id UUID NOT NULL REFERENCES knowledge_blocks(id) ON DELETE CASCADE,
    memory_kind TEXT NOT NULL DEFAULT 'reference'
        CHECK (memory_kind IN ('reference')),
    status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (status IN ('candidate', 'accepted', 'rejected')),
    content_sha256 CHAR(64) NOT NULL,
    summary TEXT NOT NULL,
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    accepted_evidence JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, source_id, block_id)
);
CREATE INDEX IF NOT EXISTS idx_knowledge_learning_candidates_user_status
    ON knowledge_learning_candidates (user_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_knowledge_learning_candidates_block
    ON knowledge_learning_candidates (block_id);

DO $$
BEGIN
    IF to_regclass('admin_users') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM pg_constraint
           WHERE conname = 'fk_knowledge_learning_candidates_user'
       ) THEN
        ALTER TABLE knowledge_learning_candidates
            ADD CONSTRAINT fk_knowledge_learning_candidates_user
            FOREIGN KEY (user_id) REFERENCES admin_users(id) ON DELETE CASCADE;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS vector_index_outbox (
    outbox_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    entity_type TEXT NOT NULL
        CHECK (entity_type IN ('knowledge_block', 'agent_pattern')),
    entity_id TEXT NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    embedding_model TEXT NOT NULL,
    canonical_store TEXT NOT NULL DEFAULT 'postgres-pgvector'
        CHECK (canonical_store = 'postgres-pgvector'),
    target_index TEXT NOT NULL DEFAULT 'milvus',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'syncing', 'indexed', 'blocked')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    indexed_at TIMESTAMPTZ,
    UNIQUE (target_index, entity_type, entity_id, content_sha256, embedding_model)
);
CREATE INDEX IF NOT EXISTS idx_vector_index_outbox_pending
    ON vector_index_outbox (target_index, status, created_at)
    WHERE status IN ('pending', 'blocked');
CREATE INDEX IF NOT EXISTS idx_vector_index_outbox_user
    ON vector_index_outbox (user_id, created_at DESC);

INSERT INTO schema_migrations (id, name)
VALUES (23, 'ouroboros_memory_cycle')
ON CONFLICT (id) DO NOTHING;

COMMIT;
