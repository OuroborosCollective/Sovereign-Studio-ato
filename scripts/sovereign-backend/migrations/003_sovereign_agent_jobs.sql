-- =============================================================================
-- Migration: sovereign_agent_jobs neutral runtime tables
-- Purpose: own Sovereign agent job truth without OpenHands-first coupling
-- Issue: #572 Runtime: define Sovereign Agent Job contract
-- =============================================================================
-- Safe to run repeatedly on the Postgres instance:
--   psql -h <host> -U <user> -d <db> -f 003_sovereign_agent_jobs.sql
-- =============================================================================

BEGIN;

-- =============================================================================
-- sovereign_agent_jobs: neutral job truth for all code-capable executors
-- =============================================================================
CREATE TABLE IF NOT EXISTS sovereign_agent_jobs (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID        NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,

    -- Job identity
    job_id              TEXT        UNIQUE NOT NULL,
    executor            TEXT        NOT NULL,

    -- Runtime input
    repo_url            TEXT        NOT NULL,
    branch              TEXT        NOT NULL DEFAULT 'main',
    mission             TEXT        NOT NULL,
    allowed_paths       JSONB       NOT NULL DEFAULT '[]',
    forbidden_paths     JSONB       NOT NULL DEFAULT '[]',
    memory_hints        JSONB       NOT NULL DEFAULT '[]',

    -- Runtime state
    status              TEXT        NOT NULL DEFAULT 'queued',
    workspace_id        TEXT,
    external_ref        TEXT,

    -- Runtime evidence
    changed_files       JSONB       NOT NULL DEFAULT '[]',
    diff_summary        TEXT,
    test_summary        TEXT,
    draft_pr_url        TEXT,
    blocker             TEXT,
    events              JSONB       NOT NULL DEFAULT '[]',

    -- Safety contract
    draft_pr_only       BOOLEAN     NOT NULL DEFAULT TRUE,
    allow_auto_merge    BOOLEAN     NOT NULL DEFAULT FALSE,

    -- Timestamps
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT sovereign_agent_jobs_status_check CHECK (
        status IN (
            'queued',
            'provisioning',
            'running',
            'waiting-for-user',
            'validating',
            'completed',
            'failed',
            'blocked',
            'cleaned'
        )
    ),
    CONSTRAINT sovereign_agent_jobs_executor_check CHECK (
        executor IN (
            'sovereign-local-runner',
            'openhands-compat-adapter',
            'external-code-agent'
        )
    ),
    CONSTRAINT sovereign_agent_jobs_draft_only_check CHECK (draft_pr_only IS TRUE),
    CONSTRAINT sovereign_agent_jobs_no_auto_merge_check CHECK (allow_auto_merge IS FALSE),
    CONSTRAINT sovereign_agent_jobs_terminal_evidence_check CHECK (
        status <> 'completed'
        OR draft_pr_url IS NOT NULL
        OR diff_summary IS NOT NULL
        OR test_summary IS NOT NULL
        OR jsonb_array_length(changed_files) > 0
    ),
    CONSTRAINT sovereign_agent_jobs_blocker_reason_check CHECK (
        status NOT IN ('failed', 'blocked')
        OR blocker IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_sovereign_agent_jobs_user_id ON sovereign_agent_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_sovereign_agent_jobs_status ON sovereign_agent_jobs(status);
CREATE INDEX IF NOT EXISTS idx_sovereign_agent_jobs_executor ON sovereign_agent_jobs(executor);
CREATE INDEX IF NOT EXISTS idx_sovereign_agent_jobs_created_at ON sovereign_agent_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sovereign_agent_jobs_workspace_id ON sovereign_agent_jobs(workspace_id);

COMMENT ON TABLE sovereign_agent_jobs IS 'Neutral Sovereign agent job truth. OpenHands is an adapter, not the state source.';
COMMENT ON COLUMN sovereign_agent_jobs.external_ref IS 'Optional executor-specific reference, such as OpenHands conversation id. Never used as the primary truth id.';
COMMENT ON COLUMN sovereign_agent_jobs.events IS 'Sanitized runtime events only. No tokens, secrets, raw auth headers, or unfiltered logs.';

-- =============================================================================
-- sovereign_agent_events: optional append-only event evidence table
-- =============================================================================
CREATE TABLE IF NOT EXISTS sovereign_agent_events (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id              TEXT        NOT NULL REFERENCES sovereign_agent_jobs(job_id) ON DELETE CASCADE,
    stage               TEXT        NOT NULL,
    level               TEXT        NOT NULL DEFAULT 'info',
    message             TEXT        NOT NULL,
    payload             JSONB       NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT sovereign_agent_events_level_check CHECK (
        level IN ('info', 'warning', 'error', 'success')
    )
);

CREATE INDEX IF NOT EXISTS idx_sovereign_agent_events_job_id ON sovereign_agent_events(job_id);
CREATE INDEX IF NOT EXISTS idx_sovereign_agent_events_created_at ON sovereign_agent_events(created_at DESC);

COMMENT ON TABLE sovereign_agent_events IS 'Append-only sanitized evidence events for Sovereign agent jobs.';

-- =============================================================================
-- Timestamp trigger
-- =============================================================================
CREATE OR REPLACE FUNCTION update_sovereign_agent_job_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    IF NEW.status IN ('completed', 'failed', 'blocked', 'cleaned') AND NEW.completed_at IS NULL THEN
        NEW.completed_at = NOW();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_sovereign_agent_job_timestamp ON sovereign_agent_jobs;
CREATE TRIGGER trigger_update_sovereign_agent_job_timestamp
    BEFORE UPDATE ON sovereign_agent_jobs
    FOR EACH ROW EXECUTE FUNCTION update_sovereign_agent_job_timestamp();

COMMIT;

-- =============================================================================
-- Verification queries
-- =============================================================================

-- SELECT 'sovereign_agent_jobs' AS table_name, COUNT(*) AS count FROM sovereign_agent_jobs;
-- SELECT 'sovereign_agent_events' AS table_name, COUNT(*) AS count FROM sovereign_agent_events;
