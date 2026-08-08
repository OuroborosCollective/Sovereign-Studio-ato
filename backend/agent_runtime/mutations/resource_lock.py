"""Resource lock primitives for mutation control.

This module provides resource locking mechanisms that prevent mutations
without blocking readback operations. Locks require explicit authorized
unlock with a new receipt.

Lock rules:
- Lock prevents mutation, not readback
- Unlock requires explicit authorized payload and new receipt
- LLM text alone cannot remove a lock
- Sub-resources inherit parent locks when mutation affects parent state

Referenced by:
    - Issue #1119: Atomic Versioned Mutation Control
    - Section 5: Resource Locks
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .versioned_resource import (
    LOCK_MODE_DEPLOYMENT_FREEZE,
    LOCK_MODE_INCIDENT_FREEZE,
    LOCK_MODE_MIGRATION_FREEZE,
    LOCK_MODE_MUTATION_LOCKED,
    LOCK_MODE_OWNER_LOCKED,
    LOCK_MODE_READ_ONLY_MAINTENANCE,
    LOCK_MODES,
    ResourceLock,
    ResourceLockError,
    ResourceScope,
    ResourceType,
)


def validate_lock_scope(
    lock: ResourceLock,
    mutation_scope: ResourceScope,
    mutation_resource_type: ResourceType,
    mutation_resource_id: str,
) -> tuple[bool, str | None]:
    """Validate that a lock's scope matches the mutation's scope.

    Locks must have compatible ownership to prevent cross-scope bypass.
    A lock in one tenant cannot block mutations in another tenant.

    Args:
        lock: The lock to validate
        mutation_scope: The scope of the attempted mutation
        mutation_resource_type: Type of resource being mutated
        mutation_resource_id: ID of resource being mutated

    Returns:
        Tuple of (is_valid, error_message)
    """
    if lock.scope is None:
        # Legacy lock without scope - be conservative
        return False, "Lock without scope cannot block scoped mutation"

    # Check owner isolation
    if lock.scope.owner_id != mutation_scope.owner_id:
        return False, f"Lock owner {lock.scope.owner_id} != mutation owner {mutation_scope.owner_id}"

    # Check organization isolation
    if lock.scope.organization_id and mutation_scope.organization_id:
        if lock.scope.organization_id != mutation_scope.organization_id:
            return False, f"Lock org {lock.scope.organization_id} != mutation org {mutation_scope.organization_id}"

    # Check repository isolation
    if lock.scope.repository_id and mutation_scope.repository_id:
        if lock.scope.repository_id != mutation_scope.repository_id:
            return False, f"Lock repo {lock.scope.repository_id} != mutation repo {mutation_scope.repository_id}"

    # Check workspace isolation
    if lock.scope.workspace_id and mutation_scope.workspace_id:
        if lock.scope.workspace_id != mutation_scope.workspace_id:
            return False, f"Lock workspace {lock.scope.workspace_id} != mutation workspace {mutation_scope.workspace_id}"

    return True, None


def check_lock_active(
    lock: ResourceLock,
    current_time: int | None = None,
) -> tuple[bool, str | None]:
    """Check if a lock is currently active.

    Args:
        lock: The lock to check
        current_time: Current timestamp in seconds (defaults to now)

    Returns:
        Tuple of (is_active, reason_if_inactive)
    """
    if current_time is None:
        current_time = int(__import__("time").time())

    # Check expiration
    if lock.expires_at is not None and current_time > lock.expires_at:
        return False, f"Lock expired at {lock.expires_at}"

    # Check predecessor chain - lock is invalid if predecessor hash doesn't match
    # This would be checked against the resource's lock history
    # Implementation depends on lock store

    return True, None


def validate_unlock_capability(
    lock: ResourceLock,
    unlock_capability_id: str,
) -> tuple[bool, str | None]:
    """Validate that an unlock request has the required capability.

    Args:
        lock: The lock to unlock
        unlock_capability_id: The capability ID attempting the unlock

    Returns:
        Tuple of (is_authorized, error_message)
    """
    if unlock_capability_id != lock.required_unlock_capability:
        return False, f"Unlock capability {unlock_capability_id} != required {lock.required_unlock_capability}"

    return True, None


def check_mutation_blocked_by_lock(
    locks: list[ResourceLock],
    mutation_scope: ResourceScope,
    mutation_resource_type: ResourceType,
    mutation_resource_id: str,
    current_time: int | None = None,
) -> tuple[bool, ResourceLock | None, str | None]:
    """Check if a mutation is blocked by any active lock.

    Args:
        locks: List of active locks on the resource
        mutation_scope: Scope of the attempted mutation
        mutation_resource_type: Type of resource being mutated
        mutation_resource_id: ID of resource being mutated
        current_time: Current timestamp (defaults to now)

    Returns:
        Tuple of (is_blocked, blocking_lock, error_message)
    """
    for lock in locks:
        # Check if lock is still active
        is_active, inactive_reason = check_lock_active(lock, current_time)
        if not is_active:
            continue

        # Validate lock scope matches mutation scope
        is_valid, scope_error = validate_lock_scope(
            lock,
            mutation_scope,
            mutation_resource_type,
            mutation_resource_id,
        )
        if not is_valid:
            # Lock exists but is for different scope - ignore
            continue

        # Lock is active and valid - mutation is blocked
        return True, lock, None

    return False, None, None


def build_lock_error(
    lock: ResourceLock,
    resource_type: ResourceType,
    resource_id: str,
) -> ResourceLockError:
    """Build a ResourceLockError from a lock and mutation details."""
    return ResourceLockError(
        resource_type=resource_type,
        resource_id=resource_id,
        lock_mode=lock.mode,
        reason_code=lock.reason_code,
        required_capability=lock.required_unlock_capability,
        lock_id=lock.lock_id,
    )


def format_lock_manifest(locks: list[ResourceLock]) -> dict[str, Any]:
    """Format locks into a manifest suitable for API responses.

    Returns a structured view of all locks without exposing internal details.
    """
    return {
        "lock_count": len(locks),
        "locks": [
            {
                "resource_type": lock.resource_type,
                "resource_id": lock.resource_id,
                "mode": lock.mode,
                "reason_code": lock.reason_code,
                "required_capability": lock.required_unlock_capability,
                "lock_id": lock.lock_id,
                "created_at": lock.created_at,
                "expires_at": lock.expires_at,
            }
            for lock in locks
        ],
    }
