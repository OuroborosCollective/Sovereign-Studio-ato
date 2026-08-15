"""Pure fail-closed contract core for Observed Tool Behavior Attestation (OTBA).

This module owns the deterministic ``ToolBehaviorContract`` schema: canonical
serialization, hash formation and validation rules. It performs no execution,
sandboxing, registry mutation, persistence, network I/O or LLM decision. Callers
must supply independently collected, revision- and identity-bound evidence.

This lane claims no real runtime attestation. It only lets a caller deterministically
bind a declared tool behavior contract to an immutable, tamper-sensitive hash.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import json
import re
import unicodedata
from typing import Any, Mapping, Sequence


_SCHEMA_CONTRACT = "sovereign.tool-behavior-contract.v1"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
# A content-addressable digest of the form ``algo:hex`` (OCI image digest) or a
# bare lowercase SHA-256. Registry digest formats are intentionally narrow.
_DIGEST = re.compile(r"^(?:sha256:[0-9a-f]{64}|[0-9a-f]{64})$")
_TOOL_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,254}$")
_EXECUTION_KINDS = frozenset({"LOCAL_OCI", "HOST_BROKER", "REMOTE_MCP"})
_EFFECT_CLASSES = frozenset({"READ_ONLY", "WORKSPACE_WRITE", "EXTERNAL_WRITE"})


class ToolBehaviorContractError(ValueError):
    """Raised when a caller crosses an OTBA contract truth-boundary invariant."""


def _normalize_text(value: Any, *, field: str) -> str:
    """Normalize a free-text identity field: NFC + strip, reject empty / NUL."""
    if not isinstance(value, str):
        raise ToolBehaviorContractError(f"{field} must be a string")
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized or "\x00" in normalized:
        raise ToolBehaviorContractError(f"{field} must be non-empty and NUL-free")
    return normalized


def _tool_id(value: Any) -> str:
    normalized = _normalize_text(value, field="tool_id").lower()
    if not _TOOL_ID.fullmatch(normalized):
        raise ToolBehaviorContractError("tool_id must be a canonical identifier")
    return normalized


def _sha40(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise ToolBehaviorContractError(f"{field} must be a lowercase Git SHA")
    normalized = value.strip().lower()
    if not _SHA40.fullmatch(normalized):
        raise ToolBehaviorContractError(f"{field} must be a lowercase 40-char Git SHA")
    return normalized


def _sha256(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise ToolBehaviorContractError(f"{field} must be a lowercase SHA-256")
    normalized = value.strip().lower()
    if not _SHA256.fullmatch(normalized):
        raise ToolBehaviorContractError(f"{field} must be a lowercase 64-char SHA-256")
    return normalized


def _digest_or_none(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ToolBehaviorContractError(f"{field} must be a digest string or null")
    normalized = unicodedata.normalize("NFC", value).strip().lower()
    if not normalized:
        raise ToolBehaviorContractError(f"{field} must be non-empty or null")
    if not _DIGEST.fullmatch(normalized):
        raise ToolBehaviorContractError(
            f"{field} must be 'sha256:<64 hex>' or a bare 64-char lowercase hex digest"
        )
    return normalized


def _kind(value: Any, *, field: str, allowed: frozenset[str]) -> str:
    if not isinstance(value, str):
        raise ToolBehaviorContractError(f"{field} must be one of {sorted(allowed)}")
    normalized = value.strip()
    if normalized not in allowed:
        raise ToolBehaviorContractError(f"{field} must be one of {sorted(allowed)}")
    return normalized


def _non_negative_int(value: Any, *, field: str) -> int:
    # bool is a subclass of int; reject it explicitly so True/False cannot pose as limits.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolBehaviorContractError(f"{field} must be a non-negative integer")
    if value < 0:
        raise ToolBehaviorContractError(f"{field} must be non-negative")
    return value


def _normalize_path(value: Any, *, field: str) -> str:
    """Normalize a declared/observed path: NFC, strip, reject NUL, traversal and empty segments."""
    normalized = _normalize_text(value, field=field)
    if "\x00" in normalized:
        raise ToolBehaviorContractError(f"{field} contains NUL byte")
    if "\\" in normalized:
        raise ToolBehaviorContractError(f"{field} must not use backslash path separators")
    if normalized in {".", ".."}:
        raise ToolBehaviorContractError(f"{field} must not be a bare traversal segment")
    # Reject interior empty segments ('//', '/a//b'). A single leading empty segment
    # is the legitimate absolute-path marker and must remain allowed.
    segments = normalized.split("/")
    interior = segments[1:] if segments and segments[0] == "" else segments
    if any(seg == "" for seg in interior):
        raise ToolBehaviorContractError(f"{field} must not contain empty path segments")
    if any(seg == ".." for seg in segments):
        raise ToolBehaviorContractError(f"{field} must not contain '..' traversal segments")
    return normalized


def _normalize_path_tuple(value: Any, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        items: Sequence[str] = (value,)
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        items = value
    else:
        raise ToolBehaviorContractError(f"{field} must be a list of path strings")
    normalized = tuple(sorted({_normalize_path(item, field=field) for item in items}))
    return normalized


def _normalize_target(value: Any, *, field: str) -> str:
    """Normalize a network target: NFC, strip, lowercase, reject NUL / control chars."""
    if not isinstance(value, str):
        raise ToolBehaviorContractError(f"{field} must be a string")
    normalized = unicodedata.normalize("NFC", value).strip().lower()
    if not normalized or "\x00" in normalized or any(ord(ch) < 0x20 for ch in normalized):
        raise ToolBehaviorContractError(f"{field} must be a non-empty control-free target")
    return normalized


def _normalize_target_tuple(value: Any, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        items: Sequence[str] = (value,)
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        items = value
    else:
        raise ToolBehaviorContractError(f"{field} must be a list of target strings")
    normalized = tuple(sorted({_normalize_target(item, field=field) for item in items}))
    return normalized


def _normalize_exec_tuple(value: Any, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        items: Sequence[str] = (value,)
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        items = value
    else:
        raise ToolBehaviorContractError(f"{field} must be a list of exec strings")
    normalized = tuple(sorted({_normalize_text(item, field=field) for item in items}))
    return normalized


def canonical_json(value: Any) -> str:
    """Encode only canonical JSON values suitable for identity hashing.

    Strings are NFC-normalized; floats, non-string keys, bytes and unknown
    types are rejected so identity fields can never carry ambiguous encodings.
    """

    def validate(item: Any, path: str = "$") -> None:
        if item is None or isinstance(item, bool) or isinstance(item, int):
            return
        if isinstance(item, str):
            return
        if isinstance(item, float):
            raise ToolBehaviorContractError(f"floating-point values are forbidden at {path}")
        if isinstance(item, Mapping):
            for key, nested in item.items():
                if not isinstance(key, str):
                    raise ToolBehaviorContractError(f"non-string key is forbidden at {path}")
                validate(nested, f"{path}.{key}")
            return
        if isinstance(item, Sequence) and not isinstance(item, (bytes, bytearray, str)):
            for index, nested in enumerate(item):
                validate(nested, f"{path}[{index}]")
            return
        raise ToolBehaviorContractError(f"unsupported canonical value at {path}")

    validate(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ToolBehaviorContract:
    """Immutable, revision- and identity-bound declared tool behavior contract."""

    schema_version: str
    tool_id: str
    execution_kind: str
    repository_revision: str
    tool_registry_revision: str
    image_digest: str | None
    effect_class: str
    allowed_exec: tuple[str, ...]
    allowed_read_paths: tuple[str, ...]
    allowed_write_paths: tuple[str, ...]
    allowed_network_targets: tuple[str, ...]
    network_required: bool
    max_wall_time_ms: int
    max_memory_bytes: int
    contract_sha256: str = field(default="")

    def __post_init__(self) -> None:
        if self.schema_version != _SCHEMA_CONTRACT:
            raise ToolBehaviorContractError("unsupported contract schema_version")
        object.__setattr__(self, "tool_id", _tool_id(self.tool_id))
        object.__setattr__(self, "execution_kind", _kind(self.execution_kind, field="execution_kind", allowed=_EXECUTION_KINDS))
        object.__setattr__(self, "repository_revision", _sha40(self.repository_revision, field="repository_revision"))
        object.__setattr__(self, "tool_registry_revision", _sha40(self.tool_registry_revision, field="tool_registry_revision"))
        object.__setattr__(self, "image_digest", _digest_or_none(self.image_digest, field="image_digest"))
        object.__setattr__(self, "effect_class", _kind(self.effect_class, field="effect_class", allowed=_EFFECT_CLASSES))
        allowed_exec = _normalize_exec_tuple(self.allowed_exec, field="allowed_exec")
        allowed_read = _normalize_path_tuple(self.allowed_read_paths, field="allowed_read_paths")
        allowed_write = _normalize_path_tuple(self.allowed_write_paths, field="allowed_write_paths")
        allowed_network = _normalize_target_tuple(self.allowed_network_targets, field="allowed_network_targets")
        if not allowed_exec:
            raise ToolBehaviorContractError("allowed_exec must be non-empty")
        object.__setattr__(self, "allowed_exec", allowed_exec)
        object.__setattr__(self, "allowed_read_paths", allowed_read)
        object.__setattr__(self, "allowed_write_paths", allowed_write)
        object.__setattr__(self, "allowed_network_targets", allowed_network)
        object.__setattr__(self, "network_required", bool(self.network_required))
        object.__setattr__(self, "max_wall_time_ms", _non_negative_int(self.max_wall_time_ms, field="max_wall_time_ms"))
        object.__setattr__(self, "max_memory_bytes", _non_negative_int(self.max_memory_bytes, field="max_memory_bytes"))
        if self.network_required and not allowed_network:
            raise ToolBehaviorContractError("network_required contracts must declare allowed_network_targets")
        if self.effect_class == "READ_ONLY" and allowed_write:
            raise ToolBehaviorContractError("READ_ONLY contracts must not declare allowed_write_paths")
        # Only a locally containerized tool carries an immutable image identity. A
        # remote MCP server has no local OCI image, so binding a digest there would
        # be a false identity claim.
        if self.execution_kind == "LOCAL_OCI" and self.image_digest is None:
            raise ToolBehaviorContractError("LOCAL_OCI contracts must bind an image_digest")
        if self.execution_kind == "REMOTE_MCP" and self.image_digest is not None:
            raise ToolBehaviorContractError("REMOTE_MCP contracts must not bind an image_digest")
        if self.effect_class == "EXTERNAL_WRITE" and not self.network_required:
            raise ToolBehaviorContractError("EXTERNAL_WRITE contracts must declare network_required")
        # The contract hash is derived from its canonical record rather than stored
        # verbatim from the caller. A self-referential stored hash would be circular
        # and trivially spoofable; deriving it from the canonical record guarantees it
        # is tamper-sensitive and reproducible.
        object.__setattr__(self, "contract_sha256", canonical_sha256(self._identity_record()))

    def _identity_record(self) -> dict[str, Any]:
        # Fields that define the contract identity. Excludes the derived
        # contract_sha256 itself to avoid a self-referential hash.
        return {
            "schemaVersion": self.schema_version,
            "toolId": self.tool_id,
            "executionKind": self.execution_kind,
            "repositoryRevision": self.repository_revision,
            "toolRegistryRevision": self.tool_registry_revision,
            "imageDigest": self.image_digest,
            "effectClass": self.effect_class,
            "allowedExec": list(self.allowed_exec),
            "allowedReadPaths": list(self.allowed_read_paths),
            "allowedWritePaths": list(self.allowed_write_paths),
            "allowedNetworkTargets": list(self.allowed_network_targets),
            "networkRequired": self.network_required,
            "maxWallTimeMs": self.max_wall_time_ms,
            "maxMemoryBytes": self.max_memory_bytes,
        }

    def canonical_record(self) -> dict[str, Any]:
        """Canonical, hash-stable record including the derived contract hash."""
        record = self._identity_record()
        record["contractSha256"] = self.contract_sha256
        return record

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ToolBehaviorContract":
        if not isinstance(value, Mapping):
            raise ToolBehaviorContractError("contract must be an object")
        return cls(
            schema_version=value.get("schemaVersion"),
            tool_id=value.get("toolId"),
            execution_kind=value.get("executionKind"),
            repository_revision=value.get("repositoryRevision"),
            tool_registry_revision=value.get("toolRegistryRevision"),
            image_digest=value.get("imageDigest"),
            effect_class=value.get("effectClass"),
            allowed_exec=tuple(value.get("allowedExec") or ()),
            allowed_read_paths=tuple(value.get("allowedReadPaths") or ()),
            allowed_write_paths=tuple(value.get("allowedWritePaths") or ()),
            allowed_network_targets=tuple(value.get("allowedNetworkTargets") or ()),
            network_required=bool(value.get("networkRequired")),
            max_wall_time_ms=value.get("maxWallTimeMs", 0),
            max_memory_bytes=value.get("maxMemoryBytes", 0),
        )

    def with_revision(self, *, repository_revision: str, tool_registry_revision: str) -> "ToolBehaviorContract":
        """Return a copy of this contract re-bound to new revisions; the hash is recomputed."""
        return replace(
            self,
            repository_revision=repository_revision,
            tool_registry_revision=tool_registry_revision,
            contract_sha256="",
        )


__all__ = [
    "ToolBehaviorContract",
    "ToolBehaviorContractError",
    "canonical_json",
    "canonical_sha256",
]
