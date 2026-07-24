-- Append-only cryptographic receipts for real Sovereign agent tool calls.
-- Canonical bodies contain identities and digests only. Raw prompts, tool
-- arguments, tool outputs, file contents, database rows and secrets are forbidden.
BEGIN;

CREATE TABLE IF NOT EXISTS agent_run_receipts (
    receipt_sha256 CHAR(64) PRIMARY KEY,
    schema_version TEXT NOT NULL,
    sequence BIGINT NOT NULL,
    repository TEXT NOT NULL,
    base_commit_sha CHAR(40) NOT NULL,
    mcp_revision CHAR(40) NOT NULL,
    mcp_image_digest TEXT NOT NULL,
    mcp_revision_verified BOOLEAN NOT NULL,
    agent_run_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    call_id TEXT NOT NULL,
    operation_identity TEXT NOT NULL,
    input_sha256 CHAR(64) NOT NULL,
    output_sha256 CHAR(64) NOT NULL,
    diff_sha256 CHAR(64) NOT NULL,
    test_evidence_sha256 CHAR(64) NOT NULL,
    evidence_gate_result TEXT NOT NULL,
    mutation_performed BOOLEAN NOT NULL,
    observed_effect TEXT NOT NULL,
    authoritative_readback_sha256 CHAR(64) NOT NULL,
    previous_receipt_sha256 CHAR(64) NOT NULL,
    canonical_body JSONB NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT agent_run_receipts_sequence_unique UNIQUE (agent_run_id, sequence),
    CONSTRAINT agent_run_receipts_call_unique UNIQUE (call_id),
    CONSTRAINT agent_run_receipts_schema_check CHECK (
        schema_version = 'sovereign.agent-run-receipt.v1'
    ),
    CONSTRAINT agent_run_receipts_sha_check CHECK (
        receipt_sha256 ~ '^[0-9a-f]{64}$'
        AND input_sha256 ~ '^[0-9a-f]{64}$'
        AND output_sha256 ~ '^[0-9a-f]{64}$'
        AND diff_sha256 ~ '^[0-9a-f]{64}$'
        AND test_evidence_sha256 ~ '^[0-9a-f]{64}$'
        AND authoritative_readback_sha256 ~ '^[0-9a-f]{64}$'
        AND previous_receipt_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT agent_run_receipts_revision_check CHECK (
        base_commit_sha ~ '^[0-9a-f]{40}$'
        AND mcp_revision ~ '^[0-9a-f]{40}$'
        AND mcp_image_digest ~ '^sha256:[0-9a-f]{64}$'
        AND mcp_revision_verified = TRUE
    ),
    CONSTRAINT agent_run_receipts_gate_check CHECK (
        evidence_gate_result IN ('PASS', 'FAIL', 'BLOCKED')
    ),
    CONSTRAINT agent_run_receipts_effect_check CHECK (
        observed_effect IN ('read', 'workspace-write', 'external-write', 'none')
    ),
    CONSTRAINT agent_run_receipts_identity_check CHECK (
        repository <> '' AND agent_run_id <> '' AND tool_name <> ''
        AND call_id <> '' AND operation_identity <> ''
    ),
    CONSTRAINT agent_run_receipts_body_check CHECK (
        jsonb_typeof(canonical_body) = 'object'
        AND canonical_body ->> 'receipt_sha256' = receipt_sha256
        AND canonical_body ->> 'agent_run_id' = agent_run_id
        AND canonical_body ->> 'call_id' = call_id
        AND canonical_body ->> 'previous_receipt_sha256' = previous_receipt_sha256
    )
);

DO $$
BEGIN
    IF to_regclass('public.agent_runs') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM pg_constraint
           WHERE conname = 'agent_run_receipts_run_fk'
             AND conrelid = 'agent_run_receipts'::regclass
       ) THEN
        ALTER TABLE agent_run_receipts
            ADD CONSTRAINT agent_run_receipts_run_fk
            FOREIGN KEY (agent_run_id) REFERENCES agent_runs(run_id) ON DELETE RESTRICT;
    END IF;
    IF to_regclass('public.agent_tool_calls') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM pg_constraint
           WHERE conname = 'agent_run_receipts_call_fk'
             AND conrelid = 'agent_run_receipts'::regclass
       ) THEN
        ALTER TABLE agent_run_receipts
            ADD CONSTRAINT agent_run_receipts_call_fk
            FOREIGN KEY (call_id) REFERENCES agent_tool_calls(tool_call_id) ON DELETE RESTRICT;
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_agent_run_receipts_run_sequence
    ON agent_run_receipts (agent_run_id, sequence ASC);
CREATE INDEX IF NOT EXISTS idx_agent_run_receipts_repository_revision
    ON agent_run_receipts (repository, base_commit_sha, mcp_revision);

CREATE OR REPLACE FUNCTION reject_agent_run_receipt_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'agent_run_receipts is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_reject_agent_run_receipt_update ON agent_run_receipts;
CREATE TRIGGER trigger_reject_agent_run_receipt_update
    BEFORE UPDATE ON agent_run_receipts
    FOR EACH ROW EXECUTE FUNCTION reject_agent_run_receipt_mutation();

DROP TRIGGER IF EXISTS trigger_reject_agent_run_receipt_delete ON agent_run_receipts;
CREATE TRIGGER trigger_reject_agent_run_receipt_delete
    BEFORE DELETE ON agent_run_receipts
    FOR EACH ROW EXECUTE FUNCTION reject_agent_run_receipt_mutation();

COMMENT ON TABLE agent_run_receipts IS
    'Append-only canonical receipt chain for real agent tool calls. Existing rows cannot be updated or deleted.';

COMMIT;
