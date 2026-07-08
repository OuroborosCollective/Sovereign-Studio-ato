"""Policy-guarded shell command tool for Sovereign Agent Runtime."""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Sequence

from ..contracts import sanitize_agent_text
from ..tool_policy import validate_repo_ready, validate_shell_command
from ..workspace_policy import repo_dir_for_workspace
from .base import ToolResult, blocked_tool_result, done_tool_result, failed_tool_result

DEFAULT_TIMEOUT_SECONDS = 120


def run_workspace_shell_command(
    workspace_id: str,
    argv: Sequence[str],
    root: Path | None = None,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> ToolResult:
    repo_policy = validate_repo_ready(workspace_id, root)
    command_policy = validate_shell_command(argv)
    blockers = repo_policy.messages + command_policy.messages
    if not repo_policy.allowed or not command_policy.allowed:
        return blocked_tool_result("shell", "; ".join(blockers), predictive_signal="agent_shell_policy_blocked")
    try:
        completed = subprocess.run(
            [str(part) for part in argv],
            cwd=str(repo_dir_for_workspace(workspace_id, root)),
            text=True,
            capture_output=True,
            shell=False,
            timeout=timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            return failed_tool_result(
                "shell",
                sanitize_agent_text(completed.stderr or completed.stdout or "Command failed.", 2000),
                exit_code=completed.returncode,
                predictive_signal="agent_shell_command_failed",
            )
        return done_tool_result(
            "shell",
            stdout=sanitize_agent_text(completed.stdout, 4000),
            stderr=sanitize_agent_text(completed.stderr, 2000),
            exit_code=completed.returncode,
            predictive_signal="agent_shell_command_completed",
        )
    except subprocess.TimeoutExpired:
        return failed_tool_result("shell", "Command timed out.", predictive_signal="agent_shell_timeout")
    except Exception as exc:
        return failed_tool_result("shell", str(exc), predictive_signal="agent_shell_failed")
