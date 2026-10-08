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


def test_canonical_sovereign_origin_uses_repository_build_policy(monkeypatch, tmp_path: Path):
    (tmp_path / "package.json").write_text('{"scripts":{"test":"vitest run"}}', encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text(
        '[remote "origin"]\n\turl = https://github.com/OuroborosCollective/Sovereign-Studio-ato.git\n',
        encoding="utf-8",
    )
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
        {"command": "pnpm test", "verbose": False},
        str(tmp_path),
    )

    assert result.status == "done"
    assert calls[0][0] == ["pnpm", "install", "--frozen-lockfile"]
    assert calls[1][0] == ["pnpm", "test"]


def test_documented_named_test_scripts_are_allowlisted(monkeypatch, tmp_path: Path):
    calls = []

    class Completed:
        returncode = 0
        stdout = "regression passed"
        stderr = ""

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return Completed()

    monkeypatch.setattr("agent_runtime.tools.test_tool.subprocess.run", run)
    for manager in ("pnpm", "npm"):
        for script in ("test:unit", "test:smoke", "test:integration", "test:release-gate"):
            result = TestTool().execute(
                {"command": f"{manager} run {script}", "verbose": False}, str(tmp_path)
            )
            assert result.is_ok(), (manager, script, result.blocker)
            assert calls[-1][0] == [manager, "run", script]
            assert calls[-1][1]["shell"] is False
            assert result.metadata["passed"] is True


def test_unknown_script_and_shell_chain_remain_blocked(monkeypatch, tmp_path: Path):
    def unexpected_run(*args, **kwargs):
        raise AssertionError("Rejected commands must not start a process")

    monkeypatch.setattr("agent_runtime.tools.test_tool.subprocess.run", unexpected_run)
    for command in (
        "pnpm run test:unknown", "npm run test:unit-evil", "pnpm run deploy",
        "pnpm run test:unit && touch escaped.txt", "bash -c 'true'",
    ):
        result = TestTool().execute({"command": command}, str(tmp_path))
        assert result.status == "blocked"
        assert result.blocker == "Custom test command is not allowlisted"
        assert "pnpm run test:unit" in result.output
        assert result.metadata["failure_family"] == "TEST_COMMAND_NOT_ALLOWLISTED"
        assert result.exit_code != 0
        assert result.metadata["executed"] is False
        assert not result.metadata.get("passed", False)


def test_custom_pytest_records_real_pass_and_failure(tmp_path: Path):
    test_file = tmp_path / "test_receipt.py"
    for assertion, expected_code in (("True", 0), ("False", 1)):
        test_file.write_text(f"def test_receipt():\n    assert {assertion}\n", encoding="utf-8")
        result = TestTool().execute(
            {"command": "python3 -m pytest -q -p no:cacheprovider test_receipt.py", "verbose": False},
            str(tmp_path),
        )
        assert result.exit_code == expected_code
        assert result.metadata["passed"] is (expected_code == 0)
        assert ("1 passed" if expected_code == 0 else "1 failed") in result.output


def test_test_tool_shipping_mirror_matches():
    root = Path(__file__).resolve().parents[2]
    assert (root / "backend/agent_runtime/tools/test_tool.py").read_bytes() == (
        root / "scripts/sovereign-backend/agent_runtime/tools/test_tool.py"
    ).read_bytes()
