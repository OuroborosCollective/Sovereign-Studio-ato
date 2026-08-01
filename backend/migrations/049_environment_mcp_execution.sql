-- Migration 049: Environment-Bound MCP Execution Receipts
-- Issue #1120 — immutable receipt store for all MCP execution identity facts.
-- Receipts are write-once; no UPDATE or DELETE is permitted via application code.

BEGIN;

-- Environment manifests (compiled + verified at runtime; stored for audit)
CREATE TABLE IF NOT EXISTS environment_manifests (
    id                      BIGSERIAL PRIMARY KEY,
    manifest_hash           TEXT        NOT NULL UNIQUE,
    environment_id          TEXT        NOT NULL,
    kind                    TEXT        NOT NULL,
    schema_version          TEXT        NOT NULL,
    repo_owner              TEXT        NOT NULL,
    repo_name               TEXT        NOT NULL,
    revision                CHAR(40),
    network_policy_hash     TEXT        NOT NULL,
    credential_scope_hash   TEXT        NOT NULL,
    allowed_protocols       TEXT[]      NOT NULL,
    allowed_egress_hosts    TEXT[]      NOT NULL DEFAULT '{}',
    is_production           BOOLEAN     NOT NULL DEFAULT FALSE,
    compiled_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Principal resolution receipts (server-side only; client candidate stored for audit)
CREATE TABLE IF NOT EXISTS principal_resolution_receipts (
    id                          BIGSERIAL PRIMARY KEY,
    receipt_id                  TEXT        NOT NULL UNIQUE,
    schema_version              TEXT        NOT NULL,
    environment_id              TEXT        NOT NULL,
    principal_id                TEXT        NOT NULL,
    owner_id                    TEXT        NOT NULL,
    resolution_method           TEXT        NOT NULL,
    is_server_resolved          BOOLEAN     NOT NULL DEFAULT TRUE,
    run_id                      TEXT,
    revision                    CHAR(40),
    client_supplied_candidate   TEXT,       -- stored for audit only; never used as auth proof
    receipt_hash                TEXT        NOT NULL,
    resolved_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Credential resolution receipts (no secret material; fingerprints only)
CREATE TABLE IF NOT EXISTS credential_resolution_receipts (
    id                          BIGSERIAL PRIMARY KEY,
    receipt_id                  TEXT        NOT NULL UNIQUE,
    schema_version              TEXT        NOT NULL,
    environment_id              TEXT        NOT NULL,
    credential_id               TEXT        NOT NULL,
    owner_id                    TEXT        NOT NULL,
    mode                        TEXT        NOT NULL,
    provider                    TEXT        NOT NULL,
    scope_hash                  TEXT        NOT NULL,   -- SHA-256 of sorted scopes; raw scopes not stored
    audience                    TEXT,
    executed_as_principal_id    TEXT        NOT NULL,
    refresh_version             INT         NOT NULL DEFAULT 1,
    receipt_hash                TEXT        NOT NULL,
    resolved_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Egress decision receipts (committed BEFORE network connection)
CREATE TABLE IF NOT EXISTS egress_decision_receipts (
    id                  BIGSERIAL PRIMARY KEY,
    receipt_id          TEXT        NOT NULL UNIQUE,
    schema_version      TEXT        NOT NULL,
    environment_id      TEXT        NOT NULL,
    environment_kind    TEXT        NOT NULL,
    target_host         TEXT        NOT NULL,
    target_port         INT,
    protocol            TEXT        NOT NULL,
    decision            TEXT        NOT NULL,   -- 'allow' | 'block'
    block_reason        TEXT,
    receipt_hash        TEXT        NOT NULL,
    decided_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- MCP installation bindings (registry-revision-bound; prevents tool confusion)
CREATE TABLE IF NOT EXISTS mcp_installation_bindings (
    id                      BIGSERIAL PRIMARY KEY,
    binding_id              TEXT        NOT NULL UNIQUE,
    tool_id                 TEXT        NOT NULL,
    server_id               TEXT        NOT NULL,
    installation_id         TEXT        NOT NULL,
    registry_revision       CHAR(40)    NOT NULL,
    verified_at_revision    CHAR(40),
    binding_hash            TEXT        NOT NULL,
    bound_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Composite execution identity receipts (write-once; references all components)
CREATE TABLE IF NOT EXISTS execution_identity_receipts (
    id                          BIGSERIAL PRIMARY KEY,
    receipt_id                  TEXT        NOT NULL UNIQUE,
    schema_version              TEXT        NOT NULL,
    run_id                      TEXT        NOT NULL,
    environment_manifest_hash   TEXT        NOT NULL REFERENCES environment_manifests(manifest_hash),
    principal_receipt_id        TEXT        NOT NULL REFERENCES principal_resolution_receipts(receipt_id),
    credential_receipt_id       TEXT        NOT NULL REFERENCES credential_resolution_receipts(receipt_id),
    egress_receipt_id           TEXT        NOT NULL REFERENCES egress_decision_receipts(receipt_id),
    installation_binding_id     TEXT        NOT NULL REFERENCES mcp_installation_bindings(binding_id),
    tool_id                     TEXT        NOT NULL,
    environment_kind            TEXT        NOT NULL,
    is_mutation                 BOOLEAN     NOT NULL DEFAULT FALSE,
    receipt_hash                TEXT        NOT NULL,
    executed_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_env_manifest_env_id
    ON environment_manifests (environment_id);

CREATE INDEX IF NOT EXISTS idx_prr_environment_id
    ON principal_resolution_receipts (environment_id);

CREATE INDEX IF NOT EXISTS idx_prr_principal_id
    ON principal_resolution_receipts (principal_id);

CREATE INDEX IF NOT EXISTS idx_crr_environment_id
    ON credential_resolution_receipts (environment_id);

CREATE INDEX IF NOT EXISTS idx_crr_credential_id
    ON credential_resolution_receipts (credential_id);

CREATE INDEX IF NOT EXISTS idx_edr_decision
    ON egress_decision_receipts (decision);

CREATE INDEX IF NOT EXISTS idx_edr_environment_id
    ON egress_decision_receipts (environment_id);

CREATE INDEX IF NOT EXISTS idx_eir_run_id
    ON execution_identity_receipts (run_id);

CREATE INDEX IF NOT EXISTS idx_eir_environment_kind
    ON execution_identity_receipts (environment_kind);

CREATE INDEX IF NOT EXISTS idx_mcp_tool_id
    ON mcp_installation_bindings (tool_id);

-- Row-level security
ALTER TABLE environment_manifests ENABLE ROW LEVEL SECURITY;
ALTER TABLE principal_resolution_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE credential_resolution_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE egress_decision_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE mcp_installation_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE execution_identity_receipts ENABLE ROW LEVEL SECURITY;

COMMIT;
