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

COMMIT;
