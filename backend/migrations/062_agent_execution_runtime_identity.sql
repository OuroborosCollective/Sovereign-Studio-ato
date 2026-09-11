-- Separate internal backend Agent Job identity from external ChatGPT MCP identity.
-- Historical v1 rows remain append-only and untouched. New execution receipts
-- store generic runtime identity in dedicated columns and leave legacy MCP fields NULL.
BEGIN;

ALTER TABLE agent_run_receipts
    ADD COLUMN IF NOT EXISTS execution_runtime_kind TEXT,
    ADD COLUMN IF NOT EXISTS execution_revision CHAR(40),
    ADD COLUMN IF NOT EXISTS execution_image_digest TEXT,
    ADD COLUMN IF NOT EXISTS execution_revision_verified BOOLEAN,
    ADD COLUMN IF NOT EXISTS execution_image_digest_verified BOOLEAN;

ALTER TABLE agent_run_receipts
    ALTER COLUMN mcp_revision DROP NOT NULL,
    ALTER COLUMN mcp_image_digest DROP NOT NULL,
    ALTER COLUMN mcp_revision_verified DROP NOT NULL;

ALTER TABLE agent_run_receipts
    DROP CONSTRAINT IF EXISTS agent_run_receipts_schema_check,
    DROP CONSTRAINT IF EXISTS agent_run_receipts_revision_check;

ALTER TABLE agent_run_receipts
    ADD CONSTRAINT agent_run_receipts_schema_check CHECK (
        schema_version IN (
            'sovereign.agent-run-receipt.v1',
            'sovereign.agent-execution-receipt.v1'
        )
    ),
    ADD CONSTRAINT agent_run_receipts_revision_check CHECK (
        base_commit_sha ~ '^[0-9a-f]{40}$'
        AND (
            (
                schema_version = 'sovereign.agent-run-receipt.v1'
                AND mcp_revision ~ '^[0-9a-f]{40}$'
                AND mcp_image_digest ~ '^sha256:[0-9a-f]{64}$'
                AND mcp_revision_verified = TRUE
                AND execution_runtime_kind IS NULL
                AND execution_revision IS NULL
                AND execution_image_digest IS NULL
                AND execution_revision_verified IS NULL
                AND execution_image_digest_verified IS NULL
            )
            OR
            (
                schema_version = 'sovereign.agent-execution-receipt.v1'
                AND mcp_revision IS NULL
                AND mcp_image_digest IS NULL
                AND mcp_revision_verified IS NULL
                AND execution_runtime_kind IN ('backend', 'mcp')
                AND execution_revision ~ '^[0-9a-f]{40}$'
                AND execution_image_digest ~ '^sha256:[0-9a-f]{64}$'
                AND execution_revision_verified = TRUE
                AND execution_image_digest_verified = TRUE
            )
        )
    );

CREATE INDEX IF NOT EXISTS idx_agent_run_receipts_execution_revision
    ON agent_run_receipts (repository, base_commit_sha, execution_runtime_kind, execution_revision);

COMMENT ON COLUMN agent_run_receipts.mcp_revision IS
    'Historical v1 MCP identity only. Internal backend execution receipts use execution_revision.';
COMMENT ON COLUMN agent_run_receipts.mcp_image_digest IS
    'Historical v1 MCP identity only. Internal backend execution receipts use execution_image_digest.';
COMMENT ON COLUMN agent_run_receipts.execution_runtime_kind IS
    'Runtime that executed the tool call: backend for normal Agent Job workspace tools; mcp only for true external MCP execution.';

COMMIT;
