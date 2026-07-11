"""Tool runner for Sovereign Agent Runtime.

This module provides the execution engine for tool calls within workspace
boundaries. It handles tool routing, validation, and event tracking.
"""

from __future__ import annotations

from pathlib import Path
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .tools import get_tool_registry, ToolResult, ToolCall
from .tool_events import ToolEventLog
from .workspace_policy import repo_dir_for_workspace


@dataclass
class ToolExecution:
    """Result of a tool execution with metadata."""
    tool_name: str
    call_id: str
    parameters: dict[str, Any]
    result: ToolResult
    duration_ms: int | None = None
    events: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ToolRunnerResult:
    """Aggregate result of a tool run session."""
    executions: list[ToolExecution] = field(default_factory=list)
    success_count: int = 0
    error_count: int = 0
    blocked_count: int = 0
    total_duration_ms: int = 0

    def add_execution(self, execution: ToolExecution) -> None:
        self.executions.append(execution)
        if execution.result.is_ok():
            self.success_count += 1
        elif execution.result.is_blocked():
            self.blocked_count += 1
        else:
            self.error_count += 1

        if execution.duration_ms:
            self.total_duration_ms += execution.duration_ms

    def is_all_success(self) -> bool:
        return (
            self.success_count == len(self.executions)
            and self.error_count == 0
            and self.blocked_count == 0
        )

    def has_blocked(self) -> bool:
        return self.blocked_count > 0

    def has_errors(self) -> bool:
        return self.error_count > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "executions": [
                {
                    "tool_name": e.tool_name,
                    "call_id": e.call_id,
                    "result": e.result.to_dict(),
                    "duration_ms": e.duration_ms,
                }
                for e in self.executions
            ],
            "success_count": self.success_count,
            "error_count": self.error_count,
            "blocked_count": self.blocked_count,
            "total_duration_ms": self.total_duration_ms,
        }


class ToolRunner:
    """Executes tool calls with workspace scoping and event tracking."""

    def __init__(self, workspace_path: str | None = None):
        self.workspace_path = workspace_path
        self.registry = get_tool_registry()
        self.event_log = ToolEventLog()

    def execute(self, tool_calls: list[ToolCall]) -> ToolRunnerResult:
        """Execute a list of tool calls."""
        result = ToolRunnerResult()

        for call in tool_calls:
            execution = self._execute_single(call)
            result.add_execution(execution)

        return result

    def execute_single(self, tool_name: str, parameters: dict[str, Any]) -> ToolExecution:
        """Execute a single tool call."""
        call = ToolCall(
            tool_name=tool_name,
            parameters=parameters,
            call_id=str(uuid.uuid4())[:8],
        )
        return self._execute_single(call)

    def _execute_single(self, call: ToolCall) -> ToolExecution:
        """Execute a single tool call with timing and event tracking."""
        start_time = time.time()
        call_id = call.call_id or str(uuid.uuid4())[:8]

        self.event_log.tool_started(call.tool_name, call_id)

        tool_result = self.registry.execute_tool(
            tool_name=call.tool_name,
            params=call.parameters,
            workspace_path=self.workspace_path,
        )

        duration_ms = int((time.time() - start_time) * 1000)

        if tool_result.is_blocked():
            self.event_log.tool_blocked(
                call.tool_name,
                tool_result.blocker or "Unknown blocker",
                call_id,
            )
        elif tool_result.is_error():
            self.event_log.tool_error(
                call.tool_name,
                tool_result.error or "Unknown error",
                call_id,
            )
        else:
            self.event_log.tool_completed(
                call.tool_name,
                call_id,
                duration_ms,
                tool_result.metadata,
            )

        return ToolExecution(
            tool_name=call.tool_name,
            call_id=call_id,
            parameters=call.parameters,
            result=tool_result,
            duration_ms=duration_ms,
            events=self.event_log.to_dict_list(),
        )

    def list_available_tools(self) -> list[dict[str, Any]]:
        """List all registered tools with their parameters."""
        return self.registry.list_tools()

    def get_events(self) -> list[dict[str, Any]]:
        """Get all logged tool events."""
        return self.event_log.to_dict_list()

    def clear_events(self) -> None:
        """Clear the event log."""
        self.event_log.clear()


def run_tool_sequence(
    tools: list[tuple[str, dict[str, Any]]],
    workspace_path: str | None = None,
) -> ToolRunnerResult:
    """Convenience function to run a sequence of tool calls."""
    runner = ToolRunner(workspace_path)
    calls = [
        ToolCall(tool_name=name, parameters=params, call_id=str(uuid.uuid4())[:8])
        for name, params in tools
    ]
    return runner.execute(calls)


def _resolve_job_id(job_or_id: Any) -> str:
    return str(getattr(job_or_id, "job_id", job_or_id))


def _resolve_workspace_id(job_or_id: Any) -> str:
    return str(getattr(job_or_id, "workspace_id", None) or getattr(job_or_id, "job_id", job_or_id))


