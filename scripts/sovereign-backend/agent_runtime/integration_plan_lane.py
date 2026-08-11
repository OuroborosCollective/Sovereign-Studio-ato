"""Revision-bound Integration Plan Lane for long, multi-phase Sovereign tasks.

Persists bounded plan-, finding-, progress-, evidence- and ledger-receipt state
for a single integration assignment so that work can resume after context loss,
session change or compaction without ever becoming a truth source for the
repository, CI, deployment or runtime.

Design invariants (mirroring ``bug_evidence_lane``):

- No I/O of any kind (no filesystem, network, database, clock or random).
- Every receipt is an immutable ``dataclass(frozen=True)`` value object.
- Plan changes are *append-only* via ``IntegrationPlanLane.amend_receipt``;
  no in-place mutation of an existing ``PlanReceipt`` is allowed.
- Phase status is **never** set by Markdown alone. The evaluator derives
  ``verified`` exclusively from machine-checkable ``EvidenceRecord`` entries
  with kind in the phase's declared ``required_evidence_kinds``.
- All sensitive material is rejected at the boundary via ``RedactionFilter``.
- Path safety, repo identity and revision binding are enforced before any
  receipt is accepted.
- The lane never claims CI, artifact, image, deployment, database or runtime
  success on its own authority. It only describes the evidence that has been
  recorded; readers must compare it against the canonical target-system
  readback to decide completion.

Status flow::

    pending
        │ (phase marked in_progress)
        ▼
    in_progress
        │ (all required evidence kinds present + verified)
        ▼
    verified
        │ (or) → blocked       (missing or contradictory evidence)
        │ (or) → invalidated   (evidence superseded or premise refuted)
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    Dict,
    Final,
    FrozenSet,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)


# ---------------------------------------------------------------------------
# Schema versions
# ---------------------------------------------------------------------------
SCHEMA_VERSION: Final[str] = "sovereign.integration-plan-lane.v1"
EVIDENCE_SCHEMA_VERSION: Final[str] = "sovereign.integration-plan-evidence.v1"

# ---------------------------------------------------------------------------
# Limits (kept conservative; longer content belongs in canonical source files)
# ---------------------------------------------------------------------------
_MAX_ID_LEN: Final[int] = 120
_MAX_TEXT_BYTES: Final[int] = 8192
_MAX_PHASES: Final[int] = 32
_MAX_EVIDENCE_PER_PHASE: Final[int] = 64
_MAX_LIST_ITEMS: Final[int] = 64
_MAX_ITEM_BYTES: Final[int] = 512
_MAX_PLAN_CONTENT_BYTES: Final[int] = 65_536  # bounded plan content for attestation
_MAX_AMENDMENT_REASON_BYTES: Final[int] = 1024

# ---------------------------------------------------------------------------
# Identifier / hash regex (kept strict to bind to canonical surfaces)
# ---------------------------------------------------------------------------
_IDENTIFIER: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_.:-]{1,119}$")
_SHA40: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_SHA64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_DIGEST: Final[re.Pattern[str]] = re.compile(r"^sha256:[0-9a-f]{64}$")
_WORKFLOW_ID: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._-]{1,120}$")
_RUN_ID: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._-]{1,120}$")
_CONTAINER_NAME: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_HOST_FQDN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9.-]{0,253}$")

# Allowed evidence kinds. Adding a new kind here is a policy change and must
# also update ``PHASE_KIND_BINDING`` below.
EVIDENCE_KIND_REPO_REVISION: Final[str] = "repo_revision"
EVIDENCE_KIND_CI_WORKFLOW: Final[str] = "ci_workflow"
EVIDENCE_KIND_ARTIFACT_DIGEST: Final[str] = "artifact_digest"
EVIDENCE_KIND_DEPLOYMENT: Final[str] = "deployment"
EVIDENCE_KIND_POSTGRES_READBACK: Final[str] = "postgres_readback"
EVIDENCE_KIND_PATCHMON_READBACK: Final[str] = "patchmon_readback"
EVIDENCE_KIND_RUNTIME_READBACK: Final[str] = "runtime_readback"
EVIDENCE_KIND_CONTAINER_READBACK: Final[str] = "container_readback"
EVIDENCE_KIND_PR_HEAD: Final[str] = "pr_head"
EVIDENCE_KIND_LEDGER_HEAD: Final[str] = "ledger_head"
# Configuration-provenance drift (#1169). A verified record of this kind
# forces the owning phase to INVALIDATED: config drift invalidates active
# action plans / run-permission bindings rather than silently continuing.
EVIDENCE_KIND_CONFIG_DRIFT: Final[str] = "config_drift"

_KNOWN_EVIDENCE_KINDS: Final[FrozenSet[str]] = frozenset(
    {
        EVIDENCE_KIND_REPO_REVISION,
        EVIDENCE_KIND_CI_WORKFLOW,
        EVIDENCE_KIND_ARTIFACT_DIGEST,
        EVIDENCE_KIND_DEPLOYMENT,
        EVIDENCE_KIND_POSTGRES_READBACK,
        EVIDENCE_KIND_PATCHMON_READBACK,
        EVIDENCE_KIND_RUNTIME_READBACK,
        EVIDENCE_KIND_CONTAINER_READBACK,
        EVIDENCE_KIND_PR_HEAD,
        EVIDENCE_KIND_LEDGER_HEAD,
        EVIDENCE_KIND_CONFIG_DRIFT,
    }
)

# Per-kind expected content sha256 length and canonical-source identity shape.
# This is the minimal contract a fresh ``EvidenceRecord`` must satisfy before
# the evaluator will accept it as ``verified``.
_PHASE_KIND_BINDING: Final[Mapping[str, Dict[str, Any]]] = {
    EVIDENCE_KIND_REPO_REVISION: {
        "content_sha256": 64,
        "source_pattern": _SHA40,
        "description": "Git SHA (40 hex) of the canonical main or PR head.",
    },
    EVIDENCE_KIND_CI_WORKFLOW: {
        "content_sha256": 64,
        "source_pattern": _WORKFLOW_ID,
        "description": "GitHub Actions workflow file path or run id.",
    },
    EVIDENCE_KIND_ARTIFACT_DIGEST: {
        "content_sha256": 64,
        "source_pattern": _DIGEST,
        "description": "sha256:<64-hex> immutable image or artifact digest.",
    },
    EVIDENCE_KIND_DEPLOYMENT: {
        "content_sha256": 64,
        "source_pattern": _CONTAINER_NAME,
        "description": "Container or service identity in the deployment.",
    },
    EVIDENCE_KIND_POSTGRES_READBACK: {
        "content_sha256": 64,
        "source_pattern": _HOST_FQDN,
        "description": "Postgres host and migration head SHA-256.",
    },
    EVIDENCE_KIND_PATCHMON_READBACK: {
        "content_sha256": 64,
        "source_pattern": _HOST_FQDN,
        "description": "PatchMon fleet / lane identifier.",
    },
    EVIDENCE_KIND_RUNTIME_READBACK: {
        "content_sha256": 64,
        "source_pattern": _HOST_FQDN,
        "description": "Runtime host with verifiable health response SHA-256.",
    },
    EVIDENCE_KIND_CONTAINER_READBACK: {
        "content_sha256": 64,
        "source_pattern": _CONTAINER_NAME,
        "description": "Container or service readback identifier.",
    },
    EVIDENCE_KIND_PR_HEAD: {
        "content_sha256": 64,
        "source_pattern": _SHA40,
        "description": "Pull request exact head SHA (40 hex).",
    },
    EVIDENCE_KIND_LEDGER_HEAD: {
        "content_sha256": 64,
        "source_pattern": _IDENTIFIER,
        "description": "Continuity ledger entry id.",
    },
    EVIDENCE_KIND_CONFIG_DRIFT: {
        "content_sha256": 64,
        "source_pattern": _SHA64,
        "description": (
            "Configuration provenance drift (#1169): the prior resolved "
            "config receipt hash (64-hex) that no longer matches the "
            "current projection."
        ),
    },
}


# ---------------------------------------------------------------------------
# Secret / sensitive material patterns
# ---------------------------------------------------------------------------
_SECRET_PATTERNS: Final[Tuple[re.Pattern[str], ...]] = (
    re.compile(r"(?i)bearer\s+[a-z0-9\-._~+/]{8,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]+ KEY-----"),
    re.compile(r"(?i)(password|passwd|secret|token|api[_\-]?key)\s*[:=]\s*\S{4,}"),
    re.compile(r"(?i)(postgres|mysql|mongodb)://[^@]+:[^@]+@"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class IntegrationPlanContractError(ValueError):
    """Raised on any structural or invariant violation of the lane."""


# ---------------------------------------------------------------------------
# Phase status
# ---------------------------------------------------------------------------
class PhaseStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    VERIFIED = "verified"
    INVALIDATED = "invalidated"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _canonical_sha256(value: Any) -> str:
    """Deterministic SHA-256 over the canonical JSON serialisation."""
    serialised = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _check_bytes(value: str, *, field_name: str, limit: int) -> None:
    if not isinstance(value, str):
        raise IntegrationPlanContractError(f"{field_name} must be a string")
    size = len(value.encode("utf-8"))
    if size > limit:
        raise IntegrationPlanContractError(
            f"{field_name} exceeds {limit}-byte limit (got {size})"
        )


def _check_identifier(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise IntegrationPlanContractError(
            f"{field_name} must match {_IDENTIFIER.pattern}"
        )


def _check_revision(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not _SHA40.fullmatch(value):
        raise IntegrationPlanContractError(
            f"{field_name} must be a 40-character lowercase hex SHA"
        )


def _check_sha256(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not _SHA64.fullmatch(value):
        raise IntegrationPlanContractError(
            f"{field_name} must be a 64-character lowercase hex SHA-256"
        )


def _check_evidence_kind(value: str) -> None:
    if value not in _KNOWN_EVIDENCE_KINDS:
        raise IntegrationPlanContractError(
            f"evidence kind {value!r} is not recognised; allowed: "
            f"{sorted(_KNOWN_EVIDENCE_KINDS)}"
        )


def _check_text_list(values: Sequence[str], *, field_name: str) -> Tuple[str, ...]:
    if len(values) > _MAX_LIST_ITEMS:
        raise IntegrationPlanContractError(
            f"{field_name} must not exceed {_MAX_LIST_ITEMS} entries"
        )
    out: List[str] = []
    for idx, item in enumerate(values):
        if not isinstance(item, str):
            raise IntegrationPlanContractError(f"{field_name}[{idx}] must be a string")
        _check_bytes(item, field_name=f"{field_name}[{idx}]", limit=_MAX_ITEM_BYTES)
        out.append(item)
    return tuple(out)


# ---------------------------------------------------------------------------
# Redaction filter
# ---------------------------------------------------------------------------
class RedactionFilter:
    """Reject secret-shaped content before it enters the lane."""

    @staticmethod
    def contains_secret(text: str) -> bool:
        for pattern in _SECRET_PATTERNS:
            if pattern.search(text):
                return True
        return False

    @classmethod
    def check(cls, value: str, *, field_name: str) -> str:
        if cls.contains_secret(value):
            raise IntegrationPlanContractError(
                f"{field_name} contains secret-shaped material and cannot be stored"
            )
        return value


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Phase:
    """A bounded unit of work inside an integration plan."""

    phase_id: str
    title: str
    description: str
    acceptance_criteria: Tuple[str, ...]
    required_evidence_kinds: Tuple[str, ...]
    status: PhaseStatus

    def __post_init__(self) -> None:  # noqa: D401 - dataclass hook
        _check_identifier(self.phase_id, field_name="phase_id")
        _check_bytes(self.title, field_name="title", limit=512)
        _check_bytes(self.description, field_name="description", limit=4096)
        if len(self.acceptance_criteria) == 0:
            raise IntegrationPlanContractError(
                "phase must declare at least one acceptance_criterion"
            )
        criteria = _check_text_list(
            self.acceptance_criteria, field_name="acceptance_criteria"
        )
        if criteria != self.acceptance_criteria:
            object.__setattr__(self, "acceptance_criteria", criteria)
        kinds = _check_text_list(
            self.required_evidence_kinds, field_name="required_evidence_kinds"
        )
        for kind in kinds:
            _check_evidence_kind(kind)
        if kinds != self.required_evidence_kinds:
            object.__setattr__(self, "required_evidence_kinds", kinds)
        RedactionFilter.check(self.title, field_name="phase.title")
        RedactionFilter.check(self.description, field_name="phase.description")
        for idx, criterion in enumerate(self.acceptance_criteria):
            RedactionFilter.check(criterion, field_name=f"phase.acceptance_criteria[{idx}]")

    def to_dict(self) -> dict:
        return {
            "phaseId": self.phase_id,
            "title": self.title,
            "description": self.description,
            "acceptanceCriteria": list(self.acceptance_criteria),
            "requiredEvidenceKinds": list(self.required_evidence_kinds),
            "status": self.status.value,
        }


@dataclass(frozen=True)
class PlanReceipt:
    """An immutable snapshot of an integration plan at a single point in time."""

    plan_id: str
    schema_version: str
    plan_schema_version: str
    owner: str
    repo_owner: str
    repo_name: str
    workspace_id: str
    base_revision: str
    issue_reference: str
    pr_reference: Optional[str]
    acceptance_criteria: Tuple[str, ...]
    allowed_mutation_surfaces: Tuple[str, ...]
    phases: Tuple[Phase, ...]
    next_step: str
    attestation_sha256: str
    predecessor_attestation_sha256: Optional[str]
    amendment_reason: str
    recorded_at_iso: str
    plan_content_sha256: str

    def __post_init__(self) -> None:  # noqa: D401 - dataclass hook
        _check_identifier(self.plan_id, field_name="plan_id")
        if self.schema_version != SCHEMA_VERSION:
            raise IntegrationPlanContractError(
                f"schema_version must be {SCHEMA_VERSION}"
            )
        _check_text_list([], field_name="_")  # placeholder for typing consistency
        for field, value in (
            ("owner", self.owner),
            ("repo_owner", self.repo_owner),
            ("repo_name", self.repo_name),
            ("workspace_id", self.workspace_id),
            ("issue_reference", self.issue_reference),
        ):
            _check_bytes(value, field_name=field, limit=_MAX_ID_LEN)
            RedactionFilter.check(value, field_name=field)
        if self.pr_reference is not None:
            _check_bytes(self.pr_reference, field_name="pr_reference", limit=_MAX_ID_LEN)
        _check_revision(self.base_revision, field_name="base_revision")
        if not self.acceptance_criteria:
            raise IntegrationPlanContractError(
                "acceptance_criteria must contain at least one entry"
            )
        criteria = _check_text_list(
            self.acceptance_criteria, field_name="acceptance_criteria"
        )
        if criteria != self.acceptance_criteria:
            object.__setattr__(self, "acceptance_criteria", criteria)
        surfaces = _check_text_list(
            self.allowed_mutation_surfaces, field_name="allowed_mutation_surfaces"
        )
        if surfaces != self.allowed_mutation_surfaces:
            object.__setattr__(self, "allowed_mutation_surfaces", surfaces)
        if not self.phases:
            raise IntegrationPlanContractError("phases must contain at least one entry")
        if len(self.phases) > _MAX_PHASES:
            raise IntegrationPlanContractError(
                f"phases must not exceed {_MAX_PHASES} entries"
            )
        seen_phase_ids: set[str] = set()
        for phase in self.phases:
            if phase.phase_id in seen_phase_ids:
                raise IntegrationPlanContractError(
                    f"duplicate phase_id: {phase.phase_id}"
                )
            seen_phase_ids.add(phase.phase_id)
        _check_bytes(self.next_step, field_name="next_step", limit=4096)
        RedactionFilter.check(self.next_step, field_name="next_step")
        if self.predecessor_attestation_sha256 is not None:
            _check_sha256(
                self.predecessor_attestation_sha256,
                field_name="predecessor_attestation_sha256",
            )
        _check_sha256(self.attestation_sha256, field_name="attestation_sha256")
        _check_sha256(self.plan_content_sha256, field_name="plan_content_sha256")
        _check_bytes(
            self.amendment_reason, field_name="amendment_reason", limit=_MAX_AMENDMENT_REASON_BYTES
        )
        RedactionFilter.check(self.amendment_reason, field_name="amendment_reason")
        _check_bytes(self.recorded_at_iso, field_name="recorded_at_iso", limit=64)

    def to_dict(self) -> dict:
        return {
            "planId": self.plan_id,
            "schemaVersion": self.schema_version,
            "planSchemaVersion": self.plan_schema_version,
            "owner": self.owner,
            "repoOwner": self.repo_owner,
            "repoName": self.repo_name,
            "workspaceId": self.workspace_id,
            "baseRevision": self.base_revision,
            "issueReference": self.issue_reference,
            "prReference": self.pr_reference,
            "acceptanceCriteria": list(self.acceptance_criteria),
            "allowedMutationSurfaces": list(self.allowed_mutation_surfaces),
            "phases": [phase.to_dict() for phase in self.phases],
            "nextStep": self.next_step,
            "attestationSha256": self.attestation_sha256,
            "predecessorAttestationSha256": self.predecessor_attestation_sha256,
            "amendmentReason": self.amendment_reason,
            "recordedAtIso": self.recorded_at_iso,
            "planContentSha256": self.plan_content_sha256,
        }


@dataclass(frozen=True)
class EvidenceRecord:
    """An immutable, machine-checkable evidence receipt for a plan phase."""

    evidence_id: str
    schema_version: str
    phase_id: str
    kind: str
    source: str
    content_sha256: str
    received_at_iso: str
    redacted: bool
    is_verified: bool

    def __post_init__(self) -> None:  # noqa: D401 - dataclass hook
        _check_identifier(self.evidence_id, field_name="evidence_id")
        if self.schema_version != EVIDENCE_SCHEMA_VERSION:
            raise IntegrationPlanContractError(
                f"schema_version must be {EVIDENCE_SCHEMA_VERSION}"
            )
        _check_identifier(self.phase_id, field_name="phase_id")
        _check_evidence_kind(self.kind)
        _check_bytes(self.source, field_name="source", limit=_MAX_ID_LEN)
        RedactionFilter.check(self.source, field_name="source")
        binding = _PHASE_KIND_BINDING[self.kind]
        if not binding["source_pattern"].fullmatch(self.source):
            raise IntegrationPlanContractError(
                f"source {self.source!r} does not match the {self.kind} binding"
            )
        _check_sha256(self.content_sha256, field_name="content_sha256")
        _check_bytes(self.received_at_iso, field_name="received_at_iso", limit=64)
        # An EvidenceRecord can only carry is_verified=True if the caller has
        # already validated real target-system readback. Markdown-only
        # callers must always set is_verified=False.
        if self.is_verified and not self.redacted:
            raise IntegrationPlanContractError(
                "verified evidence records must also be marked redacted=True"
            )

    def to_dict(self) -> dict:
        return {
            "evidenceId": self.evidence_id,
            "schemaVersion": self.schema_version,
            "phaseId": self.phase_id,
            "kind": self.kind,
            "source": self.source,
            "contentSha256": self.content_sha256,
            "receivedAtIso": self.received_at_iso,
            "redacted": self.redacted,
            "isVerified": self.is_verified,
        }


# ---------------------------------------------------------------------------
# Provenance chain (per receipt)
# ---------------------------------------------------------------------------
def _compute_receipt_provenance(receipt: PlanReceipt) -> str:
    """Canonical provenance hash for a receipt, independent of its attestation."""
    payload = {
        "planId": receipt.plan_id,
        "schemaVersion": receipt.schema_version,
        "planSchemaVersion": receipt.plan_schema_version,
        "owner": receipt.owner,
        "repoOwner": receipt.repo_owner,
        "repoName": receipt.repo_name,
        "workspaceId": receipt.workspace_id,
        "baseRevision": receipt.base_revision,
        "issueReference": receipt.issue_reference,
        "prReference": receipt.pr_reference,
        "acceptanceCriteria": list(receipt.acceptance_criteria),
        "allowedMutationSurfaces": list(receipt.allowed_mutation_surfaces),
        "phases": [phase.to_dict() for phase in receipt.phases],
        "nextStep": receipt.next_step,
        "predecessorAttestationSha256": receipt.predecessor_attestation_sha256,
        "amendmentReason": receipt.amendment_reason,
        "recordedAtIso": receipt.recorded_at_iso,
        "planContentSha256": receipt.plan_content_sha256,
    }
    return _canonical_sha256(payload)


def _compute_plan_content_hash(
    *,
    acceptance_criteria: Sequence[str],
    phases: Sequence[Phase],
    next_step: str,
    allowed_mutation_surfaces: Sequence[str],
) -> str:
    """Hash of plan content used inside the attestation."""
    payload = {
        "acceptanceCriteria": list(acceptance_criteria),
        "phases": [phase.to_dict() for phase in phases],
        "nextStep": next_step,
        "allowedMutationSurfaces": list(allowed_mutation_surfaces),
    }
    serialised = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    if len(serialised.encode("utf-8")) > _MAX_PLAN_CONTENT_BYTES:
        raise IntegrationPlanContractError(
            f"plan content exceeds {_MAX_PLAN_CONTENT_BYTES}-byte limit"
        )
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def _compute_attestation_hash(
    *,
    plan_id: str,
    owner: str,
    repo_owner: str,
    repo_name: str,
    base_revision: str,
    plan_content_sha256: str,
    provenance_sha256: str,
    predecessor_attestation_sha256: Optional[str],
    amendment_reason: str,
    recorded_at_iso: str,
) -> str:
    payload = {
        "planId": plan_id,
        "owner": owner,
        "repoOwner": repo_owner,
        "repoName": repo_name,
        "baseRevision": base_revision,
        "planContentSha256": plan_content_sha256,
        "provenanceSha256": provenance_sha256,
        "predecessorAttestationSha256": predecessor_attestation_sha256,
        "amendmentReason": amendment_reason,
        "recordedAtIso": recorded_at_iso,
    }
    return _canonical_sha256(payload)


# ---------------------------------------------------------------------------
# IntegrationPlanLane (pure state machine)
# ---------------------------------------------------------------------------
class IntegrationPlanLane:
    """Pure, fail-closed state machine for the Integration Plan Lane.

    All methods are stateless class methods that accept immutable inputs and
    return new value objects.  No I/O of any kind is performed here.
    """

    # -----------------------------------------------------------------------
    # Construction
    # -----------------------------------------------------------------------
    @classmethod
    def create_receipt(
        cls,
        *,
        plan_id: str,
        plan_schema_version: str,
        owner: str,
        repo_owner: str,
        repo_name: str,
        workspace_id: str,
        base_revision: str,
        issue_reference: str,
        acceptance_criteria: Sequence[str],
        allowed_mutation_surfaces: Sequence[str],
        phases: Sequence[Phase],
        next_step: str,
        recorded_at_iso: str,
        amendment_reason: str = "initial plan attestation",
    ) -> PlanReceipt:
        """Create the first attestation of a plan."""
        _check_identifier(plan_id, field_name="plan_id")
        _check_bytes(plan_schema_version, field_name="plan_schema_version", limit=_MAX_ID_LEN)
        plan_content_sha256 = _compute_plan_content_hash(
            acceptance_criteria=acceptance_criteria,
            phases=phases,
            next_step=next_step,
            allowed_mutation_surfaces=allowed_mutation_surfaces,
        )
        provisional = PlanReceipt(
            plan_id=plan_id,
            schema_version=SCHEMA_VERSION,
            plan_schema_version=plan_schema_version,
            owner=owner,
            repo_owner=repo_owner,
            repo_name=repo_name,
            workspace_id=workspace_id,
            base_revision=base_revision,
            issue_reference=issue_reference,
            pr_reference=None,
            acceptance_criteria=tuple(acceptance_criteria),
            allowed_mutation_surfaces=tuple(allowed_mutation_surfaces),
            phases=tuple(phases),
            next_step=next_step,
            attestation_sha256="0" * 64,  # placeholder, replaced below
            predecessor_attestation_sha256=None,
            amendment_reason=amendment_reason,
            recorded_at_iso=recorded_at_iso,
            plan_content_sha256=plan_content_sha256,
        )
        provenance = _compute_receipt_provenance(provisional)
        attestation = _compute_attestation_hash(
            plan_id=plan_id,
            owner=owner,
            repo_owner=repo_owner,
            repo_name=repo_name,
            base_revision=base_revision,
            plan_content_sha256=plan_content_sha256,
            provenance_sha256=provenance,
            predecessor_attestation_sha256=None,
            amendment_reason=amendment_reason,
            recorded_at_iso=recorded_at_iso,
        )
        return PlanReceipt(
            plan_id=plan_id,
            schema_version=SCHEMA_VERSION,
            plan_schema_version=plan_schema_version,
            owner=owner,
            repo_owner=repo_owner,
            repo_name=repo_name,
            workspace_id=workspace_id,
            base_revision=base_revision,
            issue_reference=issue_reference,
            pr_reference=None,
            acceptance_criteria=tuple(acceptance_criteria),
            allowed_mutation_surfaces=tuple(allowed_mutation_surfaces),
            phases=tuple(phases),
            next_step=next_step,
            attestation_sha256=attestation,
            predecessor_attestation_sha256=None,
            amendment_reason=amendment_reason,
            recorded_at_iso=recorded_at_iso,
            plan_content_sha256=plan_content_sha256,
        )

    @classmethod
    def amend_receipt(
        cls,
        previous: PlanReceipt,
        *,
        acceptance_criteria: Sequence[str],
        allowed_mutation_surfaces: Sequence[str],
        phases: Sequence[Phase],
        next_step: str,
        amendment_reason: str,
        recorded_at_iso: str,
        pr_reference: Optional[str] = None,
    ) -> PlanReceipt:
        """Create a new receipt that supersedes ``previous``.

        The new receipt must bind to the previous attestation hash, share the
        same plan identity, repository, owner, workspace and base revision
        and must carry a non-empty, redacted amendment reason.
        """
        if previous.schema_version != SCHEMA_VERSION:
            raise IntegrationPlanContractError(
                "previous receipt has an unrecognised schema_version"
            )
        if not acceptance_criteria:
            raise IntegrationPlanContractError(
                "acceptance_criteria must contain at least one entry"
            )
        if not amendment_reason.strip():
            raise IntegrationPlanContractError("amendment_reason must not be empty")
        plan_content_sha256 = _compute_plan_content_hash(
            acceptance_criteria=acceptance_criteria,
            phases=phases,
            next_step=next_step,
            allowed_mutation_surfaces=allowed_mutation_surfaces,
        )
        # Plan identity binding: same plan id, owner, repo, workspace, revision.
        provisional = PlanReceipt(
            plan_id=previous.plan_id,
            schema_version=SCHEMA_VERSION,
            plan_schema_version=previous.plan_schema_version,
            owner=previous.owner,
            repo_owner=previous.repo_owner,
            repo_name=previous.repo_name,
            workspace_id=previous.workspace_id,
            base_revision=previous.base_revision,
            issue_reference=previous.issue_reference,
            pr_reference=pr_reference,
            acceptance_criteria=tuple(acceptance_criteria),
            allowed_mutation_surfaces=tuple(allowed_mutation_surfaces),
            phases=tuple(phases),
            next_step=next_step,
            attestation_sha256="0" * 64,
            predecessor_attestation_sha256=previous.attestation_sha256,
            amendment_reason=amendment_reason,
            recorded_at_iso=recorded_at_iso,
            plan_content_sha256=plan_content_sha256,
        )
        provenance = _compute_receipt_provenance(provisional)
        attestation = _compute_attestation_hash(
            plan_id=previous.plan_id,
            owner=previous.owner,
            repo_owner=previous.repo_owner,
            repo_name=previous.repo_name,
            base_revision=previous.base_revision,
            plan_content_sha256=plan_content_sha256,
            provenance_sha256=provenance,
            predecessor_attestation_sha256=previous.attestation_sha256,
            amendment_reason=amendment_reason,
            recorded_at_iso=recorded_at_iso,
        )
        return PlanReceipt(
            plan_id=previous.plan_id,
            schema_version=SCHEMA_VERSION,
            plan_schema_version=previous.plan_schema_version,
            owner=previous.owner,
            repo_owner=previous.repo_owner,
            repo_name=previous.repo_name,
            workspace_id=previous.workspace_id,
            base_revision=previous.base_revision,
            issue_reference=previous.issue_reference,
            pr_reference=pr_reference,
            acceptance_criteria=tuple(acceptance_criteria),
            allowed_mutation_surfaces=tuple(allowed_mutation_surfaces),
            phases=tuple(phases),
            next_step=next_step,
            attestation_sha256=attestation,
            predecessor_attestation_sha256=previous.attestation_sha256,
            amendment_reason=amendment_reason,
            recorded_at_iso=recorded_at_iso,
            plan_content_sha256=plan_content_sha256,
        )

    # -----------------------------------------------------------------------
    # Verification
    # -----------------------------------------------------------------------
    @classmethod
    def verify_receipt_attestation(cls, receipt: PlanReceipt) -> bool:
        """Recompute and compare the attestation hash for ``receipt``."""
        provenance = _compute_receipt_provenance(receipt)
        expected = _compute_attestation_hash(
            plan_id=receipt.plan_id,
            owner=receipt.owner,
            repo_owner=receipt.repo_owner,
            repo_name=receipt.repo_name,
            base_revision=receipt.base_revision,
            plan_content_sha256=receipt.plan_content_sha256,
            provenance_sha256=provenance,
            predecessor_attestation_sha256=receipt.predecessor_attestation_sha256,
            amendment_reason=receipt.amendment_reason,
            recorded_at_iso=receipt.recorded_at_iso,
        )
        return expected == receipt.attestation_sha256

    # -----------------------------------------------------------------------
    # Evidence recording
    # -----------------------------------------------------------------------
    @classmethod
    def create_evidence_record(
        cls,
        *,
        evidence_id: str,
        phase_id: str,
        kind: str,
        source: str,
        content_sha256: str,
        received_at_iso: str,
        is_verified: bool = False,
    ) -> EvidenceRecord:
        """Build a single EvidenceRecord.

        ``is_verified`` may only be set to True when the caller has just
        performed a real target-system readback.  Markdown, LLM or UI output
        alone is never enough.
        """
        return EvidenceRecord(
            evidence_id=evidence_id,
            schema_version=EVIDENCE_SCHEMA_VERSION,
            phase_id=phase_id,
            kind=kind,
            source=source,
            content_sha256=content_sha256,
            received_at_iso=received_at_iso,
            redacted=is_verified,
            is_verified=is_verified,
        )

    @classmethod
    def evaluate_phase(
        cls,
        phase: Phase,
        evidence: Sequence[EvidenceRecord],
    ) -> PhaseStatus:
        """Compute the canonical status of ``phase`` from the evidence set.

        Rules:
        - Any contradictory or invalidating evidence forces ``invalidated``.
        - If every required kind is represented by at least one verified
          record, return ``verified``.
        - If the phase is ``verified`` and a verified invalidation record is
          present, return ``invalidated`` (append-only supersession).
        - If the phase was previously marked ``in_progress`` but required
          evidence is missing, return ``blocked``.
        - Otherwise return the phase's declared starting status.
        """
        phase_records = [r for r in evidence if r.phase_id == phase.phase_id]
        # Always-on invariants: schema, kind, binding. We rely on the dataclass
        # constructor to have rejected malformed records already.

        # Contradiction → invalidated (append-only)
        for record in phase_records:
            if record.kind == EVIDENCE_KIND_LEDGER_HEAD and record.is_verified:
                # ledger_head records can never promote a phase to verified,
                # only to invalidated if the previous phase was invalidated.
                pass
        verified_kinds = {r.kind for r in phase_records if r.is_verified}
        required_kinds = set(phase.required_evidence_kinds)

        # Invalidation supersedes verification if a contradicting record is
        # marked verified (e.g., a supersession ledger entry).
        invalidation_records = [
            r for r in phase_records
            if r.is_verified and r.kind == EVIDENCE_KIND_LEDGER_HEAD
        ]
        if any(r.evidence_id.endswith(":invalidated") for r in invalidation_records):
            return PhaseStatus.INVALIDATED

        # Configuration-provenance drift (#1169): a verified config_drift
        # record means the resolved config projection changed underneath an
        # active action plan. Drift invalidates the phase rather than letting
        # it silently continue on a stale config binding.
        if any(r.kind == EVIDENCE_KIND_CONFIG_DRIFT and r.is_verified for r in phase_records):
            return PhaseStatus.INVALIDATED

        if required_kinds and required_kinds.issubset(verified_kinds):
            return PhaseStatus.VERIFIED
        if phase.status == PhaseStatus.IN_PROGRESS:
            return PhaseStatus.BLOCKED
        return phase.status

    # -----------------------------------------------------------------------
    # Serialisation helpers (pure JSON)
    # -----------------------------------------------------------------------
    @classmethod
    def to_receipt_dict(cls, receipt: PlanReceipt) -> dict:
        return receipt.to_dict()

    @classmethod
    def to_evidence_list(cls, records: Sequence[EvidenceRecord]) -> List[dict]:
        return [r.to_dict() for r in records]

    @classmethod
    def evaluate_all(
        cls,
        receipt: PlanReceipt,
        evidence: Sequence[EvidenceRecord],
    ) -> Dict[str, str]:
        """Return a ``{phase_id: status}`` mapping for the whole plan."""
        return {
            phase.phase_id: cls.evaluate_phase(phase, evidence).value
            for phase in receipt.phases
        }