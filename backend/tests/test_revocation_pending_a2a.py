from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def source(relative: str) -> str:
    return (ROOT / relative).read_text("utf-8")


def test_pending_submission_is_local_and_permission_gated() -> None:
    runtime = source("backend/agent_runtime/repository_execution.py")
    pending = runtime.split("def _submit_pending_repository_job(", 1)[1].split(
        "def _safe_regression_commands(", 1
    )[0]
    submit = runtime.split("def _submit_after_claim(", 1)[1].split(
        "def _bind_repository_execution_permission(", 1
    )[0]
    assert "_EXECUTOR_PENDING_PREFIX" in pending
    assert "get_connection=get_connection" in pending
    assert "workspace_root=workspace_root" in pending
    assert "_require_repository_effect_authority" in submit
    assert "REVOKED_BEFORE_SOVEREIGN_EFFECT" in submit
    assert "BoundRepositoryToolset" in submit
    assert "AgentZeroA2AClient" not in submit


def test_repository_permission_contract_names_the_local_executor() -> None:
    runtime = source("backend/agent_runtime/repository_execution.py")
    permission = runtime.split("def _bind_repository_execution_permission(", 1)[1].split(
        "def _ensure_local_single_agent_run(", 1
    )[0]
    assert 'required_readback_kinds=("sovereign_local_execution",)' in permission
    assert 'tool_name="sovereign-local-runner"' in permission
    assert "repository.sovereign-execute" in permission
    assert "Agent Zero" not in permission


def test_canonical_and_shipping_permission_boundaries_match() -> None:
    canonical = ROOT / "backend" / "agent_runtime" / "repository_execution.py"
    shipping = ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / "repository_execution.py"
    assert canonical.read_bytes() == shipping.read_bytes()


def test_no_external_repository_submit_symbol_remains_in_active_runtime() -> None:
    runtime = source("backend/agent_runtime/repository_execution.py")
    assert "AgentZeroA2AClient" not in runtime
    assert "agent-zero-a2a:" not in runtime
    assert "submit_repository_task" not in runtime
    assert "cancel_repository_a2a_job" not in runtime
