-- Database-owned execution profiles for the LLM resolver/revolver.
-- Provider routes remain admin/LiteLLM owned; no provider names, aliases or keys
-- are seeded by this migration.

CREATE TABLE IF NOT EXISTS llm_execution_profiles (
    profile_id TEXT PRIMARY KEY,
    billing_categories TEXT[] NOT NULL,
    route_mode TEXT NOT NULL CHECK (route_mode IN ('single', 'revolver')),
    max_foreground_agents INTEGER NOT NULL CHECK (max_foreground_agents BETWEEN 1 AND 1),
    max_background_agents INTEGER NOT NULL CHECK (max_background_agents BETWEEN 0 AND 6),
    repository_execution_allowed BOOLEAN NOT NULL,
    requires_verified_purchase BOOLEAN NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    priority INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (cardinality(billing_categories) > 0)
);

INSERT INTO llm_execution_profiles (
    profile_id, billing_categories, route_mode,
    max_foreground_agents, max_background_agents,
    repository_execution_allowed, requires_verified_purchase,
    enabled, priority, updated_at
) VALUES
    (
        'free_single_agent', ARRAY['free']::TEXT[], 'revolver',
        1, 0, TRUE, FALSE, TRUE, 10, NOW()
    ),
    (
        'paid_swarm_6', ARRAY['standard','premium']::TEXT[], 'single',
        1, 6, TRUE, TRUE, TRUE, 20, NOW()
    )
ON CONFLICT (profile_id) DO UPDATE SET
    billing_categories = EXCLUDED.billing_categories,
    route_mode = EXCLUDED.route_mode,
    max_foreground_agents = EXCLUDED.max_foreground_agents,
    max_background_agents = EXCLUDED.max_background_agents,
    repository_execution_allowed = EXCLUDED.repository_execution_allowed,
    requires_verified_purchase = EXCLUDED.requires_verified_purchase,
    enabled = EXCLUDED.enabled,
    priority = EXCLUDED.priority,
    updated_at = NOW();

UPDATE llm_routes
SET config = COALESCE(config, '{}'::jsonb) || jsonb_build_object(
        'executionProfile', 'free_single_agent',
        'resolverMode', 'revolver',
        'maxForegroundAgents', 1,
        'maxBackgroundAgents', 0,
        'repositoryExecutionAllowed', true
    ),
    updated_at = NOW()
WHERE COALESCE(config->>'billingCategory', config->>'billingClass') = 'free';

UPDATE llm_routes
SET config = COALESCE(config, '{}'::jsonb) || jsonb_build_object(
        'executionProfile', 'paid_swarm_6',
        'resolverMode', 'single',
        'maxForegroundAgents', 1,
        'maxBackgroundAgents', 6,
        'repositoryExecutionAllowed', true
    ),
    updated_at = NOW()
WHERE COALESCE(config->>'billingCategory', config->>'billingClass') IN ('standard', 'premium');

CREATE INDEX IF NOT EXISTS idx_llm_execution_profiles_enabled
    ON llm_execution_profiles (enabled, priority, profile_id);
