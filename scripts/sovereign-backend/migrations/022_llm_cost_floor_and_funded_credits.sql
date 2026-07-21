-- 022_llm_cost_floor_and_funded_credits.sql
-- Three cost categories: free Revolver routes, standard >=4x, premium >=8x.
-- Paid provider calls are financed only by verified purchased credits.

BEGIN;

ALTER TABLE admin_users
    ADD COLUMN IF NOT EXISTS provider_funded_credits INTEGER NOT NULL DEFAULT 0;

-- Conservative historical backfill: only verified credit purchases create
-- provider-funded capacity. Historical spending consumes that capacity first;
-- bonus/admin grants never become provider-funded.
WITH funded AS (
    SELECT account.id,
           GREATEST(
               0,
               LEAST(
                   account.credits,
                   COALESCE(SUM(
                       CASE
                           WHEN ledger.type = 'credit_purchase' AND ledger.amount > 0
                           THEN ledger.amount ELSE 0
                       END
                   ), 0)
                   - COALESCE(SUM(
                       CASE WHEN ledger.amount < 0 THEN -ledger.amount ELSE 0 END
                   ), 0)
               )
           )::integer AS balance
    FROM admin_users AS account
    LEFT JOIN credit_ledger AS ledger ON ledger.user_id = account.id
    GROUP BY account.id, account.credits
)
UPDATE admin_users AS account
SET provider_funded_credits = funded.balance
FROM funded
WHERE account.id = funded.id;

ALTER TABLE admin_users
    DROP CONSTRAINT IF EXISTS admin_users_provider_funded_credits_check;
ALTER TABLE admin_users
    ADD CONSTRAINT admin_users_provider_funded_credits_check
    CHECK (provider_funded_credits >= 0 AND provider_funded_credits <= credits);

ALTER TABLE llm_usage_settlements
    ADD COLUMN IF NOT EXISTS cached_prompt_tokens INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS provider_cost_usd_micros BIGINT,
    ADD COLUMN IF NOT EXISTS billed_value_usd_micros BIGINT,
    ADD COLUMN IF NOT EXISTS markup_multiplier SMALLINT,
    ADD COLUMN IF NOT EXISTS billing_class TEXT,
    ADD COLUMN IF NOT EXISTS billing_category TEXT,
    ADD COLUMN IF NOT EXISTS funded_credits_reserved INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS request_count INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS trace_id TEXT,
    ADD COLUMN IF NOT EXISTS stage TEXT;

UPDATE llm_usage_settlements
SET billing_category = COALESCE(billing_category, billing_class)
WHERE billing_category IS NULL;

ALTER TABLE llm_usage_settlements
    DROP CONSTRAINT IF EXISTS llm_usage_settlements_status_check;
ALTER TABLE llm_usage_settlements
    ADD CONSTRAINT llm_usage_settlements_status_check
    CHECK (status IN (
        'created',
        'reserved',
        'settled_usage',
        'settled_estimate',
        'refunded',
        'failed',
        'reconciliation_required'
    ));
ALTER TABLE llm_usage_settlements
    DROP CONSTRAINT IF EXISTS llm_usage_markup_multiplier_check;
ALTER TABLE llm_usage_settlements
    DROP CONSTRAINT IF EXISTS llm_usage_billing_class_check;
ALTER TABLE llm_usage_settlements
    DROP CONSTRAINT IF EXISTS llm_usage_billing_category_check;
ALTER TABLE llm_usage_settlements
    ADD CONSTRAINT llm_usage_billing_category_check
    CHECK (
        billing_category IS NULL
        OR billing_category IN ('free', 'standard', 'premium')
    );
ALTER TABLE llm_usage_settlements
    ADD CONSTRAINT llm_usage_markup_multiplier_check
    CHECK (
        billing_category IS NULL
        OR (billing_category = 'free' AND markup_multiplier = 0)
        OR (billing_category = 'standard' AND markup_multiplier >= 4)
        OR (billing_category = 'premium' AND markup_multiplier >= 8)
    );

CREATE INDEX IF NOT EXISTS idx_llm_usage_settlements_trace
    ON llm_usage_settlements (trace_id, created_at DESC)
    WHERE trace_id IS NOT NULL;

ALTER TABLE llm_provider_deployments
    ADD COLUMN IF NOT EXISTS billing_category TEXT NOT NULL DEFAULT 'premium',
    ADD COLUMN IF NOT EXISTS markup_multiplier SMALLINT NOT NULL DEFAULT 8,
    ADD COLUMN IF NOT EXISTS input_usd_per_million NUMERIC(18,9),
    ADD COLUMN IF NOT EXISTS cached_input_usd_per_million NUMERIC(18,9),
    ADD COLUMN IF NOT EXISTS output_usd_per_million NUMERIC(18,9),
    ADD COLUMN IF NOT EXISTS pricing_source TEXT,
    ADD COLUMN IF NOT EXISTS pricing_verified_at TIMESTAMPTZ;

ALTER TABLE llm_provider_deployments
    DROP CONSTRAINT IF EXISTS llm_provider_billing_category_check;
ALTER TABLE llm_provider_deployments
    DROP CONSTRAINT IF EXISTS llm_provider_markup_multiplier_check;
ALTER TABLE llm_provider_deployments
    ADD CONSTRAINT llm_provider_billing_category_check
    CHECK (billing_category IN ('free', 'standard', 'premium'));
