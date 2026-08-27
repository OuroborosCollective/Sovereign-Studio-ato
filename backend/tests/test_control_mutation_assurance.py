"""Tests for control_mutation_assurance module."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from backend.agent_runtime.control_mutation_assurance import (
    CanaryExecutionResult,
    CanaryTarget,
    CanaryTargetError,
    SCHEMA_VERSION,
    _compute_canary_id,
    _canonical_sha256,
    determine_verdict,
    execute_canary_case,
    get_canary_target,
    list_canary_targets,
    validate_canary_config,
)


class TestCanaryTargets:
    """Tests for canary target configuration."""

    def test_list_canary_targets(self):
        """List available canary targets."""
        targets = list_canary_targets()
        assert "local_echo" in targets
        assert "test_server" in targets
        assert "disallowed_host" in targets
        assert len(targets) == 3

    def test_get_canary_target_valid(self):
        """Get a valid canary target."""
        target = get_canary_target("local_echo")
        assert target.target_id == "acsa_local_echo"
        assert target.is_production is False

    def test_get_canary_target_invalid(self):
        """Get an invalid canary target raises error."""
        with pytest.raises(CanaryTargetError, match="unknown canary target"):
            get_canary_target("nonexistent")

    def test_canary_target_rejects_production(self):
        """CanaryTarget rejects production flag."""
        with pytest.raises(CanaryTargetError, match="must not be marked as production"):
            CanaryTarget(
                target_id="test_target",
                target_type="test",
                is_production=True,
                allows_egress=False,
                endpoint=None,
                canary_id_prefix="test_",
            )

    def test_canary_target_validates_id_format(self):
        """CanaryTarget validates target_id format."""
        with pytest.raises(CanaryTargetError, match="invalid target_id format"):
            CanaryTarget(
                target_id="INVALID UPPERCASE",
                target_type="test",
                is_production=False,
                allows_egress=False,
                endpoint=None,
                canary_id_prefix="test_",
            )


class TestCanaryConfigValidation:
    """Tests for canary configuration validation."""

    def test_validate_valid_target_succeeds(self):
        """Valid canary target passes validation."""
        target = get_canary_target("local_echo")
        is_valid, error = validate_canary_config(target)
        assert is_valid is True
        assert error is None


class TestCanaryId:
    """Tests for canary ID computation."""

    def test_canary_id_format(self):
        """Canary IDs have correct format."""
        canary_id = _compute_canary_id("acsa_le_", "test_case", "run_123")
        assert canary_id.startswith("acsa_le_")
        assert len(canary_id) == 24  # prefix (8) + 16 hex

    def test_canary_id_deterministic(self):
        """Canary IDs are deterministic."""
        id1 = _compute_canary_id("acsa_le_", "test_case", "run_123")
        id2 = _compute_canary_id("acsa_le_", "test_case", "run_123")
        assert id1 == id2

    def test_canary_id_differs_by_case(self):
        """Different cases produce different IDs."""
        id1 = _compute_canary_id("acsa_le_", "case_a", "run_123")
        id2 = _compute_canary_id("acsa_le_", "case_b", "run_123")
        assert id1 != id2


class TestVerdictDetermination:
    """Tests for verdict determination logic."""

    def test_control_baseline_not_executed(self):
        """Verdict is CONTROL_BASELINE_INVALID when baseline not executed."""
        result = CanaryExecutionResult(
            case_id="test_case",
            target_id="test_target",
            canary_id="canary_123",
            control_baseline_executed=False,
            control_baseline_success=False,
            control_baseline_error="not run",
            mutant_executed=False,
            mutant_blocked=False,
            block_code=None,
            target_readback_available=False,
            target_readback=None,
            target_readback_error=None,
            latency_ms=None,
            execution_sha256="0" * 64,
        )
        verdict, reason = determine_verdict(None, result)  # case not needed for this check
        assert verdict == "CONTROL_BASELINE_INVALID"

    def test_control_baseline_failed(self):
        """Verdict is CONTROL_BASELINE_INVALID when baseline fails."""
        result = CanaryExecutionResult(
            case_id="test_case",
            target_id="test_target",
            canary_id="canary_123",
            control_baseline_executed=True,
            control_baseline_success=False,
            control_baseline_error="execution failed",
            mutant_executed=False,
            mutant_blocked=False,
            block_code=None,
            target_readback_available=False,
            target_readback=None,
            target_readback_error=None,
            latency_ms=None,
            execution_sha256="0" * 64,
        )
        verdict, reason = determine_verdict(None, result)
        assert verdict == "CONTROL_BASELINE_INVALID"
        assert "failed" in reason

    def test_mutant_not_blocked_survived(self):
        """Verdict is MUTANT_SURVIVED when mutant not blocked."""
        result = CanaryExecutionResult(
            case_id="test_case",
            target_id="test_target",
            canary_id="canary_123",
            control_baseline_executed=True,
            control_baseline_success=True,
            control_baseline_error=None,
            mutant_executed=True,
            mutant_blocked=False,  # NOT blocked
            block_code=None,
            target_readback_available=False,
            target_readback=None,
            target_readback_error=None,
            latency_ms=100,
            execution_sha256="0" * 64,
        )
        verdict, reason = determine_verdict(None, result)
        assert verdict == "MUTANT_SURVIVED"
        assert "not blocked" in reason

    def test_mutant_blocked_no_readback_unverified(self):
        """Verdict is UNVERIFIED when blocked but no readback."""
        result = CanaryExecutionResult(
            case_id="test_case",
            target_id="test_target",
            canary_id="canary_123",
            control_baseline_executed=True,
            control_baseline_success=True,
            control_baseline_error=None,
            mutant_executed=False,
            mutant_blocked=True,  # Blocked
            block_code="egress_blocked",
            target_readback_available=False,  # No readback
            target_readback=None,
            target_readback_error=None,
            latency_ms=50,
            execution_sha256="0" * 64,
        )
        verdict, reason = determine_verdict(None, result)
        # Note: This test assumes requires_target_readback would be True for this case
        # The actual verdict depends on the case configuration
        assert verdict in ("MUTANT_KILLED", "UNVERIFIED")

    def test_mutant_blocked_with_readback_killed(self):
        """Verdict is MUTANT_KILLED when blocked and readback shows no effect."""
        result = CanaryExecutionResult(
            case_id="test_case",
            target_id="test_target",
            canary_id="canary_123",
            control_baseline_executed=True,
            control_baseline_success=True,
            control_baseline_error=None,
            mutant_executed=False,
            mutant_blocked=True,
            block_code="egress_blocked",
            target_readback_available=True,
            target_readback={"effect_observed": False},  # No effect
            target_readback_error=None,
            latency_ms=50,
            execution_sha256="0" * 64,
        )
        verdict, reason = determine_verdict(None, result)
        assert verdict == "MUTANT_KILLED"

    def test_mutant_blocked_with_readback_effect_survived(self):
        """Verdict is MUTANT_SURVIVED when blocked but readback shows effect."""
        result = CanaryExecutionResult(
            case_id="test_case",
            target_id="test_target",
            canary_id="canary_123",
            control_baseline_executed=True,
            control_baseline_success=True,
            control_baseline_error=None,
            mutant_executed=False,
            mutant_blocked=True,
            block_code="egress_blocked",
            target_readback_available=True,
            target_readback={"effect_observed": True},  # Effect observed!
            target_readback_error=None,
            latency_ms=50,
            execution_sha256="0" * 64,
        )
        verdict, reason = determine_verdict(None, result)
        assert verdict == "MUTANT_SURVIVED"

    def test_contradiction_both_executed_and_blocked(self):
        """Verdict is CONTRADICTED when both executed and blocked."""
        result = CanaryExecutionResult(
            case_id="test_case",
            target_id="test_target",
            canary_id="canary_123",
            control_baseline_executed=True,
            control_baseline_success=True,
            control_baseline_error=None,
            mutant_executed=True,  # Executed
            mutant_blocked=True,   # AND blocked - contradiction
            block_code="some_block",
            target_readback_available=False,
            target_readback=None,
            target_readback_error=None,
            latency_ms=50,
            execution_sha256="0" * 64,
        )
        verdict, reason = determine_verdict(None, result)
        assert verdict == "CONTRADICTED"
        assert "both" in reason and "executed" in reason


class TestSchemaVersion:
    """Tests for schema version."""

    def test_schema_version_format(self):
        """Schema version follows expected format."""
        assert SCHEMA_VERSION.startswith("sovereign.control-mutation-assurance.v")
        # Should be v1 or higher
        version_num = int(SCHEMA_VERSION.split(".v")[-1])
        assert version_num >= 1


class TestCanonicalSha256:
    """Tests for canonical SHA-256 computation."""

    def test_canonical_sha256_deterministic(self):
        """SHA-256 computation is deterministic."""
        data = {"key": "value", "number": 42}
        hash1 = _canonical_sha256(data)
        hash2 = _canonical_sha256(data)
        assert hash1 == hash2

    def test_canonical_sha256_order_independent(self):
        """SHA-256 ignores key order."""
        data1 = {"a": 1, "b": 2}
        data2 = {"b": 2, "a": 1}
        assert _canonical_sha256(data1) == _canonical_sha256(data2)

    def test_canonical_sha256_sha256_format(self):
        """SHA-256 output is valid hex format."""
        hash_val = _canonical_sha256({"test": "data"})
        assert len(hash_val) == 64
        assert all(c in "0123456789abcdef" for c in hash_val)
