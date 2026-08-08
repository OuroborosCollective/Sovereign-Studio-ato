"""Tests for config snapshot and fingerprinting.

Referenced by:
    - Issue #1119: Atomic Versioned Mutation Control
    - Section 2: Kanonischer Konfigurationssnapshot
"""

import pytest

from backend.agent_runtime.mutations.config_snapshot import (
    AgentConfigSnapshot,
    ModelRoute,
    ToolContract,
    build_agent_config_snapshot,
    compute_config_fingerprint,
    detect_config_drift,
    fingerprint_limits,
    fingerprint_policy_set,
    fingerprint_prompt_layers,
    fingerprint_tool_contracts,
    verify_config_fingerprint,
)


class TestComputeConfigFingerprint:
    """Tests for config fingerprinting."""

    def test_fingerprint_deterministic(self) -> None:
        """Same config produces same fingerprint."""
        config = {"key": "value", "number": 42}

        fp1 = compute_config_fingerprint(config)
        fp2 = compute_config_fingerprint(config)

        assert fp1 == fp2
        assert len(fp1) == 64  # SHA-256 hex

    def test_fingerprint_different_values_different_hash(self) -> None:
        """Different values produce different fingerprints."""
        config1 = {"key": "value1"}
        config2 = {"key": "value2"}

        fp1 = compute_config_fingerprint(config1)
        fp2 = compute_config_fingerprint(config2)

        assert fp1 != fp2

    def test_fingerprint_key_order_independent(self) -> None:
        """Key order doesn't affect fingerprint."""
        config1 = {"a": 1, "b": 2, "c": 3}
        config2 = {"c": 3, "a": 1, "b": 2}

        fp1 = compute_config_fingerprint(config1)
        fp2 = compute_config_fingerprint(config2)

        assert fp1 == fp2

    def test_fingerprint_redacts_secrets(self) -> None:
        """Secret-shaped fields are redacted in fingerprint."""
        config_with_secret = {"api_key": "super-secret-value-123"}
        config_without_secret = {"api_key": "[REDACTED]"}

        # Both should produce the same fingerprint because secrets are redacted
        fp1 = compute_config_fingerprint(config_with_secret)
        fp2 = compute_config_fingerprint(config_without_secret)

        assert fp1 == fp2

    def test_fingerprint_safe_boolean_allowed(self) -> None:
        """Safe boolean fields with 'secret' in name are allowed."""
        config = {"secret_values_returned": True, "api_key": "[REDACTED]"}

        fp = compute_config_fingerprint(config)

        assert len(fp) == 64

    def test_fingerprint_rejects_floats(self) -> None:
        """Floating-point values are rejected."""
        config = {"value": 3.14}

        with pytest.raises(ValueError, match="forbidden"):
            compute_config_fingerprint(config)

    def test_fingerprint_nested_dicts(self) -> None:
        """Nested dicts are fingerprinted correctly."""
        config = {"outer": {"inner": "value"}, "list": [1, 2, 3]}

        fp = compute_config_fingerprint(config)

        assert len(fp) == 64


class TestFingerprintToolContracts:
    """Tests for tool contract fingerprinting."""

    def test_tool_contracts_sorted_before_hash(self) -> None:
        """Tool contracts are sorted by tool_id before hashing."""
        contracts1 = [
            {"tool_id": "a", "input_schema_hash": "x"},
            {"tool_id": "b", "input_schema_hash": "y"},
        ]
        contracts2 = [
            {"tool_id": "b", "input_schema_hash": "y"},
            {"tool_id": "a", "input_schema_hash": "x"},
        ]

        fp1 = fingerprint_tool_contracts(contracts1)
        fp2 = fingerprint_tool_contracts(contracts2)

        assert fp1 == fp2

    def test_different_contracts_different_hash(self) -> None:
        """Different tool contracts produce different fingerprints."""
        contracts1 = [{"tool_id": "tool1"}]
        contracts2 = [{"tool_id": "tool2"}]

        fp1 = fingerprint_tool_contracts(contracts1)
        fp2 = fingerprint_tool_contracts(contracts2)

        assert fp1 != fp2


