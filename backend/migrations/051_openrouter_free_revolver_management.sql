-- OpenRouter Free-Revolver key lifecycle metadata.
-- Raw management and execution keys remain 0600 owner-managed files.

CREATE TABLE IF NOT EXISTS openrouter_managed_execution_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    purpose TEXT NOT NULL CHECK (purpose IN ('free-revolver')),
    upstream_key_hash TEXT NOT NULL UNIQUE
        CHECK (upstream_key_hash ~ '^[0-9a-f]{64}$'),
    key_fingerprint_sha256 TEXT NOT NULL
        CHECK (key_fingerprint_sha256 ~ '^[0-9a-f]{64}$'),
    key_name TEXT NOT NULL CHECK (length(key_name) BETWEEN 1 AND 160),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','retired','retirement_pending','failed')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activated_at TIMESTAMPTZ NULL,
    last_verified_at TIMESTAMPTZ NULL,
    retired_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DO $$
DECLARE
    route_id_type TEXT;
    managed_route_id_type TEXT;
BEGIN
    SELECT format_type(attribute.atttypid, attribute.atttypmod)
      INTO route_id_type
      FROM pg_attribute attribute
      JOIN pg_class relation ON relation.oid = attribute.attrelid
      JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
     WHERE namespace.nspname = current_schema()
       AND relation.relname = 'llm_routes'
       AND attribute.attname = 'id'
       AND attribute.attnum > 0
       AND NOT attribute.attisdropped;

    IF route_id_type IS NULL THEN
        RAISE EXCEPTION 'llm_routes.id type could not be resolved';
    END IF;

    SELECT format_type(attribute.atttypid, attribute.atttypmod)
      INTO managed_route_id_type
      FROM pg_attribute attribute
      JOIN pg_class relation ON relation.oid = attribute.attrelid
      JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
     WHERE namespace.nspname = current_schema()
       AND relation.relname = 'openrouter_managed_execution_keys'
       AND attribute.attname = 'route_id'
       AND attribute.attnum > 0
       AND NOT attribute.attisdropped;

    IF managed_route_id_type IS NULL THEN
        EXECUTE format(
            'ALTER TABLE openrouter_managed_execution_keys ADD COLUMN route_id %s NULL',
            route_id_type
        );
    ELSIF managed_route_id_type <> route_id_type THEN
        RAISE EXCEPTION
            'openrouter_managed_execution_keys.route_id type % does not match llm_routes.id type %',
            managed_route_id_type,
            route_id_type;
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint constraint_row
          JOIN pg_class relation ON relation.oid = constraint_row.conrelid
          JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = current_schema()
           AND relation.relname = 'openrouter_managed_execution_keys'
           AND constraint_row.conname = 'openrouter_managed_execution_keys_route_id_fkey'
    ) THEN
        ALTER TABLE openrouter_managed_execution_keys
            ADD CONSTRAINT openrouter_managed_execution_keys_route_id_fkey
            FOREIGN KEY (route_id) REFERENCES llm_routes(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS openrouter_managed_execution_keys_one_active
    ON openrouter_managed_execution_keys (purpose)
    WHERE status='active';

CREATE INDEX IF NOT EXISTS openrouter_managed_execution_keys_status_idx
    ON openrouter_managed_execution_keys (status, updated_at DESC);
