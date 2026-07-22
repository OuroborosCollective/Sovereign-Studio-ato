from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
SCRIPT_BACKEND = ROOT / "scripts" / "sovereign-backend"


def test_changed_python_surfaces_parse_without_importing_runtime_dependencies() -> None:
    paths = [
        BACKEND / "llm_transport.py",
        BACKEND / "llm_execution_resolver.py",
        BACKEND / "llm_revolver.py",
        BACKEND / "agent_runtime" / "cognitive_llm_transport.py",
        BACKEND / "agent_runtime" / "cognitive_swarm_agents.py",
        BACKEND / "agent_runtime" / "cognitive_swarm_routes.py",
        BACKEND / "agent_runtime" / "cognitive_usage_billing.py",
        SCRIPT_BACKEND / "app.py",
        SCRIPT_BACKEND / "controller_board.py",
        SCRIPT_BACKEND / "free_revolver_provider_runtime.py",
        SCRIPT_BACKEND / "llm_provider_runtime.py",
        SCRIPT_BACKEND / "openrouter_provider_runtime.py",
        SCRIPT_BACKEND / "owner_input_runtime.py",
    ]
    for path in paths:
        ast.parse(path.read_text("utf-8"), filename=str(path))


def test_deployed_backend_mirrors_are_byte_identical() -> None:
    relative_paths = [
        "llm_transport.py",
        "llm_execution_resolver.py",
        "llm_revolver.py",
        "agent_runtime/cognitive_llm_transport.py",
        "agent_runtime/cognitive_swarm_agents.py",
        "agent_runtime/cognitive_swarm_routes.py",
        "agent_runtime/cognitive_usage_billing.py",
    ]
    for relative in relative_paths:
        assert (BACKEND / relative).read_bytes() == (SCRIPT_BACKEND / relative).read_bytes()


def test_paid_model_pair_and_free_forced_fallback_are_wired_through_user_routes() -> None:
    routes = (BACKEND / "agent_runtime" / "cognitive_swarm_routes.py").read_text("utf-8")

    assert 'main_model=str(body.get("mainModel") or "") or None' in routes
    assert 'agent_model=str(body.get("agentModel") or "") or None' in routes
    assert 'resolver_mode = "free" if _force_free_profile else normalized_mode' in routes
    assert "main_route=execution_resolution.primary_route" in routes
    assert "agent_route=execution_resolution.agent_route" in routes
    assert '"resolvedMainModelId": resolved_model' in routes
    assert '"resolvedAgentModelId": resolved_agent_model' in routes
    assert '"sixAgentModelShared": True' in routes


def test_secret_and_provider_boundaries_are_fail_closed() -> None:
    transport = (
        BACKEND / "agent_runtime" / "cognitive_llm_transport.py"
    ).read_text("utf-8")
    free_runtime = (
        SCRIPT_BACKEND / "free_revolver_provider_runtime.py"
    ).read_text("utf-8")
    openrouter = (
        SCRIPT_BACKEND / "openrouter_provider_runtime.py"
    ).read_text("utf-8")

    assert "protected[index] = 0" in transport
    assert '"provider": _openrouter_policy(route)' in transport
    assert "litellm_completion_canary" not in free_runtime
    assert "_direct_completion_canary(" in free_runtime
    assert "route_priority = 10 if model_id == OPENROUTER_DEFAULT_MODEL" in openrouter
    assert '"allow_fallbacks": False' in openrouter
    assert '"data_collection": "deny"' in openrouter
    assert '"zdr": True' in openrouter


def test_additive_migration_keeps_transports_disjoint() -> None:
    migration = (
        SCRIPT_BACKEND / "migrations" / "033_openrouter_paid_freellm_direct.sql"
    ).read_text("utf-8")

    assert "provider = 'freellm'" in migration
    assert "'openrouter'" in migration
    assert "execution_role" in migration
    assert "quota_remaining" in migration
    assert "quota_reset_at" in migration
    assert "DELETE FROM llm_routes" not in migration
    assert "COALESCE(llm_provider_deployments.markup_multiplier, 4)" in migration
    assert "VALUES (33, 'openrouter_paid_freellm_direct')" in migration
