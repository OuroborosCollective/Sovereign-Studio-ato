from __future__ import annotations

import copy
import subprocess
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

import database_evidence_tools as db_evidence
from output_contracts import install_output_contracts


REVISION = "a" * 40
OTHER_REVISION = "b" * 40
ZERO = "0" * 64


class FakeBroker:
    def __init__(self, revision: str = REVISION) -> None:
        self.revision = revision
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, action: str, arguments: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
        self.calls.append((action, arguments))
        assert action == "mcp_self_update_status"
        return {
            "ok": True,
            "status": "UPDATED",
            "revision": self.revision,
            "revision_verified": True,
            "image_digest_verified": True,
            "mcp_protocol_ready": True,
            "broker_rpc_ready": True,
        }


class FakeDatabase:
    def __init__(self) -> None:
        self.canary_calls = 0
        self.preview_calls = 0

    def canary(self) -> dict[str, Any]:
        self.canary_calls += 1
        return {
            "ok": True,
            "status": "POSTGRES_CANARY_OK",
            "value": 1,
            "database": "sovereign",
            "user": "sovereign_owner",
        }

    def schema_inventory(self) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "POSTGRES_SCHEMA_INVENTORY",
            "tableCount": 1,
            "tables": [{"table_schema": "public", "table_name": "agent_runs"}],
            "rowDataReturned": False,
            "secretValuesExposed": False,
        }

    def schema_contract_inventory(self, table_names: list[str]) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "POSTGRES_SCHEMA_CONTRACT_INVENTORY",
            "requestedTables": sorted(table_names),
            "tables": [{"table": name, "columns": [], "constraints": [], "indexes": []} for name in sorted(table_names)],
            "missingTables": [],
            "rowDataReturned": False,
            "secretValuesExposed": False,
        }

    def vector_canary(self) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "VECTOR_CANARY_OK",
            "extension_version": "0.8.0",
            "vector_columns": [],
        }

    def preview_migration(self, workspace_id: str, path: str) -> dict[str, Any]:
        self.preview_calls += 1
        return {
            "ok": True,
            "status": "POSTGRES_MIGRATION_PREVIEW_OK",
            "rolled_back": True,
            "sha256": "c" * 64,
            "database_scope": "preview",
            "workspace_id": workspace_id,
            "path": path,
        }


class FakeRuntime:
    def __init__(self, repo: Path) -> None:
        self.repo = repo

    def _repo(self, workspace_id: str) -> Path:
        assert workspace_id == "job-test"
        return self.repo


def bind(repo: Path | None = None, *, revision: str = REVISION) -> tuple[FakeDatabase, FakeBroker]:
    database = FakeDatabase()
    broker = FakeBroker(revision)
    db_evidence._DATABASE = database
    db_evidence._BROKER = broker
    db_evidence._RUNTIME = FakeRuntime(repo) if repo is not None else object()
    return database, broker


