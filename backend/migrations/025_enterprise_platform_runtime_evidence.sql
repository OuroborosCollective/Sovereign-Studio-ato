-- Evidence ledger for the modular enterprise backend control plane.
BEGIN;

CREATE TABLE IF NOT EXISTS platform_runtime_evidence (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL,
    actor_id UUID,
    scope TEXT NOT NULL CHECK (scope IN ('readiness', 'completion')),
    status TEXT NOT NULL CHECK (status IN ('verified', 'degraded', 'blocked')),
    source_revision TEXT NOT NULL,
    runtime_identity UUID NOT NULL,
    evidence_sha256 CHAR(64) NOT NULL CHECK (evidence_sha256 ~ '^[0-9a-f]{64}$'),
    evidence JSONB NOT NULL CHECK (jsonb_typeof(evidence) = 'object'),
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT platform_runtime_source_revision_check CHECK (
        source_revision = 'unverified' OR source_revision ~ '^[0-9a-f]{40}$'
    ),
    UNIQUE (request_id, evidence_sha256)
);

DO $$
BEGIN
    IF to_regclass('public.admin_users') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
           FROM pg_constraint
           WHERE conname = 'fk_platform_runtime_evidence_actor'
       ) THEN
        ALTER TABLE platform_runtime_evidence
            ADD CONSTRAINT fk_platform_runtime_evidence_actor
            FOREIGN KEY (actor_id) REFERENCES admin_users(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_platform_runtime_evidence_observed
    ON platform_runtime_evidence (observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_platform_runtime_evidence_actor_scope
    ON platform_runtime_evidence (actor_id, scope, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_platform_runtime_evidence_status
    ON platform_runtime_evidence (status, observed_at DESC);

CREATE TABLE IF NOT EXISTS schema_migrations (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO schema_migrations (id, name)
VALUES (25, 'enterprise_platform_runtime_evidence')
ON CONFLICT (id) DO NOTHING;

COMMIT;
