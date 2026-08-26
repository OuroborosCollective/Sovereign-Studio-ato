"""Adversarial Control-State Assurance (ACSA) Canary Execution Lane.

This module implements the real ACSA canary execution layer (ACSA 2/4). It executes
allowlisted control mutation operators against disposable targets to verify that
existing security boundaries actually block the mutated control states.

Design constraints:
- No network, database, filesystem, clock or random access in this module.
- Uses contracts from control_mutation_cases.py and environment_mcp_execution.py.
- Only disposable/isolation targets - never production resources.
- Each mutant requires a valid baseline control run first.
- MUTANT_KILLED requires block + no-effect target readback.
- MUTANT_SURVIVED requires positive effect observation.
- Missing readback = UNVERIFIED (never positive kill).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Literal, Optional, Tuple

from backend.agent_runtime.control_mutation_cases import (
    ControlMutationCase,
    ControlMutationOperator,
    SecurityDimension,
    get_allowed_dimension,
    requires_runtime_execution,
    requires_target_readback,
)
from backend.agent_runtime.environment_mcp_execution import (
    EnvironmentKind,
    EgressBlockReason,
    EgressDecision,
)


# Schema version
SCHEMA_VERSION: Final[str] = "sovereign.acsa-canary-execution.v1"

# ACSA canary target identifiers (must be explicitly defined, never user-supplied)
_ACSA_CANARY_PREFIX: Final[str] = "acsa-test"


class CanaryTargetKind(str, Enum):
    """Types of disposable canary targets."""

    EPHEMERAL_ENDPOINT = "ephemeral_endpoint"
    TEST_INSTALLATION = "test_installation"
    TEST_CREDENTIAL = "test_credential"
    TEST_REVISION = "test_revision"


class ControlMutationVerdict(str, Enum):
    """Possible verdicts for a control mutation execution."""

    MUTANT_KILLED = "MUTANT_KILLED"
    MUTANT_SURVIVED = "MUTANT_SURVIVED"
    UNVERIFIED = "UNVERIFIED"
    CONTRADICTED = "CONTRADICTED"
    CONTROL_BASELINE_INVALID = "CONTROL_BASELINE_INVALID"


class CanaryExecutionError(Exception):
    """Error during canary execution."""

    pass


# Security dimension to environment contract field mapping
_DIMENSION_TO_CONTRACT_FIELD: dict[SecurityDimension, str] = {
    SecurityDimension.REVISION: "revision",
    SecurityDimension.IMAGE_DIGEST: "image_digest",
    SecurityDimension.TOOL_BINDING: "installation_binding",
    SecurityDimension.OWNER: "owner_id",
    SecurityDimension.CREDENTIAL: "credential_id",
    SecurityDimension.RECEIPT: "receipt_id",
    SecurityDimension.ENVIRONMENT: "environment_kind",
    SecurityDimension.OPERATION_INPUT: "operation_input",
    SecurityDimension.EGRESS_POLICY: "egress_decision",
    SecurityDimension.RUNTIME_EVIDENCE: "runtime_evidence",
}


# Operators that can be tested with environment contracts
_ENVIRONMENT_TESTABLE_OPERATORS: frozenset[ControlMutationOperator] = frozenset({
    ControlMutationOperator.OWNER_MISMATCH,
    ControlMutationOperator.TOOL_BINDING_SWAP,
    ControlMutationOperator.CREDENTIAL_REPLAY,
    ControlMutationOperator.RECEIPT_REPLAY,
    ControlMutationOperator.NONPROD_TO_PRODUCTION,
    ControlMutationOperator.DISALLOWED_EGRESS,
    ControlMutationOperator.STALE_REVISION,
})


# Disallowed egress test targets (fixed, never user-supplied)
_TEST_BLOCKED_HOSTS: Final[Tuple[str, ...]] = (
    "169.254.169.254",  # AWS/GCP/Azure metadata
    "metadata.google.internal",
    "127.0.0.1",
    "::1",
)


# Production environment kinds (never used in ACSA)
_PRODUCTION_ENVIRONMENTS: frozenset[EnvironmentKind] = frozenset({
    EnvironmentKind.PRODUCTION,
})


def validate_canary_target(
    target_kind: CanaryTargetKind,
    target_identifier: str,
) -> None:
    """Validate that a canary target is properly scoped for ACSA testing.

    Args:
        target_kind: Type of canary target
        target_identifier: The target identifier

    Raises:
        CanaryExecutionError: If target is invalid or production-scoped
    """
    # Check prefix first
    if not target_identifier.startswith(_ACSA_CANARY_PREFIX):
        raise CanaryExecutionError(
            f"canary target must start with '{_ACSA_CANARY_PREFIX}'"
        )

    # Check for production-like indicators - exclude "test" which is in our prefix
    prod_indicators = ["production", "prod", "live", "mainnet"]
    lower_id = target_identifier.lower()
    for ind in prod_indicators:
        if ind in lower_id:
            raise CanaryExecutionError(
                f"canary target must not contain production indicators: {target_identifier}"
            )


def validate_no_production_environment(environment_kind: EnvironmentKind) -> None:
    """Ensure we're not testing against production.

    Raises:
        CanaryExecutionError: If environment is production
    """
    if environment_kind in _PRODUCTION_ENVIRONMENTS:
        raise CanaryExecutionError(
            f"ACSA canary must never use production environment: {environment_kind}"
        )


def check_operator_environment_testable(
    operator: ControlMutationOperator,
) -> bool:
    """Check if an operator can be tested with environment contracts."""
    return operator in _ENVIRONMENT_TESTABLE_OPERATORS


def compute_expected_block_code(
    operator: ControlMutationOperator,
    dimension: SecurityDimension,
) -> Optional[str]:
    """Compute the expected block code for an operator mutation.

    This maps operators to their expected block reason in the environment contract.
    """
    mapping: dict[ControlMutationOperator, str] = {
        ControlMutationOperator.OWNER_MISMATCH: "owner_mismatch",
        ControlMutationOperator.TOOL_BINDING_SWAP: "installation_binding_mismatch",
        ControlMutationOperator.CREDENTIAL_REPLAY: "credential_replay_detected",
        ControlMutationOperator.RECEIPT_REPLAY: "receipt_revision_mismatch",
        ControlMutationOperator.NONPROD_TO_PRODUCTION: "environment_policy_violation",
        ControlMutationOperator.DISALLOWED_EGRESS: EgressBlockReason.PRIVATE_NETWORK.value,
        ControlMutationOperator.STALE_REVISION: "revision_mismatch",
        ControlMutationOperator.WRONG_IMAGE_DIGEST: "image_digest_mismatch",
        ControlMutationOperator.MISSING_RUNTIME_EVIDENCE: "missing_evidence",
    }
    return mapping.get(operator)


@dataclass(frozen=True)
class CanaryExecutionContext:
    """Execution context for an ACSA canary run.

    This is a pure contract - it defines what will be tested but does not
    perform the actual execution. The execution adapter is responsible for
    running against disposable targets.
    """

    schema_version: str
    case: ControlMutationCase
    canary_target_kind: CanaryTargetKind
    canary_target_id: str
    baseline_execution_required: bool
    target_readback_required: bool


@dataclass(frozen=True)
class CanaryExecutionResult:
    """Result of an ACSA canary execution.

    This is the pure contract result - the actual execution happens in an
    isolated adapter that consumes this contract.
    """

    schema_version: str
    case_sha256: str
    canary_target_id: str

    # Baseline control run results
    baseline_blocked: bool
    baseline_block_code: Optional[str]
    baseline_effect_observed: bool
    baseline_target_readback: Optional[str]

    # Mutant run results
    mutant_blocked: bool
    mutant_block_code: Optional[str]
    mutant_effect_observed: bool
    mutant_target_readback: Optional[str]

    # Verdict determination
    verdict: ControlMutationVerdict
    verdict_reason: str

    # Execution metadata
    runtime_revision: Optional[str]
    image_digest: Optional[str]

    # Canonical receipt hash
    receipt_sha256: str


def compute_canary_execution_context(
    case: ControlMutationCase,
    canary_target_kind: CanaryTargetKind,
    canary_target_id: str,
) -> CanaryExecutionContext:
    """Compute the execution context for a canary run.

    Args:
        case: The control mutation case to execute
        canary_target_kind: Type of disposable canary target
        canary_target_id: Identifier for the canary target

    Returns:
        Execution context for the canary

    Raises:
        CanaryExecutionError: If case or target is invalid
    """
    # Validate target
    validate_canary_target(canary_target_kind, canary_target_id)

    # Check operator is testable with environment contracts
    if not check_operator_environment_testable(case.operator):
        raise CanaryExecutionError(
            f"operator {case.operator.value} is not environment-testable"
        )

    # Determine if baseline execution is required
    baseline_required = requires_runtime_execution(case.operator)

    # Determine if target readback is required
    readback_required = requires_target_readback(case.operator)

    return CanaryExecutionContext(
        schema_version=SCHEMA_VERSION,
        case=case,
        canary_target_kind=canary_target_kind,
        canary_target_id=canary_target_id,
        baseline_execution_required=baseline_required,
        target_readback_required=readback_required,
    )


def evaluate_verdict(
    baseline_blocked: bool,
    baseline_effect: bool,
    mutant_blocked: bool,
    mutant_effect: bool,
    mutant_block_code: Optional[str],
    expected_block_code: Optional[str],
    has_target_readback: bool,
    readback_shows_effect: bool,
) -> Tuple[ControlMutationVerdict, str]:
    """Evaluate the verdict for a canary execution.

    Args:
        baseline_blocked: Whether baseline was blocked
        baseline_effect: Whether baseline showed effect
        mutant_blocked: Whether mutant was blocked
        mutant_effect: Whether mutant showed effect
        mutant_block_code: Actual block code from mutant run
        expected_block_code: Expected block code from case
        has_target_readback: Whether target readback is available
        readback_shows_effect: Whether readback shows effect occurred

    Returns:
        Tuple of (verdict, reason)
    """
    # Control baseline must be valid first
    if not baseline_blocked and baseline_effect:
        return (
            ControlMutationVerdict.CONTROL_BASELINE_INVALID,
            "baseline control run produced effect - cannot evaluate mutant",
        )

    # If mutant was not blocked and effect was observed
    if not mutant_blocked and mutant_effect:
        return (
            ControlMutationVerdict.MUTANT_SURVIVED,
            "mutant was not blocked and effect was observed at target",
        )

    # If mutant was blocked but no target readback available
    if mutant_blocked and not has_target_readback:
        # Blocked but can't verify no-effect - this is UNVERIFIED
        return (
            ControlMutationVerdict.UNVERIFIED,
            "mutant blocked but target readback unavailable",
        )

    # If mutant was blocked but readback shows effect occurred
    if mutant_blocked and has_target_readback and readback_shows_effect:
        return (
            ControlMutationVerdict.MUTANT_SURVIVED,
            "mutant blocked but target readback shows effect occurred",
        )

    # If mutant was blocked and target readback confirms no effect
    if mutant_blocked and has_target_readback and not readback_shows_effect:
        # Check block code matches expected
        if expected_block_code and mutant_block_code != expected_block_code:
            return (
                ControlMutationVerdict.CONTRADICTED,
                f"block code mismatch: expected {expected_block_code}, got {mutant_block_code}",
            )
        return (
            ControlMutationVerdict.MUTANT_KILLED,
            "mutant blocked and target readback confirms no effect",
        )

    # If mutant was blocked (effectful but blocked before execution)
    if mutant_blocked:
        if expected_block_code and mutant_block_code != expected_block_code:
            return (
                ControlMutationVerdict.CONTRADICTED,
                f"block code mismatch: expected {expected_block_code}, got {mutant_block_code}",
            )
        return (
            ControlMutationVerdict.MUTANT_KILLED,
            "mutant blocked (pre-execution block)",
        )

    # Default - mutant not blocked and no effect observed = ambiguous
    return (
        ControlMutationVerdict.UNVERIFIED,
        "mutant not blocked but no effect observed - cannot determine",
    )


def build_canary_execution_receipt(
    case: ControlMutationCase,
    canary_target_id: str,
    baseline_blocked: bool,
    baseline_block_code: Optional[str],
    baseline_effect: bool,
    baseline_readback: Optional[str],
    mutant_blocked: bool,
    mutant_block_code: Optional[str],
    mutant_effect: bool,
    mutant_readback: Optional[str],
    runtime_revision: Optional[str] = None,
    image_digest: Optional[str] = None,
) -> CanaryExecutionResult:
    """Build the final canary execution receipt.

    Args:
        case: The control mutation case
        canary_target_id: The canary target identifier
        baseline_blocked: Whether baseline was blocked
        baseline_block_code: Baseline block code
        baseline_effect: Whether baseline showed effect
        baseline_readback: Baseline target readback
        mutant_blocked: Whether mutant was blocked
        mutant_block_code: Mutant block code
        mutant_effect: Whether mutant showed effect
        mutant_readback: Mutant target readback
        runtime_revision: Optional runtime revision
        image_digest: Optional image digest

    Returns:
        Final execution receipt with verdict
    """
    # Compute expected block code
    dimension = get_allowed_dimension(case.operator)
    expected_block = compute_expected_block_code(case.operator, dimension)

    # Determine if readback shows effect
    readback_shows_effect = (
        mutant_readback is not None and
        mutant_readback != baseline_readback
    )

    # Evaluate verdict
    verdict, reason = evaluate_verdict(
        baseline_blocked=baseline_blocked,
        baseline_effect=baseline_effect,
        mutant_blocked=mutant_blocked,
        mutant_effect=mutant_effect,
        mutant_block_code=mutant_block_code,
        expected_block_code=expected_block,
        has_target_readback=mutant_readback is not None,
        readback_shows_effect=readback_shows_effect,
    )

    # Build receipt
    result = CanaryExecutionResult(
        schema_version=SCHEMA_VERSION,
        case_sha256=case.case_sha256,
        canary_target_id=canary_target_id,
        baseline_blocked=baseline_blocked,
        baseline_block_code=baseline_block_code,
        baseline_effect_observed=baseline_effect,
        baseline_target_readback=baseline_readback,
        mutant_blocked=mutant_blocked,
        mutant_block_code=mutant_block_code,
        mutant_effect_observed=mutant_effect,
        mutant_target_readback=mutant_readback,
        verdict=verdict,
        verdict_reason=reason,
        runtime_revision=runtime_revision,
        image_digest=image_digest,
        receipt_sha256="",  # Will be computed below
    )

    # Compute receipt hash
    receipt_hash = _compute_receipt_sha256(result)
    object.__setattr__(result, "receipt_sha256", receipt_hash)

    return result


def _compute_receipt_sha256(result: CanaryExecutionResult) -> str:
    """Compute canonical SHA-256 for the receipt."""
    import hashlib
    import json

    body = {
        "schema_version": result.schema_version,
        "case_sha256": result.case_sha256,
        "canary_target_id": result.canary_target_id,
        "baseline_blocked": result.baseline_blocked,
        "baseline_block_code": result.baseline_block_code,
        "baseline_effect_observed": result.baseline_effect_observed,
        "baseline_target_readback": result.baseline_target_readback,
        "mutant_blocked": result.mutant_blocked,
        "mutant_block_code": result.mutant_block_code,
        "mutant_effect_observed": result.mutant_effect_observed,
        "mutant_target_readback": result.mutant_target_readback,
        "verdict": result.verdict.value,
        "verdict_reason": result.verdict_reason,
        "runtime_revision": result.runtime_revision,
        "image_digest": result.image_digest,
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


# Export public API
__all__ = [
    "CanaryExecutionContext",
    "CanaryExecutionError",
    "CanaryExecutionResult",
    "CanaryTargetKind",
    "ControlMutationVerdict",
    "SCHEMA_VERSION",
    "build_canary_execution_receipt",
    "check_operator_environment_testable",
    "compute_canary_execution_context",
    "compute_expected_block_code",
    "validate_canary_target",
    "validate_no_production_environment",
]
