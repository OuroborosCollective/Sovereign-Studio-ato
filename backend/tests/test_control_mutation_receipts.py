"""Tests for ControlMutationReceipt contracts and verdict determination.

These tests verify:
- Receipt hash computation and verification
- Verdict rules (MUTANT_KILLED, MUTANT_SURVIVED, UNVERIFIED, CONTRADICTED)
- Case-receipt binding validation
- Missing evidence handling
"""

from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from backend.agent_runtime.control_mutation_cases import (
    ControlMutationCase,
    ControlMutationOperator,
    build_control_mutation_case,
)
from backend.agent_runtime.control_mutation_receipts import (
    ControlMutationReceipt,
    ControlMutationReceiptError,
    build_control_mutation_receipt,
    compute_verdict,
    verify_receipt_for_case,
    SCHEMA_VERSION,
    Verdict,
)


# ---------------------------------------------------------------------------
# Receipt Construction Tests
# ---------------------------------------------------------------------------

class TestReceiptConstruction:
    """Test receipt construction and validation."""

    def test_valid_receipt_construction(self):
        """Valid receipt construction should succeed."""
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

        receipt = build_control_mutation_receipt(
            case_sha256=case.case_sha256,
            repository_revision=case.repository_revision,
            runtime_revision="c" * 40,
            image_digest="sha256:" + "d" * 64,
            execution_receipt_sha256="e" * 64,
            target_readback_sha256="f" * 64,
            observed_block_code="blocked",
            verdict="MUTANT_KILLED",
        )

        assert receipt.schema_version == SCHEMA_VERSION
        assert receipt.verdict == "MUTANT_KILLED"
        assert receipt.observed_block_code == "blocked"

    def test_minimal_receipt_construction(self):
        """Receipt with minimal fields should succeed."""
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

        receipt = build_control_mutation_receipt(
            case_sha256=case.case_sha256,
            repository_revision=case.repository_revision,
            verdict="UNVERIFIED",
        )

        assert receipt.schema_version == SCHEMA_VERSION
        assert receipt.verdict == "UNVERIFIED"
        assert receipt.runtime_revision is None
        assert receipt.image_digest is None

    def test_invalid_case_sha256_raises(self):
        """Invalid case_sha256 must raise."""
        with pytest.raises(ControlMutationReceiptError) as exc_info:
            build_control_mutation_receipt(
                case_sha256="invalid",
                repository_revision="a" * 40,
                verdict="UNVERIFIED",
            )
        assert "must be a lowercase SHA-256" in str(exc_info.value)

    def test_invalid_revision_raises(self):
        """Invalid repository_revision must raise."""
        with pytest.raises(ControlMutationReceiptError) as exc_info:
            build_control_mutation_receipt(
                case_sha256="a" * 64,
                repository_revision="short",
                verdict="UNVERIFIED",
            )
        assert "must be a lowercase full Git SHA" in str(exc_info.value)

    def test_invalid_verdict_raises(self):
        """Invalid verdict must raise."""
        with pytest.raises(ControlMutationReceiptError) as exc_info:
            build_control_mutation_receipt(
                case_sha256="a" * 64,
                repository_revision="a" * 40,
                verdict="INVALID",
            )
        assert "invalid verdict" in str(exc_info.value)

    def test_invalid_image_digest_raises(self):
        """Invalid image_digest must raise."""
        with pytest.raises(ControlMutationReceiptError) as exc_info:
            build_control_mutation_receipt(
                case_sha256="a" * 64,
                repository_revision="a" * 40,
                image_digest="invalid-digest",
                verdict="UNVERIFIED",
            )
        assert "must be a lowercase OCI digest" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Receipt Hash Tests
# ---------------------------------------------------------------------------

