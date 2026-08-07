"""Canonical configuration snapshot and fingerprinting.

This module provides deterministic config snapshots for security-relevant
configuration fields. Only behavioral and security-critical fields are
included; secrets are never included (only redacted credential identities).

Referenced by:
    - Issue #1119: Atomic Versioned Mutation Control
    - Section 2: Kanonischer Konfigurationssnapshot
    - Section 8: Config Fingerprint im RunEnvelope
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import hashlib
import json
import unicodedata

# Schema version for canonicalization
_CANONICALIZATION: str = "utf8-nfc-json-sorted-no-floats-v1"
_SCHEMA_VERSION: str = "sovereign.agent-config-snapshot.v1"

# Secret-shaped field markers that must be redacted
_SECRET_KEY_MARKERS: tuple[str, ...] = (
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
    "secret_key",
    "secret_value",
)

# Fields that are safe to include as booleans even if they contain "secret"
_SECRET_SAFE_BOOLEAN_KEYS: frozenset[str] = frozenset({
    "secret_values_returned",
    "secretvaluesreturned",
    "raw_secrets_persisted",
    "rawsecretspersisted",
    "mcp_revision_verified",
})


@dataclass(frozen=True)
class ModelRoute:
    """Model route configuration (without sensitive details)."""
    provider: str
    model: str
    route_revision: str


@dataclass(frozen=True)
class ToolContract:
    """A single tool contract in the capability manifest."""
    tool_id: str
    registry_revision: str
    input_schema_hash: str
    output_schema_hash: str


@dataclass(frozen=True)
class CredentialIdentity:
    """Redacted credential identity (never contains actual secrets)."""
    credential_id: str
    provider: str


@dataclass(frozen=True)
class AgentConfigSnapshot:
    """Canonical agent configuration snapshot.

    This captures all behaviorally and security-relevant fields in a
    deterministic, hashable form. Secrets are never included.
    """
    agent_id: str
    owner_id: str
    environment_id: str
    model_route: ModelRoute
    capability_manifest_hash: str
    policy_set_hash: str
    limits_hash: str
    schema_version: str = field(default=_SCHEMA_VERSION)
    repository_id: str | None = None
    credential_identity: CredentialIdentity | None = None
    prompt_layer_hashes: tuple[str, ...] = ()
    tool_contracts: tuple[ToolContract, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to a canonical dict for hashing."""
        return {
            "schema_version": self.schema_version,
            "agent_id": self.agent_id,
            "owner_id": self.owner_id,
            "repository_id": self.repository_id,
            "environment_id": self.environment_id,
            "model_route": {
                "provider": self.model_route.provider,
                "model": self.model_route.model,
                "route_revision": self.model_route.route_revision,
            },
            "credential_identity": (
                {
                    "credential_id": self.credential_identity.credential_id,
                    "provider": self.credential_identity.provider,
                }
                if self.credential_identity else None
            ),
            "capability_manifest_hash": self.capability_manifest_hash,
            "policy_set_hash": self.policy_set_hash,
            "prompt_layer_hashes": list(self.prompt_layer_hashes),
            "tool_contracts": [
                {
                    "tool_id": tc.tool_id,
                    "registry_revision": tc.registry_revision,
                    "input_schema_hash": tc.input_schema_hash,
                    "output_schema_hash": tc.output_schema_hash,
                }
                for tc in self.tool_contracts
            ],
            "limits_hash": self.limits_hash,
            "extra": self.extra,
        }


def _normalize_string(value: str) -> str:
    """Normalize a string for deterministic comparison."""
    return unicodedata.normalize("NFC", value)


def _canonical_value(value: Any, *, path: str = "$") -> Any:
    """Return the exact JSON-safe canonical value or fail closed.

    Raises:
        ValueError: If floating-point values or secret-shaped fields are encountered
    """
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        raise ValueError(f"Floating-point value is forbidden at {path}")
    if isinstance(value, str):
        return _normalize_string(value)
    if isinstance(value, bytes):
        return {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for raw_key, item in value.items():
            if not isinstance(raw_key, str):
                raise ValueError(f"Non-string object key is forbidden at {path}")
            key = _normalize_string(raw_key)
            folded = key.casefold()
            # Redact secret-shaped fields (but allow safe boolean flags)
            if any(marker in folded for marker in _SECRET_KEY_MARKERS):
                if folded not in _SECRET_SAFE_BOOLEAN_KEYS or not isinstance(item, bool):
                    output[key] = "[REDACTED]"
                else:
                    output[key] = item
            else:
                output[key] = _canonical_value(item, path=f"{path}.{key}")
        return output
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item, path=f"{path}[{i}]") for i, item in enumerate(value)]
    raise ValueError(f"Unsupported canonical type {type(value).__name__} at {path}")


