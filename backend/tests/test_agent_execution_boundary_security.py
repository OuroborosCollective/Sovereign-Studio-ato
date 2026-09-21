from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.tools.file_tool import FileReadTool  # noqa: E402
from agent_runtime.tools.test_tool import TestTool  # noqa: E402
from agent_runtime.tools.base import ToolResult  # noqa: E402


def test_file_read_blocks_path_escape(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (tmp_path / "secret.txt").write_text("must not be read", encoding="utf-8")

    result = FileReadTool().execute({"path": "../secret.txt"}, str(workspace))

    assert result.status == "blocked"
    assert result.blocker == "Path escape attempt detected"
    assert "must not be read" not in (result.output or "")


def test_custom_test_command_blocks_shell_control_tokens(tmp_path: Path):
    result = TestTool().execute(
        {"command": "python -m pytest && touch escaped.txt", "verbose": False},
        str(tmp_path),
    )

    assert result.status == "blocked"
    assert result.blocker == "Custom test command is not allowlisted"
    assert not (tmp_path / "escaped.txt").exists()


def test_vitest_framework_always_uses_run_mode(monkeypatch, tmp_path: Path):
    observed = {}

    def fake_run_command(args, cwd, timeout):
        observed["args"] = args
        observed["cwd"] = cwd
        observed["timeout"] = timeout
        return ToolResult(status="done", output="passed", exit_code=0)

    tool = TestTool()
    monkeypatch.setattr(tool, "_run_command", fake_run_command)

    result = tool.execute({"framework": "vitest", "verbose": True}, str(tmp_path))

    assert result.status == "done"
    assert observed["args"][:3] == ["npx", "vitest", "run"]
    assert "--reporter=verbose" in observed["args"]


def test_node_regression_bootstraps_frozen_dependencies_without_scripts(monkeypatch, tmp_path: Path):
    (tmp_path / "package.json").write_text('{"scripts":{"test":"vitest run"}}', encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    calls = []

    class Completed:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(args, **kwargs):
        calls.append((list(args), kwargs))
        return Completed()

    monkeypatch.setattr("agent_runtime.tools.test_tool.subprocess.run", fake_run)

    result = TestTool().execute(
        {"command": "pnpm test", "verbose": False, "timeout": 120},
        str(tmp_path),
    )

    assert result.status == "done"
    assert calls[0][0] == ["pnpm", "install", "--frozen-lockfile", "--ignore-scripts"]
    assert calls[0][1]["env"]["CI"] == "1"
    assert calls[1][0] == ["pnpm", "test"]


def test_node_regression_fails_closed_without_lockfile(monkeypatch, tmp_path: Path):
    (tmp_path / "package.json").write_text('{"scripts":{"test":"vitest run"}}', encoding="utf-8")

    def unexpected_run(*_args, **_kwargs):
        raise AssertionError("unlocked dependency bootstrap must not execute")

    monkeypatch.setattr("agent_runtime.tools.test_tool.subprocess.run", unexpected_run)

    result = TestTool().execute(
        {"command": "pnpm test", "verbose": False},
        str(tmp_path),
    )

    assert result.status == "blocked"
    assert result.blocker == "Node dependency bootstrap requires pnpm-lock.yaml or package-lock.json"
