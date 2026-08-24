from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys

import pytest

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from agent_runtime.fleet_attempts import create_worker_attempt
from agent_runtime.fleet_attempt_worktrees import provision_attempt_worktree
from agent_runtime.fleet_supervisor import FleetTask, build_fleet_plan, create_worker_assignment
from agent_runtime.live_workspace import LiveWorkspaceSessionV1, WorkspaceReadbackV1
from agent_runtime.live_workspace_projection import ProjectionContractError, projection_for_tool_result
from agent_runtime.tools.base import ToolResult


def _git(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True)


def _workspace(tmp_path: Path):
    root = tmp_path / "workspaces"
    repo = root / "job-projection" / "repo"
    repo.mkdir(parents=True)
    _git(["git", "init"], repo)
    _git(["git", "config", "user.email", "projection@example.invalid"], repo)
    _git(["git", "config", "user.name", "Projection Test"], repo)
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("print('bound')\n", encoding="utf-8")
    _git(["git", "add", "."], repo)
    _git(["git", "commit", "-m", "fixture"], repo)
    _git(["git", "remote", "add", "origin", "https://github.com/OuroborosCollective/Sovereign-Studio-ato"], repo)
    job = SimpleNamespace(
        job_id="job-projection",
        workspace_id="job-projection",
        repo_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato",
    )
    return root, repo, job


def _session(root: Path, repo: Path, job):
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, text=True, capture_output=True
    ).stdout.strip()
    task = FleetTask(
        task_id="live-projection-test",
        source_type="issue",
        source_id="1618",
        expected_base_revision=head,
        expected_head_revision=head,
        independence_proven=True,
    )
    plan = build_fleet_plan(
        integration_id="live-projection-test",
        repository="OuroborosCollective/Sovereign-Studio-ato",
        base_revision=head,
        architecture_receipt_hashes=["b" * 64],
        tasks=[task],
    )
    assignment = create_worker_assignment(
        plan,
        lane_id="lane-01",
        task_id=task.task_id,
        controller_run_id="run-live-projection",
        workspace_id=job.workspace_id,
        workspace_branch="sovereign/live-projection-test",
        run_envelope_hash="c" * 64,
        capability_manifest_hash="d" * 64,
    )
    attempt = create_worker_attempt(assignment, attempt_sequence=1)
    attempt_workspace = provision_attempt_worktree(
        assignment=assignment,
        attempt=attempt,
        active_attempt=attempt,
        repository_url=job.repo_url,
        root=root,
    )
    readback = WorkspaceReadbackV1.from_dict({
        "repository": "OuroborosCollective/Sovereign-Studio-ato",
        "workspaceId": job.workspace_id,
        "worktreeIdentityHash": attempt_workspace.worktree_readback_sha256,
        "observedHeadRevision": attempt_workspace.head_revision,
        "fleetPlanHash": assignment.plan_hash,
        "controllerStateRef": "f" * 64,
        "controllerState": "RUNNING",
        "workspacePathOwner": job.workspace_id,
    })
    session = LiveWorkspaceSessionV1.bind(
        assignment=assignment,
        attempt=attempt,
        active_attempt=attempt,
        workspace_readback=readback,
        projection_source_hashes=["a" * 64],
    )
    reconciliation = session.reconcile(active_attempt=attempt, workspace_readback=readback)
    return session, reconciliation, attempt_workspace


def _result(*, tool: str = "file", status: str = "done", output: str = "ok", exit_code: int = 0) -> ToolResult:
    return ToolResult(
        status=status,
        tool=tool,
        output=output,
        stdout=output,
        exit_code=exit_code,
        metadata={"actionId": "action-123", "providerNeutralEvidenceSha256": "a" * 64},
    )


def _project(*, root: Path, job, route_action: str, parameters: dict, result: ToolResult):
    repo = root / job.workspace_id / "repo"
    session, reconciliation, attempt_workspace = _session(root, repo, job)
    return projection_for_tool_result(
        job=job,
        attempt_workspace=attempt_workspace,
        route_action=route_action,
        parameters=parameters,
        result=result,
        session=session,
        reconciliation=reconciliation,
    )


def test_file_projection_is_bound_to_real_worktree_readback(tmp_path: Path) -> None:
    root, repo, job = _workspace(tmp_path)
    projection = _project(
        root=root,
        job=job,
        route_action="file",
        parameters={"path": "src/app.py", "mode": "read"},
        result=_result(),
    )

    payload = projection.to_dict()
    assert payload["schemaVersion"] == "sovereign.visual-projection-event.v1"
    assert payload["sessionBindingHash"]
    assert payload["attemptId"].startswith("attempt-")
    assert payload["projectionKind"] == "IDE_FILE"
    assert payload["projectionState"] == "REQUESTED"
    assert payload["payload"]["path"] == "src/app.py"
    assert payload["repositoryHead"] == subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, text=True, capture_output=True
    ).stdout.strip()
    assert payload["authoritative"] is False
    assert payload["claim"] == "OBSERVED"


