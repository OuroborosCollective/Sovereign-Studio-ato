-- 053_llm_usage_credit_ledger_types.sql
-- Reconcile the append-only credit ledger with the direct paid LLM reservation
-- types already emitted by the runtime. Existing rows are never rewritten.
BEGIN;

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
       OR constraint_definition NOT LIKE '%llm_usage_reservation%'
       OR constraint_definition NOT LIKE '%llm_usage_adjustment%'
       OR constraint_definition NOT LIKE '%llm_usage_refund%'
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
                'verification_usage',
                'llm_usage_reservation',
                'llm_usage_adjustment',
                'llm_usage_refund'
            ));
    END IF;
END $$;

COMMIT;
