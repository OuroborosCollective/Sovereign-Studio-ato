from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "scripts" / "sovereign-backend"


def test_free_profile_has_one_agent_and_code_workspace_access() -> None:
    migration = (BACKEND / "migrations" / "030_llm_execution_profiles.sql").read_text("utf-8")
    resolver = (BACKEND / "llm_execution_resolver.py").read_text("utf-8")

    assert "'free_single_agent'" in migration
    assert "1, 0, TRUE, FALSE, TRUE" in migration
    assert "max_background_agents=0" in resolver
    assert "repository_execution_allowed=True" in resolver


def test_free_agent_uses_one_isolated_workspace_task_with_write_and_test_tools() -> None:
    tools = (BACKEND / "agent_runtime" / "cognitive_repository_tools.py").read_text("utf-8")
    agents = (BACKEND / "agent_runtime" / "cognitive_swarm_agents.py").read_text("utf-8")
    routes = (BACKEND / "agent_runtime" / "cognitive_swarm_routes.py").read_text("utf-8")

    assert '"free_single_agent": ("__workspace_all__",)' in tools
    assert "def create_repository_single_agent_task(" in tools
    assert "def write_repository_file(" in tools
    assert "run_repository_test" in tools
    assert 'task_ids_by_agent={"free_single_agent": free_task_id}' in routes
    assert '"backgroundAgentsStarted": 0' in routes
    assert '"maxBackgroundAgents": 0' in routes
    assert '"codeServerWorkspace"' in routes
    assert "repository_tool_factory" in agents
    assert "tools=repository_tools" in agents
    assert "_AGENT_FREE_WORKSPACE_MAX_TURNS: Final[int] = 12" in agents
    assert 'if "free-single-agent" in normalized:' in agents
    assert "free_fallback_resolution(" in routes
    assert "paid_provider_429_resolved_to_free_revolver" in routes
    assert "_reuse_received_state=received_state" in routes


def test_code_server_and_agent_jobs_share_the_same_workspace_root() -> None:
    managed = (
        ROOT / "tools" / "sovereign-chatgpt-mcp" / "managed_compose.py"
    ).read_text("utf-8")
    workspace_policy = (
        BACKEND / "agent_runtime" / "workspace_policy.py"
    ).read_text("utf-8")

    assert 'BACKEND_WORKSPACE_HOST_ROOT = "/opt/sovereign-agent-workspaces"' in managed
    assert "CODE_SERVER_WORKSPACE_ROOT = BACKEND_WORKSPACE_HOST_ROOT" in managed
    assert 'CODE_SERVER_WORKSPACE_MOUNT = "/config/sovereign-agent-workspaces"' in managed
    assert 'return safe_workspace_path(workspace_id, root) / "repo"' in workspace_policy


def test_paid_rejection_refunds_before_free_fallback() -> None:
    agents = (BACKEND / "agent_runtime" / "cognitive_swarm_agents.py").read_text("utf-8")
    billing = (BACKEND / "agent_runtime" / "cognitive_usage_billing.py").read_text("utf-8")

    assert "refund_failed_before_usage" in agents
    assert "classified.http_status in {400, 401, 403, 404, 429}" in agents
    assert "def refund_failed_before_usage(" in billing
    assert "status='refunded'" in billing
    assert ":failed-before-usage" in billing


def test_canonical_agent_runtime_mirrors_are_equal() -> None:
    for name in (
        "cognitive_swarm_agents.py",
        "cognitive_swarm_routes.py",
        "cognitive_repository_tools.py",
        "cognitive_usage_billing.py",
    ):
        assert (BACKEND / "agent_runtime" / name).read_bytes() == (
            ROOT / "backend" / "agent_runtime" / name
        ).read_bytes()
