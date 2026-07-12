from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Füge Backend zum Python Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime import git_workspace  # noqa: E402
from agent_runtime.git_workspace import (  # noqa: E402
    build_git_clone_command,
    git_diff_summary,
    git_status_changed_files,
    publish_workspace_branch,
)
from agent_runtime.workspace import create_agent_workspace, cleanup_agent_workspace  # noqa: E402
from agent_runtime.workspace_policy import (  # noqa: E402
    WorkspacePolicyError,
    ensure_path_inside_workspace,
    repo_dir_for_workspace,
    safe_workspace_path,
    validate_repo_url_for_workspace,
    validate_workspace_branch,
)


def test_safe_workspace_path_rejects_traversal(tmp_path: Path):
    try:
        safe_workspace_path("../escape", tmp_path)
    except WorkspacePolicyError as exc:
        assert "unsafe" in str(exc) or "traversal" in str(exc)
    else:  # pragma: no cover - explicit safety guard
        raise AssertionError("workspace traversal was not blocked")


def test_create_workspace_creates_isolated_repo_directory(tmp_path: Path):
    result = create_agent_workspace("job-123", tmp_path)

    assert result.status == "created"
    assert result.path is not None
    assert result.repo_path is not None
    assert Path(result.path).exists()
    assert Path(result.repo_path).exists()
    assert Path(result.repo_path).name == "repo"
    assert result.events[0].stage == "workspace_created"


def test_create_existing_workspace_returns_recoverable_state(tmp_path: Path):
    first = create_agent_workspace("job-123", tmp_path)
    second = create_agent_workspace("job-123", tmp_path)

    assert first.status == "created"
    assert second.status == "exists"
    assert second.blocker == "Workspace already exists for this job."
    assert second.events[0].stage == "workspace_exists"


def test_cleanup_workspace_removes_only_job_workspace(tmp_path: Path):
    create_agent_workspace("job-123", tmp_path)
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    (sibling / "keep.txt").write_text("keep", encoding="utf-8")

    result = cleanup_agent_workspace("job-123", tmp_path)

    assert result.status == "cleaned"
    assert not (tmp_path / "job-123").exists()
    assert (sibling / "keep.txt").exists()


def test_cleanup_blocks_unsafe_workspace_id(tmp_path: Path):
    result = cleanup_agent_workspace("../escape", tmp_path)

    assert result.status == "blocked"
    assert result.blocker is not None


def test_ensure_path_inside_workspace_rejects_escape_and_git_internals(tmp_path: Path):
    create_agent_workspace("job-123", tmp_path)

    try:
        ensure_path_inside_workspace("job-123", "../escape.txt", tmp_path)
    except WorkspacePolicyError:
        pass
    else:  # pragma: no cover
        raise AssertionError("relative path escape was not blocked")

    try:
        ensure_path_inside_workspace("job-123", ".git/config", tmp_path)
    except WorkspacePolicyError as exc:
        assert ".git" in str(exc)
    else:  # pragma: no cover
        raise AssertionError(".git internal path was not blocked")


def test_repo_url_policy_rejects_non_github_and_embedded_credentials():
    for url in [
        "https://evil.example/owner/repo",
        "https://user:pass@github.com/owner/repo",
        "https://github.com/owner/repo?token=secret",
    ]:
        try:
            validate_repo_url_for_workspace(url)
        except WorkspacePolicyError:
            pass
        else:  # pragma: no cover
            raise AssertionError(f"repo url should have been blocked: {url}")


def test_branch_policy_rejects_shell_like_branch():
    try:
        validate_workspace_branch("main; rm -rf /")
    except WorkspacePolicyError as exc:
        assert "branch" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("unsafe branch was not blocked")