class TestFingerprintPolicySet:
    """Tests for policy set fingerprinting."""

    def test_policy_set_sorted_before_hash(self) -> None:
        """Policies are sorted by policy_id before hashing."""
        policies1 = [
            {"policy_id": "policy-a", "action": "allow"},
            {"policy_id": "policy-b", "action": "deny"},
        ]
        policies2 = [
            {"policy_id": "policy-b", "action": "deny"},
            {"policy_id": "policy-a", "action": "allow"},
        ]

        fp1 = fingerprint_policy_set(policies1)
        fp2 = fingerprint_policy_set(policies2)

        assert fp1 == fp2


class TestFingerprintPromptLayers:
    """Tests for prompt layer fingerprinting."""

    def test_returns_tuple_of_hashes(self) -> None:
        """Returns tuple with one hash per layer."""
        layers = [{"name": "layer1"}, {"name": "layer2"}]

        hashes = fingerprint_prompt_layers(layers)

        assert isinstance(hashes, tuple)
        assert len(hashes) == 2
        assert all(len(h) == 64 for h in hashes)

    def test_different_layers_different_hashes(self) -> None:
        """Different layers produce different hashes."""
        layers = [{"name": "layer1"}, {"name": "layer2"}]

        hashes = fingerprint_prompt_layers(layers)

        assert hashes[0] != hashes[1]


class TestFingerprintLimits:
    """Tests for limits fingerprinting."""

    def test_limits_fingerprint(self) -> None:
        """Limits are fingerprinted correctly."""
        limits = {
            "max_runtime_ms": 300000,
            "max_workspace_bytes": 100_000_000,
        }

        fp = fingerprint_limits(limits)

        assert len(fp) == 64


class TestAgentConfigSnapshot:
    """Tests for AgentConfigSnapshot."""

    def test_build_snapshot(self) -> None:
        """Can build a valid config snapshot."""
        model_route = ModelRoute(provider="openai", model="gpt-4", route_revision="v1")
        snapshot = AgentConfigSnapshot(
            agent_id="agent-123",
            owner_id="owner-456",
            environment_id="prod",
            model_route=model_route,
            capability_manifest_hash="a" * 64,
            policy_set_hash="b" * 64,
            limits_hash="c" * 64,
        )

        assert snapshot.agent_id == "agent-123"
        assert snapshot.model_route.provider == "openai"

    def test_to_dict(self) -> None:
        """Snapshot converts to dict correctly."""
        model_route = ModelRoute(provider="anthropic", model="claude-3", route_revision="v1")
        snapshot = AgentConfigSnapshot(
            agent_id="agent-123",
            owner_id="owner-456",
            environment_id="dev",
            model_route=model_route,
            capability_manifest_hash="x" * 64,
            policy_set_hash="y" * 64,
            limits_hash="z" * 64,
        )

        d = snapshot.to_dict()

        assert d["agent_id"] == "agent-123"
        assert d["model_route"]["provider"] == "anthropic"
        assert d["schema_version"] == "sovereign.agent-config-snapshot.v1"


class TestBuildAgentConfigSnapshot:
    """Tests for snapshot builder function."""

    def test_build_with_all_fields(self) -> None:
        """Build snapshot with all optional fields."""
        snapshot = build_agent_config_snapshot(
            agent_id="agent-1",
            owner_id="owner-1",
            environment_id="prod",
            model_provider="openai",
            model_name="gpt-4",
            model_route_revision="rev-123",
            credential_id="cred-1",
            credential_provider="openai",
            capability_manifest_hash="hash-1",
            policy_set=[{"policy_id": "p1", "action": "allow"}],
            prompt_layers=[{"name": "layer1"}],
            tool_contracts=[
                {
                    "tool_id": "tool1",
                    "registry_revision": "r1",
                    "input_schema_hash": "h1",
                    "output_schema_hash": "h2",
                }
            ],
            limits={"max_runtime_ms": 300000},
            repository_id="repo-1",
        )

        assert snapshot.agent_id == "agent-1"
        assert snapshot.repository_id == "repo-1"
        assert snapshot.credential_identity is not None
        assert len(snapshot.tool_contracts) == 1

    def test_build_without_optional_fields(self) -> None:
        """Build snapshot without optional fields."""
        snapshot = build_agent_config_snapshot(
            agent_id="agent-1",
            owner_id="owner-1",
            environment_id="prod",
            model_provider="anthropic",
            model_name="claude-3",
            model_route_revision="rev-1",
            credential_id=None,
            credential_provider=None,
            capability_manifest_hash="hash-1",
            policy_set=[],
            prompt_layers=None,
            tool_contracts=None,
            limits={},
            repository_id=None,
        )

        assert snapshot.credential_identity is None
        assert len(snapshot.prompt_layer_hashes) == 0
        assert len(snapshot.tool_contracts) == 0


