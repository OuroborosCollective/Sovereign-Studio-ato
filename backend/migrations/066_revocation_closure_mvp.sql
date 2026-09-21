-- SRCC MVP: bind repository jobs to canonical durable-workflow permission authority.
BEGIN;

CREATE TABLE IF NOT EXISTS repository_job_permission_bindings (
    job_id TEXT PRIMARY KEY,
    workflow_run_id TEXT NOT NULL,
    permission_id TEXT NOT NULL,
    approved_receipt_hash CHAR(64) NOT NULL,
    binding_hash CHAR(64) NOT NULL UNIQUE,
    canonical_body JSONB NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT repository_job_permission_bindings_hash_check CHECK (
        approved_receipt_hash ~ '^[0-9a-f]{64}$'
        AND binding_hash ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE IF NOT EXISTS workflow_revocation_receipts (
    receipt_hash CHAR(64) PRIMARY KEY,
    workflow_run_id TEXT NOT NULL,
    permission_id TEXT NOT NULL,
    predecessor_receipt_hash CHAR(64) NOT NULL,
    revoked_permission_receipt_hash CHAR(64) NOT NULL,
    revocation_sequence BIGINT NOT NULL,
    revocation_epoch_ms BIGINT NOT NULL,
    decision TEXT NOT NULL,
    progress_head_sha256 CHAR(64),
    canonical_body JSONB NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT workflow_revocation_receipts_hash_check CHECK (
        receipt_hash ~ '^[0-9a-f]{64}$'
        AND predecessor_receipt_hash ~ '^[0-9a-f]{64}$'
        AND revoked_permission_receipt_hash ~ '^[0-9a-f]{64}$'
        AND (progress_head_sha256 IS NULL OR progress_head_sha256 ~ '^[0-9a-f]{64}$')
    ),
    CONSTRAINT workflow_revocation_receipts_decision_check CHECK (
        decision IN ('REVOKED', 'SUPERSEDED')
    )
);

CREATE TABLE IF NOT EXISTS workflow_revocation_closure_receipts (
    receipt_hash CHAR(64) PRIMARY KEY,
    revocation_receipt_hash CHAR(64) NOT NULL,
    workflow_run_id TEXT NOT NULL,
    permission_id TEXT NOT NULL,
    verdict TEXT NOT NULL,
    canonical_body JSONB NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT workflow_revocation_closure_receipts_hash_check CHECK (
        receipt_hash ~ '^[0-9a-f]{64}$'
        AND revocation_receipt_hash ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT workflow_revocation_closure_receipts_verdict_check CHECK (
        verdict IN (
            'REVOCATION_CLOSED_VERIFIED',
            'REVOCATION_PARTIAL',
            'UNVERIFIED',
            'POST_REVOCATION_EFFECT_OBSERVED',
            'CONTRADICTED'
        )
    )
);

CREATE OR REPLACE FUNCTION reject_srcc_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'SRCC evidence is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS reject_repository_job_permission_bindings_update ON repository_job_permission_bindings;
CREATE TRIGGER reject_repository_job_permission_bindings_update
    BEFORE UPDATE ON repository_job_permission_bindings
    FOR EACH ROW EXECUTE FUNCTION reject_srcc_mutation();
DROP TRIGGER IF EXISTS reject_repository_job_permission_bindings_delete ON repository_job_permission_bindings;
CREATE TRIGGER reject_repository_job_permission_bindings_delete
    BEFORE DELETE ON repository_job_permission_bindings
    FOR EACH ROW EXECUTE FUNCTION reject_srcc_mutation();

DROP TRIGGER IF EXISTS reject_workflow_revocation_receipts_update ON workflow_revocation_receipts;
CREATE TRIGGER reject_workflow_revocation_receipts_update
    BEFORE UPDATE ON workflow_revocation_receipts
    FOR EACH ROW EXECUTE FUNCTION reject_srcc_mutation();
DROP TRIGGER IF EXISTS reject_workflow_revocation_receipts_delete ON workflow_revocation_receipts;
CREATE TRIGGER reject_workflow_revocation_receipts_delete
    BEFORE DELETE ON workflow_revocation_receipts
    FOR EACH ROW EXECUTE FUNCTION reject_srcc_mutation();

DROP TRIGGER IF EXISTS reject_workflow_revocation_closure_receipts_update ON workflow_revocation_closure_receipts;
CREATE TRIGGER reject_workflow_revocation_closure_receipts_update
    BEFORE UPDATE ON workflow_revocation_closure_receipts
    FOR EACH ROW EXECUTE FUNCTION reject_srcc_mutation();
DROP TRIGGER IF EXISTS reject_workflow_revocation_closure_receipts_delete ON workflow_revocation_closure_receipts;
CREATE TRIGGER reject_workflow_revocation_closure_receipts_delete
    BEFORE DELETE ON workflow_revocation_closure_receipts
    FOR EACH ROW EXECUTE FUNCTION reject_srcc_mutation();

COMMIT;
