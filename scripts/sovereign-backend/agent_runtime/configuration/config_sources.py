"""Configuration Provenance - source contracts and types.

Mirrors ``src/runtime/config/configSources.ts``. Each source binds id,
revision/digest, content-hash, schema-hash and priority. Secrets are projected
only as a redacted identity (``RedactedSecret``) - never raw material.

Resolution order (lowest priority first, later wins unless explicitly deleted):

    compiled defaults
    -> immutable image manifest
    -> revision-bound deployment config
    -> environment projection
    -> explicitly approved runtime overlay
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional


ConfigSourceKind = Literal[
    "compiled-defaults",
    "image-manifest",
    "deployment-config",
    "environment-projection",
    "approved-runtime-overlay",
]

SOURCE_PRIORITY: dict[ConfigSourceKind, int] = {
    "compiled-defaults": 0,
    "image-manifest": 10,
    "deployment-config": 20,
    "environment-projection": 30,
    "approved-runtime-overlay": 40,
}

SOURCE_ORDER: list[ConfigSourceKind] = sorted(
    SOURCE_PRIORITY.keys(), key=lambda k: SOURCE_PRIORITY[k]
)

ALLOWED_SOURCE_KINDS: frozenset[str] = frozenset(SOURCE_PRIORITY.keys())


@dataclass(frozen=True)
class RedactedSecret:
    """A non-reversible redacted identity for a secret-shaped value."""

    redacted_id: str
    kind: str = "secret"


@dataclass(frozen=True)
class RemoteBinding:
    origin: str
    digest: str
    signature_hash: str


@dataclass(frozen=True)
class ConfigSourceContract:
    id: str
    kind: ConfigSourceKind
    revision: str
    content_hash: str
    schema_hash: str
    priority: int
    values: dict[str, Any]
    remote: Optional[RemoteBinding] = None


@dataclass(frozen=True)
class SourceHashRecord:
    id: str
    kind: ConfigSourceKind
    revision: str
    content_hash: str
    schema_hash: str
    priority: int
    remote_origin: Optional[str] = None
    remote_digest: Optional[str] = None


DriftKind = Literal[
    "schema-drift", "content-drift", "source-order-drift", "remote-binding-drift"
]


@dataclass(frozen=True)
class ConfigDriftRecord:
    kind: DriftKind
    detail: str
    expected_hash: Optional[str]
    actual_hash: str


ResolutionStatus = Literal["RESOLVED", "BLOCKED", "CONTRADICTED", "DEGRADED"]


@dataclass(frozen=True)
class ConfigResolutionContract:
    status: ResolutionStatus
    source_order: tuple[ConfigSourceKind, ...]
    source_hashes: tuple[SourceHashRecord, ...]
    schema_hash: str
    resolved_hash: str
    resolved: dict[str, Any]
    drift: Optional[ConfigDriftRecord]
    errors: tuple[str, ...]


def is_allowed_source_kind(kind: str) -> bool:
    return kind in ALLOWED_SOURCE_KINDS


def default_priority_for(kind: ConfigSourceKind) -> int:
    return SOURCE_PRIORITY[kind]


@dataclass(frozen=True)
class ConfigSchemaField:
    name: str
    kind: str


@dataclass(frozen=True)
class ConfigSchemaDescriptor:
    id: str
    fields: tuple[ConfigSchemaField, ...] = field(default_factory=tuple)


__all__ = [
    "ConfigSourceKind",
    "SOURCE_PRIORITY",
    "SOURCE_ORDER",
    "ALLOWED_SOURCE_KINDS",
    "RedactedSecret",
    "RemoteBinding",
    "ConfigSourceContract",
    "SourceHashRecord",
    "ConfigDriftRecord",
    "DriftKind",
    "ConfigResolutionContract",
    "ResolutionStatus",
    "ConfigSchemaField",
    "ConfigSchemaDescriptor",
    "is_allowed_source_kind",
    "default_priority_for",
]
