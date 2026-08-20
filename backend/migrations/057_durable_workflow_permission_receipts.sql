-- Canonical durable workflow, permission and execution receipts for Issue #1113.
-- All mutable progress is derived from append-only receipt sequences; raw parameters,
-- prompts, tool output, secrets and credentials are forbidden from persistence.
BEGIN;

CREATE TABLE IF NOT EXISTS durable_workflow_runs (
    workflow_run_id TEXT PRIMARY KEY,
    workflow_schema_version TEXT NOT NULL,
    workflow_definition_hash CHAR(64) NOT NULL,
    owner_identity TEXT NOT NULL,
    tenant_or_org_identity TEXT NOT NULL,
    repository_identity TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    base_revision CHAR(40) NOT NULL,
    head_revision CHAR(40),
    merge_revision CHAR(40),
    integration_id TEXT,
    issue_number BIGINT,
    pull_request_number BIGINT,
    canonical_body JSONB NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT durable_workflow_runs_schema_check CHECK (
        workflow_schema_version = 'sovereign.durable-workflow.v1'
    ),
    CONSTRAINT durable_workflow_runs_hash_check CHECK (
        workflow_definition_hash ~ '^[0-9a-f]{64}$'
        AND base_revision ~ '^[0-9a-f]{40}$'
        AND (head_revision IS NULL OR head_revision ~ '^[0-9a-f]{40}$')
        AND (merge_revision IS NULL OR merge_revision ~ '^[0-9a-f]{40}$')
    ),
    CONSTRAINT durable_workflow_runs_identity_check CHECK (
        owner_identity <> '' AND tenant_or_org_identity <> ''
        AND repository_identity <> '' AND workspace_id <> ''
    ),
    CONSTRAINT durable_workflow_runs_body_check CHECK (
        jsonb_typeof(canonical_body) = 'object'
        AND canonical_body ->> 'workflow_run_id' = workflow_run_id
        AND canonical_body ->> 'workflow_definition_hash' = workflow_definition_hash
    )
);

CREATE TABLE IF NOT EXISTS workflow_permission_receipts (
    receipt_hash CHAR(64) PRIMARY KEY,
    workflow_run_id TEXT NOT NULL REFERENCES durable_workflow_runs(workflow_run_id) ON DELETE RESTRICT,
    receipt_sequence BIGINT NOT NULL,
    permission_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    capability TEXT NOT NULL,
    parameters_hash CHAR(64) NOT NULL,
    base_revision CHAR(40) NOT NULL,
    valid_until_epoch BIGINT NOT NULL,
    max_attempts INTEGER NOT NULL,
    decision TEXT NOT NULL,
    predecessor_receipt_hash CHAR(64) NOT NULL,
    canonical_body JSONB NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT workflow_permission_receipts_sequence_unique UNIQUE (workflow_run_id, receipt_sequence),
    CONSTRAINT workflow_permission_receipts_permission_unique UNIQUE (permission_id, receipt_hash),
    CONSTRAINT workflow_permission_receipts_schema_check CHECK (
        canonical_body ->> 'schema_version' = 'sovereign.permission-receipt.v1'
    ),
    CONSTRAINT workflow_permission_receipts_hash_check CHECK (
        receipt_hash ~ '^[0-9a-f]{64}$'
        AND parameters_hash ~ '^[0-9a-f]{64}$'
        AND predecessor_receipt_hash ~ '^[0-9a-f]{64}$'
        AND base_revision ~ '^[0-9a-f]{40}$'
    ),
    CONSTRAINT workflow_permission_receipts_decision_check CHECK (
        decision IN ('REQUESTED', 'APPROVED', 'REJECTED', 'EXPIRED', 'REVOKED', 'SUPERSEDED')
    ),
    CONSTRAINT workflow_permission_receipts_body_check CHECK (
        jsonb_typeof(canonical_body) = 'object'
        AND canonical_body ->> 'permission_id' = permission_id
        AND canonical_body ->> 'receipt_hash' = receipt_hash
    )
);

