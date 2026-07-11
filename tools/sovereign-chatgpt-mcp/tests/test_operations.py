from __future__ import annotations

import hashlib
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


def test_verified_backfill_runs_rollback_preview_then_admin_apply(tmp_path, monkeypatch) -> None:
    sql = "-- additive\nBEGIN;\nUPDATE llm_routes SET model_id = model WHERE model_id IS NULL;\nCOMMIT;\n"
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
    monkeypatch.setenv("SOVEREIGN_MCP_PREVIEW_POSTGRES_HOST", "db")
    monkeypatch.setenv("SOVEREIGN_MCP_PREVIEW_POSTGRES_PORT", "5432")
    monkeypatch.setenv("SOVEREIGN_MCP_PREVIEW_POSTGRES_DB", "sovereign_migration_preview")
    monkeypatch.setenv("SOVEREIGN_MCP_PREVIEW_POSTGRES_USER", "sovereign_mcp_preview")
    monkeypatch.setenv("SOVEREIGN_MCP_PREVIEW_POSTGRES_PASSWORD", "preview-secret")
    runtime = OperationsRuntime()
    calls = []

    def fake_run_input(argv, input_text, *, password, timeout):
        calls.append({"argv": argv, "input": input_text, "password": password, "timeout": timeout})
        return {"ok": True, "exit_code": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(runtime, "_run_input", fake_run_input)
    result = runtime.apply_verified_migration(
        workspace_id=workspace_id,
        path=relative_path,
        confirmation_sha256=checksum,
    )
    assert result["status"] == "APPLIED"
    assert result["preview"] == {"ok": True, "rolled_back": True}
    assert result["data_backfill_actions"] == ["update_rows"]
    assert len(calls) == 2
    assert calls[0]["password"] == "preview-secret"
    assert "ROLLBACK;" in calls[0]["input"]
    assert "COMMIT;" not in calls[0]["input"]
    assert calls[1]["password"] == "admin-secret"
    assert calls[1]["input"] == sql


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
