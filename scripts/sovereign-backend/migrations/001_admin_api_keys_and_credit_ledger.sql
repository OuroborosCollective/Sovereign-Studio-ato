-- =============================================================================
-- Migration: admin_api_keys and credit_ledger tables
-- Purpose: Support proper audit actor resolution and append-only credit ledger
-- Issue: #516 Admin Runtime
-- =============================================================================
-- Safe to run once or repeatedly on the Postgres instance:
--   psql -h <host> -U <user> -d <db> -f 001_admin_api_keys_and_credit_ledger.sql
--
-- Runtime invariant:
-- Existing cached user credits must not be lost when the ledger is introduced.
-- This migration therefore creates an opening_balance ledger entry for legacy
-- users with positive credits before syncing the cached balance from ledger sum.
-- =============================================================================

BEGIN;

-- =============================================================================
-- admin_api_keys: Maps API keys to admin users for audit trail
-- =============================================================================
CREATE TABLE IF NOT EXISTS admin_api_keys (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_id        UUID        NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    key_hash        TEXT        UNIQUE NOT NULL,
    label           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_admin_api_keys_key_hash ON admin_api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_admin_api_keys_admin_id ON admin_api_keys(admin_id);

COMMENT ON TABLE admin_api_keys IS 'Maps admin API keys to users for audit trail - stores SHA256 hash, never plaintext';

-- =============================================================================
-- credit_ledger: Append-only credit transaction log
-- =============================================================================
CREATE TABLE IF NOT EXISTS credit_ledger (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID        NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    type            VARCHAR(50) NOT NULL,  -- purchase, bonus, manual_adjustment, correction, refund, chargeback, spend, opening_balance
    amount          INTEGER     NOT NULL,  -- positive = credit, negative = debit
    reason          TEXT,
    provider        TEXT,
    provider_tx_id  TEXT,
    created_by      UUID        REFERENCES admin_users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_credit_ledger_user_id ON credit_ledger(user_id);
CREATE INDEX IF NOT EXISTS idx_credit_ledger_created_at ON credit_ledger(created_at DESC);

COMMENT ON TABLE credit_ledger IS 'Append-only credit ledger - balance is SUM(amount) per user; admin_users.credits is a cache';

-- Reconcile the real production CHECK constraint with every ledger type used by
-- current runtime and migrations. Older installations created a narrower
-- credit_ledger_type_check, so CREATE TABLE IF NOT EXISTS cannot repair it.
-- Existing append-only rows are preserved; the canonical set is a superset of
-- all historical values and the current runtime contract.
DO $$
DECLARE
    constraint_definition TEXT;
BEGIN
    SELECT pg_get_constraintdef(constraint_row.oid)
    INTO constraint_definition
    FROM pg_constraint AS constraint_row
    JOIN pg_class AS relation_row
      ON relation_row.oid = constraint_row.conrelid
    JOIN pg_namespace AS namespace_row
      ON namespace_row.oid = relation_row.relnamespace
    WHERE namespace_row.nspname = current_schema()
      AND relation_row.relname = 'credit_ledger'
      AND constraint_row.conname = 'credit_ledger_type_check'
      AND constraint_row.contype = 'c';

    IF constraint_definition IS NULL
       OR constraint_definition NOT LIKE '%opening_balance%'
       OR constraint_definition NOT LIKE '%migration_reconciliation%'
       OR constraint_definition NOT LIKE '%balance_reconciliation%'
       OR constraint_definition NOT LIKE '%signup_bonus%'
       OR constraint_definition NOT LIKE '%credit_purchase%'
       OR constraint_definition NOT LIKE '%usage%'
    THEN
        ALTER TABLE credit_ledger
            DROP CONSTRAINT IF EXISTS credit_ledger_type_check;
        ALTER TABLE credit_ledger
            ADD CONSTRAINT credit_ledger_type_check CHECK (type IN (
                'purchase',
                'adjustment',
                'bonus',
                'manual_adjustment',
                'correction',
                'refund',
                'chargeback',
                'spend',
                'opening_balance',
                'migration_reconciliation',
                'balance_reconciliation',
                'signup_bonus',
                'credit_purchase',
                'usage'
            ));
    END IF;
END $$;

-- =============================================================================
-- Preserve existing cached credits as opening ledger balances
-- =============================================================================
INSERT INTO credit_ledger (user_id, type, amount, reason, created_at)
SELECT
    au.id,
    'opening_balance',
    au.credits,
    'Opening balance created by Issue #516 migration from legacy admin_users.credits',
    NOW()
FROM admin_users au
WHERE au.credits > 0
  AND NOT EXISTS (
      SELECT 1
      FROM credit_ledger cl
      WHERE cl.user_id = au.id
        AND cl.type = 'opening_balance'
  )
  AND NOT EXISTS (
      SELECT 1
      FROM credit_ledger cl
      WHERE cl.user_id = au.id
  );

-- =============================================================================
-- Create a function to recalculate cached credits from ledger
-- =============================================================================
CREATE OR REPLACE FUNCTION recalculate_user_credits(p_user_id UUID)
RETURNS INTEGER AS $$
DECLARE
    v_balance INTEGER;
BEGIN
    SELECT COALESCE(SUM(amount), 0) INTO v_balance
    FROM credit_ledger
    WHERE user_id = p_user_id;

    UPDATE admin_users SET credits = GREATEST(0, v_balance)
    WHERE id = p_user_id;

    RETURN GREATEST(0, v_balance);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- Sync admin_users.credits cache with ledger for users that now have ledger rows
-- =============================================================================
UPDATE admin_users au
SET credits = GREATEST(0, ledger.balance)
FROM (
    SELECT user_id, COALESCE(SUM(amount), 0) AS balance
    FROM credit_ledger
    GROUP BY user_id
) ledger
WHERE au.id = ledger.user_id;

COMMIT;

-- =============================================================================
-- Verification queries
-- =============================================================================

-- Check migration status:
-- SELECT 'admin_api_keys' as table_name, COUNT(*) as count FROM admin_api_keys
-- UNION ALL
-- SELECT 'credit_ledger', COUNT(*) FROM credit_ledger;

-- Check users with cached credits but no ledger entries:
-- SELECT id, email, credits FROM admin_users
-- WHERE credits > 0
-- AND NOT EXISTS (SELECT 1 FROM credit_ledger WHERE user_id = admin_users.id);

-- Verify balance consistency:
-- SELECT
--     au.id,
--     au.email,
--     au.credits as cached_balance,
--     COALESCE(SUM(cl.amount), 0) as ledger_balance,
--     CASE WHEN au.credits = GREATEST(0, COALESCE(SUM(cl.amount), 0)) THEN 'OK' ELSE 'MISMATCH' END as status
-- FROM admin_users au
-- LEFT JOIN credit_ledger cl ON cl.user_id = au.id
-- GROUP BY au.id, au.email, au.credits;
