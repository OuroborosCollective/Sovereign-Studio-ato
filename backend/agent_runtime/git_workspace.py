"""Git operations for Sovereign Agent Runtime workspaces.

All commands use argv lists with shell disabled. This module validates repo URL,
branch and workspace paths before Git is invoked. It never logs tokens and never
pushes directly to main.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import subprocess
import time
from typing import Literal, Sequence

from .contracts import SovereignAgentEvent, normalize_agent_paths, sanitize_agent_text
from .workspace_policy import (
    WorkspacePolicyError,
    repo_dir_for_workspace,
    safe_workspace_path,
    validate_repo_url_for_workspace,
    validate_workspace_branch,
)

GitOperationStatus = Literal["done", "blocked", "failed"]


@dataclass(frozen=True)
class GitWorkspaceResult:
    status: GitOperationStatus
    command: tuple[str, ...] = ()
    changed_files: tuple[str, ...] = ()
    diff_summary: str | None = None
    events: tuple[SovereignAgentEvent, ...] = field(default_factory=tuple)
    blocker: str | None = None
    exit_code: int | None = None


def _event(stage: str, level: Literal["info", "warning", "error", "success"], message: str) -> SovereignAgentEvent:
    return SovereignAgentEvent(
        stage=sanitize_agent_text(stage, 80),
        level=level,
        message=sanitize_agent_text(message, 1200),
        at=int(time.time() * 1000),
    )


def build_git_clone_command(repo_url: str, branch: str, target_dir: Path) -> tuple[str, ...]:
    safe_repo = validate_repo_url_for_workspace(repo_url)
    safe_branch = validate_workspace_branch(branch)
    return (
        "git",
        "clone",
        "--depth",
        "1",
        "--branch",
        safe_branch,
        safe_repo,
        str(target_dir),
    )


def run_git_command(args: Sequence[str], cwd: Path, timeout_seconds: int = 120) -> subprocess.CompletedProcess[str]:
    if not args or args[0] != "git":
        raise WorkspacePolicyError("only git commands are allowed in git workspace runtime")
    return subprocess.run(
        list(args),
        cwd=str(cwd),
        text=True,
        capture_output=True,
        shell=False,
        timeout=timeout_seconds,
        check=False,
    )


def clone_repo_into_workspace(
    workspace_id: str,
    repo_url: str,
    branch: str = "main",
    root: Path | None = None,
    timeout_seconds: int = 120,
) -> GitWorkspaceResult:
    try:
        workspace = safe_workspace_path(workspace_id, root)
        repo_path = repo_dir_for_workspace(workspace_id, root)
        if not workspace.exists():
            return GitWorkspaceResult(
                status="blocked",
                events=(_event("repo_clone_blocked", "warning", "Workspace does not exist."),),
                blocker="Workspace does not exist.",
            )
        if any(repo_path.iterdir()):
            return GitWorkspaceResult(
                status="blocked",
                events=(_event("repo_clone_blocked", "warning", "Repo directory is not empty."),),
                blocker="Repo directory is not empty.",
            )
        command = build_git_clone_command(repo_url, branch, repo_path)
        completed = run_git_command(command, workspace, timeout_seconds)
        if completed.returncode != 0:
            return GitWorkspaceResult(
                status="failed",
                command=command[:6] + ("[repo-url-redacted]", str(repo_path)),
                events=(_event("repo_clone_failed", "error", completed.stderr or completed.stdout or "git clone failed"),),
                blocker=sanitize_agent_text(completed.stderr or completed.stdout or "git clone failed", 1200),
                exit_code=completed.returncode,
            )
        return GitWorkspaceResult(
            status="done",
            command=command[:6] + ("[repo-url-redacted]", str(repo_path)),
            events=(_event("repo_clone_completed", "success", "Repository snapshot ready."),),
            exit_code=completed.returncode,
        )
    except Exception as exc:
        return GitWorkspaceResult(
            status="blocked",
            events=(_event("repo_clone_blocked", "warning", str(exc)),),
            blocker=sanitize_agent_text(str(exc), 1200),
        )


def git_status_changed_files(workspace_id: str, root: Path | None = None) -> GitWorkspaceResult:
    try:
        repo_path = repo_dir_for_workspace(workspace_id, root)
        if not repo_path.exists():
            return GitWorkspaceResult(
                status="blocked",
                events=(_event("git_status_blocked", "warning", "Repo directory does not exist."),),
                blocker="Repo directory does not exist.",
            )
        completed = run_git_command(("git", "status", "--short"), repo_path, 30)
        if completed.returncode != 0:
            return GitWorkspaceResult(
                status="failed",
                events=(_event("git_status_failed", "error", completed.stderr or "git status failed"),),
                blocker=sanitize_agent_text(completed.stderr or "git status failed", 1200),
                exit_code=completed.returncode,
            )
        files = []
        for line in completed.stdout.splitlines():
            if len(line) < 4:
                continue
            path = line[3:].strip()
            if " -> " in path:
                path = path.split(" -> ", 1)[1].strip()
            files.append(path)
        return GitWorkspaceResult(
            status="done",
            command=("git", "status", "--short"),
            changed_files=normalize_agent_paths(files),
            events=(_event("git_status_completed", "success", "Git status collected."),),
            exit_code=completed.returncode,
        )
    except Exception as exc:
        return GitWorkspaceResult(
            status="blocked",
            events=(_event("git_status_blocked", "warning", str(exc)),),
            blocker=sanitize_agent_text(str(exc), 1200),
        )


def git_diff_summary(workspace_id: str, root: Path | None = None, max_chars: int = 4000) -> GitWorkspaceResult:
    try:
        repo_path = repo_dir_for_workspace(workspace_id, root)
        if not repo_path.exists():
            return GitWorkspaceResult(
                status="blocked",
                events=(_event("git_diff_blocked", "warning", "Repo directory does not exist."),),
                blocker="Repo directory does not exist.",
            )
        completed = run_git_command(("git", "diff", "--stat"), repo_path, 30)
        if completed.returncode != 0:
            return GitWorkspaceResult(
                status="failed",
                events=(_event("git_diff_failed", "error", completed.stderr or "git diff failed"),),
                blocker=sanitize_agent_text(completed.stderr or "git diff failed", 1200),
                exit_code=completed.returncode,
            )
        return GitWorkspaceResult(
            status="done",
            command=("git", "diff", "--stat"),
            diff_summary=sanitize_agent_text(completed.stdout, max_chars),
            events=(_event("git_diff_completed", "success", "Git diff summary collected."),),
            exit_code=completed.returncode,
        )
    except Exception as exc:
        return GitWorkspaceResult(
            status="blocked",
            events=(_event("git_diff_blocked", "warning", str(exc)),),
            blocker=sanitize_agent_text(str(exc), 1200),
        )
