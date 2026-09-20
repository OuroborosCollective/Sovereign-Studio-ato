BEGIN;

CREATE TABLE IF NOT EXISTS wolfram_cag_runtime_evidence_bindings (
    binding_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL
        CHECK (schema_version = 'sovereign.wolfram-cag-runtime-evidence-binding.v1'),
    binding_sha256 CHAR(64) NOT NULL UNIQUE
        CHECK (binding_sha256 ~ '^[0-9a-f]{64}$'),
    analysis_id TEXT NOT NULL UNIQUE,
    analysis_record_sha256 CHAR(64) NOT NULL
        CHECK (analysis_record_sha256 ~ '^[0-9a-f]{64}$'),
    repository_revision CHAR(40) NOT NULL
        CHECK (repository_revision ~ '^[0-9a-f]{40}$'),
    runtime_revision CHAR(40) NOT NULL
        CHECK (runtime_revision ~ '^[0-9a-f]{40}$'),
    immutable_image_digest TEXT NOT NULL
        CHECK (immutable_image_digest ~ '^sha256:[0-9a-f]{64}$'),
    runtime_container_identity_sha256 CHAR(64) NOT NULL
        CHECK (runtime_container_identity_sha256 ~ '^[0-9a-f]{64}$'),
    deployed_target_identity TEXT NOT NULL
        CHECK (length(btrim(deployed_target_identity)) BETWEEN 1 AND 160),
    docker_readback_sha256 CHAR(64) NOT NULL
        CHECK (docker_readback_sha256 ~ '^[0-9a-f]{64}$'),
    patchmon_readback_sha256 CHAR(64) NOT NULL
        CHECK (patchmon_readback_sha256 ~ '^[0-9a-f]{64}$'),
    cag_execution_receipt_sha256 CHAR(64) NOT NULL
        CHECK (cag_execution_receipt_sha256 ~ '^[0-9a-f]{64}$'),
    provider_request_id_sha256 CHAR(64) NOT NULL
        CHECK (provider_request_id_sha256 ~ '^[0-9a-f]{64}$'),
    provider_response_sha256 CHAR(64) NOT NULL
        CHECK (provider_response_sha256 ~ '^[0-9a-f]{64}$'),
    authorization_basis_class TEXT NOT NULL
        CHECK (authorization_basis_class = 'WOLFRAM_NON_COMMERCIAL_SOURCE_REPLY'),
    authorization_basis_ref TEXT NOT NULL
        CHECK (authorization_basis_ref = 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/issues/1458'),
    authorization_basis_sha256 CHAR(64) NOT NULL
        CHECK (authorization_basis_sha256 ~ '^[0-9a-f]{64}$'),
    authorization_source_readback_state TEXT NOT NULL
        CHECK (authorization_source_readback_state = 'VERIFIED_SCREENSHOT'),
    usage_scope TEXT NOT NULL
        CHECK (usage_scope = 'NON_COMMERCIAL_APPROVED'),
    entitlement_receipt_sha256 CHAR(64) NOT NULL
        CHECK (entitlement_receipt_sha256 ~ '^[0-9a-f]{64}$'),
    runtime_evidence_readback_verified BOOLEAN NOT NULL DEFAULT FALSE,
    public_projection_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (repository_revision = runtime_revision),
    CHECK (
        NOT public_projection_allowed
        OR (
            runtime_evidence_readback_verified
            AND usage_scope = 'NON_COMMERCIAL_APPROVED'
            AND authorization_source_readback_state = 'VERIFIED_SCREENSHOT'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_wolfram_cag_runtime_bindings_revision
    ON wolfram_cag_runtime_evidence_bindings (runtime_revision, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_wolfram_cag_runtime_bindings_component_analysis
    ON wolfram_cag_runtime_evidence_bindings (analysis_id, created_at DESC);

COMMIT;
