-- Sovereign Backend bootstrap schema.
-- Preserves the legacy auto-migrate schema as an idempotent, fail-closed SQL migration.
BEGIN;

CREATE TABLE IF NOT EXISTS admin_api_keys (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_id        UUID        NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    key_hash        TEXT        UNIQUE NOT NULL,
    label           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_admin_api_keys_key_hash ON admin_api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_admin_api_keys_admin_id ON admin_api_keys(admin_id);

CREATE TABLE IF NOT EXISTS credit_ledger (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID        NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    type            VARCHAR(50) NOT NULL,
    amount          INTEGER     NOT NULL,
    reason          TEXT,
    provider        TEXT,
    provider_tx_id  TEXT,
    created_by      UUID        REFERENCES admin_users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_credit_ledger_user_id ON credit_ledger(user_id);
CREATE INDEX IF NOT EXISTS idx_credit_ledger_created_at ON credit_ledger(created_at DESC);

CREATE TABLE IF NOT EXISTS payment_methods (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type       VARCHAR(50) UNIQUE NOT NULL,
    label      TEXT NOT NULL,
    enabled    BOOLEAN NOT NULL DEFAULT false,
    config     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO payment_methods (type, label, enabled) VALUES
    ('bitcoin', 'Bitcoin (BTC)', false),
    ('ethereum', 'Ethereum (ETH)', false),
    ('usdt_trc20', 'USDT (TRC20)', false),
    ('google_play', 'Google Play IAP', false),
    ('paypal', 'PayPal', true),
    ('skrill', 'Skrill', false)
ON CONFLICT (type) DO NOTHING;

CREATE TABLE IF NOT EXISTS credit_packages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    credits     INTEGER NOT NULL,
    price_eur   NUMERIC(10,2) NOT NULL,
    description TEXT,
    enabled     BOOLEAN NOT NULL DEFAULT true,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO credit_packages (name, credits, price_eur, description, sort_order)
SELECT seed.name, seed.credits, seed.price_eur, seed.description, seed.sort_order
FROM (VALUES
    ('Starter'::text, 500, 2.00::numeric, '500 Credits – ideal zum Ausprobieren'::text, 1),
    ('Pro'::text, 2500, 14.00::numeric, '2.500 Credits – für regelmäßige Nutzung'::text, 2),
    ('Power'::text, 10000, 26.00::numeric, '10.000 Credits – für Power-User'::text, 3),
    ('Studio'::text, 50000, 99.00::numeric, '50.000 Credits – für Studios und Teams'::text, 4)
) AS seed(name, credits, price_eur, description, sort_order)
WHERE NOT EXISTS (
    SELECT 1 FROM credit_packages existing WHERE existing.name = seed.name
);

CREATE TABLE IF NOT EXISTS llm_routes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    provider    TEXT NOT NULL,
    model       TEXT NOT NULL,
    endpoint    TEXT NOT NULL,
    api_key     TEXT,
    enabled     BOOLEAN NOT NULL DEFAULT false,
    priority    INTEGER NOT NULL DEFAULT 0,
    config      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_llm_routes_enabled ON llm_routes(enabled);
CREATE INDEX IF NOT EXISTS idx_llm_routes_priority ON llm_routes(priority);

CREATE TABLE IF NOT EXISTS launcher_overrides (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tool_id     TEXT NOT NULL,
    config      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_launcher_overrides_tool_id ON launcher_overrides(tool_id);

CREATE TABLE IF NOT EXISTS toolchain_tools (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name             TEXT NOT NULL UNIQUE,
    description      TEXT,
    input_schema     JSONB NOT NULL DEFAULT '{}'::jsonb,
    enabled          BOOLEAN NOT NULL DEFAULT true,
    write_action     BOOLEAN NOT NULL DEFAULT false,
    requires_confirm BOOLEAN NOT NULL DEFAULT false,
    sort_order       INTEGER NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_toolchain_tools_enabled ON toolchain_tools(enabled);
CREATE INDEX IF NOT EXISTS idx_toolchain_tools_sort_order ON toolchain_tools(sort_order);
INSERT INTO toolchain_tools (name, description, enabled, write_action, requires_confirm, sort_order) VALUES
    ('github_apply_search_replace_pr', 'Create a Draft PR via GitHub', true, true, true, 1),
    ('apply_patch_worker', 'Apply patch via Sovereign Worker', true, true, true, 2),
    ('toolchain_briefing', 'Get project briefing for agents', true, false, false, 3),
    ('list_archive_files', 'List files in Studio/Sandbox archives', true, false, false, 4),
    ('read_archive_text', 'Read text file from archives', true, false, false, 5),
    ('github_read_file', 'Read GitHub file via Contents API', true, false, false, 6),
    ('make_patch_payload', 'Create Sovereign Patch Worker payload', true, false, false, 7),
    ('plan_sandbox_commands', 'Plan sandbox commands (no execution)', true, false, false, 8),
    ('preview_search_replace', 'Preview SEARCH/REPLACE blocks', true, false, false, 9),
    ('apply_backend_guardrails_patch_pr', 'Apply backend guardrails patch', true, true, true, 10)
ON CONFLICT (name) DO NOTHING;

CREATE TABLE IF NOT EXISTS audit_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_id    UUID,
    admin_email TEXT NOT NULL,
    action      TEXT NOT NULL,
    target_id   TEXT,
    changes     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_log_admin_id ON audit_log(admin_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at DESC);

CREATE TABLE IF NOT EXISTS user_skills (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    skill_id   TEXT NOT NULL,
    level      INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_user_skills_user_id ON user_skills(user_id);

CREATE TABLE IF NOT EXISTS transactions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID REFERENCES admin_users(id),
    type           VARCHAR(50) NOT NULL,
    amount         NUMERIC(10,2) NOT NULL,
    currency       VARCHAR(10) DEFAULT 'EUR',
    status         VARCHAR(20) NOT NULL DEFAULT 'pending',
    provider       TEXT,
    provider_tx_id TEXT,
    description    TEXT,
    metadata       JSONB,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);
CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON transactions(created_at DESC);

CREATE TABLE IF NOT EXISTS schema_migrations (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO schema_migrations (id, name)
VALUES (1, 'initial_schema')
ON CONFLICT (id) DO NOTHING;

COMMIT;
