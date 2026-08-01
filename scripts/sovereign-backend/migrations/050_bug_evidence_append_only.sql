-- Migration 050: Bug Evidence Lane database append-only enforcement
-- Issue #1111 requires invalidation and supersession to create successor rows;
-- canonical evidence cases may never be updated or deleted in place.

BEGIN;

CREATE OR REPLACE FUNCTION bug_evidence_reject_canonical_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'BUG_EVIDENCE_APPEND_ONLY_VIOLATION:%:%', TG_TABLE_NAME, TG_OP;
END
$$;

DO $$
BEGIN
    IF to_regclass('public.bug_evidence_cases') IS NULL THEN
        RAISE NOTICE 'bug_evidence_cases is not present in this isolated preview scope';
    ELSIF NOT EXISTS (
        SELECT 1
          FROM pg_trigger
         WHERE tgname = 'bug_evidence_cases_append_only'
           AND tgrelid = to_regclass('public.bug_evidence_cases')
           AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER bug_evidence_cases_append_only
            BEFORE UPDATE OR DELETE ON bug_evidence_cases
            FOR EACH ROW EXECUTE FUNCTION bug_evidence_reject_canonical_mutation();
    END IF;
END
$$;

COMMIT;
