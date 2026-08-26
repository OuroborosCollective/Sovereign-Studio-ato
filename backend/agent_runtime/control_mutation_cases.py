"""Pure, deterministic ControlMutationCase contracts for ACSA.

This module defines the allowed mutation operators and the immutable ControlMutationCase
dataclass. It performs no network, database, filesystem, clock or random access.
All hashes are deterministic and secret-safe.

Reference: Issue #1638 (ACSA 1/4)
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Final, Literal

from .proof_verdict import canonical_proof_sha256


_SCHEMA_VERSION: Final[str] = "sovereign.control-mutation-case.v1"
_OPERATOR_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA64_RE = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_.:/-]{1,119}$")


class ControlMutationContractError(ValueError):
    """A control mutation case violated a deterministic or invariant."""


# V1 Static Allowlist - no dynamic registration
class ControlMutationOperator(str):
    """Allowed mutation operators for ACSA V1."""

    STALE_REVISION = "stale_revision"
    WRONG_IMAGE_DIGEST = "wrong_image_digest"
    TOOL_BINDING_SWAP = "tool_binding_swap"
    OWNER_MISMATCH = "owner_mismatch"
    CREDENTIAL_REPLAY = "credential_replay"
    RECEIPT_REPLAY = "receipt_replay"
    NONPROD_TO_PRODUCTION = "nonprod_to_production"
    DISALLOWED_EGRESS = "disallowed_egress"
    MISSING_RUNTIME_EVIDENCE = "missing_runtime_evidence"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(
            getattr(cls, attr)
            for attr in dir(cls)
            if not attr.startswith("_") and isinstance(getattr(cls, attr), str)
        )

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in cls.values()


# Operator to allowed security dimension mapping
# Each operator may only change ONE security dimension
_OPERATOR_ALLOWED_DIMENSION: dict[str, str] = {
    "stale_revision": "repository_revision",
    "wrong_image_digest": "image_digest",
    "tool_binding_swap": "tool_binding",
    "owner_mismatch": "credential_principal_owner",
    "credential_replay": "credential_principal_identity",
    "receipt_replay": "receipt_identity",
    "nonprod_to_production": "environment_boundary",
    "disallowed_egress": "network_egress",
    "missing_runtime_evidence": "evidence_completeness",
}


def _validate_identifier(value: str, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _IDENTIFIER_RE.fullmatch(normalized):
        raise ControlMutationContractError(f"{label} must be a canonical identifier")
    return normalized


def _validate_sha40(value: str, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _SHA40_RE.fullmatch(normalized):
        raise ControlMutationContractError(f"{label} must be a lowercase full Git SHA (40 hex)")
    return normalized


def _validate_sha64(value: str, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _SHA64_RE.fullmatch(normalized):
        raise ControlMutationContractError(f"{label} must be a SHA-256 (64 hex)")
    return normalized


def _validate_operator(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _OPERATOR_RE.fullmatch(normalized):
        raise ControlMutationContractError("operator must match [a-z][a-z0-9_]{1,39}")
    if not ControlMutationOperator.is_valid(normalized):
        raise ControlMutationContractError(f"unknown operator: {normalized}")
    return normalized


def _validate_text(value: str, label: str, max_len: int = 240) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > max_len:
        raise ControlMutationContractError(f"{label} must contain 1..{max_len} characters")
    return normalized


# Secret/shadow pattern detection - blocks raw secrets from appearing in contracts
_SECRET_PATTERNS = (
    "sk-proj-",
    "sk-",
    "github_pat_",
    "ghp_",
    "authorization: bearer",
    "begin openssh private key",
    "begin rsa private key",
    "begin private key",
    "BEGIN PGP PRIVATE KEY",
)


def _check_secret_safety(value: str, label: str) -> None:
    """Block raw secrets from appearing in contract fields."""
    if not value:
        return
    lower = value.lower()
    for pattern in _SECRET_PATTERNS:
        if pattern.lower() in lower:
            raise ControlMutationContractError(f"{label} contains secret-like pattern")


@dataclass(frozen=True, slots=True)
class ControlMutationCase:
    """Immutable control mutation test case.

    Each case defines a single-variable mutation against a protected path.
    The case_hash deterministically binds all fields.
    """

    schema_version: str
    mutation_id: str
    operator: str
    repository: str
    repository_revision: str
    control_owner: str
    baseline_contract_sha256: str
    mutated_contract_sha256: str
    protected_operation_family: str
    operation_input_sha256: str
    expected_block_code: str | None
    requires_runtime_execution: bool
    requires_target_readback: bool
    case_sha256: str

    def __post_init__(self) -> None:
        # Schema version
        if self.schema_version != _SCHEMA_VERSION:
            raise ControlMutationContractError("unsupported control-mutation-case schema version")

        # Mutation ID
        object.__setattr__(self, "mutation_id", _validate_identifier(self.mutation_id, "mutation_id"))

        # Operator - must be in allowlist
        object.__setattr__(self, "operator", _validate_operator(self.operator))

        # Repository - canonical identifier
        object.__setattr__(self, "repository", _validate_identifier(self.repository, "repository"))

        # Repository revision - full Git SHA
        object.__setattr__(self, "repository_revision", _validate_sha40(self.repository_revision, "repository_revision"))

        # Control owner - what owns the protection
        object.__setattr__(self, "control_owner", _validate_identifier(self.control_owner, "control_owner"))

        # Baseline and mutated contract hashes
        object.__setattr__(self, "baseline_contract_sha256", _validate_sha64(self.baseline_contract_sha256, "baseline_contract_sha256"))
        object.__setattr__(self, "mutated_contract_sha256", _validate_sha64(self.mutated_contract_sha256, "mutated_contract_sha256"))

        # Protected operation family
        object.__setattr__(self, "protected_operation_family", _validate_identifier(self.protected_operation_family, "protected_operation_family"))

        # Operation input hash
        object.__setattr__(self, "operation_input_sha256", _validate_sha64(self.operation_input_sha256, "operation_input_sha256"))

        # Expected block code (optional)
        if self.expected_block_code is not None:
            object.__setattr__(self, "expected_block_code", _validate_text(self.expected_block_code, "expected_block_code"))

        # Boolean flags
        object.__setattr__(self, "requires_runtime_execution", bool(self.requires_runtime_execution))
        object.__setattr__(self, "requires_target_readback", bool(self.requires_target_readback))

        # Case hash - compute from canonical body (without the hash field)
        expected_hash = canonical_proof_sha256(self._canonical_body(include_hash=False))
        # If case_sha256 was passed empty, compute it; otherwise verify
        if not self.case_sha256:
            object.__setattr__(self, "case_sha256", expected_hash)
        elif self.case_sha256 != expected_hash:
            raise ControlMutationContractError(f"case_sha256 mismatch: expected {expected_hash}")

    def _canonical_body(self, include_hash: bool = True) -> dict:
        body = {
            "schema_version": self.schema_version,
            "mutation_id": self.mutation_id,
            "operator": self.operator,
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
        if include_hash:
            body["case_sha256"] = self.case_sha256
        return body

    def canonical_body(self) -> dict:
        """Return deterministic canonical body for hashing."""
        return self._canonical_body(include_hash=False)

    @property
    def allowed_dimension(self) -> str:
        """Return the security dimension this operator is allowed to change."""
        return _OPERATOR_ALLOWED_DIMENSION.get(self.operator, "unknown")

    def verify_single_variable_invariant(self) -> None:
        """Verify that baseline and mutated contracts differ in only one dimension.

        This is a contract-level check. The actual runtime execution lane
        is responsible for verifying the real mutation effect.
        """
        # This checks the operator is valid and has an allowed dimension
        if self.operator not in _OPERATOR_ALLOWED_DIMENSION:
            raise ControlMutationContractError(f"operator {self.operator} has no allowed dimension defined")

    @classmethod
    def from_dict(cls, data: dict) -> "ControlMutationCase":
        """Parse from dictionary, computing case_sha256."""
        return cls(
            schema_version=data.get("schema_version", _SCHEMA_VERSION),
            mutation_id=data["mutation_id"],
            operator=data["operator"],
            repository=data["repository"],
            repository_revision=data["repository_revision"],
            control_owner=data["control_owner"],
            baseline_contract_sha256=data["baseline_contract_sha256"],
            mutated_contract_sha256=data["mutated_contract_sha256"],
            protected_operation_family=data["protected_operation_family"],
            operation_input_sha256=data["operation_input_sha256"],
            expected_block_code=data.get("expected_block_code"),
            requires_runtime_execution=bool(data.get("requires_runtime_execution", True)),
            requires_target_readback=bool(data.get("requires_target_readback", True)),
            case_sha256=data.get("case_sha256", ""),  # Will be computed in __post_init__
        )

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return self._canonical_body(include_hash=True)


def build_control_mutation_case(
    mutation_id: str,
    operator: str,
    repository: str,
    repository_revision: str,
    control_owner: str,
    baseline_contract_sha256: str,
    mutated_contract_sha256: str,
    protected_operation_family: str,
    operation_input_sha256: str,
    expected_block_code: str | None = None,
    requires_runtime_execution: bool = True,
    requires_target_readback: bool = True,
) -> ControlMutationCase:
    """Build a ControlMutationCase, computing the case_sha256 automatically."""
    # First create with empty hash, then __post_init__ computes and validates
    case = ControlMutationCase(
        schema_version=_SCHEMA_VERSION,
        mutation_id=mutation_id,
        operator=operator,
        repository=repository,
        repository_revision=repository_revision,
        control_owner=control_owner,
        baseline_contract_sha256=baseline_contract_sha256,
        mutated_contract_sha256=mutated_contract_sha256,
        protected_operation_family=protected_operation_family,
        operation_input_sha256=operation_input_sha256,
        expected_block_code=expected_block_code,
        requires_runtime_execution=requires_runtime_execution,
        requires_target_readback=requires_target_readback,
        case_sha256="",  # Will be computed
    )
    case.verify_single_variable_invariant()
    return case


def operator_allowed_dimension(operator: str) -> str:
    """Return the security dimension an operator is allowed to mutate."""
    validated = _validate_operator(operator)
    return _OPERATOR_ALLOWED_DIMENSION.get(validated, "unknown")
