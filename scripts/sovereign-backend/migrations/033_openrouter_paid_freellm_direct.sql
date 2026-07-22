-- Split paid OpenRouter and free direct-FreeLLM transports.
-- Historical LiteLLM rows remain intact for audit and bounded rollback.
BEGIN;

ALTER TABLE llm_usage_settlements
    ADD COLUMN IF NOT EXISTS requested_mode TEXT,
    ADD COLUMN IF NOT EXISTS execution_role TEXT,
    ADD COLUMN IF NOT EXISTS resolved_transport TEXT,
    ADD COLUMN IF NOT EXISTS fallback_from_transport TEXT,
    ADD COLUMN IF NOT EXISTS provider_generation_id TEXT,
    ADD COLUMN IF NOT EXISTS provider_cost_source TEXT,
    ADD COLUMN IF NOT EXISTS route_snapshot_sha256 TEXT,
    ADD COLUMN IF NOT EXISTS price_snapshot_sha256 TEXT;

ALTER TABLE llm_usage_settlements
    DROP CONSTRAINT IF EXISTS llm_usage_requested_mode_check;
ALTER TABLE llm_usage_settlements
    ADD CONSTRAINT llm_usage_requested_mode_check
    CHECK (requested_mode IS NULL OR requested_mode IN ('auto', 'paid', 'free'));

ALTER TABLE llm_usage_settlements
    DROP CONSTRAINT IF EXISTS llm_usage_execution_role_check;
ALTER TABLE llm_usage_settlements
    ADD CONSTRAINT llm_usage_execution_role_check
    CHECK (execution_role IS NULL OR execution_role IN ('main', 'swarm_agents'));

ALTER TABLE llm_usage_settlements
    DROP CONSTRAINT IF EXISTS llm_usage_resolved_transport_check;
ALTER TABLE llm_usage_settlements
    ADD CONSTRAINT llm_usage_resolved_transport_check
    CHECK (
        resolved_transport IS NULL
        OR resolved_transport IN ('openrouter', 'freellm', 'litellm')
    );

ALTER TABLE llm_route_revolver_state
    ADD COLUMN IF NOT EXISTS quota_remaining NUMERIC,
    ADD COLUMN IF NOT EXISTS quota_limit NUMERIC,
    ADD COLUMN IF NOT EXISTS quota_reset_at TIMESTAMPTZ;

ALTER TABLE llm_route_revolver_state
    DROP CONSTRAINT IF EXISTS llm_route_revolver_quota_non_negative;
ALTER TABLE llm_route_revolver_state
    ADD CONSTRAINT llm_route_revolver_quota_non_negative
    CHECK (
        (quota_remaining IS NULL OR quota_remaining >= 0)
        AND (quota_limit IS NULL OR quota_limit >= 0)
    );

-- Revolver v3 sources that point at the private managed FreeLLM API become
-- direct routes. The historical litellm_alias column remains a route alias,
-- while providerModel stores the upstream model understood by FreeLLM.
UPDATE llm_routes AS route
SET provider = 'freellm',
    base_url = 'http://freellmapi:3001/v1',
    runtime_kind = 'freellm',
    config = COALESCE(route.config, '{}'::jsonb) || jsonb_build_object(
        'transport', 'freellm',
        'direct', true,
        'providerModel', model.upstream_model_id,
        'authMode', 'managed-bearer',
        'executionProfile', 'free_single_agent',
        'resolverMode', 'revolver',
        'maxForegroundAgents', 1,
        'maxBackgroundAgents', 0,
        'repositoryExecutionAllowed', true,
        'quotaScope', 'freellm:model:'
            || left(replace(model.source_id::text, '-', ''), 12)
            || ':' || left(md5(model.upstream_model_id), 12),
        'quotaEvidence', 'per-model-runtime-cooldown-and-provider-catalog'
    ),
    updated_at = NOW()
FROM llm_revolver_provider_models AS model
JOIN llm_revolver_provider_sources AS source ON source.id = model.source_id
WHERE route.model_id = model.litellm_alias
  AND lower(source.api_base) = 'http://freellmapi:3001/v1'
  AND source.auth_mode = 'managed-bearer'
  AND model.free_verified = true
  AND model.status = 'ready'
  AND model.enabled = true;

