"""Policy-guarded diff summary tool."""

from __future__ import annotations

from pathlib import Path

from ..git_workspace import git_diff_summary
from .base import ToolResult, blocked_tool_result, done_tool_result, failed_tool_result


def collect_git_diff_summary(workspace_id: str, root: Path | None = None) -> ToolResult:
    result = git_diff_summary(workspace_id, root)
    if result.status == "done":
        return done_tool_result(
            "diff",
            diff_summary=result.diff_summary or "",
            exit_code=result.exit_code,
            predictive_signal="agent_diff_ready",
        )
    if result.status == "blocked":
        return blocked_tool_result("diff", result.blocker or "Diff collection blocked.", predictive_signal="agent_diff_blocked")
    return failed_tool_result("diff", result.blocker or "Diff collection failed.", exit_code=result.exit_code, predictive_signal="agent_diff_failed")
