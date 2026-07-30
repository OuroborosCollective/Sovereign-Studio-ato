from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_BACKEND = ROOT / "scripts" / "sovereign-backend"
BACKEND = ROOT / "backend"


def test_rescue_runtime_and_migration_mirrors_are_byte_equal() -> None:
    for relative_path in (
        Path("agent_runtime/rescue.py"),
        Path("agent_runtime/routes.py"),
        Path("agent_runtime/draft_pr_create_gate.py"),
    ):
        assert (
            SCRIPT_BACKEND / relative_path
        ).read_bytes() == (
            BACKEND / relative_path
        ).read_bytes()
    assert (
        SCRIPT_BACKEND / "migrations" / "045_sovereign_rescue.sql"
    ).read_bytes() == (
        BACKEND / "migrations" / "045_sovereign_rescue.sql"
    ).read_bytes()


def test_rescue_migration_enforces_tenant_idempotency_and_bounded_states() -> None:
    migration = (
        SCRIPT_BACKEND / "migrations" / "045_sovereign_rescue.sql"
    ).read_text("utf-8")
    assert "UNIQUE (user_id, idempotency_key)" in migration
    assert "UNIQUE (job_id)" in migration
    assert "sovereign_rescue_family_check" in migration
    assert "sovereign_rescue_state_check" in migration
    assert "ADD COLUMN IF NOT EXISTS published_head_sha CHAR(40)" in migration
    assert "sovereign_rescue_published_head_sha_check" in migration
    assert "REFERENCES admin_users(id) ON DELETE CASCADE" in migration


def test_rescue_repair_reservation_is_locked_and_ledger_backed() -> None:
    runtime = (
        SCRIPT_BACKEND / "agent_runtime" / "rescue.py"
    ).read_text("utf-8")
    assert "pg_advisory_xact_lock" in runtime
    assert "FOR UPDATE" in runtime
    assert "credits = credits - %s" in runtime
    assert "INSERT INTO credit_ledger" in runtime
    assert "verified_purchase_required" in runtime


def test_changed_python_surfaces_parse_and_bind_the_existing_free_executor() -> None:
    paths = (
        SCRIPT_BACKEND / "agent_runtime" / "rescue.py",
        SCRIPT_BACKEND / "agent_runtime" / "routes.py",
        SCRIPT_BACKEND / "agent_runtime" / "job_lifecycle.py",
        SCRIPT_BACKEND / "agent_runtime" / "cognitive_swarm_routes.py",
        BACKEND / "agent_runtime" / "rescue.py",
        BACKEND / "agent_runtime" / "routes.py",
        BACKEND / "agent_runtime" / "job_lifecycle.py",
        BACKEND / "agent_runtime" / "cognitive_swarm_routes.py",
    )
    for path in paths:
        ast.parse(path.read_text("utf-8"), filename=str(path))

    cognitive = (
        SCRIPT_BACKEND / "agent_runtime" / "cognitive_swarm_routes.py"
    ).read_text("utf-8")
    routes = (
        SCRIPT_BACKEND / "agent_runtime" / "routes.py"
    ).read_text("utf-8")
    lifecycle = (
        SCRIPT_BACKEND / "agent_runtime" / "job_lifecycle.py"
    ).read_text("utf-8")
    assert "mode=\"free\"" in routes
    assert "intent_mode=\"repository_execution\"" in routes
    assert "repository_url=revision[\"repository\"]" in routes
    assert "expected_head_sha=revision[\"baseSha\"]" in routes
    assert "job_id=normalized_implementation_job_id" in cognitive
    assert "repository head changed after diagnosis" in lifecycle
