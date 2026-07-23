-- Preserve exact customer credit rates for low-cost OpenRouter models.
-- Provider prices are USD per million tokens; credits_per_unit is the public
-- customer rate per one thousand tokens. NUMERIC(10,4) rounded valid rates and
-- created catalog drift, so widen precision and normalize from persisted truth.
BEGIN;

DO $migration$
BEGIN
  IF to_regclass('llm_routes') IS NOT NULL THEN
    ALTER TABLE llm_routes
      ALTER COLUMN credits_per_unit TYPE NUMERIC(18,12)
      USING credits_per_unit::numeric(18,12);

    UPDATE llm_routes
    SET credits_per_unit = ROUND(
          (config->>'outputUsdPerMillion')::numeric
          * (config->>'markupMultiplier')::numeric
          / 1000,
          12
        ),
        updated_at = NOW()
    WHERE lower(COALESCE(runtime_kind, provider)) = 'openrouter'
      AND COALESCE(config->>'outputUsdPerMillion', '') ~ '^[0-9]+(\.[0-9]+)?$'
      AND COALESCE(config->>'markupMultiplier', '') ~ '^[0-9]+$';
  END IF;
END
$migration$;

DO $migration_registry$
BEGIN
  IF to_regclass('schema_migrations') IS NOT NULL THEN
    IF EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = current_schema()
        AND table_name = 'schema_migrations'
        AND column_name = 'id'
    ) AND EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = current_schema()
        AND table_name = 'schema_migrations'
        AND column_name = 'name'
    ) THEN
      EXECUTE $sql$
        INSERT INTO schema_migrations (id, name)
        VALUES (39, 'openrouter_credit_rate_precision')
        ON CONFLICT (id) DO NOTHING
      $sql$;
    ELSIF EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = current_schema()
        AND table_name = 'schema_migrations'
        AND column_name = 'version'
    ) THEN
      EXECUTE $sql$
        INSERT INTO schema_migrations (version)
        VALUES ('20260723130039')
        ON CONFLICT (version) DO NOTHING
      $sql$;
    END IF;
  END IF;
END
$migration_registry$;

COMMIT;
