#!/bin/bash
# =============================================================================
# Sovereign Backend - Auto Migration Script
# =============================================================================
# This script is automatically run on container startup to ensure database
# tables are properly set up.
#
# Usage: This script runs automatically during container initialization
# =============================================================================

set -e

echo "[INFO] Running database migrations..."

# Database connection parameters from environment
POSTGRES_HOST="${POSTGRES_HOST:-db}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-postgres}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD}"

# Export PGPASSWORD for psql
export PGPASSWORD="${POSTGRES_PASSWORD}"

# Function to run SQL
run_sql() {
    local sql="$1"
    echo "$sql" | psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" 2>/dev/null || true
}

# =============================================================================
# Migration: admin_api_keys table
# =============================================================================
echo "[INFO] Checking admin_api_keys table..."

run_sql "
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
"

# Check if we need to insert a bootstrap key
ADMIN_API_KEY="${ADMIN_API_KEY:-}"
if [ -n "$ADMIN_API_KEY" ]; then
    echo "[INFO] Checking for bootstrap admin API key..."
    
    # Calculate SHA256 hash of the key
    KEY_HASH=$(echo -n "${ADMIN_API_KEY}" | sha256sum | cut -d' ' -f1)
    
    # Insert if not exists
    run_sql "
    INSERT INTO admin_api_keys (admin_id, key_hash, label)
    SELECT id, '${KEY_HASH}', 'Bootstrap Admin Key'
    FROM admin_users 
    WHERE role IN ('admin', 'superadmin')
    LIMIT 1
    ON CONFLICT (key_hash) DO NOTHING;
    "
    
    echo "[INFO] Bootstrap admin API key configured"
fi

# =============================================================================
# Migration: credit_ledger table
# =============================================================================
echo "[INFO] Checking credit_ledger table..."

run_sql "
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
"

# =============================================================================
# Migration: payment_methods table
# =============================================================================
echo "[INFO] Checking payment_methods table..."

run_sql "
CREATE TABLE IF NOT EXISTS payment_methods (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type       VARCHAR(50) UNIQUE NOT NULL,
    label      TEXT NOT NULL,
    enabled    BOOLEAN NOT NULL DEFAULT false,
    config     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"

# Insert default payment methods if not exists
run_sql "
INSERT INTO payment_methods (type, label, enabled) VALUES
    ('bitcoin', 'Bitcoin (BTC)', false),
    ('ethereum', 'Ethereum (ETH)', false),
    ('usdt_trc20', 'USDT (TRC20)', false),
    ('google_play', 'Google Play IAP', false),
    ('paypal', 'PayPal', true),
    ('skrill', 'Skrill', false)
ON CONFLICT (type) DO NOTHING;
"

# =============================================================================
# Migration: credit_packages table
# =============================================================================
echo "[INFO] Checking credit_packages table..."

run_sql "
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
"

# Insert default credit packages if not exists
run_sql "
INSERT INTO credit_packages (name, credits, price_eur, description, sort_order) VALUES
    ('Starter', 500, 2.00, '500 Credits – ideal zum Ausprobieren', 1),
    ('Pro', 2500, 14.00, '2.500 Credits – für regelmäßige Nutzung', 2),
    ('Power', 10000, 26.00, '10.000 Credits – für Power-User', 3),
    ('Studio', 50000, 99.00, '50.000 Credits – für Studios und Teams', 4)
ON CONFLICT DO NOTHING;
"

# =============================================================================
# Migration: llm_routes table
# =============================================================================
echo "[INFO] Checking llm_routes table..."

run_sql "
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
"

# =============================================================================
# Migration: launcher_tools table
# =============================================================================
echo "[INFO] Checking launcher_tools table..."

run_sql "
CREATE TABLE IF NOT EXISTS launcher_overrides (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tool_id     TEXT NOT NULL,
    config      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_launcher_overrides_tool_id ON launcher_overrides(tool_id);
"

# =============================================================================
# Migration: toolchain_tools table
# =============================================================================
echo "[INFO] Checking toolchain_tools table..."

run_sql "
CREATE TABLE IF NOT EXISTS toolchain_tools (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL UNIQUE,
    description     TEXT,
    input_schema    JSONB NOT NULL DEFAULT '{}'::jsonb,
    enabled         BOOLEAN NOT NULL DEFAULT true,
    write_action    BOOLEAN NOT NULL DEFAULT false,
    requires_confirm BOOLEAN NOT NULL DEFAULT false,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_toolchain_tools_enabled ON toolchain_tools(enabled);
CREATE INDEX IF NOT EXISTS idx_toolchain_tools_sort_order ON toolchain_tools(sort_order);
"

# Insert default toolchain tools if table is empty
run_sql "
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
"

# =============================================================================
# Migration: audit_log table
# =============================================================================
echo "[INFO] Checking audit_log table..."

run_sql "
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
"

# =============================================================================
# Migration: user_skills table
# =============================================================================
echo "[INFO] Checking user_skills table..."

run_sql "
CREATE TABLE IF NOT EXISTS user_skills (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    skill_id    TEXT NOT NULL,
    level       INTEGER NOT NULL DEFAULT 1,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_skills_user_id ON user_skills(user_id);
"

# =============================================================================
# Migration: transactions table
# =============================================================================
echo "[INFO] Checking transactions table..."

run_sql "
CREATE TABLE IF NOT EXISTS transactions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES admin_users(id),
    type        VARCHAR(50) NOT NULL,
    amount      NUMERIC(10,2) NOT NULL,
    currency    VARCHAR(10) DEFAULT 'EUR',
    status      VARCHAR(20) NOT NULL DEFAULT 'pending',
    provider    TEXT,
    provider_tx_id TEXT,
    description TEXT,
    metadata    JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);
CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON transactions(created_at DESC);
"

# =============================================================================
# Migration: schema_migrations table
# =============================================================================
echo "[INFO] Checking schema_migrations table..."

run_sql "
CREATE TABLE IF NOT EXISTS schema_migrations (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"

# Record this migration
run_sql "
INSERT INTO schema_migrations (id, name) VALUES (1, 'initial_schema')
ON CONFLICT (id) DO NOTHING;
"

echo "[INFO] Database migrations completed successfully!"
