-- Align the admin transaction reader/writer contract with the persisted schema.
-- Additive and idempotent. Production application requires separate approval.
BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS transactions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID,
    user_email     TEXT NOT NULL DEFAULT 'anonymous',
    type           VARCHAR(50) NOT NULL,
    amount         NUMERIC(10,2) NOT NULL,
    currency       VARCHAR(10) NOT NULL DEFAULT 'EUR',
    status         VARCHAR(20) NOT NULL DEFAULT 'pending',
    provider       TEXT,
    provider_tx_id TEXT,
    description    TEXT,
    metadata       JSONB,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS user_email TEXT;

DO $$
BEGIN
    IF to_regclass('public.admin_users') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM pg_constraint WHERE conname = 'transactions_user_id_fkey'
       ) THEN
        ALTER TABLE transactions
            ADD CONSTRAINT transactions_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES admin_users(id);
    END IF;
END $$;

DO $$
BEGIN
    IF to_regclass('public.admin_users') IS NOT NULL THEN
        UPDATE transactions AS ledger_entry
        SET user_email = account.email
        FROM admin_users AS account
        WHERE ledger_entry.user_id = account.id
          AND (ledger_entry.user_email IS NULL OR BTRIM(ledger_entry.user_email) = '');
    END IF;
END $$;

UPDATE transactions
SET user_email = 'anonymous'
WHERE user_email IS NULL OR BTRIM(user_email) = '';

ALTER TABLE transactions
    ALTER COLUMN user_email SET DEFAULT 'anonymous';

ALTER TABLE transactions
    ALTER COLUMN user_email SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);
CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON transactions(created_at DESC);

COMMIT;