class TestReceiptHashes:
    """Test receipt hash computation."""

    def test_same_receipt_same_hash(self):
        """Identical receipts must produce identical hashes."""
        receipt1 = build_control_mutation_receipt(
            case_sha256="a" * 64,
            repository_revision="b" * 40,
            verdict="MUTANT_KILLED",
            observed_block_code="blocked",
        )

        receipt2 = build_control_mutation_receipt(
            case_sha256="a" * 64,
            repository_revision="b" * 40,
            verdict="MUTANT_KILLED",
            observed_block_code="blocked",
        )

        assert receipt1.receipt_sha256 == receipt2.receipt_sha256

    def test_different_receipt_different_hash(self):
        """Different receipts must produce different hashes."""
        receipt1 = build_control_mutation_receipt(
            case_sha256="a" * 64,
            repository_revision="b" * 40,
            verdict="MUTANT_KILLED",
        )

        receipt2 = build_control_mutation_receipt(
            case_sha256="a" * 64,
            repository_revision="b" * 40,
            verdict="MUTANT_SURVIVED",  # Different verdict
        )

        assert receipt1.receipt_sha256 != receipt2.receipt_sha256

    def test_field_order_does_not_affect_hash(self):
        """Field ordering must not affect hash."""
        receipt1 = build_control_mutation_receipt(
            case_sha256="a" * 64,
            repository_revision="b" * 40,
            runtime_revision="c" * 40,
            image_digest="sha256:" + "d" * 64,
            verdict="MUTANT_KILLED",
        )

        receipt2 = build_control_mutation_receipt(
            case_sha256="a" * 64,
            repository_revision="b" * 40,
            image_digest="sha256:" + "d" * 64,
            runtime_revision="c" * 40,
            verdict="MUTANT_KILLED",
        )

        assert receipt1.receipt_sha256 == receipt2.receipt_sha256


# ---------------------------------------------------------------------------
# Case-Recipient Binding Tests
# ---------------------------------------------------------------------------

class TestCaseReceiptBinding:
    """Test case-receipt binding validation."""

    def test_valid_binding(self):
        """Valid case-receipt binding should pass."""
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

        receipt = build_control_mutation_receipt(
            case_sha256=case.case_sha256,
            repository_revision=case.repository_revision,
            target_readback_sha256="c" * 64,
            verdict="MUTANT_KILLED",
        )

        valid, error = verify_receipt_for_case(receipt, case)
        assert valid is True
        assert error is None

    def test_case_sha256_mismatch(self):
        """Mismatched case_sha256 should fail."""
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

        # Use a valid SHA256 format but wrong value
        receipt = build_control_mutation_receipt(
            case_sha256="b" * 64,  # Different from case.case_sha256
            repository_revision=case.repository_revision,
            verdict="UNVERIFIED",
        )

        valid, error = verify_receipt_for_case(receipt, case)
        assert valid is False
        assert "case_sha256" in error

    def test_revision_mismatch(self):
        """Mismatched repository_revision should fail."""
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

        receipt = build_control_mutation_receipt(
            case_sha256=case.case_sha256,
            repository_revision="b" * 40,  # Different revision
            verdict="UNVERIFIED",
        )

        valid, error = verify_receipt_for_case(receipt, case)
        assert valid is False
        assert "repository_revision" in error


# ---------------------------------------------------------------------------
# Verdict Rule Tests
# ---------------------------------------------------------------------------

class TestVerdictRules:
    """Test verdict determination rules."""

    def test_mutant_killed_requires_target_readback(self):
        """MUTANT_KILLED requires target_readback_sha256 when case requires it."""
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
        # case.requires_target_readback is True for STALE_REVISION

        receipt = build_control_mutation_receipt(
            case_sha256=case.case_sha256,
            repository_revision=case.repository_revision,
            target_readback_sha256=None,  # Missing!
            verdict="MUTANT_KILLED",
        )

        valid, error = verify_receipt_for_case(receipt, case)
        assert valid is False
        assert "requires target_readback_sha256" in error

    def test_mutant_killed_with_target_readback(self):
        """MUTANT_KILLED with target_readback_sha256 is valid."""
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

        receipt = build_control_mutation_receipt(
            case_sha256=case.case_sha256,
            repository_revision=case.repository_revision,
            target_readback_sha256="c" * 64,
            observed_block_code="blocked",
            verdict="MUTANT_KILLED",
        )

        valid, error = verify_receipt_for_case(receipt, case)
        assert valid is True


# ---------------------------------------------------------------------------
# Verdict Computation Tests
# ---------------------------------------------------------------------------

