"""Tests for rescue_evidence_gate — Issue #1100.

Covers:
- verify_diagnosis_is_read_only: rejects mutation, missing SHA, unsupported family
- evaluate_repair_baseline: blocked without valid diagnosis, repository mismatch
- evaluate_rescue_readback: VERIFIED / CONTRADICTED / BLOCKED paths
- auto_merge_allowed is always False
- Stale PR head → CONTRADICTED
- Missing CI → BLOCKED
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent_runtime.rescue_evidence_gate import (
    VERDICT_BLOCKED,
    VERDICT_CONTRADICTED,
    VERDICT_VERIFIED,
    evaluate_repair_baseline,
    evaluate_rescue_readback,
    verify_diagnosis_is_read_only,
)

SHA40 = "a" * 40
SHA40B = "b" * 40
SHA64 = "c" * 64

REPO = "https://github.com/acme/app"
REPAIR_ID = "repair-test-001"

VALID_DIAGNOSIS: dict = {
    "schemaVersion": "sovereign.rescue.v1",
    "ok": True,
    "supported": True,
    "mutationPerformed": False,
    "repository": REPO,
    "baseSha": SHA40,
    "baseBranch": "main",
    "failureFamily": "github_actions_ci",
    "evidenceSha256": SHA64,
}

PR_URL = "https://github.com/acme/app/pull/42"


# ---------------------------------------------------------------------------
# verify_diagnosis_is_read_only
# ---------------------------------------------------------------------------

def test_diagnosis_valid_is_ok() -> None:
    result = verify_diagnosis_is_read_only(VALID_DIAGNOSIS)
    assert result.ok is True
    assert result.blocker is None
    assert result.diagnosis_sha256 is not None
    assert result.evidence_sha256 == SHA64


def test_diagnosis_rejects_mutation_performed() -> None:
    bad = {**VALID_DIAGNOSIS, "mutationPerformed": True}
    result = verify_diagnosis_is_read_only(bad)
    assert result.ok is False
    assert "mutation" in (result.blocker or "")


def test_diagnosis_rejects_repair_id_present() -> None:
    bad = {**VALID_DIAGNOSIS, "repairId": "some-repair"}
    result = verify_diagnosis_is_read_only(bad)
    assert result.ok is False
    assert "repair_id" in (result.blocker or "")


def test_diagnosis_rejects_missing_base_sha() -> None:
    bad = {k: v for k, v in VALID_DIAGNOSIS.items() if k != "baseSha"}
    result = verify_diagnosis_is_read_only(bad)
    assert result.ok is False
    assert "base_sha" in (result.blocker or "")


def test_diagnosis_rejects_invalid_base_sha() -> None:
    bad = {**VALID_DIAGNOSIS, "baseSha": "not-a-sha"}
    result = verify_diagnosis_is_read_only(bad)
    assert result.ok is False


def test_diagnosis_rejects_missing_evidence_sha256() -> None:
    bad = {k: v for k, v in VALID_DIAGNOSIS.items() if k != "evidenceSha256"}
    result = verify_diagnosis_is_read_only(bad)
    assert result.ok is False
    assert "evidence_sha256" in (result.blocker or "")


def test_diagnosis_rejects_unsupported_family() -> None:
    bad = {**VALID_DIAGNOSIS, "supported": False}
    result = verify_diagnosis_is_read_only(bad)
    assert result.ok is False
    assert "family_not_supported" in (result.blocker or "")


def test_diagnosis_rejects_non_mapping() -> None:
    result = verify_diagnosis_is_read_only("not a mapping")  # type: ignore[arg-type]
    assert result.ok is False


# ---------------------------------------------------------------------------
# evaluate_repair_baseline
# ---------------------------------------------------------------------------

def test_repair_baseline_valid_is_allowed() -> None:
    result = evaluate_repair_baseline(
        diagnosis=VALID_DIAGNOSIS,
        repair_id=REPAIR_ID,
        repository=REPO,
    )
    assert result.allowed is True
    assert result.verdict == VERDICT_VERIFIED
    assert result.baseline_sha256 is not None
    assert result.base_sha == SHA40
    assert not result.blockers


def test_repair_baseline_missing_repair_id_is_blocked() -> None:
    result = evaluate_repair_baseline(
        diagnosis=VALID_DIAGNOSIS,
        repair_id="",
        repository=REPO,
    )
    assert result.allowed is False
    assert result.verdict == VERDICT_BLOCKED
    assert "repair_id_missing" in result.blockers


def test_repair_baseline_missing_repository_is_blocked() -> None:
    result = evaluate_repair_baseline(
        diagnosis=VALID_DIAGNOSIS,
        repair_id=REPAIR_ID,
        repository="",
    )
    assert result.allowed is False
    assert "repository_missing" in result.blockers


def test_repair_baseline_repository_mismatch_is_blocked() -> None:
    result = evaluate_repair_baseline(
        diagnosis=VALID_DIAGNOSIS,
        repair_id=REPAIR_ID,
        repository="https://github.com/other/repo",
    )
    assert result.allowed is False
    assert any("mismatch" in b for b in result.blockers)


def test_repair_baseline_impure_diagnosis_is_blocked() -> None:
    bad_diagnosis = {**VALID_DIAGNOSIS, "mutationPerformed": True}
    result = evaluate_repair_baseline(
        diagnosis=bad_diagnosis,
        repair_id=REPAIR_ID,
        repository=REPO,
    )
    assert result.allowed is False
    assert result.verdict == VERDICT_BLOCKED


def test_repair_baseline_sha256_is_stable() -> None:
    r1 = evaluate_repair_baseline(diagnosis=VALID_DIAGNOSIS, repair_id=REPAIR_ID, repository=REPO)
    r2 = evaluate_repair_baseline(diagnosis=VALID_DIAGNOSIS, repair_id=REPAIR_ID, repository=REPO)
    assert r1.baseline_sha256 == r2.baseline_sha256


# ---------------------------------------------------------------------------
# evaluate_rescue_readback
# ---------------------------------------------------------------------------

def _baseline() -> object:
    return evaluate_repair_baseline(
        diagnosis=VALID_DIAGNOSIS,
        repair_id=REPAIR_ID,
        repository=REPO,
    )


def test_readback_verified_on_all_green() -> None:
    baseline = _baseline()
    result = evaluate_rescue_readback(
        baseline=baseline,  # type: ignore[arg-type]
        patch_changed_files=["backend/fix.py"],
        test_summary_hash=SHA64,
        pr_head_sha=SHA40B,
        published_head_sha=SHA40B,
        ci_head_sha_match=True,
        ci_green=True,
        pr_url=PR_URL,
    )
    assert result.verdict == VERDICT_VERIFIED
    assert result.auto_merge_allowed is False
    assert result.readback_sha256 is not None


def test_readback_blocked_missing_changed_files() -> None:
    baseline = _baseline()
    result = evaluate_rescue_readback(
        baseline=baseline,  # type: ignore[arg-type]
        patch_changed_files=[],
        test_summary_hash=SHA64,
        pr_head_sha=SHA40B,
        published_head_sha=SHA40B,
        ci_head_sha_match=True,
        ci_green=True,
        pr_url=PR_URL,
    )
    assert result.verdict == VERDICT_BLOCKED
    assert "patch_changed_files_missing" in result.blockers


def test_readback_blocked_missing_test_hash() -> None:
    baseline = _baseline()
    result = evaluate_rescue_readback(
        baseline=baseline,  # type: ignore[arg-type]
        patch_changed_files=["fix.py"],
        test_summary_hash="",
        pr_head_sha=SHA40B,
        published_head_sha=SHA40B,
        ci_head_sha_match=True,
        ci_green=True,
        pr_url=PR_URL,
    )
    assert result.verdict == VERDICT_BLOCKED
    assert "test_summary_hash_missing_or_invalid" in result.blockers


def test_readback_contradicted_when_head_sha_differs() -> None:
    """Stale PR head: pr_head_sha ≠ published_head_sha → CONTRADICTED."""
    baseline = _baseline()
    result = evaluate_rescue_readback(
        baseline=baseline,  # type: ignore[arg-type]
        patch_changed_files=["fix.py"],
        test_summary_hash=SHA64,
        pr_head_sha=SHA40,          # different from published
        published_head_sha=SHA40B,
        ci_head_sha_match=True,
        ci_green=True,
        pr_url=PR_URL,
    )
    assert result.verdict == VERDICT_CONTRADICTED
    assert any("head_sha_differs" in c for c in result.contradictions)


def test_readback_contradicted_when_ci_not_bound() -> None:
    """CI ran against different head → stale binding → CONTRADICTED."""
    baseline = _baseline()
    result = evaluate_rescue_readback(
        baseline=baseline,  # type: ignore[arg-type]
        patch_changed_files=["fix.py"],
        test_summary_hash=SHA64,
        pr_head_sha=SHA40B,
        published_head_sha=SHA40B,
        ci_head_sha_match=False,    # stale
        ci_green=True,
        pr_url=PR_URL,
    )
    assert result.verdict == VERDICT_CONTRADICTED
    assert any("ci_head_sha" in c for c in result.contradictions)


def test_readback_blocked_ci_not_green() -> None:
    baseline = _baseline()
    result = evaluate_rescue_readback(
        baseline=baseline,  # type: ignore[arg-type]
        patch_changed_files=["fix.py"],
        test_summary_hash=SHA64,
        pr_head_sha=SHA40B,
        published_head_sha=SHA40B,
        ci_head_sha_match=True,
        ci_green=False,             # not green
        pr_url=PR_URL,
    )
    assert result.verdict == VERDICT_BLOCKED
    assert "ci_not_green_on_exact_head" in result.blockers


def test_readback_blocked_missing_pr_url() -> None:
    baseline = _baseline()
    result = evaluate_rescue_readback(
        baseline=baseline,  # type: ignore[arg-type]
        patch_changed_files=["fix.py"],
        test_summary_hash=SHA64,
        pr_head_sha=SHA40B,
        published_head_sha=SHA40B,
        ci_head_sha_match=True,
        ci_green=True,
        pr_url="",
    )
    assert result.verdict == VERDICT_BLOCKED
    assert "pr_url_missing_or_invalid" in result.blockers


def test_readback_auto_merge_always_false() -> None:
    baseline = _baseline()
    for ci_green in (True, False):
        result = evaluate_rescue_readback(
            baseline=baseline,  # type: ignore[arg-type]
            patch_changed_files=["fix.py"],
            test_summary_hash=SHA64,
            pr_head_sha=SHA40B,
            published_head_sha=SHA40B,
            ci_head_sha_match=True,
            ci_green=ci_green,
            pr_url=PR_URL,
        )
        assert result.auto_merge_allowed is False


def test_readback_sha256_is_stable_across_calls() -> None:
    baseline = _baseline()
    kwargs = dict(
        baseline=baseline,
        patch_changed_files=["fix.py"],
        test_summary_hash=SHA64,
        pr_head_sha=SHA40B,
        published_head_sha=SHA40B,
        ci_head_sha_match=True,
        ci_green=True,
        pr_url=PR_URL,
    )
    r1 = evaluate_rescue_readback(**kwargs)  # type: ignore[arg-type]
    r2 = evaluate_rescue_readback(**kwargs)  # type: ignore[arg-type]
    assert r1.readback_sha256 == r2.readback_sha256
