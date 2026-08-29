"""Tests for ControlMutationCase and ControlMutationOperator contracts.

These tests verify:
- Static V1 operator allowlist
- Single-variable invariant enforcement
- Canonical hash computation
- Secret-safety
- Field validation
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from backend.agent_runtime.control_mutation_cases import (
    ControlMutationCase,
    ControlMutationContractError,
    ControlMutationOperator,
    SecurityDimension,
    build_control_mutation_case,
    get_allowed_dimension,
    get_operator,
    requires_runtime_execution,
    requires_target_readback,
    validate_single_variable_invariant,
    SCHEMA_VERSION,
)


# ---------------------------------------------------------------------------
# Operator Registry Tests
# ---------------------------------------------------------------------------

class TestOperatorRegistry:
    """Test static V1 operator allowlist."""

    def test_all_operators_defined(self):
        """Verify all required operators are defined."""
        expected_operators = {
            "stale_revision",
            "wrong_image_digest",
            "tool_binding_swap",
            "owner_mismatch",
            "credential_replay",
            "receipt_replay",
            "nonprod_to_production",
            "disallowed_egress",
            "missing_runtime_evidence",
        }
        actual_operators = {op.value for op in ControlMutationOperator}
        assert actual_operators == expected_operators

    def test_unknown_operator_raises(self):
        """Unknown operators must raise ContractError."""
        with pytest.raises(ControlMutationContractError) as exc_info:
            get_operator("unknown_operator")
        assert "unknown operator" in str(exc_info.value)
        assert "Allowed:" in str(exc_info.value)

    def test_valid_operator_resolution(self):
        """Valid operators should resolve correctly."""
        op = get_operator("stale_revision")
        assert op == ControlMutationOperator.STALE_REVISION

        op = get_operator("owner_mismatch")
        assert op == ControlMutationOperator.OWNER_MISMATCH

    def test_case_sensitive_operator(self):
        """Operator lookup is case-sensitive."""
        with pytest.raises(ControlMutationContractError):
            get_operator("STALE_REVISION")

        with pytest.raises(ControlMutationContractError):
            get_operator("Stale_Revision")


# ---------------------------------------------------------------------------
# Security Dimension Tests
# ---------------------------------------------------------------------------

class TestSecurityDimensions:
    """Test single-variable invariant enforcement."""

    def test_operator_allowed_dimension_mapping(self):
        """Each operator has exactly one allowed dimension."""
        for op in ControlMutationOperator:
            dim = get_allowed_dimension(op)
            assert isinstance(dim, SecurityDimension)

    def test_stale_revision_allowed_dimension(self):
        """STALE_REVISION may change revision."""
        dim = get_allowed_dimension(ControlMutationOperator.STALE_REVISION)
        assert dim == SecurityDimension.REVISION

    def test_wrong_image_digest_allowed_dimension(self):
        """WRONG_IMAGE_DIGEST may change image digest."""
        dim = get_allowed_dimension(ControlMutationOperator.WRONG_IMAGE_DIGEST)
        assert dim == SecurityDimension.IMAGE_DIGEST

    def test_tool_binding_swap_allowed_dimension(self):
        """TOOL_BINDING_SWAP may change tool binding."""
        dim = get_allowed_dimension(ControlMutationOperator.TOOL_BINDING_SWAP)
        assert dim == SecurityDimension.TOOL_BINDING

    def test_owner_mismatch_allowed_dimension(self):
        """OWNER_MISMATCH may change owner."""
        dim = get_allowed_dimension(ControlMutationOperator.OWNER_MISMATCH)
        assert dim == SecurityDimension.OWNER


# ---------------------------------------------------------------------------
# Single-Variable Invariant Tests
# ---------------------------------------------------------------------------

class TestSingleVariableInvariant:
    """Test single-variable invariant enforcement."""

    def test_valid_single_dimension_drift(self):
        """Exactly one dimension differing is valid."""
        baseline = {"revision": "abc123", "owner": "alice"}
        mutated = {"revision": "def456", "owner": "alice"}

        valid, error = validate_single_variable_invariant(
            baseline, mutated, ControlMutationOperator.STALE_REVISION
        )
        assert valid is True
        assert error == ""

    def test_no_dimension_drift_rejected(self):
        """No differing dimensions is invalid."""
        baseline = {"revision": "abc123", "owner": "alice"}
        mutated = {"revision": "abc123", "owner": "alice"}

        valid, error = validate_single_variable_invariant(
            baseline, mutated, ControlMutationOperator.STALE_REVISION
        )
        assert valid is False
        assert "no differing dimensions" in error

    def test_multi_dimension_drift_rejected(self):
        """Multiple dimensions differing is rejected."""
        baseline = {"revision": "abc123", "owner": "alice", "image": "v1"}
        mutated = {"revision": "def456", "owner": "bob", "image": "v2"}

        valid, error = validate_single_variable_invariant(
            baseline, mutated, ControlMutationOperator.STALE_REVISION
        )
        assert valid is False
        assert "multi-variable mutant forbidden" in error
        assert "revision" in error

    def test_wrong_dimension_rejected(self):
        """Dimension other than allowed is rejected."""
        baseline = {"revision": "abc123", "owner": "alice"}
        mutated = {"revision": "abc123", "owner": "bob"}

        # STALE_REVISION can only change revision, not owner
        valid, error = validate_single_variable_invariant(
            baseline, mutated, ControlMutationOperator.STALE_REVISION
        )
        assert valid is False
        assert "may only change revision" in error

    def test_owner_mismatch_correct_dimension(self):
        """OWNER_MISMATCH changing owner is valid."""
        baseline = {"revision": "abc123", "owner": "alice"}
        mutated = {"revision": "abc123", "owner": "bob"}

        valid, error = validate_single_variable_invariant(
            baseline, mutated, ControlMutationOperator.OWNER_MISMATCH
        )
        assert valid is True


# ---------------------------------------------------------------------------
# Hash Computation Tests
# ---------------------------------------------------------------------------

class TestCanonicalHashes:
    """Test canonical hash computation."""

    def test_same_case_same_hash(self):
        """Identical cases must produce identical hashes."""
        case1 = build_control_mutation_case(
            mutation_id="test-001",
            operator=ControlMutationOperator.STALE_REVISION,
            repository="test/repo",
            repository_revision="0" * 40,
            control_owner="test-owner",
            baseline_contract={"revision": "abc123"},
            mutated_contract={"revision": "def456"},
            protected_operation_family="test_op",
            operation_input_sha256="a" * 64,
        )

        case2 = build_control_mutation_case(
            mutation_id="test-001",
            operator=ControlMutationOperator.STALE_REVISION,
            repository="test/repo",
            repository_revision="0" * 40,
            control_owner="test-owner",
            baseline_contract={"revision": "abc123"},
            mutated_contract={"revision": "def456"},
            protected_operation_family="test_op",
            operation_input_sha256="a" * 64,
        )

        assert case1.case_sha256 == case2.case_sha256

    def test_different_case_different_hash(self):
        """Different cases must produce different hashes."""
        case1 = build_control_mutation_case(
            mutation_id="test-001",
            operator=ControlMutationOperator.STALE_REVISION,
            repository="test/repo",
            repository_revision="0" * 40,
            control_owner="test-owner",
            baseline_contract={"revision": "abc123"},
            mutated_contract={"revision": "def456"},
            protected_operation_family="test_op",
            operation_input_sha256="a" * 64,
        )

        case2 = build_control_mutation_case(
            mutation_id="test-002",  # Different ID
            operator=ControlMutationOperator.STALE_REVISION,
            repository="test/repo",
            repository_revision="0" * 40,
            control_owner="test-owner",
            baseline_contract={"revision": "abc123"},
            mutated_contract={"revision": "def456"},
            protected_operation_family="test_op",
            operation_input_sha256="a" * 64,
        )

        assert case1.case_sha256 != case2.case_sha256

    def test_field_order_does_not_affect_hash(self):
        """Field ordering must not affect hash."""
        case1 = build_control_mutation_case(
            mutation_id="test-001",
            operator=ControlMutationOperator.STALE_REVISION,
            repository="test/repo",
            repository_revision="0" * 40,
            control_owner="test-owner",
            baseline_contract={"revision": "abc123", "extra": "value"},
            mutated_contract={"revision": "def456", "extra": "value"},
            protected_operation_family="test_op",
            operation_input_sha256="a" * 64,
        )

        # Same content, different key order
        case2 = build_control_mutation_case(
            mutation_id="test-001",
            operator=ControlMutationOperator.STALE_REVISION,
            repository="test/repo",
            repository_revision="0" * 40,
            control_owner="test-owner",
            baseline_contract={"extra": "value", "revision": "abc123"},
            mutated_contract={"extra": "value", "revision": "def456"},
            protected_operation_family="test_op",
            operation_input_sha256="a" * 64,
        )

        assert case1.case_sha256 == case2.case_sha256


# ---------------------------------------------------------------------------
# Validation Tests
# ---------------------------------------------------------------------------

class TestFieldValidation:
    """Test field validation."""

    def test_invalid_revision_raises(self):
        """Invalid repository revision must raise."""
        with pytest.raises(ControlMutationContractError) as exc_info:
            build_control_mutation_case(
                mutation_id="test-001",
                operator=ControlMutationOperator.STALE_REVISION,
                repository="test/repo",
                repository_revision="short",  # Not 40 chars
                control_owner="test-owner",
                baseline_contract={"revision": "abc123"},
                mutated_contract={"revision": "def456"},
                protected_operation_family="test_op",
                operation_input_sha256="a" * 64,
            )
        assert "must be a lowercase full Git SHA" in str(exc_info.value)

    def test_invalid_sha256_raises(self):
        """Invalid SHA-256 must raise."""
        with pytest.raises(ControlMutationContractError) as exc_info:
            build_control_mutation_case(
                mutation_id="test-001",
                operator=ControlMutationOperator.STALE_REVISION,
                repository="test/repo",
                repository_revision="0" * 40,
                control_owner="test-owner",
                baseline_contract={"revision": "abc123"},
                mutated_contract={"revision": "def456"},
                protected_operation_family="test_op",
                operation_input_sha256="not-a-sha256",  # Invalid
            )
        assert "must be a lowercase SHA-256" in str(exc_info.value)

    def test_invalid_identifier_raises(self):
        """Invalid identifier must raise."""
        with pytest.raises(ControlMutationContractError) as exc_info:
            build_control_mutation_case(
                mutation_id="Invalid ID!",  # Invalid characters
                operator=ControlMutationOperator.STALE_REVISION,
                repository="test/repo",
                repository_revision="0" * 40,
                control_owner="test-owner",
                baseline_contract={"revision": "abc123"},
                mutated_contract={"revision": "def456"},
                protected_operation_family="test_op",
                operation_input_sha256="a" * 64,
            )
        assert "must be a canonical identifier" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Secret Safety Tests
# ---------------------------------------------------------------------------

class TestSecretSafety:
    """Test secret-shaped field rejection."""

    def test_secret_in_baseline_rejected(self):
        """Secret-shaped fields in baseline must be rejected."""
        with pytest.raises(ControlMutationContractError) as exc_info:
            build_control_mutation_case(
                mutation_id="test-001",
                operator=ControlMutationOperator.STALE_REVISION,
                repository="test/repo",
                repository_revision="0" * 40,
                control_owner="test-owner",
                baseline_contract={"revision": "abc123", "api_key": "secret"},
                mutated_contract={"revision": "def456"},
                protected_operation_family="test_op",
                operation_input_sha256="a" * 64,
            )
        assert "secret-shaped field" in str(exc_info.value)
        assert "forbidden" in str(exc_info.value)

    def test_secret_in_mutated_rejected(self):
        """Secret-shaped fields in mutated must be rejected."""
        with pytest.raises(ControlMutationContractError) as exc_info:
            build_control_mutation_case(
                mutation_id="test-001",
                operator=ControlMutationOperator.STALE_REVISION,
                repository="test/repo",
                repository_revision="0" * 40,
                control_owner="test-owner",
                baseline_contract={"revision": "abc123"},
                mutated_contract={"revision": "def456", "token": "bearer"},
                protected_operation_family="test_op",
                operation_input_sha256="a" * 64,
            )
        assert "secret-shaped field" in str(exc_info.value)

    def test_credential_key_rejected(self):
        """Credential keys are rejected."""
        with pytest.raises(ControlMutationContractError) as exc_info:
            build_control_mutation_case(
                mutation_id="test-001",
                operator=ControlMutationOperator.STALE_REVISION,
                repository="test/repo",
                repository_revision="0" * 40,
                control_owner="test-owner",
                baseline_contract={"revision": "abc123"},
                mutated_contract={"revision": "def456", "my_credential": "value"},
                protected_operation_family="test_op",
                operation_input_sha256="a" * 64,
            )
        assert "secret-shaped field" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Forbidden Contract Value Tests
# ---------------------------------------------------------------------------

class TestForbiddenContractValues:
    """Test NaN, Infinity, float, and timestamp key rejection."""

    def test_nan_in_baseline_rejected(self):
        """NaN values in baseline contract must be rejected."""
        with pytest.raises(ControlMutationContractError) as exc_info:
            build_control_mutation_case(
                mutation_id="test-001",
                operator=ControlMutationOperator.STALE_REVISION,
                repository="test/repo",
                repository_revision="0" * 40,
                control_owner="test-owner",
                baseline_contract={"revision": float("nan")},
                mutated_contract={"revision": "def456"},
                protected_operation_family="test_op",
                operation_input_sha256="a" * 64,
            )
        assert "NaN" in str(exc_info.value)
        assert "forbidden" in str(exc_info.value)

    def test_nan_in_mutated_rejected(self):
        """NaN values in mutated contract must be rejected."""
        with pytest.raises(ControlMutationContractError) as exc_info:
            build_control_mutation_case(
                mutation_id="test-001",
                operator=ControlMutationOperator.STALE_REVISION,
                repository="test/repo",
                repository_revision="0" * 40,
                control_owner="test-owner",
                baseline_contract={"revision": "abc123"},
                mutated_contract={"revision": float("nan")},
                protected_operation_family="test_op",
                operation_input_sha256="a" * 64,
            )
        assert "NaN" in str(exc_info.value)

    def test_infinity_in_baseline_rejected(self):
        """Infinity values in baseline contract must be rejected."""
        with pytest.raises(ControlMutationContractError) as exc_info:
            build_control_mutation_case(
                mutation_id="test-001",
                operator=ControlMutationOperator.STALE_REVISION,
                repository="test/repo",
                repository_revision="0" * 40,
                control_owner="test-owner",
                baseline_contract={"revision": float("inf")},
                mutated_contract={"revision": "def456"},
                protected_operation_family="test_op",
                operation_input_sha256="a" * 64,
            )
        assert "Infinity" in str(exc_info.value)
        assert "forbidden" in str(exc_info.value)

    def test_negative_infinity_in_mutated_rejected(self):
        """Negative Infinity values in mutated contract must be rejected."""
        with pytest.raises(ControlMutationContractError) as exc_info:
            build_control_mutation_case(
                mutation_id="test-001",
                operator=ControlMutationOperator.STALE_REVISION,
                repository="test/repo",
                repository_revision="0" * 40,
                control_owner="test-owner",
                baseline_contract={"revision": "abc123"},
                mutated_contract={"revision": float("-inf")},
                protected_operation_family="test_op",
                operation_input_sha256="a" * 64,
            )
        assert "Infinity" in str(exc_info.value)

    def test_float_in_baseline_rejected(self):
        """Any float value in baseline contract must be rejected."""
        with pytest.raises(ControlMutationContractError) as exc_info:
            build_control_mutation_case(
                mutation_id="test-001",
                operator=ControlMutationOperator.STALE_REVISION,
                repository="test/repo",
                repository_revision="0" * 40,
                control_owner="test-owner",
                baseline_contract={"revision": "abc123", "score": 0.5},
                mutated_contract={"revision": "def456", "score": 0.5},
                protected_operation_family="test_op",
                operation_input_sha256="a" * 64,
            )
        assert "float" in str(exc_info.value)
        assert "forbidden" in str(exc_info.value)

    def test_float_in_nested_list_rejected(self):
        """Float values nested in lists within contracts must be rejected."""
        with pytest.raises(ControlMutationContractError) as exc_info:
            build_control_mutation_case(
                mutation_id="test-001",
                operator=ControlMutationOperator.STALE_REVISION,
                repository="test/repo",
                repository_revision="0" * 40,
                control_owner="test-owner",
                baseline_contract={"revision": "abc123", "tags": [1.0, 2.0]},
                mutated_contract={"revision": "def456", "tags": [1.0, 2.0]},
                protected_operation_family="test_op",
                operation_input_sha256="a" * 64,
            )
        assert "float" in str(exc_info.value)

    def test_timestamp_key_in_baseline_rejected(self):
        """Timestamp-shaped keys in baseline contract must be rejected."""
        with pytest.raises(ControlMutationContractError) as exc_info:
            build_control_mutation_case(
                mutation_id="test-001",
                operator=ControlMutationOperator.STALE_REVISION,
                repository="test/repo",
                repository_revision="0" * 40,
                control_owner="test-owner",
                baseline_contract={"revision": "abc123", "timestamp": "2024-01-01"},
                mutated_contract={"revision": "def456"},
                protected_operation_family="test_op",
                operation_input_sha256="a" * 64,
            )
        assert "timestamp-shaped field" in str(exc_info.value)
        assert "forbidden" in str(exc_info.value)

    def test_created_at_key_in_mutated_rejected(self):
        """'created_at' keys in mutated contract must be rejected."""
        with pytest.raises(ControlMutationContractError) as exc_info:
            build_control_mutation_case(
                mutation_id="test-001",
                operator=ControlMutationOperator.STALE_REVISION,
                repository="test/repo",
                repository_revision="0" * 40,
                control_owner="test-owner",
                baseline_contract={"revision": "abc123"},
                mutated_contract={"revision": "def456", "created_at": "2024-01-01"},
                protected_operation_family="test_op",
                operation_input_sha256="a" * 64,
            )
        assert "timestamp-shaped field" in str(exc_info.value)

    def test_updated_at_key_rejected(self):
        """'updated_at' keys in contracts must be rejected."""
        with pytest.raises(ControlMutationContractError) as exc_info:
            build_control_mutation_case(
                mutation_id="test-001",
                operator=ControlMutationOperator.STALE_REVISION,
                repository="test/repo",
                repository_revision="0" * 40,
                control_owner="test-owner",
                baseline_contract={"revision": "abc123", "updated_at": "2024-01-01"},
                mutated_contract={"revision": "def456"},
                protected_operation_family="test_op",
                operation_input_sha256="a" * 64,
            )
        assert "timestamp-shaped field" in str(exc_info.value)

    def test_integer_values_accepted(self):
        """Integer values in contracts are accepted (no float rejection)."""
        case = build_control_mutation_case(
            mutation_id="test-001",
            operator=ControlMutationOperator.STALE_REVISION,
            repository="test/repo",
            repository_revision="0" * 40,
            control_owner="test-owner",
            baseline_contract={"revision": "abc123", "priority": 50},
            mutated_contract={"revision": "def456", "priority": 50},
            protected_operation_family="test_op",
            operation_input_sha256="a" * 64,
        )
        assert case.baseline_contract_sha256  # no error raised


# ---------------------------------------------------------------------------
# Requirements Tests
# ---------------------------------------------------------------------------

class TestRequirements:
    """Test runtime execution and target readback requirements."""

    def test_most_operators_require_runtime(self):
        """Most V1 operators require runtime execution."""
        # MISSING_RUNTIME_EVIDENCE doesn't require runtime as it's about missing evidence
        for op in ControlMutationOperator:
            if op != ControlMutationOperator.MISSING_RUNTIME_EVIDENCE:
                assert requires_runtime_execution(op) is True

    def test_missing_runtime_evidence_no_runtime(self):
        """MISSING_RUNTIME_EVIDENCE doesn't require runtime."""
        assert requires_runtime_execution(ControlMutationOperator.MISSING_RUNTIME_EVIDENCE) is False

    def test_all_operators_require_target_readback(self):
        """All V1 operators require target readback for MUTANT_KILLED."""
        for op in ControlMutationOperator:
            assert requires_target_readback(op) is True


