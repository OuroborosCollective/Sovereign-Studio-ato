-- Candidate-only discovery store for the autonomous Free Revolver route scanner.
-- Discovered endpoints are never routing-eligible by this migration. Promotion
-- into llm_routes remains a separate evidence-backed operation.
BEGIN;

CREATE TABLE IF NOT EXISTS llm_route_scanner_runtime (
    singleton_id SMALLINT PRIMARY KEY CHECK (singleton_id = 1),
    lease_owner UUID,
    lease_expires_at TIMESTAMPTZ,
    last_started_at TIMESTAMPTZ,
    last_completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO llm_route_scanner_runtime (singleton_id)
VALUES (1)
ON CONFLICT (singleton_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS llm_route_scanner_runs (
    id UUID PRIMARY KEY,
    status TEXT NOT NULL
        CHECK (status IN ('completed', 'failed', 'lease_held')),
    source_count INTEGER NOT NULL DEFAULT 0 CHECK (source_count >= 0),
    source_error_count INTEGER NOT NULL DEFAULT 0 CHECK (source_error_count >= 0),
    candidate_count INTEGER NOT NULL DEFAULT 0 CHECK (candidate_count >= 0),
    canary_passed_count INTEGER NOT NULL DEFAULT 0 CHECK (canary_passed_count >= 0),
    blocked_count INTEGER NOT NULL DEFAULT 0 CHECK (blocked_count >= 0),
    rejected_count INTEGER NOT NULL DEFAULT 0 CHECK (rejected_count >= 0),
    failure_family TEXT,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    CHECK (completed_at >= started_at)
);

CREATE INDEX IF NOT EXISTS idx_llm_route_scanner_runs_started
    ON llm_route_scanner_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS llm_route_scanner_candidates (
    route_url TEXT PRIMARY KEY
        CHECK (char_length(route_url) BETWEEN 12 AND 500),
    route_sha256 TEXT NOT NULL UNIQUE
        CHECK (route_sha256 ~ '^[0-9a-f]{64}$'),
    host TEXT NOT NULL CHECK (char_length(host) BETWEEN 1 AND 253),
    source_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'discovered'
        CHECK (status IN ('discovered', 'canary_passed', 'blocked', 'rejected')),
    canary_confirmation_count INTEGER NOT NULL DEFAULT 0
        CHECK (canary_confirmation_count BETWEEN 0 AND 2),
    last_http_status INTEGER,
    last_failure_family TEXT,
    last_latency_ms INTEGER NOT NULL DEFAULT 0 CHECK (last_latency_ms >= 0),
    last_response_sha256 TEXT
        CHECK (last_response_sha256 IS NULL OR last_response_sha256 ~ '^[0-9a-f]{64}$'),
    routing_eligible BOOLEAN NOT NULL DEFAULT false
        CHECK (routing_eligible = false),
    promoted_source_id UUID,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_checked_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llm_route_scanner_candidates_status
    ON llm_route_scanner_candidates (status, last_checked_at DESC);

DO $$
BEGIN
    IF to_regclass('llm_revolver_provider_sources') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM pg_constraint
           WHERE conname = 'fk_llm_route_scanner_promoted_source'
       ) THEN
        ALTER TABLE llm_route_scanner_candidates
            ADD CONSTRAINT fk_llm_route_scanner_promoted_source
            FOREIGN KEY (promoted_source_id)
            REFERENCES llm_revolver_provider_sources(id) ON DELETE SET NULL;
    END IF;
END $$;

COMMIT;
