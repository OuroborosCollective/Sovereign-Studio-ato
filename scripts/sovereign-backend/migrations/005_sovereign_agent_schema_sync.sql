-- Migration: 005_sovereign_agent_schema_sync
-- Description: Add new draft_pr fields to StoredSovereignAgentJob and SovereignAgentJobResult
-- Created: 2026-07-08
-- Author: Sovereign Agent Runtime

-- This migration adds explicit tracking columns for draft PR state.
-- The columns were partially added in migration 004 but not fully utilized in code.
-- This migration ensures the code schema matches the database schema.

-- Add migration record
DO $$
BEGIN
    RAISE NOTICE 'Migration 005: Schema sync for draft PR preparation fields';
    RAISE NOTICE 'Columns already exist in sovereign_agent_jobs:';
    RAISE NOTICE '  - draft_pr_preparation (jsonb)';
    RAISE NOTICE '  - branch_name (text)';
    RAISE NOTICE '  - target_branch (text)';
    RAISE NOTICE '  - commit_message (text)';
    RAISE NOTICE '  - pr_url (text)';
    RAISE NOTICE '  - pr_state (text)';
    RAISE NOTICE 'Code updated to use these fields in StoredSovereignAgentJob and SovereignAgentJobResult';
END $$;

-- Verify all columns exist
DO $$
DECLARE
    expected_cols TEXT[] := ARRAY[
        'draft_pr_preparation',
        'branch_name',
        'target_branch',
        'commit_message',
        'pr_url',
        'pr_state'
    ];
    col TEXT;
    missing_cols TEXT[] := '{}';
BEGIN
    FOREACH col IN ARRAY expected_cols
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'sovereign_agent_jobs' 
            AND column_name = col
        ) THEN
            missing_cols := missing_cols || col;
        END IF;
    END LOOP;
    
    IF array_length(missing_cols, 1) > 0 THEN
        RAISE EXCEPTION 'Missing columns: %', missing_cols;
    ELSE
        RAISE NOTICE 'All expected columns verified in sovereign_agent_jobs';
    END IF;
END $$;

-- Insert the migration record using only columns that exist in the real
-- schema_migrations layout. Historical installations may expose only version,
-- while newer layouts use id/name and optionally applied_at.
DO $$
DECLARE
    ledger_columns TEXT[];
BEGIN
    IF to_regclass(format('%I.schema_migrations', current_schema())) IS NULL THEN
        RAISE NOTICE 'schema_migrations does not exist; migration ledger write skipped';
        RETURN;
    END IF;

    SELECT array_agg(column_name ORDER BY ordinal_position)
    INTO ledger_columns
    FROM information_schema.columns
    WHERE table_schema = current_schema()
      AND table_name = 'schema_migrations';

    IF ledger_columns @> ARRAY['version', 'applied_at']::TEXT[] THEN
        EXECUTE
            'INSERT INTO schema_migrations (version, applied_at) '
            'VALUES ($1, NOW()) ON CONFLICT (version) DO NOTHING'
        USING '005';
    ELSIF ledger_columns @> ARRAY['version']::TEXT[] THEN
        EXECUTE
            'INSERT INTO schema_migrations (version) '
            'VALUES ($1) ON CONFLICT (version) DO NOTHING'
        USING '005';
    ELSIF ledger_columns @> ARRAY['id', 'name']::TEXT[] THEN
        EXECUTE
            'INSERT INTO schema_migrations (id, name) '
            'VALUES ($1, $2) ON CONFLICT (id) DO NOTHING'
        USING 5, 'migration_005';
    ELSE
        RAISE EXCEPTION 'Unsupported schema_migrations layout: %', ledger_columns;
    END IF;
END $$;
