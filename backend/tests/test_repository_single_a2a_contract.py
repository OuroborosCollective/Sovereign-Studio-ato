from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_single_sovereign_repository_runtime_has_no_external_executor_dependency():
    runtime = _source("backend/agent_runtime/repository_execution.py")
    for forbidden in (
        "AgentZeroA2AClient",
        "AgentZeroA2AError",
        "AgentZeroA2ASubmitOutcomeUnknown",
        "AgentZeroA2ATaskLost",
        "agent-zero-a2a:",
        "create_draft_pr_for_job",
        "repository_merge_pr",
        "merge_pr(",
    ):
        assert forbidden not in runtime
    assert "BoundRepositoryToolset" in runtime
    assert "run_free_single_agent(" in runtime
    assert "sovereign-local-runner:" in runtime


def test_repository_http_boundary_and_frontend_use_the_unified_local_route():
    routes = _source("backend/agent_runtime/routes.py")
    repository_adapter = _source(
        "src/features/control-surface-vnext/adapter/repository-bound-adapter.ts"
    )
    client = _source("src/features/product/runtime/sovereignAgentClient.ts")

    assert '@app.route("/api/user/agent/repository/run", methods=["POST"])' in routes
    assert "start_repository_execution(" in routes
    assert "reconcile_repository_execution(" in routes
    assert "cancel_repository_execution(" in routes

    assert "'/api/user/agent/repository/run'" in repository_adapter
    assert "'/api/user/agent/swarm/run'" not in repository_adapter
    assert "'/api/user/agent/repository/run'" in client
    assert "'/api/user/agent/swarm/run'" not in client
    assert "mode: 'free'" in client
    assert "agentMode: 'single'" in client
    assert "Sovereign-local-runner" in client


def test_external_ref_is_atomic_local_executor_authority_and_recovery_is_bounded():
    store = _source("backend/agent_runtime/job_store.py")
    runtime = _source("backend/agent_runtime/repository_execution.py")

    assert "external_ref IS NOT DISTINCT FROM %s" in store
    assert "RETURNING job_id" in store
    assert '"sovereign-local-runner:"' in runtime
    assert '"sovereign-local-runner:retry:"' in runtime
    assert '"sovereign-local-runner:pending:submit:"' in runtime
    assert '"sovereign-local-runner:claim:"' in runtime
    assert "automatic resubmit" not in runtime


def test_closeout_prepares_but_does_not_create_or_merge_product_pr():
    runtime = _source("backend/agent_runtime/repository_execution.py")

    assert 'run_agent_job_tool(job, "git-status"' in runtime
    assert 'run_agent_job_tool(job, "diff"' in runtime
    assert "git_diff_check(" in runtime
    assert '"janitor"' in runtime
    assert '"test"' in runtime
    assert "evaluate_agent_evidence(" in runtime
    assert "prepare_draft_pr(" in runtime
    assert "mark_draft_pr_prepared(" in runtime
    assert "create_draft_pr_for_job" not in runtime
    assert "repository_merge_pr" not in runtime
    assert "merge_pr(" not in runtime
