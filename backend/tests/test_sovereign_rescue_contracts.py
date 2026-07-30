from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent_runtime.rescue import (
    REPAIR_PACK_CREDITS,
    build_free_diagnosis,
    build_proof_pack,
    claim_repair_execution,
    entitlement_payload,
    read_github_pr_evidence,
    redact_secret_text,
    resolve_account_entitlement,
    verify_proof_pack,
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


def test_requested_family_without_verified_path_evidence_fails_closed() -> None:
    result = diagnose("GitHub Actions failed.", requested_family="github_actions_ci")
    assert result["ok"] is False
    assert result["supported"] is True
    assert result["affectedFiles"] == []
    assert result["blocker"] == "repository_evidence_missing"
    assert "outcomeContract" not in result


def test_free_diagnosis_redacts_secrets_and_never_reflects_raw_evidence() -> None:
    secret = "github_pat_" + "x" * 30
    redacted = redact_secret_text(f"Authorization: Bearer {secret}\npassword=hunter2")
    assert secret not in redacted
    assert "hunter2" not in redacted
    result = diagnose(f"GitHub Actions failed. Authorization: Bearer {secret}")
    assert secret not in str(result)
    assert "evidenceText" not in result


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

    depleted = {**purchased, "credits": REPAIR_PACK_CREDITS - 1}
    depleted_payload = entitlement_payload(
        depleted,
        resolve_account_entitlement(depleted),
    )
    assert depleted_payload["entitled"] is False
    assert depleted_payload["checkout"]["required"] is True

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
            "draft": True,
            "ciHeadShaMatch": True,
            "ciGreen": True,
            "requiredChecksKnown": True,
            "requiredChecksPresent": True,
            "requiredChecks": ["quality"],
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
            "draft": True,
            "ciHeadShaMatch": True,
            "ciGreen": True,
            "requiredChecksKnown": True,
            "requiredChecksPresent": True,
            "requiredChecks": [],
            "checks": [],
        },
    )
    assert pack["ready"] is False
    assert "secret_material_redacted" in pack["blockers"]
    assert verify_proof_pack(pack) is False


def test_proof_pack_rejects_non_draft_mismatched_or_oversized_publication() -> None:
    pack = build_proof_pack(
        repair={
            "repair_id": "repair-1",
            "repository": "https://github.com/acme/app",
            "failure_family": "github_actions_ci",
            "base_sha": BASE_SHA,
            "published_head_sha": "c" * 40,
        },
        job={
            "changed_files": [f"src/file_{index}.ts" for index in range(13)],
            "test_summary": "targeted tests passed",
            "draft_pr_url": "https://github.com/acme/app/pull/7",
        },
        pr_evidence={
            "headSha": HEAD_SHA,
            "draft": False,
            "ciHeadShaMatch": True,
            "ciGreen": True,
            "requiredChecksKnown": True,
            "requiredChecksPresent": True,
            "checks": [],
        },
    )
    assert pack["ready"] is False
    assert "changed_file_limit_exceeded" in pack["blockers"]
    assert "draft_pr_not_draft" in pack["blockers"]
    assert "published_head_sha_mismatch" in pack["blockers"]
    assert len(pack["changedFiles"]) == 12
    assert verify_proof_pack(pack) is False


def test_pr_evidence_requires_failing_legacy_status_even_with_green_check() -> None:
    class Response:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    def opener(request, timeout=30):
        del timeout
        url = request.full_url
        if "/pulls/7" in url:
            return Response({
                "draft": True,
                "head": {"sha": HEAD_SHA},
                "base": {"ref": "main"},
            })
        if "/check-runs" in url:
            return Response({
                "check_runs": [{
                    "name": "required-ci",
                    "status": "completed",
                    "conclusion": "success",
                    "head_sha": HEAD_SHA,
                }],
            })
        if "/commits/" in url and "/status" in url:
            return Response({
                "statuses": [{
                    "context": "required-ci",
                    "state": "failure",
                }],
            })
        if "/branches/main" in url:
            return Response({
                "protected": True,
                "protection": {
                    "required_status_checks": {
                        "contexts": ["required-ci"],
                        "checks": [],
                    },
                },
            })
        if "/rules/branches/main" in url:
            return Response([])
        raise AssertionError(f"Unexpected GitHub request: {url}")

    evidence = read_github_pr_evidence(
        "https://github.com/acme/app/pull/7",
        opener=opener,
    )
    assert evidence["requiredChecksKnown"] is True
    assert evidence["requiredChecksPresent"] is True
    assert evidence["ciHeadShaMatch"] is True
    assert evidence["ciGreen"] is False
    assert evidence["statuses"] == [{"context": "required-ci", "state": "failure"}]


class ClaimCursor:
    def __init__(self, conn):
        self.conn = conn
        self.result = None

    def execute(self, sql, params):
        del params
        normalized = " ".join(sql.split())
        if normalized.startswith("UPDATE sovereign_rescue_repairs"):
            if self.conn.row["state"] == "reserved":
                self.conn.row["state"] = "running"
                self.result = dict(self.conn.row)
            else:
                self.result = None
        elif normalized.startswith("SELECT repair_id::text"):
            self.result = dict(self.conn.row)

    def fetchone(self):
        return self.result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class ClaimConnection:
    def __init__(self, state):
        self.row = {
            "repair_id": "repair-1",
            "job_id": "agent-1",
            "run_id": None,
            "state": state,
            "charged_credits": 10,
            "blocker": "classified_failure" if state == "blocked" else None,
        }
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return ClaimCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_repair_execution_claim_resumes_reserved_retry_once() -> None:
    conn = ClaimConnection("reserved")
    result = claim_repair_execution(
        conn,
        user_id="11111111-1111-4111-8111-111111111111",
        repair_id="22222222-2222-4222-8222-222222222222",
    )
    assert result["claimed"] is True
    assert result["state"] == "running"
    assert conn.commits == 1
    assert conn.rollbacks == 0


def test_repair_execution_claim_classifies_blocked_retry_without_execution() -> None:
    conn = ClaimConnection("blocked")
    result = claim_repair_execution(
        conn,
        user_id="11111111-1111-4111-8111-111111111111",
        repair_id="22222222-2222-4222-8222-222222222222",
    )
    assert result["claimed"] is False
    assert result["state"] == "blocked"
    assert result["blocker"] == "classified_failure"
    assert conn.commits == 0
    assert conn.rollbacks == 1


def test_hardening_migration_is_additive_ordered_and_mirrored() -> None:
    canonical = (
        ROOT / "backend/migrations/046_sovereign_rescue_hardening.sql"
    ).read_text("utf-8")
    deploy = (
        ROOT / "scripts/sovereign-backend/migrations/046_sovereign_rescue_hardening.sql"
    ).read_text("utf-8")
    assert canonical == deploy
    assert canonical.startswith("BEGIN;")
    assert canonical.rstrip().endswith("COMMIT;")
    assert "ADD COLUMN IF NOT EXISTS published_head_sha" in canonical
    assert "sovereign_rescue_published_head_sha_check" in canonical
    assert "DROP " not in canonical.upper()
