-- Embedded Sovereign Universal Toolchain runtime evidence.
-- Additive and idempotent. Stores hashes and bounded diagnostic metadata only;
-- raw logs, secrets, shell commands and GitHub tokens are never persisted here.
BEGIN;

CREATE TABLE IF NOT EXISTS sovereign_toolchain_incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    mission_hash CHAR(64) NOT NULL,
    evidence_hash CHAR(64) NOT NULL,
    primary_family TEXT,
    failure_families JSONB NOT NULL DEFAULT '[]'::jsonb,
    followup_predictions JSONB NOT NULL DEFAULT '[]'::jsonb,
    policy_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (jsonb_typeof(failure_families) = 'array'),
    CHECK (jsonb_typeof(followup_predictions) = 'array'),
    CHECK (jsonb_typeof(policy_snapshot) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_toolchain_incidents_user_created
    ON sovereign_toolchain_incidents (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_toolchain_incidents_family
    ON sovereign_toolchain_incidents (primary_family, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_toolchain_incidents_evidence
    ON sovereign_toolchain_incidents (user_id, evidence_hash);

CREATE TABLE IF NOT EXISTS sovereign_toolchain_handoffs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES sovereign_toolchain_incidents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    job_id TEXT NOT NULL UNIQUE,
    repo_url TEXT NOT NULL,
    branch TEXT NOT NULL DEFAULT 'main',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_toolchain_handoffs_user_created
    ON sovereign_toolchain_handoffs (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_toolchain_handoffs_incident
    ON sovereign_toolchain_handoffs (incident_id);

DO $$
BEGIN
    IF to_regclass('admin_users') IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'fk_toolchain_incidents_user'
        ) THEN
            ALTER TABLE sovereign_toolchain_incidents
                ADD CONSTRAINT fk_toolchain_incidents_user
                FOREIGN KEY (user_id) REFERENCES admin_users(id) ON DELETE CASCADE;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'fk_toolchain_handoffs_user'
        ) THEN
            ALTER TABLE sovereign_toolchain_handoffs
                ADD CONSTRAINT fk_toolchain_handoffs_user
                FOREIGN KEY (user_id) REFERENCES admin_users(id) ON DELETE CASCADE;
        END IF;
    END IF;
END $$;

COMMIT;
