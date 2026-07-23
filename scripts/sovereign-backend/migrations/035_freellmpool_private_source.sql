-- Register the private FreeLLMPool proxy as a separate managed free source.
-- No provider or proxy secret is stored in PostgreSQL.
BEGIN;

DO $$
DECLARE
    expected_id CONSTANT UUID := 'c79ff468-ee08-5686-97df-756fa58b74f0';
    expected_api_base CONSTANT TEXT := 'http://freellmpool:8080/v1';
    conflicting_id UUID;
BEGIN
    IF to_regclass('llm_revolver_provider_sources') IS NULL THEN
        RETURN;
    END IF;

    SELECT id INTO conflicting_id
    FROM llm_revolver_provider_sources
    WHERE lower(api_base) = lower(expected_api_base)
      AND id <> expected_id
    LIMIT 1;

    IF conflicting_id IS NOT NULL THEN
        RAISE EXCEPTION
            'freellmpool source identity conflict: expected %, found %',
            expected_id,
            conflicting_id;
    END IF;

    INSERT INTO llm_revolver_provider_sources (
        id,
        label,
        api_base,
        auth_mode,
        key_hint,
        status,
        last_error_code,
        enabled
    ) VALUES (
        expected_id,
        'FreeLLMPool 0.11.4 · privater Docker',
        expected_api_base,
        'managed-bearer',
        'owner-managed',
        'degraded',
        'freellmpool_runtime_canary_required',
        true
    )
    ON CONFLICT (id) DO UPDATE SET
        label = EXCLUDED.label,
        api_base = EXCLUDED.api_base,
        auth_mode = EXCLUDED.auth_mode,
        key_hint = EXCLUDED.key_hint,
        status = CASE
            WHEN llm_revolver_provider_sources.status = 'healthy' THEN 'healthy'
            ELSE 'degraded'
        END,
        last_error_code = CASE
            WHEN llm_revolver_provider_sources.status = 'healthy' THEN NULL
            ELSE 'freellmpool_runtime_canary_required'
        END,
        enabled = true,
        updated_at = NOW();
END $$;

COMMIT;
