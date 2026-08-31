from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
PRODUCTION = ROOT / "scripts" / "sovereign-backend"


MIRROR_PAIRS = (
    (
        BACKEND / "agent_runtime" / "agent_zero_runtime.py",
        PRODUCTION / "agent_runtime" / "agent_zero_runtime.py",
    ),
    (
        BACKEND / "agent_runtime" / "cognitive_run_store.py",
        PRODUCTION / "agent_runtime" / "cognitive_run_store.py",
    ),
    (
        BACKEND / "agent_runtime" / "cognitive_swarm_agents.py",
        PRODUCTION / "agent_runtime" / "cognitive_swarm_agents.py",
    ),
    (
        BACKEND / "agent_runtime" / "cognitive_swarm_routes.py",
        PRODUCTION / "agent_runtime" / "cognitive_swarm_routes.py",
    ),
)


def test_agent_zero_runtime_and_swarm_modules_parse_as_python() -> None:
    for left, right in MIRROR_PAIRS:
        ast.parse(left.read_text("utf-8"), filename=str(left))
        ast.parse(right.read_text("utf-8"), filename=str(right))
    ast.parse((PRODUCTION / "owner_input_runtime.py").read_text("utf-8"))
    ast.parse((PRODUCTION / "app.py").read_text("utf-8"))


def test_agent_zero_production_mirrors_are_byte_equal() -> None:
    for backend_path, production_path in MIRROR_PAIRS:
        assert backend_path.read_bytes() == production_path.read_bytes(), (
            f"mirror drift: {backend_path.relative_to(ROOT)} != "
            f"{production_path.relative_to(ROOT)}"
        )


def test_agent_zero_is_evidence_source_but_not_run_or_task_authority() -> None:
    migration_path = PRODUCTION / "migrations" / "054_agent_zero_capability_evidence.sql"
    backend_migration_path = BACKEND / "migrations" / "054_agent_zero_capability_evidence.sql"
    migration = migration_path.read_text("utf-8")
    assert backend_migration_path.read_bytes() == migration_path.read_bytes()
    initial_schema = (
        PRODUCTION / "migrations" / "018_agents_sdk_runtime_state.sql"
    ).read_text("utf-8")
    store = (
        PRODUCTION / "agent_runtime" / "cognitive_run_store.py"
    ).read_text("utf-8")

    assert "agent_events_source_check" in migration
    assert "agent_evidence_source_check" in migration
    assert "'agent-zero'" in migration
    assert "agent_runs_source_check" not in migration
    assert "agent_tasks_source_check" not in migration
    assert "agent-zero" not in initial_schema
    assert '"agent-zero"' in store
    assert "record_external_action_event" in store


def test_agent_zero_key_uses_owner_protected_input_not_repo_secret() -> None:
    owner_input = (PRODUCTION / "owner_input_runtime.py").read_text("utf-8")
    adapter = (
        PRODUCTION / "agent_runtime" / "agent_zero_runtime.py"
    ).read_text("utf-8")

    assert '"agent_zero_api_key"' in owner_input
    assert "agent_zero_api_key.txt" in owner_input
    assert "SOVEREIGN_AGENT_ZERO_API_KEY_FILE" in adapter
    assert "read_protected_key" in adapter
    assert '"X-API-KEY": key' in adapter
    assert '"generalUserAllowed": False' in adapter
    assert "OWNER_SCOPED_EXTERNAL_AGENT_ZERO_MODEL" in adapter


def test_agent_zero_capabilities_include_requested_expanders_with_evidence_gates() -> None:
    adapter = (
        PRODUCTION / "agent_runtime" / "agent_zero_runtime.py"
    ).read_text("utf-8")
    agents = (
        PRODUCTION / "agent_runtime" / "cognitive_swarm_agents.py"
    ).read_text("utf-8")
    routes = (
        PRODUCTION / "agent_runtime" / "cognitive_swarm_routes.py"
    ).read_text("utf-8")

    for capability in (
        "skills",
        "browser",
        "playwright",
        "memory_recall",
        "memory_remember",
        "sleep_remember",
        "code_execution",
        "research",
        "computer",
        "mcp",
    ):
        assert f'"{capability}"' in adapter
    for tool_name in (
        "skills_tool",
        "memory_load",
        "memory_save",
        "browser_agent",
        "code_execution_tool",
        "search_engine",
    ):
        assert f'"{tool_name}"' in adapter
    assert "api_message" in adapter
    assert "api_log_get" in adapter
    assert "api_files_get" in adapter
    assert "sleep_skill_evidence" in adapter
    assert "capability_tool_factory" in agents
    assert "BoundAgentZeroCapabilityToolset" in routes
    assert 'result["agentZeroCapabilities"]' in routes


def test_health_ready_requires_live_agent_zero_constraint_readback() -> None:
    app = (PRODUCTION / "app.py").read_text("utf-8")

    assert "pg_get_constraintdef(oid) LIKE '%agent-zero%'" in app
    assert "AS agent_zero_evidence_source" in app
    assert '"agent_zero_evidence_source",' in app
    assert '"agentZeroEvidenceSourceVerified": bool(schema.get("agent_zero_evidence_source"))' in app
    assert '"054_agent_zero_capability_evidence.sql"' in app


def test_agent_zero_prompt_keeps_effect_authority_in_sovereign() -> None:
    adapter = (
        PRODUCTION / "agent_runtime" / "agent_zero_runtime.py"
    ).read_text("utf-8")

    assert "Sovereign remains the sole authority" in adapter
    assert "Never push, open/merge PRs, deploy, mutate a database" in adapter
    assert "Browser/computer work is read-only" in adapter
    assert "Memory is advisory working memory only" in adapter
    assert "do not emulate" in adapter
