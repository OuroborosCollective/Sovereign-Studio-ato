-- Sovereign knowledge memory, experience vectors, passkeys and step-up security.
-- Additive, idempotent and rollback-safe. No production data is removed.
BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS knowledge_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('github', 'wikipedia', 'pdf', 'text', 'code')),
    source_url TEXT,
    title TEXT NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing'
        CHECK (status IN ('processing', 'ready', 'partial', 'blocked')),
    content_bytes BIGINT NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    blocker TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, content_sha256)
);
CREATE INDEX IF NOT EXISTS idx_knowledge_sources_user_created
    ON knowledge_sources (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_knowledge_sources_status
    ON knowledge_sources (user_id, status);

CREATE TABLE IF NOT EXISTS knowledge_blocks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    section_title TEXT,
    content TEXT NOT NULL,
    embedding vector(768),
    embedding_model TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, content_sha256)
);
CREATE INDEX IF NOT EXISTS idx_knowledge_blocks_user
    ON knowledge_blocks (user_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_blocks_embedding_hnsw
    ON knowledge_blocks USING hnsw (embedding vector_cosine_ops)
    WHERE embedding IS NOT NULL;

CREATE TABLE IF NOT EXISTS knowledge_source_blocks (
    source_id UUID NOT NULL REFERENCES knowledge_sources(id) ON DELETE CASCADE,
    block_id UUID NOT NULL REFERENCES knowledge_blocks(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    section_title TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (source_id, ordinal),
    UNIQUE (source_id, block_id)
);
CREATE INDEX IF NOT EXISTS idx_knowledge_source_blocks_block
    ON knowledge_source_blocks (block_id);

-- Keep the evidence library and the reference library separate.
CREATE TABLE IF NOT EXISTS sovereign_agent_pattern_candidates (
    candidate_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    job_id TEXT,
    decision TEXT NOT NULL CHECK (decision IN ('accepted', 'blocked')),
    kind TEXT CHECK (kind IN ('solution', 'blocker')),
    summary TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    remote_memory_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    predictive_signal TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sovereign_agent_pattern_vectors (
    candidate_id TEXT PRIMARY KEY
        REFERENCES sovereign_agent_pattern_candidates(candidate_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    pattern_text TEXT NOT NULL,
    embedding vector(768) NOT NULL,
    embedding_model TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pattern_vectors_user
    ON sovereign_agent_pattern_vectors (user_id);
CREATE INDEX IF NOT EXISTS idx_pattern_vectors_embedding_hnsw
    ON sovereign_agent_pattern_vectors USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS user_passkeys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    credential_id BYTEA NOT NULL UNIQUE,
    credential_public_key BYTEA NOT NULL,
    sign_count BIGINT NOT NULL DEFAULT 0,
    transports TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    device_type TEXT,
    backed_up BOOLEAN NOT NULL DEFAULT FALSE,
    label TEXT NOT NULL DEFAULT 'Passkey',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_user_passkeys_user
    ON user_passkeys (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS user_account_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    key_hash CHAR(64) NOT NULL UNIQUE,
    key_hint TEXT NOT NULL,
    label TEXT NOT NULL,
    scopes TEXT[] NOT NULL DEFAULT ARRAY['login', 'step_up']::TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_user_account_keys_user
    ON user_account_keys (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS user_security_policies (
    user_id UUID PRIMARY KEY,
    require_purchase_step_up BOOLEAN NOT NULL DEFAULT FALSE,
    purchase_threshold_eur NUMERIC(10,2) NOT NULL DEFAULT 20.00,
    require_expensive_route_step_up BOOLEAN NOT NULL DEFAULT FALSE,
    route_threshold_credits INTEGER NOT NULL DEFAULT 100,
    prefer_passkey BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS auth_challenges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    purpose TEXT NOT NULL CHECK (purpose IN ('passkey_register', 'passkey_login', 'step_up')),
    challenge BYTEA NOT NULL,
    context_hash CHAR(64),
    context JSONB NOT NULL DEFAULT '{}'::jsonb,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_auth_challenges_expiry
    ON auth_challenges (expires_at) WHERE consumed_at IS NULL;

CREATE TABLE IF NOT EXISTS step_up_approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    action TEXT NOT NULL,
    context_hash CHAR(64) NOT NULL,
    token_hash CHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_step_up_approvals_lookup
    ON step_up_approvals (user_id, action, context_hash, expires_at)
    WHERE consumed_at IS NULL;

CREATE TABLE IF NOT EXISTS llm_routes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id TEXT,
    model_name TEXT,
    provider TEXT NOT NULL DEFAULT 'cloudflare',
    credits_per_unit NUMERIC(12,6) NOT NULL DEFAULT 1,
    disabled BOOLEAN NOT NULL DEFAULT false,
    priority INTEGER NOT NULL DEFAULT 0,
    runtime_kind TEXT NOT NULL DEFAULT 'worker',
    tier TEXT NOT NULL DEFAULT 'smart',
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE llm_routes
    ADD COLUMN IF NOT EXISTS model_id TEXT,
    ADD COLUMN IF NOT EXISTS model_name TEXT,
    ADD COLUMN IF NOT EXISTS credits_per_unit NUMERIC(12,6) NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS disabled BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS runtime_kind TEXT NOT NULL DEFAULT 'worker',
    ADD COLUMN IF NOT EXISTS tier TEXT NOT NULL DEFAULT 'smart',
    ADD COLUMN IF NOT EXISTS config JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema=current_schema() AND table_name='llm_routes' AND column_name='model'
    ) THEN
        EXECUTE 'UPDATE llm_routes SET model_id=COALESCE(model_id, model) WHERE model_id IS NULL';
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema=current_schema() AND table_name='llm_routes' AND column_name='name'
    ) THEN
        EXECUTE 'UPDATE llm_routes SET model_name=COALESCE(model_name, name) WHERE model_name IS NULL';
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema=current_schema() AND table_name='llm_routes' AND column_name='enabled'
    ) THEN
        EXECUTE 'UPDATE llm_routes SET disabled=NOT enabled';
    END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS idx_llm_routes_model_id
    ON llm_routes(model_id) WHERE model_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_llm_routes_active_cost
    ON llm_routes(disabled, priority, credits_per_unit);

DO $$
BEGIN
    IF to_regclass('admin_users') IS NOT NULL THEN
        ALTER TABLE admin_users
            ADD COLUMN IF NOT EXISTS avatar_url TEXT,
            ADD COLUMN IF NOT EXISTS google_id TEXT,
            ADD COLUMN IF NOT EXISTS github_id TEXT,
            ADD COLUMN IF NOT EXISTS github_username TEXT,
            ADD COLUMN IF NOT EXISTS github_access_token TEXT;
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_knowledge_sources_user') THEN
            ALTER TABLE knowledge_sources ADD CONSTRAINT fk_knowledge_sources_user
                FOREIGN KEY (user_id) REFERENCES admin_users(id) ON DELETE CASCADE;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_knowledge_blocks_user') THEN
            ALTER TABLE knowledge_blocks ADD CONSTRAINT fk_knowledge_blocks_user
                FOREIGN KEY (user_id) REFERENCES admin_users(id) ON DELETE CASCADE;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_user_passkeys_user') THEN
            ALTER TABLE user_passkeys ADD CONSTRAINT fk_user_passkeys_user
                FOREIGN KEY (user_id) REFERENCES admin_users(id) ON DELETE CASCADE;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_user_account_keys_user') THEN
            ALTER TABLE user_account_keys ADD CONSTRAINT fk_user_account_keys_user
                FOREIGN KEY (user_id) REFERENCES admin_users(id) ON DELETE CASCADE;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_user_security_policies_user') THEN
            ALTER TABLE user_security_policies ADD CONSTRAINT fk_user_security_policies_user
                FOREIGN KEY (user_id) REFERENCES admin_users(id) ON DELETE CASCADE;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_auth_challenges_user') THEN
            ALTER TABLE auth_challenges ADD CONSTRAINT fk_auth_challenges_user
                FOREIGN KEY (user_id) REFERENCES admin_users(id) ON DELETE CASCADE;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_step_up_approvals_user') THEN
            ALTER TABLE step_up_approvals ADD CONSTRAINT fk_step_up_approvals_user
                FOREIGN KEY (user_id) REFERENCES admin_users(id) ON DELETE CASCADE;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS schema_migrations (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO schema_migrations (id, name)
VALUES (8, 'knowledge_memory_passkeys_stepup')
ON CONFLICT (id) DO NOTHING;

COMMIT;
