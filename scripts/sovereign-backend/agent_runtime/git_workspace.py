"""Git operations for Sovereign Agent Runtime workspaces.

All commands use argv lists with shell disabled. This module validates repo URL,
branch and workspace paths before Git is invoked. It never logs tokens and never
pushes directly to main.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Iterator, Literal, Mapping, Sequence
import uuid

from .contracts import SovereignAgentEvent, normalize_agent_paths, sanitize_agent_text
from .workspace_policy import (
    WorkspacePolicyError,
    repo_dir_for_workspace,
    safe_workspace_path,
    validate_repo_url_for_workspace,
    validate_workspace_branch,
)

GitOperationStatus = Literal["done", "blocked", "failed"]
_GITHUB_EPHEMERAL_TOKEN = re.compile(r"^(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]{8,255}$")


@dataclass(frozen=True)
class GitWorkspaceResult:
    status: GitOperationStatus
    command: tuple[str, ...] = ()
    changed_files: tuple[str, ...] = ()
    diff_summary: str | None = None
    events: tuple[SovereignAgentEvent, ...] = field(default_factory=tuple)
    blocker: str | None = None
    exit_code: int | None = None
    branch_name: str | None = None
    commit_sha: str | None = None


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


def run_git_command(
    args: Sequence[str],
    cwd: Path,
    timeout_seconds: int = 120,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
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
        env=dict(env) if env is not None else None,
    )


def normalize_ephemeral_github_token(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    token = value.strip()
    return token if _GITHUB_EPHEMERAL_TOKEN.fullmatch(token) else None


def resolve_server_github_token() -> str | None:
    for name in (
        "SOVEREIGN_GITHUB_TOKEN",
        "TOOLCHAIN_GITHUB_TOKEN",
        "GITHUB_PERSONAL_ACCESS_TOKEN",
        "GITHUB_TOKEN",
    ):
        token = (os.getenv(name) or "").strip()
        if token:
            return token
    return None


@contextmanager
def git_credential_environment(token: str | None, directory: Path) -> Iterator[Mapping[str, str] | None]:
    if not token:
        yield None
        return
    directory.mkdir(parents=True, exist_ok=True)
    askpass = directory / f".sovereign-git-askpass-{uuid.uuid4().hex}.sh"
    askpass.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  *Username*) printf '%s\\n' 'x-access-token' ;;\n"
        "  *Password*) printf '%s\\n' \"$SOVEREIGN_GIT_PUSH_TOKEN\" ;;\n"
        "  *) exit 1 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    askpass.chmod(0o700)
    env = os.environ.copy()
    env.update({
        "GIT_ASKPASS": str(askpass),
        "GIT_ASKPASS_REQUIRE": "force",
        "GIT_TERMINAL_PROMPT": "0",
        "SOVEREIGN_GIT_PUSH_TOKEN": token,
    })
    try:
        yield env
    finally:
        askpass.unlink(missing_ok=True)


def clone_repo_into_workspace(
    workspace_id: str,
    repo_url: str,
    branch: str = "main",
    root: Path | None = None,
    timeout_seconds: int = 120,
    token: str | None = None,
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
        repo_path.mkdir(parents=True, exist_ok=True)
        if any(repo_path.iterdir()):
            return GitWorkspaceResult(
                status="blocked",
                events=(_event("repo_clone_blocked", "warning", "Repo directory is not empty."),),
                blocker="Repo directory is not empty.",
            )
        command = build_git_clone_command(repo_url, branch, repo_path)
        with git_credential_environment(token or resolve_server_github_token(), workspace) as auth_env:
            completed = run_git_command(command, workspace, timeout_seconds, auth_env)
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
        completed = run_git_command(("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"), repo_path, 30)
        if completed.returncode != 0:
            return GitWorkspaceResult(
                status="failed",
                events=(_event("git_status_failed", "error", completed.stderr or "git status failed"),),
                blocker=sanitize_agent_text(completed.stderr or "git status failed", 1200),
                exit_code=completed.returncode,
            )
        files: list[str] = []
        entries = completed.stdout.split("\0")
        index = 0
        while index < len(entries):
            entry = entries[index]
            index += 1
            if len(entry) < 4:
                continue
            status_code = entry[:2]
            path = entry[3:]
            if path:
                files.append(path)
            if "R" in status_code or "C" in status_code:
                index += 1  # Porcelain -z emits the original path as the next NUL entry.
        return GitWorkspaceResult(
            status="done",
            command=("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"),
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


def git_diff_check(workspace_id: str, root: Path | None = None) -> GitWorkspaceResult:
    try:
        repo_path = repo_dir_for_workspace(workspace_id, root)
        completed = run_git_command(("git", "diff", "--check"), repo_path, 30)
        if completed.returncode != 0:
            reason = completed.stderr or completed.stdout or "git diff --check failed"
            return GitWorkspaceResult(
                status="failed",
                command=("git", "diff", "--check"),
                events=(_event("git_diff_check_failed", "error", reason),),
                blocker=sanitize_agent_text(reason, 1200),
                exit_code=completed.returncode,
            )
        return GitWorkspaceResult(
            status="done",
            command=("git", "diff", "--check"),
            events=(_event("git_diff_check_completed", "success", "Git diff check passed."),),
            exit_code=0,
        )
    except Exception as exc:
        return GitWorkspaceResult(
            status="blocked",
            events=(_event("git_diff_check_blocked", "warning", str(exc)),),
            blocker=sanitize_agent_text(str(exc), 1200),
        )


def publish_workspace_branch(
    workspace_id: str,
    *,
    repo_url: str,
    base_branch: str,
    head_branch: str,
    commit_message: str,
    changed_files: Sequence[str],
    token: str | None = None,
    root: Path | None = None,
    timeout_seconds: int = 120,
) -> GitWorkspaceResult:
    """Commit and push only the declared workspace changes to a non-base branch."""
    try:
        safe_repo = validate_repo_url_for_workspace(repo_url)
        safe_base = validate_workspace_branch(base_branch)
        safe_head = validate_workspace_branch(head_branch)
        if safe_head == safe_base:
            raise WorkspacePolicyError("head branch must differ from base branch")
        files = normalize_agent_paths(changed_files)
        if not files:
            raise WorkspacePolicyError("branch publication requires changed file evidence")
        repo_path = repo_dir_for_workspace(workspace_id, root)
        if not (repo_path / ".git").is_dir():
            raise WorkspacePolicyError("workspace repository is not cloned")

        origin = run_git_command(("git", "remote", "get-url", "origin"), repo_path, 30)
        if origin.returncode != 0:
            raise WorkspacePolicyError(origin.stderr or "git origin is unavailable")
        normalized_origin = origin.stdout.strip().removesuffix(".git")
        if normalized_origin != safe_repo.removesuffix(".git"):
            raise WorkspacePolicyError("workspace origin does not match requested repository")

        status = git_status_changed_files(workspace_id, root)
        if status.status != "done":
            return status
        unexpected = tuple(path for path in status.changed_files if path not in files)
        if unexpected:
            raise WorkspacePolicyError(
                f"workspace contains undeclared changes: {', '.join(unexpected[:10])}"
            )

        current = run_git_command(("git", "branch", "--show-current"), repo_path, 30)
        current_branch = current.stdout.strip() if current.returncode == 0 else ""
        if current_branch != safe_head:
            exists = run_git_command(("git", "show-ref", "--verify", f"refs/heads/{safe_head}"), repo_path, 30)
            checkout = (
                ("git", "checkout", safe_head)
                if exists.returncode == 0
                else ("git", "checkout", "-b", safe_head)
            )
            switched = run_git_command(checkout, repo_path, 30)
            if switched.returncode != 0:
                raise WorkspacePolicyError(switched.stderr or switched.stdout or "git branch checkout failed")

        if status.changed_files:
            added = run_git_command(("git", "add", "-A", "--", *files), repo_path, 30)
            if added.returncode != 0:
                raise WorkspacePolicyError(added.stderr or added.stdout or "git add failed")
            staged_check = run_git_command(("git", "diff", "--cached", "--check"), repo_path, 30)
            if staged_check.returncode != 0:
                raise WorkspacePolicyError(staged_check.stderr or staged_check.stdout or "staged diff check failed")
            run_git_command(("git", "config", "user.name", "Sovereign Runtime"), repo_path, 30)
            run_git_command(("git", "config", "user.email", "sovereign-runtime@users.noreply.github.com"), repo_path, 30)
            safe_message = sanitize_agent_text(commit_message, 160).strip()
            if len(safe_message) < 3:
                raise WorkspacePolicyError("commit message is missing")
            committed = run_git_command(("git", "commit", "-m", safe_message), repo_path, 60)
            if committed.returncode != 0:
                raise WorkspacePolicyError(committed.stderr or committed.stdout or "git commit failed")
        else:
            ahead = run_git_command(("git", "rev-list", "--count", f"{safe_base}..HEAD"), repo_path, 30)
            if ahead.returncode != 0 or int((ahead.stdout or "0").strip() or "0") < 1:
                raise WorkspacePolicyError("workspace has no unpublished commit for the prepared branch")

        safe_token = token or resolve_server_github_token()
        if not safe_token:
            raise WorkspacePolicyError("server GitHub credentials missing for branch publication")
        with git_credential_environment(safe_token, repo_path.parent) as auth_env:
            pushed = run_git_command(
                ("git", "push", "--set-upstream", "origin", safe_head),
                repo_path,
                timeout_seconds,
                auth_env,
            )
        if pushed.returncode != 0:
            raise WorkspacePolicyError(pushed.stderr or pushed.stdout or "git push failed")
        revision = run_git_command(("git", "rev-parse", "HEAD"), repo_path, 30)
        commit_sha = revision.stdout.strip() if revision.returncode == 0 else ""
        if len(commit_sha) != 40:
            raise WorkspacePolicyError("published commit SHA is unavailable")
        return GitWorkspaceResult(
            status="done",
            command=("git", "push", "--set-upstream", "origin", safe_head),
            changed_files=files,
            events=(_event("git_branch_published", "success", "Workspace branch published to GitHub."),),
            exit_code=0,
            branch_name=safe_head,
            commit_sha=commit_sha,
        )
    except Exception as exc:
        reason = sanitize_agent_text(str(exc), 1200)
        return GitWorkspaceResult(
            status="blocked",
            events=(_event("git_branch_publish_blocked", "warning", reason),),
            blocker=reason,
        )
