"""Fail-closed evidence bindings for Sovereign Rescue write paths.

Issue: #1100 — [Evidence/Mutation] Sovereign Rescue und GitHub-Schreibpfade fail-closed binden

Invariants
----------
- Free diagnosis is read-only. Any observation with mutationPerformed=True is CONTRADICTED.
- Paid repair must hold a verified baseline (prior free diagnosis) before starting mutation.
- Post-patch evidence requires: patch evidence + live readback with exact-head binding.
- A proof verdict of VERIFIED requires non-stale, exact-head readback. It never auto-merges.
- Diagnosis and repair are separate operations and receipts.
- No raw prompt, repository content, token, or payment date enters the proof envelope.

This module contains no network, database, filesystem, clock, or random access.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Final, Mapping


_SHA40: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_SHA64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")

RESCUE_EVIDENCE_SCHEMA: Final[str] = "sovereign.rescue-evidence-gate.v1"

# Verdict values
VERDICT_VERIFIED: Final[str] = "VERIFIED"
VERDICT_CONTRADICTED: Final[str] = "CONTRADICTED"
VERDICT_BLOCKED: Final[str] = "BLOCKED_BY_MISSING_EVIDENCE"


def _canonical_sha256(value: Any) -> str:
    def _canonical(v: Any) -> Any:
        if v is None or isinstance(v, bool):
            return v
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            raise ValueError("float forbidden in rescue evidence")
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
# 1. Free-diagnosis purity gate
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class DiagnosisPurityResult:
    """Result of verifying that a free diagnosis is read-only."""
    ok: bool
    blocker: str | None
    diagnosis_sha256: str | None
    evidence_sha256: str | None


def verify_diagnosis_is_read_only(diagnosis: Mapping[str, Any]) -> DiagnosisPurityResult:
    """Verify a free-diagnosis payload is read-only and carries no mutation evidence.

    A diagnosis that claims mutationPerformed=True or contains repairId is CONTRADICTED —
    it cannot be used as a baseline for a paid repair.
    """
    if not isinstance(diagnosis, dict):
        return DiagnosisPurityResult(
            ok=False,
            blocker="diagnosis_not_a_mapping",
            diagnosis_sha256=None,
            evidence_sha256=None,
        )

    mutation_performed = diagnosis.get("mutationPerformed")
    if mutation_performed is True:
        return DiagnosisPurityResult(
            ok=False,
            blocker="diagnosis_claims_mutation_performed",
            diagnosis_sha256=None,
            evidence_sha256=None,
        )

    if diagnosis.get("repairId") or diagnosis.get("repair_id"):
        return DiagnosisPurityResult(
            ok=False,
            blocker="diagnosis_contains_repair_id_not_read_only",
            diagnosis_sha256=None,
            evidence_sha256=None,
        )

    base_sha = str(diagnosis.get("baseSha") or diagnosis.get("base_sha") or "").strip().lower()
    if not _SHA40.fullmatch(base_sha):
        return DiagnosisPurityResult(
            ok=False,
            blocker="diagnosis_missing_valid_base_sha",
            diagnosis_sha256=None,
            evidence_sha256=None,
        )

    evidence_sha = str(diagnosis.get("evidenceSha256") or "").strip().lower()
    if not _SHA64.fullmatch(evidence_sha):
        return DiagnosisPurityResult(
            ok=False,
            blocker="diagnosis_missing_evidence_sha256",
            diagnosis_sha256=None,
            evidence_sha256=None,
        )

    if not diagnosis.get("supported"):
        return DiagnosisPurityResult(
            ok=False,
            blocker="diagnosis_family_not_supported",
            diagnosis_sha256=None,
            evidence_sha256=None,
        )

    diag_sha = _canonical_sha256({
        "baseSha": base_sha,
        "evidenceSha256": evidence_sha,
        "failureFamily": str(diagnosis.get("failureFamily") or ""),
        "repository": str(diagnosis.get("repository") or ""),
        "schemaVersion": str(diagnosis.get("schemaVersion") or ""),
        "supported": True,
    })

    return DiagnosisPurityResult(
        ok=True,
        blocker=None,
        diagnosis_sha256=diag_sha,
        evidence_sha256=evidence_sha,
    )


# ---------------------------------------------------------------------------
# 2. Repair baseline gate — must precede any mutation
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RepairBaselineResult:
    """Result of verifying that a verified read-only baseline exists before repair."""
    allowed: bool
    verdict: str
    blockers: tuple[str, ...]
    baseline_sha256: str | None
    base_sha: str | None


def evaluate_repair_baseline(
    *,
    diagnosis: Mapping[str, Any],
    repair_id: str,
    repository: str,
) -> RepairBaselineResult:
    """Verify that a real free-diagnosis baseline exists before allowing repair to start.

    A paid repair without a verified baseline is BLOCKED — no mutation may start.
    """
    blockers: list[str] = []

    purity = verify_diagnosis_is_read_only(diagnosis)
    if not purity.ok:
        blockers.append(purity.blocker or "diagnosis_purity_failed")

    clean_repair_id = str(repair_id or "").strip()
    if not clean_repair_id:
        blockers.append("repair_id_missing")

    clean_repo = str(repository or "").strip()
    if not clean_repo:
        blockers.append("repository_missing")

    diag_repo = str(diagnosis.get("repository") or "").strip()
    if clean_repo and diag_repo and diag_repo != clean_repo:
        blockers.append("repository_mismatch_between_diagnosis_and_repair")

    base_sha = str(diagnosis.get("baseSha") or diagnosis.get("base_sha") or "").strip().lower()

    if blockers:
        return RepairBaselineResult(
            allowed=False,
            verdict=VERDICT_BLOCKED,
            blockers=tuple(dict.fromkeys(blockers)),
            baseline_sha256=None,
            base_sha=None,
        )

    baseline_sha = _canonical_sha256({
        "base_sha": base_sha,
        "diagnosis_sha256": purity.diagnosis_sha256,
        "repair_id": clean_repair_id,
        "repository": clean_repo,
        "schema_version": RESCUE_EVIDENCE_SCHEMA,
    })

    return RepairBaselineResult(
        allowed=True,
        verdict=VERDICT_VERIFIED,
        blockers=(),
        baseline_sha256=baseline_sha,
        base_sha=base_sha,
    )


# ---------------------------------------------------------------------------
# 3. Post-patch readback verdict
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RescueReadbackVerdict:
    """Verdict after a repair patch plus required live readback."""
    verdict: str
    blockers: tuple[str, ...]
    contradictions: tuple[str, ...]
    baseline_sha256: str | None
    head_sha: str | None
    readback_sha256: str | None
    auto_merge_allowed: bool


def evaluate_rescue_readback(
    *,
    baseline: RepairBaselineResult,
    patch_changed_files: list[str],
    test_summary_hash: str,
    pr_head_sha: str,
    published_head_sha: str,
    ci_head_sha_match: bool,
    ci_green: bool,
    pr_url: str,
) -> RescueReadbackVerdict:
    """Evaluate post-patch evidence and live readback to derive a fail-closed verdict.

    VERIFIED only when:
    - valid baseline (prior free diagnosis)
    - patch evidence (changed files + non-empty test summary)
    - PR URL present
    - exact-head binding: ci_head_sha_match + pr_head_sha == published_head_sha
    - CI green on exact head

    Stale heads or contradictory SHAs → CONTRADICTED.
    Any missing check → BLOCKED_BY_MISSING_EVIDENCE.
    Auto-merge is always forbidden regardless of verdict.
    """
    blockers: list[str] = []
    contradictions: list[str] = []

    if not baseline.allowed:
        blockers.extend(baseline.blockers)
        blockers.append("baseline_not_established")

    if not patch_changed_files:
        blockers.append("patch_changed_files_missing")

    ts_hash = str(test_summary_hash or "").strip().lower()
    if not ts_hash or not _SHA64.fullmatch(ts_hash):
        blockers.append("test_summary_hash_missing_or_invalid")

    head = str(pr_head_sha or "").strip().lower()
    pub = str(published_head_sha or "").strip().lower()
    pr = str(pr_url or "").strip()

    if not _SHA40.fullmatch(head):
        blockers.append("pr_head_sha_missing")

    if not _SHA40.fullmatch(pub):
        blockers.append("published_head_sha_missing")

    if _SHA40.fullmatch(head) and _SHA40.fullmatch(pub) and head != pub:
        contradictions.append("pr_head_sha_differs_from_published_head")

    if not pr.startswith("https://github.com/") or "/pull/" not in pr:
        blockers.append("pr_url_missing_or_invalid")

    if not ci_head_sha_match:
        # Stale CI — head changed after CI ran
        contradictions.append("ci_head_sha_not_bound_to_pr_head")

    if not ci_green:
        blockers.append("ci_not_green_on_exact_head")

    if contradictions:
        verdict = VERDICT_CONTRADICTED
    elif blockers:
        verdict = VERDICT_BLOCKED
    else:
        verdict = VERDICT_VERIFIED

    readback_sha: str | None = None
    if verdict == VERDICT_VERIFIED:
        readback_sha = _canonical_sha256({
            "baseline_sha256": baseline.baseline_sha256,
            "ci_green": True,
            "ci_head_sha_match": True,
            "head_sha": head,
            "patch_file_count": len(patch_changed_files),
            "pr_url": pr,
            "schema_version": RESCUE_EVIDENCE_SCHEMA,
            "test_summary_hash": ts_hash,
        })

    return RescueReadbackVerdict(
        verdict=verdict,
        blockers=tuple(dict.fromkeys(blockers)),
        contradictions=tuple(dict.fromkeys(contradictions)),
        baseline_sha256=baseline.baseline_sha256,
        head_sha=head if _SHA40.fullmatch(head) else None,
        readback_sha256=readback_sha,
        auto_merge_allowed=False,  # Immutable: never auto-merge on proof verdict alone
    )


__all__ = [
    "RESCUE_EVIDENCE_SCHEMA",
    "VERDICT_BLOCKED",
    "VERDICT_CONTRADICTED",
    "VERDICT_VERIFIED",
    "DiagnosisPurityResult",
    "RepairBaselineResult",
    "RescueReadbackVerdict",
    "evaluate_repair_baseline",
    "evaluate_rescue_readback",
    "verify_diagnosis_is_read_only",
]
