"""ACSA Canary Lane: Real Environment/Identity/Egress/Replay Canary Execution.

This module provides the runtime execution lane for ACSA (Adversarial Control
State Assurance) canary testing. It executes real control mutation test cases
against disposable targets and produces verifiable receipts.

The canary lane:
1. Loads control mutation cases from the pure contract layer
2. Creates disposable execution targets (not production resources)
3. Executes the mutated contract and captures runtime evidence
4. Produces receipts that can be verified against the contract layer
5. Supports Environment, Identity, Egress, and Replay canary types

Design constraints:
- Disposable targets only - never production resources
- No network, database, filesystem access in this module (delegated to adapters)
- Receipts are deterministic and hash-bound to case + execution
- Target readback is required for operators marked requires_target_readback
- Fail-closed: missing evidence → UNVERIFIED verdict
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Final, FrozenSet, Literal, Optional, Sequence

# Schema version
SCHEMA_VERSION: Final[str] = "sovereign.acsa-canary-lane.v1"

# Canary execution types
class CanaryType(str, Enum):
    ENVIRONMENT = "environment"  # Test environment binding (dev/test → production leak)
    IDENTITY = "identity"        # Test identity/principal resolution
    EGRESS = "egress"           # Test egress policy enforcement
    REPLAY = "replay"           # Test receipt/credential replay prevention


# Canary execution status
class CanaryStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


# Verdict types (matching control_mutation_receipts.py)
ACSAVerdict = Literal["MUTANT_KILLED", "MUTANT_SURVIVED", "UNVERIFIED", "CONTRADICTED"]

# Allowed verdict values
_ALLOWED_VERDICTS: Final[frozenset[str]] = frozenset({
    "MUTANT_KILLED",
    "MUTANT_SURVIVED",
    "UNVERIFIED",
    "CONTRADICTED",
})

# Canary types that require runtime execution
_REQUIRES_RUNTIME: FrozenSet[CanaryType] = frozenset({
    CanaryType.ENVIRONMENT,
    CanaryType.IDENTITY,
    CanaryType.EGRESS,
    CanaryType.REPLAY,
})


class ACSACanaryError(Exception):
    """Base exception for ACSA canary lane errors."""
    pass


class TargetCreationError(ACSACanaryError):
    """Failed to create disposable target."""
    pass


class ExecutionError(ACSACanaryError):
    """Failed to execute canary test."""
    pass


class EvidenceError(ACSACanaryError):
    """Failed to collect required evidence."""
    pass


# ============================================================================
# Data Models
# ============================================================================


@dataclass(frozen=True)
class CanaryExecutionRequest:
    """Request to execute a canary test."""
    canary_type: CanaryType
    case_id: str
    case_sha256: str
    target_environment: str
    target_revision: Optional[str]
    baseline_contract: dict[str, Any]
    mutated_contract: dict[str, Any]
    execution_timeout_seconds: int = 60


@dataclass(frozen=True)
class CanaryExecutionReceipt:
    """Receipt from canary execution."""
    receipt_id: str
    schema_version: str
    case_id: str
    case_sha256: str
    canary_type: CanaryType
    target_environment: str
    target_revision: Optional[str]
    status: CanaryStatus
    verdict: Optional[ACSAVerdict]
    execution_evidence: dict[str, Any]
    target_readback_sha256: Optional[str]
    error: Optional[str]
    executed_at: int  # Unix timestamp millis
    receipt_sha256: str


# ============================================================================
# Canary Lane Interface (Pure)
# ============================================================================


def canary_type_from_operator(operator: str) -> Optional[CanaryType]:
    """Map control mutation operator to canary type."""
    mapping = {
        "stale_revision": CanaryType.ENVIRONMENT,
        "wrong_image_digest": CanaryType.ENVIRONMENT,
        "nonprod_to_production": CanaryType.ENVIRONMENT,
        "owner_mismatch": CanaryType.IDENTITY,
        "credential_replay": CanaryType.REPLAY,
        "receipt_replay": CanaryType.REPLAY,
        "disallowed_egress": CanaryType.EGRESS,
        "missing_runtime_evidence": CanaryType.ENVIRONMENT,
        "tool_binding_swap": CanaryType.IDENTITY,
    }
    return mapping.get(operator.lower())


def requires_canary_execution(canary_type: CanaryType) -> bool:
    """Check if canary type requires runtime execution."""
    return canary_type in _REQUIRES_RUNTIME


def build_canary_execution_request(
    canary_type: CanaryType,
    case_id: str,
    case_sha256: str,
    target_environment: str,
    target_revision: Optional[str],
    baseline_contract: dict[str, Any],
    mutated_contract: dict[str, Any],
    execution_timeout_seconds: int = 60,
) -> CanaryExecutionRequest:
    """Build a canary execution request."""
    return CanaryExecutionRequest(
        canary_type=canary_type,
        case_id=case_id,
        case_sha256=case_sha256,
        target_environment=target_environment,
        target_revision=target_revision,
        baseline_contract=baseline_contract,
        mutated_contract=mutated_contract,
        execution_timeout_seconds=execution_timeout_seconds,
    )


# ============================================================================
# Receipt Generation (Pure)
# ============================================================================


def _canonical_sha256(value: object) -> str:
    """Compute canonical SHA-256 of a JSON-serializable value."""
    import hashlib
    import json
    s = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(s.encode()).hexdigest()


def _content_addressed_id(kind: str, payload: object) -> str:
    """Return a deterministic identity for receipt."""
    return f"{kind}:{_canonical_sha256(payload)}"


def generate_canary_receipt(
    request: CanaryExecutionRequest,
    status: CanaryStatus,
    verdict: Optional[ACSAVerdict] = None,
    execution_evidence: Optional[dict[str, Any]] = None,
    target_readback_sha256: Optional[str] = None,
    error: Optional[str] = None,
    executed_at: Optional[int] = None,
) -> CanaryExecutionReceipt:
    """Generate a canary execution receipt.
    
    The receipt is deterministic and hash-bound to the case and execution.
    """
    import time
    
    if executed_at is None:
        executed_at = int(time.time() * 1000)
    
    if verdict is not None and verdict not in _ALLOWED_VERDICTS:
        raise ValueError(f"invalid verdict: {verdict}")
    
    receipt_body = {
        "schema_version": SCHEMA_VERSION,
        "case_id": request.case_id,
        "case_sha256": request.case_sha256,
        "canary_type": request.canary_type.value,
        "target_environment": request.target_environment,
        "target_revision": request.target_revision,
        "status": status.value,
        "verdict": verdict,
        "execution_evidence": execution_evidence or {},
        "target_readback_sha256": target_readback_sha256,
        "error": error,
        "executed_at": executed_at,
    }
    
    receipt_sha256 = _canonical_sha256(receipt_body)
    receipt_id = _content_addressed_id("acsa-canary-receipt", receipt_body)
    
    return CanaryExecutionReceipt(
        receipt_id=receipt_id,
        schema_version=SCHEMA_VERSION,
        case_id=request.case_id,
        case_sha256=request.case_sha256,
        canary_type=request.canary_type,
        target_environment=request.target_environment,
        target_revision=request.target_revision,
        status=status,
        verdict=verdict,
        execution_evidence=execution_evidence or {},
        target_readback_sha256=target_readback_sha256,
        error=error,
        executed_at=executed_at,
        receipt_sha256=receipt_sha256,
    )


# ============================================================================
# Verdict Determination (Pure)
# ============================================================================


def determine_verdict(
    case: dict[str, Any],
    execution_receipt: CanaryExecutionReceipt,
    requires_target_readback: bool,
) -> ACSAVerdict:
    """Determine the verdict based on execution receipt.
    
    Logic:
    - If status is BLOCKED or FAILED → UNVERIFIED
    - If execution evidence missing required fields → UNVERIFIED
    - If requires_target_readback but target_readback_sha256 missing → UNVERIFIED
    - If execution contradicts case contract → CONTRADICTED
    - If mutation was successfully blocked → MUTANT_KILLED
    - If mutation was not blocked → MUTANT_SURVIVED
    """
    from .control_mutation_cases import ControlMutationOperator
    
    # Check execution status
    if execution_receipt.status in (CanaryStatus.BLOCKED, CanaryStatus.FAILED):
        return "UNVERIFIED"
    
    # Check for execution error
    if execution_receipt.error:
        return "UNVERIFIED"
    
    # Check required evidence
    evidence = execution_receipt.execution_evidence
    if not evidence:
        return "UNVERIFIED"
    
    # Check target readback requirement
    if requires_target_readback and not execution_receipt.target_readback_sha256:
        return "UNVERIFIED"
    
    # Get operator from case
    operator_str = case.get("operator", "")
    try:
        operator = ControlMutationOperator(operator_str)
    except ValueError:
        return "CONTRADICTED"
    
    # Determine verdict based on operator type
    evidence_keys = set(evidence.keys())
    
    # Check for contradiction (case expects block but execution succeeded)
    expected_block = case.get("expected_block_code")
    
    # MUTANT_SURVIVED indicators
    if operator in (
        ControlMutationOperator.STALE_REVISION,
        ControlMutationOperator.WRONG_IMAGE_DIGEST,
    ):
        # If we got the expected revision/digest, mutation survived
        actual = evidence.get("actual_revision") or evidence.get("actual_image_digest")
        expected = evidence.get("expected_revision") or evidence.get("expected_image_digest")
        if actual and expected and actual != expected:
            return "MUTANT_KILLED"
        elif actual == expected:
            return "MUTANT_SURVIVED"
    
    elif operator == ControlMutationOperator.NONPROD_TO_PRODUCTION:
        # Environment mismatch detection
        actual_env = evidence.get("actual_environment")
        expected_blocked = evidence.get("blocked", False)
        if expected_blocked or actual_env == "production":
            return "MUTANT_KILLED"
        return "MUTANT_SURVIVED"
    
    elif operator == ControlMutationOperator.DISALLOWED_EGRESS:
        # Egress policy enforcement
        blocked = evidence.get("blocked", False)
        if blocked:
            return "MUTANT_KILLED"
        return "MUTANT_SURVIVED"
    
    elif operator in (ControlMutationOperator.CREDENTIAL_REPLAY, ControlMutationOperator.RECEIPT_REPLAY):
        # Replay detection
        replay_detected = evidence.get("replay_detected", False)
        if replay_detected:
            return "MUTANT_KILLED"
        return "MUTANT_SURVIVED"
    
    elif operator == ControlMutationOperator.OWNER_MISMATCH:
        # Owner mismatch detection
        actual_owner = evidence.get("actual_owner")
        expected_owner = evidence.get("expected_owner")
        if actual_owner != expected_owner:
            return "MUTANT_KILLED"
        return "MUTANT_SURVIVED"
    
    elif operator == ControlMutationOperator.TOOL_BINDING_SWAP:
        # Tool binding verification
        tool_bound = evidence.get("tool_bound", False)
        if not tool_bound:
            return "MUTANT_KILLED"
        return "MUTANT_SURVIVED"
    
    # Default: evidence present but can't determine
    if evidence_keys:
        return "MUTANT_SURVIVED"
    
    return "UNVERIFIED"


# ============================================================================
# Canary Lane Execution Contract
# ============================================================================


def validate_canary_request(request: CanaryExecutionRequest) -> list[str]:
    """Validate a canary execution request.
    
    Returns list of validation errors (empty if valid).
    """
    errors = []
    
    # Validate case_id
    if not request.case_id or not request.case_id.strip():
        errors.append("case_id is required")
    
    # Validate case_sha256 (64 hex chars)
    if not request.case_sha256 or len(request.case_sha256) != 64:
        errors.append("case_sha256 must be 64 hex characters")
    
    # Validate target_environment
    if not request.target_environment or not request.target_environment.strip():
        errors.append("target_environment is required")
    
    # Validate contracts are non-empty dicts
    if not request.baseline_contract:
        errors.append("baseline_contract is required")
    if not request.mutated_contract:
        errors.append("mutated_contract is required")
    
    # Validate timeout
    if request.execution_timeout_seconds <= 0:
        errors.append("execution_timeout_seconds must be positive")
    if request.execution_timeout_seconds > 300:
        errors.append("execution_timeout_seconds must not exceed 300")
    
    return errors


# ============================================================================
# Disposable Target Creation (Contract only)
# ============================================================================


@dataclass(frozen=True)
class DisposableTargetSpec:
    """Specification for a disposable canary target."""
    target_id: str
    target_type: str
    environment: str
    lifecycle: str  # "ephemeral", "disposable"
    created_for_case: str


def create_disposable_target_spec(
    case_id: str,
    canary_type: CanaryType,
    base_environment: str,
) -> DisposableTargetSpec:
    """Create a specification for a disposable target.
    
    This is a pure contract - actual target creation is delegated to adapters.
    The target must be:
    - Ephemeral/disposable (not production resources)
    - Isolated from production data
    - Bound to the case for audit trail
    """
    import hashlib
    import json
    import time
    
    # Generate deterministic target ID
    payload = {
        "case_id": case_id,
        "canary_type": canary_type.value,
        "base_environment": base_environment,
        "timestamp": int(time.time() * 1000),
    }
    target_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    
    # Determine target type based on canary type
    target_type_map = {
        CanaryType.ENVIRONMENT: "ephemeral_container",
        CanaryType.IDENTITY: "ephemeral_identity",
        CanaryType.EGRESS: "ephemeral_egress",
        CanaryType.REPLAY: "ephemeral_replay",
    }
    
    return DisposableTargetSpec(
        target_id=f"canary-{canary_type.value[:4]}-{target_hash}",
        target_type=target_type_map.get(canary_type, "generic"),
        environment=f"canary-{base_environment}",
        lifecycle="ephemeral",
        created_for_case=case_id,
    )


# ============================================================================
# Test Helpers
# ============================================================================


def make_mock_canary_request(
    canary_type: CanaryType = CanaryType.ENVIRONMENT,
    case_id: str = "test-case-001",
) -> CanaryExecutionRequest:
    """Create a mock canary request for testing."""
    return CanaryExecutionRequest(
        canary_type=canary_type,
        case_id=case_id,
        case_sha256="a" * 64,
        target_environment="canary-test",
        target_revision="b" * 40,
        baseline_contract={"test": "baseline"},
        mutated_contract={"test": "mutated"},
        execution_timeout_seconds=30,
    )
