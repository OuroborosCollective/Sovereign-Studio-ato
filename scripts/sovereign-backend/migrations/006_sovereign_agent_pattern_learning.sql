-- =============================================================================
-- Migration: sovereign agent pattern learning candidates
-- Purpose: persist local Pattern Learning Gateway decisions before any remote sync
-- =============================================================================

BEGIN;

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

CREATE INDEX IF NOT EXISTS idx_sovereign_agent_pattern_candidates_user_id
    ON sovereign_agent_pattern_candidates(user_id);

CREATE INDEX IF NOT EXISTS idx_sovereign_agent_pattern_candidates_job_id
    ON sovereign_agent_pattern_candidates(job_id);

CREATE INDEX IF NOT EXISTS idx_sovereign_agent_pattern_candidates_remote_allowed
    ON sovereign_agent_pattern_candidates(remote_memory_allowed);

COMMENT ON TABLE sovereign_agent_pattern_candidates IS 'Local runtime records for validated pattern learning decisions. Remote Memory may only ingest accepted rows with remote_memory_allowed=true.';

COMMIT;
