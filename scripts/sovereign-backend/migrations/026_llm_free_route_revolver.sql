-- Persistent runtime evidence for the price-verified free LLM route revolver.
-- No provider routes or prices are seeded here; all routes remain admin/catalog owned.

CREATE TABLE IF NOT EXISTS llm_route_revolver_state (
    quota_scope TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'ready'
        CHECK (status IN ('ready', 'cooldown', 'blocked')),
    consecutive_failures INTEGER NOT NULL DEFAULT 0
        CHECK (consecutive_failures >= 0),
    cooldown_until TIMESTAMPTZ,
    last_route_id TEXT,
    last_http_status INTEGER,
    last_blocker TEXT,
    last_request_id UUID,
    last_attempt_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (char_length(quota_scope) BETWEEN 8 AND 128)
);

CREATE TABLE IF NOT EXISTS llm_route_attempts (
    id BIGSERIAL PRIMARY KEY,
    request_id UUID NOT NULL,
    attempt_number INTEGER NOT NULL CHECK (attempt_number BETWEEN 1 AND 100),
    route_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    quota_scope TEXT NOT NULL,
    outcome TEXT NOT NULL
        CHECK (outcome IN ('success', 'retryable_failure', 'terminal_failure')),
    http_status INTEGER,
    blocker TEXT,
    upstream_request_id TEXT,
    prompt_tokens INTEGER NOT NULL DEFAULT 0 CHECK (prompt_tokens >= 0),
    completion_tokens INTEGER NOT NULL DEFAULT 0 CHECK (completion_tokens >= 0),
    total_tokens INTEGER NOT NULL DEFAULT 0 CHECK (total_tokens >= 0),
    provider_cost_usd_micros BIGINT
        CHECK (provider_cost_usd_micros IS NULL OR provider_cost_usd_micros >= 0),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (request_id, attempt_number)
);

CREATE INDEX IF NOT EXISTS idx_llm_route_attempts_request
    ON llm_route_attempts (request_id, attempt_number);
CREATE INDEX IF NOT EXISTS idx_llm_route_attempts_scope_recent
    ON llm_route_attempts (quota_scope, completed_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_route_revolver_cooldown
    ON llm_route_revolver_state (status, cooldown_until);
