"""Diff tool for Sovereign Agent Runtime.

Provides diff comparison between files or strings within workspace boundaries.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from .base import ToolBase, ToolResult, ToolPolicyError


class DiffTool(ToolBase):
    """Compare two files or strings and return a diff."""

    name = "diff"
    description = "Compare two files or strings and return a diff"
    parameters = {
        "left": {
            "type": "string",
            "required": True,
            "description": "Left side: file path (relative) or string prefixed with 'text:'",
        },
        "right": {
            "type": "string",
            "required": True,
            "description": "Right side: file path (relative) or string prefixed with 'text:'",
        },
        "context": {
            "type": "integer",
            "required": False,
            "default": 3,
            "description": "Number of context lines (default: 3)",
        },
        "unified": {
            "type": "boolean",
            "required": False,
            "default": True,
            "description": "Use unified diff format (default: True)",
        },
    }
    requires_workspace = True

    def execute(self, params: dict[str, Any], workspace_path: str | None = None) -> ToolResult:
        if not workspace_path:
            return ToolResult(status="blocked", blocker="No workspace path provided")

        left = params.get("left", "")
        right = params.get("right", "")
        context = min(max(params.get("context", 3), 0), 20)
        unified = params.get("unified", True)

        if not left or not right:
            return ToolResult(
                status="blocked",
                blocker="Both left and right parameters are required",
            )

        left_content, left_name = self._resolve_content(left, workspace_path)
        right_content, right_name = self._resolve_content(right, workspace_path)

        if left_content is None or right_content is None:
            return ToolResult(
                status="blocked",
                blocker="Could not resolve content for diff",
            )

        left_lines = left_content.splitlines(keepends=True)
        right_lines = right_content.splitlines(keepends=True)

        if unified:
            diff_lines = list(difflib.unified_diff(
                left_lines,
                right_lines,
                fromfile=left_name,
                tofile=right_name,
                n=context,
            ))
        else:
            diff_lines = list(difflib.context_diff(
                left_lines,
                right_lines,
                fromfile=left_name,
                tofile=right_name,
                n=context,
            ))

        diff_text = "".join(diff_lines)

        has_changes = bool(diff_text.strip())
        stats = self._compute_stats(left_lines, right_lines)

        return ToolResult(
            status="done",
            output=diff_text if has_changes else "Files are identical",
            metadata={
                "left": left_name,
                "right": right_name,
                "identical": not has_changes,
                **stats,
            },
        )

    def _resolve_content(self, source: str, workspace_path: str) -> tuple[str | None, str]:
        """Resolve content from file path or inline text."""
        if source.startswith("text:"):
            return source[5:], f"<text:{len(source)} chars>"

        file_path = Path(workspace_path) / source
        try:
            if not str(file_path.resolve()).startswith(str(Path(workspace_path).resolve())):
                return None, source
            if not file_path.exists():
                return None, source
            return file_path.read_text(errors="replace"), source
        except Exception:
            return None, source

    def _compute_stats(self, left_lines: list[str], right_lines: list[str]) -> dict[str, int]:
        """Compute basic diff statistics."""
        left_set = set(left_lines)
        right_set = set(right_lines)

        added = len(right_set - left_set)
        removed = len(left_set - right_set)
        unchanged = len(left_set & right_set)

        return {
            "lines_left": len(left_lines),
            "lines_right": len(right_lines),
            "lines_added": added,
            "lines_removed": removed,
            "lines_unchanged": unchanged,
        }


class SemanticDiffTool(ToolBase):
    """Perform semantic diff focusing on meaningful changes."""

    name = "semantic_diff"
    description = "Perform semantic diff focusing on meaningful code changes"
    parameters = {
        "file": {
            "type": "string",
            "required": True,
            "description": "File to analyze (relative path)",
        },
        "compare_to": {
            "type": "string",
            "required": False,
            "description": "Git ref to compare against (default: HEAD)",
        },
    }
    requires_workspace = True

    def execute(self, params: dict[str, Any], workspace_path: str | None = None) -> ToolResult:
        if not workspace_path:
            return ToolResult(status="blocked", blocker="No workspace path provided")

        file_path = params.get("file", "")
        compare_to = params.get("compare_to", "HEAD")

        if not file_path:
            return ToolResult(status="blocked", blocker="File parameter required")

        target = Path(workspace_path) / file_path
        if not str(target.resolve()).startswith(str(Path(workspace_path).resolve())):
            return ToolResult(status="blocked", blocker="Path outside workspace")

        try:
            import subprocess

            result = subprocess.run(
                ["git", "diff", compare_to, "--", file_path],
                cwd=workspace_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return ToolResult(
                    status="error",
                    error=f"Git diff failed: {result.stderr}",
                )

            diff_output = result.stdout.strip()

            stats = self._analyze_diff(diff_output)

            return ToolResult(
                status="done",
                output=diff_output if diff_output else "No changes detected",
                metadata={
                    "file": file_path,
                    "compare_to": compare_to,
                    **stats,
                },
            )

        except subprocess.TimeoutExpired:
            return ToolResult(status="blocked", blocker="Diff analysis timed out")
        except Exception as e:
            return ToolResult(status="error", error=f"Analysis failed: {e}")

    def _analyze_diff(self, diff_output: str) -> dict[str, Any]:
        """Analyze diff output for semantic meaning."""
        import re

        additions = len(re.findall(r"^\+[^+]", diff_output, re.MULTILINE))
        deletions = len(re.findall(r"^-[^-]", diff_output, re.MULTILINE))
        functions = re.findall(r"^[+-].*?def\s+(\w+)", diff_output, re.MULTILINE)

        return {
            "lines_added": additions,
            "lines_removed": deletions,
            "functions_changed": len(set(functions)),
            "net_change": additions - deletions,
        }