ALTER TABLE llm_provider_deployments
    ADD CONSTRAINT llm_provider_markup_multiplier_check
    CHECK (
        (billing_category = 'free' AND markup_multiplier = 0)
        OR (billing_category = 'standard' AND markup_multiplier >= 4)
        OR (billing_category = 'premium' AND markup_multiplier >= 8)
    );

-- Agents SDK is code-pinned to GPT-5.4 mini and standard billing, but the
-- route stays disabled until LiteLLM returns verified pricing and a completion
-- canary succeeds. No bootstrap price is treated as truth.
UPDATE llm_routes
SET credits_per_unit = 0,
    disabled = true,
    tier = 'standard',
    config = COALESCE(config, '{}'::jsonb) || jsonb_build_object(
        'alias', 'sovereign-fast',
        'providerModel', 'gpt-5.4-mini',
        'billingCategory', 'standard',
        'billingClass', 'standard',
        'markupMultiplier', 4,
        'minimumMultiplier', 4,
        'usdMicrosPerCredit', 1000,
        'pricingVerified', false,
        'pricingSource', 'requires-litellm-model-info',
        'pricingAuthority', 'litellm-model-info'
    ),
    updated_at = NOW()
WHERE model_id = 'sovereign-fast'
  AND lower(provider) = 'litellm'
  -- Startup migrations are replayed for schema-drift safety. Never erase
  -- later price/canary evidence that already activated this route.
  AND COALESCE(config->>'pricingVerified', 'false') <> 'true';

-- Every non-Agent route is re-gated. The owner must assign one of the three
-- categories and LiteLLM must confirm exact pricing before activation. Existing
-- aliases remain present but cannot consume provider money while unverified.
UPDATE llm_routes
SET disabled = true,
    tier = CASE
        WHEN COALESCE(config->>'billingCategory', config->>'billingClass') = 'free'
            THEN 'free'
        WHEN COALESCE(config->>'billingCategory', config->>'billingClass') = 'standard'
            THEN 'standard'
        ELSE 'premium'
    END,
    config = COALESCE(config, '{}'::jsonb) || jsonb_build_object(
        'billingCategory', CASE
            WHEN COALESCE(config->>'billingCategory', config->>'billingClass') = 'free'
                THEN 'free'
            WHEN COALESCE(config->>'billingCategory', config->>'billingClass') = 'standard'
                THEN 'standard'
            ELSE 'premium'
        END,
        'markupMultiplier', CASE
            WHEN COALESCE(config->>'billingCategory', config->>'billingClass') = 'free'
                THEN 0
            WHEN COALESCE(config->>'billingCategory', config->>'billingClass') = 'standard'
                THEN GREATEST(4, COALESCE(NULLIF(config->>'markupMultiplier','')::integer, 4))
            ELSE GREATEST(8, COALESCE(NULLIF(config->>'markupMultiplier','')::integer, 8))
        END,
        'usdMicrosPerCredit', 1000,
        'pricingVerified', false,
        'pricingSource', 'requires-litellm-verification',
        'pricingAuthority', 'provider-cost-settlement'
    ),
    updated_at = NOW()
WHERE lower(provider) = 'litellm'
  AND model_id <> 'sovereign-fast'
  -- Re-gate only legacy or still-unverified rows. A verified route is live
  -- runtime truth and must survive every idempotent container restart.
  AND COALESCE(config->>'pricingVerified', 'false') <> 'true';

ALTER TABLE credit_packages
    DROP CONSTRAINT IF EXISTS credit_packages_cash_buffer_check;
ALTER TABLE credit_packages
    ADD CONSTRAINT credit_packages_cash_buffer_check
    CHECK (
        NOT enabled
        OR (credits > 0 AND price_eur >= (credits::numeric * 0.0016::numeric))
    );

DO $$
DECLARE
    ledger_columns TEXT[];
BEGIN
    IF to_regclass(format('%I.schema_migrations', current_schema())) IS NULL THEN
        RAISE NOTICE 'schema_migrations does not exist; migration ledger write skipped';
        RETURN;
    END IF;

    SELECT array_agg(column_name ORDER BY ordinal_position)
    INTO ledger_columns
    FROM information_schema.columns
    WHERE table_schema = current_schema()
      AND table_name = 'schema_migrations';

    IF ledger_columns @> ARRAY['version', 'applied_at']::TEXT[] THEN
        EXECUTE
            'INSERT INTO schema_migrations (version, applied_at) '
            'VALUES ($1, NOW()) ON CONFLICT (version) DO NOTHING'
        USING '022';
    ELSIF ledger_columns @> ARRAY['version']::TEXT[] THEN
        EXECUTE
            'INSERT INTO schema_migrations (version) '
            'VALUES ($1) ON CONFLICT (version) DO NOTHING'
        USING '022';
    ELSIF ledger_columns @> ARRAY['id', 'name']::TEXT[] THEN
        EXECUTE
            'INSERT INTO schema_migrations (id, name) '
            'VALUES ($1, $2) ON CONFLICT (id) DO NOTHING'
        USING 22, 'llm_cost_floor_and_funded_credits';
    ELSE
        RAISE EXCEPTION 'Unsupported schema_migrations layout: %', ledger_columns;
    END IF;
END $$;

COMMIT;
