from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent_runtime.rescue import (
    MAX_REPAIR_CHANGED_FILES,
    REPAIR_PACK_CREDITS,
    build_free_diagnosis,
    build_proof_pack,
    entitlement_payload,
    issue_rescue_csrf_token,
    redact_secret_text,
    resolve_account_entitlement,
    verify_proof_pack,
    verify_rescue_csrf_token,
)


BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40


def diagnose(evidence: str, requested_family: str = ""):
    return build_free_diagnosis(
        repository="https://github.com/acme/app",
        base_branch="main",
        base_sha=BASE_SHA,
        evidence_text=evidence,
        requested_family=requested_family,
    )


def test_free_diagnosis_supports_exactly_the_three_v1_failure_families() -> None:
    cases = {
        "github_actions_ci": "GitHub Actions workflow: Process completed with exit code 1 in .github/workflows/ci.yml",
        "docker_compose_container": "docker compose reports container exited and unhealthy in docker-compose.yml",
        "postgresql_migration_schema": "Postgres SQLSTATE: relation does not exist in migrations/042_add_table.sql",
    }
    for family, evidence in cases.items():
        result = diagnose(evidence)
        assert result["ok"] is True
        assert result["failureFamily"] == family
        assert result["baseSha"] == BASE_SHA
        assert result["mutationPerformed"] is False
        assert result["outcomeContract"]["repairPack"]["credits"] == REPAIR_PACK_CREDITS


def test_free_diagnosis_rejects_unsupported_family_without_mutation() -> None:
    result = diagnose("CSS color is wrong and the page layout shifted.")
    assert result["ok"] is False
    assert result["supported"] is False
    assert result["blocker"] == "unsupported_failure_family"
    assert result["mutationPerformed"] is False


def test_free_diagnosis_redacts_secrets_and_never_reflects_raw_evidence() -> None:
    secret = "github_pat_" + "x" * 30
    redacted = redact_secret_text(f"Authorization: Bearer {secret}\npassword=hunter2")
    assert secret not in redacted
    assert "hunter2" not in redacted
    result = diagnose(f"GitHub Actions failed. Authorization: Bearer {secret}")
    assert secret not in str(result)
    assert "evidenceText" not in result
    for value in (
        "GITHUB_TOKEN=ghp_1234567890abcdef",
        "ACCESS_TOKEN=opaque-private-value",
        "DATABASE_PASSWORD=correct-horse-battery-staple",
    ):
        redacted_value = redact_secret_text(value)
        assert value.split("=", 1)[1] not in redacted_value
        assert "[REDACTED]" in redacted_value


def test_outcome_contract_is_revision_bound_and_bounded() -> None:
    result = diagnose("docker compose config failed in compose.yaml")
    contract = result["outcomeContract"]
    assert contract["baseSha"] == BASE_SHA
    assert contract["failureFamily"] == "docker_compose_container"
    assert contract["repairPack"]["maxChangedFiles"] == 12
    assert contract["repairPack"]["maxRepairAttempts"] == 3
    assert contract["repairPack"]["draftPrOnly"] is True
    assert contract["repairPack"]["autoMerge"] is False
    assert len(contract["contractSha256"]) == 64


def test_entitlement_requires_verified_purchase_or_privileged_identity() -> None:
    regular = {
        "id": "user-1",
        "email": "user@example.test",
        "role": "user",
        "credits": 500,
        "paid_purchase_verified": False,
    }
    regular_entitlement = resolve_account_entitlement(regular)
    assert entitlement_payload(regular, regular_entitlement)["entitled"] is False

    purchased = {**regular, "paid_purchase_verified": True}
    purchased_entitlement = resolve_account_entitlement(purchased)
    assert entitlement_payload(purchased, purchased_entitlement)["entitled"] is True

    admin = {**regular, "role": "admin", "credits": 0}
    admin_entitlement = resolve_account_entitlement(admin)
    payload = entitlement_payload(admin, admin_entitlement)
    assert payload["entitled"] is True
    assert payload["requiredCredits"] == 0


