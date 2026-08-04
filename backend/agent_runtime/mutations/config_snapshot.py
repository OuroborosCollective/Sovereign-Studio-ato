"""Canonical Configuration Snapshot compiler for security-relevant config hashing.

This module compiles agent, capability, policy, and tool configurations into
deterministic, sorted, SHA-256 hashed snapshots. Only behavior-relevant fields
are included; secret material is excluded and replaced with redacted identity.

The module performs no network, database, filesystem, clock or random access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Final, Mapping, Sequence

from .versioned_resource import canonical_sha256 as _canonical_sha256


_SCHEMA_VERSION: Final[str] = "sovereign.agent-config-snapshot.v1"
_SHA64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")

# Secret key markers that indicate fields to redact
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
)

# Fields that are safe to include as booleans even if secret-shaped
_SECRET_SAFE_BOOLEAN_KEYS: Final[frozenset[str]] = frozenset({
    "secretvaluesreturned",
    "secret_values_returned",
    "rawsecretspersisted",
    "raw_secrets_persisted",
})


class ConfigSnapshotError(ValueError):
    """A config snapshot input violated a deterministic or safety invariant."""


def _normalize_string(value: str, *, label: str, max_length: int = 240) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ConfigSnapshotError(f"{label} must be non-empty")
    if len(normalized) > max_length:
        raise ConfigSnapshotError(f"{label} exceeds maximum length of {max_length}")
    return normalized


def _normalize_sha64(value: str, *, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _SHA64.fullmatch(normalized):
        raise ConfigSnapshotError(f"{label} must be a lowercase SHA-256")
    return normalized


def _is_secret_field(key: str) -> bool:
    """Check if a field name suggests it contains secrets."""
    folded = key.casefold()
    return any(marker in folded for marker in _SECRET_KEY_MARKERS)


def _is_secret_safe_boolean(key: str, value: Any) -> bool:
    """Check if a key-value pair is a safe boolean despite secret naming."""
    return key.casefold() in _SECRET_SAFE_BOOLEAN_KEYS and isinstance(value, bool)


def canonical_config_value(value: Any, *, path: str = "$") -> Any:
    """Canonicalize a config value, redacting secrets.

    This recursively processes a configuration structure, replacing secret-shaped
    fields with their hash while preserving the structure for comparison.
    """

    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        raise ConfigSnapshotError(f"floating-point value is forbidden at {path}")
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for raw_key, item in value.items():
            if not isinstance(raw_key, str):
                raise ConfigSnapshotError(f"non-string object key is forbidden at {path}")
            key = raw_key
            if _is_secret_field(key) and not _is_secret_safe_boolean(key, item):
                # Redact secret fields - include hash but not value
                output[key] = {"redacted": True, "hash": hashlib.sha256(str(item).encode()).hexdigest()[:16]}
            else:
                output[key] = canonical_config_value(item, path=f"{path}.{key}")
        return output
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [canonical_config_value(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    raise ConfigSnapshotError(f"unsupported canonical type {type(value).__name__} at {path}")


def canonical_config_bytes(value: Any) -> bytes:
    """Return canonical JSON bytes for a config value."""
    normalized = canonical_config_value(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_config_sha256(value: Any) -> str:
    """Compute SHA-256 hash of canonical config form."""
    return hashlib.sha256(canonical_config_bytes(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class AgentConfigSnapshot:
    """Canonical snapshot of agent configuration for fingerprinting.

    This captures all behavior-relevant fields from an agent configuration
    in a deterministic, hashable form. Secret material is redacted.
    """

    schema_version: str
    agent_id: str
    owner_id: str
    repository_id: str | None
    environment_id: str
    model_route: Mapping[str, Any]
    credential_identity: Mapping[str, Any] | None
    capability_manifest_hash: str
    policy_set_hash: str
    prompt_layer_hashes: tuple[str, ...]
    tool_contracts: tuple[Mapping[str, Any], ...]
    limits_hash: str
    snapshot_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.schema_version != _SCHEMA_VERSION:
            raise ConfigSnapshotError(f"unsupported schema version: {self.schema_version}")
        object.__setattr__(self, "agent_id", _normalize_string(self.agent_id, label="agent_id", max_length=120))
        object.__setattr__(self, "owner_id", _normalize_string(self.owner_id, label="owner_id", max_length=120))
        if self.repository_id is not None:
            object.__setattr__(self, "repository_id", _normalize_string(self.repository_id, label="repository_id", max_length=120))
        object.__setattr__(self, "environment_id", _normalize_string(self.environment_id, label="environment_id", max_length=120))
        if not isinstance(self.model_route, Mapping):
            raise ConfigSnapshotError("model_route must be a Mapping")
        object.__setattr__(self, "capability_manifest_hash", _normalize_sha64(
            self.capability_manifest_hash, label="capability_manifest_hash"))
        object.__setattr__(self, "policy_set_hash", _normalize_sha64(
            self.policy_set_hash, label="policy_set_hash"))
        object.__setattr__(self, "prompt_layer_hashes", tuple(sorted(
            _normalize_sha64(h, label=f"prompt_layer_hashes[{i}]")
            for i, h in enumerate(self.prompt_layer_hashes)
        )))
        tool_contracts = []
        for i, tc in enumerate(self.tool_contracts):
            if not isinstance(tc, Mapping):
                raise ConfigSnapshotError(f"tool_contracts[{i}] must be a Mapping")
            tool_contracts.append(dict(tc))
        object.__setattr__(self, "tool_contracts", tuple(tool_contracts))
        object.__setattr__(self, "limits_hash", _normalize_sha64(
            self.limits_hash, label="limits_hash"))

        # Compute snapshot hash from canonical body - build it manually to avoid recursion
        body = {
            "schema_version": self.schema_version,
            "agent_id": self.agent_id,
            "owner_id": self.owner_id,
            "repository_id": self.repository_id,
            "environment_id": self.environment_id,
            "model_route": dict(self.model_route),
            "credential_identity": dict(self.credential_identity) if self.credential_identity else None,
            "capability_manifest_hash": self.capability_manifest_hash,
            "policy_set_hash": self.policy_set_hash,
            "prompt_layer_hashes": list(self.prompt_layer_hashes),
            "tool_contracts": list(self.tool_contracts),
            "limits_hash": self.limits_hash,
            "snapshot_hash": "placeholder",  # Temporary to avoid recursion
        }
        body["snapshot_hash"] = canonical_config_sha256(body)
        del body["snapshot_hash"]  # Remove before final hash
        object.__setattr__(self, "snapshot_hash", canonical_config_sha256(body))

    def canonical_body(self) -> dict[str, Any]:
        """Return canonical dictionary representation."""
        return {
            "schema_version": self.schema_version,
            "agent_id": self.agent_id,
            "owner_id": self.owner_id,
            "repository_id": self.repository_id,
            "environment_id": self.environment_id,
            "model_route": dict(self.model_route),
            "credential_identity": dict(self.credential_identity) if self.credential_identity else None,
            "capability_manifest_hash": self.capability_manifest_hash,
            "policy_set_hash": self.policy_set_hash,
            "prompt_layer_hashes": list(self.prompt_layer_hashes),
            "tool_contracts": list(self.tool_contracts),
            "limits_hash": self.limits_hash,
            "snapshot_hash": self.snapshot_hash,
        }


def build_agent_config_snapshot(
    agent_id: str,
    owner_id: str,
    environment_id: str,
    model_route: Mapping[str, Any],
    capability_manifest_hash: str,
    policy_set_hash: str,
    prompt_layer_hashes: Sequence[str],
    tool_contracts: Sequence[Mapping[str, Any]],
    limits_hash: str,
    *,
    repository_id: str | None = None,
    credential_identity: Mapping[str, Any] | None = None,
) -> AgentConfigSnapshot:
    """Build a validated AgentConfigSnapshot from raw inputs."""

    return AgentConfigSnapshot(
        schema_version=_SCHEMA_VERSION,
        agent_id=agent_id,
        owner_id=owner_id,
        repository_id=repository_id,
        environment_id=environment_id,
        model_route=model_route,
        credential_identity=credential_identity,
        capability_manifest_hash=capability_manifest_hash,
        policy_set_hash=policy_set_hash,
        prompt_layer_hashes=tuple(prompt_layer_hashes),
        tool_contracts=tuple(tool_contracts),
        limits_hash=limits_hash,
    )


def compile_config_fingerprint(
    agent_config: Mapping[str, Any],
    *,
    agent_id: str,
    owner_id: str,
    repository_id: str | None = None,
    environment_id: str = "default",
) -> AgentConfigSnapshot:
    """Compile an agent config mapping into a canonical snapshot.

    This extracts relevant fields from a raw agent config and builds
    a deterministic snapshot suitable for change detection.
    """

    # Extract model route
    model_route = dict(agent_config.get("model_route") or agent_config.get("modelRoute") or {})
    if not model_route:
        model_route = {
            "provider": str(agent_config.get("provider", "")),
            "model": str(agent_config.get("model", "")),
            "route_revision": str(agent_config.get("route_revision", "unknown")),
        }

    # Extract capability manifest hash
    capability_manifest_hash = str(agent_config.get("capability_manifest_hash") or agent_config.get("capabilityManifestHash", ""))
    if not _SHA64.fullmatch(capability_manifest_hash):
        capability_manifest_hash = canonical_config_sha256(agent_config.get("capability_manifest", agent_config.get("capabilityManifest", {})))

    # Extract policy set hash
    policy_set_hash = str(agent_config.get("policy_set_hash") or agent_config.get("policySetHash", ""))
    if not _SHA64.fullmatch(policy_set_hash):
        policy_set_hash = canonical_config_sha256(agent_config.get("policy_set", agent_config.get("policySet", {})))

    # Extract prompt layer hashes
    prompt_layer_hashes = agent_config.get("prompt_layer_hashes") or agent_config.get("promptLayerHashes") or []
    if not isinstance(prompt_layer_hashes, (list, tuple)):
        prompt_layer_hashes = [prompt_layer_hashes]

    # Extract tool contracts
    tool_contracts = []
    for tc in (agent_config.get("tool_contracts") or agent_config.get("toolContracts") or []):
        if isinstance(tc, Mapping):
            tool_contracts.append({
                "tool_id": str(tc.get("tool_id") or tc.get("toolId", "")),
                "registry_revision": str(tc.get("registry_revision") or tc.get("registryRevision", "")),
                "input_schema_hash": str(tc.get("input_schema_hash") or tc.get("inputSchemaHash", "")),
                "output_schema_hash": str(tc.get("output_schema_hash") or tc.get("outputSchemaHash", "")),
            })

    # Extract limits hash
    limits_hash = str(agent_config.get("limits_hash") or agent_config.get("limitsHash", ""))
    if not _SHA64.fullmatch(limits_hash):
        limits_hash = canonical_config_sha256(agent_config.get("limits", agent_config.get("limits", {})))

    # Extract credential identity (redacted)
    credential_identity = agent_config.get("credential_identity") or agent_config.get("credentialIdentity")
    if credential_identity and isinstance(credential_identity, Mapping):
        credential_identity = {
            "credential_id": str(credential_identity.get("credential_id") or credential_identity.get("credentialId", "")),
            "provider": str(credential_identity.get("provider", "")),
        }

    return build_agent_config_snapshot(
        agent_id=agent_id,
        owner_id=owner_id,
        repository_id=repository_id,
        environment_id=environment_id,
        model_route=model_route,
        capability_manifest_hash=capability_manifest_hash,
        policy_set_hash=policy_set_hash,
        prompt_layer_hashes=prompt_layer_hashes,
        tool_contracts=tool_contracts,
        limits_hash=limits_hash,
        credential_identity=credential_identity,
    )


def verify_config_fingerprint(
    snapshot: AgentConfigSnapshot,
    current_config: Mapping[str, Any],
    *,
    agent_id: str,
    owner_id: str,
) -> bool:
    """Verify that a current config matches a previously captured snapshot.

    Returns True if the current config produces the same snapshot hash.
    """

    current_snapshot = compile_config_fingerprint(
        current_config,
        agent_id=agent_id,
        owner_id=owner_id,
        repository_id=snapshot.repository_id,
        environment_id=snapshot.environment_id,
    )
    return current_snapshot.snapshot_hash == snapshot.snapshot_hash


__all__ = [
    "ConfigSnapshotError",
    "AgentConfigSnapshot",
    "build_agent_config_snapshot",
    "compile_config_fingerprint",
    "verify_config_fingerprint",
    "canonical_config_sha256",
    "canonical_config_value",
    "canonical_config_bytes",
]
