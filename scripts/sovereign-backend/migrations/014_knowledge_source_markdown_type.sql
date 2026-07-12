-- Extend the persisted knowledge source type contract for Markdown uploads.
-- Additive, idempotent and safe to re-run. Existing rows are not rewritten.
BEGIN;

DO $$
DECLARE
    constraint_row RECORD;
    compatible_constraint_count INTEGER := 0;
    source_type_constraint_count INTEGER := 0;
BEGIN
    IF to_regclass(format('%I.knowledge_sources', current_schema())) IS NULL THEN
        RAISE NOTICE 'knowledge_sources does not exist yet; Markdown type contract is not needed';
        RETURN;
    END IF;

    SELECT COUNT(*),
           COUNT(*) FILTER (
               WHERE pg_get_constraintdef(constraint_item.oid) LIKE '%''markdown''%'
                 AND pg_get_constraintdef(constraint_item.oid) LIKE '%''github''%'
                 AND pg_get_constraintdef(constraint_item.oid) LIKE '%''wikipedia''%'
                 AND pg_get_constraintdef(constraint_item.oid) LIKE '%''pdf''%'
                 AND pg_get_constraintdef(constraint_item.oid) LIKE '%''text''%'
                 AND pg_get_constraintdef(constraint_item.oid) LIKE '%''code''%'
           )
    INTO source_type_constraint_count, compatible_constraint_count
    FROM pg_constraint AS constraint_item
    JOIN pg_class AS relation_item
      ON relation_item.oid = constraint_item.conrelid
    JOIN pg_namespace AS namespace_item
      ON namespace_item.oid = relation_item.relnamespace
    WHERE namespace_item.nspname = current_schema()
      AND relation_item.relname = 'knowledge_sources'
      AND constraint_item.contype = 'c'
      AND pg_get_constraintdef(constraint_item.oid) LIKE '%source_type%';

    IF source_type_constraint_count = 1 AND compatible_constraint_count = 1 THEN
        RETURN;
    END IF;

    FOR constraint_row IN
        SELECT constraint_item.conname
        FROM pg_constraint AS constraint_item
        JOIN pg_class AS relation_item
          ON relation_item.oid = constraint_item.conrelid
        JOIN pg_namespace AS namespace_item
          ON namespace_item.oid = relation_item.relnamespace
        WHERE namespace_item.nspname = current_schema()
          AND relation_item.relname = 'knowledge_sources'
          AND constraint_item.contype = 'c'
          AND pg_get_constraintdef(constraint_item.oid) LIKE '%source_type%'
    LOOP
        EXECUTE format(
            'ALTER TABLE %I.knowledge_sources DROP CONSTRAINT %I',
            current_schema(),
            constraint_row.conname
        );
    END LOOP;

    ALTER TABLE knowledge_sources
        ADD CONSTRAINT knowledge_sources_source_type_check
        CHECK (source_type IN (
            'github',
            'wikipedia',
            'pdf',
            'text',
            'code',
            'markdown'
        )) NOT VALID;

    ALTER TABLE knowledge_sources
        VALIDATE CONSTRAINT knowledge_sources_source_type_check;
END $$;

COMMIT;
