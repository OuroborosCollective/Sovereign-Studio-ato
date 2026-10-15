from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def source(relative: str) -> str:
    return (ROOT / relative).read_text("utf-8")


def section(text: str, start: str, end: str) -> str:
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    return text[start_index:end_index]


def test_repository_execution_is_owned_by_sovereign_local_runner() -> None:
    routes = source("backend/agent_runtime/routes.py")
    runtime = source("backend/agent_runtime/repository_execution.py")
    client = source("src/features/product/runtime/sovereignAgentClient.ts")

    repo_route = section(
        routes,
        "def user_start_repository_execution():",
        '@app.route("/api/user/agent/jobs", methods=["POST"])',
    )
    assert "_github_access_token_for_session" not in repo_route
    assert "GITHUB_CREDENTIAL_FORBIDDEN_ON_EXECUTION" in repo_route
    assert "github_access_token=" not in repo_route

    start_runtime = section(
        runtime,
        "def start_repository_execution(",
        "def _submit_pending_repository_job(",
    )
    assert "clone_repo=True" in start_runtime
    assert "clone_repo=False" not in start_runtime
    assert "sovereign_repository_checked_out" in start_runtime
    assert "sovereign_local_execution_queued" in start_runtime
    assert "AgentZeroA2AClient" not in runtime
    assert "agent-zero-a2a:" not in runtime
    assert "sovereign-local-runner" in runtime

    assert "startRepositoryExecution()" in client
    assert "Agent Zero A2A" not in client
    assert "agent-zero-a2a:" not in client


def test_local_submission_uses_one_persisted_free_single_agent_with_repository_tools() -> None:
    runtime = source("backend/agent_runtime/repository_execution.py")
    tools = source("backend/agent_runtime/cognitive_repository_tools.py")
    agents = source("backend/agent_runtime/cognitive_swarm_agents.py")

    submit = section(
        runtime,
        "def _submit_after_claim(",
        "def _safe_regression_commands(",
    )
    assert "_ensure_local_single_agent_run(" in submit
    assert "create_repository_single_agent_task(" in runtime
    assert "BoundRepositoryToolset(" in submit
    assert "run_free_single_agent(" in submit
    assert "repository_tool_factory=repository_toolset.tools_for_role" in submit
    assert "capability_tool_factory=None" in submit
    assert 'requested_mode="free"' in submit
    assert "FREE_SINGLE_AGENT_PROFILE" in submit
    assert 'externalExecutor": False' in runtime

    task = section(
        tools,
        "def create_repository_single_agent_task(",
        "def _require_function_tool(",
    )
    assert 'agent_id="free_single_agent"' in task
    assert 'specialist_role="free_single_agent"' in task
    assert 'allowed_files=("isolated_code_server_workspace",)' in task
    assert "max_tool_calls=40" in task
    assert "commit=True" in task

    assert "Run exactly one foreground agent" in agents
    assert "The free profile requires a direct FreeLLM route." in agents


def test_repository_reconciler_passes_fresh_connection_and_workspace_context() -> None:
    runtime = source("backend/agent_runtime/repository_execution.py")
    reconciler = section(
        runtime,
        "def reconcile_repository_jobs_once(",
        "def start_repository_reconciler(",
    )
    assert "_submit_pending_repository_job(" in reconciler
    assert "workspace_root=workspace_root" in reconciler
    assert "get_connection=get_connection" in reconciler
    assert "repository local-runner reconcile failed" in reconciler
    assert "sovereign-repository-local-reconciler" in runtime


def test_repository_cancellation_is_local_and_external_executor_free() -> None:
    runtime = source("backend/agent_runtime/repository_execution.py")
    routes = source("backend/agent_runtime/routes.py")

    cancel = section(
        runtime,
        "def cancel_repository_execution(",
        "def _block_job(",
    )
    assert 'status="blocked"' in cancel
    assert "sovereign_executor_cancelled" in cancel
    assert "cancel_task(" not in cancel
    assert "AgentZeroA2AClient" not in cancel
    assert "cancel_repository_execution" in routes


def test_shipping_backend_is_byte_equal_to_canonical_repository_execution() -> None:
    canonical = ROOT / "backend/agent_runtime/repository_execution.py"
    shipping = ROOT / "scripts/sovereign-backend/agent_runtime/repository_execution.py"
    assert shipping.read_bytes() == canonical.read_bytes()


def test_frontend_repository_surface_has_no_external_executor_copy() -> None:
    chat = source("src/features/control-surface-vnext/components/ChatSurface/ChatSurface.tsx")
    adapter = source("src/features/control-surface-vnext/adapter/repository-bound-adapter.ts")
    client = source("src/features/product/runtime/sovereignAgentClient.ts")

    assert "Sovereign · Free" in chat
    assert "No external executor is used." in chat
    assert "Agent Zero" not in chat
    assert "executor === 'sovereign-local-runner'" in adapter
    assert "agent-zero-a2a:" not in adapter
    assert "Agent Zero A2A" not in client
