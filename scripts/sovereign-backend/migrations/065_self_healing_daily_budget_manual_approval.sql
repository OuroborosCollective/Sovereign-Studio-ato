BEGIN;

ALTER TABLE sovereign_self_healing_authority
    ADD COLUMN IF NOT EXISTS max_auto_repairs_per_day INTEGER NOT NULL DEFAULT 3;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_sovereign_self_healing_max_auto_repairs_per_day'
          AND conrelid = 'sovereign_self_healing_authority'::regclass
    ) THEN
        ALTER TABLE sovereign_self_healing_authority
            ADD CONSTRAINT chk_sovereign_self_healing_max_auto_repairs_per_day
            CHECK (max_auto_repairs_per_day BETWEEN 1 AND 30);
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS sovereign_self_healing_manual_approvals (
    approval_id TEXT PRIMARY KEY
        CHECK (approval_id ~ '^self-heal-manual-[0-9a-f]{24}$'),
    incident_id TEXT NOT NULL
        REFERENCES sovereign_self_healing_incidents(incident_id) ON DELETE CASCADE,
    owner_admin_id UUID NOT NULL
        REFERENCES admin_users(id) ON DELETE CASCADE,
    approval_sha256 CHAR(64) NOT NULL UNIQUE
        CHECK (approval_sha256 ~ '^[0-9a-f]{64}$'),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (expires_at > created_at),
    CHECK (consumed_at IS NULL OR consumed_at >= created_at)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_self_healing_manual_approval_active
    ON sovereign_self_healing_manual_approvals (incident_id)
    WHERE consumed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_self_healing_manual_approval_owner_created
    ON sovereign_self_healing_manual_approvals (owner_admin_id, created_at DESC);

COMMIT;
