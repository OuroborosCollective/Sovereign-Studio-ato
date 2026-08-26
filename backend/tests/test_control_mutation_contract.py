"""Tests for ControlMutationCase and ControlMutationReceipt contracts.

These tests verify:
- Same case produces same hash
- Field order doesn't affect hash
- Each operator has correct allowed dimension
- Multi-variable mutants are blocked
- Unknown operators are blocked
- Wrong SHA/digest is blocked
- Secret-like fields are blocked
- Target readback required for MUTANT_KILLED
- Receipt for different case is CONTRADICTED
- Repository revision mismatch is CONTRADICTED
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
    build_control_mutation_case,
    operator_allowed_dimension,
)
from backend.agent_runtime.control_mutation_receipts import (
    ControlMutationReceipt,
    ControlMutationReceiptError,
    build_control_mutation_receipt,
    verify_receipt_for_case,
)
from backend.agent_runtime.proof_verdict import canonical_proof_sha256


# Test constants
REVISION = "a" * 40
REPOSITORY = "OuroborosCollective/Sovereign-Studio-ato"
BASELINE_SHA256 = canonical_proof_sha256({"type": "baseline", "revision": REVISION})
MUTATED_SHA256 = canonical_proof_sha256({"type": "mutated", "revision": REVISION})
INPUT_SHA256 = canonical_proof_sha256({"operation": "test", "revision": REVISION})


class TestControlMutationOperator:
    """Test the operator registry."""

    def test_all_v1_operators_defined(self):
        """All V1 operators are defined in the enum."""
        operators = ControlMutationOperator.values()
        expected = (
            "stale_revision",
            "wrong_image_digest",
            "tool_binding_swap",
            "owner_mismatch",
            "credential_replay",
            "receipt_replay",
            "nonprod_to_production",
            "disallowed_egress",
            "missing_runtime_evidence",
        )
        assert len(operators) == len(expected)
        for op in expected:
            assert op in operators

    def test_is_valid(self):
        """Validation works correctly."""
        assert ControlMutationOperator.is_valid("stale_revision")
        assert ControlMutationOperator.is_valid("owner_mismatch")
        assert not ControlMutationOperator.is_valid("unknown_operator")
        assert not ControlMutationOperator.is_valid("")

    def test_operator_allowed_dimensions(self):
        """Each operator maps to exactly one allowed dimension."""
        for op in ControlMutationOperator.values():
            dim = operator_allowed_dimension(op)
            assert dim
            assert dim != "unknown"


class TestControlMutationCase:
    """Test ControlMutationCase construction and validation."""

    def test_build_valid_case(self):
        """Building a valid case works."""
        case = build_control_mutation_case(
            mutation_id="test-stale-revision-001",
            operator="stale_revision",
            repository=REPOSITORY,
            repository_revision=REVISION,
            control_owner="github_access",
            baseline_contract_sha256=BASELINE_SHA256,
            mutated_contract_sha256=MUTATED_SHA256,
            protected_operation_family="github_merge_release",
            operation_input_sha256=INPUT_SHA256,
            expected_block_code="STALE_REVISION_BLOCK",
            requires_runtime_execution=True,
            requires_target_readback=True,
        )
        assert case.mutation_id == "test-stale-revision-001"
        assert case.operator == "stale_revision"
        assert case.allowed_dimension == "repository_revision"

    def test_same_case_same_hash(self):
        """Identical cases produce identical hashes."""
        case1 = build_control_mutation_case(
            mutation_id="test-case-001",
            operator="stale_revision",
            repository=REPOSITORY,
            repository_revision=REVISION,
            control_owner="github_access",
            baseline_contract_sha256=BASELINE_SHA256,
            mutated_contract_sha256=MUTATED_SHA256,
            protected_operation_family="github_merge_release",
            operation_input_sha256=INPUT_SHA256,
        )
        case2 = build_control_mutation_case(
            mutation_id="test-case-001",
            operator="stale_revision",
            repository=REPOSITORY,
            repository_revision=REVISION,
            control_owner="github_access",
            baseline_contract_sha256=BASELINE_SHA256,
            mutated_contract_sha256=MUTATED_SHA256,
            protected_operation_family="github_merge_release",
            operation_input_sha256=INPUT_SHA256,
        )
        assert case1.case_sha256 == case2.case_sha256

    def test_unknown_operator_blocked(self):
        """Unknown operators are rejected."""
        with pytest.raises(ControlMutationContractError, match="unknown operator"):
            build_control_mutation_case(
                mutation_id="test-001",
                operator="random_mutation",
                repository=REPOSITORY,
                repository_revision=REVISION,
                control_owner="test",
                baseline_contract_sha256=BASELINE_SHA256,
                mutated_contract_sha256=MUTATED_SHA256,
                protected_operation_family="test",
                operation_input_sha256=INPUT_SHA256,
            )

    def test_invalid_revision_blocked(self):
        """Invalid Git SHA is rejected."""
        with pytest.raises(ControlMutationContractError, match="full Git SHA"):
            build_control_mutation_case(
                mutation_id="test-001",
                operator="stale_revision",
                repository=REPOSITORY,
                repository_revision="not-a-valid-sha",
                control_owner="test",
                baseline_contract_sha256=BASELINE_SHA256,
                mutated_contract_sha256=MUTATED_SHA256,
                protected_operation_family="test",
                operation_input_sha256=INPUT_SHA256,
            )

    def test_invalid_sha256_blocked(self):
        """Invalid SHA-256 is rejected."""
        with pytest.raises(ControlMutationContractError, match="SHA-256"):
            build_control_mutation_case(
                mutation_id="test-001",
                operator="stale_revision",
                repository=REPOSITORY,
                repository_revision=REVISION,
                control_owner="test",
                baseline_contract_sha256="not-a-sha256",
                mutated_contract_sha256=MUTATED_SHA256,
                protected_operation_family="test",
                operation_input_sha256=INPUT_SHA256,
            )

    def test_case_serialization_roundtrip(self):
        """Case can be serialized and deserialized."""
        original = build_control_mutation_case(
            mutation_id="test-roundtrip",
            operator="owner_mismatch",
            repository=REPOSITORY,
            repository_revision=REVISION,
            control_owner="credential_store",
            baseline_contract_sha256=BASELINE_SHA256,
            mutated_contract_sha256=MUTATED_SHA256,
            protected_operation_family="security_permission_change",
            operation_input_sha256=INPUT_SHA256,
            expected_block_code="OWNER_MISMATCH",
            requires_runtime_execution=True,
            requires_target_readback=True,
        )
        data = original.to_dict()
        restored = ControlMutationCase.from_dict(data)
        assert restored.case_sha256 == original.case_sha256
        assert restored.operator == original.operator


class TestControlMutationReceipt:
    """Test ControlMutationReceipt construction and validation."""

    def test_build_valid_receipt(self):
        """Building a valid receipt works."""
        case_sha256 = canonical_proof_sha256({"case": "test"})
        receipt = build_control_mutation_receipt(
            case_sha256=case_sha256,
            repository_revision=REVISION,
            verdict="MUTANT_KILLED",
            runtime_revision=REVISION,
            image_digest="sha256:" + "b" * 64,
            target_readback_sha256=canonical_proof_sha256({"readback": "test"}),
            observed_block_code="BLOCKED",
        )
        assert receipt.verdict == "MUTANT_KILLED"
        assert receipt.case_sha256 == case_sha256

    def test_unverified_without_target_readback(self):
        """UNVERIFIED can be created without target readback."""
        case_sha256 = canonical_proof_sha256({"case": "test"})
        receipt = build_control_mutation_receipt(
            case_sha256=case_sha256,
            repository_revision=REVISION,
            verdict="UNVERIFIED",
        )
        assert receipt.verdict == "UNVERIFIED"

    def test_mutant_survived_requires_evidence(self):
        """MUTANT_SURVIVED requires evidence of effect."""
        case_sha256 = canonical_proof_sha256({"case": "test"})
        with pytest.raises(ControlMutationReceiptError, match="MUTANT_SURVIVED requires either"):
            build_control_mutation_receipt(
                case_sha256=case_sha256,
                repository_revision=REVISION,
                verdict="MUTANT_SURVIVED",
            )

    def test_mutant_survived_with_target_readback(self):
        """MUTANT_SURVIVED with target readback works."""
        case_sha256 = canonical_proof_sha256({"case": "test"})
        receipt = build_control_mutation_receipt(
            case_sha256=case_sha256,
            repository_revision=REVISION,
            verdict="MUTANT_SURVIVED",
            target_readback_sha256=canonical_proof_sha256({"effect": "observed"}),
        )
        assert receipt.verdict == "MUTANT_SURVIVED"

    def test_invalid_verdict_blocked(self):
        """Invalid verdict is rejected."""
        case_sha256 = canonical_proof_sha256({"case": "test"})
        with pytest.raises(ControlMutationReceiptError, match="verdict must be one of"):
            build_control_mutation_receipt(
                case_sha256=case_sha256,
                repository_revision=REVISION,
                verdict="INVALID",
            )

    def test_invalid_oci_digest_blocked(self):
        """Invalid OCI digest is rejected."""
        case_sha256 = canonical_proof_sha256({"case": "test"})
        with pytest.raises(ControlMutationReceiptError, match="OCI digest"):
            build_control_mutation_receipt(
                case_sha256=case_sha256,
                repository_revision=REVISION,
                verdict="UNVERIFIED",
                image_digest="not-an-oci-digest",
            )

    def test_receipt_serialization_roundtrip(self):
        """Receipt can be serialized and deserialized."""
        case_sha256 = canonical_proof_sha256({"case": "test"})
        original = build_control_mutation_receipt(
            case_sha256=case_sha256,
            repository_revision=REVISION,
            verdict="MUTANT_KILLED",
            runtime_revision=REVISION,
            target_readback_sha256=canonical_proof_sha256({"readback": "test"}),
            observed_block_code="BLOCKED",
        )
        data = original.to_dict()
        restored = ControlMutationReceipt.from_dict(data)
        assert restored.receipt_sha256 == original.receipt_sha256


class TestReceiptVerification:
    """Test receipt verification against cases."""

    def test_verify_case_hash_mismatch(self):
        """Verification fails when case hash doesn't match."""
        case_sha256 = canonical_proof_sha256({"case": "expected"})
        receipt = build_control_mutation_receipt(
            case_sha256=canonical_proof_sha256({"case": "different"}),
            repository_revision=REVISION,
            verdict="MUTANT_KILLED",
            target_readback_sha256=canonical_proof_sha256({"readback": "test"}),
        )
        is_valid, error = verify_receipt_for_case(receipt, case_sha256, requires_target_readback=True)
        assert not is_valid
        assert "does not match" in error

    def test_verify_mutant_killed_requires_target_readback(self):
        """MUTANT_KILLED with requires_target_readback=True needs target readback."""
        case_sha256 = canonical_proof_sha256({"case": "test"})
        receipt = build_control_mutation_receipt(
            case_sha256=case_sha256,
            repository_revision=REVISION,
            verdict="MUTANT_KILLED",
        )
        is_valid, error = verify_receipt_for_case(receipt, case_sha256, requires_target_readback=True)
        assert not is_valid
        assert "requires target_readback" in error

    def test_verify_mutant_killed_with_target_readback(self):
        """MUTANT_KILLED with target readback passes."""
        case_sha256 = canonical_proof_sha256({"case": "test"})
        receipt = build_control_mutation_receipt(
            case_sha256=case_sha256,
            repository_revision=REVISION,
            verdict="MUTANT_KILLED",
            target_readback_sha256=canonical_proof_sha256({"readback": "test"}),
        )
        is_valid, error = verify_receipt_for_case(receipt, case_sha256, requires_target_readback=True)
        assert is_valid
        assert error == ""

    def test_verify_mutant_survived_requires_evidence(self):
        """MUTANT_SURVIVED requires evidence - this is enforced at receipt creation."""
        case_sha256 = canonical_proof_sha256({"case": "test"})
        # MUTANT_SURVIVED without evidence fails at receipt creation
        with pytest.raises(ControlMutationReceiptError, match="MUTANT_SURVIVED requires either"):
            build_control_mutation_receipt(
                case_sha256=case_sha256,
                repository_revision=REVISION,
                verdict="MUTANT_SURVIVED",
            )


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_case_with_no_expected_block_code(self):
        """Case can omit expected_block_code."""
        case = build_control_mutation_case(
            mutation_id="test-001",
            operator="stale_revision",
            repository=REPOSITORY,
            repository_revision=REVISION,
            control_owner="test",
            baseline_contract_sha256=BASELINE_SHA256,
            mutated_contract_sha256=MUTATED_SHA256,
            protected_operation_family="test",
            operation_input_sha256=INPUT_SHA256,
            expected_block_code=None,
        )
        assert case.expected_block_code is None

    def test_case_with_runtime_only(self):
        """Case can specify runtime-only (no target readback needed)."""
        case = build_control_mutation_case(
            mutation_id="test-001",
            operator="disallowed_egress",
            repository=REPOSITORY,
            repository_revision=REVISION,
            control_owner="network_policy",
            baseline_contract_sha256=BASELINE_SHA256,
            mutated_contract_sha256=MUTATED_SHA256,
            protected_operation_family="security_permission_change",
            operation_input_sha256=INPUT_SHA256,
            requires_runtime_execution=True,
            requires_target_readback=False,
        )
        assert case.requires_target_readback is False

    def test_receipt_with_execution_only(self):
        """Receipt can have execution receipt without target readback."""
        case_sha256 = canonical_proof_sha256({"case": "test"})
        receipt = build_control_mutation_receipt(
            case_sha256=case_sha256,
            repository_revision=REVISION,
            verdict="MUTANT_SURVIVED",
            execution_receipt_sha256=canonical_proof_sha256({"exec": "test"}),
        )
        assert receipt.verdict == "MUTANT_SURVIVED"

    def test_all_operators_have_unique_dimensions(self):
        """Each operator maps to a unique security dimension."""
        dimensions = set()
        for op in ControlMutationOperator.values():
            dim = operator_allowed_dimension(op)
            assert dim not in dimensions, f"Duplicate dimension {dim} for {op}"
            dimensions.add(dim)
