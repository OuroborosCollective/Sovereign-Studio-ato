"""Git tools for Sovereign Agent Runtime.

Provides safe git operations within workspace boundaries.
All operations are scoped to the workspace repository.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .base import ToolBase, ToolResult, ToolPolicyError


def _run_git(args: list[str], cwd: str | Path, timeout: int = 60) -> tuple[int, str, str]:
    """Run a git command and return (exit_code, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Git command timed out after {timeout}s"
    except FileNotFoundError:
        return -1, "", "Git not found in PATH"
    except Exception as e:
        return -1, "", str(e)


class GitStatusTool(ToolBase):
    """Get git status of the workspace repository."""

    name = "git_status"
    description = "Get git status of the workspace repository"
    parameters = {}
    requires_workspace = True

    def execute(self, params: dict[str, Any], workspace_path: str | None = None) -> ToolResult:
        if not workspace_path:
            return ToolResult(status="blocked", blocker="No workspace path provided")

        repo_path = Path(workspace_path)
        git_dir = repo_path / ".git"

        if not git_dir.exists():
            return ToolResult(
                status="blocked",
                blocker="Not a git repository (no .git directory)",
            )

        exit_code, stdout, stderr = _run_git(["status", "--porcelain"], repo_path)

        if exit_code != 0:
            return ToolResult(
                status="error",
                error=f"Git status failed: {stderr or stdout}",
            )

        files = [line.strip() for line in stdout.strip().split("\n") if line.strip()]
        return ToolResult(
            status="done",
            output=stdout.strip() if stdout else "Repository is clean",
            metadata={
                "changed_files": len(files),
                "files": files[:100],
            },
        )


class GitDiffTool(ToolBase):
    """Get git diff of the workspace repository."""

    name = "git_diff"
    description = "Get git diff of the workspace repository"
    parameters = {
        "file": {
            "type": "string",
            "required": False,
            "description": "Specific file to diff (relative path)",
        },
        "staged": {
            "type": "boolean",
            "required": False,
            "default": False,
            "description": "Show staged changes instead of unstaged",
        },
        "stat": {
            "type": "boolean",
            "required": False,
            "default": False,
            "description": "Show diffstat only",
        },
    }
    requires_workspace = True

    def execute(self, params: dict[str, Any], workspace_path: str | None = None) -> ToolResult:
        if not workspace_path:
            return ToolResult(status="blocked", blocker="No workspace path provided")

        repo_path = Path(workspace_path)
        git_dir = repo_path / ".git"

        if not git_dir.exists():
            return ToolResult(
                status="blocked",
                blocker="Not a git repository",
            )

        args = ["diff"]
        if params.get("staged"):
            args.append("--staged")
        if params.get("stat"):
            args.append("--stat")
        file_path = params.get("file")
        if file_path:
            target = repo_path / file_path
            if not str(target).startswith(str(repo_path.resolve())):
                return ToolResult(
                    status="blocked",
                    blocker="Path outside workspace",
                )
            args.append("--")
            args.append(file_path)

        exit_code, stdout, stderr = _run_git(args, repo_path)

        if exit_code != 0:
            return ToolResult(
                status="error",
                error=f"Git diff failed: {stderr or stdout}",
            )

        return ToolResult(
            status="done",
            output=stdout.strip() if stdout else "No changes",
            metadata={"file": file_path, "staged": params.get("staged", False)},
        )


class GitAddTool(ToolBase):
    """Stage files in the workspace repository."""

    name = "git_add"
    description = "Stage files in the workspace repository"
    parameters = {
        "files": {
            "type": "array",
            "required": True,
            "description": "Files to stage (relative paths)",
        },
        "all": {
            "type": "boolean",
            "required": False,
            "default": False,
            "description": "Stage all changed files",
        },
    }
    requires_workspace = True

    def execute(self, params: dict[str, Any], workspace_path: str | None = None) -> ToolResult:
        if not workspace_path:
            return ToolResult(status="blocked", blocker="No workspace path provided")

        repo_path = Path(workspace_path)
        git_dir = repo_path / ".git"

        if not git_dir.exists():
            return ToolResult(
                status="blocked",
                blocker="Not a git repository",
            )

        args = ["add"]
        if params.get("all"):
            args.append("-A")
        else:
            files = params.get("files", [])
            if not files:
                return ToolResult(
                    status="blocked",
                    blocker="No files specified to stage",
                )
            for f in files:
                target = repo_path / f
                if not str(target).resolve().startswith(str(repo_path.resolve())):
                    return ToolResult(
                        status="blocked",
                        blocker=f"Path outside workspace: {f}",
                    )
                args.append("--")
                args.append(f)

        exit_code, stdout, stderr = _run_git(args, repo_path)

        if exit_code != 0:
            return ToolResult(
                status="error",
                error=f"Git add failed: {stderr or stdout}",
            )

        return ToolResult(
            status="done",
            output=stdout.strip() if stdout else f"Staged {len(params.get('files', []))} file(s)",
            metadata={"staged_files": params.get("files", [])},
        )


class GitCommitTool(ToolBase):
    """Create a commit in the workspace repository."""

    name = "git_commit"
    description = "Create a commit in the workspace repository"
    parameters = {
        "message": {
            "type": "string",
            "required": True,
            "description": "Commit message",
        },
        "allow_empty": {
            "type": "boolean",
            "required": False,
            "default": False,
            "description": "Allow empty commit",
        },
    }
    requires_workspace = True

    def validate(self, params: dict[str, Any]) -> None:
        super().validate(params)
        message = params.get("message", "")
        if len(message.strip()) < 3:
            raise ToolPolicyError("Commit message too short (minimum 3 characters)")

    def execute(self, params: dict[str, Any], workspace_path: str | None = None) -> ToolResult:
        if not workspace_path:
            return ToolResult(status="blocked", blocker="No workspace path provided")

        repo_path = Path(workspace_path)
        git_dir = repo_path / ".git"

        if not git_dir.exists():
            return ToolResult(
                status="blocked",
                blocker="Not a git repository",
            )

        args = ["commit", "-m", params["message"]]
        if params.get("allow_empty"):
            args.append("--allow-empty")

        exit_code, stdout, stderr = _run_git(args, repo_path)

        if exit_code != 0:
            return ToolResult(
                status="error",
                error=f"Git commit failed: {stderr or stdout}",
            )

        commit_hash = stdout.strip().split("\n")[-1] if stdout else ""
        return ToolResult(
            status="done",
            output=stdout.strip() if stdout else "Commit created",
            metadata={"commit": commit_hash[:7] if commit_hash else None},
        )


class GitLogTool(ToolBase):
    """Get git log of the workspace repository."""

    name = "git_log"
    description = "Get git log of the workspace repository"
    parameters = {
        "max_count": {
            "type": "integer",
            "required": False,
            "default": 10,
            "description": "Maximum number of commits to show",
        },
        "oneline": {
            "type": "boolean",
            "required": False,
            "default": True,
            "description": "Show one line per commit",
        },
    }
    requires_workspace = True

    def execute(self, params: dict[str, Any], workspace_path: str | None = None) -> ToolResult:
        if not workspace_path:
            return ToolResult(status="blocked", blocker="No workspace path provided")

        repo_path = Path(workspace_path)
        git_dir = repo_path / ".git"

        if not git_dir.exists():
            return ToolResult(
                status="blocked",
                blocker="Not a git repository",
            )

        args = ["log", f"-{params.get('max_count', 10)}"]
        if params.get("oneline", True):
            args.append("--oneline")

        exit_code, stdout, stderr = _run_git(args, repo_path)

        if exit_code != 0:
            return ToolResult(
                status="error",
                error=f"Git log failed: {stderr or stdout}",
            )

        return ToolResult(
            status="done",
            output=stdout.strip() if stdout else "No commits",
            metadata={"count": stdout.count("\n") + 1 if stdout.strip() else 0},
        )
