"""Base tool class for Sovereign Agent Runtime.

All tools inherit from ToolBase and implement a minimal execute() contract.
Tools are runtime-verified before any command reaches the filesystem or shell.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """Result of a tool execution.

    Tools return ToolResult, never raw strings or exceptions.
    Exceptions are caught by the tool runner and converted to ToolResult with status='error'.

    The extra route/evidence fields keep the older `/api/user/agent/jobs/<id>/tools/*`
    route contract stable while the internal ToolRegistry remains minimal.
    """

    status: str = "done"  # done | error | blocked
    output: str | None = None
    error: str | None = None
    blocker: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # Compatibility/evidence fields used by routes, events and gates.
    tool: str = "unknown"
    allowed: bool = True
    stdout: str | None = None
    stderr: str | None = None
    changed_files: tuple[str, ...] = ()
    diff_summary: str | None = None
    test_summary: str | None = None
    exit_code: int | None = None
    events: tuple[Any, ...] = ()
    predictive_signal: str = "agent_tool_result"

    def __post_init__(self) -> None:
        if self.status == "blocked":
            self.allowed = False
        if self.stdout is None and self.output is not None:
            self.stdout = self.output
        if self.stderr is None and self.error is not None:
            self.stderr = self.error
        if not self.blocker and self.status == "blocked" and self.error:
            self.blocker = self.error
        if self.exit_code is None:
            self.exit_code = 0 if self.status == "done" else 1

    def is_ok(self) -> bool:
        return self.status == "done"

    def is_blocked(self) -> bool:
        return self.status == "blocked"

    def is_error(self) -> bool:
        return self.status == "error"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.is_ok(),
            "tool": self.tool,
            "status": self.status,
            "output": self.output,
            "stdout": self.stdout,
            "error": self.error,
            "stderr": self.stderr,
            "blocker": self.blocker,
            "metadata": self.metadata,
            "changed_files": list(self.changed_files),
            "diff_summary": self.diff_summary,
            "test_summary": self.test_summary,
            "exit_code": self.exit_code,
            "predictive_signal": self.predictive_signal,
        }


@dataclass
class ToolCall:
    """A single tool invocation request."""
    tool_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    call_id: str | None = None


class ToolPolicyError(ValueError):
    """Raised when a tool call violates Sovereign runtime policy."""


class ToolBase(ABC):
    """Abstract base class for all Sovereign agent tools.

    Each tool:
    - Has a unique name used for registration and routing
    - Declares required/optional parameters in `parameters` dict
    - Implements `execute()` which returns ToolResult
    - Validates inputs in `validate()` before execution
    """

    name: str = "base_tool"
    description: str = "Abstract base tool"
    parameters: dict[str, dict[str, Any]] = field(default_factory=dict)
    requires_workspace: bool = False

    @abstractmethod
    def execute(self, params: dict[str, Any], workspace_path: str | None = None) -> ToolResult:
        """Execute the tool with given parameters.

        Args:
            params: Tool-specific parameters
            workspace_path: Optional workspace directory path

        Returns:
            ToolResult with status, output, and metadata
        """

    def validate(self, params: dict[str, Any]) -> None:
        """Validate parameters before execution.

        Raises ToolPolicyError if validation fails.
        Subclasses should override to add parameter validation.
        """
        for required_param in self._required_parameters():
            if required_param not in params or params[required_param] is None:
                raise ToolPolicyError(f"Missing required parameter: {required_param}")

    def _required_parameters(self) -> list[str]:
        return [
            name for name, spec in self.parameters.items()
            if spec.get("required", False)
        ]

    def _sanitize_output(self, output: str, max_length: int = 100_000) -> str:
        """Sanitize tool output to prevent information leakage."""
        if not output:
            return ""
        if len(output) > max_length:
            return output[:max_length] + f"\n... [output truncated, {len(output) - max_length} chars hidden]"
        return output


class ToolRegistry:
    """Central registry for all Sovereign agent tools.

    Provides tool lookup and execution routing.
    """

    def __init__(self):
        self._tools: dict[str, ToolBase] = {}

    def register(self, tool: ToolBase) -> None:
        """Register a tool by its name."""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolBase | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, Any]]:
        """List all registered tools with metadata."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "requires_workspace": tool.requires_workspace,
            }
            for tool in self._tools.values()
        ]

    def execute_tool(
        self,
        tool_name: str,
        params: dict[str, Any],
        workspace_path: str | None = None,
    ) -> ToolResult:
        """Execute a tool by name with given parameters."""
        tool = self.get(tool_name)
        if not tool:
            return ToolResult(
                status="error",
                tool=tool_name,
                error=f"Unknown tool: {tool_name}",
                predictive_signal="agent_tool_unknown",
            )
        try:
            tool.validate(params)
            result = tool.execute(params, workspace_path)
            result.tool = tool_name
            return result
        except ToolPolicyError as e:
            return ToolResult(
                status="blocked",
                tool=tool_name,
                blocker=str(e),
                predictive_signal="agent_tool_policy_blocked",
            )
        except Exception as e:
            return ToolResult(
                status="error",
                tool=tool_name,
                error=str(e),
                predictive_signal="agent_tool_failed",
            )


# Global tool registry instance
_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry instance."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _register_default_tools(_registry)
    return _registry


def _register_default_tools(registry: ToolRegistry) -> None:
    """Register all default Sovereign tools."""
    from .file_tool import FileReadTool, FileWriteTool
    from .shell_tool import ShellTool
    from .git_tool import GitStatusTool, GitDiffTool, GitAddTool, GitUniversalTool
    from .diff_tool import DiffTool
    from .test_tool import TestTool

    registry.register(FileReadTool())
    registry.register(FileWriteTool())
    registry.register(ShellTool())
    registry.register(GitStatusTool())
    registry.register(GitDiffTool())
    registry.register(GitAddTool())
    registry.register(GitUniversalTool())
    registry.register(DiffTool())
    registry.register(TestTool())
