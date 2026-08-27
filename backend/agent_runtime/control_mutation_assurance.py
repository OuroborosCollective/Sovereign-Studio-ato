"""Adversarial Control State Assurance (ACSA) - Canary Execution Lane.

This module provides the execution layer for control mutation testing against
disposable canary targets. It verifies that existing security boundaries in
environment_mcp_execution.py correctly block mutated inputs.

Design constraints:
- No network, database, filesystem, clock or random access in this module.
- Uses existing environment_mcp_execution boundaries, does not duplicate logic.
- Canary targets must be explicitly configured as disposable/isolation targets.
- Fails closed when target readback is missing.
- No secret values in receipts.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Final, FrozenSet, Literal, Optional, Tuple

from backend.agent_runtime.control_mutation_cases import (
    ControlMutationCase,
    ControlMutationOperator,
    ControlMutationContractError,
    SecurityDimension,
    get_allowed_dimension,
    requires_runtime_execution,
    requires_target_readback,
)
from backend.agent_runtime.control_mutation_receipts import (
    ControlMutationReceipt,
    ControlMutationReceiptError,
)

# Schema version
SCHEMA_VERSION: Final[str] = "sovereign.control-mutation-assurance.v1"

# Validation patterns
_SHA40: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_SHA64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_.:/@-]{1,119}$")


class CanaryTargetError(ValueError):
    """Canary target configuration or execution error."""
    pass


@dataclass(frozen=True, slots=True)
class CanaryTarget:
    """Configuration for a disposable canary test target.

    Target must:
    - Be uniquely identifiable as ACSA/test/ephemeral
    - Not require production credentials
    - Not represent a production resource
    - Log all received requests with a bounded non-secret Canary-ID
    - Be readable before and after each case
    - Be fully cleanupable
    """

    target_id: str
    target_type: str  # "local_echo", "test_server", "disallowed_host"
    is_production: bool  # Must be False for canaries
    allows_egress: bool  # Whether egress is allowed to this target
    endpoint: Optional[str]  # URL or identifier for the target
    canary_id_prefix: str  # Prefix for canary IDs

    def __post_init__(self) -> None:
        if self.is_production:
            raise CanaryTargetError("CanaryTarget must not be marked as production")
        # Validate target_id format
        if not _IDENTIFIER.fullmatch(self.target_id):
            raise CanaryTargetError(f"invalid target_id format: {self.target_id}")


# Predefined canary targets for different test scenarios
_CANARY_TARGETS: dict[str, CanaryTarget] = {
    "local_echo": CanaryTarget(
        target_id="acsa_local_echo",
        target_type="local_echo",
        is_production=False,
        allows_egress=False,
        endpoint=None,
        canary_id_prefix="acsa_le_",
    ),
    "test_server": CanaryTarget(
        target_id="acsa_test_server",
        target_type="test_server",
        is_production=False,
        allows_egress=True,
        endpoint="http://localhost:19999",
        canary_id_prefix="acsa_ts_",
    ),
    "disallowed_host": CanaryTarget(
        target_id="acsa_disallowed_egress",
        target_type="disallowed_host",
        is_production=False,
        allows_egress=False,
        endpoint="169.254.169.254",  # Cloud metadata IP
        canary_id_prefix="acsa_de_",
    ),
}


def get_canary_target(target_id: str) -> CanaryTarget:
    """Get a predefined canary target by ID."""
    target = _CANARY_TARGETS.get(target_id)
    if target is None:
        raise CanaryTargetError(f"unknown canary target: {target_id}")
    return target


def list_canary_targets() -> FrozenSet[str]:
    """List all available canary target IDs."""
    return frozenset(_CANARY_TARGETS.keys())


# Allowed verdict values for ACSA execution
_ALLOWED_VERDICTS: Final[frozenset[str]] = frozenset({
    "MUTANT_KILLED",
    "MUTANT_SURVIVED",
    "UNVERIFIED",
    "CONTRADICTED",
    "CONTROL_BASELINE_INVALID",
})


def _normalize_sha40(value: Optional[str], *, label: str) -> Optional[str]:
    """Validate and normalize a full Git SHA (optional)."""
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized and not _SHA40.fullmatch(normalized):
        raise ValueError(f"{label} must be a lowercase full Git SHA (40 hex)")
    return normalized or None


def _normalize_sha64(value: Optional[str], *, label: str) -> Optional[str]:
    """Validate and normalize a SHA-256 hash (optional)."""
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized and not _SHA64.fullmatch(normalized):
        raise ValueError(f"{label} must be a lowercase SHA-256 (64 hex)")
    return normalized or None


def _compute_canary_id(prefix: str, case_id: str, run_id: str) -> str:
    """Compute a deterministic canary ID for a test run."""
    canary_input = f"{prefix}:{case_id}:{run_id}"
    return f"{prefix}{hashlib.sha256(canary_input.encode()).hexdigest()[:16]}"


def _canonical_sha256(value: Any) -> str:
    """Compute deterministic SHA-256 for canonical JSON."""
    s = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(s.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class CanaryExecutionResult:
    """Result of executing a control mutation case on a canary target.

    This is an internal intermediate result - not the final receipt.
    The execution result is used to determine the final verdict.
    """

    case_id: str
    target_id: str
    canary_id: str
    control_baseline_executed: bool
    control_baseline_success: bool
    control_baseline_error: Optional[str]
    mutant_executed: bool
    mutant_blocked: bool
    block_code: Optional[str]
    target_readback_available: bool
    target_readback: Optional[dict[str, Any]]
    target_readback_error: Optional[str]
    latency_ms: Optional[int]
    execution_sha256: str

    def __post_init__(self) -> None:
        # Validate case_id
        if not _IDENTIFIER.fullmatch(self.case_id):
            raise ValueError(f"invalid case_id: {self.case_id}")
        # Validate target_id
        if not _IDENTIFIER.fullmatch(self.target_id):
            raise ValueError(f"invalid target_id: {self.target_id}")
        # Compute and validate execution hash
        computed = self._compute_execution_sha256()
        # If user provided placeholder hash (all zeros), use computed
        if self.execution_sha256 == "0" * 64:
            object.__setattr__(self, "execution_sha256", computed)
        elif computed != self.execution_sha256:
            raise ValueError("execution_sha256 mismatch")

    def _compute_execution_sha256(self) -> str:
        """Compute deterministic SHA-256 for this execution result."""
        return _canonical_sha256({
            "case_id": self.case_id,
            "target_id": self.target_id,
            "canary_id": self.canary_id,
            "control_baseline_executed": self.control_baseline_executed,
            "control_baseline_success": self.control_baseline_success,
            "control_baseline_error": self.control_baseline_error,
            "mutant_executed": self.mutant_executed,
            "mutant_blocked": self.mutant_blocked,
            "block_code": self.block_code,
            "target_readback_available": self.target_readback_available,
            "target_readback": self.target_readback,
            "target_readback_error": self.target_readback_error,
            "latency_ms": self.latency_ms,
        })


def determine_verdict(
    case: Optional[ControlMutationCase],
    execution_result: CanaryExecutionResult,
) -> Tuple[str, Optional[str]]:
    """Determine the verdict for a control mutation case.

    Returns:
        Tuple of (verdict, reason)

    Verdict semantics:
        MUTANT_KILLED: Mutant was blocked AND target readback confirms no effect
        MUTANT_SURVIVED: Mutant was NOT blocked OR target shows unexpected effect
        UNVERIFIED: Cannot determine verdict (missing readback, etc.)
        CONTRADICTED: Execution state contradicts itself
        CONTROL_BASELINE_INVALID: Control baseline failed or is unreadable
    """
    # Check control baseline validity
    if not execution_result.control_baseline_executed:
        return "CONTROL_BASELINE_INVALID", "control baseline was not executed"
    if not execution_result.control_baseline_success:
        return "CONTROL_BASELINE_INVALID", f"control baseline failed: {execution_result.control_baseline_error}"

    # Check for contradiction in execution state
    if execution_result.mutant_executed and execution_result.mutant_blocked:
        # Mutant both executed AND blocked - contradiction
        return "CONTRADICTED", "mutant both executed and blocked"

    # Determine runtime execution and readback requirements
    if case is not None:
        # Use case configuration
        runtime_required = requires_runtime_execution(case.operator)
        readback_required = requires_target_readback(case.operator)
    else:
        # Default assumptions when no case provided (backwards compatibility)
        # Assume runtime execution required and readback helpful for most cases
        runtime_required = True
        readback_required = True

    # Check if case requires runtime execution
    if not runtime_required:
        # No runtime execution required - verdict depends on contract only
        return "CONTRADICTED", "operator does not require runtime execution"

    # Determine verdict based on blocking and readback
    if not execution_result.mutant_blocked:
        # Mutant was NOT blocked - it survived
        return "MUTANT_SURVIVED", "mutant was not blocked by security boundary"

    # Mutant was blocked - check readback
    if readback_required:
        if not execution_result.target_readback_available:
            # Blocked but no readback - unverified
            return "UNVERIFIED", "mutant blocked but target readback unavailable"

        # Check if target readback shows any effect
        readback = execution_result.target_readback
        if readback and readback.get("effect_observed", False):
            # Target saw an effect despite blocking - survived
            return "MUTANT_SURVIVED", "target readback shows unexpected effect despite block"

        # Blocked AND no effect observed - killed
        return "MUTANT_KILLED", "mutant blocked and target readback confirms no effect"

    # Operator doesn't require target readback - blocked is sufficient
    return "MUTANT_KILLED", "mutant blocked by security boundary"


def create_assurance_receipt(
    case: ControlMutationCase,
    execution_result: CanaryExecutionResult,
) -> ControlMutationReceipt:
    """Create a ControlMutationReceipt from execution results.

    This bridges the execution layer (this module) with the receipt layer
    (control_mutation_receipts.py).
    """
    verdict, _reason = determine_verdict(case, execution_result)

    # Build receipt data matching build_control_mutation_receipt signature
    receipt_data = {
        "case_sha256": case.case_sha256,
        "repository_revision": case.repository_revision,
        "runtime_revision": None,  # Would be set from actual runtime
        "image_digest": None,  # Would be set from actual runtime
        "execution_receipt_sha256": execution_result.execution_sha256,
        "target_readback_sha256": (
            _canonical_sha256(execution_result.target_readback)
            if execution_result.target_readback_available
            else None
        ),
        "observed_block_code": execution_result.block_code,
        "verdict": verdict,
    }

    # Create the receipt using control_mutation_receipts
    from backend.agent_runtime.control_mutation_receipts import (
        build_control_mutation_receipt,
    )

    return build_control_mutation_receipt(**receipt_data)


# Stub for canary execution - actual implementation requires runtime context
def execute_canary_case(
    case: ControlMutationCase,
    target: CanaryTarget,
    run_id: str,
) -> CanaryExecutionResult:
    """Execute a control mutation case against a canary target.

    This is a stub implementation. Real execution requires:
    - Network access to canary targets
    - Integration with environment_mcp_execution boundaries
    - Actual runtime environment

    Returns a result that can be used to determine the verdict.
    """
    canary_id = _compute_canary_id(
        target.canary_id_prefix,
        case.mutation_id,
        run_id,
    )

    # This is a stub - in production, this would:
    # 1. Execute baseline request
    # 2. Execute mutated request
    # 3. Read back from target
    # 4. Determine blocking behavior

    # For now, return an UNVERIFIED result as we can't execute real canaries
    return CanaryExecutionResult(
        case_id=case.mutation_id,
        target_id=target.target_id,
        canary_id=canary_id,
        control_baseline_executed=False,
        control_baseline_success=False,
        control_baseline_error="execution_requires_runtime_context",
        mutant_executed=False,
        mutant_blocked=False,
        block_code=None,
        target_readback_available=False,
        target_readback=None,
        target_readback_error="execution_requires_runtime_context",
        latency_ms=None,
        execution_sha256="0" * 64,  # Placeholder
    )


def validate_canary_config(target: CanaryTarget) -> Tuple[bool, Optional[str]]:
    """Validate a canary target configuration for security.

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Production targets are forbidden
    if target.is_production:
        return False, "canary target cannot be production"

    # Must have valid identifier format
    if not _IDENTIFIER.fullmatch(target.target_id):
        return False, f"invalid target_id format: {target.target_id}"

    return True, None


# Export public API
__all__ = [
    "CanaryExecutionResult",
    "CanaryTarget",
    "CanaryTargetError",
    "SCHEMA_VERSION",
    "create_assurance_receipt",
    "determine_verdict",
    "execute_canary_case",
    "get_canary_target",
    "list_canary_targets",
    "validate_canary_config",
]
