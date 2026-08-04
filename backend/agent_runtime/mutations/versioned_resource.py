"""Versioned Resource and Mutation Intent contracts for atomic versioned mutation control.

This module provides the foundational data classes for binding mutations to specific
resource versions. Every mutation intent must reference a concrete base version that
was read and used to construct the mutation payload.

The module performs no network, database, filesystem, clock or random access. It only
validates and canonicalizes structured data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Final, Mapping, Sequence

from ..agent_run_receipts import (
    ReceiptContractError,
    canonical_sha256 as _canonical_sha256,
    canonical_value as _canonical_value,
)


_SCHEMA_VERSION: Final[str] = "sovereign.versioned-resource.v1"
_SHA64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_CANONICALIZATION: Final[str] = "utf8-nfc-json-sorted-no-floats-v1"

# Supported resource types for versioned mutation control
RESOURCE_TYPES: tuple[str, ...] = (
    "agent_config",
    "capability_manifest",
    "tool_assignment",
    "policy_set",
    "integration_plan_state",
    "github_issue",
    "github_pr_metadata",
    "repository_branch",
    "appdeploy_snapshot",
    "deployment_target",
    "database_migration_ownership",
)


class VersionedResourceError(ValueError):
    """A versioned resource input violated a deterministic or safety invariant."""


def _normalize_string(value: str, *, label: str, max_length: int = 240) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise VersionedResourceError(f"{label} must be non-empty")
    if len(normalized) > max_length:
        raise VersionedResourceError(f"{label} exceeds maximum length of {max_length}")
    return normalized


def _normalize_optional_string(value: str | None, *, label: str, max_length: int = 240) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if len(normalized) > max_length:
        raise VersionedResourceError(f"{label} exceeds maximum length of {max_length}")
    return normalized


def _normalize_sha64(value: str, *, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _SHA64.fullmatch(normalized):
        raise VersionedResourceError(f"{label} must be a lowercase SHA-256")
    return normalized


def canonical_value(value: Any, *, path: str = "$") -> Any:
    """Canonicalize a value for hashing - delegates to receipt contract."""
    try:
        return _canonical_value(value, path=path)
    except ReceiptContractError as exc:
        raise VersionedResourceError(str(exc)) from exc


def canonical_bytes(value: Any) -> bytes:
    """Return canonical JSON bytes for a value."""
    normalized = canonical_value(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    """Compute SHA-256 hash of canonical form."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class VersionedResourceRef:
    """Immutable reference to a versioned resource with content hash.

    This is the base state that a mutation intent binds to. The mutation
    can only proceed if the current head matches this base reference.
    """

    resource_type: str
    resource_id: str
    owner_id: str
    organization_id: str | None
    repository_id: str | None
    workspace_id: str | None
    environment_id: str | None
    version: str
    content_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "resource_type", _normalize_string(
            self.resource_type, label="resource_type", max_length=60).lower())
        if self.resource_type not in RESOURCE_TYPES:
            raise VersionedResourceError(
                f"unsupported resource_type: {self.resource_type}; "
                f"allowed: {RESOURCE_TYPES}"
            )
        object.__setattr__(self, "resource_id", _normalize_string(
            self.resource_id, label="resource_id", max_length=120))
        object.__setattr__(self, "owner_id", _normalize_string(
            self.owner_id, label="owner_id", max_length=120))
        object.__setattr__(self, "organization_id", _normalize_optional_string(
            self.organization_id, label="organization_id", max_length=120))
        object.__setattr__(self, "repository_id", _normalize_optional_string(
            self.repository_id, label="repository_id", max_length=120))
        object.__setattr__(self, "workspace_id", _normalize_optional_string(
            self.workspace_id, label="workspace_id", max_length=120))
        object.__setattr__(self, "environment_id", _normalize_optional_string(
            self.environment_id, label="environment_id", max_length=120))
        object.__setattr__(self, "version", _normalize_string(
            self.version, label="version", max_length=120))
        object.__setattr__(self, "content_hash", _normalize_sha64(
            self.content_hash, label="content_hash"))

    def canonical_body(self) -> dict[str, Any]:
        """Return canonical dictionary representation."""
        return {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "owner_id": self.owner_id,
            "organization_id": self.organization_id,
            "repository_id": self.repository_id,
            "workspace_id": self.workspace_id,
            "environment_id": self.environment_id,
            "version": self.version,
            "content_hash": self.content_hash,
        }

    @property
    def resource_ref_hash(self) -> str:
        """Compute deterministic hash of this resource reference."""
        return canonical_sha256(self.canonical_body())


