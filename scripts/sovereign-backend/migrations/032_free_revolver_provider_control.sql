-- Free Revolver provider onboarding, discovery and health evidence.
-- Protected API keys never enter PostgreSQL. They pass once through owner-input
-- and are stored only in the private LiteLLM deployment after verification.
BEGIN;

CREATE TABLE IF NOT EXISTS llm_revolver_provider_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    label TEXT NOT NULL CHECK (char_length(label) BETWEEN 1 AND 120),
    api_base TEXT NOT NULL,
    models_url TEXT,
    auth_mode TEXT NOT NULL DEFAULT 'bearer'
        CHECK (auth_mode IN ('bearer', 'x-api-key', 'none')),
    owner_request_id UUID REFERENCES owner_input_requests(id) ON DELETE SET NULL,
    key_fingerprint TEXT,
    key_hint TEXT,
    status TEXT NOT NULL DEFAULT 'awaiting_owner_input'
        CHECK (status IN ('awaiting_owner_input', 'probing', 'healthy', 'degraded', 'blocked', 'disabled')),
    last_http_status INTEGER,
    last_error_code TEXT,
    last_discovered_at TIMESTAMPTZ,
    last_checked_at TIMESTAMPTZ,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_by UUID REFERENCES admin_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_llm_revolver_provider_api_base
    ON llm_revolver_provider_sources (lower(api_base));
CREATE INDEX IF NOT EXISTS idx_llm_revolver_provider_status
    ON llm_revolver_provider_sources (status, updated_at DESC);

CREATE TABLE IF NOT EXISTS llm_revolver_provider_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES llm_revolver_provider_sources(id) ON DELETE CASCADE,
    upstream_model_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    litellm_alias TEXT,
    capabilities JSONB NOT NULL DEFAULT '["chat"]'::jsonb,
    free_verified BOOLEAN NOT NULL DEFAULT false,
    pricing_source TEXT NOT NULL DEFAULT 'unverified',
    discovery_payload_sha256 TEXT NOT NULL,
    pricing_verified_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'discovered'
        CHECK (status IN ('discovered', 'ready', 'blocked', 'disabled')),
    last_canary_request_id TEXT,
    last_canary_at TIMESTAMPTZ,
    canary_cost_state TEXT NOT NULL DEFAULT 'unreported'
        CHECK (canary_cost_state IN ('zero', 'unreported', 'nonzero')),
    last_provider_cost_usd_micros BIGINT
        CHECK (last_provider_cost_usd_micros IS NULL OR last_provider_cost_usd_micros >= 0),
    last_error_code TEXT,
    enabled BOOLEAN NOT NULL DEFAULT false,
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_id, upstream_model_id)
);
CREATE INDEX IF NOT EXISTS idx_llm_revolver_provider_models_ready
    ON llm_revolver_provider_models (source_id, status, enabled);

CREATE TABLE IF NOT EXISTS llm_revolver_provider_checks (
    id BIGSERIAL PRIMARY KEY,
    source_id UUID NOT NULL REFERENCES llm_revolver_provider_sources(id) ON DELETE CASCADE,
    check_kind TEXT NOT NULL CHECK (check_kind IN ('models_discovery', 'route_canary')),
    models_url TEXT,
    http_status INTEGER,
    outcome TEXT NOT NULL CHECK (outcome IN ('success', 'degraded', 'blocked')),
    model_count INTEGER NOT NULL DEFAULT 0 CHECK (model_count >= 0),
    free_model_count INTEGER NOT NULL DEFAULT 0 CHECK (free_model_count >= 0),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_llm_revolver_provider_checks_recent
    ON llm_revolver_provider_checks (source_id, observed_at DESC);

COMMIT;