def _resolve_workspace_path(job_or_id: Any, root_or_path: str | Path | None) -> str | None:
    if root_or_path is None:
        return None
    root = Path(root_or_path)
    if hasattr(job_or_id, "job_id"):
        return str(repo_dir_for_workspace(_resolve_workspace_id(job_or_id), root))
    return str(root)


def _normalize_route_tool(action: str, parameters: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if action == "file":
        mode = str(parameters.get("mode") or parameters.get("action") or ("write" if "content" in parameters else "read")).lower()
        path = parameters.get("path") or parameters.get("relativePath") or ""
        if mode == "write":
            return "file_write", {
                "path": path,
                "content": str(parameters.get("content") or ""),
                "append": bool(parameters.get("append", False)),
            }
        return "file_read", {"path": path, "max_bytes": parameters.get("maxBytes", parameters.get("max_bytes", 1_000_000))}
    if action == "git-status":
        return "git_status", {}
    if action == "diff":
        return "git_diff", {
            "file": parameters.get("file"),
            "staged": bool(parameters.get("staged", False)),
            "stat": bool(parameters.get("stat", False)),
        }
    if action == "test":
        command = parameters.get("command")
        argv = parameters.get("argv")
        if not command and isinstance(argv, list):
            command = " ".join(str(part) for part in argv)
        return "test", {
            "command": command,
            "path": parameters.get("path"),
            "framework": parameters.get("framework"),
            "timeout": parameters.get("timeout", 300),
            "verbose": parameters.get("verbose", True),
        }
    if action == "janitor":
        return "janitor", dict(parameters)
    return action, parameters


def _changed_files_from_status(output: str | None, metadata: dict[str, Any]) -> tuple[str, ...]:
    files = metadata.get("files") if isinstance(metadata, dict) else None
    if isinstance(files, list):
        parsed = []
        for entry in files:
            text = str(entry).strip()
            if not text:
                continue
            parsed.append(text[3:] if len(text) > 3 and text[2] == " " else text.split()[-1])
        return tuple(dict.fromkeys(parsed))
    parsed = []
    for line in (output or "").splitlines():
        text = line.strip()
        if text and text != "Repository is clean":
            parsed.append(text[3:] if len(text) > 3 and text[2] == " " else text.split()[-1])
    return tuple(dict.fromkeys(parsed))


def _route_result(action: str, tool_name: str, execution: ToolExecution) -> ToolResult:
    result = execution.result
    output = result.output or ""
    error = result.error or ""
    changed_files: tuple[str, ...] = ()
    diff_summary = None
    test_summary = None

    if action == "file" and tool_name == "file_write" and result.status == "done":
        path = str(execution.parameters.get("path") or "")
        changed_files = (path,) if path else ()
    elif action == "git-status":
        changed_files = _changed_files_from_status(output, result.metadata)
    elif action == "diff":
        diff_summary = output[:4000]
    elif action == "test":
        test_summary = output[:4000]
    elif action == "janitor":
        changed_files = result.changed_files
        diff_summary = result.diff_summary
        test_summary = result.test_summary

    predictive_signal = {
        "file": "agent_file_tool_completed",
        "git-status": "agent_git_status_completed",
        "diff": "agent_diff_ready",
        "test": "agent_tests_completed",
        "janitor": result.predictive_signal,
    }.get(action, "agent_tool_result")
    if result.status == "blocked":
        predictive_signal = "agent_tool_blocked"
    elif result.status == "error":
        predictive_signal = "agent_tool_failed"

    return ToolResult(
        status="error" if result.status == "error" else result.status,
        output=output,
        error=error or None,
        blocker=result.blocker,
        metadata=result.metadata,
        tool=action,
        allowed=result.status == "done",
        stdout=output,
        stderr=error or None,
        changed_files=changed_files,
        diff_summary=diff_summary,
        test_summary=test_summary,
        exit_code=(
            result.exit_code
            if result.exit_code is not None
            else (0 if result.status == "done" else 1)
        ),
        events=(),
        predictive_signal=predictive_signal,
    )


def run_agent_job_tool(
    job_or_id: Any,
    tool_name: str,
    parameters: dict[str, Any] | None = None,
    workspace_path: str | Path | None = None,
) -> ToolResult:
    """Run a single route tool for an agent job and return route-compatible ToolResult.

    Supports both the user route call shape `(job, action, payload, workspace_root)`
    and the direct runner call shape `(job_id, tool_name, params, workspace_path)`.
    """
    params = parameters or {}
    normalized_tool, normalized_params = _normalize_route_tool(tool_name, params)
    resolved_workspace = _resolve_workspace_path(job_or_id, workspace_path)
    call_id = f"{_resolve_job_id(job_or_id)[:8]}-{normalized_tool[:8]}"

    runner = ToolRunner(resolved_workspace)
    execution = runner._execute_single(ToolCall(tool_name=normalized_tool, parameters=normalized_params, call_id=call_id))
    return _route_result(tool_name, normalized_tool, execution)
