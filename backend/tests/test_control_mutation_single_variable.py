"""Tests for single-variable invariant enforcement in control mutations.

These tests verify that each operator can only change its allowed dimension
and that multi-dimensional mutants are blocked.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from backend.agent_runtime.control_mutation_cases import (
    ControlMutationOperator,
    SecurityDimension,
    build_control_mutation_case,
    get_allowed_dimension,
    validate_single_variable_invariant,
)


# ---------------------------------------------------------------------------
# Per-Operator Dimension Tests
# ---------------------------------------------------------------------------

class TestOperatorDimensions:
    """Test each operator's allowed security dimension."""

    def test_stale_revision_dimension(self):
        """STALE_REVISION may only change revision."""
        dim = get_allowed_dimension(ControlMutationOperator.STALE_REVISION)
        assert dim == SecurityDimension.REVISION

        # Valid single drift
        baseline = {
            "revision": "abc123",
            "image_digest": "sha256:def456",
            "owner": "alice",
            "tool_binding": "tool-1",
        }
        mutated = {
            "revision": "stale123",  # Changed
            "image_digest": "sha256:def456",
            "owner": "alice",
            "tool_binding": "tool-1",
        }
        valid, error = validate_single_variable_invariant(
            baseline, mutated, ControlMutationOperator.STALE_REVISION
        )
        assert valid is True

    def test_wrong_image_digest_dimension(self):
        """WRONG_IMAGE_DIGEST may only change image_digest."""
        dim = get_allowed_dimension(ControlMutationOperator.WRONG_IMAGE_DIGEST)
        assert dim == SecurityDimension.IMAGE_DIGEST

        baseline = {"revision": "abc123", "image_digest": "sha256:orig"}
        mutated = {"revision": "abc123", "image_digest": "sha256:wrong"}
        valid, error = validate_single_variable_invariant(
            baseline, mutated, ControlMutationOperator.WRONG_IMAGE_DIGEST
        )
        assert valid is True

    def test_tool_binding_swap_dimension(self):
        """TOOL_BINDING_SWAP may only change tool_binding."""
        dim = get_allowed_dimension(ControlMutationOperator.TOOL_BINDING_SWAP)
        assert dim == SecurityDimension.TOOL_BINDING

    def test_owner_mismatch_dimension(self):
        """OWNER_MISMATCH may only change owner."""
        dim = get_allowed_dimension(ControlMutationOperator.OWNER_MISMATCH)
        assert dim == SecurityDimension.OWNER

    def test_credential_replay_dimension(self):
        """CREDENTIAL_REPLAY may only change credential."""
        dim = get_allowed_dimension(ControlMutationOperator.CREDENTIAL_REPLAY)
        assert dim == SecurityDimension.CREDENTIAL

    def test_receipt_replay_dimension(self):
        """RECEIPT_REPLAY may only change receipt."""
        dim = get_allowed_dimension(ControlMutationOperator.RECEIPT_REPLAY)
        assert dim == SecurityDimension.RECEIPT

    def test_nonprod_to_production_dimension(self):
        """NONPROD_TO_PRODUCTION may only change environment."""
        dim = get_allowed_dimension(ControlMutationOperator.NONPROD_TO_PRODUCTION)
        assert dim == SecurityDimension.ENVIRONMENT

    def test_disallowed_egress_dimension(self):
        """DISALLOWED_EGRESS may only change egress_policy."""
        dim = get_allowed_dimension(ControlMutationOperator.DISALLOWED_EGRESS)
        assert dim == SecurityDimension.EGRESS_POLICY

    def test_missing_runtime_evidence_dimension(self):
        """MISSING_RUNTIME_EVIDENCE may only change runtime_evidence."""
        dim = get_allowed_dimension(ControlMutationOperator.MISSING_RUNTIME_EVIDENCE)
        assert dim == SecurityDimension.RUNTIME_EVIDENCE


# ---------------------------------------------------------------------------
# Multi-Variable Blocking Tests
# ---------------------------------------------------------------------------

class TestMultiVariableBlocking:
    """Test that multi-dimensional mutants are blocked."""

    def test_two_dimension_drift_blocked(self):
        """Two dimensions drifting must be blocked."""
        baseline = {
            "revision": "abc123",
            "owner": "alice",
        }
        mutated = {
            "revision": "stale",  # Changed
            "owner": "bob",  # Also changed!
        }

        valid, error = validate_single_variable_invariant(
            baseline, mutated, ControlMutationOperator.STALE_REVISION
        )
        assert valid is False
        assert "multi-variable mutant forbidden" in error

    def test_three_dimension_drift_blocked(self):
        """Three dimensions drifting must be blocked."""
        baseline = {
            "revision": "abc123",
            "owner": "alice",
            "image_digest": "sha256:abc",
        }
        mutated = {
            "revision": "stale",
            "owner": "bob",
            "image_digest": "sha256:def",
        }

        valid, error = validate_single_variable_invariant(
            baseline, mutated, ControlMutationOperator.STALE_REVISION
        )
        assert valid is False
        assert "multi-variable mutant forbidden" in error


