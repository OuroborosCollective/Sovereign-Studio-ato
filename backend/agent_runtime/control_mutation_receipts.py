"""Pure, deterministic ControlMutationReceipt contracts for ACSA.

This module defines the ControlMutationReceipt dataclass for recording
mutation test results. It performs no network, database, filesystem, clock or random access.
All hashes are deterministic and secret-safe.

Reference: Issue #1638 (ACSA 1/4)
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Final, Literal

from .proof_verdict import canonical_proof_sha256


_SCHEMA_VERSION: Final[str] = "sovereign.control-mutation-receipt.v1"
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA64_RE = re.compile(r"^[0-9a-f]{64}$")
_OCI_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ControlMutationReceiptError(ValueError):
    """A control mutation receipt violated a deterministic or invariant."""


# Allowed verdict values
_ALLOWED_VERDICTS = frozenset({
    "MUTANT_KILLED",
    "MUTANT_SURVIVED",
    "UNVERIFIED",
    "CONTRADICTED",
})


def _validate_sha40(value: str, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _SHA40_RE.fullmatch(normalized):
        raise ControlMutationReceiptError(f"{label} must be a lowercase full Git SHA (40 hex)")
    return normalized


def _validate_sha64(value: str, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _SHA64_RE.fullmatch(normalized):
        raise ControlMutationReceiptError(f"{label} must be a SHA-256 (64 hex)")
    return normalized


def _validate_oci_digest(value: str, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _OCI_DIGEST_RE.fullmatch(normalized):
        raise ControlMutationReceiptError(f"{label} must be a valid OCI digest (sha256:<64hex>)")
    return normalized


def _validate_verdict(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in _ALLOWED_VERDICTS:
        raise ControlMutationReceiptError(f"verdict must be one of: {', '.join(sorted(_ALLOWED_VERDICTS))}")
    return normalized


def _validate_optional_sha64(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    return _validate_sha64(value, label)


@dataclass(frozen=True, slots=True)
class ControlMutationReceipt:
    """Immutable receipt for a control mutation test.

    Records the outcome of running a ControlMutationCase against the
    protected execution path. The receipt_hash deterministically binds all fields.
    """

    schema_version: str
    case_sha256: str
    repository_revision: str
    runtime_revision: str | None
    image_digest: str | None
    execution_receipt_sha256: str | None
    target_readback_sha256: str | None
    observed_block_code: str | None
    verdict: str
    receipt_sha256: str

    def __post_init__(self) -> None:
        # Schema version
        if self.schema_version != _SCHEMA_VERSION:
            raise ControlMutationReceiptError("unsupported control-mutation-receipt schema version")

        # Case SHA256
        object.__setattr__(self, "case_sha256", _validate_sha64(self.case_sha256, "case_sha256"))

        # Repository revision
        object.__setattr__(self, "repository_revision", _validate_sha40(self.repository_revision, "repository_revision"))

        # Runtime revision (optional)
        if self.runtime_revision is not None:
            object.__setattr__(self, "runtime_revision", _validate_sha40(self.runtime_revision, "runtime_revision"))

        # Image digest (optional, must be valid OCI format if provided)
        if self.image_digest is not None:
            object.__setattr__(self, "image_digest", _validate_oci_digest(self.image_digest, "image_digest"))

        # Execution receipt SHA256 (optional)
        if self.execution_receipt_sha256 is not None:
            object.__setattr__(self, "execution_receipt_sha256", _validate_sha64(self.execution_receipt_sha256, "execution_receipt_sha256"))

        # Target readback SHA256 (optional)
        if self.target_readback_sha256 is not None:
            object.__setattr__(self, "target_readback_sha256", _validate_sha64(self.target_readback_sha256, "target_readback_sha256"))

        # Verdict - must be in allowlist
        object.__setattr__(self, "verdict", _validate_verdict(self.verdict))

        # Observed block code (optional)
        if self.observed_block_code is not None:
            object.__setattr__(self, "observed_block_code", str(self.observed_block_code).strip())

        # Validate verdict-specific constraints
        self._validate_verdict_constraints()

        # Receipt hash - compute from canonical body (without the hash field)
        expected_hash = canonical_proof_sha256(self._canonical_body(include_hash=False))
        if not self.receipt_sha256:
            object.__setattr__(self, "receipt_sha256", expected_hash)
        elif self.receipt_sha256 != expected_hash:
            raise ControlMutationReceiptError(f"receipt_sha256 mismatch: expected {expected_hash}")

    def _validate_verdict_constraints(self) -> None:
        """Validate verdict-specific constraints."""
        # MUTANT_SURVIVED requires evidence (either execution receipt or target readback)
        if self.verdict == "MUTANT_SURVIVED":
            if not self.execution_receipt_sha256 and not self.target_readback_sha256:
                raise ControlMutationReceiptError(
                    "MUTANT_SURVIVED requires either execution_receipt_sha256 or target_readback_sha256"
                )

    def _canonical_body(self, include_hash: bool = True) -> dict:
        body = {
            "schema_version": self.schema_version,
            "case_sha256": self.case_sha256,
            "repository_revision": self.repository_revision,
            "runtime_revision": self.runtime_revision,
            "image_digest": self.image_digest,
            "execution_receipt_sha256": self.execution_receipt_sha256,
            "target_readback_sha256": self.target_readback_sha256,
            "observed_block_code": self.observed_block_code,
            "verdict": self.verdict,
        }
        if include_hash:
            body["receipt_sha256"] = self.receipt_sha256
        return body

    def canonical_body(self) -> dict:
        """Return deterministic canonical body for hashing."""
        return self._canonical_body(include_hash=False)

    @classmethod
    def from_dict(cls, data: dict) -> "ControlMutationReceipt":
        """Parse from dictionary, computing receipt_sha256."""
        return cls(
            schema_version=data.get("schema_version", _SCHEMA_VERSION),
            case_sha256=data["case_sha256"],
            repository_revision=data["repository_revision"],
            runtime_revision=data.get("runtime_revision"),
            image_digest=data.get("image_digest"),
            execution_receipt_sha256=data.get("execution_receipt_sha256"),
            target_readback_sha256=data.get("target_readback_sha256"),
            observed_block_code=data.get("observed_block_code"),
            verdict=data["verdict"],
            receipt_sha256=data.get("receipt_sha256", ""),
        )

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return self._canonical_body(include_hash=True)


def build_control_mutation_receipt(
    case_sha256: str,
    repository_revision: str,
    verdict: str,
    runtime_revision: str | None = None,
    image_digest: str | None = None,
    execution_receipt_sha256: str | None = None,
    target_readback_sha256: str | None = None,
    observed_block_code: str | None = None,
) -> ControlMutationReceipt:
    """Build a ControlMutationReceipt, computing the receipt_sha256 automatically."""
    receipt = ControlMutationReceipt(
        schema_version=_SCHEMA_VERSION,
        case_sha256=case_sha256,
        repository_revision=repository_revision,
        runtime_revision=runtime_revision,
        image_digest=image_digest,
        execution_receipt_sha256=execution_receipt_sha256,
        target_readback_sha256=target_readback_sha256,
        observed_block_code=observed_block_code,
        verdict=verdict,
        receipt_sha256="",  # Will be computed
    )
    return receipt


def verify_receipt_for_case(
    receipt: ControlMutationReceipt,
    expected_case_sha256: str,
    requires_target_readback: bool = False,
) -> tuple[bool, str]:
    """Verify a receipt is valid for a given case.

    Returns (is_valid, error_message).
    """
    # Verify case SHA256 matches
    if receipt.case_sha256 != expected_case_sha256:
        return False, f"receipt case_sha256 {receipt.case_sha256[:16]}... does not match expected {expected_case_sha256[:16]}..."

    # Verify MUTANT_KILLED has target_readback_sha256 when required
    if receipt.verdict == "MUTANT_KILLED" and requires_target_readback:
        if not receipt.target_readback_sha256:
            return False, "MUTANT_KILLED verdict requires target_readback_sha256 when case.requires_target_readback is True"

    # Verify MUTANT_SURVIVED has evidence
    if receipt.verdict == "MUTANT_SURVIVED":
        if not receipt.execution_receipt_sha256 and not receipt.target_readback_sha256:
            return False, "MUTANT_SURVIVED requires evidence of effect"

    return True, ""
