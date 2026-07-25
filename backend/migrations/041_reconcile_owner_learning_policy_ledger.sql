-- Reconcile migration 028 with the live migration ledger without replaying its
-- table or policy mutations.
-- Bound source: scripts/sovereign-backend/migrations/028_owner_learning_policy.sql
-- Bound source SHA-256: 38d1a58f762e9622f37b41e9cb46711c20fabb4151b9bee6930e78b27da3d61e
BEGIN;

DO $migration_reconcile$
DECLARE
  ledger_columns TEXT[];
  policy_columns TEXT[];
  policy_rows BIGINT;
  enabled_policy_rows BIGINT;
  canonical_policy_rows BIGINT;
BEGIN
  IF to_regclass(format('%I.owner_learning_policies', current_schema())) IS NULL THEN
    RAISE EXCEPTION 'Migration 028 reconciliation blocked: owner_learning_policies is missing';
  END IF;

  SELECT COALESCE(array_agg(column_name ORDER BY ordinal_position), ARRAY[]::TEXT[])
  INTO policy_columns
  FROM information_schema.columns
  WHERE table_schema = current_schema()
    AND table_name = 'owner_learning_policies';

  IF NOT policy_columns @> ARRAY[
    'owner_admin_id',
    'auto_accept_useful_unique',
    'policy_source',
    'created_at',
    'updated_at'
  ]::TEXT[] THEN
    RAISE EXCEPTION 'Migration 028 reconciliation blocked: owner_learning_policies layout mismatch: %', policy_columns;
  END IF;

  SELECT COUNT(*),
         COUNT(*) FILTER (WHERE auto_accept_useful_unique IS TRUE),
         COUNT(*) FILTER (
           WHERE auto_accept_useful_unique IS TRUE
             AND policy_source = 'owner-explicit-2026-07-20'
         )
  INTO policy_rows, enabled_policy_rows, canonical_policy_rows
  FROM owner_learning_policies;

  IF policy_rows <> 1 OR enabled_policy_rows <> 1 OR canonical_policy_rows <> 1 THEN
    RAISE EXCEPTION
      'Migration 028 reconciliation blocked: expected exactly one canonical enabled owner policy, got total=%, enabled=%, canonical=%',
      policy_rows,
      enabled_policy_rows,
      canonical_policy_rows;
  END IF;

  IF to_regclass(format('%I.schema_migrations', current_schema())) IS NULL THEN
    RAISE EXCEPTION 'Migration 028 reconciliation blocked: schema_migrations is missing';
  END IF;

  SELECT COALESCE(array_agg(column_name ORDER BY ordinal_position), ARRAY[]::TEXT[])
  INTO ledger_columns
  FROM information_schema.columns
  WHERE table_schema = current_schema()
    AND table_name = 'schema_migrations';

  IF ledger_columns @> ARRAY['version', 'applied_at']::TEXT[]
     AND NOT ledger_columns @> ARRAY['id', 'name']::TEXT[] THEN
    INSERT INTO schema_migrations (version, applied_at)
    VALUES ('028', NOW()), ('041', NOW())
    ON CONFLICT (version) DO NOTHING;
  ELSIF ledger_columns @> ARRAY['version']::TEXT[]
        AND NOT ledger_columns @> ARRAY['id', 'name']::TEXT[] THEN
    INSERT INTO schema_migrations (version)
    VALUES ('028'), ('041')
    ON CONFLICT (version) DO NOTHING;
  ELSIF ledger_columns @> ARRAY['id', 'name']::TEXT[]
        AND NOT ledger_columns @> ARRAY['version']::TEXT[] THEN
    INSERT INTO schema_migrations (id, name)
    VALUES
      (28, 'owner_learning_policy'),
      (41, 'reconcile_owner_learning_policy_ledger')
    ON CONFLICT (id) DO NOTHING;
  ELSE
    RAISE EXCEPTION 'Migration 028 reconciliation blocked: unsupported schema_migrations layout: %', ledger_columns;
  END IF;
END
$migration_reconcile$;

COMMIT;
