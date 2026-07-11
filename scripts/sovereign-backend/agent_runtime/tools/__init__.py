"""Sovereign Agent Tools.

This package contains the tool implementations for the Sovereign Agent Runtime.
All tools inherit from ToolBase and are registered in the ToolRegistry.

Available tools:
- file_read: Read files from workspace
- file_write: Write files from workspace
- file_list: List directory contents
- shell: Execute shell commands
- git_status: Get git repository status
- git_diff: Get git diff
- git_add: Stage files for commit
- git_commit: Create a commit
- git_log: Get commit history
- diff: Compare two files or strings
- semantic_diff: Analyze code changes semantically
- test: Run test suites
- janitor: Deterministic AST/regex scan and confirmed exact patch
"""

from .base import (
    ToolBase,
    ToolResult,
    ToolCall,
    ToolPolicyError,
    ToolRegistry,
    get_tool_registry,
)

# Re-export ToolEvent from tool_events for convenience
from ..tool_events import ToolEvent

from .file_tool import FileReadTool, FileWriteTool, FileListTool
from .shell_tool import ShellTool
from .git_tool import (
    GitStatusTool,
    GitDiffTool,
    GitAddTool,
    GitCommitTool,
    GitLogTool,
    GitUniversalTool,
)
from .diff_tool import DiffTool, SemanticDiffTool
from .test_tool import TestTool
from .janitor_tool import DynamicJanitorTool

__all__ = [
    "ToolBase",
    "ToolResult",
    "ToolCall",
    "ToolPolicyError",
    "ToolRegistry",
    "get_tool_registry",
    "FileReadTool",
    "FileWriteTool",
    "FileListTool",
    "ShellTool",
    "GitStatusTool",
    "GitDiffTool",
    "GitAddTool",
    "GitCommitTool",
    "GitLogTool",
    "GitUniversalTool",
    "DiffTool",
    "SemanticDiffTool",
    "TestTool",
    "DynamicJanitorTool",
    # Convenience result constructors
    "blocked_tool_result",
    "done_tool_result",
    "failed_tool_result",
    # Workspace helpers
    "read_workspace_file",
    "write_workspace_file",
    "run_workspace_shell_command",
    "run_workspace_test_command",
    "collect_git_status",
    "collect_git_diff_summary",
]


# Convenience result constructors
def blocked_tool_result(reason: str, tool: str = "unknown") -> dict:
    """Create a blocked tool result."""
    return {
        "ok": False,
        "tool": tool,
        "error": f"Tool blocked: {reason}",
        "blocked": True,
    }


def done_tool_result(output: str, tool: str = "unknown") -> dict:
    """Create a successful tool result."""
    return {
        "ok": True,
        "tool": tool,
        "output": output,
    }


def failed_tool_result(error: str, tool: str = "unknown") -> dict:
    """Create a failed tool result."""
    return {
        "ok": False,
        "tool": tool,
        "error": error,
    }


# Workspace helper functions
def read_workspace_file(workspace_path: str, file_path: str) -> dict:
    """Read a file from workspace."""
    import os
    full_path = os.path.join(workspace_path, file_path)
    try:
        with open(full_path, "r") as f:
            return done_tool_result(f.read(), f"read:{file_path}")
    except Exception as e:
        return failed_tool_result(str(e), f"read:{file_path}")


def write_workspace_file(workspace_path: str, file_path: str, content: str) -> dict:
    """Write a file to workspace."""
    import os
    full_path = os.path.join(workspace_path, file_path)
    try:
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            f.write(content)
        return done_tool_result(f"Written: {file_path}", f"write:{file_path}")
    except Exception as e:
        return failed_tool_result(str(e), f"write:{file_path}")


def run_workspace_shell_command(workspace_path: str, command: str) -> dict:
    """Run a shell command in workspace."""
    import subprocess
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=workspace_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = result.stdout + result.stderr
        if result.returncode == 0:
            return done_tool_result(output, f"shell:{command[:20]}")
        else:
            return failed_tool_result(output, f"shell:{command[:20]}")
    except Exception as e:
        return failed_tool_result(str(e), f"shell:{command[:20]}")


def run_workspace_test_command(workspace_path: str, test_command: str = "pytest") -> dict:
    """Run tests in workspace."""
    return run_workspace_shell_command(workspace_path, test_command)


def collect_git_status(workspace_path: str) -> dict:
    """Collect git status from workspace."""
    return run_workspace_shell_command(workspace_path, "git status --porcelain")


def collect_git_diff_summary(workspace_path: str) -> dict:
    """Collect git diff summary from workspace."""
    return run_workspace_shell_command(workspace_path, "git diff --stat")
