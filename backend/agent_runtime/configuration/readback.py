"""Configuration Provenance - PatchMon readback verification.

Mirrors ``src/runtime/config/configReadback.ts``. PatchMon independently reads
back the config projection that a running container actually loaded (bound
revision, image digest, schema hash and redacted resolved hash). This module
compares that independent observation against a materialized
:class:`ConfigReceipt` and returns a deterministic readback verdict. Mismatch
routes the next action to BLOCKED / CONTRADICTED so prior run/permission
bindings are invalidated rather than silently continuing - the runtime half of
acceptance criterion #6 for #1169.

This is read-only verification. It never mutates configuration (mutation flows
through #1119) and it never touches secret material: it only compares the
redacted hash/digest readback values that PatchMon observes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional

from .receipt import ConfigReceipt


ReadbackVerdict = Literal["MATCHED", "MISMATCHED", "UNVERIFIABLE"]
ReadbackField = Literal["revision", "imageDigest", "schemaHash", "resolvedHash"]
ReadbackFieldState = Literal["matched", "mismatched", "unbound", "unobserved"]


@dataclass(frozen=True)
class PatchMonReadback:
    """The independent PatchMon observation of what the container loaded.

    Every field is a redacted hash/digest identity - never a secret. ``None``
    means PatchMon did not observe that field.
    """

    revision: Optional[str] = None
    image_digest: Optional[str] = None
    schema_hash: Optional[str] = None
    resolved_hash: Optional[str] = None


@dataclass(frozen=True)
class ConfigReadbackResult:
    verdict: ReadbackVerdict
    matched: bool
    fields: Dict[str, ReadbackFieldState] = field(default_factory=dict)
    reason: str = ""


def verify_config_readback(
    receipt: ConfigReceipt, readback: PatchMonReadback
) -> ConfigReadbackResult:
    """Compare a materialized receipt against an independent PatchMon observation.

    A field is "bound" when the receipt carries a value for it (revision and
    schema_hash are always present; image_digest may be None when no image is
    bound). A bound field that PatchMon did not observe (``None`` in the
    readback) yields UNVERIFIABLE, because PatchMon cannot confirm something it
    did not read. A bound field whose observed value differs from the receipt
    yields MISMATCHED. All bound fields matching yields MATCHED.

    Unbound optional fields (image_digest absent on the receipt) are skipped:
    PatchMon is not required to read back a digest that was never bound.
    """
    if receipt.status != "RESOLVED":
        return _unverified("receipt is not RESOLVED", receipt)

    fields: Dict[str, ReadbackFieldState] = {
        "revision": _compare_bound(receipt.revision, readback.revision),
        "imageDigest": _compare_optional_bound(
            receipt.image_digest, readback.image_digest
        ),
        "schemaHash": _compare_bound(receipt.schema_hash, readback.schema_hash),
        "resolvedHash": _compare_bound(
            receipt.resolved_hash, readback.resolved_hash
        ),
    }

    mismatched = [f for f, s in fields.items() if s == "mismatched"]
    unobserved = [f for f, s in fields.items() if s == "unobserved"]

    if mismatched:
        reason = "PatchMon readback mismatch: " + ", ".join(mismatched)
        return ConfigReadbackResult("MISMATCHED", False, fields, reason)
    if unobserved:
        reason = "PatchMon readback unverified: " + ", ".join(unobserved) + " not observed"
        return ConfigReadbackResult("UNVERIFIABLE", False, fields, reason)
    return ConfigReadbackResult("MATCHED", True, fields, "")


def _compare_bound(
    receipt_value: Optional[str], observed: Optional[str]
) -> ReadbackFieldState:
    if receipt_value is None or receipt_value == "":
        return "unbound"
    if observed is None:
        return "unobserved"
    return "matched" if observed == receipt_value else "mismatched"


def _compare_optional_bound(
    receipt_value: Optional[str], observed: Optional[str]
) -> ReadbackFieldState:
    if receipt_value is None or receipt_value == "":
        return "unbound"
    if observed is None:
        return "unobserved"
    return "matched" if observed == receipt_value else "mismatched"


def _unverified(reason: str, receipt: ConfigReceipt) -> ConfigReadbackResult:
    fields: Dict[str, ReadbackFieldState] = {
        "revision": "unobserved" if receipt.revision else "unbound",
        "imageDigest": "unobserved" if receipt.image_digest else "unbound",
        "schemaHash": "unobserved" if receipt.schema_hash else "unbound",
        "resolvedHash": "unobserved" if receipt.resolved_hash else "unbound",
    }
    return ConfigReadbackResult("UNVERIFIABLE", False, fields, reason)


def is_config_readback_confirmed(result: ConfigReadbackResult) -> bool:
    """A container is considered configured only when PatchMon's independent
    readback matches the resolved receipt. Convenience wrapper for the runtime gate.
    """
    return result.verdict == "MATCHED" and result.matched


__all__ = [
    "ReadbackVerdict",
    "ReadbackField",
    "ReadbackFieldState",
    "PatchMonReadback",
    "ConfigReadbackResult",
    "verify_config_readback",
    "is_config_readback_confirmed",
]
