"""Pure, fail-closed proof envelopes and verdicts for risky Sovereign operations.

The core performs no network, database, filesystem, clock or random access. It
accepts only canonical observations that were produced elsewhere. Existing
agent-run receipts remain their own truth source; the adapter below verifies and
projects them without duplicating persistence or promoting an adapter result to
VERIFIED.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Final, Mapping, Sequence

from .agent_run_receipts import (
    ReceiptContractError,
    canonical_sha256 as receipt_canonical_sha256,
    canonical_value as receipt_canonical_value,
    verify_agent_run_receipt_chain,
)


_SCHEMA_REQUIREMENT_SET: Final[str] = "sovereign.proof-requirement-set.v1"
_SCHEMA_ENVELOPE: Final[str] = "sovereign.proof-envelope.v1"
_SCHEMA_OBSERVATION: Final[str] = "sovereign.proof-observation.v1"
_SCHEMA_VERDICT: Final[str] = "sovereign.proof-verdict.v1"
_SHA40: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_SHA64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_.:-]{1,119}$")
_ALLOWED_ASSERTIONS: Final[frozenset[str]] = frozenset({"OBSERVED", "CONTRADICTED", "UNAVAILABLE"})
_ALLOWED_SOURCES: Final[frozenset[str]] = frozenset({
    "AGENT_RUN_RECEIPT",
    "CI_READBACK",
    "DATABASE_READBACK",
    "IMAGE_READBACK",
    "MCP_READBACK",
    "PATCHMON_READBACK",
    "REPOSITORY_READBACK",
    "RUNTIME_READBACK",
    "STATIC_CANDIDATE",
})
_IMPLICIT_TIME_KEYS: Final[frozenset[str]] = frozenset({
    "created_at",
    "current_time",
    "epoch",
    "now",
    "observed_at",
    "timestamp",
    "updated_at",
})


class ProofContractError(ValueError):
    """One proof input violated a deterministic or truth-boundary invariant."""


def _normalize_identifier(value: str, *, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _IDENTIFIER.fullmatch(normalized):
        raise ProofContractError(f"{label} must be a canonical identifier")
    return normalized


def _normalize_text(value: str, *, label: str, maximum: int = 240) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > maximum:
        raise ProofContractError(f"{label} must contain 1..{maximum} characters")
    return normalized


def _normalize_sha40(value: str, *, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _SHA40.fullmatch(normalized):
        raise ProofContractError(f"{label} must be a lowercase full Git SHA")
    return normalized


def _normalize_sha64(value: str, *, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _SHA64.fullmatch(normalized):
        raise ProofContractError(f"{label} must be a lowercase SHA-256")
    return normalized


def _reject_implicit_time(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            if not isinstance(raw_key, str):
                raise ProofContractError(f"non-string object key is forbidden at {path}")
            if raw_key.strip().lower() in _IMPLICIT_TIME_KEYS:
                raise ProofContractError(f"implicit time field is forbidden at {path}.{raw_key}")
            _reject_implicit_time(item, path=f"{path}.{raw_key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _reject_implicit_time(item, path=f"{path}[{index}]")


def canonical_proof_value(value: Any) -> Any:
    """Canonicalize through the existing receipt contract plus proof-only guards."""

    _reject_implicit_time(value)
    try:
        return receipt_canonical_value(value)
    except ReceiptContractError as exc:
        raise ProofContractError(str(exc)) from exc


def canonical_proof_sha256(value: Any) -> str:
    canonical_proof_value(value)
    try:
        return receipt_canonical_sha256(value)
    except ReceiptContractError as exc:
        raise ProofContractError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class ProofRequirement:
    requirement_id: str
    evidence_kind: str
    allowed_source_kinds: tuple[str, ...]
    runtime_required: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "requirement_id", _normalize_identifier(self.requirement_id, label="requirement_id"))
        object.__setattr__(self, "evidence_kind", _normalize_identifier(self.evidence_kind, label="evidence_kind"))
        sources = tuple(sorted({str(item or "").strip().upper() for item in self.allowed_source_kinds}))
        if not sources or any(item not in _ALLOWED_SOURCES for item in sources):
            raise ProofContractError("allowed_source_kinds contains an unsupported source")
        if self.runtime_required and sources == ("STATIC_CANDIDATE",):
            raise ProofContractError("a runtime requirement cannot allow only static candidates")
        object.__setattr__(self, "allowed_source_kinds", sources)
        object.__setattr__(self, "runtime_required", bool(self.runtime_required))

    def canonical_body(self) -> dict[str, Any]:
        return {
            "allowed_source_kinds": list(self.allowed_source_kinds),
            "evidence_kind": self.evidence_kind,
            "requirement_id": self.requirement_id,
            "runtime_required": self.runtime_required,
        }


@dataclass(frozen=True, slots=True)
class ProofRequirementSet:
    operation_family: str
    version: int
    requirements: tuple[ProofRequirement, ...]
    schema_version: str = _SCHEMA_REQUIREMENT_SET

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_family", _normalize_identifier(self.operation_family, label="operation_family"))
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ProofContractError("requirement-set version must be a positive integer")
        requirements = tuple(sorted(tuple(self.requirements), key=lambda item: item.requirement_id))
        if not requirements:
            raise ProofContractError("a requirement set must contain at least one requirement")
        ids = [item.requirement_id for item in requirements]
        if len(ids) != len(set(ids)):
            raise ProofContractError("requirement IDs must be unique")
        object.__setattr__(self, "requirements", requirements)
        if self.schema_version != _SCHEMA_REQUIREMENT_SET:
            raise ProofContractError("unsupported requirement-set schema version")

    @property
    def requirement_ids(self) -> tuple[str, ...]:
        return tuple(item.requirement_id for item in self.requirements)

    def canonical_body(self) -> dict[str, Any]:
        return {
            "operation_family": self.operation_family,
            "requirements": [item.canonical_body() for item in self.requirements],
            "schema_version": self.schema_version,
            "version": self.version,
        }

    @property
    def requirement_set_sha256(self) -> str:
        return canonical_proof_sha256(self.canonical_body())


@dataclass(frozen=True, slots=True)
class ProofEnvelope:
    operation_family: str
    operation_identity: str
    repository: str
    revision: str
    input_sha256: str
    diff_sha256: str
    requirement_set_version: int
    requirement_set_sha256: str
    required_requirement_ids: tuple[str, ...]
    schema_version: str = _SCHEMA_ENVELOPE

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_family", _normalize_identifier(self.operation_family, label="operation_family"))
        object.__setattr__(self, "operation_identity", _normalize_text(self.operation_identity, label="operation_identity"))
        object.__setattr__(self, "repository", _normalize_text(self.repository, label="repository"))
        object.__setattr__(self, "revision", _normalize_sha40(self.revision, label="revision"))
        object.__setattr__(self, "input_sha256", _normalize_sha64(self.input_sha256, label="input_sha256"))
        object.__setattr__(self, "diff_sha256", _normalize_sha64(self.diff_sha256, label="diff_sha256"))
        if isinstance(self.requirement_set_version, bool) or not isinstance(self.requirement_set_version, int) or self.requirement_set_version < 1:
            raise ProofContractError("requirement_set_version must be a positive integer")
        object.__setattr__(
            self,
            "requirement_set_sha256",
            _normalize_sha64(self.requirement_set_sha256, label="requirement_set_sha256"),
        )
        ids = tuple(sorted({_normalize_identifier(item, label="required_requirement_id") for item in self.required_requirement_ids}))
        if not ids:
            raise ProofContractError("required_requirement_ids must not be empty")
        object.__setattr__(self, "required_requirement_ids", ids)
        if self.schema_version != _SCHEMA_ENVELOPE:
            raise ProofContractError("unsupported proof-envelope schema version")

    def canonical_body(self) -> dict[str, Any]:
        return {
            "diff_sha256": self.diff_sha256,
            "input_sha256": self.input_sha256,
            "operation_family": self.operation_family,
            "operation_identity": self.operation_identity,
            "repository": self.repository,
            "required_requirement_ids": list(self.required_requirement_ids),
            "requirement_set_sha256": self.requirement_set_sha256,
            "requirement_set_version": self.requirement_set_version,
            "revision": self.revision,
            "schema_version": self.schema_version,
        }

    @property
    def envelope_sha256(self) -> str:
        return canonical_proof_sha256(self.canonical_body())


@dataclass(frozen=True, slots=True)
class ProofObservation:
    observation_id: str
    requirement_id: str
    evidence_kind: str
    source_kind: str
    assertion: str
    operation_family: str
    operation_identity: str
    revision: str
    input_sha256: str
    diff_sha256: str
    evidence_sha256: str
    schema_version: str = _SCHEMA_OBSERVATION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_id", _normalize_identifier(self.observation_id, label="observation_id"))
        object.__setattr__(self, "requirement_id", _normalize_identifier(self.requirement_id, label="requirement_id"))
        object.__setattr__(self, "evidence_kind", _normalize_identifier(self.evidence_kind, label="evidence_kind"))
        source = str(self.source_kind or "").strip().upper()
        if source not in _ALLOWED_SOURCES:
            raise ProofContractError("unsupported proof observation source")
        object.__setattr__(self, "source_kind", source)
        assertion = str(self.assertion or "").strip().upper()
        if assertion not in _ALLOWED_ASSERTIONS:
            raise ProofContractError("unsupported proof observation assertion")
        object.__setattr__(self, "assertion", assertion)
        object.__setattr__(self, "operation_family", _normalize_identifier(self.operation_family, label="operation_family"))
        object.__setattr__(self, "operation_identity", _normalize_text(self.operation_identity, label="operation_identity"))
        object.__setattr__(self, "revision", _normalize_sha40(self.revision, label="revision"))
        object.__setattr__(self, "input_sha256", _normalize_sha64(self.input_sha256, label="input_sha256"))
        object.__setattr__(self, "diff_sha256", _normalize_sha64(self.diff_sha256, label="diff_sha256"))
        object.__setattr__(self, "evidence_sha256", _normalize_sha64(self.evidence_sha256, label="evidence_sha256"))
        if self.schema_version != _SCHEMA_OBSERVATION:
            raise ProofContractError("unsupported proof-observation schema version")

    def canonical_body(self) -> dict[str, Any]:
        return {
            "assertion": self.assertion,
            "diff_sha256": self.diff_sha256,
            "evidence_kind": self.evidence_kind,
            "evidence_sha256": self.evidence_sha256,
            "input_sha256": self.input_sha256,
            "observation_id": self.observation_id,
            "operation_family": self.operation_family,
            "operation_identity": self.operation_identity,
            "requirement_id": self.requirement_id,
            "revision": self.revision,
            "schema_version": self.schema_version,
            "source_kind": self.source_kind,
        }

    @property
    def observation_sha256(self) -> str:
        return canonical_proof_sha256(self.canonical_body())


@dataclass(frozen=True, slots=True)
class ProofVerdict:
    status: str
    envelope_sha256: str
    requirement_set_sha256: str
    satisfied_requirements: tuple[str, ...]
    missing_requirements: tuple[str, ...]
    contradictory_requirements: tuple[str, ...]
    observation_sha256s: tuple[str, ...]
    finding_codes: tuple[str, ...]
    schema_version: str = _SCHEMA_VERDICT

    def __post_init__(self) -> None:
        status = str(self.status or "").strip().upper()
        if status not in {"VERIFIED", "CONTRADICTED", "BLOCKED_BY_MISSING_EVIDENCE"}:
            raise ProofContractError("unsupported proof verdict")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "envelope_sha256", _normalize_sha64(self.envelope_sha256, label="envelope_sha256"))
        object.__setattr__(
            self,
            "requirement_set_sha256",
            _normalize_sha64(self.requirement_set_sha256, label="requirement_set_sha256"),
        )
        for field_name in ("satisfied_requirements", "missing_requirements", "contradictory_requirements"):
            values = tuple(sorted({_normalize_identifier(item, label=field_name) for item in getattr(self, field_name)}))
            object.__setattr__(self, field_name, values)
        hashes = tuple(sorted({_normalize_sha64(item, label="observation_sha256") for item in self.observation_sha256s}))
        object.__setattr__(self, "observation_sha256s", hashes)
        findings = tuple(sorted({_normalize_identifier(item, label="finding_code") for item in self.finding_codes}))
        object.__setattr__(self, "finding_codes", findings)
        if self.schema_version != _SCHEMA_VERDICT:
            raise ProofContractError("unsupported proof-verdict schema version")
        if status == "VERIFIED" and (self.missing_requirements or self.contradictory_requirements):
            raise ProofContractError("VERIFIED cannot contain missing or contradictory requirements")
        if status == "CONTRADICTED" and not self.contradictory_requirements:
            raise ProofContractError("CONTRADICTED requires at least one contradictory requirement")
        if status == "BLOCKED_BY_MISSING_EVIDENCE" and not self.missing_requirements:
            raise ProofContractError("BLOCKED_BY_MISSING_EVIDENCE requires at least one missing requirement")

    def canonical_body(self) -> dict[str, Any]:
        return {
            "contradictory_requirements": list(self.contradictory_requirements),
            "envelope_sha256": self.envelope_sha256,
            "finding_codes": list(self.finding_codes),
            "missing_requirements": list(self.missing_requirements),
            "observation_sha256s": list(self.observation_sha256s),
            "requirement_set_sha256": self.requirement_set_sha256,
            "satisfied_requirements": list(self.satisfied_requirements),
            "schema_version": self.schema_version,
            "status": self.status,
        }

    @property
    def verdict_sha256(self) -> str:
        return canonical_proof_sha256(self.canonical_body())

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_body(), "verdict_sha256": self.verdict_sha256}


def build_proof_envelope(
    *,
    requirement_set: ProofRequirementSet,
    operation_identity: str,
    repository: str,
    revision: str,
    input_sha256: str,
    diff_sha256: str,
) -> ProofEnvelope:
    return ProofEnvelope(
        operation_family=requirement_set.operation_family,
        operation_identity=operation_identity,
        repository=repository,
        revision=revision,
        input_sha256=input_sha256,
        diff_sha256=diff_sha256,
        requirement_set_version=requirement_set.version,
        requirement_set_sha256=requirement_set.requirement_set_sha256,
        required_requirement_ids=requirement_set.requirement_ids,
    )


def evaluate_proof(
    envelope: ProofEnvelope,
    observations: Sequence[ProofObservation],
    *,
    requirement_sets: Mapping[str, ProofRequirementSet],
) -> ProofVerdict:
    requirement_set = requirement_sets.get(envelope.operation_family)
    observation_hashes = tuple(item.observation_sha256 for item in observations)
    if requirement_set is None:
        return ProofVerdict(
            status="BLOCKED_BY_MISSING_EVIDENCE",
            envelope_sha256=envelope.envelope_sha256,
            requirement_set_sha256=envelope.requirement_set_sha256,
            satisfied_requirements=(),
            missing_requirements=("registered_requirement_set",),
            contradictory_requirements=(),
            observation_sha256s=observation_hashes,
            finding_codes=("unknown_operation_family",),
        )

    binding_mismatch = (
        envelope.requirement_set_version != requirement_set.version
        or envelope.requirement_set_sha256 != requirement_set.requirement_set_sha256
        or envelope.required_requirement_ids != requirement_set.requirement_ids
    )
    if binding_mismatch:
        return ProofVerdict(
            status="CONTRADICTED",
            envelope_sha256=envelope.envelope_sha256,
            requirement_set_sha256=requirement_set.requirement_set_sha256,
            satisfied_requirements=(),
            missing_requirements=(),
            contradictory_requirements=("requirement_set_binding",),
            observation_sha256s=observation_hashes,
            finding_codes=("requirement_set_binding_mismatch",),
        )

    satisfied: set[str] = set()
    missing: set[str] = set()
    contradictory: set[str] = set()
    findings: set[str] = set()

    for requirement in requirement_set.requirements:
        candidates = [
            item
            for item in observations
            if item.requirement_id == requirement.requirement_id
            and item.evidence_kind == requirement.evidence_kind
        ]
        if not candidates:
            missing.add(requirement.requirement_id)
            findings.add("required_observation_missing")
            continue

        requirement_satisfied = False
        requirement_contradicted = False
        for observation in candidates:
            if (
                observation.operation_family != envelope.operation_family
                or observation.operation_identity != envelope.operation_identity
                or observation.revision != envelope.revision
                or observation.input_sha256 != envelope.input_sha256
                or observation.diff_sha256 != envelope.diff_sha256
            ):
                requirement_contradicted = True
                findings.add("observation_binding_mismatch")
                continue
            if observation.assertion == "CONTRADICTED":
                requirement_contradicted = True
                findings.add("observation_reports_contradiction")
                continue
            if observation.assertion == "UNAVAILABLE":
                findings.add("observation_unavailable")
                continue
            if observation.source_kind not in requirement.allowed_source_kinds:
                findings.add("observation_source_not_allowed")
                continue
            if requirement.runtime_required and observation.source_kind == "STATIC_CANDIDATE":
                findings.add("static_candidate_cannot_satisfy_runtime")
                continue
            requirement_satisfied = True

        if requirement_contradicted:
            contradictory.add(requirement.requirement_id)
        elif requirement_satisfied:
            satisfied.add(requirement.requirement_id)
        else:
            missing.add(requirement.requirement_id)

    if contradictory:
        status = "CONTRADICTED"
    elif missing:
        status = "BLOCKED_BY_MISSING_EVIDENCE"
    else:
        status = "VERIFIED"

    return ProofVerdict(
        status=status,
        envelope_sha256=envelope.envelope_sha256,
        requirement_set_sha256=requirement_set.requirement_set_sha256,
        satisfied_requirements=tuple(satisfied),
        missing_requirements=tuple(missing),
        contradictory_requirements=tuple(contradictory),
        observation_sha256s=observation_hashes,
        finding_codes=tuple(findings),
    )


def observation_from_agent_run_receipt(
    receipt: Mapping[str, Any],
    *,
    observation_id: str,
    requirement_id: str,
    operation_family: str,
    expected_repository: str,
    expected_revision: str,
) -> ProofObservation:
    """Verify and project one existing receipt into a non-verdict observation."""

    header = dict(receipt.get("header") or {})
    body = dict(receipt.get("body") or {})
    sequence = body.get("sequence")
    previous = str(body.get("previous_receipt_sha256") or "").strip().lower()
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise ProofContractError("agent receipt sequence is invalid")
    if not _SHA64.fullmatch(previous):
        raise ProofContractError("agent receipt previous hash is invalid")
    receipt_hash = _normalize_sha64(str(header.get("hash") or ""), label="agent receipt hash")
    try:
        verification = verify_agent_run_receipt_chain(
            [receipt],
            expected_repository=expected_repository,
            expected_base_commit_sha=_normalize_sha40(expected_revision, label="expected_revision"),
            expected_start_sequence=sequence,
            anchor_previous_receipt_sha256=previous,
        )
    except ReceiptContractError as exc:
        raise ProofContractError(str(exc)) from exc

    gate = str(body.get("evidence_gate_result") or "").strip().upper()
    if not verification["ok"] or gate == "FAIL":
        assertion = "CONTRADICTED"
    elif gate == "PASS":
        assertion = "OBSERVED"
    else:
        assertion = "UNAVAILABLE"

    return ProofObservation(
        observation_id=observation_id,
        requirement_id=requirement_id,
        evidence_kind="agent_run_receipt",
        source_kind="AGENT_RUN_RECEIPT",
        assertion=assertion,
        operation_family=operation_family,
        operation_identity=str(body.get("operation_identity") or ""),
        revision=str(body.get("base_commit_sha") or ""),
        input_sha256=str(body.get("input_sha256") or ""),
        diff_sha256=str(body.get("diff_sha256") or ""),
        evidence_sha256=receipt_hash,
    )


AGENT_REPOSITORY_MUTATION_REQUIREMENTS_V1: Final[ProofRequirementSet] = ProofRequirementSet(
    operation_family="agent_repository_mutation",
    version=1,
    requirements=(
        ProofRequirement(
            requirement_id="agent_run_receipt",
            evidence_kind="agent_run_receipt",
            allowed_source_kinds=("AGENT_RUN_RECEIPT",),
            runtime_required=True,
        ),
        ProofRequirement(
            requirement_id="authoritative_readback",
            evidence_kind="authoritative_readback",
            allowed_source_kinds=("CI_READBACK", "REPOSITORY_READBACK", "RUNTIME_READBACK"),
            runtime_required=True,
        ),
    ),
)

DEFAULT_PROOF_REQUIREMENT_SETS: Final[Mapping[str, ProofRequirementSet]] = {
    AGENT_REPOSITORY_MUTATION_REQUIREMENTS_V1.operation_family: AGENT_REPOSITORY_MUTATION_REQUIREMENTS_V1,
}

__all__ = [
    "AGENT_REPOSITORY_MUTATION_REQUIREMENTS_V1",
    "DEFAULT_PROOF_REQUIREMENT_SETS",
    "ProofContractError",
    "ProofEnvelope",
    "ProofObservation",
    "ProofRequirement",
    "ProofRequirementSet",
    "ProofVerdict",
    "build_proof_envelope",
    "canonical_proof_sha256",
    "canonical_proof_value",
    "evaluate_proof",
    "observation_from_agent_run_receipt",
]
