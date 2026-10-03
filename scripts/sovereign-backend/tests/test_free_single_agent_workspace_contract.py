from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "scripts" / "sovereign-backend"


def test_free_profile_has_one_agent_and_repository_access() -> None:
    migration = (BACKEND / "migrations" / "030_llm_execution_profiles.sql").read_text("utf-8")
    resolver = (BACKEND / "llm_execution_resolver.py").read_text("utf-8")

    assert "'free_single_agent'" in migration
    assert "1, 0, TRUE, FALSE, TRUE" in migration
    assert "max_background_agents=0" in resolver
    assert "repository_execution_allowed=True" in resolver


def test_free_agent_repository_execution_uses_the_local_single_agent_boundary() -> None:
    tools = (BACKEND / "agent_runtime" / "cognitive_repository_tools.py").read_text("utf-8")
    agents = (BACKEND / "agent_runtime" / "cognitive_swarm_agents.py").read_text("utf-8")
    runtime = (BACKEND / "agent_runtime" / "repository_execution.py").read_text("utf-8")

    assert "def create_repository_single_agent_task(" in tools
    assert "run_repository_test" in tools
    assert 'agent_id = f"{execution_mode}_single_agent"' in tools
    assert 'execution_mode: str = "free"' in tools
    assert "repository_tool_factory" in agents
    assert "capability_tool_factory" in agents
    assert "tools=[*repository_tools, *capability_tools]" in agents
    assert "The free profile requires a direct FreeLLM route." in agents
    assert "BoundRepositoryToolset(" in runtime
    assert "run_free_single_agent(" in runtime
    assert "AgentZeroA2AClient" not in runtime
    assert "agent-zero-a2a:" not in runtime
    assert "sovereign-local-runner:" in runtime


def test_code_server_and_agent_jobs_share_the_same_workspace_root() -> None:
    managed = (ROOT / "tools" / "sovereign-chatgpt-mcp" / "managed_compose.py").read_text("utf-8")
    workspace_policy = (BACKEND / "agent_runtime" / "workspace_policy.py").read_text("utf-8")

    assert 'BACKEND_WORKSPACE_HOST_ROOT = "/opt/sovereign-agent-workspaces"' in managed
    assert "CODE_SERVER_WORKSPACE_ROOT = BACKEND_WORKSPACE_HOST_ROOT" in managed
    assert 'CODE_SERVER_WORKSPACE_MOUNT = "/config/sovereign-agent-workspaces"' in managed
    assert 'return safe_workspace_path(workspace_id, root) / "repo"' in workspace_policy


def test_canonical_agent_runtime_mirrors_are_equal() -> None:
    for name in (
        "cognitive_swarm_agents.py",
        "cognitive_swarm_routes.py",
        "cognitive_repository_tools.py",
        "cognitive_usage_billing.py",
        "repository_execution.py",
    ):
        assert (BACKEND / "agent_runtime" / name).read_bytes() == (
            ROOT / "backend" / "agent_runtime" / name
        ).read_bytes()


def test_execution_resolver_top_level_mirrors_are_equal() -> None:
    for name in ("llm_cost_policy.py", "llm_revolver.py", "llm_execution_resolver.py"):
        assert (BACKEND / name).read_bytes() == (ROOT / "backend" / name).read_bytes()
