"""Pure fail-closed contract core for the Sovereign Architecture Truth Compiler.

This module does not inspect a repository, contact a runtime, invoke an LLM, or
perform an effect. Callers must supply independently collected, revision-bound
evidence. The core only canonicalizes, binds and evaluates that evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, Mapping, Sequence


_SCHEMA_POLICY = "sovereign.architecture-truth-policy.v1"
_SCHEMA_CONTRACT = "sovereign.architecture-truth-contract.v1"
_SCHEMA_DECISION = "sovereign.architecture-truth-decision.v1"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.:-]{1,119}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_EVIDENCE_KINDS = frozenset({
    "architecture_inventory",
    "architecture_drift_report",
    "backend_assessment",
    "canonical_ownership",
    "repository_snapshot",
    "runtime_readback",
})


class ArchitectureTruthContractError(ValueError):
    """Raised when a caller crosses a SATC truth-boundary invariant."""


class ArchitectureTruthVerdict(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_REVALIDATION = "REQUIRE_REVALIDATION"
    CONTRADICTED = "CONTRADICTED"


class EvidenceAssertion(str, Enum):
    OBSERVED = "OBSERVED"
    CONTRADICTED = "CONTRADICTED"
    UNAVAILABLE = "UNAVAILABLE"


def _identifier(value: Any, *, field: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _IDENTIFIER.fullmatch(normalized):
        raise ArchitectureTruthContractError(f"{field} must be a canonical identifier")
    return normalized


def _sha40(value: Any, *, field: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _SHA40.fullmatch(normalized):
        raise ArchitectureTruthContractError(f"{field} must be a lowercase full Git SHA")
    return normalized


def _sha256(value: Any, *, field: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _SHA256.fullmatch(normalized):
        raise ArchitectureTruthContractError(f"{field} must be a lowercase SHA-256")
    return normalized


def canonical_json(value: Any) -> str:
    """Encode only canonical JSON values suitable for identity hashing."""

    def validate(item: Any, path: str = "$") -> None:
        if item is None or isinstance(item, (bool, int, str)):
            return
        if isinstance(item, float):
            raise ArchitectureTruthContractError(f"floating-point values are forbidden at {path}")
        if isinstance(item, Mapping):
            for key, nested in item.items():
                if not isinstance(key, str):
                    raise ArchitectureTruthContractError(f"non-string key is forbidden at {path}")
                validate(nested, f"{path}.{key}")
            return
        if isinstance(item, Sequence) and not isinstance(item, (bytes, bytearray, str)):
            for index, nested in enumerate(item):
                validate(nested, f"{path}[{index}]")
            return
        raise ArchitectureTruthContractError(f"unsupported canonical value at {path}")

    validate(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ArchitectureEvidence:
    evidence_kind: str
    repository: str
    repository_revision: str
    evidence_sha256: str
    assertion: EvidenceAssertion = EvidenceAssertion.OBSERVED

    def __post_init__(self) -> None:
        kind = _identifier(self.evidence_kind, field="evidence_kind")
        if kind not in _EVIDENCE_KINDS:
            raise ArchitectureTruthContractError("unsupported evidence_kind")
        object.__setattr__(self, "evidence_kind", kind)
        repository = str(self.repository or "").strip()
        if not _REPOSITORY.fullmatch(repository):
            raise ArchitectureTruthContractError("repository must be owner/name")
        object.__setattr__(self, "repository", repository)
        object.__setattr__(self, "repository_revision", _sha40(self.repository_revision, field="repository_revision"))
        object.__setattr__(self, "evidence_sha256", _sha256(self.evidence_sha256, field="evidence_sha256"))
        object.__setattr__(self, "assertion", EvidenceAssertion(self.assertion))

    def canonical_record(self) -> dict[str, str]:
        return {
            "assertion": self.assertion.value,
            "evidenceKind": self.evidence_kind,
            "evidenceSha256": self.evidence_sha256,
            "repository": self.repository,
            "repositoryRevision": self.repository_revision,
        }


@dataclass(frozen=True, slots=True)
class ArchitectureInvariant:
    invariant_id: str
    version: int
    domain: str
    required_evidence_kinds: tuple[str, ...]
    requires_runtime_evidence: bool
    failure_mode: ArchitectureTruthVerdict

    def __post_init__(self) -> None:
        object.__setattr__(self, "invariant_id", _identifier(self.invariant_id, field="invariant_id"))
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ArchitectureTruthContractError("invariant version must be a positive integer")
        object.__setattr__(self, "domain", _identifier(self.domain, field="domain"))
        kinds = tuple(sorted({_identifier(item, field="required_evidence_kind") for item in self.required_evidence_kinds}))
        if not kinds or any(item not in _EVIDENCE_KINDS for item in kinds):
            raise ArchitectureTruthContractError("invariant requires supported evidence kinds")
        object.__setattr__(self, "required_evidence_kinds", kinds)
        object.__setattr__(self, "requires_runtime_evidence", bool(self.requires_runtime_evidence))
        failure_mode = ArchitectureTruthVerdict(self.failure_mode)
        if failure_mode not in {ArchitectureTruthVerdict.DENY, ArchitectureTruthVerdict.REQUIRE_REVALIDATION}:
            raise ArchitectureTruthContractError("invariant failure mode must deny or require revalidation")
        object.__setattr__(self, "failure_mode", failure_mode)

    def canonical_record(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "failureMode": self.failure_mode.value,
            "invariantId": self.invariant_id,
            "requiredEvidenceKinds": list(self.required_evidence_kinds),
            "requiresRuntimeEvidence": self.requires_runtime_evidence,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class ArchitecturePolicy:
    policy_id: str
    policy_version: int
    repository: str
    required_evidence_kinds: tuple[str, ...]
    invariants: tuple[ArchitectureInvariant, ...]
    schema_version: str = _SCHEMA_POLICY

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _identifier(self.policy_id, field="policy_id"))
        if isinstance(self.policy_version, bool) or not isinstance(self.policy_version, int) or self.policy_version < 1:
            raise ArchitectureTruthContractError("policy_version must be a positive integer")
        repository = str(self.repository or "").strip()
        if not _REPOSITORY.fullmatch(repository):
            raise ArchitectureTruthContractError("policy repository must be owner/name")
        object.__setattr__(self, "repository", repository)
        kinds = tuple(sorted({_identifier(item, field="required_evidence_kind") for item in self.required_evidence_kinds}))
        if not kinds or any(item not in _EVIDENCE_KINDS for item in kinds):
            raise ArchitectureTruthContractError("policy requires supported evidence kinds")
        object.__setattr__(self, "required_evidence_kinds", kinds)
        invariants = tuple(sorted(self.invariants, key=lambda item: item.invariant_id))
        if not invariants or len({item.invariant_id for item in invariants}) != len(invariants):
            raise ArchitectureTruthContractError("policy invariants must be non-empty and uniquely identified")
        object.__setattr__(self, "invariants", invariants)
        if self.schema_version != _SCHEMA_POLICY:
            raise ArchitectureTruthContractError("unsupported policy schema version")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ArchitecturePolicy":
        if not isinstance(value, Mapping):
            raise ArchitectureTruthContractError("policy must be an object")
        raw_invariants = value.get("invariants")
        if not isinstance(raw_invariants, list):
            raise ArchitectureTruthContractError("policy invariants must be a list")
        return cls(
            policy_id=value.get("policyId"),
            policy_version=value.get("policyVersion"),
            repository=value.get("repository"),
            required_evidence_kinds=tuple(value.get("requiredEvidenceKinds") or ()),
            invariants=tuple(ArchitectureInvariant(
                invariant_id=item.get("invariantId"),
                version=item.get("version"),
                domain=item.get("domain"),
                required_evidence_kinds=tuple(item.get("requiredEvidenceKinds") or ()),
                requires_runtime_evidence=bool(item.get("requiresRuntimeEvidence")),
                failure_mode=item.get("failureMode"),
            ) for item in raw_invariants if isinstance(item, Mapping)),
            schema_version=value.get("schemaVersion"),
        )

    def canonical_record(self) -> dict[str, Any]:
        return {
            "invariants": [item.canonical_record() for item in self.invariants],
            "policyId": self.policy_id,
            "policyVersion": self.policy_version,
            "repository": self.repository,
            "requiredEvidenceKinds": list(self.required_evidence_kinds),
            "schemaVersion": self.schema_version,
        }

    @property
    def policy_sha256(self) -> str:
        return canonical_sha256(self.canonical_record())


@dataclass(frozen=True, slots=True)
class CompiledArchitectureTruthContract:
    repository: str
    repository_revision: str
    architecture_policy_revision: int
    architecture_policy_sha256: str
    evidence: tuple[ArchitectureEvidence, ...]
    invariants: tuple[ArchitectureInvariant, ...]
    schema_version: str = _SCHEMA_CONTRACT

    def __post_init__(self) -> None:
        repository = str(self.repository or "").strip()
        if not _REPOSITORY.fullmatch(repository):
            raise ArchitectureTruthContractError("contract repository must be owner/name")
        object.__setattr__(self, "repository", repository)
        object.__setattr__(self, "repository_revision", _sha40(self.repository_revision, field="repository_revision"))
        if isinstance(self.architecture_policy_revision, bool) or not isinstance(self.architecture_policy_revision, int) or self.architecture_policy_revision < 1:
            raise ArchitectureTruthContractError("architecture_policy_revision must be positive")
        object.__setattr__(self, "architecture_policy_sha256", _sha256(self.architecture_policy_sha256, field="architecture_policy_sha256"))
        evidence = tuple(sorted(self.evidence, key=lambda item: item.evidence_kind))
        if not evidence or len({item.evidence_kind for item in evidence}) != len(evidence):
            raise ArchitectureTruthContractError("contract evidence kinds must be unique and non-empty")
        if any(item.repository != repository or item.repository_revision != self.repository_revision for item in evidence):
            raise ArchitectureTruthContractError("contract evidence must bind the exact repository revision")
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "invariants", tuple(sorted(self.invariants, key=lambda item: item.invariant_id)))
        if self.schema_version != _SCHEMA_CONTRACT:
            raise ArchitectureTruthContractError("unsupported contract schema version")

    def canonical_record(self) -> dict[str, Any]:
        return {
            "architecturePolicyRevision": self.architecture_policy_revision,
            "architecturePolicySha256": self.architecture_policy_sha256,
            "evidence": [item.canonical_record() for item in self.evidence],
            "invariants": [item.canonical_record() for item in self.invariants],
            "repository": self.repository,
            "repositoryRevision": self.repository_revision,
            "schemaVersion": self.schema_version,
        }

    @property
    def contract_sha256(self) -> str:
        return canonical_sha256(self.canonical_record())


def compile_architecture_truth_contract(
    *,
    policy: ArchitecturePolicy,
    evidence: Sequence[ArchitectureEvidence],
) -> CompiledArchitectureTruthContract:
    """Compile current same-revision evidence into one deterministic SATC contract."""
    evidence_items = tuple(evidence)
    provided_kinds = {item.evidence_kind for item in evidence_items}
    missing = sorted(set(policy.required_evidence_kinds) - provided_kinds)
    if missing:
        raise ArchitectureTruthContractError(f"required evidence is missing: {','.join(missing)}")
    if any(item.repository != policy.repository for item in evidence_items):
        raise ArchitectureTruthContractError("evidence repository differs from policy repository")
    revisions = {item.repository_revision for item in evidence_items}
    if len(revisions) != 1:
        raise ArchitectureTruthContractError("evidence revisions are not identical")
    return CompiledArchitectureTruthContract(
        repository=policy.repository,
        repository_revision=next(iter(revisions)),
        architecture_policy_revision=policy.policy_version,
        architecture_policy_sha256=policy.policy_sha256,
        evidence=evidence_items,
        invariants=policy.invariants,
    )


def evaluate_pre_effect(
    *,
    contract: CompiledArchitectureTruthContract,
    effect_id: str,
    effect_domain: str,
    effect_repository: str,
    effect_revision: str,
    runtime_evidence: ArchitectureEvidence | None = None,
) -> dict[str, Any]:
    """Evaluate a requested effect without executing, authorizing or claiming it."""
    normalized_effect_id = _identifier(effect_id, field="effect_id")
    normalized_domain = _identifier(effect_domain, field="effect_domain")
    repository = str(effect_repository or "").strip()
    revision = _sha40(effect_revision, field="effect_revision")
    if repository != contract.repository:
        verdict = ArchitectureTruthVerdict.CONTRADICTED
        findings = ("EFFECT_REPOSITORY_MISMATCH",)
    elif revision != contract.repository_revision:
        verdict = ArchitectureTruthVerdict.REQUIRE_REVALIDATION
        findings = ("EFFECT_REVISION_STALE",)
    else:
        relevant = tuple(item for item in contract.invariants if item.domain == normalized_domain)
        if not relevant:
            verdict = ArchitectureTruthVerdict.DENY
            findings = ("EFFECT_DOMAIN_NOT_DECLARED",)
        else:
            evidence_by_kind = {item.evidence_kind: item for item in contract.evidence}
            contradiction = any(item.assertion == EvidenceAssertion.CONTRADICTED for item in contract.evidence)
            missing: set[str] = set()
            requires_runtime = False
            for invariant in relevant:
                missing.update(kind for kind in invariant.required_evidence_kinds if kind not in evidence_by_kind)
                requires_runtime = requires_runtime or invariant.requires_runtime_evidence
            runtime_valid = runtime_evidence is not None and (
                runtime_evidence.repository == repository
                and runtime_evidence.repository_revision == revision
                and runtime_evidence.evidence_kind == "runtime_readback"
                and runtime_evidence.assertion == EvidenceAssertion.OBSERVED
            )
            if contradiction:
                verdict = ArchitectureTruthVerdict.CONTRADICTED
                findings = ("CONTRACT_EVIDENCE_CONTRADICTED",)
            elif missing:
                verdict = ArchitectureTruthVerdict.DENY
                findings = tuple(f"MISSING_CONTRACT_EVIDENCE:{item}" for item in sorted(missing))
            elif requires_runtime and not runtime_valid:
                verdict = ArchitectureTruthVerdict.REQUIRE_REVALIDATION
                findings = ("RUNTIME_REVISION_EVIDENCE_MISSING_OR_STALE",)
            else:
                verdict = ArchitectureTruthVerdict.ALLOW
                findings = ("PRE_EFFECT_CONTRACT_SATISFIED",)
    decision = {
        "contractSha256": contract.contract_sha256,
        "effectDomain": normalized_domain,
        "effectId": normalized_effect_id,
        "effectRepository": repository,
        "effectRevision": revision,
        "findings": list(findings),
        "schemaVersion": _SCHEMA_DECISION,
        "verdict": verdict.value,
    }
    return {**decision, "decisionSha256": canonical_sha256(decision)}


__all__ = [
    "ArchitectureEvidence",
    "ArchitectureInvariant",
    "ArchitecturePolicy",
    "ArchitectureTruthContractError",
    "ArchitectureTruthVerdict",
    "CompiledArchitectureTruthContract",
    "EvidenceAssertion",
    "canonical_json",
    "canonical_sha256",
    "compile_architecture_truth_contract",
    "evaluate_pre_effect",
]
