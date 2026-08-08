"""Versioned resource contracts for atomic mutation control.

This module defines the core data structures for binding mutations to
specific resource versions, following the contracts from issue #1119.

Key concepts:
- VersionedResourceRef: Immutable reference to a specific resource version
- VersionedResource: A resource with version tracking
- MutationIntent: A planned mutation with bound base state
- ResourceScope: Owner/scope boundaries for lock and CAS checks

Referenced by:
    - Issue #1119: Atomic Versioned Mutation Control
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import os
from typing import Any, Final, Mapping, Literal

# Supported resource types
ResourceType = Literal[
    "agent_config",
    "capability_manifest",
    "tool_assignment",
    "policy_set",
    "integration_plan_state",
    "github_issue",
    "github_pr",
    "github_branch",
    "appdeploy_snapshot",
    "deployment_target",
    "database_migration",
    "runtime_config",
]

# Lock modes
LOCK_MODE_MUTATION_LOCKED: Final[str] = "mutation_locked"
LOCK_MODE_OWNER_LOCKED: Final[str] = "owner_locked"
LOCK_MODE_DEPLOYMENT_FREEZE: Final[str] = "deployment_freeze"
LOCK_MODE_INCIDENT_FREEZE: Final[str] = "incident_freeze"
LOCK_MODE_MIGRATION_FREEZE: Final[str] = "migration_freeze"
LOCK_MODE_READ_ONLY_MAINTENANCE: Final[str] = "read_only_maintenance"

LOCK_MODES: tuple[str, ...] = (
    LOCK_MODE_MUTATION_LOCKED,
    LOCK_MODE_OWNER_LOCKED,
    LOCK_MODE_DEPLOYMENT_FREEZE,
    LOCK_MODE_INCIDENT_FREEZE,
    LOCK_MODE_MIGRATION_FREEZE,
    LOCK_MODE_READ_ONLY_MAINTENANCE,
)


@dataclass(frozen=True)
class ResourceScope:
    """Ownership and scope boundaries for a resource.
    
    Used for cross-tenant, cross-owner, cross-repo, cross-workspace,
    and cross-environment isolation checks.
    """
    owner_id: str
    organization_id: str | None = None
    repository_id: str | None = None
    workspace_id: str | None = None
    environment_id: str | None = None

    def __post_init__(self) -> None:
        if not self.owner_id or not self.owner_id.strip():
            raise ValueError("owner_id is required")


@dataclass(frozen=True, slots=True)
class VersionedResourceRef:
    """Immutable reference to a specific resource at a specific version.
    
    This is the base state that a mutation intends to modify.
    """
    resource_type: ResourceType
    resource_id: str
    scope: ResourceScope
    version: str
    content_hash: str

    def __post_init__(self) -> None:
        if not self.resource_id or not self.resource_id.strip():
            raise ValueError("resource_id is required")
        if not self.version or not self.version.strip():
            raise ValueError("version is required")
        if not self.content_hash or not len(self.content_hash) == 64:
            raise ValueError("content_hash must be a 64-character hex string (SHA-256)")


@dataclass(frozen=True, slots=True)
class VersionedResource:
    """A mutable resource with version tracking.
    
    This represents the current state of a resource that can be read
    and updated through CAS operations.
    """
    ref: VersionedResourceRef
    payload: Mapping[str, Any]
    created_at: int
    updated_at: int

    @property
    def resource_type(self) -> ResourceType:
        return self.ref.resource_type

    @property
    def resource_id(self) -> str:
        return self.ref.resource_id

    @property
    def version(self) -> str:
        return self.ref.version

    @property
    def content_hash(self) -> str:
        return self.ref.content_hash

    @property
    def scope(self) -> ResourceScope:
        return self.ref.scope


@dataclass(frozen=True, slots=True)
class MutationIntent:
    """A planned mutation bound to a specific base state.
    
    This captures the intent to mutate a resource with a specific
    base version. The mutation will only succeed if the current
    head matches the bound base.
    """
    resource: VersionedResourceRef
    capability_id: str
    canonical_payload: Mapping[str, Any]
    payload_hash: str
    permission_receipt_hash: str
    intent_id: str = field(default_factory=lambda: hashlib.sha256(os.urandom(32)).hexdigest()[:16])
    created_at: int = field(default_factory=lambda: int(__import__("time").time()))

    def __post_init__(self) -> None:
        if not self.capability_id or not self.capability_id.strip():
            raise ValueError("capability_id is required")
        if not self.payload_hash or len(self.payload_hash) != 64:
            raise ValueError("payload_hash must be a 64-character hex string (SHA-256)")
        if not self.permission_receipt_hash or len(self.permission_receipt_hash) != 64:
            raise ValueError("permission_receipt_hash must be a 64-character hex string (SHA-256)")


@dataclass
class ResourceLock:
    """A lock on a resource that prevents mutations.
    
    Locks block mutations but do not block readback operations.
    They require explicit authorized unlock with a new receipt.
    """
    resource_type: ResourceType
    resource_id: str
    mode: str
    reason_code: str
    required_unlock_capability: str
    owner_id: str
    created_by_capability: str
    created_at_revision: str
    created_at: int = field(default_factory=lambda: int(__import__("time").time()))
    expires_at: int | None = None
    predecessor_hash: str | None = None
    lock_id: str = field(default_factory=lambda: hashlib.sha256(os.urandom(32)).hexdigest()[:16])
    scope: ResourceScope | None = None

    def __post_init__(self) -> None:
        if self.mode not in LOCK_MODES:
            raise ValueError(f"Invalid lock mode: {self.mode}")
        if not self.resource_id or not self.resource_id.strip():
            raise ValueError("resource_id is required")


@dataclass
class MutationPhase(Enum):
    """Phases in the mutation lifecycle for idempotency and crash recovery."""
    PREPARED = "prepared"
    LOCKED = "locked"
    APPLIED_UNVERIFIED = "applied_unverified"
    VERIFIED = "verified"
    CONFLICTED = "conflicted"
    BLOCKED = "blocked"
    INVALIDATED = "invalidated"


class MutationFailureCode(Enum):
    """Structured conflict error codes for mutation failures."""
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


@dataclass
class MutationConflict(Exception):
    """Raised when a CAS check fails due to stale base state."""
    code: MutationFailureCode
    expected_hash: str
    actual_hash: str
    conflicting_fields: tuple[str, ...] = ()
    lock_ref: str | None = None
    suggested_action: str | None = None

    def __init__(
        self,
        code: MutationFailureCode,
        expected_hash: str,
        actual_hash: str,
        conflicting_fields: tuple[str, ...] = (),
        lock_ref: str | None = None,
        suggested_action: str | None = None,
    ) -> None:
        super().__init__(f"{code.value}: expected {expected_hash[:16]}..., got {actual_hash[:16]}...")
        self.code = code
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash
        self.conflicting_fields = conflicting_fields
        self.lock_ref = lock_ref
        self.suggested_action = suggested_action

    def to_dict(self) -> dict[str, Any]:
        """Convert to a redacted dict suitable for API responses."""
        return {
            "code": self.code.value,
            "expected_hash_prefix": self.expected_hash[:16] + "...",
            "actual_hash_prefix": self.actual_hash[:16] + "...",
            "conflicting_fields": list(self.conflicting_fields),
            "lock_ref": self.lock_ref,
            "suggested_action": self.suggested_action,
        }


class ResourceLockError(Exception):
    """Raised when a mutation is blocked by a resource lock."""
    def __init__(
        self,
        resource_type: ResourceType,
        resource_id: str,
        lock_mode: str,
        reason_code: str,
        required_capability: str,
        lock_id: str | None = None,
    ) -> None:
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.lock_mode = lock_mode
        self.reason_code = reason_code
        self.required_capability = required_capability
        self.lock_id = lock_id
        super().__init__(
            f"Resource {resource_type}/{resource_id} is locked ({lock_mode}): "
            f"reason={reason_code}, requires={required_capability}"
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to a redacted dict suitable for API responses."""
        return {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "lock_mode": self.lock_mode,
            "reason_code": self.reason_code,
            "required_capability": self.required_capability,
            "lock_id": self.lock_id,
        }


# Fields that are never safe to auto-merge
PROTECTED_FIELDS: frozenset[str] = frozenset({
    "permissions",
    "owner_id",
    "tenant_id",
    "organization_id",
    "repository_id",
    "workspace_id",
    "environment_id",
    "credentials",
    "credential_identity",
    "policy_actions",
    "capability_classes",
    "deployment_target",
    "migration_owner",
    "continuity_ledger",
    "secret",
    "api_key",
    "private_key",
    "token",
})


def verify_scope_isolation(base_scope: ResourceScope, head_scope: ResourceScope) -> bool:
    """Verify that two resource scopes maintain proper isolation boundaries."""
    if base_scope.owner_id != head_scope.owner_id:
        return False
    if base_scope.organization_id != head_scope.organization_id:
        return False
    return True
