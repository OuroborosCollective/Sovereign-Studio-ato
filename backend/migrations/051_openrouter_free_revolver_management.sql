-- OpenRouter Free-Revolver key lifecycle metadata.
-- Raw management and execution keys remain 0600 owner-managed files.

CREATE TABLE IF NOT EXISTS openrouter_managed_execution_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    purpose TEXT NOT NULL CHECK (purpose IN ('free-revolver')),
    upstream_key_hash TEXT NOT NULL UNIQUE
        CHECK (upstream_key_hash ~ '^[0-9a-f]{64}$'),
    key_fingerprint_sha256 TEXT NOT NULL
        CHECK (key_fingerprint_sha256 ~ '^[0-9a-f]{64}$'),
    key_name TEXT NOT NULL CHECK (length(key_name) BETWEEN 1 AND 160),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','retired','retirement_pending','failed')),
    route_id UUID NULL REFERENCES llm_routes(id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activated_at TIMESTAMPTZ NULL,
    last_verified_at TIMESTAMPTZ NULL,
    retired_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS openrouter_managed_execution_keys_one_active
    ON openrouter_managed_execution_keys (purpose)
    WHERE status='active';

CREATE INDEX IF NOT EXISTS openrouter_managed_execution_keys_status_idx
    ON openrouter_managed_execution_keys (status, updated_at DESC);
