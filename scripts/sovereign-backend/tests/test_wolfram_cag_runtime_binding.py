from __future__ import annotations

from pathlib import Path
import importlib.util

import pytest


_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "agent_runtime"
    / "wolfram_cag_runtime_binding.py"
)
_SPEC = importlib.util.spec_from_file_location("wolfram_cag_runtime_binding_test", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_BINDING = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_BINDING)

AUTHORIZATION_BASIS_REF = _BINDING.AUTHORIZATION_BASIS_REF
AUTHORIZATION_BASIS_SHA256 = _BINDING.AUTHORIZATION_BASIS_SHA256
RuntimeBindingError = _BINDING.RuntimeBindingError
build_runtime_evidence_binding = _BINDING.build_runtime_evidence_binding


def _binding(**overrides):
    values = {
        "analysis_id": "cag-analysis-" + "1" * 24,
        "analysis_record_sha256": "2" * 64,
        "repository_revision": "3" * 40,
        "runtime_revision": "3" * 40,
        "immutable_image_digest": "sha256:" + "4" * 64,
        "runtime_container_identity_sha256": "5" * 64,
        "deployed_target_identity": "sovereign-backend",
        "docker_readback_sha256": "6" * 64,
        "patchmon_readback_sha256": "7" * 64,
        "cag_execution_receipt_sha256": "8" * 64,
        "provider_request_id_sha256": "9" * 64,
        "provider_response_sha256": "a" * 64,
        "entitlement_receipt_sha256": "b" * 64,
        "runtime_evidence_readback_verified": True,
        "public_projection_allowed": True,
        "created_at": "2026-09-20T02:00:00Z",
    }
    values.update(overrides)
    return build_runtime_evidence_binding(**values)


def test_runtime_binding_is_deterministic_and_timestamp_is_metadata_only() -> None:
    first = _binding(created_at="2026-09-20T02:00:00Z")
    second = _binding(created_at="2026-09-20T02:05:00Z")

    assert first["bindingSha256"] == second["bindingSha256"]
    assert first["bindingId"] == second["bindingId"]
    assert first["createdAt"] != second["createdAt"]
    assert first["authorizationBasisRef"] == AUTHORIZATION_BASIS_REF
    assert first["authorizationBasisSha256"] == AUTHORIZATION_BASIS_SHA256
    assert AUTHORIZATION_BASIS_SHA256 == "a51863c526e961af71475e3fd64076de33d132bd97cd4946406aea5ed471d908"
    assert first["usageScope"] == "NON_COMMERCIAL_APPROVED"
    assert first["publicProjectionAllowed"] is True


def test_runtime_binding_requires_revision_parity_and_verified_readback() -> None:
    with pytest.raises(RuntimeBindingError, match="revision parity"):
        _binding(runtime_revision="c" * 40)

    with pytest.raises(RuntimeBindingError, match="public projection requires"):
        _binding(runtime_evidence_readback_verified=False)


def test_runtime_binding_migration_has_required_evidence_columns() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "063_wolfram_cag_runtime_evidence_binding.sql"
    ).read_text("utf-8")

    for column in (
        "analysis_record_sha256",
        "immutable_image_digest",
        "runtime_container_identity_sha256",
        "docker_readback_sha256",
        "patchmon_readback_sha256",
        "cag_execution_receipt_sha256",
        "provider_request_id_sha256",
        "provider_response_sha256",
        "authorization_basis_class",
        "authorization_basis_ref",
        "authorization_basis_sha256",
        "authorization_source_readback_state",
        "entitlement_receipt_sha256",
        "runtime_evidence_readback_verified",
        "public_projection_allowed",
    ):
        assert column in migration
    assert "analysis_id TEXT NOT NULL UNIQUE" in migration
    assert "CHECK (usage_scope = 'NON_COMMERCIAL_APPROVED')" in migration