# ---------------------------------------------------------------------------
# Cross-Operator Dimension Tests
# ---------------------------------------------------------------------------

class TestCrossOperatorDimensions:
    """Test that wrong dimensions are rejected for each operator."""

    def test_owner_mismatch_rejects_revision_change(self):
        """OWNER_MISMATCH rejects revision change."""
        baseline = {"revision": "abc123", "owner": "alice"}
        mutated = {"revision": "stale", "owner": "alice"}

        valid, error = validate_single_variable_invariant(
            baseline, mutated, ControlMutationOperator.OWNER_MISMATCH
        )
        assert valid is False
        assert "may only change owner" in error

    def test_credential_replay_rejects_owner_change(self):
        """CREDENTIAL_REPLAY rejects owner change."""
        baseline = {"revision": "abc123", "credential": "cred1"}
        mutated = {"revision": "abc123", "credential": "cred2"}

        # Wait - this is actually valid because credential is changing
        # Let me fix this test
        baseline = {"revision": "abc123", "owner": "alice", "credential": "cred1"}
        mutated = {"revision": "abc123", "owner": "bob", "credential": "cred1"}

        valid, error = validate_single_variable_invariant(
            baseline, mutated, ControlMutationOperator.CREDENTIAL_REPLAY
        )
        assert valid is False
        assert "may only change credential" in error


# ---------------------------------------------------------------------------
# Build Integration Tests
# ---------------------------------------------------------------------------

class TestBuildIntegration:
    """Test single-variable invariant in case building."""

    def test_build_valid_single_dimension_case(self):
        """Building a case with valid single dimension should succeed."""
        case = build_control_mutation_case(
            mutation_id="test-001",
            operator=ControlMutationOperator.STALE_REVISION,
            repository="test/repo",
            repository_revision="a" * 40,
            control_owner="test-owner",
            baseline_contract={"revision": "abc123", "owner": "alice"},
            mutated_contract={"revision": "stale123", "owner": "alice"},
            protected_operation_family="test_op",
            operation_input_sha256="b" * 64,
        )
        assert case.case_sha256 is not None

    def test_build_invalid_multi_dimension_case(self):
        """Building a case with multiple dimensions should fail."""
        with pytest.raises(Exception):
            build_control_mutation_case(
                mutation_id="test-001",
                operator=ControlMutationOperator.STALE_REVISION,
                repository="test/repo",
                repository_revision="a" * 40,
                control_owner="test-owner",
                baseline_contract={"revision": "abc123", "owner": "alice"},
                mutated_contract={"revision": "stale", "owner": "bob"},  # Two changes!
                protected_operation_family="test_op",
                operation_input_sha256="b" * 64,
            )


# ---------------------------------------------------------------------------
# Preservation Tests
# ---------------------------------------------------------------------------

class TestDimensionPreservation:
    """Test that non-mutated dimensions are preserved."""

    def test_preserved_dimensions_not_checked(self):
        """The validation only checks the mutated dimension."""
        # This test verifies the implementation handles preserved dimensions
        baseline = {
            "revision": "abc123",
            "image_digest": "sha256:def",
            "owner": "alice",
            "tool_binding": "tool-1",
            "credential": "cred1",
        }
        mutated = {
            "revision": "stale123",  # Only this changed
            "image_digest": "sha256:def",
            "owner": "alice",
            "tool_binding": "tool-1",
            "credential": "cred1",
        }

        valid, error = validate_single_variable_invariant(
            baseline, mutated, ControlMutationOperator.STALE_REVISION
        )
        assert valid is True
        # All other dimensions are preserved


# ---------------------------------------------------------------------------
# Operator Enumeration Tests
# ---------------------------------------------------------------------------

class TestOperatorEnumeration:
    """Test complete operator enumeration."""

    def test_all_operators_have_dimensions(self):
        """All operators must have defined allowed dimensions."""
        for op in ControlMutationOperator:
            dim = get_allowed_dimension(op)
            assert dim is not None
            assert isinstance(dim, SecurityDimension)

    def test_all_dimensions_covered(self):
        """All security dimensions must be assigned to operators."""
        covered_dimensions = {get_allowed_dimension(op) for op in ControlMutationOperator}
        expected_dimensions = {
            SecurityDimension.REVISION,
            SecurityDimension.IMAGE_DIGEST,
            SecurityDimension.TOOL_BINDING,
            SecurityDimension.OWNER,
            SecurityDimension.CREDENTIAL,
            SecurityDimension.RECEIPT,
            SecurityDimension.ENVIRONMENT,
            SecurityDimension.EGRESS_POLICY,
            SecurityDimension.RUNTIME_EVIDENCE,
        }
        assert covered_dimensions == expected_dimensions
