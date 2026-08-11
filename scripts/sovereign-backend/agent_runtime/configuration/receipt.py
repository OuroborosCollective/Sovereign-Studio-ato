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


@dataclass(frozen=True)
class ConfigReadbackObservation:
    """Independent PatchMon readback of the actually-loaded config projection.

    PatchMon observes the running container and reports the identity fields
    it read back. These are compared against the materialized
    :class:`ConfigReceipt` that RunEnvelope carries. Every bound (non-empty)
    field must match exactly. This is the readback side of the #1169
    acceptance contract: RunEnvelope and PatchMon must read back the same
    redacted config fingerprint; deviation blocks.
    """

    revision: Optional[str]
    image_digest: Optional[str]
    schema_hash: Optional[str]
    resolved_hash: Optional[str]
    receipt_hash: Optional[str]


@dataclass(frozen=True)
class ConfigReadbackAudit:
    """Fail-closed audit of a config readback against a bound receipt.

    ``accepted`` is ``True`` only when the receipt self-verifies and every
    bound readback field matches the receipt exactly. Otherwise ``blocker``
    names the precise finding code so the runtime can route to ``BLOCKED``
    /``CONTRADICTED`` rather than advancing.
    """

    accepted: bool
    blocker: Optional[str] = None

    @property
    def contradicted(self) -> bool:
        """A contradiction is a harder failure than missing evidence."""
        return self.blocker == "config_readback_contradicts_receipt"


def verify_config_readback(
    receipt: ConfigReceipt,
    observation: ConfigReadbackObservation,
) -> ConfigReadbackAudit:
    """Confirm a PatchMon readback matches a bound config receipt.

    Fails closed: the receipt must self-verify (no tampering), then every
    bound field on the observation must equal the receipt's bound field.
    A mismatch on a populated field is a *contradiction* (the wrong config
    is loaded); a missing field (empty on the observation while the receipt
    binds it) is a *blocker* (readback incomplete). Either blocks RUNTIME
    advancement per the #1169 DoD.
    """
    if not verify_receipt(receipt):
        return ConfigReadbackAudit(False, "config_receipt_self_verification_failed")
    if receipt.status != "RESOLVED":
        return ConfigReadbackAudit(False, "config_receipt_not_resolved")
    if receipt.drift is not None or receipt.errors:
        return ConfigReadbackAudit(False, "config_receipt_not_advanceable")

    pairs = (
        ("revision", receipt.revision, observation.revision),
        ("imageDigest", receipt.image_digest, observation.image_digest),
        ("schemaHash", receipt.schema_hash, observation.schema_hash),
        ("resolvedHash", receipt.resolved_hash, observation.resolved_hash),
    )

    for _field, expected, actual in pairs:
        expected_norm = str(expected or "").strip().lower()
        actual_norm = str(actual or "").strip().lower()
        if not expected_norm:
            continue  # receipt does not bind this field; nothing to confirm
        if not actual_norm:
            return ConfigReadbackAudit(False, "config_readback_missing_bound_field")
        if actual_norm != expected_norm:
            return ConfigReadbackAudit(False, "config_readback_contradicts_receipt")

    # The receipt hash itself is the redacted config fingerprint both sides
    # must agree on. When PatchMon reports it, it must match byte-for-byte;
    # when PatchMon omits it, readback is incomplete rather than contradictory.
    reported_hash = str(observation.receipt_hash or "").strip().lower()
    if reported_hash:
        if reported_hash != str(receipt.receipt_hash or "").strip().lower():
            return ConfigReadbackAudit(False, "config_readback_contradicts_receipt")
    else:
        return ConfigReadbackAudit(False, "config_readback_missing_bound_field")

    return ConfigReadbackAudit(True, None)


__all__ = [
    "ConfigReceipt",
    "ReceiptOptions",
    "materialize_receipt",
    "compute_receipt_hash",
    "verify_receipt",
    "DETERMINISTIC_EPOCH",
    "ConfigReadbackObservation",
    "ConfigReadbackAudit",
    "verify_config_readback",
]
