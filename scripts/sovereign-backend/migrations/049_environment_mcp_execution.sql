-- Migration 049: Environment-Bound MCP Execution Receipts
-- Issue #1120 — immutable receipt store for all MCP execution identity facts.
-- Receipts are write-once; no UPDATE or DELETE is permitted via application code.

BEGIN;

-- Environment manifests (compiled + verified at runtime; stored for audit)
CREATE TABLE IF NOT EXISTS environment_manifests (
    manifest_hash           TEXT        PRIMARY KEY,
    environment_id          TEXT        NOT NULL,
    kind                    TEXT        NOT NULL,
    schema_version          TEXT        NOT NULL,
    repo_owner              TEXT        NOT NULL,
    repo_name               TEXT        NOT NULL,
    revision                CHAR(40),
    network_policy_hash     TEXT        NOT NULL,
    credential_scope_hash   TEXT        NOT NULL,
    allowed_protocols       TEXT[]      NOT NULL,
    allowed_egress_hosts    TEXT[]      NOT NULL,
    is_production           BOOLEAN     NOT NULL,
    CHECK (manifest_hash ~ '^[0-9a-f]{64}$'),
    CHECK (network_policy_hash ~ '^[0-9a-f]{64}$'),
    CHECK (credential_scope_hash ~ '^[0-9a-f]{64}$'),
    CHECK (revision IS NULL OR revision ~ '^[0-9a-f]{40}$'),
    CHECK (cardinality(allowed_protocols) > 0),
    CHECK ((kind = 'production') = is_production),
    CHECK (kind IN ('development', 'test', 'staging', 'production', 'ephemeral'))
);

-- Principal resolution receipts (server-side only; client candidate stored for audit)
CREATE TABLE IF NOT EXISTS principal_resolution_receipts (
    receipt_id                  TEXT        PRIMARY KEY,
    schema_version              TEXT        NOT NULL,
    environment_id              TEXT        NOT NULL,
    principal_id                TEXT        NOT NULL,
    owner_id                    TEXT        NOT NULL,
    resolution_method           TEXT        NOT NULL,
    is_server_resolved          BOOLEAN     NOT NULL CHECK (is_server_resolved),
    run_id                      TEXT,
    revision                    CHAR(40),
    client_supplied_candidate   TEXT,       -- stored for audit only; never used as auth proof
    receipt_hash                TEXT        NOT NULL CHECK (receipt_hash ~ '^[0-9a-f]{64}$'),
    CHECK (receipt_id ~ '^principal-[0-9a-f]{64}$'),
    CHECK (revision IS NULL OR revision ~ '^[0-9a-f]{40}$'),
    CHECK (run_id IS NULL OR btrim(run_id) <> '')
);

-- Credential resolution receipts (no secret material; fingerprints only)
CREATE TABLE IF NOT EXISTS credential_resolution_receipts (
    receipt_id                  TEXT        PRIMARY KEY,
    schema_version              TEXT        NOT NULL,
    environment_id              TEXT        NOT NULL,
    credential_id               TEXT        NOT NULL,
    owner_id                    TEXT        NOT NULL,
    mode                        TEXT        NOT NULL,
    provider                    TEXT        NOT NULL,
    scope_hash                  TEXT        NOT NULL CHECK (scope_hash ~ '^[0-9a-f]{64}$'),
    audience                    TEXT,
    executed_as_principal_id    TEXT        NOT NULL,
    refresh_version             INT         NOT NULL CHECK (refresh_version >= 1),
    receipt_hash                TEXT        NOT NULL CHECK (receipt_hash ~ '^[0-9a-f]{64}$'),
    CHECK (receipt_id ~ '^credential-[0-9a-f]{64}$'),
    CHECK (mode IN ('direct', 'on_behalf_of', 'service_account', 'anonymous')),
    CHECK (mode <> 'on_behalf_of' OR audience IS NOT NULL)
);

