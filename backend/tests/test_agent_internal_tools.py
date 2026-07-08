from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Füge Backend zum Python Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.tool_events import predictive_tool_signal, tool_result_to_agent_events  # noqa: E402
from agent_runtime.tools.diff_tool import collect_git_diff_summary  # noqa: E402
from agent_runtime.tools.file_tool import read_workspace_file, write_workspace_file  # noqa: E402
from agent_runtime.tools.git_tool import collect_git_status  # noqa: E402
from agent_runtime.tools.shell_tool import run_workspace_shell_command  # noqa: E402
from agent_runtime.tools.test_tool import run_workspace_test_command  # noqa: E402
from agent_runtime.workspace import create_agent_workspace  # noqa: E402
from agent_runtime.workspace_policy import repo_dir_for_workspace  # noqa: E402


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Sovereign Test"], cwd=path, check=True, capture_output=True, text=True)
    (path / "README.md").write_text("initial\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=path, check=True, capture_output=True, text=True)


def test_file_tool_writes_and_reads_allowed_file(tmp_path: Path):
    create_agent_workspace("agent-1", tmp_path)

    write = write_workspace_file("agent-1", "src/example.ts", "export const ok = true;\n", tmp_path)
    read = read_workspace_file("agent-1", "src/example.ts", tmp_path)

    assert write.status == "done"
    assert write.changed_files == ("src/example.ts",)
    assert write.predictive_signal == "agent_file_changed"
    assert read.status == "done"
    assert "export const ok" in read.stdout


def test_file_tool_blocks_secret_path(tmp_path: Path):
    create_agent_workspace("agent-1", tmp_path)

    result = write_workspace_file("agent-1", ".env", "SECRET=value", tmp_path)

    assert result.status == "blocked"
    assert result.allowed is False
    assert "Secret-like path" in (result.blocker or "")


def test_shell_tool_blocks_unknown_command(tmp_path: Path):
    create_agent_workspace("agent-1", tmp_path)

    result = run_workspace_shell_command("agent-1", ("node", "bad.js"), tmp_path)

    assert result.status == "blocked"
    assert result.predictive_signal == "agent_shell_policy_blocked"


def test_shell_tool_runs_allowlisted_git_status(tmp_path: Path):
    create_agent_workspace("agent-1", tmp_path)
    repo = repo_dir_for_workspace("agent-1", tmp_path)
    _init_git_repo(repo)

    result = run_workspace_shell_command("agent-1", ("git", "status", "--short"), tmp_path)

    assert result.status == "done"
    assert result.exit_code == 0
    assert result.predictive_signal == "agent_shell_command_completed"


def test_git_and_diff_tools_collect_evidence(tmp_path: Path):
    create_agent_workspace("agent-1", tmp_path)
    repo = repo_dir_for_workspace("agent-1", tmp_path)
    _init_git_repo(repo)
    (repo / "README.md").write_text("changed\n", encoding="utf-8")

    status = collect_git_status("agent-1", tmp_path)
    diff = collect_git_diff_summary("agent-1", tmp_path)

    assert status.status == "done"
    assert status.changed_files == ("README.md",)
    assert status.predictive_signal == "agent_git_status_completed"
    assert diff.status == "done"
    assert diff.diff_summary is not None
    assert "README.md" in diff.diff_summary
    assert diff.predictive_signal == "agent_diff_ready"


def test_test_tool_blocks_non_test_command(tmp_path: Path):
    create_agent_workspace("agent-1", tmp_path)

    result = run_workspace_test_command("agent-1", ("git", "status"), tmp_path)

    assert result.status == "blocked"
    assert result.predictive_signal == "agent_test_command_blocked"


def test_test_tool_uses_shell_runtime_for_approved_commands(monkeypatch, tmp_path: Path):
    from agent_runtime.tools.base import done_tool_result

    def fake_shell(workspace_id, argv, root=None, timeout_seconds=300):
        assert workspace_id == "agent-1"
        assert argv[:3] == ("python", "-m", "pytest")
        return done_tool_result("shell", stdout="1 passed", exit_code=0, predictive_signal="agent_shell_command_completed")

    monkeypatch.setattr("agent_runtime.tools.test_tool.run_workspace_shell_command", fake_shell)

    result = run_workspace_test_command("agent-1", ("python", "-m", "pytest", "backend/tests"), tmp_path)

    assert result.status == "done"
    assert result.test_summary == "1 passed"
    assert result.predictive_signal == "agent_tests_completed"


def test_tool_result_becomes_predictive_agent_signal(tmp_path: Path):
    create_agent_workspace("agent-1", tmp_path)
    result = write_workspace_file("agent-1", "README.md", "hello\n", tmp_path)

    events = tool_result_to_agent_events(result)
    signal = predictive_tool_signal(result)

    assert events[0].stage == "file_tool_completed"
    assert signal["signal"] == "agent_file_changed"
    assert signal["changedFiles"] == ["README.md"]
