"""Compare-and-Swap (CAS) primitive for atomic versioned mutation control.

This module provides the core CAS operation that binds mutations to specific
resource versions. A mutation is only applied if the current head matches
the base version that was read.

The module performs no network, database, filesystem, clock or random access.
It only validates and coordinates the CAS decision logic.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Awaitable, Callable, Final, Mapping, Protocol

from .versioned_resource import (
    MutationIntent,
    VersionedResourceRef,
    VersionedResourceError,
    canonical_sha256,
)


_SCHEMA_VERSION: Final[str] = "sovereign.mutation-conflict.v1"
_SHA64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")


class MutationConflict(RuntimeError):
    """Raised when a CAS check fails due to version mismatch.

    This exception carries structured information about the conflict
    to enable deterministic handling and recovery.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        expected_hash: str | None = None,
        actual_hash: str | None = None,
        conflict_fields: tuple[str, ...] = (),
        lock_ref: str | None = None,
        receipt_ref: str | None = None,
        allowed_next_step: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash
        self.conflict_fields = conflict_fields
        self.lock_ref = lock_ref
        self.receipt_ref = receipt_ref
        self.allowed_next_step = allowed_next_step

    def to_dict(self) -> dict[str, Any]:
        """Return structured conflict representation."""
        return {
            "code": self.code,
            "message": self.message,
            "expected_hash": self.expected_hash,
            "actual_hash": self.actual_hash,
            "conflict_fields": list(self.conflict_fields),
            "lock_ref": self.lock_ref,
            "receipt_ref": self.receipt_ref,
            "allowed_next_step": self.allowed_next_step,
        }


# Conflict codes following the issue specification
class ConflictCode:
    BASE_STATE_STALE = "BASE_STATE_STALE"
    HEAD_MOVED = "HEAD_MOVED"
    OVERLAPPING_CHANGE = "OVERLAPPING_CHANGE"
    RESOURCE_LOCKED = "RESOURCE_LOCKED"
    LOCK_SCOPE_MISMATCH = "LOCK_SCOPE_MISMATCH"
    CONFIG_FINGERPRINT_CHANGED = "CONFIG_FINGERPRINT_CHANGED"
    PERMISSION_BASE_MISMATCH = "PERMISSION_BASE_MISMATCH"
    DUPLICATE_EFFECT_DETECTED = "DUPLICATE_EFFECT_DETECTED"
    MUTATED_UNRECEIPTED_BLOCKED = "MUTATED_UNRECEIPTED_BLOCKED"
    IDEMPOTENCY_REPLAY_MISMATCH = "IDEMPOTENCY_REPLAY_MISMATCH"


@dataclass(frozen=True, slots=True)
class CASDecision:
    """Result of a Compare-and-Swap check."""

    allowed: bool
    decision_code: str
    base_resource: VersionedResourceRef
    head_resource: VersionedResourceRef | None
    merged_payload: Mapping[str, Any] | None
    reason: str


@dataclass(frozen=True, slots=True)
class CASContext:
    """Context for a CAS operation containing the mutation intent and base state."""

    intent: MutationIntent
    base_resource: VersionedResourceRef
    head_resource: VersionedResourceRef | None = None
    lock_active: bool = False
    lock_mode: str | None = None


# Protocol for resource store operations
class ResourceStore(Protocol):
    """Protocol for resource store that provides head state."""

    async def read_resource_head(
        self, resource_ref: VersionedResourceRef
    ) -> VersionedResourceRef | None:
        """Read the current head state of a resource."""
        ...

    async def lock_resource(
        self, resource_ref: VersionedResourceRef, *, mode: str = "mutation_locked"
    ) -> bool:
        """Acquire a lock on a resource. Returns True if lock acquired."""
        ...

    async def unlock_resource(
        self, resource_ref: VersionedResourceRef
    ) -> bool:
        """Release a lock on a resource. Returns True if lock released."""
        ...


def check_base_head_match(base: VersionedResourceRef, head: VersionedResourceRef | None) -> bool:
    """Check if base version matches current head.

    Returns True if head is None (resource doesn't exist yet and base expects that)
    or if head's content_hash matches base's content_hash.
    """

    if head is None:
        # Resource doesn't exist - valid only if base has no prior version
        return base.version == "0" or base.content_hash == "0" * 64

    return head.content_hash == base.content_hash


def check_version_progression(base: VersionedResourceRef, head: VersionedResourceRef | None) -> bool:
    """Check if head represents a newer version than base.

    This prevents replaying a mutation against an older state.
    """

    if head is None:
        return True  # No head means we're at base or before

    # Compare versions numerically or lexicographically depending on format
    try:
        base_num = int(base.version)
        head_num = int(head.version)
        return head_num >= base_num
    except ValueError:
        # Fall back to string comparison
        return head.version >= base.version


