-- Owner-controlled one-time protected input requests.
-- PostgreSQL stores request metadata and lifecycle evidence only.
-- The protected value is never stored in this table, audit logs or API responses.
BEGIN;

CREATE TABLE IF NOT EXISTS owner_input_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_id TEXT NOT NULL,
    title TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    field_label TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    owner_admin_id UUID,
    owner_comment TEXT NOT NULL DEFAULT '',
    result_code TEXT NOT NULL DEFAULT '',
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    consumed_at TIMESTAMPTZ,
    CONSTRAINT owner_input_requests_target_check CHECK (
        target_id ~ '^[a-z][a-z0-9_]{2,63}$'
    ),
    CONSTRAINT owner_input_requests_status_check CHECK (
        status IN ('pending', 'processing', 'denied', 'consumed', 'failed', 'expired')
    ),
    CONSTRAINT owner_input_requests_comment_check CHECK (
        char_length(owner_comment) <= 1000
    ),
    CONSTRAINT owner_input_requests_expiry_check CHECK (
        expires_at > requested_at
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_owner_input_requests_open_target
    ON owner_input_requests (target_id)
    WHERE status IN ('pending', 'processing');

CREATE INDEX IF NOT EXISTS idx_owner_input_requests_pending
    ON owner_input_requests (requested_at ASC)
    WHERE status IN ('pending', 'processing');

CREATE INDEX IF NOT EXISTS idx_owner_input_requests_expiry
    ON owner_input_requests (expires_at ASC)
    WHERE status = 'pending';

COMMENT ON TABLE owner_input_requests IS
    'Metadata-only owner approval lifecycle. Protected values are accepted only by the owner endpoint and are never persisted here.';
COMMENT ON COLUMN owner_input_requests.owner_admin_id IS
    'Authenticated owner identifier captured as evidence without coupling the lifecycle table to an optional admin schema.';
COMMENT ON COLUMN owner_input_requests.result_code IS
    'Non-sensitive completion evidence such as target_updated, owner_denied or expired.';

COMMIT;
