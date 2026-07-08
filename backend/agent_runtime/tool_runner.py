"""Dispatch internal ToolResult-producing tools for a stored Sovereign Agent job."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Sequence

from .job_store import StoredSovereignAgentJob
from .tools.base import ToolResult, blocked_tool_result
from .tools.diff_tool import collect_git_diff_summary
from .tools.file_tool import read_workspace_file, write_workspace_file
from .tools.git_tool import collect_git_status
from .tools.test_tool import run_workspace_test_command

AgentToolAction = Literal["file", "git-status", "diff", "test"]

_TERMINAL_STATUSES = {"completed", "failed", "blocked", "cleaned"}


def _job_workspace_id(job: StoredSovereignAgentJob) -> str | None:
    return job.workspace_id or job.job_id


def _command_from_payload(payload: dict[str, Any]) -> tuple[str, ...]:
    command = payload.get("argv") or payload.get("command") or ()
    if isinstance(command, str):
        return tuple(part for part in command.split(" ") if part)
    if isinstance(command, Sequence):
        return tuple(str(part) for part in command)
    return ()


def run_agent_job_tool(
    job: StoredSovereignAgentJob,
    action: AgentToolAction,
    payload: dict[str, Any] | None = None,
    root: Path | None = None,
) -> ToolResult:
    body = payload or {}
    if job.status in _TERMINAL_STATUSES:
        return blocked_tool_result("agent", "Terminal agent jobs cannot run tools.", predictive_signal="agent_tool_terminal_blocked")

    workspace_id = _job_workspace_id(job)
    if not workspace_id:
        return blocked_tool_result("agent", "Agent job has no workspace id.", predictive_signal="agent_tool_requires_workspace")

    if action == "file":
        relative_path = str(body.get("path") or body.get("relativePath") or "")
        mode = str(body.get("mode") or body.get("action") or ("write" if "content" in body else "read")).strip().lower()
        if mode == "write":
            return write_workspace_file(workspace_id, relative_path, str(body.get("content") or ""), root)
        if mode == "read":
            return read_workspace_file(workspace_id, relative_path, root)
        return blocked_tool_result("file", "File tool mode must be read or write.", predictive_signal="agent_file_mode_blocked")

    if action == "git-status":
        return collect_git_status(workspace_id, root)

    if action == "diff":
        return collect_git_diff_summary(workspace_id, root)

    if action == "test":
        return run_workspace_test_command(workspace_id, _command_from_payload(body), root)

    return blocked_tool_result("agent", "Unknown agent tool action.", predictive_signal="agent_tool_unknown_blocked")
