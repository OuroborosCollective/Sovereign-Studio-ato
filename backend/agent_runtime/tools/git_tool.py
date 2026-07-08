"""Policy-guarded Git status tool."""

from __future__ import annotations

from pathlib import Path

from ..git_workspace import git_status_changed_files
from .base import ToolResult, done_tool_result, failed_tool_result


def collect_git_status(workspace_id: str, root: Path | None = None) -> ToolResult:
    result = git_status_changed_files(workspace_id, root)
    if result.status == "done":
        return done_tool_result(
            "git",
            changed_files=result.changed_files,
            exit_code=result.exit_code,
            predictive_signal="agent_git_status_completed",
        )
    if result.status == "blocked":
        from .base import blocked_tool_result

        return blocked_tool_result("git", result.blocker or "Git status blocked.", predictive_signal="agent_git_status_blocked")
    return failed_tool_result("git", result.blocker or "Git status failed.", exit_code=result.exit_code, predictive_signal="agent_git_status_failed")
