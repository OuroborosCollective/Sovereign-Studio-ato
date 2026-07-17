"""File tools for Sovereign Agent Runtime.

Provides safe file read/write operations within workspace boundaries.
All file operations are validated against workspace policy.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from .base import ToolBase, ToolResult, ToolPolicyError


class FileReadTool(ToolBase):
    """Read a file from the workspace."""

    name = "file_read"
    description = "Read contents of a file from the workspace"
    parameters = {
        "path": {
            "type": "string",
            "required": True,
            "description": "Relative path to the file within workspace",
        },
        "max_bytes": {
            "type": "integer",
            "required": False,
            "default": 1_000_000,
            "description": "Maximum bytes to read (default: 1MB)",
        },
    }
    requires_workspace = True

    def execute(self, params: dict[str, Any], workspace_path: str | None = None) -> ToolResult:
        if not workspace_path:
            return ToolResult(status="blocked", blocker="No workspace path provided")

        rel_path = params.get("path", "")
        max_bytes = params.get("max_bytes", 1_000_000)

        if not rel_path or rel_path.startswith("/"):
            return ToolResult(
                status="blocked",
                blocker="File path must be relative and non-empty",
            )

        try:
            target = Path(workspace_path) / rel_path
            target = target.resolve()
            workspace_root = Path(workspace_path).resolve()

            if not target.is_relative_to(workspace_root):
                return ToolResult(
                    status="blocked",
                    blocker="Path escape attempt detected",
                )

            if not target.exists():
                return ToolResult(status="error", error=f"File not found: {rel_path}")

            if not target.is_file():
                return ToolResult(status="error", error=f"Not a file: {rel_path}")

            content_bytes = target.read_bytes()
            if len(content_bytes) > max_bytes:
                return ToolResult(
                    status="blocked",
                    blocker=f"File exceeds max_bytes limit ({len(content_bytes)} > {max_bytes})",
                )

            content = target.read_text(encoding="utf-8", errors="replace")
            return ToolResult(
                status="done",
                output=content,
                metadata={
                    "path": rel_path,
                    "bytes": len(content_bytes),
                    "sha256": hashlib.sha256(content_bytes).hexdigest(),
                },
            )

        except PermissionError:
            return ToolResult(status="error", error=f"Permission denied: {rel_path}")
        except Exception as e:
            return ToolResult(status="error", error=f"Read failed: {e}")


class FileWriteTool(ToolBase):
    """Write content to a file in the workspace."""

    name = "file_write"
    description = "Write content to a file in the workspace"
    parameters = {
        "path": {
            "type": "string",
            "required": True,
            "description": "Relative path to the file within workspace",
        },
        "content": {
            "type": "string",
            "required": True,
            "description": "Content to write to the file",
        },
        "append": {
            "type": "boolean",
            "required": False,
            "default": False,
            "description": "Append to existing file instead of overwriting",
        },
    }
    requires_workspace = True

    def execute(self, params: dict[str, Any], workspace_path: str | None = None) -> ToolResult:
        if not workspace_path:
            return ToolResult(status="blocked", blocker="No workspace path provided")

        rel_path = params.get("path", "")
        content = params.get("content", "")
        append = params.get("append", False)

        if not rel_path or rel_path.startswith("/"):
            return ToolResult(
                status="blocked",
                blocker="File path must be relative and non-empty",
            )

        forbidden_paths = {".git", ".env", "node_modules", "__pycache__", ".pytest_cache"}
        if any(fp in rel_path.split("/") for fp in forbidden_paths):
            return ToolResult(
                status="blocked",
                blocker=f"Writing to '{rel_path}' is forbidden by policy",
            )

        try:
            target = Path(workspace_path) / rel_path
            target = target.resolve()

            if not str(target).startswith(str(Path(workspace_path).resolve())):
                return ToolResult(
                    status="blocked",
                    blocker="Path escape attempt detected",
                )

            target.parent.mkdir(parents=True, exist_ok=True)

            mode = "ab" if append else "wb"
            if not append:
                target.write_bytes(content.encode("utf-8", errors="replace"))
            else:
                with open(target, mode) as f:
                    f.write(content.encode("utf-8", errors="replace"))

            return ToolResult(
                status="done",
                output=f"Written {len(content)} bytes to {rel_path}",
                metadata={"path": rel_path, "bytes": len(content), "append": append},
            )

        except PermissionError:
            return ToolResult(status="error", error=f"Permission denied: {rel_path}")
        except Exception as e:
            return ToolResult(status="error", error=f"Write failed: {e}")


class FileListTool(ToolBase):
    """List files in a directory within the workspace."""

    name = "file_list"
    description = "List files in a directory within the workspace"
    parameters = {
        "path": {
            "type": "string",
            "required": False,
            "default": ".",
            "description": "Relative path to directory (default: workspace root)",
        },
        "recursive": {
            "type": "boolean",
            "required": False,
            "default": False,
            "description": "Recursively list subdirectories",
        },
        "pattern": {
            "type": "string",
            "required": False,
            "description": "Glob pattern to filter files",
        },
    }
    requires_workspace = True

    def execute(self, params: dict[str, Any], workspace_path: str | None = None) -> ToolResult:
        if not workspace_path:
            return ToolResult(status="blocked", blocker="No workspace path provided")

        rel_path = params.get("path", ".")
        recursive = params.get("recursive", False)
        pattern = params.get("pattern", "*")

        if rel_path.startswith("/"):
            return ToolResult(
                status="blocked",
                blocker="Path must be relative",
            )

        try:
            target = Path(workspace_path) / rel_path
            target = target.resolve()

            if not str(target).startswith(str(Path(workspace_path).resolve())):
                return ToolResult(
                    status="blocked",
                    blocker="Path escape attempt detected",
                )

            if not target.exists():
                return ToolResult(status="error", error=f"Directory not found: {rel_path}")

            if not target.is_dir():
                return ToolResult(status="error", error=f"Not a directory: {rel_path}")

            files = []
            if recursive:
                for item in target.rglob(pattern):
                    if item.is_file():
                        rel = item.relative_to(target)
                        files.append(str(rel))
            else:
                for item in target.glob(pattern):
                    if item.is_file():
                        files.append(item.name)

            return ToolResult(
                status="done",
                output="\n".join(sorted(files)),
                metadata={"path": rel_path, "count": len(files)},
            )

        except Exception as e:
            return ToolResult(status="error", error=f"List failed: {e}")
