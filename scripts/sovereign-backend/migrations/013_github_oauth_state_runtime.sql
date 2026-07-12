-- Persist GitHub OAuth state across multiple Gunicorn workers.
-- Raw OAuth state values are never stored; only SHA-256 fingerprints exist.
-- Additive, idempotent and safe to re-run.
BEGIN;

CREATE TABLE IF NOT EXISTS github_oauth_states (
    state_hash  TEXT        PRIMARY KEY,
    payload     JSONB       NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT github_oauth_states_hash_format
        CHECK (state_hash ~ '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS idx_github_oauth_states_expires_at
    ON github_oauth_states(expires_at);

COMMIT;
