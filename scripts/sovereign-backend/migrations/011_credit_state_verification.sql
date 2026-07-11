-- Reconcile user credit cache with the append-only ledger and introduce a
-- unique provider receipt gate. Additive, idempotent and safe to re-run.
-- Production application requires separate approval.
BEGIN;

CREATE TABLE IF NOT EXISTS credit_receipts (
    provider        TEXT        NOT NULL,
    provider_tx_id  TEXT        NOT NULL,
    user_id         UUID        NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    credits         INTEGER     NOT NULL CHECK (credits > 0),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (provider, provider_tx_id)
);
CREATE INDEX IF NOT EXISTS idx_credit_receipts_user_id
    ON credit_receipts(user_id);

-- Existing installations historically stored signup bonuses and confirmed
-- purchases only in admin_users.credits. Record exactly the current difference
-- once so ledger SUM(amount) becomes equal to the persisted cache.
WITH ledger_balances AS (
    SELECT user_id, COALESCE(SUM(amount), 0)::INTEGER AS balance
    FROM credit_ledger
    GROUP BY user_id
), reconciliation AS (
    SELECT
        account.id AS user_id,
        account.credits - COALESCE(ledger.balance, 0) AS delta
    FROM admin_users AS account
    LEFT JOIN ledger_balances AS ledger ON ledger.user_id = account.id
)
INSERT INTO credit_ledger (
    user_id,
    type,
    amount,
    reason,
    provider,
    provider_tx_id
)
SELECT
    user_id,
    'balance_reconciliation',
    delta,
    'Migration 011: persisted cache reconciled with append-only ledger',
    'system',
    NULL
FROM reconciliation
WHERE delta <> 0;

COMMIT;
