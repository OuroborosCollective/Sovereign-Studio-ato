-- Migration 049: Environment-Bound MCP Execution Receipts
-- Issue #1120 — deterministic, immutable receipt storage.
-- This migration defines the persistence contract only. No runtime activation,
-- production apply or effect-ordering success is claimed by repository presence.

BEGIN;

CREATE TABLE environment_manifests (
    manifest_hash           CHAR(64) PRIMARY KEY
        CHECK (manifest_hash ~ '^[0-9a-f]{64}$'),
    environment_id          TEXT NOT NULL,
    kind                    TEXT NOT NULL
        CHECK (kind IN ('development', 'test', 'staging', 'production', 'ephemeral')),
    schema_version          TEXT NOT NULL
        CHECK (schema_version = 'sovereign.environment-mcp-execution.v1'),
    repo_owner              TEXT NOT NULL,
    repo_name               TEXT NOT NULL,
    revision                CHAR(40) NOT NULL
        CHECK (revision ~ '^[0-9a-f]{40}$'),
    network_policy_hash     CHAR(64) NOT NULL
        CHECK (network_policy_hash ~ '^[0-9a-f]{64}$'),
    credential_scope_hash   CHAR(64) NOT NULL
        CHECK (credential_scope_hash ~ '^[0-9a-f]{64}$'),
    allowed_protocols       TEXT[] NOT NULL
        CHECK (cardinality(allowed_protocols) >= 1),
    allowed_egress_hosts    TEXT[] NOT NULL,
    is_production           BOOLEAN NOT NULL,
    CHECK (is_production = (kind = 'production'))
);

CREATE TABLE principal_resolution_receipts (
    receipt_id                  TEXT PRIMARY KEY
        CHECK (receipt_id ~ '^principal:[0-9a-f]{64}$'),
    schema_version              TEXT NOT NULL
        CHECK (schema_version = 'sovereign.environment-mcp-execution.v1'),
    environment_id              TEXT NOT NULL,
    principal_id                TEXT NOT NULL,
    owner_id                    TEXT NOT NULL,
    resolution_method           TEXT NOT NULL
        CHECK (resolution_method IN (
            'server_jwt', 'session_cookie', 'api_key_hash',
            'service_account', 'anonymous'
        )),
    is_server_resolved          BOOLEAN NOT NULL CHECK (is_server_resolved),
    run_id                      TEXT NOT NULL,
    revision                    CHAR(40) NOT NULL
        CHECK (revision ~ '^[0-9a-f]{40}$'),
    client_supplied_candidate   TEXT,
    receipt_hash                CHAR(64) NOT NULL
        CHECK (receipt_hash ~ '^[0-9a-f]{64}$')
);

CREATE TABLE credential_resolution_receipts (
    receipt_id                  TEXT PRIMARY KEY
        CHECK (receipt_id ~ '^credential:[0-9a-f]{64}$'),
    schema_version              TEXT NOT NULL
        CHECK (schema_version = 'sovereign.environment-mcp-execution.v1'),
    environment_id              TEXT NOT NULL,
    credential_id               TEXT NOT NULL,
    owner_id                    TEXT NOT NULL,
    mode                        TEXT NOT NULL
        CHECK (mode IN ('direct', 'on_behalf_of', 'service_account', 'anonymous')),
    provider                    TEXT NOT NULL,
    scope_hash                  CHAR(64) NOT NULL
        CHECK (scope_hash ~ '^[0-9a-f]{64}$'),
    audience                    TEXT,
    executed_as_principal_id    TEXT NOT NULL,
    refresh_version             INTEGER NOT NULL CHECK (refresh_version >= 1),
    is_expired                  BOOLEAN NOT NULL CHECK (NOT is_expired),
    receipt_hash                CHAR(64) NOT NULL
        CHECK (receipt_hash ~ '^[0-9a-f]{64}$'),
    CHECK (mode <> 'on_behalf_of' OR audience IS NOT NULL)
);

