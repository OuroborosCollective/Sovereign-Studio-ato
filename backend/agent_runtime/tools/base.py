"""Tool result contract for internal Sovereign Agent tools."""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Literal

from ..contracts import sanitize_agent_text

ToolStatus = Literal["done", "blocked", "failed"]
ToolEventLevel = Literal["info", "warning", "error", "success"]


@dataclass(frozen=True)
class ToolEvent:
    stage: str
    level: ToolEventLevel
    message: str
    at: int = field(default_factory=lambda: int(time.time() * 1000))


@dataclass(frozen=True)
class ToolResult:
    tool: str
    allowed: bool
    status: ToolStatus
    stdout: str = ""
    stderr: str = ""
    changed_files: tuple[str, ...] = ()
    diff_summary: str | None = None
    test_summary: str | None = None
    blocker: str | None = None
    exit_code: int | None = None
    events: tuple[ToolEvent, ...] = ()
    predictive_signal: str | None = None


def tool_event(stage: str, level: ToolEventLevel, message: str) -> ToolEvent:
    return ToolEvent(
        stage=sanitize_agent_text(stage, 80),
        level=level,
        message=sanitize_agent_text(message, 1200),
    )


def blocked_tool_result(tool: str, blocker: str, *, predictive_signal: str | None = None) -> ToolResult:
    clean = sanitize_agent_text(blocker, 1200)
    return ToolResult(
        tool=tool,
        allowed=False,
        status="blocked",
        blocker=clean,
        events=(tool_event(f"{tool}_tool_blocked", "warning", clean),),
        predictive_signal=predictive_signal or "agent_tool_blocked",
    )


def failed_tool_result(tool: str, stderr: str, *, exit_code: int | None = None, predictive_signal: str | None = None) -> ToolResult:
    clean = sanitize_agent_text(stderr, 2000)
    return ToolResult(
        tool=tool,
        allowed=True,
        status="failed",
        stderr=clean,
        blocker=clean,
        exit_code=exit_code,
        events=(tool_event(f"{tool}_tool_failed", "error", clean),),
        predictive_signal=predictive_signal or "agent_tool_failed",
    )


def done_tool_result(
    tool: str,
    *,
    stdout: str = "",
    stderr: str = "",
    changed_files: tuple[str, ...] = (),
    diff_summary: str | None = None,
    test_summary: str | None = None,
    exit_code: int | None = 0,
    predictive_signal: str | None = None,
) -> ToolResult:
    return ToolResult(
        tool=tool,
        allowed=True,
        status="done",
        stdout=sanitize_agent_text(stdout, 4000),
        stderr=sanitize_agent_text(stderr, 2000),
        changed_files=changed_files,
        diff_summary=sanitize_agent_text(diff_summary, 4000) if diff_summary else None,
        test_summary=sanitize_agent_text(test_summary, 4000) if test_summary else None,
        exit_code=exit_code,
        events=(tool_event(f"{tool}_tool_completed", "success", f"{tool} tool completed."),),
        predictive_signal=predictive_signal or f"agent_{tool}_tool_completed",
    )
