-- Agent Zero is an external capability/evidence producer, never canonical run authority.
-- Additive/idempotent source-enum expansion for evidence/events only. Agent runs and
-- tasks remain owned by the Sovereign Agents SDK control plane.
BEGIN;

ALTER TABLE agent_events
    DROP CONSTRAINT IF EXISTS agent_events_source_check;
ALTER TABLE agent_events
    ADD CONSTRAINT agent_events_source_check CHECK (source IN (
        'agents-sdk', 'mcp', 'broker', 'github', 'browserless', 'tika',
        'gotenberg', 'database', 'agent-zero'
    ));

ALTER TABLE agent_evidence
    DROP CONSTRAINT IF EXISTS agent_evidence_source_check;
ALTER TABLE agent_evidence
    ADD CONSTRAINT agent_evidence_source_check CHECK (source IN (
        'agents-sdk', 'mcp', 'broker', 'github', 'browserless', 'tika',
        'gotenberg', 'database', 'agent-zero'
    ));

COMMENT ON CONSTRAINT agent_events_source_check ON agent_events IS
    'External Agent Zero observations are evidence only; they do not own canonical run/task state.';
COMMENT ON CONSTRAINT agent_evidence_source_check ON agent_evidence IS
    'Agent Zero may persist bounded external evidence, never raw credentials or authoritative Sovereign verdicts.';

COMMIT;
