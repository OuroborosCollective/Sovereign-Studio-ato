"""Tool runner for Sovereign Agent Runtime.

This module provides the execution engine for tool calls within
workspace boundaries. It handles tool routing, validation, and
event tracking.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .tools import get_tool_registry, ToolResult, ToolCall
from .tool_events import ToolEventLog, ToolEvent


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
                    "result": {
                        "status": e.result.status,
                        "output": e.result.output,
                        "error": e.result.error,
                        "blocker": e.result.blocker,
                        "metadata": e.result.metadata,
                    },
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
    """Executes tool calls with workspace scoping and event tracking.
    
    The runner:
    1. Validates tool calls against policy
    2. Executes tools with workspace isolation
    3. Tracks events for audit and debugging
    4. Returns sanitized results
    """

    def __init__(self, workspace_path: str | None = None):
        self.workspace_path = workspace_path
        self.registry = get_tool_registry()
        self.event_log = ToolEventLog()

    def execute(self, tool_calls: list[ToolCall]) -> ToolRunnerResult:
        """Execute a list of tool calls.
        
        Args:
            tool_calls: List of ToolCall objects to execute
            
        Returns:
            ToolRunnerResult with aggregate results
        """
        result = ToolRunnerResult()

        for call in tool_calls:
            execution = self._execute_single(call)
            result.add_execution(execution)

        return result

    def execute_single(self, tool_name: str, parameters: dict[str, Any]) -> ToolExecution:
        """Execute a single tool call.
        
        Args:
            tool_name: Name of the tool to execute
            parameters: Tool-specific parameters
            
        Returns:
            ToolExecution with result and metadata
        """
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
    """Convenience function to run a sequence of tool calls.
    
    Args:
        tools: List of (tool_name, parameters) tuples
        workspace_path: Optional workspace path for scoping
        
    Returns:
        ToolRunnerResult with aggregate results
    """
    runner = ToolRunner(workspace_path)
    calls = [
        ToolCall(tool_name=name, parameters=params, call_id=str(uuid.uuid4())[:8])
        for name, params in tools
    ]
    return runner.execute(calls)


def run_agent_job_tool(
    job_id: str,
    tool_name: str,
    parameters: dict[str, Any],
    workspace_path: str | None = None,
) -> ToolRunnerResult:
    """Run a single tool for an agent job.
    
    This is a convenience wrapper for running individual tools
    in the context of an agent job.
    
    Args:
        job_id: The job ID for tracking
        tool_name: Name of the tool to run
        parameters: Tool parameters
        workspace_path: Optional workspace path
    
    Returns:
        ToolRunnerResult with the tool execution result
    """
    runner = ToolRunner(workspace_path)
    call = ToolCall(
        tool_name=tool_name,
        parameters=parameters,
        call_id=f"{job_id[:8]}-{tool_name[:8]}",
    )
    return runner.execute([call])