def test_build_git_clone_command_uses_argv_without_shell_string(tmp_path: Path):
    command = build_git_clone_command(
        "https://github.com/OuroborosCollective/Sovereign-Studio-ato",
        "main",
        tmp_path / "repo",
    )

    assert command[:5] == ("git", "clone", "--depth", "1", "--branch")
    assert "https://github.com/OuroborosCollective/Sovereign-Studio-ato" in command
    assert all(";" not in part for part in command)


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Sovereign Test"], cwd=path, check=True, capture_output=True, text=True)
    (path / "README.md").write_text("initial\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=path, check=True, capture_output=True, text=True)


def test_git_status_and_diff_collect_real_workspace_evidence(tmp_path: Path):
    create_agent_workspace("job-123", tmp_path)
    repo = repo_dir_for_workspace("job-123", tmp_path)
    _init_git_repo(repo)
    (repo / "README.md").write_text("changed\n", encoding="utf-8")

    status = git_status_changed_files("job-123", tmp_path)
    diff = git_diff_summary("job-123", tmp_path)

    assert status.status == "done"
    assert status.changed_files == ("README.md",)
    assert diff.status == "done"
    assert diff.diff_summary is not None
    assert "README.md" in diff.diff_summary


def test_publish_workspace_branch_commits_declared_files_and_hides_token(monkeypatch, tmp_path: Path):
    create_agent_workspace("job-publish", tmp_path)
    repo = repo_dir_for_workspace("job-publish", tmp_path)
    _init_git_repo(repo)
    repo_url = "https://github.com/OuroborosCollective/Sovereign-Studio-ato"
    subprocess.run(["git", "remote", "add", "origin", repo_url], cwd=repo, check=True)
    target = repo / "docs" / "Release Notes.md"
    target.parent.mkdir()
    target.write_text("verified release notes\n", encoding="utf-8")

    real_run = git_workspace.run_git_command
    observed = {}

    def fake_run(args, cwd, timeout_seconds=120, env=None):
        if tuple(args[:2]) == ("git", "push"):
            observed["args"] = tuple(args)
            observed["askpass"] = env.get("GIT_ASKPASS") if env else None
            observed["token_env"] = env.get("SOVEREIGN_GIT_PUSH_TOKEN") if env else None
            assert observed["askpass"] and Path(observed["askpass"]).exists()
            return subprocess.CompletedProcess(list(args), 0, stdout="published", stderr="")
        return real_run(args, cwd, timeout_seconds, env)

    monkeypatch.setattr(git_workspace, "run_git_command", fake_run)
    result = publish_workspace_branch(
        "job-publish",
        repo_url=repo_url,
        base_branch="main",
        head_branch="sovereign/agent-job-publish-release-notes",
        commit_message="Update release notes",
        changed_files=("docs/Release Notes.md",),
        token="test-secret-token",
        root=tmp_path,
    )

    assert result.status == "done", result.blocker
    assert result.branch_name == "sovereign/agent-job-publish-release-notes"
    assert result.commit_sha and len(result.commit_sha) == 40
    assert "test-secret-token" not in " ".join(observed["args"])
    assert observed["token_env"] == "test-secret-token"
    assert not Path(observed["askpass"]).exists()


def test_publish_workspace_branch_blocks_undeclared_changes_before_push(monkeypatch, tmp_path: Path):
    create_agent_workspace("job-undeclared", tmp_path)
    repo = repo_dir_for_workspace("job-undeclared", tmp_path)
    _init_git_repo(repo)
    repo_url = "https://github.com/OuroborosCollective/Sovereign-Studio-ato"
    subprocess.run(["git", "remote", "add", "origin", repo_url], cwd=repo, check=True)
    (repo / "README.md").write_text("declared\n", encoding="utf-8")
    (repo / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")

    result = publish_workspace_branch(
        "job-undeclared",
        repo_url=repo_url,
        base_branch="main",
        head_branch="sovereign/agent-job-undeclared",
        commit_message="Update README",
        changed_files=("README.md",),
        token="test-secret-token",
        root=tmp_path,
    )

    assert result.status == "blocked"
    assert "undeclared changes" in (result.blocker or "")


def test_git_status_blocks_when_repo_directory_missing(tmp_path: Path):
    result = git_status_changed_files("job-123", tmp_path)

    assert result.status == "blocked"
    assert result.blocker == "Repo directory does not exist."
