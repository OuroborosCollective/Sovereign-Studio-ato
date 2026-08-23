-- Issue #1620: real PostgreSQL persistence for typed Live Workspace bubbles.
-- Sessions and bubbles are immutable. Client routes may append only MISSION_INPUT;
-- workflow, consent and effect-readback bubbles are produced by server-side contracts.
BEGIN;

CREATE TABLE IF NOT EXISTS live_workspace_chat_sessions (
    session_id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    repository_identity TEXT NOT NULL,
    repository_branch TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT 'sovereign.live-workspace-chat-session.v1',
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT live_workspace_chat_sessions_scope_unique
        UNIQUE (user_id, repository_identity, repository_branch),
    CONSTRAINT live_workspace_chat_sessions_owner_pair_unique
        UNIQUE (session_id, user_id),
    CONSTRAINT live_workspace_chat_sessions_schema_check
        CHECK (schema_version = 'sovereign.live-workspace-chat-session.v1'),
    CONSTRAINT live_workspace_chat_sessions_id_check
        CHECK (session_id ~ '^livechat-[0-9a-f]{24}$'),
    CONSTRAINT live_workspace_chat_sessions_repository_check
        CHECK (
            repository_identity = 'UNBOUND'
            OR repository_identity ~ '^https://github[.]com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'
        ),
    CONSTRAINT live_workspace_chat_sessions_branch_check
        CHECK (
            repository_branch ~ '^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$'
            AND repository_branch NOT LIKE '%..%'
        )
);

