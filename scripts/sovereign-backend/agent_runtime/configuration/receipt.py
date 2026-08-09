"""Configuration Provenance - receipts.

Mirrors ``src/runtime/config/configReceipt.ts``. A public receipt is a redacted,
serializable projection of a resolved configuration. The same resolved
configuration always produces the same ``receipt_hash`` (byte-identical).
Receipts never contain secrets - only redacted identities and hash/digest
readback values. PatchMon reads back revision, image digest, schema hash and
the redacted config hash from the same receipt.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from .config_canonicalize import canonical_json, hash_value
from .config_sources import ConfigDriftRecord, ConfigResolutionContract, SourceHashRecord


DETERMINISTIC_EPOCH = "1970-01-01T00:00:00Z"


@dataclass(frozen=True)
class ConfigReceipt:
    receipt_hash: str
    status: str
    source_order: tuple[str, ...]
    source_hashes: tuple[dict[str, Any], ...]
    schema_hash: str
    resolved_hash: str
    resolved: dict[str, Any]
    drift: Optional[dict[str, Any]]
    errors: tuple[str, ...]
    revision: Optional[str]
    image_digest: Optional[str]
    materialized_at: str


@dataclass(frozen=True)
class ReceiptOptions:
    revision: Optional[str] = None
    image_digest: Optional[str] = None
    materialized_at: Optional[str] = None


def _source_hash_to_dict(record: SourceHashRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "kind": record.kind,
        "revision": record.revision,
        "contentHash": record.content_hash,
        "schemaHash": record.schema_hash,
        "priority": record.priority,
        "remoteOrigin": record.remote_origin,
        "remoteDigest": record.remote_digest,
    }


def _drift_to_dict(drift: Optional[ConfigDriftRecord]) -> Optional[dict[str, Any]]:
    if drift is None:
        return None
    return {
        "kind": drift.kind,
        "detail": drift.detail,
        "expectedHash": drift.expected_hash,
        "actualHash": drift.actual_hash,
    }


def _receipt_body(
    contract: ConfigResolutionContract,
    options: ReceiptOptions,
) -> dict[str, Any]:
    return {
        "status": contract.status,
        "sourceOrder": tuple(contract.source_order),
        "sourceHashes": tuple(
            _source_hash_to_dict(s) for s in contract.source_hashes
        ),
        "schemaHash": contract.schema_hash,
        "resolvedHash": contract.resolved_hash,
        "resolved": contract.resolved,
        "drift": _drift_to_dict(contract.drift),
        "errors": contract.errors,
        "revision": options.revision,
        "imageDigest": options.image_digest,
        "materializedAt": options.materialized_at or DETERMINISTIC_EPOCH,
    }


def compute_receipt_hash(body: dict[str, Any]) -> str:
    return hash_value(json.loads(canonical_json(body)))


def materialize_receipt(
    contract: ConfigResolutionContract,
    options: Any = None,
) -> ConfigReceipt:
    if options is None:
        options = ReceiptOptions()
    if isinstance(options, ReceiptOptions):
        opts = options
    elif isinstance(options, dict):
        opts = ReceiptOptions(
            revision=options.get("revision"),
            image_digest=options.get("image_digest"),
            materialized_at=options.get("materialized_at"),
        )
    else:
        opts = ReceiptOptions()
    body = _receipt_body(contract, opts)
    receipt_hash = compute_receipt_hash(body)
    return ConfigReceipt(
        receipt_hash=receipt_hash,
        status=body["status"],
        source_order=body["sourceOrder"],
        source_hashes=body["sourceHashes"],
        schema_hash=body["schemaHash"],
        resolved_hash=body["resolvedHash"],
        resolved=body["resolved"],
        drift=body["drift"],
        errors=body["errors"],
        revision=body["revision"],
        image_digest=body["imageDigest"],
        materialized_at=body["materializedAt"],
    )


def verify_receipt(receipt: ConfigReceipt) -> bool:
    body = {
        "status": receipt.status,
        "sourceOrder": receipt.source_order,
        "sourceHashes": receipt.source_hashes,
        "schemaHash": receipt.schema_hash,
        "resolvedHash": receipt.resolved_hash,
        "resolved": receipt.resolved,
        "drift": receipt.drift,
        "errors": receipt.errors,
        "revision": receipt.revision,
        "imageDigest": receipt.image_digest,
        "materializedAt": receipt.materialized_at,
    }
    return compute_receipt_hash(body) == receipt.receipt_hash


# ---------------------------------------------------------------------------
# PatchMon readback (#1169)
#
# PatchMon independently reads back the configuration identity the running
# container actually loaded. A container is considered configured only when
# PatchMon's readback matches the resolved receipt exactly. Any mismatch, or a
# receipt that was never RESOLVED/bound, yields BLOCKED or CONTRADICTED - never
# a green state on a stale or unbound projection.
# ---------------------------------------------------------------------------

READBACK_VERIFIED: str = "VERIFIED"
READBACK_CONTRADICTED: str = "CONTRADICTED"
READBACK_BLOCKED: str = "BLOCKED"


@dataclass(frozen=True)
class PatchMonReadback:
    """Independent PatchMon observation of the loaded configuration identity.

    Every field is a redacted, hash/digest value - never raw config or secrets.
    """

    revision: Optional[str]
    image_digest: Optional[str]
    schema_hash: Optional[str]
    config_hash: Optional[str]


@dataclass(frozen=True)
class ReadbackResult:
    verdict: str
    matched_fields: tuple[str, ...]
    mismatched_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    detail: str


_READBACK_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("revision", "revision", "revision"),
    ("image_digest", "image_digest", "imageDigest"),
    ("schema_hash", "schema_hash", "schemaHash"),
    ("config_hash", "resolved_hash", "resolvedHash (config)"),
)


def compare_patchmon_readback(
    receipt: ConfigReceipt,
    observed: PatchMonReadback,
) -> ReadbackResult:
    """Compare a bound receipt against an independent PatchMon readback.

    Returns a ReadbackResult whose verdict is:
      - VERIFIED      only when the receipt is RESOLVED and every bound field
                      PatchMon must confirm matches exactly;
      - CONTRADICTED  when a field PatchMon observed does not match the bound
                      receipt (loaded projection diverges from resolved);
      - BLOCKED       when the receipt was not RESOLVED, or a required field
                      is missing on either side (unknown truth, not green).

    PatchMon readback never promotes a non-RESOLVED or tampered receipt to
    VERIFIED.
    """
    matched: list[str] = []
    mismatched: list[str] = []
    missing: list[str] = []

    if receipt.status != "RESOLVED":
        return ReadbackResult(
            verdict=READBACK_BLOCKED,
            matched_fields=(),
            mismatched_fields=(),
            missing_fields=(),
            detail=f"receipt not RESOLVED (status={receipt.status})",
        )

    for obs_attr, receipt_attr, label in _READBACK_FIELDS:
        bound = getattr(receipt, receipt_attr)
        seen = getattr(observed, obs_attr)
        if not bound or not seen:
            missing.append(label)
            continue
        if bound == seen:
            matched.append(label)
        else:
            mismatched.append(label)

    if mismatched:
        return ReadbackResult(
            verdict=READBACK_CONTRADICTED,
            matched_fields=tuple(matched),
            mismatched_fields=tuple(mismatched),
            missing_fields=tuple(missing),
            detail=f"PatchMon readback contradicts receipt: {', '.join(mismatched)}",
        )
    if missing:
        return ReadbackResult(
            verdict=READBACK_BLOCKED,
            matched_fields=tuple(matched),
            mismatched_fields=(),
            missing_fields=tuple(missing),
            detail=f"PatchMon readback incomplete: {', '.join(missing)}",
        )
    return ReadbackResult(
        verdict=READBACK_VERIFIED,
        matched_fields=tuple(matched),
        mismatched_fields=(),
        missing_fields=(),
        detail="PatchMon readback matches resolved receipt",
    )


# ---------------------------------------------------------------------------
# RunEnvelope config binding (#1116 / #1169)
#
# Binds a redacted config fingerprint to a run envelope hash so the run carries
# a deterministic, tamper-evident reference to the exact configuration
# projection it started under. The binding is read-only provenance: it never
# mutates config and never carries raw secret material (only hashes).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigRunBinding:
    """A run envelope <-> resolved config binding.

    ``binding_hash`` is sha256 of the canonical binding body (excluding the
    hash itself), so identical (runEnvelopeHash, receiptHash) pairs always
    produce identical bindings.
    """

    run_envelope_hash: str
    config_receipt_hash: str
    config_fingerprint: str
    schema_hash: str
    revision: Optional[str]
    image_digest: Optional[str]
    binding_hash: str


def bind_config_to_run(
    run_envelope_hash: str,
    receipt: ConfigReceipt,
) -> ConfigRunBinding:
    """Bind a resolved config receipt to a run envelope hash (#1116).

    Produces a deterministic ``ConfigRunBinding`` whose ``config_fingerprint``
    is the redacted public config hash (the receipt's resolved_hash) and whose
    ``binding_hash`` ties the run envelope to that fingerprint. A non-RESOLVED
    or tampered receipt still produces a binding, but callers MUST gate
    advancement on ``is_safe_to_advance`` (resolver) / receipt.status ==
    RESOLVED before trusting the binding - the fingerprint alone does not prove
    the config was safely resolved.
    """
    if not run_envelope_hash:
        raise ValueError("run_envelope_hash is required")
    if not receipt.receipt_hash:
        raise ValueError("receipt must carry a receipt_hash")
    body = {
        "runEnvelopeHash": run_envelope_hash,
        "configReceiptHash": receipt.receipt_hash,
        "configFingerprint": receipt.resolved_hash,
        "schemaHash": receipt.schema_hash,
        "revision": receipt.revision,
        "imageDigest": receipt.image_digest,
    }
    binding_hash = hash_value(json.loads(canonical_json(body)))
    return ConfigRunBinding(
        run_envelope_hash=run_envelope_hash,
        config_receipt_hash=receipt.receipt_hash,
        config_fingerprint=receipt.resolved_hash,
        schema_hash=receipt.schema_hash,
        revision=receipt.revision,
        image_digest=receipt.image_digest,
        binding_hash=binding_hash,
    )


__all__ = [
    "ConfigReceipt",
    "ReceiptOptions",
    "materialize_receipt",
    "compute_receipt_hash",
    "verify_receipt",
    "DETERMINISTIC_EPOCH",
    "PatchMonReadback",
    "ReadbackResult",
    "READBACK_VERIFIED",
    "READBACK_CONTRADICTED",
    "READBACK_BLOCKED",
    "compare_patchmon_readback",
    "ConfigRunBinding",
    "bind_config_to_run",
]