def init_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    (repo / "backend" / "migrations").mkdir(parents=True)
    (repo / "backend" / "migrations" / "001.sql").write_text(
        "CREATE TABLE evidence_receipts (receipt_sha256 text primary key);\n",
        "utf-8",
    )
    (repo / "tools").mkdir()
    (repo / "tools" / "database.py").write_text("import psycopg2\n", "utf-8")
    (repo / ".env.production").write_text("POSTGRES_PASSWORD=must-not-be-read\n", "utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)
    return repo


def test_skill_inventory_rejects_archive_truth_gaps() -> None:
    result = db_evidence.database_evidence_skill_inventory()

    assert result.ok is True
    assert result.boundaries["genericSqlPathAdded"] is False
    assert result.boundaries["mockTracerUsed"] is False
    assert "simulated PostgreSQL and MySQL success" in result.source_material_use["rejected"]
    assert len(result.tools) == 5


def test_architecture_inventory_maps_tracked_db_surfaces_without_env_content(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    bind(repo)

    result = db_evidence.database_evidence_architecture_inventory("job-test")

    assert result.ok is True
    assert result.revision == subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    assert "postgresql" in result.database_families
    assert all(surface.path != ".env.production" for surface in result.surfaces)
    assert any(surface.kind == "migration" for surface in result.surfaces)
    assert result.runtime_success_claimed is False


def test_postgres_read_is_revision_bound_and_receipt_is_deterministic() -> None:
    database, _ = bind()

    first = db_evidence.postgres_evidence_read(
        operation="postgres_canary",
        expected_revision=REVISION,
    )
    second = db_evidence.postgres_evidence_read(
        operation="postgres_canary",
        expected_revision=REVISION,
    )

    assert first.ok is True
    assert first.revision_verified is True
    assert first.receipt is not None
    assert second.receipt is not None
    assert first.receipt.header.hash == second.receipt.header.hash
    assert first.receipt.body.previous_receipt_sha256 == ZERO
    assert first.receipt.body.observed_effect == "read"
    assert first.receipt.body.revision == REVISION
    assert database.canary_calls == 2


def test_revision_mismatch_blocks_before_database_call() -> None:
    database, _ = bind(revision=OTHER_REVISION)

    result = db_evidence.postgres_evidence_read(
        operation="postgres_canary",
        expected_revision=REVISION,
    )

    assert result.ok is False
    assert result.status == "BLOCKED_REVISION_MISMATCH"
    assert result.receipt is None
    assert database.canary_calls == 0


def test_migration_preview_requires_real_rollback_marker() -> None:
    database, _ = bind()

    result = db_evidence.postgres_evidence_migration_preview(
        workspace_id="job-test",
        path="backend/migrations/001.sql",
        expected_revision=REVISION,
    )

    assert result.ok is True
    assert result.receipt is not None
    assert result.receipt.body.operation == "postgres_migration_preview"
    assert result.receipt.body.observed_effect == "ephemeral-write"
    assert result.receipt.body.mutation_performed is False
    assert result.operation_result["rolled_back"] is True
    assert database.preview_calls == 1


def test_receipt_chain_verifier_detects_tampering() -> None:
    bind()
    first = db_evidence.postgres_evidence_read(
        operation="postgres_canary",
        expected_revision=REVISION,
    )
    assert first.receipt is not None
    second = db_evidence.postgres_evidence_read(
        operation="postgres_schema_inventory",
        expected_revision=REVISION,
        sequence=1,
        previous_receipt_sha256=first.receipt.header.hash,
    )
    assert second.receipt is not None

    verified = db_evidence.database_evidence_receipt_verify(
        [first.receipt, second.receipt],
        expected_revision=REVISION,
    )
    assert verified.ok is True
    assert verified.verified_count == 2
    assert verified.chain_head_sha256 == second.receipt.header.hash

    tampered = copy.deepcopy(second.receipt)
    tampered.body.operation_identity = "postgres:tampered"
    invalid = db_evidence.database_evidence_receipt_verify(
        [first.receipt, tampered],
        expected_revision=REVISION,
    )
    assert invalid.ok is False
    assert any(item.family == "RECEIPT_HASH_MISMATCH" for item in invalid.findings)


def test_secret_shaped_payload_and_floats_fail_closed() -> None:
    try:
        db_evidence._sha256({"password": "not-returned"})
    except ValueError as exc:
        assert "secret-shaped" in str(exc)
    else:
        raise AssertionError("secret-shaped field must be rejected")

    try:
        db_evidence._sha256({"latency": 1.5})
    except ValueError as exc:
        assert "floating-point" in str(exc)
    else:
        raise AssertionError("float must be rejected")


def test_registered_tools_keep_strict_output_schemas(monkeypatch) -> None:
    monkeypatch.setattr(db_evidence, "_REGISTERED", False)
    mcp = FastMCP("db-evidence-schema-test")
    db_evidence.register(mcp, object(), object(), object())
    report = install_output_contracts(mcp)
    tools = {tool.name: tool for tool in mcp._tool_manager.list_tools()}

    assert report["ok"] is True
    assert set(tools) == {
        "database_evidence_skill_inventory",
        "database_evidence_architecture_inventory",
        "postgres_evidence_read",
        "postgres_evidence_migration_preview",
        "database_evidence_receipt_verify",
    }
    for tool in tools.values():
        assert tool.output_schema["type"] == "object"
        assert tool.output_schema["required"]
        assert "schemaVersion" in tool.output_schema["required"]
        assert "secretValuesReturned" in tool.output_schema["required"]
