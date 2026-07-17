-- 021_litellm_provider_registry.sql
-- One routing truth: every online model is exposed through private LiteLLM.

CREATE TABLE IF NOT EXISTS llm_provider_deployments (
    deployment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    route_id TEXT NOT NULL UNIQUE,
    provider_name TEXT NOT NULL,
    provider_prefix TEXT NOT NULL,
    upstream_model_id TEXT NOT NULL,
    litellm_model_name TEXT NOT NULL UNIQUE,
    api_base TEXT,
    key_fingerprint CHAR(64),
    key_hint TEXT,
    owner_request_id UUID REFERENCES owner_input_requests(id),
    litellm_deployment_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    last_canary_request_id TEXT,
    last_canary_at TIMESTAMPTZ,
    last_error_code TEXT,
    created_by UUID REFERENCES admin_users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT llm_provider_deployments_status_check
        CHECK (status IN ('pending','awaiting_owner_input','provisioning','ready','blocked','disabled')),
    CONSTRAINT llm_provider_deployments_prefix_check
        CHECK (provider_prefix ~ '^[a-z0-9][a-z0-9_.-]{0,47}$'),
    CONSTRAINT llm_provider_deployments_https_check
        CHECK (api_base IS NULL OR api_base ~ '^https://')
);

CREATE INDEX IF NOT EXISTS idx_llm_provider_deployments_status
    ON llm_provider_deployments (status, updated_at DESC);

-- Legacy direct providers are never a live route after this migration.
UPDATE llm_routes
SET disabled = true,
    config = COALESCE(config, '{}'::jsonb) - 'fallback',
    updated_at = NOW()
WHERE lower(COALESCE(provider, '')) <> 'litellm';

UPDATE llm_routes
SET config = COALESCE(config, '{}'::jsonb) - 'fallback',
    updated_at = NOW()
WHERE lower(COALESCE(provider, '')) = 'litellm';

-- The Sovereign database never owns provider credentials.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'llm_routes'
          AND column_name = 'api_key'
    ) THEN
        EXECUTE 'UPDATE llm_routes SET api_key = NULL WHERE api_key IS NOT NULL';
    END IF;
END $$;

INSERT INTO schema_migrations (id, name)
VALUES (21, 'litellm_provider_registry')
ON CONFLICT (id) DO NOTHING;
