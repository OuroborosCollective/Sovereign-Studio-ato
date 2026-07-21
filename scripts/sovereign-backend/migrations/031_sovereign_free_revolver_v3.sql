-- Sovereign Free Revolver v3 control plane.
-- PostgreSQL remains the canonical configuration and evidence source.
BEGIN;

CREATE TABLE IF NOT EXISTS llm_revolver_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    profile_key TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'sequential'
        CHECK (mode IN ('sequential', 'weighted', 'race')),
    race_n INTEGER NOT NULL DEFAULT 3 CHECK (race_n BETWEEN 1 AND 8),
    timeout_ms INTEGER NOT NULL DEFAULT 30000 CHECK (timeout_ms BETWEEN 1000 AND 120000),
    token_budget INTEGER NOT NULL DEFAULT 32000 CHECK (token_budget BETWEEN 128 AND 256000),
    required_capabilities JSONB NOT NULL DEFAULT '["chat"]'::jsonb,
    preferred_route_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    route_weights JSONB NOT NULL DEFAULT '{}'::jsonb,
    structured_repair_attempts INTEGER NOT NULL DEFAULT 1 CHECK (structured_repair_attempts BETWEEN 0 AND 3),
    semantic_cache_enabled BOOLEAN NOT NULL DEFAULT false,
    semantic_cache_threshold_ppm INTEGER NOT NULL DEFAULT 930000
        CHECK (semantic_cache_threshold_ppm BETWEEN 500000 AND 1000000),
    auto_weight_policy TEXT NOT NULL DEFAULT 'recommendation_only'
        CHECK (auto_weight_policy IN ('disabled', 'recommendation_only')),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_llm_revolver_profiles_scope
    ON llm_revolver_profiles (COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid), profile_key);

CREATE TABLE IF NOT EXISTS llm_revolver_schema_contracts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    schema_id TEXT NOT NULL,
    schema_body JSONB NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_llm_revolver_schema_scope
    ON llm_revolver_schema_contracts (COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid), schema_id);

CREATE TABLE IF NOT EXISTS llm_revolver_bandit_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    profile_key TEXT NOT NULL,
    route_id TEXT NOT NULL,
    recommended_weight_ppm INTEGER NOT NULL CHECK (recommended_weight_ppm BETWEEN 0 AND 1000000),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    approved BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_llm_revolver_bandit_pending
    ON llm_revolver_bandit_recommendations (profile_key, created_at DESC)
    WHERE approved=false;

CREATE TABLE IF NOT EXISTS llm_revolver_structured_evidence (
    id BIGSERIAL PRIMARY KEY,
    request_id UUID NOT NULL,
    route_id TEXT NOT NULL,
    schema_id TEXT NOT NULL,
    valid BOOLEAN NOT NULL,
    validation_errors JSONB NOT NULL DEFAULT '[]'::jsonb,
    repair_attempt INTEGER NOT NULL DEFAULT 0 CHECK (repair_attempt BETWEEN 0 AND 3),
    response_sha256 TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (request_id, route_id, schema_id, repair_attempt)
);
CREATE INDEX IF NOT EXISTS idx_llm_revolver_structured_recent
    ON llm_revolver_structured_evidence (observed_at DESC, valid);

CREATE TABLE IF NOT EXISTS llm_semantic_cache_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    capability TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    policy_revision INTEGER NOT NULL,
    knowledge_revision TEXT NOT NULL,
    model_family TEXT NOT NULL,
    schema_id TEXT NOT NULL DEFAULT '',
    response_body JSONB NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (capability IN ('cache_safe'))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_llm_semantic_cache_identity
    ON llm_semantic_cache_entries
       (tenant_id, capability, prompt_hash, policy_revision, knowledge_revision, model_family, schema_id);
CREATE INDEX IF NOT EXISTS idx_llm_semantic_cache_expiry
    ON llm_semantic_cache_entries (expires_at);

INSERT INTO llm_revolver_profiles (tenant_id, profile_key, mode)
VALUES (NULL, 'default-free', 'sequential')
ON CONFLICT DO NOTHING;

COMMIT;
