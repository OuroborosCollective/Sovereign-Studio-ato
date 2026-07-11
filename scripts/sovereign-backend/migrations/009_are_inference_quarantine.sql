-- ARE deterministic inference quarantine.
-- Additive only. Online output remains pending until an accepted evidence pattern exists.

CREATE TABLE IF NOT EXISTS are_learning_quarantine (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    state_hash CHAR(64) NOT NULL,
    prompt_sha256 CHAR(64) NOT NULL,
    response_sha256 CHAR(64) NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    prompt_text TEXT NOT NULL,
    response_text TEXT NOT NULL,
    adapter VARCHAR(160) NOT NULL DEFAULT '',
    model_id VARCHAR(240) NOT NULL DEFAULT '',
    status VARCHAR(24) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'rejected', 'promoted')),
    promoted_pattern_candidate_id TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, content_sha256)
);

CREATE INDEX IF NOT EXISTS idx_are_learning_quarantine_user_status
    ON are_learning_quarantine (user_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_are_learning_quarantine_state_hash
    ON are_learning_quarantine (user_id, state_hash);

DO $$
BEGIN
    IF to_regclass('public.admin_users') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
           FROM pg_constraint
           WHERE conname = 'are_learning_quarantine_user_fk'
       ) THEN
        ALTER TABLE are_learning_quarantine
            ADD CONSTRAINT are_learning_quarantine_user_fk
            FOREIGN KEY (user_id) REFERENCES admin_users(id) ON DELETE CASCADE;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS schema_migrations (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO schema_migrations (id, name)
VALUES (9, 'are_inference_quarantine')
ON CONFLICT (id) DO NOTHING;