# ---------------------------------------------------------------------------
# Schema Version Tests
# ---------------------------------------------------------------------------

class TestSchemaVersion:
    """Test schema version enforcement."""

    def test_correct_schema_version(self):
        """Correct schema version is accepted."""
        case = build_control_mutation_case(
            mutation_id="test-001",
            operator=ControlMutationOperator.STALE_REVISION,
            repository="test/repo",
            repository_revision="0" * 40,
            control_owner="test-owner",
            baseline_contract={"revision": "abc123"},
            mutated_contract={"revision": "def456"},
            protected_operation_family="test_op",
            operation_input_sha256="a" * 64,
        )
        assert case.schema_version == SCHEMA_VERSION

    def test_case_serialization(self):
        """Case can be serialized to canonical body."""
        case = build_control_mutation_case(
            mutation_id="test-001",
            operator=ControlMutationOperator.STALE_REVISION,
            repository="test/repo",
            repository_revision="0" * 40,
            control_owner="test-owner",
            baseline_contract={"revision": "abc123"},
            mutated_contract={"revision": "def456"},
            protected_operation_family="test_op",
            operation_input_sha256="a" * 64,
        )

        body = case.canonical_body()
        assert body["schema_version"] == SCHEMA_VERSION
        assert body["mutation_id"] == "test-001"
        assert body["operator"] == "stale_revision"
        assert body["requires_runtime_execution"] is True
        assert body["requires_target_readback"] is True


