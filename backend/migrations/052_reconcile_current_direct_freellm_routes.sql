-- Reconcile evidence-backed direct FreeLLM routes to the current v3 contract.
--
-- Historical migration 037 used the old `verified_zero_cost` / pricingVerified=true
-- semantics. The current billing contract is provider_free_quota and explicitly
-- requires pricingVerified=false for free routes. This migration repairs only
-- rows that already carry revision-bound double-canary evidence; it does not
-- fabricate runtime identity, receipts, eligibility, or provider health.
BEGIN;

DO $migration$
BEGIN
    IF to_regclass('llm_routes') IS NOT NULL
       AND to_regclass('llm_revolver_provider_models') IS NOT NULL
       AND to_regclass('llm_revolver_provider_sources') IS NOT NULL THEN
        EXECUTE $reconcile$
            UPDATE llm_routes AS route
            SET provider = 'freellm',
                runtime_kind = 'freellm',
                base_url = source.api_base,
                disabled = false,
                config = route.config || jsonb_build_object(
                    'transport', 'freellm',
                    'direct', true,
                    'providerModel', model.upstream_model_id,
                    'billingCategory', 'free',
                    'billingClass', 'free',
                    'fundingMode', 'provider_free_quota',
                    'pricingVerified', false,
                    'freeEligible', true,
                    'quotaContractVerified', true,
                    'userChargeCredits', 0,
                    'markupMultiplier', 0,
                    'executionProfile', 'free_single_agent',
                    'resolverMode', 'revolver'
                ),
                updated_at = NOW()
            FROM llm_revolver_provider_models AS model
            JOIN llm_revolver_provider_sources AS source
              ON source.id = model.source_id
            WHERE route.model_id = model.litellm_alias
              AND source.enabled = true
              AND source.auth_mode = 'managed-bearer'
              AND source.api_base IN (
                    'http://freellmapi:3001/v1',
                    'http://freellmpool:8080/v1'
                  )
              AND source.last_http_status = 200
              AND model.status = 'ready'
              AND model.enabled = true
              AND model.free_eligible = true
              AND model.eligibility_verified_at IS NOT NULL
              AND model.last_canary_at IS NOT NULL
              AND model.last_error_code IS NULL
              AND COALESCE(route.config->>'routingOwner', '') = 'free-revolver-v3'
              AND COALESCE(route.config->>'canaryVerified', 'false') = 'true'
              AND COALESCE(route.config->>'canaryConfirmationCount', '') ~ '^[0-9]+$'
              AND (route.config->>'canaryConfirmationCount')::integer >= 2
              AND route.config->'runtimeIdentity'->>'sourceRevisionVerified' = 'true'
              AND route.config->'runtimeIdentity'->>'imageDigestVerified' = 'true'
              AND route.config->'runtimeIdentity'->>'sourceRevision' ~ '^[0-9a-f]{40}$'
              AND route.config->'runtimeIdentity'->>'imageDigest' ~ '^sha256:[0-9a-f]{64}$'
              AND route.config->'canaryReceipt'->>'schemaVersion' =
                    'sovereign.freellm-route-receipt.v3'
              AND route.config->'canaryReceipt'->>'generalChatEvidenceVerified' = 'true'
              AND route.config->'canaryReceipt'->>'receiptSha256' ~ '^[0-9a-f]{64}$'
        $reconcile$;
    END IF;
END
$migration$;

INSERT INTO schema_migrations (id, name)
VALUES (52, 'reconcile_current_direct_freellm_routes')
ON CONFLICT (id) DO NOTHING;

COMMIT;
