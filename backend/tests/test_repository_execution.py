from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def source(relative: str) -> str:
    return (ROOT / relative).read_text("utf-8")


def section(text: str, start: str, end: str) -> str:
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    return text[start_index:end_index]


def test_active_repository_executor_is_sovereign_local_only() -> None:
    runtime = source("backend/agent_runtime/repository_execution.py")
    assert "AgentZeroA2AClient" not in runtime
    assert "AgentZeroA2AError" not in runtime
    assert "agent-zero-a2a:" not in runtime
    assert '_EXECUTOR_PREFIX: Final[str] = "sovereign-local-runner:"' in runtime
    assert '_EXECUTOR_PENDING_PREFIX: Final[str] = "sovereign-local-runner:pending:submit:"' in runtime
    assert '_EXECUTOR_CLAIM_PREFIX: Final[str] = "sovereign-local-runner:claim:"' in runtime


def test_repository_start_clones_into_the_isolated_workspace() -> None:
    runtime = source("backend/agent_runtime/repository_execution.py")
    start = section(
        runtime,
        "def start_repository_execution(",
        "def _submit_pending_repository_job(",
    )
    assert "provision_workspace=True" in start
    assert "clone_repo=True" in start
    assert "clone_repo=False" not in start
    assert "sovereign_repository_checked_out" in start
    assert "sovereign_local_execution_queued" in start


def test_single_agent_run_is_persisted_before_model_execution() -> None:
    runtime = source("backend/agent_runtime/repository_execution.py")
    submit = section(runtime, "def _ensure_local_single_agent_run(", "def _submit_after_claim(")
    assert "create_agent_run(" in submit
    assert "read_agent_run(" in submit
    assert "read_agent_task_ids(" in submit
    assert "create_repository_single_agent_task(" in submit
    assert 'agent_id="free_single_agent"' in submit
    assert 'status="RUNNING"' in submit
    assert 'source="agents-sdk"' in submit


def test_local_executor_binds_real_repository_toolset_and_free_route() -> None:
    runtime = source("backend/agent_runtime/repository_execution.py")
    submit = section(runtime, "def _submit_after_claim(", "def _safe_regression_commands(")
    assert "BoundRepositoryToolset(" in submit
    assert "write_confirmed=True" in submit
    assert "run_free_single_agent(" in submit
    assert "repository_tool_factory=repository_toolset.tools_for_role" in submit
    assert "capability_tool_factory=None" in submit
    assert 'requested_mode="free"' in submit
    assert "FREE_SINGLE_AGENT_PROFILE" in submit
    assert "route_provider_model" in submit


def test_local_executor_uses_the_isolated_repository_directory_as_tool_root() -> None:
    runtime = source("backend/agent_runtime/repository_execution.py")
    assert "repo_dir_for_workspace(workspace_id, workspace_root)" in runtime
    assert "workspace_root=repo_path.parent.parent" in runtime


def test_pending_reconcile_forwards_a_fresh_database_connection_and_workspace() -> None:
    runtime = source("backend/agent_runtime/repository_execution.py")
    pending = section(runtime, "def _submit_pending_repository_job(", "def _safe_regression_commands(")
    reconcile = section(runtime, "def reconcile_repository_jobs_once(", "def start_repository_reconciler(")
    assert "get_connection: ConnectionFactory | None = None" in pending
    assert "workspace_root=workspace_root" in pending
    assert "get_connection=get_connection" in pending
    assert "workspace_root=workspace_root" in reconcile
    assert "get_connection=get_connection" in reconcile


def test_local_executor_closeout_requires_real_git_diff_and_regression() -> None:
    runtime = source("backend/agent_runtime/repository_execution.py")
    closeout = section(runtime, "def _closeout_repository_job(", "def reconcile_repository_execution(")
    assert 'run_agent_job_tool(job, "git-status"' in closeout
    assert 'run_agent_job_tool(job, "diff"' in closeout
    assert "git_diff_full(" in closeout
    assert "git_diff_check(" in closeout
    assert "repository_regression_started" in closeout
    assert 'run_agent_job_tool(' in closeout
    assert '"test"' in closeout
    assert "evaluate_agent_evidence(" in closeout
    assert "prepare_draft_pr(" in closeout


def test_local_executor_never_auto_merges_or_deploys() -> None:
    tools = source("backend/agent_runtime/cognitive_repository_tools.py")
    task = section(tools, "def create_repository_single_agent_task(", "def _require_function_tool(")
    assert "No background agent, production deploy, merge or auto-merge is started." in task
    assert "start background agents" in task
    assert "merge a pull request" in task
    assert "deploy to production" in task
    assert "claim success without tool, diff and test evidence" in task


def test_cancellation_is_local_only() -> None:
    runtime = source("backend/agent_runtime/repository_execution.py")
    cancel = section(runtime, "def cancel_repository_execution(", "def _block_job(")
    assert 'status="blocked"' in cancel
    assert "sovereign_executor_cancelled" in cancel
    assert "external executor cancellation" in cancel
    assert "AgentZeroA2AClient" not in cancel
    assert "submit_repository_task" not in cancel


def test_frontend_repository_surface_matches_local_executor_contract() -> None:
    chat = source("src/features/control-surface-vnext/components/ChatSurface/ChatSurface.tsx")
    adapter = source("src/features/control-surface-vnext/adapter/repository-bound-adapter.ts")
    client = source("src/features/product/runtime/sovereignAgentClient.ts")
    assert "Sovereign · Free" in chat
    assert "No external executor is used." in chat
    assert "Agent Zero" not in chat
    assert "executor === 'sovereign-local-runner'" in adapter
    assert "agent-zero-a2a:" not in adapter
    assert "Agent Zero A2A" not in client
    assert "Sovereign-local-runner route" in client


def test_unified_frontend_backend_boundary_has_no_external_repository_executor() -> None:
    runtime = source("src/features/product/runtime/sovereignAgentRuntime.ts")
    boundary = source("src/features/product/runtime/sovereignEngineBoundary.ts")
    bridge = source("src/features/product/runtime/devChatWorkerBridge.ts")
    assert "readSameOriginBackendUrl()" in runtime
    assert "await transport.startRepositoryExecution(command.payload.input)" in boundary
    assert "await transport.listJobs()" in boundary
    assert "agent-zero-a2a:" not in runtime
    assert "agent-zero-a2a:" not in bridge


def test_canonical_and_shipping_repository_execution_mirrors_are_equal() -> None:
    canonical = ROOT / "backend/agent_runtime/repository_execution.py"
    shipping = ROOT / "scripts/sovereign-backend/agent_runtime/repository_execution.py"
    assert shipping.read_bytes() == canonical.read_bytes()