# ---------------------------------------------------------------------------
# Contract Integrity Tests
# ---------------------------------------------------------------------------

class TestContractIntegrity:
    """Test contract integrity checks."""

    def test_mismatch_case_sha256_raises(self):
        """Mismatched case_sha256 must raise."""
        case = build_control_mutation_case(
            mutation_id="test-001",
            operator=ControlMutationOperator.STALE_REVISION,
            repository="test/repo",
            repository_revision="a" * 40,
            control_owner="test-owner",
            baseline_contract={"revision": "abc123"},
            mutated_contract={"revision": "def456"},
            protected_operation_family="test_op",
            operation_input_sha256="b" * 64,
        )

        # Manually create with wrong hash - use valid format but wrong value
        with pytest.raises(ControlMutationContractError) as exc_info:
            ControlMutationCase(
                schema_version=case.schema_version,
                mutation_id=case.mutation_id,
                operator=case.operator,
                repository=case.repository,
                repository_revision=case.repository_revision,
                control_owner=case.control_owner,
                baseline_contract_sha256=case.baseline_contract_sha256,
                mutated_contract_sha256=case.mutated_contract_sha256,
                protected_operation_family=case.protected_operation_family,
                operation_input_sha256=case.operation_input_sha256,
                expected_block_code=case.expected_block_code,
                requires_runtime_execution=case.requires_runtime_execution,
                requires_target_readback=case.requires_target_readback,
                case_sha256="b" * 64,  # Different valid hash
            )
        assert "case_sha256 mismatch" in str(exc_info.value)