CREATE TABLE IF NOT EXISTS live_workspace_chat_bubbles (
    ordinal BIGSERIAL PRIMARY KEY,
    bubble_hash CHAR(64) NOT NULL UNIQUE,
    session_id TEXT NOT NULL,
    user_id UUID NOT NULL,
    client_message_id TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    bubble_kind TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    bubble_text TEXT NOT NULL,
    canonical_reference_hashes JSONB NOT NULL DEFAULT '[]'::jsonb,
    session_binding_hash CHAR(64),
    run_id TEXT,
    attempt_id TEXT,
    workflow_state TEXT NOT NULL,
    bound_revision CHAR(40),
    effect_kind TEXT,
    target_hash CHAR(64),
    consent_binding_hash CHAR(64),
    canonical_body JSONB NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT live_workspace_chat_bubbles_session_owner_fk
        FOREIGN KEY (session_id, user_id)
        REFERENCES live_workspace_chat_sessions(session_id, user_id)
        ON DELETE RESTRICT,
    CONSTRAINT live_workspace_chat_bubbles_idempotency_unique
        UNIQUE (session_id, client_message_id),
    CONSTRAINT live_workspace_chat_bubbles_schema_check
        CHECK (schema_version = 'sovereign.live-workspace-chat-bubble.v1'),
    CONSTRAINT live_workspace_chat_bubbles_kind_check
        CHECK (bubble_kind IN (
            'MISSION_INPUT',
            'REQUIRED_QUESTION',
            'OWNER_CONSENT_REQUEST',
            'MATERIAL_BLOCKER',
            'FINAL_RESULT'
        )),
    CONSTRAINT live_workspace_chat_bubbles_source_check
        CHECK (
            (bubble_kind = 'MISSION_INPUT' AND source_kind = 'USER_INPUT')
            OR (bubble_kind IN ('REQUIRED_QUESTION', 'MATERIAL_BLOCKER') AND source_kind = 'CANONICAL_WORKFLOW')
            OR (bubble_kind = 'OWNER_CONSENT_REQUEST' AND source_kind = 'CONSENT_CONTRACT')
            OR (bubble_kind = 'FINAL_RESULT' AND source_kind = 'EFFECT_READBACK')
        ),
    CONSTRAINT live_workspace_chat_bubbles_hash_check
        CHECK (
            bubble_hash ~ '^[0-9a-f]{64}$'
            AND (session_binding_hash IS NULL OR session_binding_hash ~ '^[0-9a-f]{64}$')
            AND (bound_revision IS NULL OR bound_revision ~ '^[0-9a-f]{40}$')
            AND (target_hash IS NULL OR target_hash ~ '^[0-9a-f]{64}$')
            AND (consent_binding_hash IS NULL OR consent_binding_hash ~ '^[0-9a-f]{64}$')
        ),
    CONSTRAINT live_workspace_chat_bubbles_client_id_check
        CHECK (client_message_id ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$'),
    CONSTRAINT live_workspace_chat_bubbles_text_check
        CHECK (length(btrim(bubble_text)) BETWEEN 1 AND 2000),
    CONSTRAINT live_workspace_chat_bubbles_refs_check
        CHECK (jsonb_typeof(canonical_reference_hashes) = 'array'),
    CONSTRAINT live_workspace_chat_bubbles_state_check
        CHECK (workflow_state IN (
            'RECORDED',
            'WAITING_FOR_USER',
            'BLOCKED',
            'FAILED',
            'UNVERIFIED',
            'CONTRADICTED',
            'VERIFIED'
        )),
    CONSTRAINT live_workspace_chat_bubbles_binding_check
        CHECK (
            (
                bubble_kind = 'MISSION_INPUT'
                AND workflow_state = 'RECORDED'
                AND session_binding_hash IS NULL
                AND run_id IS NULL
                AND attempt_id IS NULL
                AND bound_revision IS NULL
                AND effect_kind IS NULL
                AND target_hash IS NULL
                AND consent_binding_hash IS NULL
            )
            OR (
                bubble_kind <> 'MISSION_INPUT'
                AND session_binding_hash IS NOT NULL
                AND run_id IS NOT NULL
                AND attempt_id IS NOT NULL
                AND jsonb_array_length(canonical_reference_hashes) > 0
            )
        ),
    CONSTRAINT live_workspace_chat_bubbles_semantics_check
        CHECK (
            (bubble_kind = 'MISSION_INPUT')
            OR (bubble_kind = 'REQUIRED_QUESTION' AND workflow_state = 'WAITING_FOR_USER')
            OR (
                bubble_kind = 'OWNER_CONSENT_REQUEST'
                AND workflow_state = 'WAITING_FOR_USER'
                AND bound_revision IS NOT NULL
                AND effect_kind IS NOT NULL
                AND target_hash IS NOT NULL
                AND consent_binding_hash IS NOT NULL
            )
            OR (
                bubble_kind = 'MATERIAL_BLOCKER'
                AND workflow_state IN ('BLOCKED', 'FAILED', 'UNVERIFIED', 'CONTRADICTED')
            )
            OR (
                bubble_kind = 'FINAL_RESULT'
                AND workflow_state = 'VERIFIED'
                AND bound_revision IS NOT NULL
                AND effect_kind IS NULL
                AND consent_binding_hash IS NULL
            )
        ),
    CONSTRAINT live_workspace_chat_bubbles_body_check
        CHECK (
            jsonb_typeof(canonical_body) = 'object'
            AND canonical_body ->> 'bubbleHash' = bubble_hash
            AND canonical_body ->> 'sessionId' = session_id
            AND canonical_body ->> 'clientMessageId' = client_message_id
            AND canonical_body ->> 'bubbleKind' = bubble_kind
            AND canonical_body ->> 'sourceKind' = source_kind
        )
);

CREATE INDEX IF NOT EXISTS idx_live_workspace_chat_bubbles_session_order
    ON live_workspace_chat_bubbles (session_id, ordinal);
CREATE INDEX IF NOT EXISTS idx_live_workspace_chat_sessions_owner_scope
    ON live_workspace_chat_sessions (user_id, repository_identity, repository_branch);

CREATE OR REPLACE FUNCTION reject_live_workspace_chat_history_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'live workspace chat persistence is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS reject_live_workspace_chat_sessions_update
    ON live_workspace_chat_sessions;
CREATE TRIGGER reject_live_workspace_chat_sessions_update
    BEFORE UPDATE ON live_workspace_chat_sessions
    FOR EACH ROW EXECUTE FUNCTION reject_live_workspace_chat_history_mutation();

DROP TRIGGER IF EXISTS reject_live_workspace_chat_sessions_delete
    ON live_workspace_chat_sessions;
CREATE TRIGGER reject_live_workspace_chat_sessions_delete
    BEFORE DELETE ON live_workspace_chat_sessions
    FOR EACH ROW EXECUTE FUNCTION reject_live_workspace_chat_history_mutation();

DROP TRIGGER IF EXISTS reject_live_workspace_chat_bubbles_update
    ON live_workspace_chat_bubbles;
CREATE TRIGGER reject_live_workspace_chat_bubbles_update
    BEFORE UPDATE ON live_workspace_chat_bubbles
    FOR EACH ROW EXECUTE FUNCTION reject_live_workspace_chat_history_mutation();

DROP TRIGGER IF EXISTS reject_live_workspace_chat_bubbles_delete
    ON live_workspace_chat_bubbles;
CREATE TRIGGER reject_live_workspace_chat_bubbles_delete
    BEFORE DELETE ON live_workspace_chat_bubbles
    FOR EACH ROW EXECUTE FUNCTION reject_live_workspace_chat_history_mutation();

COMMENT ON TABLE live_workspace_chat_sessions IS
    'Immutable real-PostgreSQL owner/repository/branch scope for situational Live Workspace chat.';
COMMENT ON TABLE live_workspace_chat_bubbles IS
    'Append-only typed user-visible bubbles. Rows never create workflow, permission or effect truth.';

COMMIT;
