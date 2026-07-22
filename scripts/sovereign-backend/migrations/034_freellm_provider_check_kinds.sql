-- Allow the direct managed FreeLLM canary evidence emitted by Revolver v3.
-- The change is additive: legacy discovery and route-canary rows remain valid.
BEGIN;

DO $$
BEGIN
    IF to_regclass('llm_revolver_provider_checks') IS NOT NULL THEN
        ALTER TABLE llm_revolver_provider_checks
            DROP CONSTRAINT IF EXISTS llm_revolver_provider_checks_check_kind_check;
        ALTER TABLE llm_revolver_provider_checks
            ADD CONSTRAINT llm_revolver_provider_checks_check_kind_check
            CHECK (
                check_kind IN (
                    'models_discovery',
                    'route_canary',
                    'managed_quota_direct_canary',
                    'direct_route_canary'
                )
            ) NOT VALID;
        ALTER TABLE llm_revolver_provider_checks
            VALIDATE CONSTRAINT llm_revolver_provider_checks_check_kind_check;
    END IF;
END $$;

COMMIT;
