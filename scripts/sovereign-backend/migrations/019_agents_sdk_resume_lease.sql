-- Atomic resume ownership for persistent OpenAI Agents SDK runs.
-- Lease tokens are SHA-256 digests; raw claim tokens are never persisted.
BEGIN;

ALTER TABLE agent_runs
    ADD COLUMN IF NOT EXISTS lease_token CHAR(64),
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS resume_task_id TEXT;

ALTER TABLE agent_runs
    DROP CONSTRAINT IF EXISTS agent_runs_lease_digest_check;
ALTER TABLE agent_runs
    ADD CONSTRAINT agent_runs_lease_digest_check CHECK (
        lease_token IS NULL OR lease_token ~ '^[0-9a-f]{64}$'
    );

ALTER TABLE agent_runs
    DROP CONSTRAINT IF EXISTS agent_runs_lease_pair_check;
ALTER TABLE agent_runs
    ADD CONSTRAINT agent_runs_lease_pair_check CHECK (
        (lease_token IS NULL AND lease_expires_at IS NULL AND resume_task_id IS NULL)
        OR (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL AND resume_task_id IS NOT NULL)
    );

CREATE INDEX IF NOT EXISTS idx_agent_runs_resume_lease
    ON agent_runs (lease_expires_at ASC)
    WHERE lease_token IS NOT NULL;

COMMENT ON COLUMN agent_runs.lease_token IS
    'SHA-256 digest of the transient resume claim token. The raw token is process-local only.';
COMMENT ON COLUMN agent_runs.lease_expires_at IS
    'Expiry gate that makes abandoned RUNNING claims resumable again.';
COMMENT ON COLUMN agent_runs.resume_task_id IS
    'Current bounded recovery task owning the resume lease.';

COMMIT;