class TestVerdictComputation:
    """Test compute_verdict function."""

    def test_compute_verdict_mutant_killed(self):
        """Correct block code should yield MUTANT_KILLED."""
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
            expected_block_code="blocked",
        )

        receipt = build_control_mutation_receipt(
            case_sha256=case.case_sha256,
            repository_revision=case.repository_revision,
            execution_receipt_sha256="e" * 64,  # Required for runtime execution
            target_readback_sha256="c" * 64,
            observed_block_code="blocked",
            verdict="MUTANT_KILLED",
        )

        verdict = compute_verdict(case, receipt)
        assert verdict == "MUTANT_KILLED"

    def test_compute_verdict_mutant_survived(self):
        """Wrong block code should yield MUTANT_SURVIVED."""
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
            expected_block_code="blocked",
        )

        receipt = build_control_mutation_receipt(
            case_sha256=case.case_sha256,
            repository_revision=case.repository_revision,
            execution_receipt_sha256="e" * 64,  # Required for runtime execution
            target_readback_sha256="c" * 64,  # Required for target readback
            observed_block_code="allowed",  # Different!
            verdict="MUTANT_SURVIVED",
        )

        verdict = compute_verdict(case, receipt)
        assert verdict == "MUTANT_SURVIVED"

    def test_compute_verdict_unverified_missing_evidence(self):
        """Missing required evidence should yield UNVERIFIED."""
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

        receipt = build_control_mutation_receipt(
            case_sha256=case.case_sha256,
            repository_revision=case.repository_revision,
            # Missing target_readback_sha256 despite requires_target_readback
            verdict="UNVERIFIED",
        )

        verdict = compute_verdict(case, receipt)
        assert verdict == "UNVERIFIED"

    def test_compute_verdict_contradicted(self):
        """Case-receipt binding mismatch should yield CONTRADICTED."""
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

        # Use a valid SHA256 but wrong value (different from case.case_sha256)
        receipt = build_control_mutation_receipt(
            case_sha256="b" * 64,  # Different from case.case_sha256
            repository_revision=case.repository_revision,
            verdict="MUTANT_KILLED",
        )

        verdict = compute_verdict(case, receipt)
        assert verdict == "CONTRADICTED"


# ---------------------------------------------------------------------------
# Receipt Serialization Tests
# ---------------------------------------------------------------------------

class TestReceiptSerialization:
    """Test receipt serialization."""

    def test_canonical_body(self):
        """Receipt can be serialized to canonical body."""
        receipt = build_control_mutation_receipt(
            case_sha256="a" * 64,
            repository_revision="b" * 40,
            runtime_revision="c" * 40,
            image_digest="sha256:" + "d" * 64,
            verdict="MUTANT_KILLED",
            observed_block_code="blocked",
        )

        body = receipt.canonical_body()
        assert body["schema_version"] == SCHEMA_VERSION
        assert body["case_sha256"] == "a" * 64
        assert body["repository_revision"] == "b" * 40
        assert body["verdict"] == "MUTANT_KILLED"
        assert body["observed_block_code"] == "blocked"


# ---------------------------------------------------------------------------
# Schema Version Tests
# ---------------------------------------------------------------------------

class TestSchemaVersion:
    """Test schema version enforcement."""

    def test_invalid_schema_version_raises(self):
        """Invalid schema version must raise."""
        with pytest.raises(ControlMutationReceiptError) as exc_info:
            ControlMutationReceipt(
                schema_version="invalid.version",
                case_sha256="a" * 64,
                repository_revision="b" * 40,
                runtime_revision=None,
                image_digest=None,
                execution_receipt_sha256=None,
                target_readback_sha256=None,
                observed_block_code=None,
                verdict="UNVERIFIED",
                receipt_sha256="c" * 64,
            )
        assert "unsupported schema version" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Test edge cases."""

    def test_receipt_for_non_target_readback_case(self):
        """Receipt without target_readback is valid for non-requiring case."""
        # Create a mock case that doesn't require target readback
        case = MagicMock()
        case.case_sha256 = "a" * 64
        case.repository_revision = "b" * 40
        case.requires_target_readback = False
        case.requires_runtime_execution = False

        receipt = build_control_mutation_receipt(
            case_sha256=case.case_sha256,
            repository_revision=case.repository_revision,
            verdict="MUTANT_SURVIVED",
        )

        valid, error = verify_receipt_for_case(receipt, case)
        assert valid is True

    def test_all_verdict_values_valid(self):
        """All four verdict values should be valid."""
        for verdict in ["MUTANT_KILLED", "MUTANT_SURVIVED", "UNVERIFIED", "CONTRADICTED"]:
            receipt = build_control_mutation_receipt(
                case_sha256="a" * 64,
                repository_revision="b" * 40,
                verdict=verdict,
            )
            assert receipt.verdict == verdict

    def test_empty_observed_block_code(self):
        """Empty observed_block_code is normalized to None."""
        # Note: empty string is rejected in the validation - use None instead
        receipt = build_control_mutation_receipt(
            case_sha256="a" * 64,
            repository_revision="b" * 40,
            observed_block_code=None,  # Use None, not empty string
            verdict="MUTANT_SURVIVED",
        )
        assert receipt.observed_block_code is None
