from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys

import pytest

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

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
    job = SimpleNamespace(job_id="job-projection", workspace_id="job-projection")
    return root, repo, job


def _result(*, tool: str = "file", status: str = "done", output: str = "ok", exit_code: int = 0) -> ToolResult:
    return ToolResult(
        status=status,
        tool=tool,
        output=output,
        stdout=output,
        exit_code=exit_code,
        metadata={"actionId": "action-123", "providerNeutralEvidenceSha256": "a" * 64},
    )


def test_file_projection_is_bound_to_real_worktree_readback(tmp_path: Path) -> None:
    root, repo, job = _workspace(tmp_path)
    projection = projection_for_tool_result(
        job=job,
        route_action="file",
        parameters={"path": "src/app.py", "mode": "read"},
        result=_result(),
        workspace_root=root,
    )

    payload = projection.to_dict()
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
    with pytest.raises((ProjectionContractError, ValueError)):
        projection_for_tool_result(
            job=job,
            route_action="file",
            parameters={"path": "../outside.py", "mode": "read"},
            result=_result(),
            workspace_root=root,
        )
    with pytest.raises(ProjectionContractError, match="unavailable"):
        projection_for_tool_result(
            job=job,
            route_action="file",
            parameters={"path": "src/missing.py", "mode": "read"},
            result=_result(),
            workspace_root=root,
        )


def test_diff_projection_binds_head_and_real_diff_digest(tmp_path: Path) -> None:
    root, _, job = _workspace(tmp_path)
    projection = projection_for_tool_result(
        job=job,
        route_action="diff",
        parameters={},
        result=_result(tool="diff", output="diff --git a/src/app.py b/src/app.py\n"),
        workspace_root=root,
    )
    assert projection.projection_kind == "IDE_DIFF"
    assert projection.payload["diffSha256"]
    assert projection.repository_head


def test_terminal_projection_is_observation_and_keeps_exit_receipt_separate(tmp_path: Path) -> None:
    root, _, job = _workspace(tmp_path)
    projection = projection_for_tool_result(
        job=job,
        route_action="test",
        parameters={"command": "pytest -q"},
        result=_result(tool="test", output="1 passed\n", exit_code=0),
        workspace_root=root,
    )
    assert projection.projection_kind == "TERMINAL"
    assert projection.payload["processState"] == "EXITED"
    assert projection.payload["exitCode"] == 0
    assert projection.to_dict()["authoritative"] is False


def test_failed_canonical_action_degrades_projection_without_rewriting_result(tmp_path: Path) -> None:
    root, _, job = _workspace(tmp_path)
    result = _result(status="blocked", output="", exit_code=1)
    projection = projection_for_tool_result(
        job=job,
        route_action="test",
        parameters={"command": "pytest -q"},
        result=result,
        workspace_root=root,
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
        projection_for_tool_result(
            job=job,
            route_action="file",
            parameters={"path": "src/app.py", "mode": "read"},
            result=result,
            workspace_root=root,
        )