def canonical_bytes(value: Any) -> bytes:
    """Convert a value to canonical bytes for hashing."""
    normalized = _canonical_value(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def compute_config_fingerprint(config: dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 fingerprint of a config dict.

    The fingerprint is computed over a canonicalized, sorted JSON
    representation with secret-shaped fields redacted.

    Args:
        config: The configuration dict to fingerprint

    Returns:
        A 64-character lowercase hex string (SHA-256)
    """
    return hashlib.sha256(canonical_bytes(config)).hexdigest()


def fingerprint_tool_contracts(contracts: list[dict[str, Any]]) -> str:
    """Fingerprint a list of tool contracts.

    Contracts are sorted by tool_id before hashing to ensure
    deterministic output regardless of input order.
    """
    sorted_contracts = sorted(contracts, key=lambda c: str(c.get("tool_id", "")))
    return compute_config_fingerprint({"contracts": sorted_contracts})


def fingerprint_policy_set(policies: list[dict[str, Any]]) -> str:
    """Fingerprint a policy set configuration."""
    # Sort by policy ID for determinism
    sorted_policies = sorted(policies, key=lambda p: str(p.get("policy_id", "")))
    return compute_config_fingerprint({"policies": sorted_policies})


def fingerprint_prompt_layers(layers: list[dict[str, Any]]) -> tuple[str, ...]:
    """Fingerprint each prompt layer individually.

    Returns a tuple of hashes, one per layer in order.
    """
    return tuple(compute_config_fingerprint(layer) for layer in layers)


def fingerprint_limits(limits: dict[str, Any]) -> str:
    """Fingerprint runtime limits configuration."""
    return compute_config_fingerprint(limits)


def build_agent_config_snapshot(
    agent_id: str,
    owner_id: str,
    environment_id: str,
    model_provider: str,
    model_name: str,
    model_route_revision: str,
    credential_id: str | None,
    credential_provider: str | None,
    capability_manifest_hash: str,
    policy_set: list[dict[str, Any]],
    prompt_layers: list[dict[str, Any]] | None,
    tool_contracts: list[dict[str, Any]] | None,
    limits: dict[str, Any],
    repository_id: str | None = None,
) -> AgentConfigSnapshot:
    """Build a canonical agent config snapshot.

    Args:
        agent_id: The agent's unique identifier
        owner_id: The owner's identifier
        environment_id: The environment identifier
        model_provider: LLM provider name
        model_name: Model name
        model_route_revision: Revision of the route configuration
        credential_id: Redacted credential identifier (never the actual secret)
        credential_provider: Provider name for the credential
        capability_manifest_hash: Hash of the capability manifest
        policy_set: List of policy configurations
        prompt_layers: Optional list of prompt layer configs
        tool_contracts: Optional list of tool contract configs
        limits: Runtime limits configuration
        repository_id: Optional repository identifier

    Returns:
        An immutable AgentConfigSnapshot
    """
    model_route = ModelRoute(
        provider=model_provider,
        model=model_name,
        route_revision=model_route_revision,
    )

    credential_identity = None
    if credential_id and credential_provider:
        credential_identity = CredentialIdentity(
            credential_id=credential_id,
            provider=credential_provider,
        )

    policy_hash = fingerprint_policy_set(policy_set)

    prompt_hashes = ()
    if prompt_layers:
        prompt_hashes = fingerprint_prompt_layers(prompt_layers)

    tool_contracts_hashes = ()
    if tool_contracts:
        contracts = [
            ToolContract(
                tool_id=tc.get("tool_id", ""),
                registry_revision=tc.get("registry_revision", ""),
                input_schema_hash=tc.get("input_schema_hash", ""),
                output_schema_hash=tc.get("output_schema_hash", ""),
            )
            for tc in tool_contracts
        ]
        tool_contracts_hashes = tuple(contracts)

    limits_hash = fingerprint_limits(limits)

    return AgentConfigSnapshot(
        agent_id=agent_id,
        owner_id=owner_id,
        repository_id=repository_id,
        environment_id=environment_id,
        model_route=model_route,
        credential_identity=credential_identity,
        capability_manifest_hash=capability_manifest_hash,
        policy_set_hash=policy_hash,
        prompt_layer_hashes=prompt_hashes,
        tool_contracts=tool_contracts_hashes,
        limits_hash=limits_hash,
    )


def verify_config_fingerprint(
    config: dict[str, Any],
    expected_fingerprint: str,
) -> tuple[bool, str | None]:
    """Verify a config matches an expected fingerprint.

    Returns:
        Tuple of (matches, computed_fingerprint_or_error)
    """
    try:
        computed = compute_config_fingerprint(config)
        return computed == expected_fingerprint, computed
    except (ValueError, TypeError) as e:
        return False, str(e)


def detect_config_drift(
    snapshot_a: AgentConfigSnapshot,
    snapshot_b: AgentConfigSnapshot,
) -> dict[str, Any]:
    """Detect which configuration fields differ between two snapshots.

    Returns a dict describing the drift for display or audit purposes.
    """
    drift: dict[str, Any] = {
        "has_drift": False,
        "fields": [],
    }

    if snapshot_a.agent_id != snapshot_b.agent_id:
        drift["has_drift"] = True
        drift["fields"].append("agent_id")

    if snapshot_a.owner_id != snapshot_b.owner_id:
        drift["has_drift"] = True
        drift["fields"].append("owner_id")

    if snapshot_a.environment_id != snapshot_b.environment_id:
        drift["has_drift"] = True
        drift["fields"].append("environment_id")

    if snapshot_a.model_route != snapshot_b.model_route:
        drift["has_drift"] = True
        drift["fields"].append("model_route")

    if snapshot_a.capability_manifest_hash != snapshot_b.capability_manifest_hash:
        drift["has_drift"] = True
        drift["fields"].append("capability_manifest_hash")

    if snapshot_a.policy_set_hash != snapshot_b.policy_set_hash:
        drift["has_drift"] = True
        drift["fields"].append("policy_set_hash")

    if snapshot_a.prompt_layer_hashes != snapshot_b.prompt_layer_hashes:
        drift["has_drift"] = True
        drift["fields"].append("prompt_layer_hashes")

    if snapshot_a.tool_contracts != snapshot_b.tool_contracts:
        drift["has_drift"] = True
        drift["fields"].append("tool_contracts")

    if snapshot_a.limits_hash != snapshot_b.limits_hash:
        drift["has_drift"] = True
        drift["fields"].append("limits_hash")

    return drift
