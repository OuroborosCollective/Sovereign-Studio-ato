-- Reclassify historical FreeLLM pool availability failures.
-- A generic canary failure did not prove that the model or zero-cost policy was invalid;
-- it commonly meant that no enabled/healthy upstream existed or a keyless provider was
-- cooling down. Keep such aliases disabled but retryable/discovered instead of hard-blocked.
BEGIN;

DO $migration$
BEGIN
  IF to_regclass('llm_revolver_provider_models') IS NOT NULL
     AND to_regclass('llm_revolver_provider_sources') IS NOT NULL THEN
    UPDATE llm_revolver_provider_models
    SET status = 'discovered',
        enabled = false,
        last_error_code = 'freellm_upstream_availability_unconfirmed',
        updated_at = NOW()
    WHERE free_verified = true
      AND status = 'blocked'
      AND last_error_code = 'free_provider_canary_failed';

    UPDATE llm_revolver_provider_sources AS source
    SET status = CASE
            WHEN EXISTS (
                SELECT 1
                FROM llm_revolver_provider_models AS model
                WHERE model.source_id = source.id
                  AND model.status = 'ready'
                  AND model.enabled = true
            ) THEN 'degraded'
            ELSE source.status
        END,
        last_error_code = CASE
            WHEN EXISTS (
                SELECT 1
                FROM llm_revolver_provider_models AS model
                WHERE model.source_id = source.id
                  AND model.status = 'discovered'
                  AND model.last_error_code = 'freellm_upstream_availability_unconfirmed'
            ) THEN 'freellm_routes_awaiting_upstream_availability'
            ELSE source.last_error_code
        END,
        updated_at = NOW()
    WHERE EXISTS (
        SELECT 1
        FROM llm_revolver_provider_models AS model
        WHERE model.source_id = source.id
          AND model.status = 'discovered'
          AND model.last_error_code = 'freellm_upstream_availability_unconfirmed'
    );
  END IF;
END
$migration$;

INSERT INTO schema_migrations (id, name)
VALUES (38, 'reclassify_retryable_freellm_canary_failures')
ON CONFLICT (id) DO NOTHING;

COMMIT;
