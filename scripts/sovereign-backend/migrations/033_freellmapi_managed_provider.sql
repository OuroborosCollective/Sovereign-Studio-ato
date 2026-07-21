-- Additive FreeLLM API 0.5.0 Docker-provider authentication mode.
-- Existing bearer, x-api-key and none semantics remain unchanged.
BEGIN;

DO $$
BEGIN
    IF to_regclass('llm_revolver_provider_sources') IS NOT NULL THEN
        ALTER TABLE llm_revolver_provider_sources
            DROP CONSTRAINT IF EXISTS llm_revolver_provider_sources_auth_mode_check;
        ALTER TABLE llm_revolver_provider_sources
            ADD CONSTRAINT llm_revolver_provider_sources_auth_mode_check
            CHECK (auth_mode IN ('bearer', 'x-api-key', 'none', 'managed-bearer'));
    END IF;
END $$;

COMMIT;
