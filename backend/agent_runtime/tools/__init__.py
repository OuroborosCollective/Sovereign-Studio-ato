"""Sovereign Agent Tools.

This package contains the tool implementations for the Sovereign Agent Runtime.
All tools inherit from ToolBase and are registered in the ToolRegistry.

Available tools:
- file_read: Read files from workspace
- file_write: Write files to workspace
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
"""

from .base import (
    ToolBase,
    ToolResult,
    ToolCall,
    ToolPolicyError,
    ToolRegistry,
    get_tool_registry,
)

from .file_tool import FileReadTool, FileWriteTool, FileListTool
from .shell_tool import ShellTool
from .git_tool import (
    GitStatusTool,
    GitDiffTool,
    GitAddTool,
    GitCommitTool,
    GitLogTool,
)
from .diff_tool import DiffTool, SemanticDiffTool
from .test_tool import TestTool

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
    "DiffTool",
    "SemanticDiffTool",
    "TestTool",
]
