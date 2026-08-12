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
from .receipt import (
    ConfigReceipt,
    ConfigReadbackObservation,
    materialize_receipt,
    verify_receipt,
    verify_config_readback,
)


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


def bind_config_fingerprint(
    receipt: ConfigReceipt,
    options: Any = None,
) -> ConfigFingerprintBinding:
    """Project only an advanceable receipt into the RunEnvelope fingerprint.

    Fail-closed at the binding boundary: an unverified, non-RESOLVED, drifted,
    or error-bearing receipt cannot become a run binding at all. Callers that
    need diagnostics can inspect the receipt or ``advance_decision`` result;
    they cannot accidentally attach unsafe configuration provenance to a run.

    When a PatchMon ``readback`` observation is supplied (via
    ``options["readback"]``), the bound receipt must additionally pass
    ``verify_config_readback``: RunEnvelope and PatchMon must read back the
    same redacted config fingerprint (#1169 DoD). A rejected readback fails
    closed with the readback finding code rather than producing a binding.
    """
    if not verify_receipt(receipt):
        raise ValueError("config receipt failed integrity verification")
    if receipt.status != "RESOLVED":
        raise ValueError(f"config receipt is not RESOLVED: {receipt.status}")
    if receipt.drift is not None or receipt.errors:
        raise ValueError("config receipt is not advanceable")
    readback = (options or {}).get("readback") if isinstance(options, dict) else None
    if readback is not None:
        audit = verify_config_readback(receipt, readback)
        if not audit.accepted:
            raise ValueError(f"config readback rejected: {audit.blocker}")
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
    options: Any = None,
) -> AdvanceDecision:
    """Fail-closed drift gate for new mutations and active action plans.

    Returns ``safe=True`` only when the contract is ``RESOLVED`` with no drift
    and no errors, AND the supplied receipt (if any) passes integrity
    verification and matches the contract. Any drift, error, status downgrade
    or receipt mismatch blocks advancement with an explicit reason.

    When a PatchMon ``readback`` observation is supplied (via
    ``options["readback"]``), the supplied receipt must additionally pass
    ``verify_config_readback`` before advancement is authorized (#1169 DoD).
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

    readback = (options or {}).get("readback") if isinstance(options, dict) else None
    if readback is not None:
        advanceable_receipt = receipt if receipt is not None else None
        if advanceable_receipt is None:
            return AdvanceDecision(
                safe=False,
                reason="READBACK_NO_RECEIPT",
                status=contract.status,
                drift_kind=drift_kind,
            )
        audit = verify_config_readback(advanceable_receipt, readback)
        if not audit.accepted:
            return AdvanceDecision(
                safe=False,
                reason=audit.blocker or "READBACK_REJECTED",
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
    """Convenience: materialize a redacted receipt and bind its fingerprint.

    When a PatchMon ``readback`` observation is supplied (via
    ``options["readback"]``), the bound receipt must additionally pass
    ``verify_config_readback`` before the fingerprint is bound, enforcing the
    #1169 readback contract at the live binding path.
    """
    readback = None
    if isinstance(options, dict):
        readback = options.get("readback")
    receipt = materialize_receipt(contract, options)
    binding = bind_config_fingerprint(receipt, {"readback": readback} if readback is not None else None)
    return receipt, binding


__all__ = [
    "ConfigFingerprintBinding",
    "AdvanceDecision",
    "bind_config_fingerprint",
    "advance_decision",
    "materialize_and_bind",
]
