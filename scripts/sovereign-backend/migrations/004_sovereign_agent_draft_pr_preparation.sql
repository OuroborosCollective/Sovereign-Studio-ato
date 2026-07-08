-- =============================================================================
-- Migration: sovereign_agent_jobs draft PR preparation state
-- Purpose: persist Draft-PR-ready runtime state without creating a PR or auto-merge
-- =============================================================================

BEGIN;

ALTER TABLE sovereign_agent_jobs
    ADD COLUMN IF NOT EXISTS draft_pr_head_branch TEXT,
    ADD COLUMN IF NOT EXISTS draft_pr_base_branch TEXT,
    ADD COLUMN IF NOT EXISTS draft_pr_title TEXT,
    ADD COLUMN IF NOT EXISTS draft_pr_body TEXT,
    ADD COLUMN IF NOT EXISTS draft_pr_ready BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS draft_pr_ready_at TIMESTAMPTZ;

COMMENT ON COLUMN sovereign_agent_jobs.draft_pr_ready IS 'Runtime-prepared Draft PR state only. This does not mean a PR exists.';
COMMENT ON COLUMN sovereign_agent_jobs.draft_pr_head_branch IS 'Prepared head branch for a future explicit Draft PR create action.';
COMMENT ON COLUMN sovereign_agent_jobs.draft_pr_base_branch IS 'Prepared base branch for a future explicit Draft PR create action.';
COMMENT ON COLUMN sovereign_agent_jobs.draft_pr_title IS 'Prepared Draft PR title generated from validated runtime evidence.';
COMMENT ON COLUMN sovereign_agent_jobs.draft_pr_body IS 'Prepared Draft PR body generated from validated runtime evidence.';

CREATE INDEX IF NOT EXISTS idx_sovereign_agent_jobs_draft_pr_ready ON sovereign_agent_jobs(draft_pr_ready);

COMMIT;
