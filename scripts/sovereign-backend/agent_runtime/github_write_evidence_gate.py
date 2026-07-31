"""Fail-closed evidence gate for all GitHub write-path operations.

Issue: #1100 — [Evidence/Mutation] Sovereign Rescue und GitHub-Schreibpfade fail-closed binden

Protected operation families
-----------------------------
- branch_file_change     Branch creation and file mutations
- draft_pr_lifecycle     Draft-PR creation and update
- pr_merge_close         Merge, close, reopen, branch cleanup
- workflow_control        Workflow retry and dispatch
- ruleset_gate_change    Ruleset and required-gate modifications

Fail-closed invariants
----------------------
- An operation without a verified authorization scope returns BLOCKED.
- Any observation with a stale or mismatched revision returns CONTRADICTED.
- Ruleset bypass cannot silently remove evidence requirements.
- No auto-merge from a proof verdict alone.
- No raw prompt, repository content, token, or payment date in the evidence envelope.

This module contains no network, database, filesystem, clock, or random access.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Final, Mapping, Sequence


_SHA40: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_SHA64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_.:-]{1,119}$")
_SAFE_PATH: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_./@+\- ]{1,300}$")

GITHUB_WRITE_EVIDENCE_SCHEMA: Final[str] = "sovereign.github-write-evidence-gate.v1"

VERDICT_VERIFIED: Final[str] = "VERIFIED"
VERDICT_CONTRADICTED: Final[str] = "CONTRADICTED"
VERDICT_BLOCKED: Final[str] = "BLOCKED_BY_MISSING_EVIDENCE"

# All protected operation families
OPERATION_FAMILIES: Final[frozenset[str]] = frozenset({
    "branch_file_change",
    "draft_pr_lifecycle",
    "pr_merge_close",
    "ruleset_gate_change",
    "workflow_control",
})

# Minimum required evidence per operation family (requirement_id → human description)
_FAMILY_REQUIREMENTS: Final[dict[str, tuple[str, ...]]] = {
    "branch_file_change": (
        "owner_authorization_scope",
        "repository_revision",
        "input_hash",
        "diff_hash",
        "changed_paths",
        "agent_run_receipt",
    ),
    "draft_pr_lifecycle": (
        "owner_authorization_scope",
        "repository_revision",
        "input_hash",
        "diff_hash",
        "changed_paths",
        "test_evidence",
        "agent_run_receipt",
    ),
    "pr_merge_close": (
        "owner_authorization_scope",
        "repository_revision",
        "input_hash",
        "diff_hash",
        "changed_paths",
        "test_evidence",
        "pr_readback",
        "ci_head_sha_bound",
        "agent_run_receipt",
    ),
    "workflow_control": (
        "owner_authorization_scope",
        "repository_revision",
        "input_hash",
        "workflow_sha",
        "agent_run_receipt",
    ),
    "ruleset_gate_change": (
        "owner_authorization_scope",
        "repository_revision",
        "input_hash",
        "ruleset_readback",
        "agent_run_receipt",
        "capability_delta",
    ),
}


def _canonical_sha256(value: Any) -> str:
    def _canonical(v: Any) -> Any:
        if v is None or isinstance(v, bool):
            return v
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            raise ValueError("float forbidden in github write evidence")
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            return {str(k): _canonical(val) for k, val in sorted(v.items())}
        if isinstance(v, (list, tuple)):
            return [_canonical(item) for item in v]
        raise ValueError(f"non-serializable type: {type(v).__name__}")
    serialized = json.dumps(_canonical(value), separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# GitHub write-path evidence envelope
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class GitHubWriteEvidenceEnvelope:
    """Immutable evidence envelope for one GitHub write-path operation.

    All fields must be caller-supplied from real observations — no defaults
    that substitute for missing evidence.
    """

    operation_family: str
    operation_identity: str
    repository: str
    base_revision: str          # git SHA-40 of the repository head before mutation
    input_hash: str             # SHA-256 of canonical operation parameters
    diff_hash: str              # SHA-256 of canonical diff content (empty string if no diff yet)
    changed_paths: tuple[str, ...]
    agent_run_receipt_hash: str
    owner_authorization_scope: str  # e.g. "owner_private_mode" or "configured_owner_id"
    envelope_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        family = str(self.operation_family or "").strip().lower()
        if family not in OPERATION_FAMILIES:
            raise ValueError(f"unknown operation_family: {family!r}")
        if not _SHA40.fullmatch(str(self.base_revision or "").strip().lower()):
            raise ValueError("base_revision must be a full Git SHA-40")
        if not _SHA64.fullmatch(str(self.input_hash or "").strip().lower()):
            raise ValueError("input_hash must be a SHA-256")
        # diff_hash may be empty string when no diff is present (e.g. workflow_control)
        dh = str(self.diff_hash or "").strip().lower()
        if dh and not _SHA64.fullmatch(dh):
            raise ValueError("diff_hash must be a SHA-256 or empty string")
        if not _SHA64.fullmatch(str(self.agent_run_receipt_hash or "").strip().lower()):
            raise ValueError("agent_run_receipt_hash must be a SHA-256")
        if not str(self.owner_authorization_scope or "").strip():
            raise ValueError("owner_authorization_scope must not be empty")
        object.__setattr__(self, "operation_family", family)
        object.__setattr__(self, "base_revision", str(self.base_revision).strip().lower())
        object.__setattr__(self, "input_hash", str(self.input_hash).strip().lower())
        object.__setattr__(self, "diff_hash", dh)
        object.__setattr__(self, "agent_run_receipt_hash", str(self.agent_run_receipt_hash).strip().lower())
        object.__setattr__(self, "changed_paths", tuple(sorted({
            str(p or "").strip() for p in self.changed_paths if _SAFE_PATH.fullmatch(str(p or "").strip())
        })))
        sha = _canonical_sha256(self._body())
        object.__setattr__(self, "envelope_sha256", sha)

    def _body(self) -> dict[str, Any]:
        return {
            "agent_run_receipt_hash": str(self.agent_run_receipt_hash),
            "base_revision": str(self.base_revision),
            "changed_paths": list(self.changed_paths),
            "diff_hash": str(self.diff_hash),
            "input_hash": str(self.input_hash),
            "operation_family": str(self.operation_family),
            "operation_identity": str(self.operation_identity),
            "owner_authorization_scope": str(self.owner_authorization_scope),
            "repository": str(self.repository),
            "schema_version": GITHUB_WRITE_EVIDENCE_SCHEMA,
        }


# ---------------------------------------------------------------------------
# Evidence observations per operation
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class GitHubWriteObservation:
    """Single collected observation for a GitHub write-path requirement."""
    requirement_id: str
    value_hash: str             # SHA-256 of the canonical observation payload
    source: str                 # e.g. "CI_READBACK", "REPOSITORY_READBACK", "AGENT_RUN_RECEIPT"
    assertion: str              # "OBSERVED" | "CONTRADICTED" | "UNAVAILABLE"
    bound_revision: str         # must match envelope.base_revision or result head SHA

    def __post_init__(self) -> None:
        assertion = str(self.assertion or "").strip().upper()
        if assertion not in {"OBSERVED", "CONTRADICTED", "UNAVAILABLE"}:
            raise ValueError(f"unsupported assertion: {assertion!r}")
        object.__setattr__(self, "assertion", assertion)
        if not _SHA64.fullmatch(str(self.value_hash or "").strip().lower()):
            raise ValueError("value_hash must be a SHA-256")
        rev = str(self.bound_revision or "").strip().lower()
        if rev and not (_SHA40.fullmatch(rev) or _SHA64.fullmatch(rev)):
            raise ValueError("bound_revision must be a full Git SHA-40 or SHA-256")
        object.__setattr__(self, "bound_revision", rev)
        object.__setattr__(self, "value_hash", str(self.value_hash).strip().lower())

    @property
    def observation_sha256(self) -> str:
        return _canonical_sha256({
            "assertion": self.assertion,
            "bound_revision": self.bound_revision,
            "requirement_id": self.requirement_id,
            "source": self.source,
            "value_hash": self.value_hash,
        })


# ---------------------------------------------------------------------------
# Fail-closed evaluation
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class GitHubWriteEvidenceResult:
    """Result of evaluating evidence for a GitHub write-path operation."""
    verdict: str
    operation_family: str
    envelope_sha256: str
    satisfied: tuple[str, ...]
    missing: tuple[str, ...]
    contradicted: tuple[str, ...]
    finding_codes: tuple[str, ...]
    auto_merge_allowed: bool    # always False


def evaluate_github_write_evidence(
    envelope: GitHubWriteEvidenceEnvelope,
    observations: Sequence[GitHubWriteObservation],
) -> GitHubWriteEvidenceResult:
    """Evaluate fail-closed evidence for a GitHub write-path operation.

    Returns VERIFIED only when every requirement for the operation family
    has an OBSERVED observation with a matching bound_revision.

    Stale revisions or CONTRADICTED observations → CONTRADICTED.
    Missing or UNAVAILABLE observations → BLOCKED_BY_MISSING_EVIDENCE.
    """
    required = _FAMILY_REQUIREMENTS.get(envelope.operation_family, ())
    obs_by_req: dict[str, list[GitHubWriteObservation]] = {}
    for obs in observations:
        obs_by_req.setdefault(obs.requirement_id, []).append(obs)

    satisfied: set[str] = set()
    missing: set[str] = set()
    contradicted: set[str] = set()
    findings: set[str] = set()

    for req_id in required:
        candidates = obs_by_req.get(req_id, [])
        if not candidates:
            missing.add(req_id)
            findings.add("required_observation_missing")
            continue

        req_satisfied = False
        req_contradicted = False

        for obs in candidates:
            # Revision binding check: bound_revision must match envelope base or be empty
            if obs.bound_revision and obs.bound_revision != envelope.base_revision:
                req_contradicted = True
                findings.add("observation_bound_to_stale_revision")
                continue
            if obs.assertion == "CONTRADICTED":
                req_contradicted = True
                findings.add("observation_reports_contradiction")
                continue
            if obs.assertion == "UNAVAILABLE":
                findings.add("observation_unavailable")
                continue
            req_satisfied = True

        if req_contradicted:
            contradicted.add(req_id)
        elif req_satisfied:
            satisfied.add(req_id)
        else:
            missing.add(req_id)

    if contradicted:
        verdict = VERDICT_CONTRADICTED
    elif missing:
        verdict = VERDICT_BLOCKED
    else:
        verdict = VERDICT_VERIFIED

    return GitHubWriteEvidenceResult(
        verdict=verdict,
        operation_family=envelope.operation_family,
        envelope_sha256=envelope.envelope_sha256,
        satisfied=tuple(sorted(satisfied)),
        missing=tuple(sorted(missing)),
        contradicted=tuple(sorted(contradicted)),
        finding_codes=tuple(sorted(findings)),
        auto_merge_allowed=False,
    )


# ---------------------------------------------------------------------------
# Ruleset bypass guard
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RulesetBypassAudit:
    """Audit result for a proposed ruleset change."""
    allowed: bool
    blocker: str | None
    removed_requirements: tuple[str, ...]
    bypass_actors_present: bool


def audit_ruleset_change(
    *,
    proposed_required_checks: Sequence[str],
    canonical_required_checks: Sequence[str],
    bypass_actors: Sequence[Any],
) -> RulesetBypassAudit:
    """Verify that a ruleset change does not silently remove evidence requirements.

    A bypass that removes a required check returns BLOCKED.
    Any bypass actors → BLOCKED (fail-closed: no bypass).
    """
    canonical_set = frozenset(str(c or "").strip() for c in canonical_required_checks if str(c or "").strip())
    proposed_set = frozenset(str(c or "").strip() for c in proposed_required_checks if str(c or "").strip())
    removed = tuple(sorted(canonical_set - proposed_set))
    actors_present = bool(bypass_actors)

    if actors_present:
        return RulesetBypassAudit(
            allowed=False,
            blocker="ruleset_bypass_actors_present_violates_evidence_requirement",
            removed_requirements=removed,
            bypass_actors_present=True,
        )

    if removed:
        return RulesetBypassAudit(
            allowed=False,
            blocker=f"ruleset_change_removes_required_checks: {', '.join(removed)}",
            removed_requirements=removed,
            bypass_actors_present=False,
        )

    return RulesetBypassAudit(
        allowed=True,
        blocker=None,
        removed_requirements=(),
        bypass_actors_present=False,
    )


__all__ = [
    "GITHUB_WRITE_EVIDENCE_SCHEMA",
    "OPERATION_FAMILIES",
    "VERDICT_BLOCKED",
    "VERDICT_CONTRADICTED",
    "VERDICT_VERIFIED",
    "GitHubWriteEvidenceEnvelope",
    "GitHubWriteEvidenceResult",
    "GitHubWriteObservation",
    "RulesetBypassAudit",
    "audit_ruleset_change",
    "evaluate_github_write_evidence",
]