class TestVerifyConfigFingerprint:
    """Tests for fingerprint verification."""

    def test_verify_matching_fingerprint(self) -> None:
        """Matching fingerprint passes verification."""
        config = {"key": "value"}
        fingerprint = compute_config_fingerprint(config)

        matches, result = verify_config_fingerprint(config, fingerprint)

        assert matches
        assert result == fingerprint

    def test_verify_non_matching_fingerprint(self) -> None:
        """Non-matching fingerprint fails verification."""
        config = {"key": "value"}
        wrong_fingerprint = "a" * 64

        matches, result = verify_config_fingerprint(config, wrong_fingerprint)

        assert not matches


class TestDetectConfigDrift:
    """Tests for config drift detection."""

    def test_no_drift(self) -> None:
        """Identical configs have no drift."""
        model_route1 = ModelRoute(provider="openai", model="gpt-4", route_revision="v1")
        model_route2 = ModelRoute(provider="openai", model="gpt-4", route_revision="v1")

        snap1 = AgentConfigSnapshot(
            agent_id="agent-1",
            owner_id="owner-1",
            environment_id="prod",
            model_route=model_route1,
            capability_manifest_hash="a" * 64,
            policy_set_hash="b" * 64,
            limits_hash="c" * 64,
        )
        snap2 = AgentConfigSnapshot(
            agent_id="agent-1",
            owner_id="owner-1",
            environment_id="prod",
            model_route=model_route2,
            capability_manifest_hash="a" * 64,
            policy_set_hash="b" * 64,
            limits_hash="c" * 64,
        )

        drift = detect_config_drift(snap1, snap2)

        assert not drift["has_drift"]
        assert len(drift["fields"]) == 0

    def test_detects_model_route_drift(self) -> None:
        """Detects drift in model route."""
        model_route1 = ModelRoute(provider="openai", model="gpt-4", route_revision="v1")
        model_route2 = ModelRoute(provider="anthropic", model="claude-3", route_revision="v1")

        snap1 = AgentConfigSnapshot(
            agent_id="agent-1",
            owner_id="owner-1",
            environment_id="prod",
            model_route=model_route1,
            capability_manifest_hash="a" * 64,
            policy_set_hash="b" * 64,
            limits_hash="c" * 64,
        )
        snap2 = AgentConfigSnapshot(
            agent_id="agent-1",
            owner_id="owner-1",
            environment_id="prod",
            model_route=model_route2,
            capability_manifest_hash="a" * 64,
            policy_set_hash="b" * 64,
            limits_hash="c" * 64,
        )

        drift = detect_config_drift(snap1, snap2)

        assert drift["has_drift"]
        assert "model_route" in drift["fields"]

    def test_detects_multiple_fields_drift(self) -> None:
        """Detects drift in multiple fields."""
        model_route1 = ModelRoute(provider="openai", model="gpt-4", route_revision="v1")
        model_route2 = ModelRoute(provider="openai", model="gpt-4o", route_revision="v1")

        snap1 = AgentConfigSnapshot(
            agent_id="agent-1",
            owner_id="owner-1",
            environment_id="prod",
            model_route=model_route1,
            capability_manifest_hash="a" * 64,
            policy_set_hash="b" * 64,
            limits_hash="c" * 64,
        )
        snap2 = AgentConfigSnapshot(
            agent_id="agent-1",
            owner_id="owner-2",  # Changed
            environment_id="staging",  # Changed
            model_route=model_route2,  # Changed
            capability_manifest_hash="a" * 64,
            policy_set_hash="b" * 64,
            limits_hash="c" * 64,
        )

        drift = detect_config_drift(snap1, snap2)

        assert drift["has_drift"]
        assert "owner_id" in drift["fields"]
        assert "environment_id" in drift["fields"]
        assert "model_route" in drift["fields"]
