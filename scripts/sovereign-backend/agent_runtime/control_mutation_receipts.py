"""Pure, deterministic ControlMutationReceipts for ACSA verdict determination.

This module defines the receipt structure for control mutation test results.
It performs no network, database, filesystem, clock or random access.

The receipt captures:
- Case binding (sha256)
- Runtime state (revision, image digest)
- Execution evidence (receipt sha256, target readback)
- Verdict determination (MUTANT_KILLED, MUTANT_SURVIVED, UNVERIFIED, CONTRADICTED)

Design constraints:
- MUTANT_KILLED requires target_readback_sha256 when case.requires_target_readback
- Missing required evidence → UNVERIFIED
- Revision/digest/case binding mismatch → CONTRADICTED
- Secret-shaped fields are never stored in receipts
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Final, Literal, Optional

# Schema version
SCHEMA_VERSION: Final[str] = "sovereign.control-mutation-receipt.v1"

# Validation patterns
_SHA40: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_SHA64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_IMAGE_DIGEST: Final[re.Pattern[str]] = re.compile(r"^sha256:[0-9a-f]{64}$")

# Allowed verdict values
_ALLOWED_VERDICTS: Final[frozenset[str]] = frozenset({
    "MUTANT_KILLED",
    "MUTANT_SURVIVED",
    "UNVERIFIED",
    "CONTRADICTED",
})

# Secret-shaped key markers
_SECRET_KEY_MARKERS: Final[tuple[str, ...]] = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "private_key",
    "client_secret",
    "cookie",
    "raw_prompt",
    "prompt_text",
    "file_content",
    "database_row",
    "credential",
    "auth",
)


class ControlMutationReceiptError(ValueError):
    """A receipt input violated a deterministic or invariant."""

    pass


def _normalize_sha40(value: Optional[str], *, label: str) -> Optional[str]:
    """Validate and normalize a full Git SHA (optional)."""
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized and not _SHA40.fullmatch(normalized):
        raise ControlMutationReceiptError(f"{label} must be a lowercase full Git SHA (40 hex)")
    return normalized or None


def _normalize_sha64(value: Optional[str], *, label: str) -> Optional[str]:
    """Validate and normalize a SHA-256 hash (optional)."""
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized and not _SHA64.fullmatch(normalized):
        raise ControlMutationReceiptError(f"{label} must be a lowercase SHA-256 (64 hex)")
    return normalized or None


def _normalize_image_digest(value: Optional[str], *, label: str) -> Optional[str]:
    """Validate and normalize an OCI image digest (optional)."""
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized and not _IMAGE_DIGEST.fullmatch(normalized):
        raise ControlMutationReceiptError(f"{label} must be a lowercase OCI digest (sha256:<64hex>)")
    return normalized or None


def _canonical_sha256(value: Any) -> str:
    """Compute deterministic SHA-256 for canonical JSON."""
    s = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(s.encode()).hexdigest()


def _reject_secret_shaped_field(value: Any, *, path: str = "$") -> None:
    """Reject secret-shaped raw fields from receipts."""
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                key_lower = key.lower()
                if any(marker in key_lower for marker in _SECRET_KEY_MARKERS):
                    raise ControlMutationReceiptError(
                        f"secret-shaped field '{key}' is forbidden at {path}"
                    )
                _reject_secret_shaped_field(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            _reject_secret_shaped_field(item, path=f"{path}[{idx}]")


Verdict = Literal["MUTANT_KILLED", "MUTANT_SURVIVED", "UNVERIFIED", "CONTRADICTED"]


@dataclass(frozen=True, slots=True)
class ControlMutationReceipt:
    """Immutable receipt for a control mutation test result.

    The receipt captures the runtime state when the case was executed and
    the verdict determination. It is bound to a specific case_sha256 and
    repository_revision.
    """

    schema_version: str
    case_sha256: str
    repository_revision: str
    runtime_revision: Optional[str]
    image_digest: Optional[str]
    execution_receipt_sha256: Optional[str]
    target_readback_sha256: Optional[str]
    observed_block_code: Optional[str]
    verdict: Verdict
    receipt_sha256: str

    def __post_init__(self) -> None:
        # Validate schema version
        if self.schema_version != SCHEMA_VERSION:
            raise ControlMutationReceiptError(
                f"unsupported schema version: {self.schema_version!r}"
            )

        # Validate case_sha256
        object.__setattr__(
            self,
            "case_sha256",
            _normalize_sha64(self.case_sha256, label="case_sha256"),
        )

        # Validate repository_revision
        object.__setattr__(
            self,
            "repository_revision",
            _normalize_sha40(self.repository_revision, label="repository_revision"),
        )

        # Validate optional runtime fields
        object.__setattr__(
            self,
            "runtime_revision",
            _normalize_sha40(self.runtime_revision, label="runtime_revision"),
        )
        object.__setattr__(
            self,
            "image_digest",
            _normalize_image_digest(self.image_digest, label="image_digest"),
        )
        object.__setattr__(
            self,
            "execution_receipt_sha256",
            _normalize_sha64(self.execution_receipt_sha256, label="execution_receipt_sha256"),
        )
        object.__setattr__(
            self,
            "target_readback_sha256",
            _normalize_sha64(self.target_readback_sha256, label="target_readback_sha256"),
        )

        # Validate observed_block_code if provided
        if self.observed_block_code is not None:
            code = str(self.observed_block_code).strip().lower()
            if not code:
                raise ControlMutationReceiptError("observed_block_code must not be empty")
            object.__setattr__(self, "observed_block_code", code)

        # Validate verdict
        if self.verdict not in _ALLOWED_VERDICTS:
            raise ControlMutationReceiptError(
                f"invalid verdict: {self.verdict!r}. "
                f"Allowed: {sorted(_ALLOWED_VERDICTS)}"
            )

        # Validate receipt_sha256
        object.__setattr__(
            self,
            "receipt_sha256",
            _normalize_sha64(self.receipt_sha256, label="receipt_sha256"),
        )

        # Verify receipt hash matches computed hash
        computed_hash = self._compute_receipt_sha256()
        if computed_hash != self.receipt_sha256:
            raise ControlMutationReceiptError("receipt_sha256 mismatch")

    def _compute_receipt_sha256(self) -> str:
        """Compute the canonical receipt SHA-256."""
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
        return _canonical_sha256(body)

    def canonical_body(self) -> dict[str, Any]:
        """Return the canonical receipt body for hashing."""
        return {
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


def build_control_mutation_receipt(
    *,
    case_sha256: str,
    repository_revision: str,
    runtime_revision: Optional[str] = None,
    image_digest: Optional[str] = None,
    execution_receipt_sha256: Optional[str] = None,
    target_readback_sha256: Optional[str] = None,
    observed_block_code: Optional[str] = None,
    verdict: Verdict,
) -> ControlMutationReceipt:
    """Build a ControlMutationReceipt with computed hash.

    Args:
        case_sha256: SHA-256 of the case being executed
        repository_revision: Full Git SHA-40 of repository
        runtime_revision: Optional runtime revision
        image_digest: Optional OCI image digest
        execution_receipt_sha256: Optional execution receipt hash
        target_readback_sha256: Optional target readback hash
        observed_block_code: Optional observed block code
        verdict: The verdict (MUTANT_KILLED, MUTANT_SURVIVED, UNVERIFIED, CONTRADICTED)

    Returns:
        Immutable ControlMutationReceipt with computed hash
    """
    # Build receipt body for hash computation
    receipt_body = {
        "schema_version": SCHEMA_VERSION,
        "case_sha256": case_sha256,
        "repository_revision": repository_revision,
        "runtime_revision": runtime_revision,
        "image_digest": image_digest,
        "execution_receipt_sha256": execution_receipt_sha256,
        "target_readback_sha256": target_readback_sha256,
        "observed_block_code": observed_block_code,
        "verdict": verdict,
    }
    computed_receipt_sha256 = _canonical_sha256(receipt_body)

    receipt = ControlMutationReceipt(
        schema_version=SCHEMA_VERSION,
        case_sha256=case_sha256,
        repository_revision=repository_revision,
        runtime_revision=runtime_revision,
        image_digest=image_digest,
        execution_receipt_sha256=execution_receipt_sha256,
        target_readback_sha256=target_readback_sha256,
        observed_block_code=observed_block_code,
        verdict=verdict,
        receipt_sha256=computed_receipt_sha256,
    )

    return receipt


def verify_receipt_for_case(
    receipt: ControlMutationReceipt,
    case: Any,  # ControlMutationCase type
) -> tuple[bool, Optional[str]]:
    """Verify that a receipt is valid for a given case.

    This checks:
    - case_sha256 binding
    - repository_revision binding
    - MUTANT_KILLED requires target_readback_sha256 when case.requires_target_readback

    Args:
        receipt: The receipt to verify
        case: The case the receipt should be for

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check case_sha256 binding
    if receipt.case_sha256 != case.case_sha256:
        return False, f"receipt case_sha256 {receipt.case_sha256!r} != case {case.case_sha256!r}"

    # Check repository_revision binding
    if receipt.repository_revision != case.repository_revision:
        return False, (
            f"receipt repository_revision {receipt.repository_revision!r} != "
            f"case {case.repository_revision!r}"
        )

    # Check: MUTANT_KILLED requires target_readback when case.requires_target_readback
    if receipt.verdict == "MUTANT_KILLED" and case.requires_target_readback:
        if not receipt.target_readback_sha256:
            return False, "MUTANT_KILLED requires target_readback_sha256"

    return True, None


