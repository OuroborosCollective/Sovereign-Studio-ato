BEGIN;

CREATE TABLE IF NOT EXISTS sovereign_owner_learning_policies (
    owner_admin_id UUID PRIMARY KEY REFERENCES admin_users(id) ON DELETE CASCADE,
    auto_accept_proven_patterns BOOLEAN NOT NULL DEFAULT FALSE,
    require_evidence BOOLEAN NOT NULL DEFAULT TRUE,
    reject_duplicates BOOLEAN NOT NULL DEFAULT TRUE,
    minimum_confidence NUMERIC(5,4) NOT NULL DEFAULT 0.7000,
    directive_source TEXT NOT NULL,
    enabled_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT sovereign_owner_learning_minimum_confidence_check
      CHECK (minimum_confidence >= 0 AND minimum_confidence <= 1)
);

INSERT INTO sovereign_owner_learning_policies (
    owner_admin_id,
    auto_accept_proven_patterns,
    require_evidence,
    reject_duplicates,
    minimum_confidence,
    directive_source,
    enabled_at,
    revoked_at
)
SELECT id,
       TRUE,
       TRUE,
       TRUE,
       0.7000,
       'owner-explicit-standing-directive-2026-07-20',
       NOW(),
       NULL
FROM admin_users
WHERE role = 'superadmin'
ORDER BY created_at ASC
LIMIT 1
ON CONFLICT (owner_admin_id) DO UPDATE SET
    auto_accept_proven_patterns = TRUE,
    require_evidence = TRUE,
    reject_duplicates = TRUE,
    minimum_confidence = 0.7000,
    directive_source = EXCLUDED.directive_source,
    enabled_at = COALESCE(sovereign_owner_learning_policies.enabled_at, NOW()),
    revoked_at = NULL,
    updated_at = NOW();

COMMENT ON TABLE sovereign_owner_learning_policies IS
'Persisted and revocable Owner directive for evidence-proven, deduplicated learning-pattern ingestion.';

COMMIT;
