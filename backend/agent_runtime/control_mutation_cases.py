"""Pure, deterministic ControlMutation contracts for Adversarial Control State Assurance.

This module defines the static operator registry, case definitions, and single-variable
invariant enforcement for ACSA. It performs no network, database, filesystem, clock or
random access. It only defines the contract layer that other lanes can use to produce
receipts.

Design constraints:
- No network, database, filesystem, clock or random access in this module.
- Unknown operators are blocked with ContractError.
- No dynamic plugin/LLM registry - static V1 allowlist only.
- Single-variable invariant: exactly one security dimension may drift.
- Baseline and mutant must share operation identity.
- Secret-shaped raw fields are never stored in contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from enum import Enum
from typing import Any, Final, Literal, Mapping, Optional, Tuple

# Schema version
SCHEMA_VERSION: Final[str] = "sovereign.control-mutation-case.v1"

# Validation patterns
_SHA40: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_SHA64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_IMAGE_DIGEST: Final[re.Pattern[str]] = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_.:/@-]{1,119}$")

# Security dimension constants (for single-variable invariant)
class SecurityDimension(str, Enum):
    REVISION = "revision"
    IMAGE_DIGEST = "image_digest"
    TOOL_BINDING = "tool_binding"
    OWNER = "owner"
    CREDENTIAL = "credential"
    RECEIPT = "receipt"
    ENVIRONMENT = "environment"
    OPERATION_INPUT = "operation_input"
    EGRESS_POLICY = "egress_policy"
    RUNTIME_EVIDENCE = "runtime_evidence"


class ControlMutationOperator(str, Enum):
    """Static V1 operator allowlist. Unknown operators trigger ContractError."""

    STALE_REVISION = "stale_revision"
    WRONG_IMAGE_DIGEST = "wrong_image_digest"
    TOOL_BINDING_SWAP = "tool_binding_swap"
    OWNER_MISMATCH = "owner_mismatch"
    CREDENTIAL_REPLAY = "credential_replay"
    RECEIPT_REPLAY = "receipt_replay"
    NONPROD_TO_PRODUCTION = "nonprod_to_production"
    DISALLOWED_EGRESS = "disallowed_egress"
    MISSING_RUNTIME_EVIDENCE = "missing_runtime_evidence"


# Operator to allowed security dimension mapping (single-variable invariant)
_OPERATOR_ALLOWED_DIMENSION: Mapping[ControlMutationOperator, SecurityDimension] = {
    ControlMutationOperator.STALE_REVISION: SecurityDimension.REVISION,
    ControlMutationOperator.WRONG_IMAGE_DIGEST: SecurityDimension.IMAGE_DIGEST,
    ControlMutationOperator.TOOL_BINDING_SWAP: SecurityDimension.TOOL_BINDING,
    ControlMutationOperator.OWNER_MISMATCH: SecurityDimension.OWNER,
    ControlMutationOperator.CREDENTIAL_REPLAY: SecurityDimension.CREDENTIAL,
    ControlMutationOperator.RECEIPT_REPLAY: SecurityDimension.RECEIPT,
    ControlMutationOperator.NONPROD_TO_PRODUCTION: SecurityDimension.ENVIRONMENT,
    ControlMutationOperator.DISALLOWED_EGRESS: SecurityDimension.EGRESS_POLICY,
    ControlMutationOperator.MISSING_RUNTIME_EVIDENCE: SecurityDimension.RUNTIME_EVIDENCE,
}

# Operators that require runtime execution for verification
_REQUIRES_RUNTIME_EXECUTION: frozenset[ControlMutationOperator] = frozenset({
    ControlMutationOperator.STALE_REVISION,
    ControlMutationOperator.WRONG_IMAGE_DIGEST,
    ControlMutationOperator.TOOL_BINDING_SWAP,
    ControlMutationOperator.OWNER_MISMATCH,
    ControlMutationOperator.CREDENTIAL_REPLAY,
    ControlMutationOperator.RECEIPT_REPLAY,
    ControlMutationOperator.NONPROD_TO_PRODUCTION,
    ControlMutationOperator.DISALLOWED_EGRESS,
})

# Operators that require target readback for MUTANT_KILLED verdict
_REQUIRES_TARGET_READBACK: frozenset[ControlMutationOperator] = frozenset({
    ControlMutationOperator.STALE_REVISION,
    ControlMutationOperator.WRONG_IMAGE_DIGEST,
    ControlMutationOperator.TOOL_BINDING_SWAP,
    ControlMutationOperator.OWNER_MISMATCH,
    ControlMutationOperator.CREDENTIAL_REPLAY,
    ControlMutationOperator.RECEIPT_REPLAY,
    ControlMutationOperator.NONPROD_TO_PRODUCTION,
    ControlMutationOperator.DISALLOWED_EGRESS,
    ControlMutationOperator.MISSING_RUNTIME_EVIDENCE,
})


class ControlMutationContractError(ValueError):
    """A control mutation input violated a deterministic or invariant."""

    pass


# Secret-shaped key markers (from agent_run_receipts)
_SECRET_KEY_MARKERS: Final[tuple[str, ...]] = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "private_key",
    "client_secret",
    "cookie",
    "raw_prompt",
    "prompt_text",
    "file_content",
    "database_row",
    "credential",
    "auth",
)

# Timestamp-shaped key markers (implicit time identity is forbidden)
_TIMESTAMP_KEY_MARKERS: Final[tuple[str, ...]] = (
    "timestamp",
    "created_at",
    "updated_at",
    "now",
    "time",
    "datetime",
    "date",
)


def _normalize_sha40(value: str, *, label: str) -> str:
    """Validate and normalize a full Git SHA."""
    normalized = str(value or "").strip().lower()
    if not _SHA40.fullmatch(normalized):
        raise ControlMutationContractError(f"{label} must be a lowercase full Git SHA (40 hex)")
    return normalized


def _normalize_sha64(value: str, *, label: str) -> str:
    """Validate and normalize a SHA-256 hash."""
    normalized = str(value or "").strip().lower()
    if not _SHA64.fullmatch(normalized):
        raise ControlMutationContractError(f"{label} must be a lowercase SHA-256 (64 hex)")
    return normalized


def _normalize_image_digest(value: str, *, label: str) -> str:
    """Validate and normalize an OCI image digest."""
    normalized = str(value or "").strip().lower()
    if not _IMAGE_DIGEST.fullmatch(normalized):
        raise ControlMutationContractError(f"{label} must be a lowercase OCI digest (sha256:<64hex>)")
    return normalized


def _normalize_identifier(value: str, *, label: str) -> str:
    """Validate and normalize a canonical identifier."""
    normalized = str(value or "").strip().lower()
    if not _IDENTIFIER.fullmatch(normalized):
        raise ControlMutationContractError(f"{label} must be a canonical identifier")
    return normalized


def _reject_secret_shaped_field(value: Any, *, path: str = "$") -> None:
    """Reject secret-shaped raw fields from contracts."""
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                key_lower = key.lower()
                if any(marker in key_lower for marker in _SECRET_KEY_MARKERS):
                    raise ControlMutationContractError(
                        f"secret-shaped field '{key}' is forbidden at {path}"
                    )
                _reject_secret_shaped_field(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            _reject_secret_shaped_field(item, path=f"{path}[{idx}]")


def _reject_forbidden_contract_values(value: Any, *, path: str = "$") -> None:
    """Reject NaN, Infinity, floats, and timestamp-shaped keys from contracts.

    The architecture specifies that contracts must not contain:
    - Float values (NaN, Infinity, or any float)
    - Timestamp-shaped keys (implicit time identity)
    """
    if isinstance(value, float):
        if value != value:  # NaN check (NaN != NaN is True)
            raise ControlMutationContractError(
                f"NaN value is forbidden in contract at {path}"
            )
        if value == float("inf") or value == float("-inf"):
            raise ControlMutationContractError(
                f"Infinity value is forbidden in contract at {path}"
            )
        raise ControlMutationContractError(
            f"float value is forbidden in contract at {path}"
        )
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                key_lower = key.lower()
                if any(marker == key_lower for marker in _TIMESTAMP_KEY_MARKERS):
                    raise ControlMutationContractError(
                        f"timestamp-shaped field '{key}' is forbidden at {path}"
                    )
            _reject_forbidden_contract_values(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            _reject_forbidden_contract_values(item, path=f"{path}[{idx}]")


def _canonical_sha256(value: Any) -> str:
    """Compute deterministic SHA-256 for canonical JSON."""
    s = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(s.encode()).hexdigest()


def get_allowed_dimension(operator: ControlMutationOperator) -> SecurityDimension:
    """Get the single security dimension an operator is allowed to mutate."""
    return _OPERATOR_ALLOWED_DIMENSION[operator]


def get_operator(operator_str: str) -> ControlMutationOperator:
    """Resolve an operator string to the enum, raising on unknown operators."""
    try:
        return ControlMutationOperator(operator_str)
    except ValueError as exc:
        raise ControlMutationContractError(
            f"unknown operator: {operator_str!r}. "
            f"Allowed: {[o.value for o in ControlMutationOperator]}"
        ) from exc


def requires_runtime_execution(operator: ControlMutationOperator) -> bool:
    """Check if an operator requires runtime execution for verification."""
    return operator in _REQUIRES_RUNTIME_EXECUTION


def requires_target_readback(operator: ControlMutationOperator) -> bool:
    """Check if an operator requires target readback for MUTANT_KILLED verdict."""
    return operator in _REQUIRES_TARGET_READBACK


@dataclass(frozen=True, slots=True)
class ControlMutationCase:
    """Immutable case definition for a control mutation test.

    The case defines a baseline contract and a mutated contract that differ in
    exactly one security dimension. The case is bound to a specific repository
    and revision, and specifies whether runtime execution or target readback
    is required for verdict determination.
    """

    schema_version: str
    mutation_id: str
    operator: ControlMutationOperator
    repository: str
    repository_revision: str
    control_owner: str
    baseline_contract_sha256: str
    mutated_contract_sha256: str
    protected_operation_family: str
    operation_input_sha256: str
    expected_block_code: Optional[str]
    requires_runtime_execution: bool
    requires_target_readback: bool
    case_sha256: str

    def __post_init__(self) -> None:
        # Validate schema version
        if self.schema_version != SCHEMA_VERSION:
            raise ControlMutationContractError(
                f"unsupported schema version: {self.schema_version!r}"
            )

        # Validate and normalize fields
        object.__setattr__(self, "mutation_id", _normalize_identifier(self.mutation_id, label="mutation_id"))
        object.__setattr__(self, "repository", _normalize_identifier(self.repository, label="repository"))

        # Validate repository revision (full Git SHA-40)
        object.__setattr__(
            self,
            "repository_revision",
            _normalize_sha40(self.repository_revision, label="repository_revision"),
        )

        # Validate control owner
        object.__setattr__(
            self,
            "control_owner",
            _normalize_identifier(self.control_owner, label="control_owner"),
        )

        # Validate SHA-256 hashes
        object.__setattr__(
            self,
            "baseline_contract_sha256",
            _normalize_sha64(self.baseline_contract_sha256, label="baseline_contract_sha256"),
        )
        object.__setattr__(
            self,
            "mutated_contract_sha256",
            _normalize_sha64(self.mutated_contract_sha256, label="mutated_contract_sha256"),
        )
        object.__setattr__(
            self,
            "operation_input_sha256",
            _normalize_sha64(self.operation_input_sha256, label="operation_input_sha256"),
        )

        # Validate protected operation family
        object.__setattr__(
            self,
            "protected_operation_family",
            _normalize_identifier(self.protected_operation_family, label="protected_operation_family"),
        )

        # Validate expected_block_code if provided
        if self.expected_block_code is not None:
            code = str(self.expected_block_code).strip().lower()
            if not code:
                raise ControlMutationContractError("expected_block_code must not be empty")
            object.__setattr__(self, "expected_block_code", code)

        # Validate case_sha256
        object.__setattr__(
            self,
            "case_sha256",
            _normalize_sha64(self.case_sha256, label="case_sha256"),
        )

        # Verify single-variable invariant - case hash must match computed hash
        computed_hash = self._compute_case_sha256()
        if computed_hash != self.case_sha256:
            raise ControlMutationContractError("case_sha256 mismatch")

    def _compute_case_sha256(self) -> str:
        """Compute the canonical case SHA-256."""
        body = {
            "schema_version": self.schema_version,
            "mutation_id": self.mutation_id,
            "operator": self.operator.value,
            "repository": self.repository,
            "repository_revision": self.repository_revision,
            "control_owner": self.control_owner,
            "baseline_contract_sha256": self.baseline_contract_sha256,
            "mutated_contract_sha256": self.mutated_contract_sha256,
            "protected_operation_family": self.protected_operation_family,
            "operation_input_sha256": self.operation_input_sha256,
            "expected_block_code": self.expected_block_code,
            "requires_runtime_execution": self.requires_runtime_execution,
            "requires_target_readback": self.requires_target_readback,
        }
        return _canonical_sha256(body)

    def canonical_body(self) -> dict[str, Any]:
        """Return the canonical case body for hashing."""
        return {
            "schema_version": self.schema_version,
            "mutation_id": self.mutation_id,
            "operator": self.operator.value,
            "repository": self.repository,
            "repository_revision": self.repository_revision,
            "control_owner": self.control_owner,
            "baseline_contract_sha256": self.baseline_contract_sha256,
            "mutated_contract_sha256": self.mutated_contract_sha256,
            "protected_operation_family": self.protected_operation_family,
            "operation_input_sha256": self.operation_input_sha256,
            "expected_block_code": self.expected_block_code,
            "requires_runtime_execution": self.requires_runtime_execution,
            "requires_target_readback": self.requires_target_readback,
        }


def build_control_mutation_case(
    *,
    mutation_id: str,
    operator: ControlMutationOperator,
    repository: str,
    repository_revision: str,
    control_owner: str,
    baseline_contract: dict[str, Any],
    mutated_contract: dict[str, Any],
    protected_operation_family: str,
    operation_input_sha256: str,
    expected_block_code: Optional[str] = None,
) -> ControlMutationCase:
    """Build a ControlMutationCase with computed hashes.

    This factory ensures the single-variable invariant is satisfied:
    - Baseline and mutated contracts must share operation identity
    - Exactly one security dimension should differ

    Args:
        mutation_id: Unique identifier for this mutation case
        operator: The control mutation operator
        repository: Repository identifier
        repository_revision: Full Git SHA-40
        control_owner: Owner responsible for this control
        baseline_contract: The baseline contract dictionary
        mutated_contract: The mutated contract dictionary
        protected_operation_family: The operation family being protected
        operation_input_sha256: SHA-256 of the operation input
        expected_block_code: Optional expected block code

    Returns:
        Immutable ControlMutationCase with computed hashes
    """
    # Reject secret-shaped fields
    _reject_secret_shaped_field(baseline_contract, path="baseline_contract")
    _reject_secret_shaped_field(mutated_contract, path="mutated_contract")

    # Reject forbidden contract values (NaN, Infinity, floats, timestamp keys)
    _reject_forbidden_contract_values(baseline_contract, path="baseline_contract")
    _reject_forbidden_contract_values(mutated_contract, path="mutated_contract")

    # Validate single-variable invariant
    valid, error = validate_single_variable_invariant(baseline_contract, mutated_contract, operator)
    if not valid:
        raise ControlMutationContractError(f"single-variable invariant violated: {error}")

    # Compute contract hashes
    baseline_sha = _canonical_sha256(baseline_contract)
    mutated_sha = _canonical_sha256(mutated_contract)

    # Determine runtime requirements
    runtime_required = requires_runtime_execution(operator)
    readback_required = requires_target_readback(operator)

    # Build the case body for hash computation
    case_body = {
        "schema_version": SCHEMA_VERSION,
        "mutation_id": mutation_id,
        "operator": operator.value,
        "repository": repository,
        "repository_revision": repository_revision,
        "control_owner": control_owner,
        "baseline_contract_sha256": baseline_sha,
        "mutated_contract_sha256": mutated_sha,
        "protected_operation_family": protected_operation_family,
        "operation_input_sha256": operation_input_sha256,
        "expected_block_code": expected_block_code,
        "requires_runtime_execution": runtime_required,
        "requires_target_readback": readback_required,
    }
    computed_case_sha256 = _canonical_sha256(case_body)

    # Build the case
    case = ControlMutationCase(
        schema_version=SCHEMA_VERSION,
        mutation_id=mutation_id,
        operator=operator,
        repository=repository,
        repository_revision=repository_revision,
        control_owner=control_owner,
        baseline_contract_sha256=baseline_sha,
        mutated_contract_sha256=mutated_sha,
        protected_operation_family=protected_operation_family,
        operation_input_sha256=operation_input_sha256,
        expected_block_code=expected_block_code,
        requires_runtime_execution=runtime_required,
        requires_target_readback=readback_required,
        case_sha256=computed_case_sha256,
    )

    return case


def validate_single_variable_invariant(
    baseline_contract: dict[str, Any],
    mutated_contract: dict[str, Any],
    operator: ControlMutationOperator,
) -> Tuple[bool, str]:
    """Validate that exactly one security dimension differs between contracts.

    Args:
        baseline_contract: The baseline contract
        mutated_contract: The mutated contract
        operator: The operator being tested

    Returns:
        Tuple of (is_valid, error_message)
    """
    allowed_dimension = get_allowed_dimension(operator)

    # Collect differing keys
    differing_keys: set[str] = set()
    all_keys = set(baseline_contract.keys()) | set(mutated_contract.keys())

    for key in all_keys:
        baseline_val = baseline_contract.get(key)
        mutated_val = mutated_contract.get(key)
        if baseline_val != mutated_val:
            differing_keys.add(key)

    # Check: exactly one dimension should differ
    if len(differing_keys) == 0:
        return False, "no differing dimensions between baseline and mutated"
    if len(differing_keys) > 1:
        return False, f"multi-variable mutant forbidden: {sorted(differing_keys)} differ"

    # Check: the differing dimension must be the allowed one
    differing_dimension = list(differing_keys)[0]
    if differing_dimension != allowed_dimension.value:
        return False, (
            f"operator {operator.value} may only change {allowed_dimension.value}, "
            f"but found {differing_dimension}"
        )

    return True, ""


__all__ = [
    "ControlMutationCase",
    "ControlMutationContractError",
    "ControlMutationOperator",
    "SCHEMA_VERSION",
    "SecurityDimension",
    "build_control_mutation_case",
    "get_allowed_dimension",
    "get_operator",
    "requires_runtime_execution",
    "requires_target_readback",
    "validate_single_variable_invariant",
]
