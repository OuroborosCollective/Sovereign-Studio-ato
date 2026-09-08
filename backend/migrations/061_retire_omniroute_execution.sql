-- Owner-approved retirement of OmniRoute from all live LLM execution surfaces.
-- Historical OmniRoute migrations and evidence remain readable; only current
-- execution eligibility, discovery and selection are disabled.
BEGIN;

DO $migration$
DECLARE
    omniroute_base CONSTANT TEXT := 'http://omniroute:20128/v1';
    retirement_family CONSTANT TEXT := 'omniroute_retired_owner_simplification';
BEGIN
    UPDATE llm_revolver_provider_sources
    SET enabled=false,
        status='disabled',
        last_error_code=retirement_family,
        updated_at=NOW()
    WHERE lower(api_base)=lower(omniroute_base);

    UPDATE llm_revolver_provider_models AS model
    SET enabled=false,
        status='disabled',
        free_verified=false,
        free_eligible=false,
        last_error_code=retirement_family,
        eligibility_source='omniroute-retired-historical-only',
        eligibility_verified_at=NULL,
        updated_at=NOW()
    WHERE EXISTS (
        SELECT 1
        FROM llm_revolver_provider_sources AS source
        WHERE source.id=model.source_id
          AND lower(source.api_base)=lower(omniroute_base)
    );

    UPDATE llm_routes
    SET disabled=true,
        config=COALESCE(config, '{}'::jsonb) || jsonb_build_object(
            'executionRetired', true,
            'executionRetirementFamily', retirement_family,
            'routeSource', 'omniroute',
            'selectable', false,
            'freeEligible', false,
            'canaryVerified', false,
            'transportCanaryVerified', false,
            'repositoryExecutionAllowed', false,
            'activationState', 'retired'
        ),
        updated_at=NOW()
    WHERE lower(COALESCE(base_url, ''))=lower(omniroute_base)
       OR lower(COALESCE(config->>'routeSource', ''))='omniroute'
       OR lower(COALESCE(config->>'sourceType', ''))='omniroute';
END
$migration$;

INSERT INTO schema_migrations (id, name)
VALUES (61, 'retire_omniroute_execution')
ON CONFLICT (id) DO NOTHING;

COMMIT;