def test_proof_pack_is_incomplete_until_exact_head_ci_is_green() -> None:
    repair = {
        "repair_id": "repair-1",
        "repository": "https://github.com/acme/app",
        "failure_family": "github_actions_ci",
        "base_sha": BASE_SHA,
        "published_head_sha": HEAD_SHA,
    }
    job = {
        "changed_files": [".github/workflows/ci.yml"],
        "test_summary": "targeted test passed",
        "draft_pr_url": "https://github.com/acme/app/pull/7",
    }
    incomplete = build_proof_pack(repair=repair, job=job)
    assert incomplete["ready"] is False
    assert "draft_pr_head_sha_missing" in incomplete["blockers"]
    assert verify_proof_pack(incomplete) is False

    complete = build_proof_pack(
        repair=repair,
        job=job,
        pr_evidence={
            "url": job["draft_pr_url"],
            "headSha": HEAD_SHA,
            "ciHeadShaMatch": True,
            "ciGreen": True,
            "checks": [
                {
                    "name": "quality",
                    "status": "completed",
                    "conclusion": "success",
                    "headSha": HEAD_SHA,
                }
            ],
        },
    )
    assert complete["ready"] is True
    assert verify_proof_pack(complete) is True


def test_proof_pack_fails_closed_when_secret_material_was_redacted() -> None:
    pack = build_proof_pack(
        repair={
            "repair_id": "repair-1",
            "repository": "https://github.com/acme/app",
            "failure_family": "github_actions_ci",
            "base_sha": BASE_SHA,
            "published_head_sha": HEAD_SHA,
        },
        job={
            "changed_files": [".github/workflows/ci.yml"],
            "test_summary": "Authorization: Bearer github_pat_" + "x" * 30,
            "draft_pr_url": "https://github.com/acme/app/pull/7",
        },
        pr_evidence={
            "headSha": HEAD_SHA,
            "ciHeadShaMatch": True,
            "ciGreen": True,
            "checks": [],
        },
    )
    assert pack["ready"] is False
    assert "secret_material_redacted" in pack["blockers"]
    assert verify_proof_pack(pack) is False


def test_proof_pack_keeps_the_full_changed_file_set_and_blocks_over_limit() -> None:
    changed_files = [f"backend/change_{index}.py" for index in range(MAX_REPAIR_CHANGED_FILES + 1)]
    pack = build_proof_pack(
        repair={
            "repair_id": "repair-limit",
            "repository": "https://github.com/acme/app",
            "failure_family": "github_actions_ci",
            "base_sha": BASE_SHA,
            "published_head_sha": HEAD_SHA,
        },
        job={
            "changed_files": changed_files,
            "test_summary": "targeted tests passed",
            "draft_pr_url": "https://github.com/acme/app/pull/8",
        },
        pr_evidence={
            "headSha": HEAD_SHA,
            "ciHeadShaMatch": True,
            "ciGreen": True,
            "checks": [],
        },
    )
    assert pack["changedFiles"] == changed_files
    assert pack["changedFileCount"] == MAX_REPAIR_CHANGED_FILES + 1
    assert f"changed_file_limit_exceeded:{MAX_REPAIR_CHANGED_FILES + 1}>{MAX_REPAIR_CHANGED_FILES}" in pack["blockers"]
    assert pack["ready"] is False
    assert verify_proof_pack(pack) is False


def test_proof_pack_requires_the_current_pr_head_to_match_published_commit() -> None:
    pack = build_proof_pack(
        repair={
            "repair_id": "repair-head",
            "repository": "https://github.com/acme/app",
            "failure_family": "github_actions_ci",
            "base_sha": BASE_SHA,
            "published_head_sha": HEAD_SHA,
        },
        job={
            "changed_files": [".github/workflows/ci.yml"],
            "test_summary": "targeted tests passed",
            "draft_pr_url": "https://github.com/acme/app/pull/9",
        },
        pr_evidence={
            "headSha": "c" * 40,
            "ciHeadShaMatch": True,
            "ciGreen": True,
            "checks": [],
        },
    )
    assert "draft_pr_head_changed_after_publication" in pack["blockers"]
    assert pack["ready"] is False


def test_rescue_csrf_token_is_user_origin_and_time_bound() -> None:
    secret = "s" * 48
    token = issue_rescue_csrf_token(
        user_id="user-1",
        origin="https://studio.example.test",
        secret=secret,
        now=1_000,
    )
    assert verify_rescue_csrf_token(
        token,
        user_id="user-1",
        origin="https://studio.example.test",
        secret=secret,
        now=1_200,
    ) is True
    assert verify_rescue_csrf_token(
        token,
        user_id="user-2",
        origin="https://studio.example.test",
        secret=secret,
        now=1_200,
    ) is False
    assert verify_rescue_csrf_token(
        token,
        user_id="user-1",
        origin="https://evil.example.test",
        secret=secret,
        now=1_200,
    ) is False
    assert verify_rescue_csrf_token(
        token,
        user_id="user-1",
        origin="https://studio.example.test",
        secret=secret,
        now=1_700,
    ) is False
