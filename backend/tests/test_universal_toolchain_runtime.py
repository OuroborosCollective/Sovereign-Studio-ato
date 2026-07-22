from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
DEPLOY = ROOT / "scripts" / "sovereign-backend"
sys.path.insert(0, str(BACKEND))

from agent_runtime import universal_toolchain as runtime


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_backend_and_deployment_runtime_are_exact_mirrors() -> None:
    assert read(BACKEND / "agent_runtime" / "universal_toolchain.py") == read(
        DEPLOY / "agent_runtime" / "universal_toolchain.py"
    )
    assert read(BACKEND / "agent_runtime" / "routes.py") == read(
        DEPLOY / "agent_runtime" / "routes.py"
    )


def test_diagnosis_detects_real_families_and_returns_exactly_four_followups() -> None:
    evidence = (
        "ModuleNotFoundError: No module named flask\n"
        "TypeScript TS2339: Property packages does not exist\n"
        "Playwright browser executable missing\n"
        "GitHub Draft PR returned 403"
    )
    result = runtime.runtime_failure_diagnose(evidence, mission="Fix the full runtime path")

    codes = {item["code"] for item in result["failureFamilies"]}
    assert "dependency_runtime_missing" in codes
    assert "typescript_contract_mismatch" in codes
    assert "playwright_runtime_missing" in codes
    assert "github_access_or_scope" in codes
    assert len(result["nextLogicalFailures"]) == 4
    assert result["policy"]["pushToMain"] is False
    assert result["policy"]["draftPrOnly"] is True


def test_diagnosis_never_reflects_raw_evidence_or_secret_like_text() -> None:
    marker = "github_pat_DO_NOT_REFLECT_123456789"
    result = runtime.runtime_failure_diagnose(
        f"Authorization: Bearer {marker}\nEmbedding proxy returned HTTP 404"
    )
    serialized = json.dumps(result, ensure_ascii=False)

    assert marker not in serialized
    assert "Authorization: Bearer" not in serialized
    assert result["logsReflected"] is False
    assert len(result["evidenceHash"]) == 64


def test_manifest_exposes_only_policy_guarded_embedded_capabilities() -> None:
    manifest = runtime.toolchain_manifest()
    names = {tool["name"] for tool in manifest["tools"]}

    assert manifest["runtime"] == "embedded"
    assert "runtime_failure_diagnose" in names
    assert "policy_guarded_rollback_preview" in names
    assert "agent_toolchain_handoff" in names
    assert manifest["policy"] == {
        "autoLoad": True,
        "pushToMain": False,
        "draftPrOnly": True,
        "confirmRequired": True,
        "arbitraryShell": False,
        "directProductionRunner": False,
        "directGithubToken": False,
        "auditEvidence": True,
    }


def test_rollback_preview_masks_plpgsql_and_preserves_original_sha() -> None:
    migration = """BEGIN;
DO $$
BEGIN
  PERFORM 1;
END $$;
CREATE TABLE IF NOT EXISTS sample(id integer);
COMMIT;
"""
    expected = runtime.sha256_text(migration)
    result = runtime.validate_migration_for_rollback_preview(
        migration,
        expected_sha256=expected,
        repair_attempt=1,
    )

    assert result["ok"] is True
    assert result["originalMigrationUnchanged"] is True
    assert result["originalSha256"] == expected
    assert len(result["maskedPlpgsqlBlocks"]) == 1
    assert [item["keyword"] for item in result["topLevelTransactions"]] == ["BEGIN", "COMMIT"]
    assert result["productionWrite"] is False


def test_rollback_preview_blocks_sha_drift_and_unbounded_repair() -> None:
    migration = "BEGIN; SELECT 1; COMMIT;"
    assert runtime.validate_migration_for_rollback_preview(
        migration,
        expected_sha256="0" * 64,
    )["ok"] is False
    assert runtime.validate_migration_for_rollback_preview(
        migration,
        repair_attempt=runtime.MAX_AUTO_REPAIR_ATTEMPTS + 1,
    )["ok"] is False


def test_routes_handoff_to_existing_agent_and_keep_draft_pr_separate() -> None:
    routes = read(BACKEND / "agent_runtime" / "routes.py")
    app_source = read(DEPLOY / "app.py")

    assert '/api/user/agent/toolchain/handoff' in routes
    assert "create_sovereign_agent_job(" in routes
    assert "persist_toolchain_incident(" in routes
    assert "persist_toolchain_handoff(" in routes
    assert '/draft-pr/prepare' in routes
    assert '/draft-pr/create' in routes
    assert "dispatch_embedded_tool" in app_source
    assert "Use /api/user/agent/toolchain/handoff" in app_source


def test_migration_stores_hashes_and_metadata_but_not_raw_logs() -> None:
    migration = read(DEPLOY / "migrations" / "015_universal_toolchain_runtime.sql")

    assert "sovereign_toolchain_incidents" in migration
    assert "sovereign_toolchain_handoffs" in migration
    assert "mission_hash CHAR(64)" in migration
    assert "evidence_hash CHAR(64)" in migration
    assert "raw_log" not in migration.lower()
    assert "github_token" not in migration.lower()
    assert "ON DELETE CASCADE" in migration


def test_handoff_context_contains_four_predictive_checks_and_hard_policy() -> None:
    handoff = runtime.build_agent_handoff_context(
        "Fix the frontend TypeScript error and deliver a Draft PR",
        "TS2339 Property paymentMethods does not exist",
    )
    mission = handoff["mission"]

    assert len(handoff["diagnosis"]["nextLogicalFailures"]) == 4
    assert "Four logical neighbouring failures to verify:" in mission
    assert "no direct main write" in mission
    assert "Draft PR only" in mission
