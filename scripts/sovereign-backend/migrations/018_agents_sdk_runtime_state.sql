-- Persistent truth tables for the Sovereign OpenAI Agents SDK orchestrator.
-- Additive and idempotent. No raw secrets, credentials or full tool arguments
-- belong in these tables; callers persist bounded summaries and SHA-256 digests.
BEGIN;

CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    job_id TEXT REFERENCES sovereign_agent_jobs(job_id) ON DELETE SET NULL,
    session_key TEXT NOT NULL UNIQUE,
    mission_summary TEXT NOT NULL,
    mission_digest CHAR(64) NOT NULL,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    next_action TEXT NOT NULL,
    context_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    max_active_specialists INTEGER NOT NULL DEFAULT 4,
    max_iterations INTEGER NOT NULL DEFAULT 12,
    iteration_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resumed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    CONSTRAINT agent_runs_id_check CHECK (run_id <> '' AND session_key <> '' AND trace_id <> ''),
    CONSTRAINT agent_runs_digest_check CHECK (mission_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT agent_runs_status_check CHECK (status IN (
        'RECEIVED', 'SCOPING', 'PLANNED', 'QUEUED', 'ASSIGNED', 'RUNNING',
        'WAITING_FOR_TOOL', 'WAITING_FOR_AGENT', 'WAITING_FOR_OWNER', 'VERIFYING',
        'BLOCKED', 'FAILED_RECOVERABLE', 'FAILED_FINAL', 'READY_FOR_DRAFT_PR',
        'DRAFT_PR_CREATED', 'COMPLETED'
    )),
    CONSTRAINT agent_runs_source_check CHECK (source IN (
        'agents-sdk', 'mcp', 'broker', 'github', 'browserless', 'tika', 'gotenberg', 'database'
    )),
    CONSTRAINT agent_runs_state_evidence_check CHECK (
        evidence_id <> '' AND reason <> '' AND next_action <> ''
    ),
    CONSTRAINT agent_runs_context_check CHECK (jsonb_typeof(context_snapshot) = 'object'),
    CONSTRAINT agent_runs_limits_check CHECK (
        max_active_specialists BETWEEN 1 AND 8
        AND max_iterations BETWEEN 1 AND 100
        AND iteration_count BETWEEN 0 AND max_iterations
    )
);

CREATE TABLE IF NOT EXISTS agent_tasks (
    task_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    specialist_role TEXT,
    work_package TEXT NOT NULL,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    next_action TEXT NOT NULL,
    allowed_files JSONB NOT NULL DEFAULT '[]'::jsonb,
    allowed_tools JSONB NOT NULL DEFAULT '[]'::jsonb,
    acceptance_criteria JSONB NOT NULL DEFAULT '[]'::jsonb,
    forbidden_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    timeout_seconds INTEGER NOT NULL DEFAULT 900,
    max_tool_calls INTEGER NOT NULL DEFAULT 20,
    tool_call_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 2,
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT agent_tasks_status_check CHECK (status IN (
        'RECEIVED', 'SCOPING', 'PLANNED', 'QUEUED', 'ASSIGNED', 'RUNNING',
        'WAITING_FOR_TOOL', 'WAITING_FOR_AGENT', 'WAITING_FOR_OWNER', 'VERIFYING',
        'BLOCKED', 'FAILED_RECOVERABLE', 'FAILED_FINAL', 'READY_FOR_DRAFT_PR',
        'DRAFT_PR_CREATED', 'COMPLETED'
    )),
    CONSTRAINT agent_tasks_source_check CHECK (source IN (
        'agents-sdk', 'mcp', 'broker', 'github', 'browserless', 'tika', 'gotenberg', 'database'
    )),
    CONSTRAINT agent_tasks_state_evidence_check CHECK (
        task_id <> '' AND agent_id <> '' AND evidence_id <> ''
        AND reason <> '' AND next_action <> ''
    ),
    CONSTRAINT agent_tasks_json_check CHECK (
        jsonb_typeof(allowed_files) = 'array'
        AND jsonb_typeof(allowed_tools) = 'array'
        AND jsonb_typeof(acceptance_criteria) = 'array'
        AND jsonb_typeof(forbidden_actions) = 'array'
    ),
    CONSTRAINT agent_tasks_limits_check CHECK (
        timeout_seconds BETWEEN 1 AND 86400
        AND max_tool_calls BETWEEN 0 AND 200
        AND tool_call_count BETWEEN 0 AND max_tool_calls
        AND max_retries BETWEEN 0 AND 10
        AND retry_count BETWEEN 0 AND max_retries
    )
);

