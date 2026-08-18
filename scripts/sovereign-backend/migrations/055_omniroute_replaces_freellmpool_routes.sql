-- Keep the managed FreeLLMAPI route intact and replace only the retired
-- FreeLLMPool route source with an OmniRoute `auto` candidate.
-- The candidate is deliberately fail-closed until the deployed runtime performs
-- two real chat-completion canaries on the exact source revision/image digest.
BEGIN;

DO $migration$
DECLARE
    omniroute_source_id CONSTANT UUID := '0609e75c-8c48-59db-80a4-3155b823205b';
    omniroute_model_id CONSTANT UUID := '1d001977-d93c-5c78-ae36-567af97101b4';
    omniroute_base CONSTANT TEXT := 'http://omniroute:20128/v1';
    retired_pool_base CONSTANT TEXT := 'http://freellmpool:8080/v1';
BEGIN
    UPDATE llm_revolver_provider_sources
    SET enabled=false,
        status='disabled',
        last_error_code='freellmpool_replaced_by_omniroute',
        updated_at=NOW()
    WHERE lower(api_base)=lower(retired_pool_base);

    UPDATE llm_revolver_provider_models AS model
    SET enabled=false,
        status='disabled',
        last_error_code='freellmpool_replaced_by_omniroute',
        updated_at=NOW()
    WHERE EXISTS (
        SELECT 1
        FROM llm_revolver_provider_sources AS source
        WHERE source.id=model.source_id
          AND lower(source.api_base)=lower(retired_pool_base)
    );

    UPDATE llm_routes
    SET disabled=true,
        config=COALESCE(config, '{}'::jsonb) || jsonb_build_object(
            'executionRetired', true,
            'executionRetirementFamily', 'freellmpool_replaced_by_omniroute',
            'replacementRouteSource', 'omniroute'
        ),
        updated_at=NOW()
    WHERE lower(COALESCE(base_url, ''))=lower(retired_pool_base);

    INSERT INTO llm_revolver_provider_sources (
        id, label, api_base, models_url, auth_mode, status,
        last_error_code, enabled, updated_at
    ) VALUES (
        omniroute_source_id,
        'OmniRoute Free Routes',
        omniroute_base,
        omniroute_base || '/models',
        'none',
        'probing',
        'omniroute_runtime_double_canary_required',
        true,
        NOW()
    )
    ON CONFLICT (id) DO UPDATE SET
        label=EXCLUDED.label,
        api_base=EXCLUDED.api_base,
        models_url=EXCLUDED.models_url,
        auth_mode='none',
        status='probing',
        last_error_code='omniroute_runtime_double_canary_required',
        enabled=true,
        updated_at=NOW();

    INSERT INTO llm_revolver_provider_models (
        id, source_id, upstream_model_id, display_name, litellm_alias,
        capabilities, free_verified, pricing_source,
        discovery_payload_sha256, status, last_error_code, enabled,
        free_eligible, eligibility_source, eligibility_verified_at,
        pricing_verified_at, updated_at
    ) VALUES (
        omniroute_model_id,
        omniroute_source_id,
        'auto',
        'OmniRoute Auto',
        'sovereign-omniroute:auto',
        '["chat"]'::jsonb,
        false,
        'provider-free-quota-no-price',
        'e5931a7b93e0ea7ee152d64095d4f840779993f3fd0fbd0e6aabcfbce44ffa71',
        'discovered',
        'omniroute_runtime_double_canary_required',
        false,
        false,
        'omniroute-runtime-double-canary-required',
        NULL,
        NULL,
        NOW()
    )
    ON CONFLICT (source_id, upstream_model_id) DO UPDATE SET
        display_name=EXCLUDED.display_name,
        litellm_alias=EXCLUDED.litellm_alias,
        capabilities=EXCLUDED.capabilities,
        free_verified=false,
        pricing_source=EXCLUDED.pricing_source,
        status='discovered',
        last_error_code='omniroute_runtime_double_canary_required',
        enabled=false,
        free_eligible=false,
        eligibility_source='omniroute-runtime-double-canary-required',
        eligibility_verified_at=NULL,
        pricing_verified_at=NULL,
        updated_at=NOW();

    INSERT INTO llm_routes (
        id, model_id, model_name, provider, base_url, credits_per_unit,
        disabled, priority, runtime_kind, tier, config, updated_at
    ) VALUES (
        'sovereign-omniroute-auto',
        'sovereign-omniroute:auto',
        'OmniRoute Auto',
        'freellm',
        omniroute_base,
        0,
        true,
        35,
        'freellm',
        'free',
        jsonb_build_object(
            'transport', 'freellm',
            'routeSource', 'omniroute',
            'sourceType', 'omniroute',
            'providerModel', 'auto',
            'direct', true,
            'routingOwner', 'free-revolver-v3',
            'billingCategory', 'free',
            'billingClass', 'free',
            'fundingMode', 'provider_free_quota',
            'providerPricingRequired', false,
            'pricingVerified', false,
            'freeEligible', false,
            'quotaContractVerified', false,
            'canaryVerified', false,
            'canaryConfirmationCount', 0,
            'catalogVerified', false,
            'transportCanaryVerified', false,
            'selectable', false,
            'userChargeCredits', 0,
            'markupMultiplier', 0,
            'minimumMultiplier', 0,
            'executionProfile', 'free_single_agent',
            'resolverMode', 'revolver',
            'maxForegroundAgents', 1,
            'maxBackgroundAgents', 0,
            'repositoryExecutionAllowed', true,
            'quotaScope', 'freellm:omniroute:auto',
            'quotaEvidence', jsonb_build_object(
                'scope', 'freellm:omniroute:auto',
                'stateOwner', 'postgresql-revolver-state'
            ),
            'activationState', 'runtime-double-canary-required'
        ),
        NOW()
    )
    ON CONFLICT (model_id) DO UPDATE SET
        model_name=EXCLUDED.model_name,
        provider='freellm',
        base_url=omniroute_base,
        credits_per_unit=0,
        disabled=true,
        priority=EXCLUDED.priority,
        runtime_kind='freellm',
        tier='free',
        config=EXCLUDED.config,
        updated_at=NOW();
END
$migration$;

INSERT INTO schema_migrations (id, name)
VALUES (55, 'omniroute_replaces_freellmpool_routes')
ON CONFLICT (id) DO NOTHING;

COMMIT;
