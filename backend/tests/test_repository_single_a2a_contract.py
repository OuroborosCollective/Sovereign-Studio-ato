from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_single_a2a_repository_runtime_has_no_swarm_or_auto_publication_dependency():
    runtime = _source("backend/agent_runtime/repository_execution.py")
    a2a = _source("backend/agent_runtime/agent_zero_a2a.py")

    for forbidden in (
        "run_cognitive_swarm",
        "create_repository_swarm_tasks",
        "cognitive_swarm",
        "/swarm/run",
        "create_draft_pr_for_job",
        "repository_merge",
        "merge_pr",
    ):
        assert forbidden not in runtime

    assert "message/send" in a2a
    assert '"blocking": False' in a2a
    assert "tasks/get" in a2a
    assert '"Authorization": f"Bearer {token}"' in a2a
    assert '"X-API-KEY": token' in a2a
    assert "/a0/sovereign-workspaces" in a2a


def test_repository_http_boundary_and_frontend_are_not_swarm_backed():
    routes = _source("backend/agent_runtime/routes.py")
    repository_adapter = _source(
        "src/features/control-surface-vnext/adapter/repository-bound-adapter.ts"
    )
    client = _source("src/features/product/runtime/sovereignAgentClient.ts")

    assert '@app.route("/api/user/agent/repository/run", methods=["POST"])' in routes
    assert "start_repository_execution(" in routes
    assert "reconcile_repository_execution(" in routes

    assert "'/api/user/agent/repository/run'" in repository_adapter
    assert "'/api/user/agent/swarm/run'" not in repository_adapter
    assert "'/api/user/agent/repository/run'" in client
    assert "'/api/user/agent/swarm/run'" not in client
    assert "mode: 'free'" in client
    assert "agentMode: 'single'" in client


def test_external_ref_is_atomic_task_authority_and_recovery_is_bounded():
    store = _source("backend/agent_runtime/job_store.py")
    runtime = _source("backend/agent_runtime/repository_execution.py")

    assert "external_ref IS NOT DISTINCT FROM %s" in store
    assert "RETURNING job_id" in store
    assert '"agent-zero-a2a:"' in runtime
    assert '"agent-zero-a2a:retry:"' in runtime
    assert "AgentZeroA2ASubmitOutcomeUnknown" in runtime
    assert "automatic resubmit is forbidden" in runtime
    assert "no further resubmit is allowed" in runtime


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
