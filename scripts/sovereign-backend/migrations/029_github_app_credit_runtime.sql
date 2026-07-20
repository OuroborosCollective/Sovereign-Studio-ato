BEGIN;

CREATE TABLE IF NOT EXISTS github_app_credits (
    installation_id BIGINT PRIMARY KEY CHECK (installation_id > 0),
    account_id BIGINT,
    account_login TEXT NOT NULL CHECK (btrim(account_login) <> ''),
    credits INTEGER NOT NULL DEFAULT 0 CHECK (credits >= 0),
    plan TEXT NOT NULL DEFAULT 'free' CHECK (btrim(plan) <> ''),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'suspended')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_github_app_credits_account_id
    ON github_app_credits(account_id)
    WHERE account_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_github_app_credits_account_login
    ON github_app_credits(lower(account_login));

CREATE TABLE IF NOT EXISTS github_app_credit_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key UUID NOT NULL UNIQUE,
    installation_id BIGINT NOT NULL
        REFERENCES github_app_credits(installation_id) ON DELETE CASCADE,
    amount INTEGER NOT NULL CHECK (amount <> 0),
    action TEXT NOT NULL CHECK (btrim(action) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_github_app_credit_transactions_installation_created
    ON github_app_credit_transactions(installation_id, created_at DESC);

COMMENT ON TABLE github_app_credits IS
'Canonical GitHub App installation credit account keyed by the real GitHub installation and stable account identity.';

COMMENT ON TABLE github_app_credit_transactions IS
'Idempotent append-only GitHub App credit mutations; retries reuse idempotency_key and cannot double-charge.';

COMMIT;
