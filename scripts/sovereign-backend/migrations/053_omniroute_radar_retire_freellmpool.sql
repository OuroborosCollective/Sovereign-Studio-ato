-- Retire the private FreeLLMPool proxy from execution while preserving all
-- historical provider/check/receipt evidence, and add a candidate-only
-- OmniRoute radar store. OmniRoute catalog rows are metadata sensors only:
-- routing_eligible is permanently false in this surface.
BEGIN;

DO $retire$
DECLARE
    pool_source_id CONSTANT UUID := 'c79ff468-ee08-5686-97df-756fa58b74f0';
    pool_api_base CONSTANT TEXT := 'http://freellmpool:8080/v1';
BEGIN
    IF to_regclass('llm_revolver_provider_sources') IS NOT NULL THEN
        UPDATE llm_revolver_provider_sources
        SET enabled = false,
            status = 'disabled',
            last_error_code = 'freellmpool_retired_from_execution',
            updated_at = NOW()
        WHERE id = pool_source_id
           OR lower(api_base) = lower(pool_api_base);
    END IF;

    IF to_regclass('llm_revolver_provider_models') IS NOT NULL THEN
        UPDATE llm_revolver_provider_models
        SET enabled = false,
            status = 'disabled',
            last_error_code = 'freellmpool_retired_from_execution',
            updated_at = NOW()
        WHERE source_id = pool_source_id;
    END IF;

    IF to_regclass('llm_routes') IS NOT NULL THEN
        UPDATE llm_routes
        SET disabled = true,
            config = COALESCE(config, '{}'::jsonb) || jsonb_build_object(
                'executionRetired', true,
                'executionRetirementFamily', 'freellmpool_retired_from_execution',
                'executionRetirementMigration', '053'
            ),
            updated_at = NOW()
        WHERE lower(COALESCE(base_url, '')) = lower(pool_api_base)
           OR COALESCE(config->>'revolverProviderSourceId', '') = pool_source_id::text;
    END IF;
END
$retire$;

CREATE TABLE IF NOT EXISTS llm_provider_radar_runs (
    id UUID PRIMARY KEY,
    sensor_id TEXT NOT NULL CHECK (char_length(sensor_id) BETWEEN 1 AND 120),
    source_repository TEXT NOT NULL CHECK (char_length(source_repository) BETWEEN 3 AND 240),
    source_ref TEXT NOT NULL CHECK (char_length(source_ref) BETWEEN 1 AND 240),
    source_revision TEXT CHECK (source_revision IS NULL OR source_revision ~ '^[0-9a-f]{40}$'),
    source_path TEXT NOT NULL CHECK (char_length(source_path) BETWEEN 1 AND 500),
    source_blob_sha TEXT CHECK (source_blob_sha IS NULL OR source_blob_sha ~ '^[0-9a-f]{40}$'),
    source_content_sha256 TEXT CHECK (
        source_content_sha256 IS NULL OR source_content_sha256 ~ '^[0-9a-f]{64}$'
    ),
    status TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
    candidate_count INTEGER NOT NULL DEFAULT 0 CHECK (candidate_count >= 0),
    quarantined_count INTEGER NOT NULL DEFAULT 0 CHECK (quarantined_count >= 0),
    blocked_count INTEGER NOT NULL DEFAULT 0 CHECK (blocked_count >= 0),
    rejected_count INTEGER NOT NULL DEFAULT 0 CHECK (rejected_count >= 0),
    failure_family TEXT,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    CHECK (completed_at >= started_at)
);

CREATE INDEX IF NOT EXISTS idx_llm_provider_radar_runs_started
    ON llm_provider_radar_runs (sensor_id, started_at DESC);

CREATE TABLE IF NOT EXISTS llm_provider_radar_candidates (
    candidate_sha256 TEXT PRIMARY KEY CHECK (candidate_sha256 ~ '^[0-9a-f]{64}$'),
    sensor_id TEXT NOT NULL CHECK (char_length(sensor_id) BETWEEN 1 AND 120),
    provider_id TEXT NOT NULL CHECK (char_length(provider_id) BETWEEN 1 AND 120),
    model_id TEXT NOT NULL CHECK (char_length(model_id) BETWEEN 1 AND 300),
    display_name TEXT NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 400),
    pool_key TEXT CHECK (pool_key IS NULL OR char_length(pool_key) BETWEEN 1 AND 180),
    free_type TEXT NOT NULL CHECK (free_type IN (
        'recurring-daily',
        'recurring-monthly',
        'recurring-credit',
        'recurring-uncapped',
        'one-time-initial',
        'keyless',
        'discontinued'
    )),
    tos_verdict TEXT NOT NULL CHECK (tos_verdict IN (
        'ok', 'caution', 'ambiguous', 'avoid', 'unknown'
    )),
    trains_on_prompts BOOLEAN,
    monthly_tokens BIGINT NOT NULL DEFAULT 0 CHECK (monthly_tokens >= 0),
    credit_tokens BIGINT NOT NULL DEFAULT 0 CHECK (credit_tokens >= 0),
    source_revision TEXT NOT NULL CHECK (source_revision ~ '^[0-9a-f]{40}$'),
    source_blob_sha TEXT NOT NULL CHECK (source_blob_sha ~ '^[0-9a-f]{40}$'),
    source_content_sha256 TEXT NOT NULL CHECK (source_content_sha256 ~ '^[0-9a-f]{64}$'),
    source_curated_at DATE,
    status TEXT NOT NULL DEFAULT 'quarantined'
        CHECK (status IN ('quarantined', 'blocked_tos', 'stale')),
    routing_eligible BOOLEAN NOT NULL DEFAULT false CHECK (routing_eligible = false),
    promotion_requires_direct_canary BOOLEAN NOT NULL DEFAULT true
        CHECK (promotion_requires_direct_canary = true),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (sensor_id, provider_id, model_id, pool_key)
);

CREATE INDEX IF NOT EXISTS idx_llm_provider_radar_candidates_status
    ON llm_provider_radar_candidates (sensor_id, status, last_seen_at DESC);

INSERT INTO schema_migrations (id, name)
VALUES (53, 'omniroute_radar_retire_freellmpool')
ON CONFLICT (id) DO NOTHING;

COMMIT;