CREATE TABLE IF NOT EXISTS agent_handoffs (
    handoff_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    task_id TEXT REFERENCES agent_tasks(task_id) ON DELETE SET NULL,
    from_agent TEXT NOT NULL,
    to_agent TEXT NOT NULL,
    reason TEXT NOT NULL,
    input_summary TEXT NOT NULL,
    permitted_context JSONB NOT NULL DEFAULT '[]'::jsonb,
    excluded_context JSONB NOT NULL DEFAULT '[]'::jsonb,
    expected_output TEXT NOT NULL,
    acceptance_criteria JSONB NOT NULL DEFAULT '[]'::jsonb,
    trace_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT agent_handoffs_identity_check CHECK (
        handoff_id <> '' AND from_agent <> '' AND to_agent <> '' AND from_agent <> to_agent
    ),
    CONSTRAINT agent_handoffs_context_check CHECK (
        jsonb_typeof(permitted_context) = 'array'
        AND jsonb_typeof(excluded_context) = 'array'
        AND jsonb_typeof(acceptance_criteria) = 'array'
    )
);

CREATE TABLE IF NOT EXISTS agent_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    task_id TEXT REFERENCES agent_tasks(task_id) ON DELETE SET NULL,
    agent_id TEXT NOT NULL,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    summary TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    next_action TEXT NOT NULL,
    CONSTRAINT agent_events_status_check CHECK (status IN (
        'RECEIVED', 'SCOPING', 'PLANNED', 'QUEUED', 'ASSIGNED', 'RUNNING',
        'WAITING_FOR_TOOL', 'WAITING_FOR_AGENT', 'WAITING_FOR_OWNER', 'VERIFYING',
        'BLOCKED', 'FAILED_RECOVERABLE', 'FAILED_FINAL', 'READY_FOR_DRAFT_PR',
        'DRAFT_PR_CREATED', 'COMPLETED'
    )),
    CONSTRAINT agent_events_source_check CHECK (source IN (
        'agents-sdk', 'mcp', 'broker', 'github', 'browserless', 'tika', 'gotenberg', 'database'
    )),
    CONSTRAINT agent_events_evidence_check CHECK (
        event_id <> '' AND agent_id <> '' AND type <> '' AND summary <> ''
        AND evidence_id <> '' AND trace_id <> '' AND next_action <> ''
    )
);

CREATE TABLE IF NOT EXISTS agent_tool_calls (
    tool_call_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    task_id TEXT REFERENCES agent_tasks(task_id) ON DELETE SET NULL,
    agent_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    arguments_digest CHAR(64) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    result_digest CHAR(64),
    mutating BOOLEAN NOT NULL DEFAULT FALSE,
    approval_id TEXT,
    failure_family TEXT,
    CONSTRAINT agent_tool_calls_digest_check CHECK (
        arguments_digest ~ '^[0-9a-f]{64}$'
        AND (result_digest IS NULL OR result_digest ~ '^[0-9a-f]{64}$')
    ),
    CONSTRAINT agent_tool_calls_status_check CHECK (status IN (
        'QUEUED', 'RUNNING', 'WAITING_FOR_OWNER', 'COMPLETED', 'BLOCKED', 'FAILED_RECOVERABLE', 'FAILED_FINAL'
    )),
    CONSTRAINT agent_tool_calls_identity_check CHECK (
        tool_call_id <> '' AND agent_id <> '' AND tool_name <> ''
    )
);

CREATE TABLE IF NOT EXISTS agent_evidence (
    evidence_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    task_id TEXT REFERENCES agent_tasks(task_id) ON DELETE SET NULL,
    agent_id TEXT NOT NULL,
    source TEXT NOT NULL,
    kind TEXT NOT NULL,
    summary TEXT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT agent_evidence_source_check CHECK (source IN (
        'agents-sdk', 'mcp', 'broker', 'github', 'browserless', 'tika', 'gotenberg', 'database'
    )),
    CONSTRAINT agent_evidence_digest_check CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT agent_evidence_payload_check CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT agent_evidence_identity_check CHECK (
        evidence_id <> '' AND agent_id <> '' AND kind <> '' AND summary <> ''
    )
);

