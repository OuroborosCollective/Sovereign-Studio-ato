"""Tests for ControlMutationAssurance canary execution lane.

These tests verify:
- Canary target validation
- Execution context computation
- Verdict evaluation
- Receipt generation
- Single-variable invariant enforcement
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from backend.agent_runtime.control_mutation_assurance import (
    CanaryExecutionResult,
    CanaryExecutionContext,
    CanaryExecutionError,
    CanaryTargetKind,
    ControlMutationVerdict,
    SCHEMA_VERSION,
    build_canary_execution_receipt,
    check_operator_environment_testable,
    compute_canary_execution_context,
    compute_expected_block_code,
    evaluate_verdict,
    validate_canary_target,
    validate_no_production_environment,
)
from backend.agent_runtime.control_mutation_cases import (
    ControlMutationCase,
    ControlMutationOperator,
    SecurityDimension,
    build_control_mutation_case,
)
from backend.agent_runtime.environment_mcp_execution import (
    EnvironmentKind,
)


# Test constants
TEST_CANARY_ID = "acsa-test-001"
TEST_REVISION = "0" * 40
TEST_OTHER_REVISION = "a" * 40
TEST_REPO = "test/repo"
TEST_OWNER = "test-owner"


def make_test_case(
    operator: ControlMutationOperator,
    mutation_id: str = "test-mutation-001",
    revision: str = TEST_REVISION,
    expected_block_code: str | None = "owner_mismatch",
) -> ControlMutationCase:
    """Helper to create a test control mutation case using the builder.
    
    The builder enforces single-variable invariant - only the allowed dimension
    for the operator may differ between baseline and mutated contracts.
    
    Note: Contract keys must match SecurityDimension values (without _id suffix).
    For OWNER_MISMATCH, use "owner" not "owner_id".
    """
    # Build baseline contract - use exact same structure for all fields
    baseline_contract = {
        "owner": TEST_OWNER,   # Note: "owner" not "owner_id"
        "revision": revision,
    }

    # Build mutated contract - only the allowed dimension differs
    if operator == ControlMutationOperator.OWNER_MISMATCH:
        mutated_contract = {
            "owner": "attacker",  # Only owner differs!
            "revision": revision,  # Same as baseline
        }
    elif operator == ControlMutationOperator.STALE_REVISION:
        mutated_contract = {
            "owner": TEST_OWNER,          # Same as baseline
            "revision": TEST_OTHER_REVISION,  # Only revision differs!
        }
    elif operator == ControlMutationOperator.NONPROD_TO_PRODUCTION:
        # NONPROD_TO_PRODUCTION changes environment
        baseline_contract["environment"] = "development"
        mutated_contract = {
            "owner": TEST_OWNER,
            "revision": revision,
            "environment": "production",  # Only this differs!
        }
    else:
        # For other operators, use a simple owner mismatch case
        mutated_contract = {
            "owner": "attacker",
            "revision": revision,
        }

    return build_control_mutation_case(
        mutation_id=mutation_id,
        operator=operator,
        repository=TEST_REPO,
        repository_revision=revision,
        control_owner=TEST_OWNER,
        baseline_contract=baseline_contract,
        mutated_contract=mutated_contract,
        protected_operation_family="test.operation",
        operation_input_sha256="c" * 64,
        expected_block_code=expected_block_code,
    )


# ---------------------------------------------------------------------------
# Canary Target Validation Tests
# ---------------------------------------------------------------------------

class TestCanaryTargetValidation:
    """Test canary target validation."""

    def test_valid_canary_target(self):
        """Valid ACSA canary targets should pass validation."""
        # Should not raise
        validate_canary_target(CanaryTargetKind.EPHEMERAL_ENDPOINT, "acsa-test-001")

    def test_invalid_prefix_rejected(self):
        """Non-ACSA prefixed targets should be rejected."""
        with pytest.raises(CanaryExecutionError, match="must start with"):
            validate_canary_target(CanaryTargetKind.EPHEMERAL_ENDPOINT, "test-001")

    def test_production_indicator_rejected(self):
        """Targets with production indicators should be rejected."""
        # These start with the valid prefix but contain prod indicators
        with pytest.raises(CanaryExecutionError, match="production indicators"):
            validate_canary_target(CanaryTargetKind.EPHEMERAL_ENDPOINT, "acsa-test-prod-001")

    def test_live_indicator_rejected(self):
        """Targets with live indicators should be rejected."""
        # This starts with valid prefix but contains live
        with pytest.raises(CanaryExecutionError, match="production indicators"):
            validate_canary_target(CanaryTargetKind.EPHEMERAL_ENDPOINT, "acsa-test-live-001")


class TestNoProductionEnvironment:
    """Test production environment validation."""

    def test_production_rejected(self):
        """Production environment should be rejected."""
        with pytest.raises(CanaryExecutionError, match="must never use production"):
            validate_no_production_environment(EnvironmentKind.PRODUCTION)

    def test_nonprod_allowed(self):
        """Non-production environments should be allowed."""
        # Should not raise
        validate_no_production_environment(EnvironmentKind.DEVELOPMENT)
        validate_no_production_environment(EnvironmentKind.TEST)
        validate_no_production_environment(EnvironmentKind.STAGING)
        validate_no_production_environment(EnvironmentKind.EPHEMERAL)


# ---------------------------------------------------------------------------
# Operator Testability Tests
# ---------------------------------------------------------------------------

class TestOperatorEnvironmentTestable:
    """Test which operators can be tested with environment contracts."""

    def test_owner_mismatch_testable(self):
        """OWNER_MISMATCH should be environment-testable."""
        assert check_operator_environment_testable(ControlMutationOperator.OWNER_MISMATCH) is True

    def test_tool_binding_swap_testable(self):
        """TOOL_BINDING_SWAP should be environment-testable."""
        assert check_operator_environment_testable(ControlMutationOperator.TOOL_BINDING_SWAP) is True

    def test_credential_replay_testable(self):
        """CREDENTIAL_REPLAY should be environment-testable."""
        assert check_operator_environment_testable(ControlMutationOperator.CREDENTIAL_REPLAY) is True

    def test_receipt_replay_testable(self):
        """RECEIPT_REPLAY should be environment-testable."""
        assert check_operator_environment_testable(ControlMutationOperator.RECEIPT_REPLAY) is True

    def test_nonprod_to_production_testable(self):
        """NONPROD_TO_PRODUCTION should be environment-testable."""
        assert check_operator_environment_testable(ControlMutationOperator.NONPROD_TO_PRODUCTION) is True

    def test_disallowed_egress_testable(self):
        """DISALLOWED_EGRESS should be environment-testable."""
        assert check_operator_environment_testable(ControlMutationOperator.DISALLOWED_EGRESS) is True

    def test_stale_revision_testable(self):
        """STALE_REVISION should be environment-testable."""
        assert check_operator_environment_testable(ControlMutationOperator.STALE_REVISION) is True


# ---------------------------------------------------------------------------
# Execution Context Tests
# ---------------------------------------------------------------------------

class TestCanaryExecutionContext:
    """Test canary execution context computation."""

    def test_valid_context_creation(self):
        """Valid inputs should create execution context."""
        case = make_test_case(ControlMutationOperator.OWNER_MISMATCH)
        context = compute_canary_execution_context(
            case=case,
            canary_target_kind=CanaryTargetKind.EPHEMERAL_ENDPOINT,
            canary_target_id="acsa-test-001",
        )

        assert context.schema_version == SCHEMA_VERSION
        assert context.case == case
        assert context.canary_target_kind == CanaryTargetKind.EPHEMERAL_ENDPOINT
        assert context.canary_target_id == "acsa-test-001"
        assert context.baseline_execution_required is True
        assert context.target_readback_required is True

    def test_invalid_target_rejected(self):
        """Invalid canary target should raise error."""
        case = make_test_case(ControlMutationOperator.OWNER_MISMATCH)
        with pytest.raises(CanaryExecutionError):
            compute_canary_execution_context(
                case=case,
                canary_target_kind=CanaryTargetKind.EPHEMERAL_ENDPOINT,
                canary_target_id="invalid-target",
            )


# ---------------------------------------------------------------------------
# Verdict Evaluation Tests
# ---------------------------------------------------------------------------

class TestVerdictEvaluation:
    """Test verdict evaluation logic."""

    def test_mutant_killed_with_readback(self):
        """Mutant blocked with no-effect readback should be MUTANT_KILLED."""
        verdict, reason = evaluate_verdict(
            baseline_blocked=True,
            baseline_effect=False,
            mutant_blocked=True,
            mutant_effect=False,
            mutant_block_code="owner_mismatch",
            expected_block_code="owner_mismatch",
            has_target_readback=True,
            readback_shows_effect=False,
        )
        assert verdict == ControlMutationVerdict.MUTANT_KILLED

    def test_mutant_survived_with_effect(self):
        """Mutant with observed effect should be MUTANT_SURVIVED."""
        verdict, reason = evaluate_verdict(
            baseline_blocked=True,
            baseline_effect=False,
            mutant_blocked=False,
            mutant_effect=True,
            mutant_block_code=None,
            expected_block_code="owner_mismatch",
            has_target_readback=True,
            readback_shows_effect=True,
        )
        assert verdict == ControlMutationVerdict.MUTANT_SURVIVED
        assert "effect was observed" in reason.lower()

    def test_unverified_no_readback(self):
        """Mutant blocked but no readback should be UNVERIFIED."""
        verdict, reason = evaluate_verdict(
            baseline_blocked=True,
            baseline_effect=False,
            mutant_blocked=True,
            mutant_effect=False,
            mutant_block_code="owner_mismatch",
            expected_block_code="owner_mismatch",
            has_target_readback=False,
            readback_shows_effect=False,
        )
        assert verdict == ControlMutationVerdict.UNVERIFIED

    def test_unverified_no_effect_no_readback(self):
        """Mutant not blocked and no readback should be UNVERIFIED."""
        verdict, reason = evaluate_verdict(
            baseline_blocked=True,
            baseline_effect=False,
            mutant_blocked=False,
            mutant_effect=False,
            mutant_block_code=None,
            expected_block_code="owner_mismatch",
            has_target_readback=False,
            readback_shows_effect=False,
        )
        assert verdict == ControlMutationVerdict.UNVERIFIED

    def test_contradicted_block_code_mismatch(self):
        """Block code mismatch should be CONTRADICTED."""
        verdict, reason = evaluate_verdict(
            baseline_blocked=True,
            baseline_effect=False,
            mutant_blocked=True,
            mutant_effect=False,
            mutant_block_code="wrong_code",
            expected_block_code="owner_mismatch",
            has_target_readback=True,
            readback_shows_effect=False,
        )
        assert verdict == ControlMutationVerdict.CONTRADICTED
        assert "mismatch" in reason.lower()

    def test_control_baseline_invalid(self):
        """Baseline with effect should invalidate mutant evaluation."""
        verdict, reason = evaluate_verdict(
            baseline_blocked=False,
            baseline_effect=True,
            mutant_blocked=True,
            mutant_effect=False,
            mutant_block_code="owner_mismatch",
            expected_block_code="owner_mismatch",
            has_target_readback=True,
            readback_shows_effect=False,
        )
        assert verdict == ControlMutationVerdict.CONTROL_BASELINE_INVALID


# ---------------------------------------------------------------------------
# Expected Block Code Tests
# ---------------------------------------------------------------------------

class TestExpectedBlockCode:
    """Test expected block code computation."""

    def test_owner_mismatch_block_code(self):
        """OWNER_MISMATCH should have expected block code."""
        code = compute_expected_block_code(
            ControlMutationOperator.OWNER_MISMATCH,
            SecurityDimension.OWNER,
        )
        assert code == "owner_mismatch"

    def test_credential_replay_block_code(self):
        """CREDENTIAL_REPLAY should have expected block code."""
        code = compute_expected_block_code(
            ControlMutationOperator.CREDENTIAL_REPLAY,
            SecurityDimension.CREDENTIAL,
        )
        assert code == "credential_replay_detected"

    def test_disallowed_egress_block_code(self):
        """DISALLOWED_EGRESS should have expected block code."""
        code = compute_expected_block_code(
            ControlMutationOperator.DISALLOWED_EGRESS,
            SecurityDimension.EGRESS_POLICY,
        )
        assert code == "private_network"


# ---------------------------------------------------------------------------
# Receipt Generation Tests
# ---------------------------------------------------------------------------

class TestCanaryExecutionReceipt:
    """Test canary execution receipt generation."""

    def test_full_receipt_generation(self):
        """Full execution should generate valid receipt."""
        case = make_test_case(ControlMutationOperator.OWNER_MISMATCH)

        receipt = build_canary_execution_receipt(
            case=case,
            canary_target_id="acsa-test-001",
            baseline_blocked=True,
            baseline_block_code="owner_mismatch",
            baseline_effect=False,
            baseline_readback="baseline-state",
            mutant_blocked=True,
            mutant_block_code="owner_mismatch",
            mutant_effect=False,
            mutant_readback="baseline-state",  # Same as baseline = no effect
            runtime_revision=TEST_REVISION,
            image_digest="sha256:abc123",
        )

        assert receipt.schema_version == SCHEMA_VERSION
        assert receipt.case_sha256 == case.case_sha256
        assert receipt.canary_target_id == "acsa-test-001"
        assert receipt.verdict == ControlMutationVerdict.MUTANT_KILLED
        assert receipt.receipt_sha256 is not None
        assert len(receipt.receipt_sha256) == 64

    def test_mutant_survived_receipt(self):
        """Mutant with effect should generate SURVIVED receipt."""
        case = make_test_case(ControlMutationOperator.OWNER_MISMATCH)

        receipt = build_canary_execution_receipt(
            case=case,
            canary_target_id="acsa-test-001",
            baseline_blocked=True,
            baseline_block_code="owner_mismatch",
            baseline_effect=False,
            baseline_readback="baseline-state",
            mutant_blocked=False,
            mutant_block_code=None,
            mutant_effect=True,
            mutant_readback="mutated-state",
            runtime_revision=TEST_REVISION,
            image_digest="sha256:abc123",
        )

        assert receipt.verdict == ControlMutationVerdict.MUTANT_SURVIVED

    def test_unverified_receipt(self):
        """Missing readback should generate UNVERIFIED receipt."""
        case = make_test_case(ControlMutationOperator.OWNER_MISMATCH)

        receipt = build_canary_execution_receipt(
            case=case,
            canary_target_id="acsa-test-001",
            baseline_blocked=True,
            baseline_block_code="owner_mismatch",
            baseline_effect=False,
            baseline_readback="baseline-state",
            mutant_blocked=True,
            mutant_block_code="owner_mismatch",
            mutant_effect=False,
            mutant_readback=None,  # No readback
            runtime_revision=TEST_REVISION,
            image_digest="sha256:abc123",
        )

        assert receipt.verdict == ControlMutationVerdict.UNVERIFIED


# ---------------------------------------------------------------------------
# Schema Version Test
# ---------------------------------------------------------------------------

class TestSchemaVersion:
    """Test schema version constant."""

    def test_schema_version_format(self):
        """Schema version should follow expected format."""
        assert SCHEMA_VERSION == "sovereign.acsa-canary-execution.v1"
        assert "v1" in SCHEMA_VERSION
