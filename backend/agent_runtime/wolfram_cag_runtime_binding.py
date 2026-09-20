"""Runtime-evidence binding for real Wolfram CAG analysis records (#1626).

This module does not call Wolfram and never receives a raw credential. It binds an
already persisted partner-analysis record to exact runtime/deployment evidence
collected independently by the operator. The binding is append-only/idempotent:
one analysis id can have exactly one canonical runtime binding.

The non-commercial authorization basis is intentionally narrow and source-bound
to issue #1458, which records the owner-supplied Wolfram reply screenshot.
Commercial use, Agent One and raw-provider redistribution are not inferred.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

SCHEMA_VERSION = "sovereign.wolfram-cag-runtime-evidence-binding.v1"
AUTHORIZATION_BASIS_CLASS = "WOLFRAM_NON_COMMERCIAL_SOURCE_REPLY"
AUTHORIZATION_BASIS_REF = (
    "https://github.com/OuroborosCollective/Sovereign-Studio-ato/issues/1458"
)
AUTHORIZATION_SOURCE_READBACK_STATE = "VERIFIED_SCREENSHOT"
USAGE_SCOPE = "NON_COMMERCIAL_APPROVED"
PUBLIC_OUTPUT_BOUNDARY = "DERIVED_PUBLIC_SAFE_ONLY"
AUTHORIZATION_BASIS_EVIDENCE: dict[str, Any] = {
    "authorizationBasisClass": AUTHORIZATION_BASIS_CLASS,
    "authorizationBasisRef": AUTHORIZATION_BASIS_REF,
    "authorizationSourceReadbackState": AUTHORIZATION_SOURCE_READBACK_STATE,
    "usageScope": USAGE_SCOPE,
    "attribution": "OPTIONAL",
    "commercialUseAuthorized": False,
    "publicOutputBoundary": PUBLIC_OUTPUT_BOUNDARY,
}

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class RuntimeBindingError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


AUTHORIZATION_BASIS_SHA256 = sha256_json(AUTHORIZATION_BASIS_EVIDENCE)


def _sha(value: Any, *, label: str) -> str:
    selected = str(value or "").strip().casefold()
    if not _HEX64.fullmatch(selected):
        raise RuntimeBindingError(f"{label} must be a lowercase SHA-256")
    return selected


def _revision(value: Any, *, label: str) -> str:
    selected = str(value or "").strip().casefold()
    if not _HEX40.fullmatch(selected):
        raise RuntimeBindingError(f"{label} must be an exact 40-character Git SHA")
    return selected


def _digest(value: Any) -> str:
    selected = str(value or "").strip().casefold()
    if not _DIGEST.fullmatch(selected):
        raise RuntimeBindingError("immutable image digest must be sha256:<64 hex>")
    return selected


def _target(value: Any) -> str:
    selected = " ".join(str(value or "").replace("\x00", "").split())[:160]
    if not selected:
        raise RuntimeBindingError("deployed target identity is required")
    return selected


def build_runtime_evidence_binding(
    *,
    analysis_id: str,
    analysis_record_sha256: str,
    repository_revision: str,
    runtime_revision: str,
    immutable_image_digest: str,
    runtime_container_identity_sha256: str,
    deployed_target_identity: str,
    docker_readback_sha256: str,
    patchmon_readback_sha256: str,
    cag_execution_receipt_sha256: str,
    provider_request_id_sha256: str,
    provider_response_sha256: str,
    entitlement_receipt_sha256: str,
    runtime_evidence_readback_verified: bool,
    public_projection_allowed: bool,
    created_at: str | None = None,
) -> dict[str, Any]:
    selected_analysis_id = str(analysis_id or "").strip()
    if not re.fullmatch(r"cag-analysis-[0-9a-f]{24}", selected_analysis_id):
        raise RuntimeBindingError("analysis_id is invalid")
    repository = _revision(repository_revision, label="repository revision")
    runtime = _revision(runtime_revision, label="runtime revision")
    if repository != runtime:
        raise RuntimeBindingError("repository/runtime revision parity is required")
    if public_projection_allowed and not runtime_evidence_readback_verified:
        raise RuntimeBindingError("public projection requires verified runtime readback")

    causal = {
        "schemaVersion": SCHEMA_VERSION,
        "analysisId": selected_analysis_id,
        "analysisRecordSha256": _sha(
            analysis_record_sha256, label="analysis record sha256"
        ),
        "repositoryRevision": repository,
        "runtimeRevision": runtime,
        "immutableImageDigest": _digest(immutable_image_digest),
        "runtimeContainerIdentitySha256": _sha(
            runtime_container_identity_sha256,
            label="runtime container identity sha256",
        ),
        "deployedTargetIdentity": _target(deployed_target_identity),
        "dockerReadbackSha256": _sha(
            docker_readback_sha256, label="docker readback sha256"
        ),
        "patchmonReadbackSha256": _sha(
            patchmon_readback_sha256, label="patchmon readback sha256"
        ),
        "cagExecutionReceiptSha256": _sha(
            cag_execution_receipt_sha256,
            label="CAG execution receipt sha256",
        ),
        "providerRequestIdSha256": _sha(
            provider_request_id_sha256, label="provider request id sha256"
        ),
        "providerResponseSha256": _sha(
            provider_response_sha256, label="provider response sha256"
        ),
        "authorizationBasisClass": AUTHORIZATION_BASIS_CLASS,
        "authorizationBasisRef": AUTHORIZATION_BASIS_REF,
        "authorizationBasisSha256": AUTHORIZATION_BASIS_SHA256,
        "authorizationSourceReadbackState": AUTHORIZATION_SOURCE_READBACK_STATE,
        "usageScope": USAGE_SCOPE,
        "entitlementReceiptSha256": _sha(
            entitlement_receipt_sha256, label="entitlement receipt sha256"
        ),
        "runtimeEvidenceReadbackVerified": bool(runtime_evidence_readback_verified),
        "publicProjectionAllowed": bool(public_projection_allowed),
    }
    binding_sha256 = sha256_json(causal)
    return {
        **causal,
        "bindingId": f"cag-runtime-binding-{binding_sha256[:24]}",
        "bindingSha256": binding_sha256,
        "createdAt": str(created_at or "").strip() or None,
    }


def _row_projection(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "bindingId": row["binding_id"],
        "schemaVersion": row["schema_version"],
        "bindingSha256": row["binding_sha256"],
        "analysisId": row["analysis_id"],
        "analysisRecordSha256": row["analysis_record_sha256"],
        "repositoryRevision": row["repository_revision"],
        "runtimeRevision": row["runtime_revision"],
        "immutableImageDigest": row["immutable_image_digest"],
        "runtimeContainerIdentitySha256": row["runtime_container_identity_sha256"],
        "deployedTargetIdentity": row["deployed_target_identity"],
        "dockerReadbackSha256": row["docker_readback_sha256"],
        "patchmonReadbackSha256": row["patchmon_readback_sha256"],
        "cagExecutionReceiptSha256": row["cag_execution_receipt_sha256"],
        "providerRequestIdSha256": row["provider_request_id_sha256"],
        "providerResponseSha256": row["provider_response_sha256"],
        "authorizationBasisClass": row["authorization_basis_class"],
        "authorizationBasisRef": row["authorization_basis_ref"],
        "authorizationBasisSha256": row["authorization_basis_sha256"],
        "authorizationSourceReadbackState": row[
            "authorization_source_readback_state"
        ],
        "usageScope": row["usage_scope"],
        "entitlementReceiptSha256": row["entitlement_receipt_sha256"],
        "runtimeEvidenceReadbackVerified": bool(
            row["runtime_evidence_readback_verified"]
        ),
        "publicProjectionAllowed": bool(row["public_projection_allowed"]),
    }


def persist_runtime_evidence_binding(connection: Any, binding: Mapping[str, Any]) -> dict[str, Any]:
    """Persist one binding only after the referenced analysis record matches exactly."""
    required = {
        "bindingId",
        "bindingSha256",
        "analysisId",
        "analysisRecordSha256",
        "repositoryRevision",
        "runtimeRevision",
        "immutableImageDigest",
        "runtimeContainerIdentitySha256",
        "deployedTargetIdentity",
        "dockerReadbackSha256",
        "patchmonReadbackSha256",
        "cagExecutionReceiptSha256",
        "providerRequestIdSha256",
        "providerResponseSha256",
        "authorizationBasisClass",
        "authorizationBasisRef",
        "authorizationBasisSha256",
        "authorizationSourceReadbackState",
        "usageScope",
        "entitlementReceiptSha256",
        "runtimeEvidenceReadbackVerified",
        "publicProjectionAllowed",
    }
    if not required.issubset(binding):
        raise RuntimeBindingError("runtime evidence binding is incomplete")

    cursor = connection.cursor()
    try:
        cursor.execute(
            """SELECT analysis_id, record_sha256, repository_revision,
                      runtime_revision, provider_response_sha256
               FROM wolfram_cag_analysis_records
               WHERE analysis_id=%s
               LIMIT 1""",
            (binding["analysisId"],),
        )
        analysis = cursor.fetchone()
        if not analysis:
            raise RuntimeBindingError("analysis record does not exist")
        observed = tuple(str(value or "").strip() for value in analysis)
        expected = (
            str(binding["analysisId"]),
            str(binding["analysisRecordSha256"]),
            str(binding["repositoryRevision"]),
            str(binding["runtimeRevision"]),
            str(binding["providerResponseSha256"]),
        )
        if observed != expected:
            raise RuntimeBindingError("analysis record/runtime evidence identity mismatch")

        cursor.execute(
            """INSERT INTO wolfram_cag_runtime_evidence_bindings (
                   binding_id, schema_version, binding_sha256, analysis_id,
                   analysis_record_sha256, repository_revision, runtime_revision,
                   immutable_image_digest, runtime_container_identity_sha256,
                   deployed_target_identity, docker_readback_sha256,
                   patchmon_readback_sha256, cag_execution_receipt_sha256,
                   provider_request_id_sha256, provider_response_sha256,
                   authorization_basis_class, authorization_basis_ref,
                   authorization_basis_sha256, authorization_source_readback_state,
                   usage_scope, entitlement_receipt_sha256,
                   runtime_evidence_readback_verified, public_projection_allowed
               ) VALUES (
                   %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                   %s,%s,%s,%s,%s
               )
               ON CONFLICT (analysis_id) DO NOTHING""",
            (
                binding["bindingId"],
                SCHEMA_VERSION,
                binding["bindingSha256"],
                binding["analysisId"],
                binding["analysisRecordSha256"],
                binding["repositoryRevision"],
                binding["runtimeRevision"],
                binding["immutableImageDigest"],
                binding["runtimeContainerIdentitySha256"],
                binding["deployedTargetIdentity"],
                binding["dockerReadbackSha256"],
                binding["patchmonReadbackSha256"],
                binding["cagExecutionReceiptSha256"],
                binding["providerRequestIdSha256"],
                binding["providerResponseSha256"],
                AUTHORIZATION_BASIS_CLASS,
                AUTHORIZATION_BASIS_REF,
                AUTHORIZATION_BASIS_SHA256,
                AUTHORIZATION_SOURCE_READBACK_STATE,
                USAGE_SCOPE,
                binding["entitlementReceiptSha256"],
                bool(binding["runtimeEvidenceReadbackVerified"]),
                bool(binding["publicProjectionAllowed"]),
            ),
        )
        inserted = cursor.rowcount == 1
        cursor.execute(
            """SELECT binding_id, schema_version, binding_sha256, analysis_id,
                      analysis_record_sha256, repository_revision, runtime_revision,
                      immutable_image_digest, runtime_container_identity_sha256,
                      deployed_target_identity, docker_readback_sha256,
                      patchmon_readback_sha256, cag_execution_receipt_sha256,
                      provider_request_id_sha256, provider_response_sha256,
                      authorization_basis_class, authorization_basis_ref,
                      authorization_basis_sha256, authorization_source_readback_state,
                      usage_scope, entitlement_receipt_sha256,
                      runtime_evidence_readback_verified, public_projection_allowed
               FROM wolfram_cag_runtime_evidence_bindings
               WHERE analysis_id=%s
               LIMIT 1""",
            (binding["analysisId"],),
        )
        names = [item.name for item in cursor.description]
        row = cursor.fetchone()
        if not row:
            raise RuntimeBindingError("runtime evidence binding readback is missing")
        observed_binding = _row_projection(dict(zip(names, row)))
        expected_binding = {key: binding[key] for key in observed_binding}
        if observed_binding != expected_binding:
            raise RuntimeBindingError("runtime evidence binding readback mismatch")
        connection.commit()
        return {
            "bindingId": binding["bindingId"],
            "bindingSha256": binding["bindingSha256"],
            "inserted": inserted,
            "readbackVerified": True,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


__all__ = [
    "AUTHORIZATION_BASIS_CLASS",
    "AUTHORIZATION_BASIS_EVIDENCE",
    "AUTHORIZATION_BASIS_REF",
    "AUTHORIZATION_BASIS_SHA256",
    "AUTHORIZATION_SOURCE_READBACK_STATE",
    "PUBLIC_OUTPUT_BOUNDARY",
    "SCHEMA_VERSION",
    "USAGE_SCOPE",
    "RuntimeBindingError",
    "build_runtime_evidence_binding",
    "persist_runtime_evidence_binding",
    "sha256_json",
]
