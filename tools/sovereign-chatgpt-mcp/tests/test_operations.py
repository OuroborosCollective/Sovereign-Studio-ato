from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from operations import OperationsRuntime


DIGEST = "sha256:" + "a" * 64
REVISION = "b" * 40


def test_deploy_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("SOVEREIGN_MCP_ENABLE_DEPLOY", raising=False)
    result = OperationsRuntime().deploy_verified_release(
        image_digest=DIGEST,
        expected_revision=REVISION,
        confirmation_revision=REVISION,
    )
    assert result["status"] == "BLOCKED"
    assert result["blocker"] == "Deploy-Writes sind nicht aktiviert"


def test_deploy_requires_exact_confirmation(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_DEPLOY", "1")
    result = OperationsRuntime().deploy_verified_release(
        image_digest=DIGEST,
        expected_revision=REVISION,
        confirmation_revision="c" * 40,
    )
    assert result["status"] == "BLOCKED"
    assert "Bestätigung" in result["blocker"]


def test_invalid_digest_never_reaches_script(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_DEPLOY", "1")
    with pytest.raises(ValueError, match="image_digest"):
        OperationsRuntime().deploy_verified_release(
            image_digest="latest",
            expected_revision=REVISION,
            confirmation_revision=REVISION,
        )


def test_failed_deploy_returns_only_bounded_diagnostic_marker(tmp_path, monkeypatch) -> None:
    script = tmp_path / "deploy-sovereign-backend"
    script.write_text("#!/usr/bin/env bash\n", "utf-8")
    script.chmod(0o750)
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_DEPLOY", "1")
    runtime = OperationsRuntime()
    runtime.deploy_script = script
    monkeypatch.setattr(
        runtime,
        "_run",
        lambda _script, _args: {
            "ok": False,
            "exit_code": 1,
            "stdout": "",
            "stderr": (
                "provider body and protected details\n"
                "SOVEREIGN_DEPLOY_DIAGNOSTIC:platform_identity:HTTPError\n"
            ),
        },
    )

    result = runtime.deploy_verified_release(
        image_digest=DIGEST,
        expected_revision=REVISION,
        confirmation_revision=REVISION,
    )

    assert result["status"] == "FAILED"
    assert result["diagnosticStage"] == "platform_identity"
    assert result["diagnosticErrorType"] == "HTTPError"
    assert "provider body" not in str(result)
    assert "stderr" not in result
    assert len(result["stderrSha256"]) == 64


def test_failed_deploy_preserves_causal_and_terminal_diagnostic_markers(tmp_path, monkeypatch) -> None:
    script = tmp_path / "deploy-sovereign-backend"
    script.write_text("#!/usr/bin/env bash\n", "utf-8")
    script.chmod(0o750)
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_DEPLOY", "1")
    runtime = OperationsRuntime()
    runtime.deploy_script = script
    monkeypatch.setattr(
        runtime,
        "_run",
        lambda _script, _args: {
            "ok": False,
            "exit_code": 1,
            "stdout": "",
            "stderr": (
                "SOVEREIGN_DEPLOY_DIAGNOSTIC:freellm_bootstrap_final_status:RuntimeError\n"
                "SOVEREIGN_DEPLOY_DIAGNOSTIC:admin_canary:ContractFailure\n"
            ),
        },
    )

    result = runtime.deploy_verified_release(
        image_digest=DIGEST,
        expected_revision=REVISION,
        confirmation_revision=REVISION,
    )

    assert result["diagnosticStage"] == "freellm_bootstrap_final_status"
    assert result["diagnosticErrorType"] == "RuntimeError"
    assert result["terminalDiagnosticStage"] == "admin_canary"
    assert result["terminalDiagnosticErrorType"] == "ContractFailure"
    assert result["diagnosticTrace"] == [
        {"stage": "freellm_bootstrap_final_status", "errorType": "RuntimeError"},
        {"stage": "admin_canary", "errorType": "ContractFailure"},
    ]


def test_failed_deploy_returns_early_shell_stage_without_raw_stderr(tmp_path, monkeypatch) -> None:
    script = tmp_path / "deploy-sovereign-backend"
    script.write_text("#!/usr/bin/env bash\n", "utf-8")
    script.chmod(0o750)
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_DEPLOY", "1")
    runtime = OperationsRuntime()
    runtime.deploy_script = script
    monkeypatch.setattr(
        runtime,
        "_run",
        lambda _script, _args: {
            "ok": False,
            "exit_code": 1,
            "stdout": "",
            "stderr": (
                "docker and protected environment details\n"
                "SOVEREIGN_DEPLOY_CANDIDATE:status=exited:exit=1:oom=false:"
                "lastMigration=050_bug_evidence_append_only.sql:"
                "logsSha256=" + "d" * 64 + "\n"
                "SOVEREIGN_DEPLOY_DIAGNOSTIC:candidate_health:CommandFailure\n"
            ),
        },
    )

    result = runtime.deploy_verified_release(
        image_digest=DIGEST,
        expected_revision=REVISION,
        confirmation_revision=REVISION,
    )

    assert result["status"] == "FAILED"
    assert result["diagnosticStage"] == "candidate_health"
    assert result["diagnosticErrorType"] == "CommandFailure"
    assert result["candidateStatus"] == "exited"
    assert result["candidateExitCode"] == 1
    assert result["candidateOOMKilled"] is False
    assert result["candidateLastMigration"] == "050_bug_evidence_append_only.sql"
    assert result["candidateLogsSha256"] == "d" * 64
    assert "protected environment" not in str(result)
    assert "stderr" not in result
    assert len(result["stderrSha256"]) == 64


def test_deploy_requires_structured_admin_and_rollback_readback(tmp_path, monkeypatch) -> None:
    script = tmp_path / "deploy-sovereign-backend"
    script.write_text("#!/usr/bin/env bash\n", "utf-8")
    script.chmod(0o750)
    previous_digest = "sha256:" + "c" * 64
    previous_revision = "d" * 40
    payload = {
        "ok": True,
        "status": "DEPLOYED_ADMIN_VERIFIED",
        "imageDigest": DIGEST,
        "revision": REVISION,
        "health": {
            "ok": True,
            "sourceRevision": REVISION,
            "imageDigest": DIGEST,
        },
        "adminCanary": {
            "ok": True,
            "status": "ENTERPRISE_ADMIN_LIVE_CANARY_VERIFIED",
            "sourceRevision": REVISION,
            "imageDigest": DIGEST,
            "secretValuesReturned": False,
        },
        "rollback": {
            "previousImageDigest": previous_digest,
            "previousRevision": previous_revision,
            "previewVerified": True,
            "receiptSha256": "e" * 64,
        },
        "readbackVerified": True,
    }
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_DEPLOY", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    runtime = OperationsRuntime()
    runtime.deploy_script = script
    monkeypatch.setattr(
        runtime,
        "_run",
        lambda _script, _args: {
            "ok": True,
            "exit_code": 0,
            "stdout": json.dumps(payload, sort_keys=True) + "\n",
            "stderr": "",
        },
    )

    result = runtime.deploy_verified_release(
        image_digest=DIGEST,
        expected_revision=REVISION,
        confirmation_revision=REVISION,
    )

    assert result["ok"] is True
    assert result["status"] == "DEPLOYED_ADMIN_VERIFIED"
    assert result["readbackVerified"] is True
    assert result["mutationPerformed"] is True
    assert result["ownerApproved"] is True
    assert result["actualRevision"] == REVISION
    assert result["rollback"]["previousImageDigest"] == previous_digest
    assert result["secretValuesReturned"] is False


def test_deploy_blocks_green_status_when_rollback_readback_is_missing(tmp_path, monkeypatch) -> None:
    script = tmp_path / "deploy-sovereign-backend"
    script.write_text("#!/usr/bin/env bash\n", "utf-8")
    script.chmod(0o750)
    payload = {
        "ok": True,
        "status": "DEPLOYED_ADMIN_VERIFIED",
        "imageDigest": DIGEST,
        "revision": REVISION,
        "health": {"ok": True, "sourceRevision": REVISION, "imageDigest": DIGEST},
        "adminCanary": {
            "ok": True,
            "status": "ENTERPRISE_ADMIN_LIVE_CANARY_VERIFIED",
            "sourceRevision": REVISION,
            "imageDigest": DIGEST,
            "secretValuesReturned": False,
        },
        "rollback": {"previewVerified": False},
        "readbackVerified": True,
    }
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_DEPLOY", "1")
    runtime = OperationsRuntime()
    runtime.deploy_script = script
    monkeypatch.setattr(
        runtime,
        "_run",
        lambda _script, _args: {
            "ok": True,
            "exit_code": 0,
            "stdout": json.dumps(payload) + "\n",
            "stderr": "",
        },
    )

    result = runtime.deploy_verified_release(
        image_digest=DIGEST,
        expected_revision=REVISION,
        confirmation_revision=REVISION,
    )

    assert result["ok"] is False
    assert result["status"] == "DEPLOYED_ADMIN_READBACK_INCOMPLETE"
    assert result["readbackVerified"] is False
    assert result["mutationPerformed"] is True


def test_rollback_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("SOVEREIGN_MCP_ENABLE_DEPLOY", raising=False)
    result = OperationsRuntime().rollback_release(
        target_image_digest=DIGEST,
        confirmation_digest=DIGEST,
    )
    assert result["status"] == "BLOCKED"


def _migration_workspace(tmp_path: Path, sql: str) -> tuple[str, str, str]:
    workspace_id = "job-123456abcdef"
    relative_path = "scripts/sovereign-backend/migrations/008.sql"
    migration = tmp_path / workspace_id / "repo" / relative_path
    migration.parent.mkdir(parents=True)
    migration.write_text(sql, "utf-8")
    checksum = hashlib.sha256(sql.encode()).hexdigest()
    return workspace_id, relative_path, checksum


def test_verified_migration_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("SOVEREIGN_MCP_ENABLE_DB_WRITES", raising=False)
    result = OperationsRuntime().apply_verified_migration(
        workspace_id="job-123456abcdef",
        path="migrations/008.sql",
        confirmation_sha256="0" * 64,
    )
    assert result["status"] == "BLOCKED"
    assert result["blocker"] == "Produktive DB-Writes sind nicht aktiviert"


def test_update_backfill_requires_separate_broker_gate(tmp_path, monkeypatch) -> None:
    sql = "UPDATE llm_routes SET model_id = model WHERE model_id IS NULL;\n"
    workspace_id, relative_path, checksum = _migration_workspace(tmp_path, sql)
    monkeypatch.setenv("SOVEREIGN_MCP_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_DB_WRITES", "1")
    monkeypatch.delenv("SOVEREIGN_MCP_ALLOW_DATA_BACKFILLS", raising=False)
    result = OperationsRuntime().apply_verified_migration(
        workspace_id=workspace_id,
        path=relative_path,
        confirmation_sha256=checksum,
    )
    assert result["status"] == "BLOCKED"
    assert result["blocker"] == "Daten-Backfills sind nicht separat aktiviert"
    assert result["data_backfill_actions"] == ["update_rows"]


def test_destructive_delete_remains_separately_blocked(tmp_path, monkeypatch) -> None:
    sql = "DELETE FROM knowledge_blocks WHERE content = '';\n"
    workspace_id, relative_path, checksum = _migration_workspace(tmp_path, sql)
    monkeypatch.setenv("SOVEREIGN_MCP_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_DB_WRITES", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ALLOW_DATA_BACKFILLS", "1")
    monkeypatch.delenv("SOVEREIGN_MCP_ALLOW_DESTRUCTIVE_MIGRATIONS", raising=False)
    result = OperationsRuntime().apply_verified_migration(
        workspace_id=workspace_id,
        path=relative_path,
        confirmation_sha256=checksum,
    )
    assert result["status"] == "BLOCKED"
    assert result["destructive_actions"] == ["delete_rows"]


def test_preview_hydrates_real_schema_without_copying_rows(tmp_path, monkeypatch) -> None:
    sql = "ALTER TABLE agent_events DROP CONSTRAINT IF EXISTS agent_events_source_check;\n"
    workspace_id, relative_path, checksum = _migration_workspace(tmp_path, sql)
    backend_env = tmp_path / "backend.env"
    backend_env.write_text(
        "POSTGRES_HOST=db\n"
        "POSTGRES_PORT=5432\n"
        "POSTGRES_DB=postgres\n"
        "POSTGRES_USER=postgres\n"
        "POSTGRES_PASSWORD=admin-secret\n",
        "utf-8",
    )
    monkeypatch.setenv("SOVEREIGN_MCP_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("SOVEREIGN_BACKEND_ENV_FILE", str(backend_env))
    monkeypatch.setenv("SOVEREIGN_MCP_PREVIEW_POSTGRES_HOST", "db")
    monkeypatch.setenv("SOVEREIGN_MCP_PREVIEW_POSTGRES_PORT", "5432")
    monkeypatch.setenv("SOVEREIGN_MCP_PREVIEW_POSTGRES_DB", "sovereign_migration_preview")
    runtime = OperationsRuntime()
    calls = []
    dump_calls = []
    schema_sql = "CREATE TABLE public.agent_events(event_id text PRIMARY KEY, source text NOT NULL);\n"

    def fake_run_input(argv, input_text, *, password, timeout):
        calls.append({"argv": argv, "input": input_text, "password": password, "timeout": timeout})
        return {"ok": True, "exit_code": 0, "stdout": "", "stderr": ""}

    def fake_run_capture(argv, *, password, timeout, max_stdout_bytes):
        dump_calls.append({
            "argv": argv,
            "password": password,
            "timeout": timeout,
            "max_stdout_bytes": max_stdout_bytes,
        })
        return {
            "ok": True,
            "exit_code": 0,
            "stdout": schema_sql,
            "stdout_bytes": len(schema_sql.encode()),
            "stdout_sha256": hashlib.sha256(schema_sql.encode()).hexdigest(),
            "stderr_sha256": hashlib.sha256(b"").hexdigest(),
            "failure_family": None,
        }

    monkeypatch.setattr(runtime, "_run_input", fake_run_input)
    monkeypatch.setattr(runtime, "_run_capture", fake_run_capture)
    result = runtime.preview_verified_migration(
        workspace_id=workspace_id,
        path=relative_path,
        expected_sha256=checksum,
    )

    assert result["ok"] is True
    assert result["status"] == "PREVIEW_VERIFIED"
    assert result["rolled_back"] is True
    assert result["schema_hydrated"] is True
    assert result["schema_source"] == "production-schema-only"
    assert result["production_rows_copied"] is False
    assert result["production_write_performed"] is False
    assert result["preview_cleanup_verified"] is True
    assert len(dump_calls) == 1
    assert "--schema-only" in dump_calls[0]["argv"]
    assert "--no-owner" in dump_calls[0]["argv"]
    assert "--no-privileges" in dump_calls[0]["argv"]
    assert dump_calls[0]["argv"][-1] == "postgres"
    assert len(calls) == 4
    assert 'DROP DATABASE IF EXISTS "sovereign_migration_preview" WITH (FORCE);' in calls[0]["input"]
    assert 'CREATE DATABASE "sovereign_migration_preview"' in calls[0]["input"]
    assert calls[1]["input"] == schema_sql
    assert "ALTER TABLE agent_events" in calls[2]["input"]
    assert "ROLLBACK;" in calls[2]["input"]
    assert calls[3]["input"] == calls[0]["input"]


def test_preview_database_can_never_equal_production_database(tmp_path, monkeypatch) -> None:
    sql = "ALTER TABLE agent_events DROP CONSTRAINT IF EXISTS agent_events_source_check;\n"
    workspace_id, relative_path, checksum = _migration_workspace(tmp_path, sql)
    backend_env = tmp_path / "backend.env"
    backend_env.write_text(
        "POSTGRES_HOST=db\nPOSTGRES_PORT=5432\nPOSTGRES_DB=postgres\n"
        "POSTGRES_USER=postgres\nPOSTGRES_PASSWORD=admin-secret\n",
        "utf-8",
    )
    monkeypatch.setenv("SOVEREIGN_MCP_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("SOVEREIGN_BACKEND_ENV_FILE", str(backend_env))
    monkeypatch.setenv("SOVEREIGN_MCP_PREVIEW_POSTGRES_HOST", "db")
    monkeypatch.setenv("SOVEREIGN_MCP_PREVIEW_POSTGRES_PORT", "5432")
    monkeypatch.setenv("SOVEREIGN_MCP_PREVIEW_POSTGRES_DB", "postgres")
    runtime = OperationsRuntime()

    with pytest.raises(ValueError, match="niemals die Produktionsdatenbank"):
        runtime.preview_verified_migration(
            workspace_id=workspace_id,
            path=relative_path,
            expected_sha256=checksum,
        )


def test_verified_backfill_runs_hydrated_preview_then_admin_apply(tmp_path, monkeypatch) -> None:
    sql = """-- additive
BEGIN;
DO $$
BEGIN
    IF EXISTS (SELECT 1) THEN
        EXECUTE 'UPDATE llm_routes SET model_id = model WHERE model_id IS NULL';
    END IF;
END $$;
COMMIT;
"""
    workspace_id, relative_path, checksum = _migration_workspace(tmp_path, sql)
    backend_env = tmp_path / "backend.env"
    backend_env.write_text(
        "POSTGRES_HOST=db\n"
        "POSTGRES_PORT=5432\n"
        "POSTGRES_DB=postgres\n"
        "POSTGRES_USER=postgres\n"
        "POSTGRES_PASSWORD=admin-secret\n",
        "utf-8",
    )
    monkeypatch.setenv("SOVEREIGN_MCP_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("SOVEREIGN_BACKEND_ENV_FILE", str(backend_env))
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_DB_WRITES", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ALLOW_DATA_BACKFILLS", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ALLOW_DESTRUCTIVE_MIGRATIONS", "0")
    runtime = OperationsRuntime()
    calls = []

    def fake_run_input(argv, input_text, *, password, timeout):
        calls.append({"argv": argv, "input": input_text, "password": password, "timeout": timeout})
        return {"ok": True, "exit_code": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(runtime, "_run_input", fake_run_input)
    monkeypatch.setattr(
        runtime,
        "preview_verified_migration",
        lambda **_kwargs: {
            "ok": True,
            "status": "PREVIEW_VERIFIED",
            "rolled_back": True,
            "sha256": checksum,
            "schema_hydrated": True,
            "production_rows_copied": False,
        },
    )
    result = runtime.apply_verified_migration(
        workspace_id=workspace_id,
        path=relative_path,
        confirmation_sha256=checksum,
    )
    assert result["status"] == "APPLIED"
    assert result["preview"]["schema_hydrated"] is True
    assert result["data_backfill_actions"] == ["update_rows"]
    assert result["policy_repair"]["status"] == "APPLIED"
    assert result["policy_repair"]["scope"] == "preview_only"
    assert result["policy_repair"]["source_unchanged"] is True
    assert len(calls) == 1
    assert calls[0]["password"] == "admin-secret"
    assert calls[0]["input"] == sql


def test_migration_path_cannot_escape_workspace(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_DB_WRITES", "1")
    runtime = OperationsRuntime()
    with pytest.raises((ValueError, FileNotFoundError)):
        runtime.apply_verified_migration(
            workspace_id="job-123456abcdef",
            path="../../outside.sql",
            confirmation_sha256="0" * 64,
        )
