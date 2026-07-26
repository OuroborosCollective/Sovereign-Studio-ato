-- Separate direct FreeLLM quota eligibility from paid provider pricing.
-- OpenRouter and other paid routes keep their strict pricing evidence untouched.
-- Existing FreeLLM receipt-v1 routes fail closed until a fresh revision-bound
-- double canary recreates them under the receipt-v2 quota contract.
BEGIN;

UPDATE llm_routes
SET disabled = true,
    credits_per_unit = 0,
    tier = 'free',
    config = (
        config
        - 'inputUsdPerMillion'
        - 'cachedInputUsdPerMillion'
        - 'outputUsdPerMillion'
        - 'pricingSource'
        - 'pricingEvidence'
    ) || jsonb_build_object(
        'billingCategory', 'free',
        'billingClass', 'free',
        'fundingMode', 'provider_free_quota',
        'markupMultiplier', 0,
        'minimumMultiplier', 0,
        'providerPricingRequired', false,
        'pricingVerified', false,
        'freeEligible', false,
        'quotaContractVerified', false,
        'userChargeCredits', 0,
        'providerCostState', COALESCE(
            config->>'providerCostState',
            config->'pricingEvidence'->>'canaryCostState',
            'unreported'
        ),
        'revolverEligible', false,
        'certificationState', 'recheck_required'
    ),
    updated_at = NOW()
WHERE lower(COALESCE(runtime_kind, provider)) = 'freellm'
  AND COALESCE(config->>'routingOwner', '') = 'free-revolver-v3';

DO $migration$
BEGIN
    IF to_regclass('llm_revolver_provider_models') IS NOT NULL
       AND to_regclass('llm_routes') IS NOT NULL THEN
        ALTER TABLE llm_revolver_provider_models
            ADD COLUMN IF NOT EXISTS free_eligible BOOLEAN NOT NULL DEFAULT false,
            ADD COLUMN IF NOT EXISTS eligibility_source TEXT NOT NULL DEFAULT 'unverified',
            ADD COLUMN IF NOT EXISTS eligibility_verified_at TIMESTAMPTZ;

        UPDATE llm_revolver_provider_models AS model
        SET status = 'discovered',
            enabled = false,
            free_eligible = false,
            eligibility_source = 'migration-042-recheck-required',
            eligibility_verified_at = NULL,
            pricing_verified_at = NULL,
            last_error_code = 'freellm_quota_contract_recheck_required',
            updated_at = NOW()
        WHERE model.litellm_alias IS NOT NULL
          AND EXISTS (
              SELECT 1
              FROM llm_routes AS route
              WHERE route.model_id = model.litellm_alias
                AND lower(COALESCE(route.runtime_kind, route.provider)) = 'freellm'
                AND COALESCE(route.config->>'routingOwner', '') = 'free-revolver-v3'
          );
    END IF;
END
$migration$;

DO $migration_ledger$
DECLARE
    ledger_columns TEXT[];
BEGIN
    IF to_regclass(format('%I.schema_migrations', current_schema())) IS NULL THEN
        RAISE EXCEPTION 'Migration 042 blocked: schema_migrations is missing';
    END IF;

    SELECT COALESCE(array_agg(column_name ORDER BY ordinal_position), ARRAY[]::TEXT[])
    INTO ledger_columns
    FROM information_schema.columns
    WHERE table_schema = current_schema()
      AND table_name = 'schema_migrations';

    IF ledger_columns @> ARRAY['version', 'applied_at']::TEXT[]
       AND NOT ledger_columns @> ARRAY['id', 'name']::TEXT[] THEN
        INSERT INTO schema_migrations (version, applied_at)
        VALUES ('042', NOW())
        ON CONFLICT (version) DO NOTHING;
    ELSIF ledger_columns @> ARRAY['version']::TEXT[]
          AND NOT ledger_columns @> ARRAY['id', 'name']::TEXT[] THEN
        INSERT INTO schema_migrations (version)
        VALUES ('042')
        ON CONFLICT (version) DO NOTHING;
    ELSIF ledger_columns @> ARRAY['id', 'name']::TEXT[]
          AND NOT ledger_columns @> ARRAY['version']::TEXT[] THEN
        INSERT INTO schema_migrations (id, name)
        VALUES (42, 'separate_freellm_quota_from_provider_pricing')
        ON CONFLICT (id) DO NOTHING;
    ELSE
        RAISE EXCEPTION 'Migration 042 blocked: unsupported schema_migrations layout: %', ledger_columns;
    END IF;
END
$migration_ledger$;

COMMIT;