async def compare_and_swap(
    store: ResourceStore,
    intent: MutationIntent,
    apply_change: Callable[[VersionedResourceRef, MutationIntent], Awaitable[Mapping[str, Any]]],
    *,
    accept_merge: bool = True,
) -> CASDecision:
    """Execute a Compare-and-Swap operation with optional deterministic merge.

    Args:
        store: Resource store providing head state and locking
        intent: Mutation intent binding to base version
        apply_change: Function to apply the mutation and return new state
        accept_merge: Whether to attempt merge on conflict (default True)

    Returns:
        CASDecision with allowed=True if mutation can proceed

    Raises:
        MutationConflict: If CAS check fails and merge not possible
    """

    base = intent.resource

    # Step 1: Acquire lock
    lock_acquired = await store.lock_resource(base, mode="mutation_locked")
    if not lock_acquired:
        raise MutationConflict(
            code=ConflictCode.RESOURCE_LOCKED,
            message=f"Resource {base.resource_type}/{base.resource_id} is locked",
            expected_hash=base.content_hash,
            lock_ref=f"{base.resource_type}:{base.resource_id}",
            allowed_next_step="retry_after_unlock",
        )

    try:
        # Step 2: Read current head
        head = await store.read_resource_head(base)

        # Step 3: Verify base matches head
        if not check_base_head_match(base, head):
            raise MutationConflict(
                code=ConflictCode.BASE_STATE_STALE,
                message=f"Base state {base.content_hash[:8]} does not match current head {head.content_hash[:8] if head else 'none'}",
                expected_hash=base.content_hash,
                actual_hash=head.content_hash if head else None,
                allowed_next_step="rebase_and_retry",
            )

        # Step 4: Check version progression
        if not check_version_progression(base, head):
            raise MutationConflict(
                code=ConflictCode.HEAD_MOVED,
                message=f"Head version {head.version if head else 'none'} is older than base {base.version}",
                expected_hash=base.content_hash,
                actual_hash=head.content_hash if head else None,
                allowed_next_step="rebase_and_retry",
            )

        # Step 5: Apply change
        new_state = await apply_change(base if head is None else head, intent)

        return CASDecision(
            allowed=True,
            decision_code="APPLIED",
            base_resource=base,
            head_resource=head,
            merged_payload=new_state,
            reason="Mutation applied successfully",
        )

    finally:
        # Step 6: Release lock
        await store.unlock_resource(base)


def detect_overlapping_changes(
    base: Mapping[str, Any],
    head: Mapping[str, Any],
    proposed: Mapping[str, Any],
    protected_fields: frozenset[str],
) -> tuple[frozenset[str], bool]:
    """Detect overlapping changes between head and proposed against base.

    Returns:
        Tuple of (overlapping_fields, has_protected_overlap)
    """

    # Find fields that changed in head vs base
    head_changed: set[str] = set()
    for key in set(base.keys()) | set(head.keys()):
        if base.get(key) != head.get(key):
            head_changed.add(key)

    # Find fields that changed in proposed vs base
    proposed_changed: set[str] = set()
    for key in set(base.keys()) | set(proposed.keys()):
        if base.get(key) != proposed.get(key):
            proposed_changed.add(key)

    # Find overlap
    overlap = head_changed & proposed_changed

    # Check for protected field overlap
    protected_overlap = overlap & protected_fields

    return frozenset(overlap), len(protected_overlap) > 0


def cas_from_github_pr(
    intent: MutationIntent,
    expected_pr_head: str,
    actual_pr_head: str | None,
    expected_main_head: str,
    actual_main_head: str,
) -> CASDecision:
    """Evaluate CAS decision for a GitHub PR merge operation.

    For GitHub operations, we bind both the PR head and main head.
    """

    base = intent.resource

    if actual_pr_head is None:
        return CASDecision(
            allowed=False,
            decision_code=ConflictCode.BASE_STATE_STALE,
            base_resource=base,
            head_resource=None,
            merged_payload=None,
            reason="PR does not exist or has been closed",
        )

    if expected_pr_head != actual_pr_head:
        raise MutationConflict(
            code=ConflictCode.HEAD_MOVED,
            message=f"PR head changed from {expected_pr_head[:8]} to {actual_pr_head[:8]}",
            expected_hash=expected_pr_head,
            actual_hash=actual_pr_head,
            allowed_next_step="rebase_and_retry",
        )

    if expected_main_head != actual_main_head:
        raise MutationConflict(
            code=ConflictCode.BASE_STATE_STALE,
            message=f"Main branch moved from {expected_main_head[:8]} to {actual_main_head[:8]}",
            expected_hash=expected_main_head,
            actual_hash=actual_main_head,
            allowed_next_step="rebase_and_retry",
        )

    return CASDecision(
        allowed=True,
        decision_code="GITHUB_CAS_PASSED",
        base_resource=base,
        head_resource=None,
        merged_payload=None,
        reason="GitHub PR merge CAS check passed",
    )


def build_conflict_response(conflict: MutationConflict) -> dict[str, Any]:
    """Build a structured conflict response for API consumers."""

    return {
        "ok": False,
        "error": {
            "code": conflict.code,
            "message": conflict.message,
            "details": conflict.to_dict(),
        },
        "allowed_next_step": conflict.allowed_next_step,
    }


__all__ = [
    "MutationConflict",
    "ConflictCode",
    "CASDecision",
    "CASContext",
    "ResourceStore",
    "compare_and_swap",
    "check_base_head_match",
    "check_version_progression",
    "detect_overlapping_changes",
    "cas_from_github_pr",
    "build_conflict_response",
]
