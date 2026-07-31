"""Tests for github_write_evidence_gate — Issue #1100.

Covers:
- GitHubWriteEvidenceEnvelope: valid construction, rejection of bad inputs
- evaluate_github_write_evidence: VERIFIED / CONTRADICTED / BLOCKED for all families
- Stale revision binding → CONTRADICTED
- Missing observations → BLOCKED
- audit_ruleset_change: bypass actors, removed required checks
- auto_merge_allowed is always False
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent_runtime.github_write_evidence_gate import (
    OPERATION_FAMILIES,
    VERDICT_BLOCKED,
    VERDICT_CONTRADICTED,
    VERDICT_VERIFIED,
    GitHubWriteEvidenceEnvelope,
    GitHubWriteObservation,
    audit_ruleset_change,
    evaluate_github_write_evidence,
)

SHA40 = "a" * 40
SHA40B = "b" * 40
SHA64 = "c" * 64
SHA64B = "d" * 64

REPO = "https://github.com/acme/app"

_FAMILY_REQS = {
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


def _envelope(family: str = "branch_file_change") -> GitHubWriteEvidenceEnvelope:
    return GitHubWriteEvidenceEnvelope(
        operation_family=family,
        operation_identity="op-identity-001",
        repository=REPO,
        base_revision=SHA40,
        input_hash=SHA64,
        diff_hash=SHA64B,
        changed_paths=("src/fix.py",),
        agent_run_receipt_hash=SHA64,
        owner_authorization_scope="owner_private_mode",
    )


def _obs(req_id: str, rev: str = SHA40, assertion: str = "OBSERVED") -> GitHubWriteObservation:
    return GitHubWriteObservation(
        requirement_id=req_id,
        value_hash=SHA64,
        source="REPOSITORY_READBACK",
        assertion=assertion,
        bound_revision=rev,
    )


def _full_observations(family: str, rev: str = SHA40) -> list[GitHubWriteObservation]:
    return [_obs(req_id, rev) for req_id in _FAMILY_REQS[family]]


# ---------------------------------------------------------------------------
# GitHubWriteEvidenceEnvelope
# ---------------------------------------------------------------------------

def test_envelope_valid_construction() -> None:
    env = _envelope("branch_file_change")
    assert env.operation_family == "branch_file_change"
    assert len(env.envelope_sha256) == 64
    assert env.base_revision == SHA40


def test_envelope_rejects_unknown_family() -> None:
    try:
        GitHubWriteEvidenceEnvelope(
            operation_family="unknown_family",
            operation_identity="op",
            repository=REPO,
            base_revision=SHA40,
            input_hash=SHA64,
            diff_hash=SHA64B,
            changed_paths=(),
            agent_run_receipt_hash=SHA64,
            owner_authorization_scope="owner",
        )
        assert False, "should have raised"
    except ValueError:
        pass


def test_envelope_rejects_bad_base_revision() -> None:
    try:
        GitHubWriteEvidenceEnvelope(
            operation_family="branch_file_change",
            operation_identity="op",
            repository=REPO,
            base_revision="not-a-sha",
            input_hash=SHA64,
            diff_hash=SHA64B,
            changed_paths=(),
            agent_run_receipt_hash=SHA64,
            owner_authorization_scope="owner",
        )
        assert False, "should have raised"
    except ValueError:
        pass


def test_envelope_sha256_changes_with_content() -> None:
    e1 = _envelope("branch_file_change")
    e2 = GitHubWriteEvidenceEnvelope(
        operation_family="branch_file_change",
        operation_identity="different-op",
        repository=REPO,
        base_revision=SHA40,
        input_hash=SHA64,
        diff_hash=SHA64B,
        changed_paths=(),
        agent_run_receipt_hash=SHA64,
        owner_authorization_scope="owner_private_mode",
    )
    assert e1.envelope_sha256 != e2.envelope_sha256


def test_envelope_allows_empty_diff_hash_for_workflow_control() -> None:
    env = GitHubWriteEvidenceEnvelope(
        operation_family="workflow_control",
        operation_identity="op",
        repository=REPO,
        base_revision=SHA40,
        input_hash=SHA64,
        diff_hash="",  # no diff for workflow control
        changed_paths=(),
        agent_run_receipt_hash=SHA64,
        owner_authorization_scope="owner_private_mode",
    )
    assert env.diff_hash == ""


def test_envelope_all_operation_families_accepted() -> None:
    for family in OPERATION_FAMILIES:
        env = GitHubWriteEvidenceEnvelope(
            operation_family=family,
            operation_identity="op",
            repository=REPO,
            base_revision=SHA40,
            input_hash=SHA64,
            diff_hash=SHA64B,
            changed_paths=(),
            agent_run_receipt_hash=SHA64,
            owner_authorization_scope="owner_private_mode",
        )
        assert env.operation_family == family


# ---------------------------------------------------------------------------
# GitHubWriteObservation
# ---------------------------------------------------------------------------

def test_observation_valid() -> None:
    obs = _obs("owner_authorization_scope")
    assert obs.assertion == "OBSERVED"
    assert len(obs.observation_sha256) == 64


def test_observation_rejects_bad_assertion() -> None:
    try:
        GitHubWriteObservation(
            requirement_id="owner_authorization_scope",
            value_hash=SHA64,
            source="REPOSITORY_READBACK",
            assertion="MAYBE",
            bound_revision=SHA40,
        )
        assert False, "should have raised"
    except ValueError:
        pass


def test_observation_rejects_bad_value_hash() -> None:
    try:
        GitHubWriteObservation(
            requirement_id="owner_authorization_scope",
            value_hash="short",
            source="REPOSITORY_READBACK",
            assertion="OBSERVED",
            bound_revision=SHA40,
        )
        assert False, "should have raised"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# evaluate_github_write_evidence — branch_file_change
# ---------------------------------------------------------------------------

def test_branch_file_change_verified_all_present() -> None:
    env = _envelope("branch_file_change")
    obs = _full_observations("branch_file_change")
    result = evaluate_github_write_evidence(env, obs)
    assert result.verdict == VERDICT_VERIFIED
    assert result.auto_merge_allowed is False
    assert not result.missing
    assert not result.contradicted


def test_branch_file_change_blocked_missing_one() -> None:
    env = _envelope("branch_file_change")
    obs = [o for o in _full_observations("branch_file_change") if o.requirement_id != "diff_hash"]
    result = evaluate_github_write_evidence(env, obs)
    assert result.verdict == VERDICT_BLOCKED
    assert "diff_hash" in result.missing


def test_branch_file_change_contradicted_on_stale_revision() -> None:
    env = _envelope("branch_file_change")  # base_revision = SHA40
    # Bind all observations to a DIFFERENT revision → stale
    obs = _full_observations("branch_file_change", rev=SHA40B)
    result = evaluate_github_write_evidence(env, obs)
    assert result.verdict == VERDICT_CONTRADICTED
    assert result.auto_merge_allowed is False


def test_branch_file_change_contradicted_on_contradicted_assertion() -> None:
    env = _envelope("branch_file_change")
    obs = _full_observations("branch_file_change")
    # Replace one observation with a CONTRADICTED assertion
    contradicted = [
        _obs(o.requirement_id, SHA40, "CONTRADICTED") if o.requirement_id == "diff_hash" else o
        for o in obs
    ]
    result = evaluate_github_write_evidence(env, contradicted)
    assert result.verdict == VERDICT_CONTRADICTED
    assert "diff_hash" in result.contradicted


# ---------------------------------------------------------------------------
# evaluate_github_write_evidence — pr_merge_close
# ---------------------------------------------------------------------------

def test_pr_merge_close_verified() -> None:
    env = _envelope("pr_merge_close")
    obs = _full_observations("pr_merge_close")
    result = evaluate_github_write_evidence(env, obs)
    assert result.verdict == VERDICT_VERIFIED


def test_pr_merge_close_blocked_missing_ci_head_sha_bound() -> None:
    env = _envelope("pr_merge_close")
    obs = [o for o in _full_observations("pr_merge_close") if o.requirement_id != "ci_head_sha_bound"]
    result = evaluate_github_write_evidence(env, obs)
    assert result.verdict == VERDICT_BLOCKED
    assert "ci_head_sha_bound" in result.missing


def test_pr_merge_close_blocked_missing_pr_readback() -> None:
    env = _envelope("pr_merge_close")
    obs = [o for o in _full_observations("pr_merge_close") if o.requirement_id != "pr_readback"]
    result = evaluate_github_write_evidence(env, obs)
    assert result.verdict == VERDICT_BLOCKED
    assert "pr_readback" in result.missing


# ---------------------------------------------------------------------------
# evaluate_github_write_evidence — ruleset_gate_change
# ---------------------------------------------------------------------------

def test_ruleset_gate_change_verified() -> None:
    env = _envelope("ruleset_gate_change")
    obs = _full_observations("ruleset_gate_change")
    result = evaluate_github_write_evidence(env, obs)
    assert result.verdict == VERDICT_VERIFIED


def test_ruleset_gate_change_blocked_missing_capability_delta() -> None:
    env = _envelope("ruleset_gate_change")
    obs = [o for o in _full_observations("ruleset_gate_change") if o.requirement_id != "capability_delta"]
    result = evaluate_github_write_evidence(env, obs)
    assert result.verdict == VERDICT_BLOCKED
    assert "capability_delta" in result.missing


# ---------------------------------------------------------------------------
# evaluate_github_write_evidence — workflow_control
# ---------------------------------------------------------------------------

def test_workflow_control_verified() -> None:
    env = _envelope("workflow_control")
    obs = _full_observations("workflow_control")
    result = evaluate_github_write_evidence(env, obs)
    assert result.verdict == VERDICT_VERIFIED


def test_workflow_control_blocked_missing_workflow_sha() -> None:
    env = _envelope("workflow_control")
    obs = [o for o in _full_observations("workflow_control") if o.requirement_id != "workflow_sha"]
    result = evaluate_github_write_evidence(env, obs)
    assert result.verdict == VERDICT_BLOCKED
    assert "workflow_sha" in result.missing


# ---------------------------------------------------------------------------
# audit_ruleset_change
# ---------------------------------------------------------------------------

CANONICAL_CHECKS = ["Release Gate", "Agent Runtime Tests", "continuity-ledger", "Revision Guardian"]


def test_ruleset_audit_no_change_allowed() -> None:
    audit = audit_ruleset_change(
        proposed_required_checks=CANONICAL_CHECKS,
        canonical_required_checks=CANONICAL_CHECKS,
        bypass_actors=[],
    )
    assert audit.allowed is True
    assert audit.blocker is None
    assert not audit.removed_requirements
    assert not audit.bypass_actors_present


def test_ruleset_audit_bypass_actors_blocked() -> None:
    audit = audit_ruleset_change(
        proposed_required_checks=CANONICAL_CHECKS,
        canonical_required_checks=CANONICAL_CHECKS,
        bypass_actors=[{"actor_id": 123, "actor_type": "Team"}],
    )
    assert audit.allowed is False
    assert "bypass_actors" in (audit.blocker or "")
    assert audit.bypass_actors_present is True


def test_ruleset_audit_removed_check_blocked() -> None:
    reduced = [c for c in CANONICAL_CHECKS if c != "Release Gate"]
    audit = audit_ruleset_change(
        proposed_required_checks=reduced,
        canonical_required_checks=CANONICAL_CHECKS,
        bypass_actors=[],
    )
    assert audit.allowed is False
    assert "Release Gate" in audit.removed_requirements
    assert "removes" in (audit.blocker or "") or "removed" in (audit.blocker or "")


def test_ruleset_audit_extra_checks_allowed() -> None:
    """Adding a new check to the proposed set is fine."""
    extended = CANONICAL_CHECKS + ["Extra Check"]
    audit = audit_ruleset_change(
        proposed_required_checks=extended,
        canonical_required_checks=CANONICAL_CHECKS,
        bypass_actors=[],
    )
    assert audit.allowed is True


# ---------------------------------------------------------------------------
# auto_merge_allowed invariant across all families
# ---------------------------------------------------------------------------

def test_auto_merge_always_false_all_families() -> None:
    for family in OPERATION_FAMILIES:
        env = GitHubWriteEvidenceEnvelope(
            operation_family=family,
            operation_identity="op",
            repository=REPO,
            base_revision=SHA40,
            input_hash=SHA64,
            diff_hash=SHA64B,
            changed_paths=(),
            agent_run_receipt_hash=SHA64,
            owner_authorization_scope="owner_private_mode",
        )
        result = evaluate_github_write_evidence(env, [])
        assert result.auto_merge_allowed is False, f"auto_merge_allowed must be False for {family}"
