-- Add evidence-based LiteLLM routing and request settlement records.
-- Additive, idempotent and safe to re-run. No existing route or credit row is removed.
BEGIN;

ALTER TABLE llm_routes
    ADD COLUMN IF NOT EXISTS base_url TEXT;

CREATE TABLE IF NOT EXISTS llm_usage_settlements (
    request_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    route_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'created',
        'reserved',
        'settled_usage',
        'settled_estimate',
        'refunded',
        'failed'
    )),
    reserved_credits INTEGER NOT NULL DEFAULT 0 CHECK (reserved_credits >= 0),
    settled_credits INTEGER NOT NULL DEFAULT 0 CHECK (settled_credits >= 0),
    refunded_credits INTEGER NOT NULL DEFAULT 0 CHECK (refunded_credits >= 0),
    estimated_tokens INTEGER NOT NULL DEFAULT 0 CHECK (estimated_tokens >= 0),
    prompt_tokens INTEGER NOT NULL DEFAULT 0 CHECK (prompt_tokens >= 0),
    completion_tokens INTEGER NOT NULL DEFAULT 0 CHECK (completion_tokens >= 0),
    total_tokens INTEGER NOT NULL DEFAULT 0 CHECK (total_tokens >= 0),
    upstream_request_id TEXT,
    provider_cost_usd NUMERIC(18,9),
    fallback_provider TEXT,
    fallback_model_id TEXT,
    error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    settled_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_llm_usage_settlements_user_created
    ON llm_usage_settlements (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_usage_settlements_status
    ON llm_usage_settlements (status, updated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_llm_usage_settlements_upstream_request
    ON llm_usage_settlements (upstream_request_id)
    WHERE upstream_request_id IS NOT NULL AND btrim(upstream_request_id) <> '';

INSERT INTO llm_routes (
    id,
    model_id,
    model_name,
    provider,
    base_url,
    credits_per_unit,
    disabled,
    priority,
    runtime_kind,
    tier,
    config
)
VALUES
    (
        'litellm-sovereign-fast',
        'sovereign-fast',
        'Sovereign Fast',
        'litellm',
        'http://litellm:4000',
        1,
        true,
        10,
        'litellm',
        'fast',
        '{"alias":"sovereign-fast","fallback":"cloudflare"}'::jsonb
    ),
    (
        'litellm-sovereign-balanced',
        'sovereign-balanced',
        'Sovereign Balanced',
        'litellm',
        'http://litellm:4000',
        2,
        true,
        30,
        'litellm',
        'balanced',
        '{"alias":"sovereign-balanced","fallback":"cloudflare"}'::jsonb
    )
ON CONFLICT (model_id) DO UPDATE SET
    id = EXCLUDED.id,
    model_name = EXCLUDED.model_name,
    provider = EXCLUDED.provider,
    base_url = EXCLUDED.base_url,
    credits_per_unit = EXCLUDED.credits_per_unit,
    runtime_kind = EXCLUDED.runtime_kind,
    tier = EXCLUDED.tier,
    config = COALESCE(llm_routes.config, '{}'::jsonb) || EXCLUDED.config,
    disabled = true,
    updated_at = NOW();

COMMIT;
