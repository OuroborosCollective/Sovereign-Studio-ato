-- Restore only evidence-backed direct FreeLLM routes after legacy migration replay.
-- Migration 021 predates the direct FreeLLM transport and disables every
-- non-LiteLLM route whenever the full migration directory is replayed at boot.
-- This final reconciliation is deliberately narrow: it can only re-enable a
-- managed direct FreeLLM route whose provider model is still persisted as
-- ready, enabled, free-verified and double-canary confirmed.
BEGIN;

DO $migration$
BEGIN
    IF to_regclass('llm_routes') IS NOT NULL
       AND to_regclass('llm_revolver_provider_models') IS NOT NULL
       AND to_regclass('llm_revolver_provider_sources') IS NOT NULL THEN
        EXECUTE $reconcile$
            UPDATE llm_routes AS route
            SET disabled = false,
                provider = 'freellm',
                runtime_kind = 'freellm',
                base_url = source.api_base,
                updated_at = NOW()
            FROM llm_revolver_provider_models AS model
            JOIN llm_revolver_provider_sources AS source
              ON source.id = model.source_id
            WHERE route.model_id = model.litellm_alias
              AND source.enabled = true
              AND source.auth_mode = 'managed-bearer'
              AND source.last_http_status = 200
              AND model.status = 'ready'
              AND model.enabled = true
              AND model.free_verified = true
              AND model.pricing_verified_at IS NOT NULL
              AND model.last_canary_at IS NOT NULL
              AND model.last_error_code IS NULL
              AND route.config->>'revolverProviderSourceId' = source.id::text
              AND COALESCE(route.config->>'transport', '') = 'freellm'
              AND COALESCE(route.config->>'direct', 'false') = 'true'
              AND COALESCE(
                    route.config->>'billingCategory',
                    route.config->>'billingClass',
                    ''
                  ) = 'free'
              AND COALESCE(route.config->>'fundingMode', '') = 'verified_zero_cost'
              AND COALESCE(route.config->>'pricingVerified', 'false') = 'true'
              AND COALESCE(route.config->>'canaryVerified', 'false') = 'true'
              AND COALESCE(route.config->>'executionProfile', '') = 'free_single_agent'
              AND COALESCE(route.config->>'resolverMode', '') = 'revolver'
              AND COALESCE(route.config->>'canaryConfirmationCount', '') ~ '^[0-9]+$'
              AND (route.config->>'canaryConfirmationCount')::integer >= 2
        $reconcile$;
    END IF;
END
$migration$;

INSERT INTO schema_migrations (id, name)
VALUES (37, 'reenable_verified_direct_freellm_routes')
ON CONFLICT (id) DO NOTHING;

COMMIT;
