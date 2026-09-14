-- Isolated PostgreSQL regression fixture. Run with postgres_migration_preview only.
-- Dedicated preview tables plus the tool's unconditional rollback; never apply to production.
SET LOCAL search_path = public;
CREATE TABLE llm_routes (
    id text PRIMARY KEY,
    model_id text UNIQUE NOT NULL,
    provider text NOT NULL DEFAULT 'openrouter',
    runtime_kind text NOT NULL DEFAULT 'openrouter',
    disabled boolean NOT NULL DEFAULT false,
    priority integer NOT NULL DEFAULT 100,
    config jsonb NOT NULL DEFAULT '{"selectable":true}'::jsonb
);
CREATE TABLE root_reference (
    route_id text REFERENCES llm_routes(id) ON DELETE RESTRICT
);
INSERT INTO llm_routes (id, model_id) VALUES
    ('openrouter-paid-gpt-5-4-mini', 'sovereign-openrouter:inclusionai/ling-2.6-flash'),
    ('openrouter-paid-deed65be08ae504b63c183700aadfefd', 'sovereign-openrouter:openai/gpt-5.4-mini'),
    ('4fa1b665-f47b-5514-8627-36780c833199', 'sovereign-openrouter-free');
INSERT INTO root_reference VALUES ('openrouter-paid-gpt-5-4-mini');
DO $replay$
DECLARE
    original_free jsonb;
    root_model text;
    n integer;
BEGIN
    SELECT to_jsonb(route) INTO original_free FROM llm_routes AS route
      WHERE model_id='sovereign-openrouter-free';
    -- Reproduce the old algorithm against two independent uniqueness constraints.
    BEGIN
        INSERT INTO llm_routes (id, model_id)
          VALUES ('openrouter-paid-gpt-5-4-mini', 'sovereign-openrouter:openai/gpt-5.4-mini')
          ON CONFLICT (id) DO UPDATE SET model_id=EXCLUDED.model_id;
        RAISE EXCEPTION 'Old root-switching algorithm unexpectedly succeeded';
    EXCEPTION WHEN unique_violation THEN
        RAISE NOTICE 'OLD_ALGORITHM_UNIQUE_VIOLATION_REPRODUCED';
    END;
    -- Repeat the repaired model-identity upsert through default rotations.
    FOR n IN 1..3 LOOP
        INSERT INTO llm_routes (id, model_id, priority) VALUES
            ('openrouter-paid-deed65be08ae504b63c183700aadfefd', 'sovereign-openrouter:openai/gpt-5.4-mini', CASE WHEN n=1 THEN 10 ELSE 100 END),
            ('openrouter-paid-96abc145a3f0bcd28a895a7728d3ab7e', 'sovereign-openrouter:inclusionai/ling-2.6-flash', CASE WHEN n=2 THEN 10 ELSE 101 END),
            ('openrouter-paid-e8ba98b33d8a56f4a2671f638c694433', 'sovereign-openrouter:vendor/new-default', CASE WHEN n=3 THEN 10 ELSE 102 END)
          ON CONFLICT (model_id) DO UPDATE SET
            disabled=false, priority=EXCLUDED.priority,
            config=EXCLUDED.config;
    END LOOP;
    SELECT model_id INTO root_model FROM llm_routes WHERE id='openrouter-paid-gpt-5-4-mini';
    IF root_model <> 'sovereign-openrouter:inclusionai/ling-2.6-flash' THEN
        RAISE EXCEPTION 'Existing root identity changed';
    END IF;
    IF (SELECT count(*) FROM llm_routes) <> 4 THEN
        RAISE EXCEPTION 'Refresh duplicated or removed routes';
    END IF;
    IF (SELECT count(*) FROM root_reference JOIN llm_routes ON id=route_id) <> 1 THEN
        RAISE EXCEPTION 'Root foreign-key reference was lost';
    END IF;
    UPDATE llm_routes SET disabled=true,
        config=config || '{"selectable":false,"activationState":"missing-from-current-catalog"}'::jsonb
      WHERE lower(COALESCE(runtime_kind, provider))='openrouter'
        AND model_id LIKE 'sovereign-openrouter:%'
        AND NOT (model_id = ANY(ARRAY['sovereign-openrouter:vendor/new-default']));
    IF (SELECT to_jsonb(route) FROM llm_routes AS route WHERE model_id='sovereign-openrouter-free') IS DISTINCT FROM original_free THEN
        RAISE EXCEPTION 'Paid refresh changed the dedicated free route';
    END IF;
    IF (SELECT count(*) FROM llm_routes WHERE NOT disabled AND model_id LIKE 'sovereign-openrouter:%' AND config->>'selectable'='true') <> 1 THEN
        RAISE EXCEPTION 'Paid readiness counted free or retired models';
    END IF;
    RAISE NOTICE 'MODEL_IDENTITY_ROTATION_REPEAT_FK_AND_FREE_BOUNDARY_VERIFIED';
END
$replay$;
