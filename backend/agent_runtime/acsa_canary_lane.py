"""ACSA Canary Execution Lane - Runtime mutation testing against protected paths.

This module provides the execution lane for testing ControlMutationCase against
the existing environment/identity/egress contracts. It runs mutations against
disposable canary targets and generates ControlMutationReceipt.

Reference: Issue #1639 (ACSA 2/4)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Optional

from .control_mutation_cases import (
    ControlMutationCase,
    ControlMutationOperator,
    operator_allowed_dimension,
)
from .control_mutation_receipts import (
    ControlMutationReceipt,
    build_control_mutation_receipt,
    verify_receipt_for_case,
)
from .proof_verdict import canonical_proof_sha256


# V1 Canary operator family mapping
# Maps ControlMutationOperator to the environment contract field/path it mutates
_OPERATOR_MUTATION_FIELD: dict[str, str] = {
    "owner_mismatch": "credential_owner",
    "tool_binding_swap": "tool_binding",
    "credential_replay": "credential_identity",
    "receipt_replay": "execution_receipt",
    "nonprod_to_production": "environment_promotion",
    "disallowed_egress": "egress_policy",
    "stale_revision": "revision",
    "wrong_image_digest": "image_digest",
    "missing_runtime_evidence": "evidence_completeness",
}


@dataclass(frozen=True, slots=True)
class CanaryExecutionResult:
    """Result of executing a canary mutation."""

    case_sha256: str
    mutation_field: str
    baseline_behavior: str  # "allowed" | "blocked"
    mutated_behavior: str   # "allowed" | "blocked" | "error"
    execution_error: Optional[str]
    target_readback_sha256: Optional[str]


def execute_canary_mutation(
    case: ControlMutationCase,
    baseline_execution_fn,  # Function that runs the protected path
    mutated_execution_fn,   # Function that runs with mutation applied
    canary_target_fn,       # Function that provides disposable canary target
) -> CanaryExecutionResult:
    """Execute a canary mutation against the protected execution path.

    Args:
        case: The ControlMutationCase to execute
        baseline_execution_fn: Function that executes baseline (protected) request
        mutated_execution_fn: Function that executes with mutation applied
        canary_target_fn: Function that returns a disposable canary target

    Returns:
        CanaryExecutionResult with execution details
    """
    mutation_field = operator_allowed_dimension(case.operator)

    # Get canary target
    canary_target = canary_target_fn()

    # Execute baseline (should behave according to contract)
    baseline_result = None
    baseline_error = None
    try:
        baseline_result = baseline_execution_fn(
            operation_family=case.protected_operation_family,
            input_sha256=case.operation_input_sha256,
            target=canary_target,
        )
    except Exception as e:
        baseline_error = str(e)

    # Determine baseline behavior
    if baseline_error:
        baseline_behavior = "error"
    elif baseline_result and baseline_result.get("blocked"):
        baseline_behavior = "blocked"
    else:
        baseline_behavior = "allowed"

    # Execute mutated (should be blocked for security mutations)
    mutated_result = None
    mutated_error = None
    target_readback = None
    try:
        mutated_result = mutated_execution_fn(
            operation_family=case.protected_operation_family,
            input_sha256=case.operation_input_sha256,
            target=canary_target,
            mutation={
                "operator": case.operator,
                "field": mutation_field,
                "baseline": case.baseline_contract_sha256,
                "mutated": case.mutated_contract_sha256,
            },
        )
        # Try to get target readback if execution succeeded
        if mutated_result and mutated_result.get("readback_sha256"):
            target_readback = mutated_result["readback_sha256"]
    except Exception as e:
        mutated_error = str(e)

    # Determine mutated behavior
    if mutated_error:
        mutated_behavior = "error"
    elif mutated_result and mutated_result.get("blocked"):
        mutated_behavior = "blocked"
    elif mutated_result:
        mutated_behavior = "allowed"
    else:
        mutated_behavior = "error"

    # Compute execution hash
    execution_sha256 = canonical_proof_sha256({
        "case_sha256": case.case_sha256,
        "baseline_behavior": baseline_behavior,
        "mutated_behavior": mutated_behavior,
        "target": canary_target,
    })

    return CanaryExecutionResult(
        case_sha256=case.case_sha256,
        mutation_field=mutation_field,
        baseline_behavior=baseline_behavior,
        mutated_behavior=mutated_behavior,
        execution_error=mutated_error,
        target_readback_sha256=target_readback,
    )


def generate_receipt_from_canary(
    case: ControlMutationCase,
    result: CanaryExecutionResult,
    repository_revision: str,
    runtime_revision: Optional[str] = None,
    image_digest: Optional[str] = None,
) -> ControlMutationReceipt:
    """Generate a ControlMutationReceipt from canary execution result.

    Determines verdict based on:
    - MUTANT_KILLED: Mutation was blocked (expected for security cases)
    - MUTANT_SURVIVED: Mutation was allowed (security failure)
    - UNVERIFIED: Execution error or inconclusive
    - CONTRADICTED: Baseline and mutated have contradictory results
    """
    # Determine verdict based on execution result
    # CONTRADICTED: Baseline was blocked but mutated had error (inconsistent)
    # UNVERIFIED: Other execution errors
    if result.execution_error:
        if result.baseline_behavior == "blocked" and result.mutated_behavior == "error":
            verdict = "CONTRADICTED"
            observed_block_code = None
        else:
            verdict = "UNVERIFIED"
            observed_block_code = None
    elif result.baseline_behavior == result.mutated_behavior:
        # No difference - could be UNVERIFIED or MUTANT_SURVIVED depending on context
        if result.baseline_behavior == "blocked" and result.mutated_behavior == "blocked":
            # Both blocked - mutation had no additional effect
            verdict = "MUTANT_KILLED"
            observed_block_code = "ALREADY_BLOCKED"
        elif result.baseline_behavior == "allowed" and result.mutated_behavior == "allowed":
            # Both allowed - mutation didn't help (could be non-security case)
            verdict = "UNVERIFIED"
            observed_block_code = None
        else:
            verdict = "UNVERIFIED"
            observed_block_code = None
    else:
        # Different behaviors
        if result.baseline_behavior == "allowed" and result.mutated_behavior == "blocked":
            # Baseline allowed, mutation blocked - good!
            verdict = "MUTANT_KILLED"
            observed_block_code = result.mutation_field.upper() + "_BLOCK"
        elif result.baseline_behavior == "blocked" and result.mutated_behavior == "allowed":
            # Baseline blocked, mutation allowed - security failure!
            verdict = "MUTANT_SURVIVED"
            observed_block_code = None
        else:
            verdict = "CONTRADICTED"
            observed_block_code = None

    return build_control_mutation_receipt(
        case_sha256=case.case_sha256,
        repository_revision=repository_revision,
        runtime_revision=runtime_revision,
        image_digest=image_digest,
        execution_receipt_sha256=canonical_proof_sha256({
            "case_sha256": case.case_sha256,
            "result": result.mutated_behavior,
        }) if not result.execution_error else None,
        target_readback_sha256=result.target_readback_sha256,
        observed_block_code=observed_block_code,
        verdict=verdict,
    )


# Operator family to execution family mapping
# This maps our ControlMutationCase to the actual environment contract families
OPERATOR_EXECUTION_FAMILY: dict[str, str] = {
    "owner_mismatch": "credential_binding",
    "tool_binding_swap": "mcp_tool_binding",
    "credential_replay": "credential_replay",
    "receipt_replay": "receipt_replay",
    "nonprod_to_production": "environment_promotion",
    "disallowed_egress": "egress_policy",
    "stale_revision": "revision_binding",
    "wrong_image_digest": "image_binding",
    "missing_runtime_evidence": "evidence_completeness",
}


def get_execution_family_for_operator(operator: str) -> str:
    """Get the environment execution family for an operator."""
    return OPERATOR_EXECUTION_FAMILY.get(operator, "unknown")


def is_security_operator(operator: str) -> bool:
    """Check if operator targets a security boundary."""
    security_operators = {
        "owner_mismatch",
        "credential_replay",
        "receipt_replay",
        "nonprod_to_production",
        "disallowed_egress",
    }
    return operator in security_operators
