"""Resource Lock primitive for mutation coordination.

This module provides owner- and scope-bound locks that prevent mutations
on resources without blocking read access. Locks are explicit, authorized
actions that require a valid receipt for both acquisition and release.

The module performs no network, database, filesystem, clock or random access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Final, Mapping, Optional, Sequence

from .versioned_resource import (
    canonical_sha256,
    canonical_value,
)


_SCHEMA_VERSION: Final[str] = "sovereign.resource-lock.v1"
_SHA64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")


# Supported lock modes
class LockMode:
    MUTATION_LOCKED = "mutation_locked"
    OWNER_LOCKED = "owner_locked"
    DEPLOYMENT_FREEZE = "deployment_freeze"
    INCIDENT_FREEZE = "incident_freeze"
    MIGRATION_FREEZE = "migration_freeze"
    READ_ONLY_MAINTENANCE = "read_only_maintenance"


VALID_LOCK_MODES: tuple[str, ...] = (
    LockMode.MUTATION_LOCKED,
    LockMode.OWNER_LOCKED,
    LockMode.DEPLOYMENT_FREEZE,
    LockMode.INCIDENT_FREEZE,
    LockMode.MIGRATION_FREEZE,
    LockMode.READ_ONLY_MAINTENANCE,
)


class ResourceLockError(ValueError):
    """A resource lock input violated a deterministic or safety invariant."""


def _normalize_string(value: str, *, label: str, max_length: int = 240) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ResourceLockError(f"{label} must be non-empty")
    if len(normalized) > max_length:
        raise ResourceLockError(f"{label} exceeds maximum length of {max_length}")
    return normalized


def _normalize_sha64(value: str, *, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _SHA64.fullmatch(normalized):
        raise ResourceLockError(f"{label} must be a lowercase SHA-256")
    return normalized


def _normalize_optional_sha64(value: str | None, *, label: str) -> str | None:
    if value is None:
        return None
    return _normalize_sha64(value, label=label)


@dataclass(frozen=True, slots=True)
class ResourceLock:
    """Immutable resource lock specification.

    A lock prevents mutations on a resource without blocking reads.
    Locks are owner-bound and require explicit authorization for release.
    """

    resource_type: str
    resource_id: str
    lock_mode: str
    reason_code: str
    required_unlock_capability: str
    required_readbacks: tuple[str, ...]
    owner_id: str
    created_by_receipt: str
    created_at_revision: str
    predecessor_hash: str | None
    expires_at_version: str | None
    lock_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "resource_type", _normalize_string(
            self.resource_type, label="resource_type", max_length=60).lower())
        object.__setattr__(self, "resource_id", _normalize_string(
            self.resource_id, label="resource_id", max_length=120))
        object.__setattr__(self, "lock_mode", _normalize_string(
            self.lock_mode, label="lock_mode", max_length=40).lower())
        if self.lock_mode not in VALID_LOCK_MODES:
            raise ResourceLockError(f"unsupported lock_mode: {self.lock_mode}")
        object.__setattr__(self, "reason_code", _normalize_string(
            self.reason_code, label="reason_code", max_length=80).lower())
        object.__setattr__(self, "required_unlock_capability", _normalize_string(
            self.required_unlock_capability, label="required_unlock_capability", max_length=120))
        object.__setattr__(self, "required_readbacks", tuple(sorted(
            _normalize_string(r, label=f"required_readbacks[{i}]", max_length=80)
            for i, r in enumerate(self.required_readbacks)
        )))
        object.__setattr__(self, "owner_id", _normalize_string(
            self.owner_id, label="owner_id", max_length=120))
        object.__setattr__(self, "created_by_receipt", _normalize_sha64(
            self.created_by_receipt, label="created_by_receipt"))
        object.__setattr__(self, "created_at_revision", _normalize_string(
            self.created_at_revision, label="created_at_revision", max_length=120))
        object.__setattr__(self, "predecessor_hash", _normalize_optional_sha64(
            self.predecessor_hash, label="predecessor_hash"))
        object.__setattr__(self, "expires_at_version", _normalize_optional_sha64(
            self.expires_at_version, label="expires_at_version") if self.expires_at_version and self.expires_at_version != "0" * 64 else None)

        # Compute lock hash manually to avoid recursion
        body = {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "lock_mode": self.lock_mode,
            "reason_code": self.reason_code,
            "required_unlock_capability": self.required_unlock_capability,
            "required_readbacks": list(self.required_readbacks),
            "owner_id": self.owner_id,
            "created_by_receipt": self.created_by_receipt,
            "created_at_revision": self.created_at_revision,
            "predecessor_hash": self.predecessor_hash,
            "expires_at_version": self.expires_at_version,
            "lock_hash": "placeholder",
        }
        body["lock_hash"] = canonical_sha256(body)
        del body["lock_hash"]
        object.__setattr__(self, "lock_hash", canonical_sha256(body))

    def canonical_body(self) -> dict[str, Any]:
        """Return canonical dictionary representation."""
        return {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "lock_mode": self.lock_mode,
            "reason_code": self.reason_code,
            "required_unlock_capability": self.required_unlock_capability,
            "required_readbacks": list(self.required_readbacks),
            "owner_id": self.owner_id,
            "created_by_receipt": self.created_by_receipt,
            "created_at_revision": self.created_at_revision,
            "predecessor_hash": self.predecessor_hash,
            "expires_at_version": self.expires_at_version,
            "lock_hash": self.lock_hash,
        }

    def scopes_match(self, other_resource_type: str, other_resource_id: str) -> bool:
        """Check if this lock applies to a given resource scope."""
        return self.resource_type == other_resource_type and self.resource_id == other_resource_id

    def can_unlock_with(self, capability_id: str, readbacks: Sequence[str]) -> tuple[bool, str]:
        """Check if a capability and set of readbacks can release this lock.

        Returns (allowed, reason).
        """

        if capability_id != self.required_unlock_capability:
            return False, f"capability {capability_id} does not match required {self.required_unlock_capability}"

        missing_readbacks = set(self.required_readbacks) - set(readbacks)
        if missing_readbacks:
            return False, f"missing required readbacks: {sorted(missing_readbacks)}"

        return True, "unlock authorized"


def build_resource_lock(
    resource_type: str,
    resource_id: str,
    lock_mode: str,
    reason_code: str,
    required_unlock_capability: str,
    owner_id: str,
    created_by_receipt: str,
    created_at_revision: str,
    *,
    required_readbacks: Sequence[str] = (),
    predecessor_hash: str | None = None,
    expires_at_version: str | None = None,
) -> ResourceLock:
    """Build a validated ResourceLock from raw inputs."""

    return ResourceLock(
        resource_type=resource_type,
        resource_id=resource_id,
        lock_mode=lock_mode,
        reason_code=reason_code,
        required_unlock_capability=required_unlock_capability,
        required_readbacks=tuple(required_readbacks),
        owner_id=owner_id,
        created_by_receipt=created_by_receipt,
        created_at_revision=created_at_revision,
        predecessor_hash=predecessor_hash,
        expires_at_version=expires_at_version,
    )


@dataclass(frozen=True, slots=True)
class LockAcquisitionRequest:
    """Request to acquire a resource lock."""

    resource_type: str
    resource_id: str
    lock_mode: str
    reason_code: str
    required_unlock_capability: str
    required_readbacks: tuple[str, ...]
    owner_id: str
    created_by_receipt: str
    created_at_revision: str
    predecessor_hash: str | None
    expires_at_version: str | None


@dataclass(frozen=True, slots=True)
class LockReleaseRequest:
    """Request to release a resource lock."""

    resource_type: str
    resource_id: str
    lock_hash: str
    unlock_capability_id: str
    unlock_receipt_hash: str
    unlock_readbacks: tuple[str, ...]


def validate_lock_release(
    lock: ResourceLock,
    request: LockReleaseRequest,
) -> tuple[bool, str]:
    """Validate a lock release request against an existing lock.

    Returns (valid, reason).
    """

    # Check scope matches
    if not lock.scopes_match(request.resource_type, request.resource_id):
        return False, "resource scope mismatch"

    # Check lock hash matches
    if lock.lock_hash != request.lock_hash:
        return False, "lock hash mismatch"

    # Check unlock capability and readbacks
    return lock.can_unlock_with(request.unlock_capability_id, request.unlock_readbacks)


def check_resource_locked(
    locks: Sequence[ResourceLock],
    resource_type: str,
    resource_id: str,
    exclude_modes: frozenset[str] | None = None,
) -> tuple[bool, ResourceLock | None]:
    """Check if a resource has any active locks.

    Returns (is_locked, blocking_lock).
    """

    for lock in locks:
        if lock.scopes_match(resource_type, resource_id):
            if exclude_modes and lock.lock_mode in exclude_modes:
                continue
            return True, lock

    return False, None


__all__ = [
    "LockMode",
    "VALID_LOCK_MODES",
    "ResourceLockError",
    "ResourceLock",
    "LockAcquisitionRequest",
    "LockReleaseRequest",
    "build_resource_lock",
    "validate_lock_release",
    "check_resource_locked",
]
