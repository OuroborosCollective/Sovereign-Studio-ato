-- =============================================================================
-- Migration: admin_api_keys and credit_ledger tables
-- Purpose: Support for proper audit trail and append-only credit ledger
-- Issue: #516 Admin Runtime
-- =============================================================================
-- Run this once on the Postgres instance:
--   psql -h <host> -U <user> -d <db> -f 001_admin_api_keys_and_credit_ledger.sql
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

-- Index for fast lookup by key hash
CREATE INDEX IF NOT EXISTS idx_admin_api_keys_key_hash ON admin_api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_admin_api_keys_admin_id ON admin_api_keys(admin_id);

COMMENT ON TABLE admin_api_keys IS 'Maps admin API keys to users for audit trail - stores SHA256 hash, never plaintext';

-- =============================================================================
-- credit_ledger: Append-only credit transaction log
-- =============================================================================
CREATE TABLE IF NOT EXISTS credit_ledger (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID        NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    type            VARCHAR(50) NOT NULL,  -- purchase, bonus, manual_adjustment, correction, refund, chargeback, spend
    amount          INTEGER     NOT NULL,  -- positive = credit, negative = debit
    reason          TEXT,
    provider        TEXT,       -- payment provider (paypal, skrill, google_play, etc)
    provider_tx_id  TEXT,       -- masked provider transaction ID
    created_by      UUID        REFERENCES admin_users(id),  -- admin who made the adjustment
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for fast balance calculation
CREATE INDEX IF NOT EXISTS idx_credit_ledger_user_id ON credit_ledger(user_id);
CREATE INDEX IF NOT EXISTS idx_credit_ledger_created_at ON credit_ledger(created_at DESC);

COMMENT ON TABLE credit_ledger IS 'Append-only credit ledger - balance is SUM(amount) per user, never updated directly';

-- =============================================================================
-- Update admin_users.credits to be consistent with ledger
-- This is a one-time migration to sync existing credits with ledger
-- =============================================================================

-- Create a function to recalculate credits from ledger
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
-- Sync admin_users.credits with ledger for all users
-- =============================================================================

UPDATE admin_users au
SET credits = COALESCE(
    (SELECT GREATEST(0, SUM(cl.amount)) 
    FROM credit_ledger cl 
    WHERE cl.user_id = au.id
    GROUP BY cl.user_id
), 0);

COMMIT;

-- =============================================================================
-- Verification queries (run these to check migration)
-- =============================================================================

-- Check migration status:
-- SELECT 'admin_api_keys' as table_name, COUNT(*) as count FROM admin_api_keys
-- UNION ALL
-- SELECT 'credit_ledger', COUNT(*) FROM credit_ledger;

-- Check for users with credits but no ledger entries (these are legacy):
-- SELECT id, email, credits FROM admin_users 
-- WHERE credits > 0 
-- AND id NOT IN (SELECT user_id FROM credit_ledger WHERE amount > 0);

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