CREATE TABLE IF NOT EXISTS workflow_execution_receipts (
    execution_hash CHAR(64) PRIMARY KEY,
    workflow_run_id TEXT NOT NULL REFERENCES durable_workflow_runs(workflow_run_id) ON DELETE RESTRICT,
    execution_sequence BIGINT NOT NULL,
    execution_id TEXT NOT NULL,
    permission_receipt_hash CHAR(64) NOT NULL REFERENCES workflow_permission_receipts(receipt_hash) ON DELETE RESTRICT,
    step_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    parameters_hash CHAR(64) NOT NULL,
    observed_revision CHAR(40) NOT NULL,
    idempotency_key TEXT NOT NULL,
    output_hash CHAR(64) NOT NULL,
    patch_hash CHAR(64) NOT NULL,
    verdict TEXT NOT NULL,
    readback_hash CHAR(64),
    previous_execution_hash CHAR(64) NOT NULL,
    canonical_body JSONB NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT workflow_execution_receipts_sequence_unique UNIQUE (workflow_run_id, execution_sequence),
    CONSTRAINT workflow_execution_receipts_idempotency_unique UNIQUE (workflow_run_id, idempotency_key, attempt_number),
    CONSTRAINT workflow_execution_receipts_schema_check CHECK (
        canonical_body ->> 'schema_version' = 'sovereign.execution-receipt.v1'
    ),
    CONSTRAINT workflow_execution_receipts_hash_check CHECK (
        execution_hash ~ '^[0-9a-f]{64}$'
        AND permission_receipt_hash ~ '^[0-9a-f]{64}$'
        AND parameters_hash ~ '^[0-9a-f]{64}$'
        AND observed_revision ~ '^[0-9a-f]{40}$'
        AND output_hash ~ '^[0-9a-f]{64}$'
        AND patch_hash ~ '^[0-9a-f]{64}$'
        AND previous_execution_hash ~ '^[0-9a-f]{64}$'
        AND (readback_hash IS NULL OR readback_hash ~ '^[0-9a-f]{64}$')
    ),
    CONSTRAINT workflow_execution_receipts_verdict_check CHECK (
        verdict IN ('SUCCEEDED_UNVERIFIED', 'VERIFIED', 'CONTRADICTED', 'INVALIDATED', 'BLOCKED', 'RETRYABLE_FAILURE')
    ),
    CONSTRAINT workflow_execution_receipts_body_check CHECK (
        jsonb_typeof(canonical_body) = 'object'
        AND canonical_body ->> 'execution_id' = execution_id
        AND canonical_body ->> 'execution_hash' = execution_hash
    )
);

CREATE OR REPLACE FUNCTION reject_durable_workflow_receipt_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'durable workflow receipts are append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS reject_durable_workflow_runs_update ON durable_workflow_runs;
CREATE TRIGGER reject_durable_workflow_runs_update
    BEFORE UPDATE ON durable_workflow_runs
    FOR EACH ROW EXECUTE FUNCTION reject_durable_workflow_receipt_mutation();
DROP TRIGGER IF EXISTS reject_durable_workflow_runs_delete ON durable_workflow_runs;
CREATE TRIGGER reject_durable_workflow_runs_delete
    BEFORE DELETE ON durable_workflow_runs
    FOR EACH ROW EXECUTE FUNCTION reject_durable_workflow_receipt_mutation();

DROP TRIGGER IF EXISTS reject_workflow_permission_receipts_update ON workflow_permission_receipts;
CREATE TRIGGER reject_workflow_permission_receipts_update
    BEFORE UPDATE ON workflow_permission_receipts
    FOR EACH ROW EXECUTE FUNCTION reject_durable_workflow_receipt_mutation();
DROP TRIGGER IF EXISTS reject_workflow_permission_receipts_delete ON workflow_permission_receipts;
CREATE TRIGGER reject_workflow_permission_receipts_delete
    BEFORE DELETE ON workflow_permission_receipts
    FOR EACH ROW EXECUTE FUNCTION reject_durable_workflow_receipt_mutation();

DROP TRIGGER IF EXISTS reject_workflow_execution_receipts_update ON workflow_execution_receipts;
CREATE TRIGGER reject_workflow_execution_receipts_update
    BEFORE UPDATE ON workflow_execution_receipts
    FOR EACH ROW EXECUTE FUNCTION reject_durable_workflow_receipt_mutation();
DROP TRIGGER IF EXISTS reject_workflow_execution_receipts_delete ON workflow_execution_receipts;
CREATE TRIGGER reject_workflow_execution_receipts_delete
    BEFORE DELETE ON workflow_execution_receipts
    FOR EACH ROW EXECUTE FUNCTION reject_durable_workflow_receipt_mutation();

CREATE INDEX IF NOT EXISTS idx_workflow_permission_receipts_run_step
    ON workflow_permission_receipts (workflow_run_id, step_id, receipt_sequence);
CREATE INDEX IF NOT EXISTS idx_workflow_execution_receipts_run_step
    ON workflow_execution_receipts (workflow_run_id, step_id, execution_sequence);

COMMENT ON TABLE durable_workflow_runs IS
    'Immutable revision-bound workflow identity. Progress is derived only from append-only receipts.';
COMMENT ON TABLE workflow_permission_receipts IS
    'Append-only permission decisions bound to exact owner, repository, workspace, revision and payload hashes.';
COMMENT ON TABLE workflow_execution_receipts IS
    'Append-only execution evidence. VERIFIED requires an independent authorized target readback.';

COMMIT;