-- Pin the paid swarm model and current OpenRouter price snapshot. Activation
-- remains fail-closed until a protected key and completion canary are verified.
INSERT INTO llm_routes (
    id, model_id, model_name, provider, base_url, credits_per_unit,
    disabled, priority, runtime_kind, tier, config, updated_at
) VALUES (
    'openrouter-paid-gpt-5-4-mini',
    'sovereign-openrouter:openai/gpt-5.4-mini',
    'Sovereign OpenRouter GPT-5.4 Mini',
    'openrouter',
    'https://openrouter.ai/api/v1',
    18,
    true,
    10,
    'openrouter',
    'standard',
    jsonb_build_object(
        'transport', 'openrouter',
        'direct', true,
        'providerModel', 'openai/gpt-5.4-mini',
        'canonicalModelSlug', 'openai/gpt-5.4-mini-20260317',
        'billingCategory', 'standard',
        'billingClass', 'standard',
        'markupMultiplier', 4,
        'minimumMultiplier', 4,
        'fundingMode', 'provider_priced',
        'inputUsdPerMillion', 0.75,
        'cachedInputUsdPerMillion', 0.075,
        'outputUsdPerMillion', 4.50,
        'pricingVerified', true,
        'pricingSource', 'openrouter-models-api-2026-07-22',
        'pricingAuthority', 'openrouter-models-api',
        'usdMicrosPerCredit', 1000,
        'executionProfile', 'paid_swarm_6',
        'supportedExecutionRoles', jsonb_build_array('main', 'swarm_agents'),
        'resolverMode', 'selected-pair',
        'maxForegroundAgents', 1,
        'maxBackgroundAgents', 6,
        'repositoryExecutionAllowed', true,
        'quotaScope', 'openrouter:model:gpt-5-4-mini',
        'providerPolicy', jsonb_build_object(
            'require_parameters', true,
            'allow_fallbacks', false,
            'data_collection', 'deny',
            'zdr', true
        ),
        'catalogVerified', false,
        'transportCanaryVerified', false,
        'canaryVerified', false,
        'selectable', false,
        'activationState', 'protected-key-and-canary-required'
    ),
    NOW()
)
ON CONFLICT (model_id) DO UPDATE SET
    model_name = EXCLUDED.model_name,
    provider = EXCLUDED.provider,
    base_url = EXCLUDED.base_url,
    credits_per_unit = EXCLUDED.credits_per_unit,
    priority = EXCLUDED.priority,
    runtime_kind = EXCLUDED.runtime_kind,
    tier = EXCLUDED.tier,
    config = CASE
        WHEN COALESCE(llm_routes.config->>'canaryVerified', 'false') = 'true'
        THEN llm_routes.config
        ELSE EXCLUDED.config
    END,
    disabled = CASE
        WHEN COALESCE(llm_routes.config->>'canaryVerified', 'false') = 'true'
        THEN llm_routes.disabled
        ELSE true
    END,
    updated_at = NOW();

-- One credential/root deployment keeps owner-input and operator activation
-- compatible while the current OpenRouter catalog materializes as llm_routes.
INSERT INTO llm_provider_deployments (
    route_id, provider_name, provider_prefix, upstream_model_id,
    litellm_model_name, api_base, status, billing_category,
    markup_multiplier, input_usd_per_million,
    cached_input_usd_per_million, output_usd_per_million,
    pricing_source, pricing_verified_at, updated_at
) VALUES (
    'openrouter-paid-gpt-5-4-mini',
    'OpenRouter',
    'openrouter',
    'openai/gpt-5.4-mini',
    'sovereign-openrouter-gpt-5.4-mini',
    'https://openrouter.ai/api/v1',
    'pending',
    'standard',
    4,
    0.75,
    0.075,
    4.50,
    'openrouter-models-api-2026-07-22',
    NOW(),
    NOW()
)
ON CONFLICT (route_id) DO UPDATE SET
    provider_name=EXCLUDED.provider_name,
    provider_prefix=EXCLUDED.provider_prefix,
    upstream_model_id=EXCLUDED.upstream_model_id,
    api_base=EXCLUDED.api_base,
    billing_category=EXCLUDED.billing_category,
    markup_multiplier=GREATEST(
        4,
        COALESCE(llm_provider_deployments.markup_multiplier, 4)
    ),
    input_usd_per_million=EXCLUDED.input_usd_per_million,
    cached_input_usd_per_million=EXCLUDED.cached_input_usd_per_million,
    output_usd_per_million=EXCLUDED.output_usd_per_million,
    pricing_source=EXCLUDED.pricing_source,
    pricing_verified_at=EXCLUDED.pricing_verified_at,
    status=CASE
        WHEN llm_provider_deployments.status='ready' THEN 'ready'
        ELSE 'pending'
    END,
    updated_at=NOW();

INSERT INTO schema_migrations (id, name)
VALUES (33, 'openrouter_paid_freellm_direct')
ON CONFLICT (id) DO NOTHING;

COMMIT;