def test_file_projection_rejects_path_escape_or_missing_readback(tmp_path: Path) -> None:
    root, _, job = _workspace(tmp_path)
    with pytest.raises(ProjectionContractError, match="invalid"):
        _project(
            root=root,
            job=job,
            route_action="file",
            parameters={"path": "../outside.py", "mode": "read"},
            result=_result(),
        )
    with pytest.raises(ProjectionContractError, match="unavailable"):
        _project(
            root=root,
            job=job,
            route_action="file",
            parameters={"path": "src/missing.py", "mode": "read"},
            result=_result(),
        )


def test_diff_projection_binds_head_and_real_diff_digest(tmp_path: Path) -> None:
    root, _, job = _workspace(tmp_path)
    projection = _project(
        root=root,
        job=job,
        route_action="diff",
        parameters={},
        result=_result(tool="diff", output="diff --git a/src/app.py b/src/app.py\n"),
    )
    assert projection.projection_kind == "IDE_DIFF"
    assert projection.payload["diffSha256"]
    assert projection.repository_head


def test_terminal_projection_is_observation_and_keeps_exit_receipt_separate(tmp_path: Path) -> None:
    root, _, job = _workspace(tmp_path)
    projection = _project(
        root=root,
        job=job,
        route_action="test",
        parameters={"command": "pytest -q"},
        result=_result(tool="test", output="1 passed\n", exit_code=0),
    )
    assert projection.projection_kind == "TERMINAL"
    assert projection.payload["processState"] == "EXITED"
    assert projection.payload["exitCode"] == 0
    assert projection.to_dict()["authoritative"] is False


def test_executed_failing_test_remains_visible_with_nonzero_exit(tmp_path: Path) -> None:
    root, _, job = _workspace(tmp_path)
    result = _result(status="error", tool="test", output="1 failed\n", exit_code=1)
    projection = _project(
        root=root,
        job=job,
        route_action="test",
        parameters={"command": "pytest -q"},
        result=result,
    )
    assert projection.projection_kind == "TERMINAL"
    assert projection.projection_state == "REQUESTED"
    assert projection.payload["processState"] == "EXITED"
    assert projection.payload["exitCode"] == 1
    assert projection.payload["successful"] is False
    assert projection.payload["canonicalStatus"] == "error"
    assert result.status == "error"


def test_failed_canonical_action_degrades_projection_without_rewriting_result(tmp_path: Path) -> None:
    root, _, job = _workspace(tmp_path)
    result = _result(status="blocked", output="", exit_code=1)
    projection = _project(
        root=root,
        job=job,
        route_action="test",
        parameters={"command": "pytest -q"},
        result=result,
    )
    assert projection.projection_state == "UNAVAILABLE"
    assert result.status == "blocked"


def test_projection_requires_real_action_identity(tmp_path: Path) -> None:
    root, _, job = _workspace(tmp_path)
    result = _result()
    result = ToolResult(
        status=result.status,
        tool=result.tool,
        output=result.output,
        stdout=result.stdout,
        exit_code=result.exit_code,
        metadata={"providerNeutralEvidenceSha256": "a" * 64},
    )
    with pytest.raises(ProjectionContractError, match="action identity"):
        _project(
            root=root,
            job=job,
            route_action="file",
            parameters={"path": "src/app.py", "mode": "read"},
            result=result,
        )


def test_projection_rejects_outer_agent_job_clone_as_attempt_source(tmp_path: Path) -> None:
    root, repo, job = _workspace(tmp_path)
    session, reconciliation, attempt_workspace = _session(root, repo, job)
    outer_clone = replace(attempt_workspace, worktree_path=repo)

    with pytest.raises(ProjectionContractError, match="repository is unavailable"):
        projection_for_tool_result(
            job=job,
            attempt_workspace=outer_clone,
            route_action="file",
            parameters={"path": "src/app.py", "mode": "read"},
            result=_result(),
            session=session,
            reconciliation=reconciliation,
        )


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "backend").is_dir() and (candidate / "scripts/sovereign-backend").is_dir():
            return candidate
    raise AssertionError("repository root not found")


def test_projection_bridge_is_byte_identical_in_deployment_mirror() -> None:
    root = _repo_root()
    canonical = root / "backend/agent_runtime/live_workspace_projection.py"
    mirror = root / "scripts/sovereign-backend/agent_runtime/live_workspace_projection.py"
    assert canonical.read_bytes() == mirror.read_bytes()
