-- Reconcile historical credit_ledger CHECK constraints with every ledger type
-- used by the current runtime and migrations. Additive, idempotent and safe to
-- re-run. Existing append-only rows are never rewritten or deleted.
BEGIN;

DO $$
DECLARE
    constraint_definition TEXT;
BEGIN
    IF to_regclass(format('%I.credit_ledger', current_schema())) IS NULL THEN
        RAISE NOTICE 'credit_ledger does not exist yet; type contract repair is not needed';
        RETURN;
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

COMMIT;