-- Egress decision receipts (committed BEFORE network connection)
CREATE TABLE IF NOT EXISTS egress_decision_receipts (
    receipt_id          TEXT        PRIMARY KEY,
    schema_version      TEXT        NOT NULL,
    environment_id      TEXT        NOT NULL,
    environment_kind    TEXT        NOT NULL,
    target_host         TEXT        NOT NULL,
    resolved_ip         INET,
    target_port         INT CHECK (target_port IS NULL OR target_port BETWEEN 1 AND 65535),
    protocol            TEXT        NOT NULL,
    decision            TEXT        NOT NULL CHECK (decision IN ('allow', 'block')),
    block_reason        TEXT,
    receipt_hash        TEXT        NOT NULL CHECK (receipt_hash ~ '^[0-9a-f]{64}$'),
    CHECK (receipt_id ~ '^egress-[0-9a-f]{64}$'),
    CHECK ((decision = 'allow' AND block_reason IS NULL AND resolved_ip IS NOT NULL)
        OR (decision = 'block' AND block_reason IS NOT NULL))
);

-- MCP installation bindings (registry-revision-bound; prevents tool confusion)
CREATE TABLE IF NOT EXISTS mcp_installation_bindings (
    binding_id              TEXT        PRIMARY KEY,
    tool_id                 TEXT        NOT NULL,
    server_id               TEXT        NOT NULL,
    installation_id         TEXT        NOT NULL,
    registry_revision       CHAR(40)    NOT NULL,
    verified_at_revision    CHAR(40),
    binding_hash            TEXT        NOT NULL CHECK (binding_hash ~ '^[0-9a-f]{64}$'),
    CHECK (binding_id ~ '^installation-[0-9a-f]{64}$'),
    CHECK (registry_revision ~ '^[0-9a-f]{40}$'),
    CHECK (verified_at_revision IS NULL OR verified_at_revision ~ '^[0-9a-f]{40}$')
);

-- Composite execution identity receipts (write-once; references all components)
CREATE TABLE IF NOT EXISTS execution_identity_receipts (
    receipt_id                  TEXT        PRIMARY KEY,
    schema_version              TEXT        NOT NULL,
    run_id                      TEXT        NOT NULL,
    environment_manifest_hash   TEXT        NOT NULL REFERENCES environment_manifests(manifest_hash),
    principal_receipt_id        TEXT        NOT NULL REFERENCES principal_resolution_receipts(receipt_id),
    credential_receipt_id       TEXT        NOT NULL REFERENCES credential_resolution_receipts(receipt_id),
    egress_receipt_id           TEXT        NOT NULL REFERENCES egress_decision_receipts(receipt_id),
    installation_binding_id     TEXT        NOT NULL REFERENCES mcp_installation_bindings(binding_id),
    tool_id                     TEXT        NOT NULL,
    environment_kind            TEXT        NOT NULL,
    is_mutation                 BOOLEAN     NOT NULL,
    receipt_hash                TEXT        NOT NULL CHECK (receipt_hash ~ '^[0-9a-f]{64}$'),
    CHECK (receipt_id ~ '^execution-[0-9a-f]{64}$')
);

-- Cross-table execution identity validation. The trigger is deliberately
-- SECURITY DEFINER so fail-closed RLS cannot turn integrity validation into a
-- caller-controlled omission; it uses no dynamic SQL and a fixed search_path.
CREATE OR REPLACE FUNCTION sovereign_validate_execution_identity_receipt()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    manifest environment_manifests%ROWTYPE;
    principal principal_resolution_receipts%ROWTYPE;
    credential credential_resolution_receipts%ROWTYPE;
    egress egress_decision_receipts%ROWTYPE;
    binding mcp_installation_bindings%ROWTYPE;
