"""Tests for ACSA Canary Execution Lane.

These tests verify:
- Canary execution result generation
- Receipt generation from canary results
- Verdict determination logic
- Edge cases for mutation testing
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from backend.agent_runtime.acsa_canary_lane import (
    CanaryExecutionResult,
    execute_canary_mutation,
    generate_receipt_from_canary,
    get_execution_family_for_operator,
    is_security_operator,
    OPERATOR_EXECUTION_FAMILY,
)
from backend.agent_runtime.control_mutation_cases import build_control_mutation_case
from backend.agent_runtime.control_mutation_receipts import ControlMutationReceipt
from backend.agent_runtime.proof_verdict import canonical_proof_sha256


# Test constants
REVISION = "a" * 40
REPOSITORY = "OuroborosCollective/Sovereign-Studio-ato"
BASELINE_SHA256 = canonical_proof_sha256({"type": "baseline", "revision": REVISION})
MUTATED_SHA256 = canonical_proof_sha256({"type": "mutated", "revision": REVISION})
INPUT_SHA256 = canonical_proof_sha256({"operation": "test", "revision": REVISION})


class TestOperatorMapping:
    """Test operator to execution family mapping."""

    def test_all_v1_operators_mapped(self):
        """All V1 operators have execution family mapping."""
        from backend.agent_runtime.control_mutation_cases import ControlMutationOperator

        for op in ControlMutationOperator.values():
            family = get_execution_family_for_operator(op)
            assert family != "unknown", f"Operator {op} has no execution family"

    def test_security_operators_identified(self):
        """Security operators are correctly identified."""
        assert is_security_operator("owner_mismatch")
        assert is_security_operator("credential_replay")
        assert is_security_operator("receipt_replay")
        assert is_security_operator("nonprod_to_production")
        assert is_security_operator("disallowed_egress")
        assert not is_security_operator("stale_revision")
        assert not is_security_operator("wrong_image_digest")


class TestCanaryExecutionResult:
    """Test CanaryExecutionResult creation."""

    def test_result_allowed_to_blocked(self):
        """Result shows mutation blocked."""
        result = CanaryExecutionResult(
            case_sha256=BASELINE_SHA256,
            mutation_field="credential_owner",
            baseline_behavior="allowed",
            mutated_behavior="blocked",
            execution_error=None,
            target_readback_sha256=MUTATED_SHA256,
        )
        assert result.mutation_field == "credential_owner"
        assert result.baseline_behavior == "allowed"
        assert result.mutated_behavior == "blocked"

    def test_result_with_error(self):
        """Can create result with execution error."""
        result = CanaryExecutionResult(
            case_sha256=BASELINE_SHA256,
            mutation_field="credential_owner",
            baseline_behavior="allowed",
            mutated_behavior="error",
            execution_error="Connection refused",
            target_readback_sha256=None,
        )
        assert result.execution_error == "Connection refused"
        assert result.mutated_behavior == "error"


class TestReceiptGeneration:
    """Test receipt generation from canary results."""

    def test_mutant_killed_when_blocked(self):
        """MUTANT_KILLED when mutation is blocked."""
        case = build_control_mutation_case(
            mutation_id="test-001",
            operator="owner_mismatch",
            repository=REPOSITORY,
            repository_revision=REVISION,
            control_owner="credential_store",
            baseline_contract_sha256=BASELINE_SHA256,
            mutated_contract_sha256=MUTATED_SHA256,
            protected_operation_family="credential_binding",
            operation_input_sha256=INPUT_SHA256,
            requires_target_readback=True,
        )
        
        result = CanaryExecutionResult(
            case_sha256=case.case_sha256,
            mutation_field="credential_principal_owner",
            baseline_behavior="allowed",
            mutated_behavior="blocked",
            execution_error=None,
            target_readback_sha256=MUTATED_SHA256,
        )
        
        receipt = generate_receipt_from_canary(
            case=case,
            result=result,
            repository_revision=REVISION,
            runtime_revision=REVISION,
            image_digest="sha256:" + "b" * 64,
        )
        
        assert receipt.verdict == "MUTANT_KILLED"
        assert receipt.case_sha256 == case.case_sha256

    def test_mutant_survived_when_allowed(self):
        """MUTANT_SURVIVED when mutation is allowed (security failure)."""
        case = build_control_mutation_case(
            mutation_id="test-002",
            operator="credential_replay",
            repository=REPOSITORY,
            repository_revision=REVISION,
            control_owner="credential_store",
            baseline_contract_sha256=BASELINE_SHA256,
            mutated_contract_sha256=MUTATED_SHA256,
            protected_operation_family="credential_replay",
            operation_input_sha256=INPUT_SHA256,
            requires_target_readback=True,
        )
        
        result = CanaryExecutionResult(
            case_sha256=case.case_sha256,
            mutation_field="credential_principal_identity",
            baseline_behavior="blocked",
            mutated_behavior="allowed",
            execution_error=None,
            target_readback_sha256=MUTATED_SHA256,
        )
        
        receipt = generate_receipt_from_canary(
            case=case,
            result=result,
            repository_revision=REVISION,
        )
        
        assert receipt.verdict == "MUTANT_SURVIVED"

    def test_unverified_on_error(self):
        """UNVERIFIED when execution error."""
        case = build_control_mutation_case(
            mutation_id="test-003",
            operator="disallowed_egress",
            repository=REPOSITORY,
            repository_revision=REVISION,
            control_owner="network_policy",
            baseline_contract_sha256=BASELINE_SHA256,
            mutated_contract_sha256=MUTATED_SHA256,
            protected_operation_family="egress_policy",
            operation_input_sha256=INPUT_SHA256,
            requires_target_readback=False,
        )
        
        result = CanaryExecutionResult(
            case_sha256=case.case_sha256,
            mutation_field="network_egress",
            baseline_behavior="allowed",
            mutated_behavior="error",
            execution_error="Timeout",
            target_readback_sha256=None,
        )
        
        receipt = generate_receipt_from_canary(
            case=case,
            result=result,
            repository_revision=REVISION,
        )
        
        assert receipt.verdict == "UNVERIFIED"

    def test_contradicted_when_inconsistent(self):
        """CONTRADICTED when results are inconsistent."""
        case = build_control_mutation_case(
            mutation_id="test-004",
            operator="tool_binding_swap",
            repository=REPOSITORY,
            repository_revision=REVISION,
            control_owner="mcp_registry",
            baseline_contract_sha256=BASELINE_SHA256,
            mutated_contract_sha256=MUTATED_SHA256,
            protected_operation_family="mcp_tool_binding",
            operation_input_sha256=INPUT_SHA256,
            requires_target_readback=False,
        )
        
        # Baseline blocked, mutated error - contradictory
        result = CanaryExecutionResult(
            case_sha256=case.case_sha256,
            mutation_field="tool_binding",
            baseline_behavior="blocked",
            mutated_behavior="error",
            execution_error="Invalid tool",
            target_readback_sha256=None,
        )
        
        receipt = generate_receipt_from_canary(
            case=case,
            result=result,
            repository_revision=REVISION,
        )
        
        assert receipt.verdict == "CONTRADICTED"


class TestEdgeCases:
    """Test edge cases."""

    def test_already_blocked_mutation(self):
        """MUTANT_KILLED when baseline already blocked."""
        case = build_control_mutation_case(
            mutation_id="test-005",
            operator="nonprod_to_production",
            repository=REPOSITORY,
            repository_revision=REVISION,
            control_owner="environment_policy",
            baseline_contract_sha256=BASELINE_SHA256,
            mutated_contract_sha256=MUTATED_SHA256,
            protected_operation_family="environment_promotion",
            operation_input_sha256=INPUT_SHA256,
            requires_target_readback=False,
        )
        
        result = CanaryExecutionResult(
            case_sha256=case.case_sha256,
            mutation_field="environment_boundary",
            baseline_behavior="blocked",
            mutated_behavior="blocked",
            execution_error=None,
            target_readback_sha256=None,
        )
        
        receipt = generate_receipt_from_canary(
            case=case,
            result=result,
            repository_revision=REVISION,
        )
        
        assert receipt.verdict == "MUTANT_KILLED"
        assert receipt.observed_block_code == "ALREADY_BLOCKED"

    def test_allowed_to_allowed(self):
        """UNVERIFIED when both allowed (no mutation effect)."""
        case = build_control_mutation_case(
            mutation_id="test-006",
            operator="stale_revision",
            repository=REPOSITORY,
            repository_revision=REVISION,
            control_owner="github_access",
            baseline_contract_sha256=BASELINE_SHA256,
            mutated_contract_sha256=MUTATED_SHA256,
            protected_operation_family="revision_binding",
            operation_input_sha256=INPUT_SHA256,
            requires_target_readback=False,
        )
        
        result = CanaryExecutionResult(
            case_sha256=case.case_sha256,
            mutation_field="repository_revision",
            baseline_behavior="allowed",
            mutated_behavior="allowed",
            execution_error=None,
            target_readback_sha256=None,
        )
        
        receipt = generate_receipt_from_canary(
            case=case,
            result=result,
            repository_revision=REVISION,
        )
        
        assert receipt.verdict == "UNVERIFIED"

    def test_execution_family_for_all_operators(self):
        """All operators have execution family."""
        from backend.agent_runtime.control_mutation_cases import ControlMutationOperator

        for op in ControlMutationOperator.values():
            family = get_execution_family_for_operator(op)
            assert family in OPERATOR_EXECUTION_FAMILY.values()
