"""Configuration Provenance - runtime binding & advance gate.

Mirrors ``src/runtime/config/runtimeBinding.ts``.

This module is the integration seam between the read-only configuration
provenance layer and the runtime's advancement / RunEnvelope contracts:

* ``bind_config_fingerprint`` projects a resolved, redacted receipt into the
  single canonical ``ConfigFingerprintBinding`` that the RunEnvelope (#1116)
  binds and PatchMon reads back. The same resolved configuration always
  produces the same ``fingerprint_hash`` (byte-identical). Receipts that fail
  integrity verification bind as ``UNVERIFIED`` and fail closed.

* ``advance_decision`` is the fail-closed drift gate for new mutations and
  active action plans. Only a ``RESOLVED`` contract with no drift, no errors
  and an integrity-verified receipt may advance. ``CONTRADICTED`` /
  ``BLOCKED`` / ``DEGRADED`` resolutions, or an unverifiable receipt, block
  advancement with an explicit, machine-checkable reason.

Mutation of configuration runs through #1119; this module performs read-only
projection and gating only - it never persists state or calls a target system.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .config_canonicalize import hash_value
from .config_sources import ConfigResolutionContract
from .receipt import ConfigReceipt, materialize_receipt, verify_receipt


_FINGERPRINT_VERSION = "sovereign.config.fingerprint.v1"


@dataclass(frozen=True)
class ConfigFingerprintBinding:
    """Redacted config fingerprint bound into the RunEnvelope and read by PatchMon.

    Contains no raw secret material. ``fingerprint_hash`` is the byte-identical
    public hash for the same resolved configuration + binding options.
    """

    fingerprint_hash: str
    version: str
    status: str
    verified: bool
    receipt_hash: str
    schema_hash: str
    resolved_hash: str
    revision: Optional[str]
    image_digest: Optional[str]
    drift_kind: Optional[str]


@dataclass(frozen=True)
class AdvanceDecision:
    """Fail-closed advancement verdict for mutations and active action plans."""

    safe: bool
    reason: str
    status: str
    drift_kind: Optional[str]


def _binding_body(receipt: ConfigReceipt) -> dict[str, Any]:
    return {
        "version": _FINGERPRINT_VERSION,
        "status": receipt.status,
        "verified": verify_receipt(receipt),
        "receiptHash": receipt.receipt_hash,
        "schemaHash": receipt.schema_hash,
        "resolvedHash": receipt.resolved_hash,
        "revision": receipt.revision,
        "imageDigest": receipt.image_digest,
        "driftKind": (receipt.drift or {}).get("kind") if receipt.drift else None,
    }


def bind_config_fingerprint(receipt: ConfigReceipt) -> ConfigFingerprintBinding:
    """Project a redacted receipt into the RunEnvelope / PatchMon fingerprint.

    Fail-closed: a receipt that fails integrity verification is bound as
    ``UNVERIFIED`` (its ``fingerprint_hash`` still reflects the tampered body,
    so tampering is detectable, but ``verified`` is False).
    """
    body = _binding_body(receipt)
    fingerprint_hash = hash_value(body)
    return ConfigFingerprintBinding(
        fingerprint_hash=fingerprint_hash,
        version=body["version"],
        status=body["status"],
        verified=body["verified"],
        receipt_hash=body["receiptHash"],
        schema_hash=body["schemaHash"],
        resolved_hash=body["resolvedHash"],
        revision=body["revision"],
        image_digest=body["imageDigest"],
        drift_kind=body["driftKind"],
    )


def advance_decision(
    contract: ConfigResolutionContract,
    receipt: Optional[ConfigReceipt] = None,
) -> AdvanceDecision:
    """Fail-closed drift gate for new mutations and active action plans.

    Returns ``safe=True`` only when the contract is ``RESOLVED`` with no drift
    and no errors, AND the supplied receipt (if any) passes integrity
    verification and matches the contract. Any drift, error, status downgrade
    or receipt mismatch blocks advancement with an explicit reason.
    """
    drift_kind = contract.drift.kind if contract.drift else None

    if contract.status == "CONTRADICTED":
        return AdvanceDecision(
            safe=False,
            reason=f"CONFIG_CONTRADICTED:{drift_kind or 'content-drift'}",
            status=contract.status,
            drift_kind=drift_kind,
        )
    if contract.status == "BLOCKED":
        return AdvanceDecision(
            safe=False,
            reason=f"CONFIG_BLOCKED:{drift_kind or 'resolution-error'}",
            status=contract.status,
            drift_kind=drift_kind,
        )
    if contract.status == "DEGRADED":
        return AdvanceDecision(
            safe=False,
            reason=f"CONFIG_DEGRADED:{drift_kind or 'degraded'}",
            status=contract.status,
            drift_kind=drift_kind,
        )
    if contract.errors:
        return AdvanceDecision(
            safe=False,
            reason=f"CONFIG_ERRORS:{len(contract.errors)}",
            status=contract.status,
            drift_kind=drift_kind,
        )
    if contract.drift is not None:
        return AdvanceDecision(
            safe=False,
            reason=f"CONFIG_DRIFT:{drift_kind or 'unknown'}",
            status=contract.status,
            drift_kind=drift_kind,
        )
    if contract.status != "RESOLVED":
        return AdvanceDecision(
            safe=False,
            reason=f"CONFIG_NOT_RESOLVED:{contract.status}",
            status=contract.status,
            drift_kind=drift_kind,
        )

    if receipt is not None:
        if not verify_receipt(receipt):
            return AdvanceDecision(
                safe=False,
                reason="RECEIPT_UNVERIFIED",
                status=contract.status,
                drift_kind=drift_kind,
            )
        if receipt.status != "RESOLVED":
            return AdvanceDecision(
                safe=False,
                reason=f"RECEIPT_STATUS:{receipt.status}",
                status=contract.status,
                drift_kind=drift_kind,
            )
        # A stale receipt materialized from a different contract must not
        # authorize advancement of this contract's mutations/action plans.
        if receipt.resolved_hash != contract.resolved_hash:
            return AdvanceDecision(
                safe=False,
                reason="RECEIPT_MISMATCH",
                status=contract.status,
                drift_kind=drift_kind,
            )

    return AdvanceDecision(
        safe=True,
        reason="RESOLVED",
        status=contract.status,
        drift_kind=None,
    )


def materialize_and_bind(
    contract: ConfigResolutionContract,
    options: Any = None,
) -> tuple[ConfigReceipt, ConfigFingerprintBinding]:
    """Convenience: materialize a redacted receipt and bind its fingerprint."""
    receipt = materialize_receipt(contract, options)
    binding = bind_config_fingerprint(receipt)
    return receipt, binding


__all__ = [
    "ConfigFingerprintBinding",
    "AdvanceDecision",
    "bind_config_fingerprint",
    "advance_decision",
    "materialize_and_bind",
]
