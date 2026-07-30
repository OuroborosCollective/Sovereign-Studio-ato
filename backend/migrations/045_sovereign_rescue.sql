BEGIN;

CREATE TABLE IF NOT EXISTS sovereign_rescue_repairs (
    repair_id                 UUID PRIMARY KEY,
    user_id                   UUID NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    job_id                    TEXT NOT NULL,
    run_id                    TEXT,
    idempotency_key           UUID NOT NULL,
    repository                TEXT NOT NULL,
    base_branch               TEXT NOT NULL,
    base_sha                  CHAR(40) NOT NULL,
    failure_family            TEXT NOT NULL,
    repair_pack_id            TEXT NOT NULL,
    outcome_contract_sha256   CHAR(64) NOT NULL,
    entitlement_source        TEXT NOT NULL,
    charged_credits           INTEGER NOT NULL DEFAULT 0 CHECK (charged_credits >= 0),
    published_head_sha        CHAR(40),
    state                     TEXT NOT NULL DEFAULT 'reserved',
    blocker                   TEXT,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT sovereign_rescue_base_sha_check
        CHECK (base_sha ~ '^[0-9a-f]{40}$'),
    CONSTRAINT sovereign_rescue_outcome_sha_check
        CHECK (outcome_contract_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT sovereign_rescue_published_head_sha_check
        CHECK (
            published_head_sha IS NULL
            OR published_head_sha ~ '^[0-9a-f]{40}$'
        ),
    CONSTRAINT sovereign_rescue_family_check
        CHECK (failure_family IN (
            'github_actions_ci',
            'docker_compose_container',
            'postgresql_migration_schema'
        )),
    CONSTRAINT sovereign_rescue_pack_check
        CHECK (repair_pack_id = 'rescue-repair-pack-v1'),
    CONSTRAINT sovereign_rescue_state_check
        CHECK (state IN (
            'reserved',
            'running',
            'blocked',
            'draft_pr_ready',
            'completed',
            'cancelled'
        )),
    UNIQUE (user_id, idempotency_key),
    UNIQUE (job_id)
);

ALTER TABLE sovereign_rescue_repairs
    ADD COLUMN IF NOT EXISTS published_head_sha CHAR(40);

DO $rescue$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'sovereign_rescue_repairs'::regclass
          AND conname = 'sovereign_rescue_published_head_sha_check'
    ) THEN
        ALTER TABLE sovereign_rescue_repairs
            ADD CONSTRAINT sovereign_rescue_published_head_sha_check
            CHECK (
                published_head_sha IS NULL
                OR published_head_sha ~ '^[0-9a-f]{40}$'
            );
    END IF;
END
$rescue$;

CREATE INDEX IF NOT EXISTS idx_sovereign_rescue_user_created
    ON sovereign_rescue_repairs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sovereign_rescue_run
    ON sovereign_rescue_repairs(run_id)
    WHERE run_id IS NOT NULL;

COMMENT ON TABLE sovereign_rescue_repairs IS
    'Server-side Rescue entitlement reservation and exact-revision repair state. '
    'Repository content, credentials, raw logs and model output are not stored here.';

COMMIT;