def compute_verdict(
    case: Any,  # ControlMutationCase type
    receipt: ControlMutationReceipt,
) -> Verdict:
    """Compute the verdict based on case and receipt.

    This is a pure function that determines the verdict based on:
    - Whether the receipt is bound to the case
    - Whether required evidence is present
    - The observed block code vs expected

    Args:
        case: The control mutation case
        receipt: The execution receipt

    Returns:
        The computed verdict
    """
    # First check for contradictions - note: verify_receipt_for_case takes receipt first
    valid, error = verify_receipt_for_case(receipt, case)
    if not valid:
        return "CONTRADICTED"

    # Check for missing required evidence
    if case.requires_target_readback and not receipt.target_readback_sha256:
        return "UNVERIFIED"

    if case.requires_runtime_execution and not receipt.execution_receipt_sha256:
        return "UNVERIFIED"

    # Determine verdict based on block code comparison
    if receipt.observed_block_code:
        if case.expected_block_code:
            if receipt.observed_block_code == case.expected_block_code:
                return "MUTANT_KILLED"
            else:
                return "MUTANT_SURVIVED"
        else:
            # No expected block code - any block means killed
            return "MUTANT_KILLED"
    else:
        # No observed block code
        if case.expected_block_code:
            return "MUTANT_SURVIVED"
        else:
            return "UNVERIFIED"


__all__ = [
    "ControlMutationReceipt",
    "ControlMutationReceiptError",
    "SCHEMA_VERSION",
    "Verdict",
    "build_control_mutation_receipt",
    "compute_verdict",
    "verify_receipt_for_case",
]
