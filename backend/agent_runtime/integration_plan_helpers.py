"""Bounded helpers for the revision-bound Integration Plan Lane.

This module owns the *non-stateful* helpers that surround the lane:

- ``render_task_plan`` / ``render_findings`` / ``render_progress``:
  canonical Markdown templates for the three human-readable files in
  ``.planning/<integration-id>/``. The templates are intentionally
  narrow: they only embed data that has already been validated through
  the lane and the redaction filter.
- ``render_context_injection``: builds a size-bounded, secret-redacted
  context block that an agent may inject before a mutation, before a
  compaction or before resuming work. Markdown, LLM and UI status are
  never promoted to "verified" inside this block.
- ``evaluate_gated_completion``: implements the optional fail-safe
  Completion Gate (Issue #1112, \u00a78) with a block ceiling, a
  progress-evidence requirement and a recursion guard.
- ``snapshot_plan_lane_surfaces``: writes an architecture snapshot of
  every existing plan / continuity / memory / evidence surface that the
  lane depends on or extends. Drift is reported fail-closed.
- ``resume_session``: pre-resume readback that checks Plan, Ledger,
  Git-Diff, Workspace- and Remote-Revision before any state mutation.

The module is pure: no filesystem, network, database, clock or random.
All filesystem side effects live in ``integration_plan_store``.

\u26a0\ufe0f  Plan, progress, LLM or UI text alone can never produce a
verified or completion status. Every status here is a projection; the
canonical truth lives in the running repository, CI, deployment and
runtime.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, Final, List, Mapping, Optional, Sequence, Tuple

from .integration_plan_lane import (
    EVIDENCE_KIND_CI_WORKFLOW,
    EVIDENCE_KIND_REPO_REVISION,
    EvidenceRecord,
    IntegrationPlanContractError,
    IntegrationPlanLane,
    PhaseStatus,
    PlanReceipt,
    RedactionFilter,
    SCHEMA_VERSION,
)


# Re-export so callers only need to import this module.
__all__ = [
    "render_task_plan",
    "render_findings",
    "render_progress",
    "render_context_injection",
    "evaluate_gated_completion",
    "snapshot_plan_lane_surfaces",
    "resume_session",
    "ResumeReport",
    "GatedCompletionReport",
    "ArchitectureSnapshot",
    "DriftFinding",
]


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------
_MAX_MD_BYTES: Final[int] = 16_384
_MAX_CONTEXT_BYTES: Final[int] = 8_192
_MAX_RESUME_REPORT_BYTES: Final[int] = 4_096
_MAX_SNAPSHOT_BYTES: Final[int] = 32_768
_MAX_GATE_LOOP_GUARD: Final[int] = 32
_MAX_LEDGER_HEAD_HOPS: Final[int] = 64

_FINDING_SECTIONS: Final[Tuple[str, ...]] = (
    "untrusted_external",
    "repository_observed",
    "runtime_observed",
    "verified",
    "invalidated",
)

_PHASE_STATUS_LABELS: Final[Mapping[PhaseStatus, str]] = {
    PhaseStatus.PENDING: "pending",
    PhaseStatus.IN_PROGRESS: "in_progress",
    PhaseStatus.BLOCKED: "blocked",
    PhaseStatus.VERIFIED: "verified",
    PhaseStatus.INVALIDATED: "invalidated",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _bounded(value: str, *, field_name: str, limit: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) > limit:
        raise IntegrationPlanContractError(
            f"{field_name} exceeds {limit}-byte limit (got {len(encoded)})"
        )
    return value


# ---------------------------------------------------------------------------
# Canonical Markdown templates
# ---------------------------------------------------------------------------
def render_task_plan(
    receipt: PlanReceipt,
    status_map: Mapping[str, str],
) -> str:
    """Render the canonical ``task_plan.md`` body for ``receipt``.

    The body only carries fields the lane has already validated. The
    header declares the schema version, attestation hash, predecessor
    binding and base revision so any agent reading the file can confirm
    it is the same plan the lane last attested.
    """
    if receipt.schema_version != SCHEMA_VERSION:
        raise IntegrationPlanContractError(
            f"receipt schema_version must be {SCHEMA_VERSION}"
        )
    lines: List[str] = [
        "# Integration Task Plan",
        "",
        f"- plan_id: `{receipt.plan_id}`",
        f"- schema_version: `{receipt.schema_version}`",
        f"- plan_schema_version: `{receipt.plan_schema_version}`",
        f"- owner: `{receipt.owner}`",
        f"- repo: `{receipt.repo_owner}/{receipt.repo_name}`",
        f"- workspace_id: `{receipt.workspace_id}`",
        f"- base_revision: `{receipt.base_revision}`",
        f"- issue_reference: `{receipt.issue_reference}`",
        f"- pr_reference: `{receipt.pr_reference or ''}`",
        f"- attestation_sha256: `{receipt.attestation_sha256}`",
        f"- predecessor_attestation_sha256: `{receipt.predecessor_attestation_sha256 or ''}`",
        f"- amendment_reason: `{receipt.amendment_reason}`",
        f"- recorded_at_iso: `{receipt.recorded_at_iso}`",
        "",
        "## Acceptance Criteria",
        "",
    ]
    for criterion in receipt.acceptance_criteria:
        lines.append(f"- {criterion}")
    lines.extend(["", "## Allowed Mutation Surfaces", ""])
    for surface in receipt.allowed_mutation_surfaces:
        lines.append(f"- `{surface}`")
    lines.extend(["", "## Phases", ""])
    for phase in receipt.phases:
        lines.append(f"### {phase.phase_id} \u2014 {phase.title}")
        lines.append("")
        lines.append(f"- status: `{status_map.get(phase.phase_id, phase.status.value)}`")
        lines.append(f"- description: {phase.description}")
        lines.append("- acceptance_criteria:")
        for criterion in phase.acceptance_criteria:
            lines.append(f"  - {criterion}")
        lines.append("- required_evidence_kinds:")
        for kind in phase.required_evidence_kinds:
            lines.append(f"  - `{kind}`")
        lines.append("")
    lines.extend(
        [
            "## Next Step",
            "",
            receipt.next_step,
            "",
            "## Truth Notice",
            "",
            "Plan status is a projection. Repository, CI, artifact, image, "
            "deployment, database and runtime truth remain canonical. "
            "Marking `Status: complete` in this file alone does not close "
            "the integration.",
            "",
        ]
    )
    body = "\n".join(lines)
    return _bounded(body, field_name="task_plan.md", limit=_MAX_MD_BYTES)


def render_findings(
    findings: Mapping[str, Sequence[str]],
) -> str:
    """Render the canonical ``findings.md`` body.

    ``findings`` must provide exactly the five canonical sections. Empty
    lists are allowed and rendered as "(empty)" so the structure is
    visible to any reader.
    """
    unknown = sorted(set(findings) - set(_FINDING_SECTIONS))
    if unknown:
        raise IntegrationPlanContractError(
            f"unknown findings sections: {', '.join(unknown)}"
        )
    lines: List[str] = [
        "# Integration Findings",
        "",
        "Each finding carries a single canonical classification. Web, LLM, "
        "Issue, PR-comment and external documentation content stays "
        "`untrusted_external` until it is matched against a canonical "
        "source. External instructions never become plan phases, tool "
        "calls or owner approvals.",
        "",
    ]
    for section in _FINDING_SECTIONS:
        entries = list(findings.get(section, ()))
        for entry in entries:
            RedactionFilter.check(entry, field_name=f"findings.{section}")
        lines.append(f"## {section}")
        lines.append("")
        if not entries:
            lines.append("(empty)")
        else:
            for entry in entries:
                lines.append(f"- {entry}")
        lines.append("")
    body = "\n".join(lines)
    return _bounded(body, field_name="findings.md", limit=_MAX_MD_BYTES)


def render_progress(events: Sequence[Mapping[str, str]]) -> str:
    """Render the canonical ``progress.md`` body.

    Each event must already carry ``ts``, ``kind`` and ``text``. The
    renderer rejects secret-shaped content and enforces a bounded total
    payload size.
    """
    if not events:
        body = (
            "# Integration Progress\n\n"
            "No events recorded yet. The lane does not infer completion from\n"
            "an empty progress log.\n"
        )
        return _bounded(body, field_name="progress.md", limit=_MAX_MD_BYTES)
    lines: List[str] = ["# Integration Progress", ""]
    for event in events:
        ts = str(event.get("ts", ""))
        kind = str(event.get("kind", ""))
        text = str(event.get("text", ""))
        RedactionFilter.check(text, field_name="progress.text")
        lines.append(f"- {ts} [{kind}] {text}")
    body = "\n".join(lines) + "\n"
    return _bounded(body, field_name="progress.md", limit=_MAX_MD_BYTES)


# ---------------------------------------------------------------------------
# Context injection
# ---------------------------------------------------------------------------
def render_context_injection(
    *,
    receipt: PlanReceipt,
    status_map: Mapping[str, str],
    progress_excerpt: Sequence[Mapping[str, str]],
    additional_lines: Sequence[str] = (),
) -> str:
    """Build a size-bounded, redacted context block for an agent.

    The block never carries secret-shaped material, never repeats
    full CI/runtime logs and never promotes a phase to ``verified`` by
    itself. Markdown status strings are explicitly labelled as
    projections.
    """
    if receipt.schema_version != SCHEMA_VERSION:
        raise IntegrationPlanContractError(
            f"receipt schema_version must be {SCHEMA_VERSION}"
        )
    lines: List[str] = [
        "# Integration Plan Projection (NOT runtime truth)",
        "",
        f"- plan_id: `{receipt.plan_id}`",
        f"- base_revision: `{receipt.base_revision}`",
        f"- workspace_id: `{receipt.workspace_id}`",
        f"- attestation_sha256: `{receipt.attestation_sha256}`",
        f"- next_step: {receipt.next_step}",
        "",
        "## Phases (projection only)",
        "",
    ]
    for phase in receipt.phases:
        status = status_map.get(phase.phase_id, phase.status.value)
        lines.append(
            f"- `{phase.phase_id}` -> `{status}` (projection; not proof of "
            "runtime, CI, deployment or database success)"
        )
    lines.extend(["", "## Recent progress (bounded excerpt)", ""])
    if not progress_excerpt:
        lines.append("(no progress events recorded)")
    else:
        for event in progress_excerpt[-8:]:
            ts = str(event.get("ts", ""))
            kind = str(event.get("kind", ""))
            text = str(event.get("text", ""))
            RedactionFilter.check(text, field_name="context.progress.text")
            lines.append(f"- {ts} [{kind}] {text}")
    if additional_lines:
        lines.extend(["", "## Caller-supplied hints (untrusted)", ""])
        for hint in additional_lines:
            RedactionFilter.check(hint, field_name="context.hint")
            lines.append(f"- {hint}")
    lines.extend(
        [
            "",
            "## Truth notice",
            "",
            "The block above is a projection. It must never be used to "
            "claim repository, CI, artifact, image, deployment, database "
            "or runtime success. Phase `verified` requires real "
            "machine-checkable evidence in `evidence-index.json`.",
            "",
        ]
    )
    body = "\n".join(lines)
    return _bounded(body, field_name="context_injection", limit=_MAX_CONTEXT_BYTES)


# ---------------------------------------------------------------------------
# Gated completion evaluator
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class GatedCompletionReport:
    schema_version: str
    plan_id: str
    mode: str
    in_progress_phases: Tuple[str, ...]
    blocked_phases: Tuple[str, ...]
    verified_phases: Tuple[str, ...]
    invalidated_phases: Tuple[str, ...]
    missing_required_kinds: Mapping[str, Tuple[str, ...]]
    loop_guard_hits: int
    block_ceiling_hits: int
    progress_evidence_present: bool
    last_decision_sha256: Optional[str]
    eligible_to_release: bool
    decision_reason: str
    mutationPerformed: bool
    runtimeVerified: bool
    secretValuesReturned: bool

    def to_dict(self) -> dict:
        return {
            "schemaVersion": self.schema_version,
            "planId": self.plan_id,
            "mode": self.mode,
            "inProgressPhases": list(self.in_progress_phases),
            "blockedPhases": list(self.blocked_phases),
            "verifiedPhases": list(self.verified_phases),
            "invalidatedPhases": list(self.invalidated_phases),
            "missingRequiredKinds": {
                phase_id: list(kinds)
                for phase_id, kinds in self.missing_required_kinds.items()
            },
            "loopGuardHits": self.loop_guard_hits,
            "blockCeilingHits": self.block_ceiling_hits,
            "progressEvidencePresent": self.progress_evidence_present,
            "lastDecisionSha256": self.last_decision_sha256,
            "eligibleToRelease": self.eligible_to_release,
            "decisionReason": self.decision_reason,
            "mutationPerformed": False,
            "runtimeVerified": False,
            "secretValuesReturned": False,
        }


_GATED_SCHEMA_VERSION: Final[str] = "sovereign.integration-plan-gated-completion.v1"


def evaluate_gated_completion(
    receipt: PlanReceipt,
    evidence: Sequence[EvidenceRecord],
    ledger_actions: Sequence[Mapping[str, Any]],
    *,
    mode: str,
    previous_decision: Optional[Mapping[str, Any]] = None,
    block_ceiling: int = 5,
    loop_guard_hits: int = 0,
) -> GatedCompletionReport:
    """Compute a gated completion decision for ``receipt``.

    The decision is fail-closed unless *every* required condition holds.
    Markdown status alone is never enough.
    """
    if mode not in {"open", "gated", "closed"}:
        raise IntegrationPlanContractError(
            f"mode must be open|gated|closed (got {mode!r})"
        )
    if mode != "gated":
        # Only the gated mode ever blocks. ``open`` and ``closed`` short-circuit.
        if mode == "open":
            eligible = False
            reason = "mode is open; lane does not claim completion"
        else:
            eligible = True
            reason = "mode is closed; lane is terminal"
        return GatedCompletionReport(
            schema_version=_GATED_SCHEMA_VERSION,
            plan_id=receipt.plan_id,
            mode=mode,
            in_progress_phases=(),
            blocked_phases=(),
            verified_phases=(),
            invalidated_phases=(),
            missing_required_kinds={},
            loop_guard_hits=loop_guard_hits,
            block_ceiling_hits=0,
            progress_evidence_present=False,
            last_decision_sha256=None,
            eligible_to_release=eligible,
            decision_reason=reason,
            mutationPerformed=False,
            runtimeVerified=False,
            secretValuesReturned=False,
        )
    if loop_guard_hits >= _MAX_GATE_LOOP_GUARD:
        return GatedCompletionReport(
            schema_version=_GATED_SCHEMA_VERSION,
            plan_id=receipt.plan_id,
            mode=mode,
            in_progress_phases=(),
            blocked_phases=(),
            verified_phases=(),
            invalidated_phases=(),
            missing_required_kinds={},
            loop_guard_hits=loop_guard_hits,
            block_ceiling_hits=0,
            progress_evidence_present=False,
            last_decision_sha256=None,
            eligible_to_release=False,
            decision_reason="loop guard tripped; refusing to re-decide",
            mutationPerformed=False,
            runtimeVerified=False,
            secretValuesReturned=False,
        )
    if block_ceiling <= 0:
        raise IntegrationPlanContractError(
            "block_ceiling must be a positive integer"
        )

    status_map = {
        phase.phase_id: IntegrationPlanLane.evaluate_phase(phase, evidence).value
        for phase in receipt.phases
    }
    missing_kinds: Dict[str, Tuple[str, ...]] = {}
    for phase in receipt.phases:
        status = PhaseStatus(status_map[phase.phase_id])
        # Only IN_PROGRESS and BLOCKED phases contribute missing evidence;
        # VERIFIED phases already have all evidence, INVALIDATED phases are
        # terminal and PENDING phases have not started.
        if status not in (PhaseStatus.IN_PROGRESS, PhaseStatus.BLOCKED):
            continue
        verified_kinds = {
            r.kind for r in evidence if r.phase_id == phase.phase_id and r.is_verified
        }
        absent = tuple(k for k in phase.required_evidence_kinds if k not in verified_kinds)
        if absent:
            missing_kinds[phase.phase_id] = absent
    in_progress = tuple(
        phase.phase_id for phase in receipt.phases
        if status_map[phase.phase_id] == PhaseStatus.IN_PROGRESS.value
    )
    blocked = tuple(
        phase.phase_id for phase in receipt.phases
        if status_map[phase.phase_id] == PhaseStatus.BLOCKED.value
    )
    verified = tuple(
        phase.phase_id for phase in receipt.phases
        if status_map[phase.phase_id] == PhaseStatus.VERIFIED.value
    )
    invalidated = tuple(
        phase.phase_id for phase in receipt.phases
        if status_map[phase.phase_id] == PhaseStatus.INVALIDATED.value
    )

    progress_present = bool(ledger_actions)
    if previous_decision is not None:
        previous_sha = _text_sha256(json.dumps(previous_decision, sort_keys=True))
    else:
        previous_sha = None

    eligible = (
        not missing_kinds
        and not in_progress
        and not blocked
        and progress_present
        and loop_guard_hits == 0
    )
    if not eligible:
        reason = "missing evidence or progress for in-progress phases"
    else:
        reason = "all required evidence + progress present"

    return GatedCompletionReport(
        schema_version=_GATED_SCHEMA_VERSION,
        plan_id=receipt.plan_id,
        mode=mode,
        in_progress_phases=in_progress,
        blocked_phases=blocked,
        verified_phases=verified,
        invalidated_phases=invalidated,
        missing_required_kinds=missing_kinds,
        loop_guard_hits=loop_guard_hits,
        block_ceiling_hits=block_ceiling,
        progress_evidence_present=progress_present,
        last_decision_sha256=previous_sha,
        eligible_to_release=eligible,
        decision_reason=reason,
        mutationPerformed=False,
        runtimeVerified=False,
        secretValuesReturned=False,
    )


# ---------------------------------------------------------------------------
# Architecture snapshot
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DriftFinding:
    surface: str
    severity: str
    detail: str

    def to_dict(self) -> dict:
        return {"surface": self.surface, "severity": self.severity, "detail": self.detail}


@dataclass(frozen=True)
class ArchitectureSnapshot:
    schema_version: str
    repository_root_label: str
    surfaces: Tuple[Mapping[str, str], ...]
    drift: Tuple[DriftFinding, ...]
    snapshot_sha256: str
    mutationPerformed: bool
    runtimeVerified: bool
    secretValuesReturned: bool

    def to_dict(self) -> dict:
        return {
            "schemaVersion": self.schema_version,
            "repositoryRootLabel": self.repository_root_label,
            "surfaces": [dict(s) for s in self.surfaces],
            "drift": [f.to_dict() for f in self.drift],
            "snapshotSha256": self.snapshot_sha256,
            "mutationPerformed": False,
            "runtimeVerified": False,
            "secretValuesReturned": False,
        }


_SNAPSHOT_SCHEMA_VERSION: Final[str] = "sovereign.integration-plan-architecture-snapshot.v1"

_REQUIRED_SURFACES: Final[Tuple[Tuple[str, str], ...]] = (
    ("canonical-continuity-context", "docs/sovereign-continuity/CONTEXT.md"),
    ("canonical-continuity-ledger", "docs/sovereign-continuity/LEDGER.jsonl"),
    ("continuity-policy", "tools/sovereign-chatgpt-mcp/config/sovereign-continuity-policy.json"),
    ("bug-evidence-lane", "backend/agent_runtime/bug_evidence_lane.py"),
    ("bug-evidence-tests", "backend/tests/test_bug_evidence_lane.py"),
    ("plan-lane-canonical", "backend/agent_runtime/integration_plan_lane.py"),
    ("plan-lane-store", "backend/agent_runtime/integration_plan_store.py"),
    ("plan-lane-helpers", "backend/agent_runtime/integration_plan_helpers.py"),
    ("plan-lane-tests", "backend/tests/test_integration_plan_lane.py"),
    ("plan-store-tests", "backend/tests/test_integration_plan_store.py"),
)


def snapshot_plan_lane_surfaces(
    repo_root_label: str,
    exists: Mapping[str, bool],
    *,
    expected_surface_labels: Sequence[str] = (),
) -> ArchitectureSnapshot:
    """Build an architecture snapshot without touching the filesystem.

    ``exists`` must be a mapping from the canonical ``surface_label`` to
    a boolean indicating whether the file exists in the bound
    workspace. Drift is reported fail-closed.
    """
    surfaces: List[Mapping[str, str]] = []
    drift: List[DriftFinding] = []
    for label, relative in _REQUIRED_SURFACES:
        present = exists.get(label, False)
        sha_label = "sha256-not-probed"
        surfaces.append(
            {
                "label": label,
                "relativePath": relative,
                "present": "yes" if present else "no",
                "sha256": sha_label,
            }
        )
        if not present:
            drift.append(
                DriftFinding(
                    surface=label,
                    severity="P1",
                    detail=f"required surface {relative} is missing",
                )
            )
    for expected in expected_surface_labels:
        if expected not in exists:
            drift.append(
                DriftFinding(
                    surface=expected,
                    severity="P2",
                    detail=f"expected surface {expected} was not provided",
                )
            )
    payload = {
        "schemaVersion": _SNAPSHOT_SCHEMA_VERSION,
        "repositoryRootLabel": repo_root_label,
        "surfaces": [dict(s) for s in surfaces],
        "drift": [f.to_dict() for f in drift],
    }
    snapshot_sha = _text_sha256(json.dumps(payload, sort_keys=True))
    body = json.dumps(payload, indent=2, sort_keys=True)
    if len(body.encode("utf-8")) > _MAX_SNAPSHOT_BYTES:
        raise IntegrationPlanContractError(
            f"snapshot payload exceeds {_MAX_SNAPSHOT_BYTES}-byte limit"
        )
    return ArchitectureSnapshot(
        schema_version=_SNAPSHOT_SCHEMA_VERSION,
        repository_root_label=repo_root_label,
        surfaces=tuple(surfaces),
        drift=tuple(drift),
        snapshot_sha256=snapshot_sha,
        mutationPerformed=False,
        runtimeVerified=False,
        secretValuesReturned=False,
    )


# ---------------------------------------------------------------------------
# Resume readback
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ResumeReport:
    schema_version: str
    plan_id: str
    workspace_root_label: str
    plan_present: bool
    ledger_present: bool
    git_diff_lines: int
    workspace_revision: Optional[str]
    remote_revision: Optional[str]
    revision_match: bool
    active_revision_present: bool
    next_step: Optional[str]
    status_map: Mapping[str, str]
    findings: Tuple[DriftFinding, ...]
    resume_decision: str
    mutationPerformed: bool
    runtimeVerified: bool
    secretValuesReturned: bool

    def to_dict(self) -> dict:
        return {
            "schemaVersion": self.schema_version,
            "planId": self.plan_id,
            "workspaceRootLabel": self.workspace_root_label,
            "planPresent": self.plan_present,
            "ledgerPresent": self.ledger_present,
            "gitDiffLines": self.git_diff_lines,
            "workspaceRevision": self.workspace_revision,
            "remoteRevision": self.remote_revision,
            "revisionMatch": self.revision_match,
            "activeRevisionPresent": self.active_revision_present,
            "nextStep": self.next_step,
            "statusMap": dict(self.status_map),
            "findings": [f.to_dict() for f in self.findings],
            "resumeDecision": self.resume_decision,
            "mutationPerformed": False,
            "runtimeVerified": False,
            "secretValuesReturned": False,
        }


_RESUME_SCHEMA_VERSION: Final[str] = "sovereign.integration-plan-resume-report.v1"

_SHA40 = re.compile(r"^[0-9a-f]{40}$")


def _git(repo_root: str, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", repo_root, *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def resume_session(
    *,
    repo_root: str,
    workspace_root: str,
    integration_id: str,
    plan_present: bool,
    ledger_actions_present: bool,
    active_revision: Optional[str],
    receipt: Optional[PlanReceipt],
    evidence: Sequence[EvidenceRecord],
) -> ResumeReport:
    """Pre-resume readback for an integration plan.

    Returns a ``ResumeReport`` describing whether resuming work is safe.
    ``mutation`` is the only allowed side effect, and even then the
    function performs *no* filesystem write. Callers must compare the
    returned drift findings against fresh runtime readback before
    continuing.
    """
    workspace_revision = _git(workspace_root, "rev-parse", "HEAD")
    remote_revision = _git(workspace_root, "rev-parse", "origin/HEAD") or _git(
        workspace_root, "rev-parse", "@{u}"
    )
    diff_output = _git(workspace_root, "diff", "--shortstat")
    diff_lines = 0
    if diff_output:
        # Format: "<files> files changed, <insertions>(+), <deletions>(-)"
        # We deliberately use the line count of the diff stat itself.
        diff_lines = len(diff_output.splitlines())

    findings: List[DriftFinding] = []
    if receipt is not None and not plan_present:
        findings.append(
            DriftFinding(
                surface="plan-receipt",
                severity="P0",
                detail="receipt supplied to resume but plan is not on disk",
            )
        )
    if not ledger_actions_present and receipt is not None:
        findings.append(
            DriftFinding(
                surface="ledger-actions",
                severity="P1",
                detail="no append-only ledger actions recorded",
            )
        )
    if active_revision is not None and not _SHA40.fullmatch(active_revision):
        findings.append(
            DriftFinding(
                surface="active-revision",
                severity="P0",
                detail="active_revision is not a 40-hex SHA",
            )
        )
    revision_match = (
        workspace_revision == receipt.base_revision
        if (workspace_revision and receipt is not None and receipt.base_revision)
        else False
    )
    if receipt is not None and workspace_revision and not revision_match:
        findings.append(
            DriftFinding(
                surface="workspace-revision",
                severity="P1",
                detail=(
                    f"workspace HEAD {workspace_revision[:12]} != "
                    f"plan base_revision {receipt.base_revision[:12]}"
                ),
            )
        )

    status_map: Dict[str, str] = {}
    if receipt is not None:
        status_map = {
            phase.phase_id: IntegrationPlanLane.evaluate_phase(phase, evidence).value
            for phase in receipt.phases
        }

    if findings:
        decision = "resume-blocked-by-drift"
    elif receipt is None and not plan_present:
        # No active plan at all \u2014 not even drift, just nothing to resume.
        decision = "resume-no-active-plan"
    elif receipt is None:
        decision = "resume-no-active-plan"
    else:
        decision = "resume-ready"

    return ResumeReport(
        schema_version=_RESUME_SCHEMA_VERSION,
        plan_id=receipt.plan_id if receipt is not None else integration_id,
        workspace_root_label=workspace_root,
        plan_present=plan_present,
        ledger_present=ledger_actions_present,
        git_diff_lines=diff_lines,
        workspace_revision=workspace_revision or None,
        remote_revision=remote_revision or None,
        revision_match=revision_match,
        active_revision_present=active_revision is not None,
        next_step=receipt.next_step if receipt is not None else None,
        status_map=status_map,
        findings=tuple(findings),
        resume_decision=decision,
        mutationPerformed=False,
        runtimeVerified=False,
        secretValuesReturned=False,
    )