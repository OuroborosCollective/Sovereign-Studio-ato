from __future__ import annotations

import os
import sys
from pathlib import Path

# Füge Backend zum Python Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.tool_policy import (  # noqa: E402
    resolve_repo_tool_path,
    validate_shell_command,
    validate_tool_path,
    validate_workspace_ready,
)
from agent_runtime.workspace import create_agent_workspace  # noqa: E402


def test_workspace_ready_blocks_missing_workspace(tmp_path: Path):
    result = validate_workspace_ready("agent-missing", tmp_path)

    assert result.allowed is False
    assert "tool_requires_workspace" in result.blockers


def test_tool_path_blocks_secret_and_git_paths():
    secret = validate_tool_path(".env")
    git = validate_tool_path(".git/config")

    assert secret.allowed is False
    assert "tool_secret_path_blocked" in secret.blockers
    assert git.allowed is False
    assert "tool_path_forbidden" in git.blockers


def test_tool_path_blocks_generated_write_targets():
    result = validate_tool_path("dist/bundle.js", write=True)

    assert result.allowed is False
    assert "tool_path_forbidden" in result.blockers


def test_resolve_repo_tool_path_stays_inside_repo(tmp_path: Path):
    create_agent_workspace("agent-1", tmp_path)

    target, policy = resolve_repo_tool_path("agent-1", "src/example.ts", tmp_path, write=True)

    assert policy.allowed is True
    assert target is not None
    assert target == tmp_path / "agent-1" / "repo" / "src" / "example.ts"


def test_resolve_repo_tool_path_blocks_escape(tmp_path: Path):
    create_agent_workspace("agent-1", tmp_path)

    target, policy = resolve_repo_tool_path("agent-1", "../escape.txt", tmp_path, write=True)

    assert target is None
    assert policy.allowed is False


def test_shell_policy_allows_release_gate_commands():
    assert validate_shell_command(("pnpm", "run", "type-check")).allowed is True
    assert validate_shell_command(("python", "-m", "pytest", "backend/tests/test_agent_tool_policy.py", "-v")).allowed is True
    assert validate_shell_command(("git", "status", "--short")).allowed is True


def test_shell_policy_blocks_forbidden_or_unknown_commands():
    forbidden = validate_shell_command(("sudo", "rm", "-rf", "/"))
    unknown = validate_shell_command(("node", "scripts/random-live-write.js"))

    assert forbidden.allowed is False
    assert "tool_command_forbidden" in forbidden.blockers
    assert unknown.allowed is False
    assert "tool_command_not_allowlisted" in unknown.blockers
