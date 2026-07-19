-- Repair duplicate credit packages and close billing/idempotency schema drift.
BEGIN;

-- Historical transactions tables predate provider receipt evidence.
ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS provider TEXT,
    ADD COLUMN IF NOT EXISTS provider_tx_id TEXT,
    ADD COLUMN IF NOT EXISTS metadata JSONB,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE UNIQUE INDEX IF NOT EXISTS uq_transactions_provider_receipt
    ON transactions (provider, provider_tx_id)
    WHERE provider IS NOT NULL AND provider_tx_id IS NOT NULL;

-- Bind idempotency keys to the exact normalized request content.
ALTER TABLE IF EXISTS credit_receipts
    ADD COLUMN IF NOT EXISTS request_fingerprint TEXT;

-- Keep the newest configured package for each exact name and remove only
-- duplicate rows. The retained UUID remains a valid purchase target.
WITH ranked AS (
    SELECT id,
           ROW_NUMBER() OVER (
               PARTITION BY name
               ORDER BY created_at DESC, id DESC
           ) AS row_number
    FROM credit_packages
)
DELETE FROM credit_packages AS package
USING ranked
WHERE package.id = ranked.id
  AND ranked.row_number > 1;

CREATE UNIQUE INDEX IF NOT EXISTS uq_credit_packages_name
    ON credit_packages (name);

COMMIT;
