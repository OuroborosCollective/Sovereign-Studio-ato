BEGIN;

CREATE TABLE IF NOT EXISTS owner_learning_policies (
    owner_admin_id UUID PRIMARY KEY REFERENCES admin_users(id) ON DELETE CASCADE,
    auto_accept_useful_unique BOOLEAN NOT NULL DEFAULT FALSE,
    policy_source TEXT NOT NULL DEFAULT 'owner-explicit',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

WITH selected_owner AS (
    SELECT id
    FROM admin_users
    WHERE role IN ('admin', 'superadmin')
    ORDER BY CASE WHEN role = 'superadmin' THEN 0 ELSE 1 END,
             created_at ASC,
             id ASC
    LIMIT 1
)
INSERT INTO owner_learning_policies (
    owner_admin_id,
    auto_accept_useful_unique,
    policy_source
)
SELECT id, TRUE, 'owner-explicit-2026-07-20'
FROM selected_owner
ON CONFLICT (owner_admin_id) DO UPDATE SET
    auto_accept_useful_unique = TRUE,
    policy_source = EXCLUDED.policy_source,
    updated_at = NOW();

COMMENT ON TABLE owner_learning_policies IS
'Persisted, revocable owner policy for evidence-proven, useful and content-deduplicated learning patterns.';

COMMIT;
