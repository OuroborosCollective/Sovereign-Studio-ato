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


__all__ = [
    "ConfigReceipt",
    "ReceiptOptions",
    "materialize_receipt",
    "compute_receipt_hash",
    "verify_receipt",
    "DETERMINISTIC_EPOCH",
]