CREATE TABLE IF NOT EXISTS agent_artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    task_id TEXT REFERENCES agent_tasks(task_id) ON DELETE SET NULL,
    evidence_id TEXT NOT NULL REFERENCES agent_evidence(evidence_id) ON DELETE RESTRICT,
    kind TEXT NOT NULL,
    uri TEXT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    media_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT agent_artifacts_digest_check CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT agent_artifacts_size_check CHECK (size_bytes >= 0),
    CONSTRAINT agent_artifacts_identity_check CHECK (
        artifact_id <> '' AND kind <> '' AND uri <> '' AND media_type <> ''
    )
);

CREATE TABLE IF NOT EXISTS agent_approvals (
    approval_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    task_id TEXT REFERENCES agent_tasks(task_id) ON DELETE SET NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'WAITING_FOR_OWNER',
    protected_input_ref TEXT,
    requested_by_agent TEXT NOT NULL,
    decided_by_user UUID REFERENCES admin_users(id) ON DELETE SET NULL,
    evidence_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decided_at TIMESTAMPTZ,
    CONSTRAINT agent_approvals_status_check CHECK (status IN (
        'WAITING_FOR_OWNER', 'APPROVED', 'REJECTED', 'EXPIRED'
    )),
    CONSTRAINT agent_approvals_identity_check CHECK (
        approval_id <> '' AND kind <> '' AND requested_by_agent <> ''
        AND evidence_id <> '' AND reason <> ''
    ),
    CONSTRAINT agent_approvals_decision_check CHECK (
        (status = 'WAITING_FOR_OWNER' AND decided_at IS NULL)
        OR (status <> 'WAITING_FOR_OWNER' AND decided_at IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS agent_failures (
    failure_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    task_id TEXT REFERENCES agent_tasks(task_id) ON DELETE SET NULL,
    agent_id TEXT NOT NULL,
    family TEXT NOT NULL,
    recoverable BOOLEAN NOT NULL,
    summary TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    retry_after TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    CONSTRAINT agent_failures_identity_check CHECK (
        failure_id <> '' AND agent_id <> '' AND family <> ''
        AND summary <> '' AND evidence_id <> ''
    )
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_user_created
    ON agent_runs (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status
    ON agent_runs (status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_run_status
    ON agent_tasks (run_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_events_run_created
    ON agent_events (run_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_agent_tool_calls_run_started
    ON agent_tool_calls (run_id, started_at ASC);
CREATE INDEX IF NOT EXISTS idx_agent_evidence_run_created
    ON agent_evidence (run_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_agent_artifacts_run_created
    ON agent_artifacts (run_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_agent_approvals_waiting
    ON agent_approvals (run_id, created_at ASC)
    WHERE status = 'WAITING_FOR_OWNER';
CREATE INDEX IF NOT EXISTS idx_agent_failures_unresolved
    ON agent_failures (run_id, created_at ASC)
    WHERE resolved_at IS NULL;

CREATE OR REPLACE FUNCTION update_agent_runtime_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    IF NEW.status IN ('COMPLETED', 'FAILED_FINAL', 'DRAFT_PR_CREATED')
       AND NEW.completed_at IS NULL THEN
        NEW.completed_at = NOW();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_agent_runs_timestamp ON agent_runs;
CREATE TRIGGER trigger_update_agent_runs_timestamp
    BEFORE UPDATE ON agent_runs
    FOR EACH ROW EXECUTE FUNCTION update_agent_runtime_timestamp();

DROP TRIGGER IF EXISTS trigger_update_agent_tasks_timestamp ON agent_tasks;
CREATE TRIGGER trigger_update_agent_tasks_timestamp
    BEFORE UPDATE ON agent_tasks
    FOR EACH ROW EXECUTE FUNCTION update_agent_runtime_timestamp();

COMMENT ON TABLE agent_runs IS
    'Persistent Agents SDK run truth. Every visible status requires source, evidence_id, reason and next_action.';
COMMENT ON TABLE agent_tool_calls IS
    'Stores argument/result digests only; raw secret-bearing tool arguments are forbidden.';
COMMENT ON TABLE agent_approvals IS
    'Stores protected owner references only. Protected values never enter the LLM or this table.';

COMMIT;