CREATE TABLE egress_decision_receipts (
    receipt_id          TEXT PRIMARY KEY
        CHECK (receipt_id ~ '^egress:[0-9a-f]{64}$'),
    schema_version      TEXT NOT NULL
        CHECK (schema_version = 'sovereign.environment-mcp-execution.v1'),
    environment_id      TEXT NOT NULL,
    environment_kind    TEXT NOT NULL
        CHECK (environment_kind IN ('development', 'test', 'staging', 'production', 'ephemeral')),
    target_host         TEXT NOT NULL,
    resolved_ip         INET,
    target_port         INTEGER CHECK (target_port BETWEEN 1 AND 65535),
    protocol            TEXT NOT NULL,
    decision            TEXT NOT NULL CHECK (decision IN ('allow', 'block')),
    block_reason        TEXT CHECK (block_reason IN (
        'loopback', 'metadata_ip', 'private_network', 'blocked_hostname',
        'environment_policy', 'unknown_ip_class', 'protocol_not_allowed',
        'dns_evidence_required', 'production_target_from_nonprod'
    )),
    receipt_hash        CHAR(64) NOT NULL
        CHECK (receipt_hash ~ '^[0-9a-f]{64}$'),
    CHECK (
        (decision = 'allow' AND block_reason IS NULL AND resolved_ip IS NOT NULL)
        OR (decision = 'block' AND block_reason IS NOT NULL)
    )
);

CREATE TABLE mcp_installation_bindings (
    binding_id              TEXT PRIMARY KEY
        CHECK (binding_id ~ '^installation:[0-9a-f]{64}$'),
    tool_id                 TEXT NOT NULL,
    server_id               TEXT NOT NULL,
    installation_id         TEXT NOT NULL,
    registry_revision       CHAR(40) NOT NULL
        CHECK (registry_revision ~ '^[0-9a-f]{40}$'),
    verified_at_revision    CHAR(40) NOT NULL
        CHECK (verified_at_revision ~ '^[0-9a-f]{40}$'),
    binding_hash            CHAR(64) NOT NULL
        CHECK (binding_hash ~ '^[0-9a-f]{64}$')
);

CREATE TABLE execution_identity_receipts (
    receipt_id                  TEXT PRIMARY KEY
        CHECK (receipt_id ~ '^execution:[0-9a-f]{64}$'),
    schema_version              TEXT NOT NULL
        CHECK (schema_version = 'sovereign.environment-mcp-execution.v1'),
    run_id                      TEXT NOT NULL,
    revision                    CHAR(40) NOT NULL
        CHECK (revision ~ '^[0-9a-f]{40}$'),
    environment_manifest_hash   CHAR(64) NOT NULL
        REFERENCES environment_manifests(manifest_hash) ON DELETE RESTRICT,
    principal_receipt_id        TEXT NOT NULL
        REFERENCES principal_resolution_receipts(receipt_id) ON DELETE RESTRICT,
    credential_receipt_id       TEXT NOT NULL
        REFERENCES credential_resolution_receipts(receipt_id) ON DELETE RESTRICT,
    egress_receipt_id           TEXT NOT NULL
        REFERENCES egress_decision_receipts(receipt_id) ON DELETE RESTRICT,
    installation_binding_id     TEXT NOT NULL
        REFERENCES mcp_installation_bindings(binding_id) ON DELETE RESTRICT,
    tool_id                     TEXT NOT NULL,
    environment_kind            TEXT NOT NULL
        CHECK (environment_kind IN ('development', 'test', 'staging', 'production', 'ephemeral')),
    is_mutation                 BOOLEAN NOT NULL,
    receipt_hash                CHAR(64) NOT NULL
        CHECK (receipt_hash ~ '^[0-9a-f]{64}$')
);

CREATE OR REPLACE FUNCTION environment_execution_reject_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'ENVIRONMENT_EXECUTION_APPEND_ONLY_VIOLATION:%:%', TG_TABLE_NAME, TG_OP;
END
$$;

CREATE OR REPLACE FUNCTION environment_execution_validate_composite()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    manifest_environment_id TEXT;
    manifest_kind TEXT;
    manifest_owner TEXT;
    manifest_revision CHAR(40);
    principal_environment_id TEXT;
    principal_owner TEXT;
    principal_id_value TEXT;
    principal_run_id TEXT;
    principal_revision CHAR(40);
    credential_environment_id TEXT;
    credential_owner TEXT;
    credential_principal TEXT;
    credential_mode TEXT;
    egress_environment_id TEXT;
    egress_kind TEXT;
    egress_decision TEXT;
    binding_tool_id TEXT;
    binding_revision CHAR(40);
