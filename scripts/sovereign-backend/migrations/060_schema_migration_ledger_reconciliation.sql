-- Reconcile Sovereign's own migration ledger without rewriting historical migrations.
-- Versions 056-059 were applied idempotently by auto-migrate but did not self-record.
-- The live estate also contains long-form external/historical migration versions, so
-- this migration touches only the bounded Sovereign 56-59 identities.
BEGIN;

DO $migration$
DECLARE
    migration_ids CONSTANT integer[] := ARRAY[56, 57, 58, 59];
    migration_names CONSTANT text[] := ARRAY[
        'evidence_observatory_publication_receipts_v2',
        'durable_workflow_permission_receipts',
        'wolfram_cag_partner_analysis',
        'live_workspace_chat_bubbles'
    ];
    has_version boolean;
    has_id boolean;
    has_name boolean;
    item_index integer;
BEGIN
    IF to_regclass('public.schema_migrations') IS NULL THEN
        RAISE EXCEPTION 'schema_migrations table is missing';
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema=current_schema()
          AND table_name='schema_migrations'
          AND column_name='version'
    ) INTO has_version;
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema=current_schema()
          AND table_name='schema_migrations'
          AND column_name='id'
    ) INTO has_id;
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema=current_schema()
          AND table_name='schema_migrations'
          AND column_name='name'
    ) INTO has_name;

    IF has_version THEN
        FOR item_index IN 1..array_length(migration_ids, 1) LOOP
            EXECUTE
                'INSERT INTO schema_migrations (version) VALUES ($1) ON CONFLICT (version) DO NOTHING'
                USING migration_ids[item_index]::text;
        END LOOP;
    ELSIF has_id AND has_name THEN
        FOR item_index IN 1..array_length(migration_ids, 1) LOOP
            EXECUTE
                'INSERT INTO schema_migrations (id, name) VALUES ($1, $2) ON CONFLICT (id) DO NOTHING'
                USING migration_ids[item_index], migration_names[item_index];
        END LOOP;
    ELSE
        RAISE EXCEPTION 'unsupported schema_migrations layout';
    END IF;
END
$migration$;

-- Keep the standard self-registration shape so migration_ledger_adapter.py can
-- translate this final marker on version-only historical databases.
INSERT INTO schema_migrations (id, name)
VALUES (60, 'schema_migration_ledger_reconciliation')
ON CONFLICT (id) DO NOTHING;

COMMIT;
