"""Compare-and-Swap (CAS) primitives for atomic mutations.

This module provides deterministic CAS operations for versioned resources,
including field-level merge detection for safe automatic merging of disjoint
changes.

Referenced by:
    - Issue #1119: Atomic Versioned Mutation Control
    - Section 3: CAS-Entscheidung
    - Section 4: Deterministischer Merge
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Generic, ParamSpec, TypeVar

from .versioned_resource import (
    MutationConflict,
    MutationFailureCode,
    PROTECTED_FIELDS,
    VersionedResource,
    VersionedResourceRef,
)

P = ParamSpec("P")
T = TypeVar("T")


@dataclass(frozen=True)
class CASDecision:
    """Result of a CAS check decision."""
    decision: str  # "apply", "merge", "conflict"
    head: VersionedResource | None
    merged_payload: dict[str, Any] | None = None
    conflicting_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class CASResult(Generic[T]):
    """Result of a CAS operation."""
    success: bool
    new_resource: T | None = None
    cas_decision: CASDecision | None = None
    error: MutationConflict | None = None


async def compare_and_swap(
    store: Any,
    intent: Any,
    apply_change: Callable[..., Awaitable[T]],
    head_reader: Callable[..., Awaitable[VersionedResource]] | None = None,
) -> CASResult[T]:
    """Perform a CAS operation on a versioned resource.

    The operation:
    1. Acquires a lock on the resource
    2. Reads the current head
    3. Compares head content_hash with intent base content_hash
    4. Either applies, merges, or raises a conflict
    5. Returns the result

    Args:
        store: The resource store with lock_resource support
        intent: A MutationIntent with the base state
        apply_change: Async function to apply the change (head, intent) -> T
        head_reader: Optional custom head reader (defaults to store.read_resource)

    Returns:
        CASResult with success=True and new_resource, or success=False with error

    Raises:
        MutationConflict: When base != head and merge is not possible
    """
    resource_ref = intent.resource

    # Acquire lock if store supports it
    lock_ctx = None
    if hasattr(store, "lock_resource"):
        lock_ctx = store.lock_resource(resource_ref)
        if hasattr(lock_ctx, "__aenter__"):
            await lock_ctx.__aenter__()
        elif hasattr(lock_ctx, "__enter__"):
            lock_ctx.__enter__()

    try:
        # Read current head
        if head_reader:
            head = await head_reader(resource_ref)
        else:
            head = await store.read_resource(resource_ref)

        # CAS check: compare base with head
        if head.content_hash != resource_ref.content_hash:
            # State has changed since intent was created
            return CASResult(
                success=False,
                cas_decision=CASDecision(
                    decision="conflict",
                    head=head,
                    conflicting_fields=(resource_ref.resource_id,),
                ),
                error=MutationConflict(
                    code=MutationFailureCode.BASE_STATE_STALE,
                    expected_hash=resource_ref.content_hash,
                    actual_hash=head.content_hash,
                    conflicting_fields=(resource_ref.resource_id,),
                    suggested_action="Read the new head and create a new intent with updated base",
                ),
            )

        # Base matches head - safe to apply
        new_resource = await apply_change(head, intent)
        return CASResult(
            success=True,
            new_resource=new_resource,
            cas_decision=CASDecision(
                decision="apply",
                head=head,
            ),
        )

    finally:
        # Release lock
        if lock_ctx is not None:
            if hasattr(lock_ctx, "__aexit__"):
                await lock_ctx.__aexit__(None, None, None)
            elif hasattr(lock_ctx, "__exit__"):
                lock_ctx.__exit__(None, None, None)


def merge_disjoint_fields(
    base: dict[str, Any],
    head: dict[str, Any],
    proposed: dict[str, Any],
    protected: frozenset[str] | set[str] = PROTECTED_FIELDS,
) -> tuple[dict[str, Any], CASDecision]:
    """Attempt to merge disjoint field changes deterministically.

    Auto-merge is only allowed when changes are provably disjoint
    (no overlapping fields and no protected fields modified).

    Args:
        base: The base state that both head and proposed derived from
        head: The current head state (may have changes from base)
        proposed: The proposed new state (may have changes from base)
        protected: Fields that can never be auto-merged

    Returns:
        Tuple of (merged_payload, cas_decision) if merge possible

    Raises:
        MutationConflict: When changes overlap or protected fields modified
    """
    # Find what changed from base
    changed_in_head = {k for k in head if head.get(k) != base.get(k)}
    changed_in_proposal = {k for k in proposed if proposed.get(k) != base.get(k)}

    # Check for overlap
    overlap = changed_in_head & changed_in_proposal

    # Check for protected field modifications
    protected_modified = changed_in_proposal & set(protected)

    if overlap or protected_modified:
        raise MutationConflict(
            code=MutationFailureCode.OVERLAPPING_CHANGE,
            expected_hash="base",
            actual_hash="head",
            conflicting_fields=tuple(sorted(overlap | protected_modified)),
            suggested_action="Manually resolve conflicts or create new intent with current head",
        )

    # Build merged result: start from head, apply proposal changes
    merged: dict[str, Any] = {**head}
    for key in changed_in_proposal:
        merged[key] = proposed[key]

    decision = CASDecision(
        decision="merge",
        head=None,  # Not needed for merge
        merged_payload=merged,
        conflicting_fields=(),
    )

    return merged, decision


def check_cas_prerequisites(
    base_hash: str,
    head_hash: str,
    payload_hash: str,
    expected_base_hash: str,
    expected_payload_hash: str,
) -> tuple[bool, MutationConflict | None]:
    """Check CAS prerequisites before attempting a mutation.

    Validates:
    - Base hash matches expected
    - Head hash matches base (no drift since intent creation)
    - Payload hash matches expected

    Returns:
        Tuple of (prerequisites_ok, error_or_none)
    """
    if base_hash != expected_base_hash:
        return False, MutationConflict(
            code=MutationFailureCode.BASE_STATE_STALE,
            expected_hash=expected_base_hash,
            actual_hash=base_hash,
            suggested_action="Read current head and create new intent",
        )

    if head_hash != base_hash:
        return False, MutationConflict(
            code=MutationFailureCode.HEAD_MOVED,
            expected_hash=base_hash,
            actual_hash=head_hash,
            suggested_action="Another mutation occurred; read new head and retry",
        )

    if payload_hash != expected_payload_hash:
        return False, MutationConflict(
            code=MutationFailureCode.IDEMPOTENCY_REPLAY_MISMATCH,
            expected_hash=expected_payload_hash,
            actual_hash=payload_hash,
            suggested_action="Same idempotency key with different payload is rejected",
        )

    return True, None


def detect_field_overlap(
    base: dict[str, Any],
    current: dict[str, Any],
    proposed: dict[str, Any],
) -> tuple[bool, set[str]]:
    """Detect if proposed changes overlap with current changes.

    Returns:
        Tuple of (has_overlap, overlapping_fields)
    """
    base_changed = {k for k in current if current.get(k) != base.get(k)}
    proposed_changed = {k for k in proposed if proposed.get(k) != base.get(k)}
    overlap = base_changed & proposed_changed
    return bool(overlap), overlap
