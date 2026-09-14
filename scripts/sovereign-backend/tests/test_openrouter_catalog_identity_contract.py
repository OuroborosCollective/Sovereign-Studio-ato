"""Pure source-contract regressions; no provider, database or Flask stand-ins.

The paired SQL replay is executed separately against real preview PostgreSQL.
Neither these tests nor that isolated replay claim production provider readiness.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
SOURCE = (BACKEND / "openrouter_provider_runtime.py").read_text("utf-8")
TREE = ast.parse(SOURCE)


def _function(name: str) -> ast.FunctionDef:
    return next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == name)


def _sql(name: str) -> list[str]:
    return [
        node.value
        for node in ast.walk(_function(name))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and any(word in node.value for word in ("SELECT ", "INSERT INTO ", "UPDATE "))
    ]


def _route_id():
    # Execute the actual dependency-free function body, not a rewritten algorithm.
    module = ast.Module(body=[_function("_route_id")], type_ignores=[])
    namespace = {
        "hashlib": hashlib,
        "OPENROUTER_DEFAULT_MODEL": "openai/gpt-5.4-mini",
        "OPENROUTER_ROOT_ROUTE_ID": "openrouter-paid-gpt-5-4-mini",
    }
    exec(compile(ast.fix_missing_locations(module), "openrouter_provider_runtime.py", "exec"), namespace)
    return namespace["_route_id"]


@pytest.mark.parametrize("model", ["openai/gpt-5.4-mini", "inclusionai/ling-2.6-flash", "vendor/new-default"])
def test_model_identity_does_not_change_when_canary_default_rotates(model: str) -> None:
    route_id = _route_id()
    expected = "openrouter-paid-" + hashlib.sha256(model.encode()).hexdigest()[:32]
    assert route_id(model, default_model=model) == expected
    assert route_id(model, default_model="vendor/other") == expected
    assert expected != "openrouter-paid-gpt-5-4-mini"


def test_catalog_upsert_preserves_existing_primary_identity() -> None:
    upsert = next(sql for sql in _sql("_sync_catalog") if "INSERT INTO llm_routes" in sql)
    assert "ON CONFLICT (model_id) DO UPDATE SET" in upsert
    updates = upsert.split("DO UPDATE SET", 1)[1]
    assert "model_id=EXCLUDED.model_id" not in updates
    assert "id=EXCLUDED.id" not in updates
    assert "disabled=false" in updates


def test_retirement_is_limited_to_owned_paid_catalog_rows() -> None:
    retirement = next(sql for sql in _sql("_sync_catalog") if "SET disabled=true" in sql)
    assert "model_id LIKE 'sovereign-openrouter:%%'" in retirement
    assert "NOT (model_id = ANY(%s))" in retirement
    assert "lower(COALESCE(runtime_kind, provider))='openrouter'" in retirement
    assert not "sovereign-openrouter-free".startswith("sovereign-openrouter:")


def test_paid_status_counts_only_selectable_owned_paid_models() -> None:
    status_sql = _sql("_openrouter_status_payload")[0]
    assert "route.model_id LIKE 'sovereign-openrouter:%%'" in status_sql
    assert "COALESCE(route.config->>'selectable', 'false')='true'" in status_sql
    assert "route.disabled=false" in status_sql


def test_paid_catalog_readers_exclude_dedicated_free_route() -> None:
    registration = _function("register_openrouter_provider_runtime")
    for name in ("admin_openrouter_models", "user_openrouter_models"):
        node = next(n for n in registration.body if isinstance(n, ast.FunctionDef) and n.name == name)
        queries = [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str) and "FROM llm_routes" in n.value]
        assert len(queries) == 1
        assert "model_id LIKE 'sovereign-openrouter:%%'" in queries[0]


def test_legacy_registry_replay_cannot_disable_current_provider_routes() -> None:
    migration = (BACKEND / "migrations/021_litellm_provider_registry.sql").read_text("utf-8")
    executable = "\n".join(line for line in migration.splitlines() if not line.lstrip().startswith("--"))
    assert "SET disabled" not in executable
    assert "SET config" not in executable
