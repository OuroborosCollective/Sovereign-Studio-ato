-- Sovereign Verification Gateway: persisted receipts plus additive credit-ledger type reconciliation.
BEGIN;

CREATE TABLE IF NOT EXISTS verification_receipts (
    request_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    request_fingerprint TEXT NOT NULL CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
    claim_sha256 TEXT NOT NULL CHECK (claim_sha256 ~ '^[0-9a-f]{64}$'),
    route TEXT NOT NULL CHECK (route IN (
        'formal computation',
        'runtime readback',
        'source provenance',
        'federated receipt',
        'unknown'
    )),
    verdict TEXT NOT NULL CHECK (verdict IN (
        'PROVEN',
        'CONTRADICTED',
        'UNPROVEN',
        'EVIDENCE_PRESENT_REVIEW_REQUIRED'
    )),
    receipt_sha256 TEXT NOT NULL UNIQUE CHECK (receipt_sha256 ~ '^[0-9a-f]{64}$'),
    receipt JSONB NOT NULL,
    charged_credits INTEGER NOT NULL DEFAULT 0 CHECK (charged_credits >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS verification_receipts_user_created_idx
    ON verification_receipts (user_id, created_at DESC);

DO $$
DECLARE
    constraint_definition TEXT;
BEGIN
    IF to_regclass(format('%I.credit_ledger', current_schema())) IS NULL THEN
        RAISE EXCEPTION 'credit_ledger does not exist';
    END IF;

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
       OR constraint_definition NOT LIKE '%verification_usage%'
       OR constraint_definition NOT LIKE '%agent_usage_reservation%'
       OR constraint_definition NOT LIKE '%agent_usage_adjustment%'
       OR constraint_definition NOT LIKE '%agent_usage_refund%'
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
                'usage',
                'agent_usage_reservation',
                'agent_usage_adjustment',
                'agent_usage_refund',
                'verification_usage'
            ));
    END IF;
END $$;

COMMIT;