BEGIN
    SELECT environment_id, kind, repo_owner, revision
      INTO STRICT manifest_environment_id, manifest_kind, manifest_owner, manifest_revision
      FROM environment_manifests
     WHERE manifest_hash = NEW.environment_manifest_hash;

    SELECT environment_id, owner_id, principal_id, run_id, revision
      INTO STRICT principal_environment_id, principal_owner, principal_id_value,
                  principal_run_id, principal_revision
      FROM principal_resolution_receipts
     WHERE receipt_id = NEW.principal_receipt_id;

    SELECT environment_id, owner_id, executed_as_principal_id, mode
      INTO STRICT credential_environment_id, credential_owner,
                  credential_principal, credential_mode
      FROM credential_resolution_receipts
     WHERE receipt_id = NEW.credential_receipt_id;

    SELECT environment_id, environment_kind, decision
      INTO STRICT egress_environment_id, egress_kind, egress_decision
      FROM egress_decision_receipts
     WHERE receipt_id = NEW.egress_receipt_id;

    SELECT tool_id, verified_at_revision
      INTO STRICT binding_tool_id, binding_revision
      FROM mcp_installation_bindings
     WHERE binding_id = NEW.installation_binding_id;

    IF manifest_environment_id <> principal_environment_id
       OR manifest_environment_id <> credential_environment_id
       OR manifest_environment_id <> egress_environment_id
       OR manifest_kind <> egress_kind
       OR manifest_kind <> NEW.environment_kind
       OR manifest_owner <> principal_owner
       OR principal_owner <> credential_owner
       OR principal_id_value <> credential_principal
       OR principal_run_id <> NEW.run_id
       OR manifest_revision <> principal_revision
       OR manifest_revision <> binding_revision
       OR manifest_revision <> NEW.revision
       OR binding_tool_id <> NEW.tool_id
       OR egress_decision <> 'allow'
       OR (NEW.is_mutation AND credential_mode = 'anonymous') THEN
        RAISE EXCEPTION 'ENVIRONMENT_EXECUTION_COMPOSITE_CONTRACT_VIOLATION';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER execution_identity_validate_before_insert
    BEFORE INSERT ON execution_identity_receipts
    FOR EACH ROW EXECUTE FUNCTION environment_execution_validate_composite();

CREATE TRIGGER environment_manifests_append_only
    BEFORE UPDATE OR DELETE ON environment_manifests
    FOR EACH ROW EXECUTE FUNCTION environment_execution_reject_mutation();
CREATE TRIGGER principal_receipts_append_only
    BEFORE UPDATE OR DELETE ON principal_resolution_receipts
    FOR EACH ROW EXECUTE FUNCTION environment_execution_reject_mutation();
CREATE TRIGGER credential_receipts_append_only
    BEFORE UPDATE OR DELETE ON credential_resolution_receipts
    FOR EACH ROW EXECUTE FUNCTION environment_execution_reject_mutation();
CREATE TRIGGER egress_receipts_append_only
    BEFORE UPDATE OR DELETE ON egress_decision_receipts
    FOR EACH ROW EXECUTE FUNCTION environment_execution_reject_mutation();
CREATE TRIGGER installation_bindings_append_only
    BEFORE UPDATE OR DELETE ON mcp_installation_bindings
    FOR EACH ROW EXECUTE FUNCTION environment_execution_reject_mutation();
CREATE TRIGGER execution_receipts_append_only
    BEFORE UPDATE OR DELETE ON execution_identity_receipts
    FOR EACH ROW EXECUTE FUNCTION environment_execution_reject_mutation();

CREATE INDEX idx_env_manifest_environment
    ON environment_manifests (environment_id, revision);
CREATE INDEX idx_principal_environment_run
    ON principal_resolution_receipts (environment_id, run_id, revision);
CREATE INDEX idx_credential_environment_owner
    ON credential_resolution_receipts (environment_id, owner_id);
CREATE INDEX idx_egress_environment_decision
    ON egress_decision_receipts (environment_id, decision);
CREATE INDEX idx_execution_run_revision
    ON execution_identity_receipts (run_id, revision);
CREATE INDEX idx_installation_tool_revision
    ON mcp_installation_bindings (tool_id, verified_at_revision);

-- Fail closed until an independently verified runtime session identity contract
-- installs explicit policies. FORCE RLS prevents table-owner bypass; PostgreSQL
-- superusers remain a database-level trust boundary and are not claimed here.
ALTER TABLE environment_manifests ENABLE ROW LEVEL SECURITY;
ALTER TABLE environment_manifests FORCE ROW LEVEL SECURITY;
ALTER TABLE principal_resolution_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE principal_resolution_receipts FORCE ROW LEVEL SECURITY;
ALTER TABLE credential_resolution_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE credential_resolution_receipts FORCE ROW LEVEL SECURITY;
ALTER TABLE egress_decision_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE egress_decision_receipts FORCE ROW LEVEL SECURITY;
ALTER TABLE mcp_installation_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE mcp_installation_bindings FORCE ROW LEVEL SECURITY;
ALTER TABLE execution_identity_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE execution_identity_receipts FORCE ROW LEVEL SECURITY;

COMMIT;
