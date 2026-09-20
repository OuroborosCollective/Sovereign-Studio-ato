BEGIN;

CREATE TABLE IF NOT EXISTS sovereign_self_healing_authority (
    owner_admin_id UUID PRIMARY KEY REFERENCES admin_users(id) ON DELETE CASCADE,
    schema_version TEXT NOT NULL
        CHECK (schema_version = 'sovereign.cag-self-healing-authority.v1'),
    mode TEXT NOT NULL
        CHECK (mode IN ('OBSERVE_ONLY','ASK_FIRST','AUTO_SAFE','AUTO_BOUNDED_CODE_REPAIR')),
    allowed_failure_families JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(allowed_failure_families) = 'array'),
    max_auto_repairs_per_hour INTEGER NOT NULL DEFAULT 1
        CHECK (max_auto_repairs_per_hour BETWEEN 1 AND 10),
    max_changed_files INTEGER NOT NULL DEFAULT 8
        CHECK (max_changed_files BETWEEN 1 AND 50),
    expires_at TIMESTAMPTZ NOT NULL,
    paused BOOLEAN NOT NULL DEFAULT FALSE,
    grant_sha256 CHAR(64) NOT NULL
        CHECK (grant_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS sovereign_self_healing_incidents (
    incident_id TEXT PRIMARY KEY
        CHECK (incident_id ~ '^self-heal-[0-9a-f]{24}$'),
    schema_version TEXT NOT NULL
        CHECK (schema_version = 'sovereign.cag-self-healing.v1'),
    source_job_id TEXT NOT NULL,
    source_user_id UUID NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    failure_family TEXT NOT NULL
        CHECK (failure_family IN (
            'EXECUTOR_MISMATCH',
            'ENDPOINT_ROUTE_MISMATCH',
            'HANDOFF_TIMEOUT_WITH_READBACK',
            'JOB_STATE_TRANSITION_VIOLATION',
            'BILLING_ROUTE_MISMATCH'
        )),
    observation_sha256 CHAR(64) NOT NULL
        CHECK (observation_sha256 ~ '^[0-9a-f]{64}$'),
    observation JSONB NOT NULL,
    cag_request_sha256 CHAR(64)
        CHECK (cag_request_sha256 IS NULL OR cag_request_sha256 ~ '^[0-9a-f]{64}$'),
    cag_response_sha256 CHAR(64)
        CHECK (cag_response_sha256 IS NULL OR cag_response_sha256 ~ '^[0-9a-f]{64}$'),
    cag_result_sha256 CHAR(64)
        CHECK (cag_result_sha256 IS NULL OR cag_result_sha256 ~ '^[0-9a-f]{64}$'),
    cag_verified BOOLEAN NOT NULL DEFAULT FALSE,
    repair_contract_sha256 CHAR(64)
        CHECK (repair_contract_sha256 IS NULL OR repair_contract_sha256 ~ '^[0-9a-f]{64}$'),
    repair_contract JSONB,
    authority_owner_admin_id UUID REFERENCES admin_users(id) ON DELETE SET NULL,
    repair_job_id TEXT,
    status TEXT NOT NULL
        CHECK (status IN (
            'DETECTED',
            'CAG_VERIFYING',
            'CAG_VERIFIED',
            'WAITING_FOR_AUTHORITY',
            'REPAIR_CLAIMED',
            'READBACK_RECOVERED',
            'REPAIR_STARTED',
            'REPAIR_BLOCKED',
            'RESOLVED',
            'FAILED'
        )),
    blocker TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    UNIQUE (source_job_id, failure_family, observation_sha256)
);

CREATE INDEX IF NOT EXISTS idx_self_healing_incidents_status_created
    ON sovereign_self_healing_incidents (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_self_healing_incidents_source_job
    ON sovereign_self_healing_incidents (source_job_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_self_healing_incidents_repair_job
    ON sovereign_self_healing_incidents (repair_job_id)
    WHERE repair_job_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS sovereign_self_healing_action_receipts (
    receipt_id TEXT PRIMARY KEY
        CHECK (receipt_id ~ '^self-heal-receipt-[0-9a-f]{24}$'),
    incident_id TEXT NOT NULL REFERENCES sovereign_self_healing_incidents(incident_id) ON DELETE CASCADE,
    action_kind TEXT NOT NULL
        CHECK (action_kind IN (
            'DETECTED',
            'CAG_VERIFIED',
            'AUTHORITY_BLOCKED',
            'READBACK_RETRY',
            'READBACK_RECOVERED',
            'REPAIR_JOB_STARTED',
            'REPAIR_BLOCKED',
            'RESOLVED',
            'FAILED'
        )),
    effect_class TEXT NOT NULL
        CHECK (effect_class IN ('read','workspace-write','external-write')),
    receipt_sha256 CHAR(64) NOT NULL UNIQUE
        CHECK (receipt_sha256 ~ '^[0-9a-f]{64}$'),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;
