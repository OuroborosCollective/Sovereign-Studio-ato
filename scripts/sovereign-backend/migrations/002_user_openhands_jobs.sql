-- =============================================================================
-- Migration: user_openhands_jobs table
-- Purpose: Track OpenHands jobs per user for the tool section
-- Issue: #517 User-specific OpenHands Integration
-- =============================================================================
-- Safe to run once or repeatedly on the Postgres instance:
--   psql -h <host> -U <user> -d <db> -f 002_user_openhands_jobs.sql
-- =============================================================================

BEGIN;

-- =============================================================================
-- user_openhands_jobs: Track OpenHands execution jobs per user
-- =============================================================================
CREATE TABLE IF NOT EXISTS user_openhands_jobs (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID        NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    
    -- Job identification
    job_id              TEXT        UNIQUE NOT NULL,  -- External OpenHands job ID
    external_conv_id    TEXT,                       -- OpenHands conversation ID
    
    -- Job parameters
    repo_url            TEXT        NOT NULL,
    branch              TEXT        DEFAULT 'main',
    mission             TEXT        NOT NULL,
    
    -- Job status
    status              VARCHAR(50) NOT NULL DEFAULT 'pending',
    -- pending, queued, running, waiting-for-user, blocked, failed, completed
    
    -- Results
    draft_pr_url        TEXT,
    changed_files       JSONB       DEFAULT '[]',
    events              JSONB       DEFAULT '[]',
    last_error          TEXT,
    
    -- Runtime info
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_openhands_jobs_user_id ON user_openhands_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_user_openhands_jobs_status ON user_openhands_jobs(status);
CREATE INDEX IF NOT EXISTS idx_user_openhands_jobs_created_at ON user_openhands_jobs(created_at DESC);

COMMENT ON TABLE user_openhands_jobs IS 'Track OpenHands execution jobs per user - enables individual repository work';

-- =============================================================================
-- Update timestamp on changes
-- =============================================================================
CREATE OR REPLACE FUNCTION update_openhands_job_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    IF NEW.status IN ('completed', 'failed', 'blocked') AND NEW.completed_at IS NULL THEN
        NEW.completed_at = NOW();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_openhands_job_timestamp ON user_openhands_jobs;
CREATE TRIGGER trigger_update_openhands_job_timestamp
    BEFORE UPDATE ON user_openhands_jobs
    FOR EACH ROW EXECUTE FUNCTION update_openhands_job_timestamp();

COMMIT;

-- =============================================================================
-- Verification queries
-- =============================================================================

-- Check migration status:
-- SELECT 'user_openhands_jobs' as table_name, COUNT(*) as count FROM user_openhands_jobs;

-- Check jobs by user:
-- SELECT 
--     au.email,
--     COUNT(*) as total_jobs,
--     SUM(CASE WHEN uoj.status = 'completed' THEN 1 ELSE 0 END) as completed,
--     SUM(CASE WHEN uoj.status = 'running' THEN 1 ELSE 0 END) as running
-- FROM user_openhands_jobs uoj
-- JOIN admin_users au ON au.id = uoj.user_id
-- GROUP BY au.email;
