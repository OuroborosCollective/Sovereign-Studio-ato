-- Fleet O2: retry-safe assignment attempt identity for persisted agent evidence.
-- Additive and replay-safe. Historical NULL attempt columns remain valid history and
-- must never be interpreted as evidence for a current attempt.
BEGIN;

ALTER TABLE agent_events
    ADD COLUMN IF NOT EXISTS attempt_id TEXT,
    ADD COLUMN IF NOT EXISTS attempt_sequence INTEGER,
    ADD COLUMN IF NOT EXISTS attempt_hash CHAR(64),
    ADD COLUMN IF NOT EXISTS assignment_hash CHAR(64);
ALTER TABLE agent_tool_calls
    ADD COLUMN IF NOT EXISTS attempt_id TEXT,
    ADD COLUMN IF NOT EXISTS attempt_sequence INTEGER,
    ADD COLUMN IF NOT EXISTS attempt_hash CHAR(64),
    ADD COLUMN IF NOT EXISTS assignment_hash CHAR(64);
ALTER TABLE agent_evidence
    ADD COLUMN IF NOT EXISTS attempt_id TEXT,
    ADD COLUMN IF NOT EXISTS attempt_sequence INTEGER,
    ADD COLUMN IF NOT EXISTS attempt_hash CHAR(64),
    ADD COLUMN IF NOT EXISTS assignment_hash CHAR(64);
ALTER TABLE agent_failures
    ADD COLUMN IF NOT EXISTS attempt_id TEXT,
    ADD COLUMN IF NOT EXISTS attempt_sequence INTEGER,
    ADD COLUMN IF NOT EXISTS attempt_hash CHAR(64),
    ADD COLUMN IF NOT EXISTS assignment_hash CHAR(64);
ALTER TABLE agent_handoffs
    ADD COLUMN IF NOT EXISTS attempt_id TEXT,
    ADD COLUMN IF NOT EXISTS attempt_sequence INTEGER,
    ADD COLUMN IF NOT EXISTS attempt_hash CHAR(64),
    ADD COLUMN IF NOT EXISTS assignment_hash CHAR(64);

ALTER TABLE agent_events DROP CONSTRAINT IF EXISTS agent_events_attempt_identity_check;
ALTER TABLE agent_events ADD CONSTRAINT agent_events_attempt_identity_check CHECK (
    (attempt_id IS NULL AND attempt_sequence IS NULL AND attempt_hash IS NULL AND assignment_hash IS NULL)
    OR (
        attempt_id ~ '^attempt-[0-9a-f]{24}$'
        AND attempt_sequence >= 1
        AND attempt_hash ~ '^[0-9a-f]{64}$'
        AND assignment_hash ~ '^[0-9a-f]{64}$'
    )
);
ALTER TABLE agent_tool_calls DROP CONSTRAINT IF EXISTS agent_tool_calls_attempt_identity_check;
ALTER TABLE agent_tool_calls ADD CONSTRAINT agent_tool_calls_attempt_identity_check CHECK (
    (attempt_id IS NULL AND attempt_sequence IS NULL AND attempt_hash IS NULL AND assignment_hash IS NULL)
    OR (
        attempt_id ~ '^attempt-[0-9a-f]{24}$'
        AND attempt_sequence >= 1
        AND attempt_hash ~ '^[0-9a-f]{64}$'
        AND assignment_hash ~ '^[0-9a-f]{64}$'
    )
);
ALTER TABLE agent_evidence DROP CONSTRAINT IF EXISTS agent_evidence_attempt_identity_check;
ALTER TABLE agent_evidence ADD CONSTRAINT agent_evidence_attempt_identity_check CHECK (
    (attempt_id IS NULL AND attempt_sequence IS NULL AND attempt_hash IS NULL AND assignment_hash IS NULL)
    OR (
        attempt_id ~ '^attempt-[0-9a-f]{24}$'
        AND attempt_sequence >= 1
        AND attempt_hash ~ '^[0-9a-f]{64}$'
        AND assignment_hash ~ '^[0-9a-f]{64}$'
    )
);
ALTER TABLE agent_failures DROP CONSTRAINT IF EXISTS agent_failures_attempt_identity_check;
ALTER TABLE agent_failures ADD CONSTRAINT agent_failures_attempt_identity_check CHECK (
    (attempt_id IS NULL AND attempt_sequence IS NULL AND attempt_hash IS NULL AND assignment_hash IS NULL)
    OR (
        attempt_id ~ '^attempt-[0-9a-f]{24}$'
        AND attempt_sequence >= 1
        AND attempt_hash ~ '^[0-9a-f]{64}$'
        AND assignment_hash ~ '^[0-9a-f]{64}$'
    )
);
ALTER TABLE agent_handoffs DROP CONSTRAINT IF EXISTS agent_handoffs_attempt_identity_check;
ALTER TABLE agent_handoffs ADD CONSTRAINT agent_handoffs_attempt_identity_check CHECK (
    (attempt_id IS NULL AND attempt_sequence IS NULL AND attempt_hash IS NULL AND assignment_hash IS NULL)
    OR (
        attempt_id ~ '^attempt-[0-9a-f]{24}$'
        AND attempt_sequence >= 1
        AND attempt_hash ~ '^[0-9a-f]{64}$'
        AND assignment_hash ~ '^[0-9a-f]{64}$'
    )
);

CREATE INDEX IF NOT EXISTS idx_agent_events_run_task_attempt
    ON agent_events (run_id, task_id, attempt_id, created_at ASC)
    WHERE attempt_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_agent_tool_calls_run_task_attempt
    ON agent_tool_calls (run_id, task_id, attempt_id, started_at ASC)
    WHERE attempt_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_agent_evidence_run_task_attempt
    ON agent_evidence (run_id, task_id, attempt_id, created_at ASC)
    WHERE attempt_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_agent_failures_run_task_attempt
    ON agent_failures (run_id, task_id, attempt_id, created_at ASC)
    WHERE attempt_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_agent_handoffs_run_task_attempt
    ON agent_handoffs (run_id, task_id, attempt_id, created_at ASC)
    WHERE attempt_id IS NOT NULL;

COMMENT ON COLUMN agent_events.attempt_id IS
    'Nullable only for historical pre-Fleet-O2 rows; NULL is never current-attempt evidence.';
COMMENT ON COLUMN agent_evidence.attempt_id IS
    'Exact Fleet attempt identity for evidence gating; historical NULL rows cannot satisfy an active attempt.';

COMMIT;