@dataclass(frozen=True, slots=True)
class MutationIntent:
    """Immutable intent to mutate a versioned resource with bound base state.

    The intent captures what was read (base resource), what will be changed
    (canonical payload), and proof of authorization (permission receipt hash).
    """

    resource: VersionedResourceRef
    capability_id: str
    canonical_payload: Mapping[str, Any]
    payload_hash: str
    permission_receipt_hash: str
    idempotency_key: str
    expected_effect_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "capability_id", _normalize_string(
            self.capability_id, label="capability_id", max_length=120))
        # canonical_payload must be a Mapping
        if not isinstance(self.canonical_payload, Mapping):
            raise VersionedResourceError("canonical_payload must be a Mapping")
        object.__setattr__(self, "payload_hash", _normalize_sha64(
            self.payload_hash, label="payload_hash"))
        object.__setattr__(self, "permission_receipt_hash", _normalize_sha64(
            self.permission_receipt_hash, label="permission_receipt_hash"))
        object.__setattr__(self, "idempotency_key", _normalize_string(
            self.idempotency_key, label="idempotency_key", max_length=240))
        object.__setattr__(self, "expected_effect_hash", _normalize_sha64(
            self.expected_effect_hash, label="expected_effect_hash"))

    def canonical_body(self) -> dict[str, Any]:
        """Return canonical dictionary representation."""
        return {
            "resource": self.resource.canonical_body(),
            "capability_id": self.capability_id,
            "canonical_payload": dict(self.canonical_payload),
            "payload_hash": self.payload_hash,
            "permission_receipt_hash": self.permission_receipt_hash,
            "idempotency_key": self.idempotency_key,
            "expected_effect_hash": self.expected_effect_hash,
        }

    @property
    def intent_hash(self) -> str:
        """Compute deterministic hash of this mutation intent."""
        return canonical_sha256(self.canonical_body())


def build_versioned_resource_ref(
    resource_type: str,
    resource_id: str,
    owner_id: str,
    *,
    organization_id: str | None = None,
    repository_id: str | None = None,
    workspace_id: str | None = None,
    environment_id: str | None = None,
    version: str,
    content_hash: str,
) -> VersionedResourceRef:
    """Build a validated VersionedResourceRef from raw inputs."""

    return VersionedResourceRef(
        resource_type=resource_type,
        resource_id=resource_id,
        owner_id=owner_id,
        organization_id=organization_id,
        repository_id=repository_id,
        workspace_id=workspace_id,
        environment_id=environment_id,
        version=version,
        content_hash=content_hash,
    )


def build_mutation_intent(
    resource: VersionedResourceRef,
    capability_id: str,
    canonical_payload: Mapping[str, Any],
    permission_receipt_hash: str,
    idempotency_key: str,
    expected_effect_hash: str,
) -> MutationIntent:
    """Build a validated MutationIntent with computed payload hash."""

    # Compute payload hash from canonical form
    payload_hash = canonical_sha256(canonical_payload)

    return MutationIntent(
        resource=resource,
        capability_id=capability_id,
        canonical_payload=canonical_payload,
        payload_hash=payload_hash,
        permission_receipt_hash=permission_receipt_hash,
        idempotency_key=idempotency_key,
        expected_effect_hash=expected_effect_hash,
    )


def verify_intent_integrity(intent: MutationIntent) -> bool:
    """Verify that the intent's payload_hash matches the canonical_payload."""
    expected = canonical_sha256(intent.canonical_payload)
    return expected == intent.payload_hash


__all__ = [
    "RESOURCE_TYPES",
    "VersionedResourceError",
    "VersionedResourceRef",
    "MutationIntent",
    "build_versioned_resource_ref",
    "build_mutation_intent",
    "verify_intent_integrity",
    "canonical_sha256",
    "canonical_value",
    "canonical_bytes",
]
