"""Atomic Mutation Receipt with phase tracking and idempotency.

This module provides mutation receipts that bind mutation intent to outcome
in an append-only, hash-chained structure. Receipts track mutation phases
to enable safe crash recovery and prevent duplicate effects.

The module performs no network, database, filesystem, clock or random access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import enum
import hashlib
import json
import re
from typing import Any, Final, Mapping, Sequence

from .versioned_resource import (
    MutationIntent,
    VersionedResourceRef,
    canonical_sha256,
    canonical_value,
)


_SCHEMA_VERSION: Final[str] = "sovereign.mutation-receipt.v1"
_MUTATION_SCHEMA_VERSION: Final[str] = "sovereign.mutation-state.v1"
_SHA64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")


class MutationPhase(enum.StrEnum):
    """Phases of a mutation lifecycle for crash-safe idempotency."""

    PREPARED = "prepared"
    LOCKED = "locked"
    APPLIED_UNVERIFIED = "applied_unverified"
    VERIFIED = "verified"
    CONFLICTED = "conflicted"
    BLOCKED = "blocked"
    INVALIDATED = "invalidated"


class ReceiptContractError(ValueError):
    """A receipt input violated a deterministic or safety invariant."""


class MutationPhaseError(RuntimeError):
    """Mutation is in an invalid phase for the requested operation."""


def _normalize_string(value: str, *, label: str, max_length: int = 240) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ReceiptContractError(f"{label} must be non-empty")
    if len(normalized) > max_length:
        raise ReceiptContractError(f"{label} exceeds maximum length of {max_length}")
    return normalized


def _normalize_sha64(value: str, *, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _SHA64.fullmatch(normalized):
        raise ReceiptContractError(f"{label} must be a lowercase SHA-256")
    return normalized


def _normalize_optional_sha64(value: str | None, *, label: str) -> str | None:
    if value is None:
        return None
    return _normalize_sha64(value, label=label)


@dataclass(frozen=True, slots=True)
class MutationState:
    """Complete state of a mutation for persistence."""

    schema_version: str
    mutation_id: str
    idempotency_key: str
    intent: Mapping[str, Any]
    payload_hash: str
    base_state_hash: str
    expected_effect_hash: str
    phase: str
    phase_transitions: tuple[Mapping[str, Any], ...]
    previous_receipt_hash: str | None
    applied_state: Mapping[str, Any] | None
    applied_version: str | None
    applied_content_hash: str | None
    receipt_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.schema_version != _MUTATION_SCHEMA_VERSION:
            raise ReceiptContractError(f"unsupported schema version: {self.schema_version}")
        object.__setattr__(self, "mutation_id", _normalize_string(
            self.mutation_id, label="mutation_id", max_length=120))
        object.__setattr__(self, "idempotency_key", _normalize_string(
            self.idempotency_key, label="idempotency_key", max_length=240))
        object.__setattr__(self, "intent", dict(self.intent))
        object.__setattr__(self, "payload_hash", _normalize_sha64(
            self.payload_hash, label="payload_hash"))
        object.__setattr__(self, "base_state_hash", _normalize_sha64(
            self.base_state_hash, label="base_state_hash"))
        object.__setattr__(self, "expected_effect_hash", _normalize_sha64(
            self.expected_effect_hash, label="expected_effect_hash"))
        object.__setattr__(self, "phase", _normalize_string(
            self.phase, label="phase", max_length=40).lower())
        if self.phase not in [p.value for p in MutationPhase]:
            raise ReceiptContractError(f"invalid phase: {self.phase}")
        object.__setattr__(self, "phase_transitions", tuple(
            dict(t) for t in self.phase_transitions))
        object.__setattr__(self, "previous_receipt_hash", _normalize_optional_sha64(
            self.previous_receipt_hash, label="previous_receipt_hash"))
        if self.applied_state is not None:
            object.__setattr__(self, "applied_state", dict(self.applied_state))
        object.__setattr__(self, "applied_version", _normalize_optional_sha64(
            self.applied_version, label="applied_version") if self.applied_version else None)
        object.__setattr__(self, "applied_content_hash", _normalize_optional_sha64(
            self.applied_content_hash, label="applied_content_hash") if self.applied_content_hash else None)

        # Compute receipt hash manually to avoid recursion
        body = {
            "schema_version": self.schema_version,
            "mutation_id": self.mutation_id,
            "idempotency_key": self.idempotency_key,
            "intent": self.intent,
            "payload_hash": self.payload_hash,
            "base_state_hash": self.base_state_hash,
            "expected_effect_hash": self.expected_effect_hash,
            "phase": self.phase,
            "phase_transitions": list(self.phase_transitions),
            "previous_receipt_hash": self.previous_receipt_hash,
            "applied_state": self.applied_state,
            "applied_version": self.applied_version,
            "applied_content_hash": self.applied_content_hash,
            "receipt_hash": "placeholder",
        }
        body["receipt_hash"] = canonical_sha256(body)
        del body["receipt_hash"]
        object.__setattr__(self, "receipt_hash", canonical_sha256(body))

    def canonical_body(self) -> dict[str, Any]:
        """Return canonical dictionary representation."""
        return {
            "schema_version": self.schema_version,
            "mutation_id": self.mutation_id,
            "idempotency_key": self.idempotency_key,
            "intent": self.intent,
            "payload_hash": self.payload_hash,
            "base_state_hash": self.base_state_hash,
            "expected_effect_hash": self.expected_effect_hash,
            "phase": self.phase,
            "phase_transitions": list(self.phase_transitions),
            "previous_receipt_hash": self.previous_receipt_hash,
            "applied_state": self.applied_state,
            "applied_version": self.applied_version,
            "applied_content_hash": self.applied_content_hash,
            "receipt_hash": self.receipt_hash,
        }

    def transition_to(self, new_phase: MutationPhase, **metadata: Any) -> MutationState:
        """Create a new state with a phase transition."""

        transition = {
            "from_phase": self.phase,
            "to_phase": new_phase.value,
            "metadata": dict(metadata),
        }

        return MutationState(
            schema_version=self.schema_version,
            mutation_id=self.mutation_id,
            idempotency_key=self.idempotency_key,
            intent=self.intent,
            payload_hash=self.payload_hash,
            base_state_hash=self.base_state_hash,
            expected_effect_hash=self.expected_effect_hash,
            phase=new_phase.value,
            phase_transitions=(*self.phase_transitions, transition),
            previous_receipt_hash=self.receipt_hash,
            applied_state=self.applied_state,
            applied_version=self.applied_version,
            applied_content_hash=self.applied_content_hash,
        )

    def with_applied_state(
        self,
        state: Mapping[str, Any],
        version: str,
        content_hash: str,
    ) -> MutationState:
        """Create a new state with applied result."""

        return MutationState(
            schema_version=self.schema_version,
            mutation_id=self.mutation_id,
            idempotency_key=self.idempotency_key,
            intent=self.intent,
            payload_hash=self.payload_hash,
            base_state_hash=self.base_state_hash,
            expected_effect_hash=self.expected_effect_hash,
            phase=self.phase,
            phase_transitions=self.phase_transitions,
            previous_receipt_hash=self.previous_receipt_hash,
            applied_state=dict(state),
            applied_version=_normalize_sha64(version, label="version"),
            applied_content_hash=_normalize_sha64(content_hash, label="content_hash"),
        )


@dataclass(frozen=True, slots=True)
class MutationReceipt:
    """Canonical receipt for a mutation operation.

    The receipt binds the mutation intent to its outcome in an
    append-only, hash-chained structure suitable for audit.
    """

    schema_version: str
    mutation_id: str
    idempotency_key: str
    resource_type: str
    resource_id: str
    owner_id: str
    capability_id: str
    base_version: str
    base_content_hash: str
    head_version: str | None
    head_content_hash: str | None
    payload_hash: str
    permission_receipt_hash: str
    phase: str
    outcome: str
    effect_hash: str | None
    previous_receipt_hash: str | None
    receipt_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.schema_version != _SCHEMA_VERSION:
            raise ReceiptContractError(f"unsupported schema version: {self.schema_version}")
        object.__setattr__(self, "mutation_id", _normalize_string(
            self.mutation_id, label="mutation_id", max_length=120))
        object.__setattr__(self, "idempotency_key", _normalize_string(
            self.idempotency_key, label="idempotency_key", max_length=240))
        object.__setattr__(self, "resource_type", _normalize_string(
            self.resource_type, label="resource_type", max_length=60).lower())
        object.__setattr__(self, "resource_id", _normalize_string(
            self.resource_id, label="resource_id", max_length=120))
        object.__setattr__(self, "owner_id", _normalize_string(
            self.owner_id, label="owner_id", max_length=120))
        object.__setattr__(self, "capability_id", _normalize_string(
            self.capability_id, label="capability_id", max_length=120))
        object.__setattr__(self, "base_version", _normalize_string(
            self.base_version, label="base_version", max_length=120))
        object.__setattr__(self, "base_content_hash", _normalize_sha64(
            self.base_content_hash, label="base_content_hash"))
        object.__setattr__(self, "head_version", _normalize_optional_sha64(
            self.head_version, label="head_version"))
        object.__setattr__(self, "head_content_hash", _normalize_optional_sha64(
            self.head_content_hash, label="head_content_hash"))
        object.__setattr__(self, "payload_hash", _normalize_sha64(
            self.payload_hash, label="payload_hash"))
        object.__setattr__(self, "permission_receipt_hash", _normalize_sha64(
            self.permission_receipt_hash, label="permission_receipt_hash"))
        object.__setattr__(self, "phase", _normalize_string(
            self.phase, label="phase", max_length=40).lower())
        object.__setattr__(self, "outcome", _normalize_string(
            self.outcome, label="outcome", max_length=40).lower())
        object.__setattr__(self, "effect_hash", _normalize_optional_sha64(
            self.effect_hash, label="effect_hash"))
        object.__setattr__(self, "previous_receipt_hash", _normalize_optional_sha64(
            self.previous_receipt_hash, label="previous_receipt_hash"))

        # Compute receipt hash manually to avoid recursion
        body = {
            "schema_version": self.schema_version,
            "mutation_id": self.mutation_id,
            "idempotency_key": self.idempotency_key,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "owner_id": self.owner_id,
            "capability_id": self.capability_id,
            "base_version": self.base_version,
            "base_content_hash": self.base_content_hash,
            "head_version": self.head_version,
            "head_content_hash": self.head_content_hash,
            "payload_hash": self.payload_hash,
            "permission_receipt_hash": self.permission_receipt_hash,
            "phase": self.phase,
            "outcome": self.outcome,
            "effect_hash": self.effect_hash,
            "previous_receipt_hash": self.previous_receipt_hash,
            "receipt_hash": "placeholder",
        }
        body["receipt_hash"] = canonical_sha256(body)
        del body["receipt_hash"]
        object.__setattr__(self, "receipt_hash", canonical_sha256(body))

    def canonical_body(self) -> dict[str, Any]:
        """Return canonical dictionary representation."""
        return {
            "schema_version": self.schema_version,
            "mutation_id": self.mutation_id,
            "idempotency_key": self.idempotency_key,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "owner_id": self.owner_id,
            "capability_id": self.capability_id,
            "base_version": self.base_version,
            "base_content_hash": self.base_content_hash,
            "head_version": self.head_version,
            "head_content_hash": self.head_content_hash,
            "payload_hash": self.payload_hash,
            "permission_receipt_hash": self.permission_receipt_hash,
            "phase": self.phase,
            "outcome": self.outcome,
            "effect_hash": self.effect_hash,
            "previous_receipt_hash": self.previous_receipt_hash,
            "receipt_hash": self.receipt_hash,
        }

    def to_dict(self) -> dict[str, Any]:
        """Return receipt as dictionary."""
        return self.canonical_body()


def build_mutation_receipt(
    mutation_id: str,
    intent: MutationIntent,
    phase: MutationPhase,
    outcome: str,
    head_version: str | None = None,
    head_content_hash: str | None = None,
    effect_hash: str | None = None,
    previous_receipt_hash: str | None = None,
) -> MutationReceipt:
    """Build a validated MutationReceipt from intent and outcome."""

    return MutationReceipt(
        schema_version=_SCHEMA_VERSION,
        mutation_id=mutation_id,
        idempotency_key=intent.idempotency_key,
        resource_type=intent.resource.resource_type,
        resource_id=intent.resource.resource_id,
        owner_id=intent.resource.owner_id,
        capability_id=intent.capability_id,
        base_version=intent.resource.version,
        base_content_hash=intent.resource.content_hash,
        head_version=head_version,
        head_content_hash=head_content_hash,
        payload_hash=intent.payload_hash,
        permission_receipt_hash=intent.permission_receipt_hash,
        phase=phase.value,
        outcome=outcome,
        effect_hash=effect_hash,
        previous_receipt_hash=previous_receipt_hash,
    )


def verify_idempotency(
    existing_receipt: MutationReceipt,
    new_intent: MutationIntent,
) -> tuple[bool, str]:
    """Verify that a new intent matches an existing receipt for idempotency.

    Returns (matches, reason).
    """

    # Check idempotency key
    if existing_receipt.idempotency_key != new_intent.idempotency_key:
        return False, "idempotency_key mismatch"

    # Check resource
    if existing_receipt.resource_id != new_intent.resource.resource_id:
        return False, "resource_id mismatch"

    # Check payload hash
    if existing_receipt.payload_hash != new_intent.payload_hash:
        return False, "payload_hash mismatch - different mutation with same idempotency key"

    # Check permission (should match for same key)
    if existing_receipt.permission_receipt_hash != new_intent.permission_receipt_hash:
        return False, "permission_receipt_hash mismatch"

    return True, "idempotency key matches existing receipt"


def verify_receipt_chain(
    receipts: Sequence[MutationReceipt],
    anchor_previous_hash: str | None = None,
) -> dict[str, Any]:
    """Verify a chain of mutation receipts.

    Returns verification result with findings.
    """

    if not receipts:
        return {
            "ok": False,
            "reason": "at least one receipt is required",
            "verified_count": 0,
            "findings": [],
        }

    findings: list[dict[str, Any]] = []
    previous = anchor_previous_hash
    verified = 0

    for index, receipt in enumerate(receipts):
        stored_hash = receipt.receipt_hash
        body_hash = canonical_sha256(receipt.canonical_body())

        # Check hash integrity
        if stored_hash != body_hash:
            findings.append({
                "index": index,
                "mutation_id": receipt.mutation_id,
                "family": "RECEIPT_HASH_MISMATCH",
            })
        else:
            verified += 1

        # Check chain link
        if previous is not None and receipt.previous_receipt_hash != previous:
            findings.append({
                "index": index,
                "mutation_id": receipt.mutation_id,
                "family": "CHAIN_LINK_MISMATCH",
                "expected": previous,
                "actual": receipt.previous_receipt_hash,
            })

        previous = stored_hash

    return {
        "ok": len(findings) == 0,
        "verified_count": verified,
        "receipt_count": len(receipts),
        "chain_head_hash": previous,
        "findings": findings,
    }


def recovery_decision(receipt: MutationReceipt, current_head: VersionedResourceRef | None) -> str:
    """Determine safe recovery action after crash based on receipt and current state.

    Returns recommended action: 'retry', 'continue_readback', or 'block'.
    """

    phase = MutationPhase(receipt.phase)

    if phase == MutationPhase.PREPARED:
        # Prepared but not applied - safe to retry
        return "retry"

    if phase == MutationPhase.LOCKED:
        # Had lock but crashed before apply - retry with CAS recheck
        return "retry"

    if phase == MutationPhase.APPLIED_UNVERIFIED:
        # Applied but not verified - don't reapply, continue readback
        if current_head is not None and current_head.content_hash == receipt.effect_hash:
            return "continue_readback"
        return "block"

    if phase == MutationPhase.VERIFIED:
        # Successfully completed - no action needed
        return "continue_readback"

    if phase in (MutationPhase.CONFLICTED, MutationPhase.BLOCKED, MutationPhase.INVALIDATED):
        # Terminal failure states
        return "block"

    return "block"


__all__ = [
    "MutationPhase",
    "ReceiptContractError",
    "MutationPhaseError",
    "MutationState",
    "MutationReceipt",
    "build_mutation_receipt",
    "verify_idempotency",
    "verify_receipt_chain",
    "recovery_decision",
]