BEGIN
    SELECT * INTO STRICT manifest
      FROM environment_manifests
     WHERE manifest_hash = NEW.environment_manifest_hash;
    SELECT * INTO STRICT principal
      FROM principal_resolution_receipts
     WHERE receipt_id = NEW.principal_receipt_id;
    SELECT * INTO STRICT credential
      FROM credential_resolution_receipts
     WHERE receipt_id = NEW.credential_receipt_id;
    SELECT * INTO STRICT egress
      FROM egress_decision_receipts
     WHERE receipt_id = NEW.egress_receipt_id;
    SELECT * INTO STRICT binding
      FROM mcp_installation_bindings
     WHERE binding_id = NEW.installation_binding_id;

    IF principal.environment_id <> manifest.environment_id
       OR credential.environment_id <> manifest.environment_id
       OR egress.environment_id <> manifest.environment_id THEN
        RAISE EXCEPTION 'EXECUTION_ENVIRONMENT_ID_MISMATCH';
    END IF;
    IF principal.run_id IS DISTINCT FROM NEW.run_id THEN
        RAISE EXCEPTION 'EXECUTION_RUN_ID_MISMATCH';
    END IF;
    IF principal.revision IS DISTINCT FROM manifest.revision THEN
        RAISE EXCEPTION 'EXECUTION_PRINCIPAL_REVISION_MISMATCH';
    END IF;
    IF credential.owner_id <> principal.owner_id
       OR credential.executed_as_principal_id <> principal.principal_id THEN
        RAISE EXCEPTION 'EXECUTION_CREDENTIAL_IDENTITY_MISMATCH';
    END IF;
    IF egress.environment_kind <> manifest.kind
       OR NEW.environment_kind <> manifest.kind THEN
        RAISE EXCEPTION 'EXECUTION_ENVIRONMENT_KIND_MISMATCH';
    END IF;
    IF egress.decision <> 'allow' OR egress.resolved_ip IS NULL THEN
        RAISE EXCEPTION 'EXECUTION_EGRESS_NOT_VERIFIED';
    END IF;
    IF binding.tool_id <> NEW.tool_id THEN
        RAISE EXCEPTION 'EXECUTION_TOOL_BINDING_MISMATCH';
    END IF;
    IF binding.verified_at_revision IS DISTINCT FROM manifest.revision THEN
        RAISE EXCEPTION 'EXECUTION_INSTALLATION_REVISION_MISMATCH';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER validate_execution_identity_receipt
BEFORE INSERT ON execution_identity_receipts
FOR EACH ROW EXECUTE FUNCTION sovereign_validate_execution_identity_receipt();

-- Immutable means technically immutable, not merely documented as write-once.
CREATE OR REPLACE FUNCTION sovereign_reject_receipt_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'IMMUTABLE_EXECUTION_RECEIPT_STORE';
END;
$$;

CREATE TRIGGER immutable_environment_manifests
BEFORE UPDATE OR DELETE ON environment_manifests
FOR EACH ROW EXECUTE FUNCTION sovereign_reject_receipt_mutation();
CREATE TRIGGER immutable_principal_resolution_receipts
BEFORE UPDATE OR DELETE ON principal_resolution_receipts
FOR EACH ROW EXECUTE FUNCTION sovereign_reject_receipt_mutation();
CREATE TRIGGER immutable_credential_resolution_receipts
BEFORE UPDATE OR DELETE ON credential_resolution_receipts
FOR EACH ROW EXECUTE FUNCTION sovereign_reject_receipt_mutation();
CREATE TRIGGER immutable_egress_decision_receipts
BEFORE UPDATE OR DELETE ON egress_decision_receipts
FOR EACH ROW EXECUTE FUNCTION sovereign_reject_receipt_mutation();
CREATE TRIGGER immutable_mcp_installation_bindings
BEFORE UPDATE OR DELETE ON mcp_installation_bindings
FOR EACH ROW EXECUTE FUNCTION sovereign_reject_receipt_mutation();
CREATE TRIGGER immutable_execution_identity_receipts
BEFORE UPDATE OR DELETE ON execution_identity_receipts
FOR EACH ROW EXECUTE FUNCTION sovereign_reject_receipt_mutation();

REVOKE UPDATE, DELETE ON environment_manifests FROM PUBLIC;
REVOKE UPDATE, DELETE ON principal_resolution_receipts FROM PUBLIC;
REVOKE UPDATE, DELETE ON credential_resolution_receipts FROM PUBLIC;
REVOKE UPDATE, DELETE ON egress_decision_receipts FROM PUBLIC;
REVOKE UPDATE, DELETE ON mcp_installation_bindings FROM PUBLIC;
REVOKE UPDATE, DELETE ON execution_identity_receipts FROM PUBLIC;

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
