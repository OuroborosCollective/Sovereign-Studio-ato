"""Real Git/subprocess regressions for the shared-workspace ownership boundary."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_runtime.git_environment import workspace_git_environment
from agent_runtime.tool_runner import _workspace_revision
from agent_runtime.tools.git_tool import GitDiffTool, GitStatusTool
from agent_runtime.tools.test_tool import TestTool as WorkspaceTestTool


def git(repo: Path, *args: str, env: dict[str, str] | None = None):
    return subprocess.run(
        ["git", "-C", str(repo), *args], env=env,
        capture_output=True, text=True, timeout=15, check=False,
    )


@pytest.fixture
def repositories(tmp_path, monkeypatch):
    for key in tuple(os.environ):
        if key.startswith("GIT_") or key == "SUDO_UID":
            monkeypatch.delenv(key, raising=False)
    config = tmp_path / "global.gitconfig"
    config.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("HOME", str(tmp_path))
    result = []
    for name in ("assigned", "assigned-neighbor"):
        root = tmp_path / name
        root.mkdir()
        (root / "nested").mkdir()
        (root / "README.md").write_text("# Before\n")
        assert git(root, "init", "-q").returncode == 0
        assert git(root, "add", "README.md").returncode == 0
        assert git(root, "-c", "user.name=Ownership Regression", "-c",
                   "user.email=regression@example.invalid", "commit", "-qm", "baseline").returncode == 0
        head = git(root, "rev-parse", "HEAD").stdout.strip()
        (root / "README.md").write_text("# After\n")
        result.append((root, head))
    return result, config


@pytest.fixture
def foreign_repositories(repositories):
    """Change actual directory ownership; never fake a Git command result."""
    if os.name != "posix":
        pytest.skip("Cross-UID regression needs POSIX ownership")
    repos, config = repositories
    old = [(p, p.stat().st_uid, p.stat().st_gid) for root, _ in repos for p in (root, root / ".git")]
    direct = os.geteuid() == 0
    sudo = shutil.which("sudo")
    if not direct and (not sudo or subprocess.run(
        [sudo, "-n", "true"], capture_output=True, timeout=5, check=False,
    ).returncode != 0):
        pytest.skip("Cross-UID regression needs root or passwordless sudo on its temporary fixture")
    uid = 65534 if os.geteuid() != 65534 else 65533
    def change(path: Path, owner: int, group: int):
        if direct:
            os.chown(path, owner, group)
        else:
            subprocess.run([sudo, "-n", "chown", f"{owner}:{group}", "--", str(path)],
                           check=True, capture_output=True, timeout=10)
    try:
        for path, _, _ in old:
            change(path, uid, uid)
        yield repos, config
    finally:
        for path, owner, group in old:
            change(path, owner, group)


def test_real_cross_owner_status_diff_head_and_nested_check(foreign_repositories):
    repos, _ = foreign_repositories
    root, expected_head = repos[0]
    before = git(root, "status", "--porcelain")
    assert before.returncode != 0
    assert "dubious ownership" in before.stderr
    assert root.stat().st_uid != os.geteuid()
    assert _workspace_revision(str(root)) == expected_head
    status = GitStatusTool().execute({}, str(root))
    diff = GitDiffTool().execute({}, str(root))
    assert status.is_ok(), status.error
    assert "README.md" in status.output
    assert diff.is_ok(), diff.error
    assert "+# After" in diff.output
    for path in (None, "nested"):
        args = {"command": "git diff --check", "verbose": False}
        if path:
            args["path"] = path
        result = WorkspaceTestTool().execute(args, str(root))
        assert result.is_ok(), result.error
        assert result.exit_code == 0


def test_real_child_pytest_keeps_root_scope_and_excludes_parent_secrets(foreign_repositories, monkeypatch):
    repos, _ = foreign_repositories
    root, expected_head = repos[0]
    (root / "nested" / "test_head.py").write_text(
        "import os, subprocess\n\ndef test_actual_head():\n"
        "    assert 'SOVEREIGN_PARENT_SECRET_CANARY' not in os.environ\n"
        "    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()\n"
        f"    assert head == {expected_head!r}\n"
    )
    monkeypatch.setenv("SOVEREIGN_PARENT_SECRET_CANARY", "isolated-canary-not-a-credential")
    for args in (
        {"command": "python3 -m pytest -q -o addopts= test_head.py"},
        {"framework": "pytest"},
    ):
        result = WorkspaceTestTool().execute({**args, "path": "nested", "verbose": False}, str(root))
        assert result.is_ok(), result.error
        assert "1 passed" in result.output


def test_inherited_wildcard_does_not_trust_neighbor_or_change_config(foreign_repositories):
    repos, config = foreign_repositories
    root, _ = repos[0]
    neighbor, _ = repos[1]
    config.write_text("[safe]\n\tdirectory = *\n")
    original = config.read_bytes()
    parent = dict(os.environ)
    child = workspace_git_environment(root, base_env=parent)
    assert parent == dict(os.environ)
    assert git(root, "status", "--porcelain", env=child).returncode == 0
    denied = git(neighbor, "status", "--porcelain", env=child)
    assert denied.returncode != 0
    assert "dubious ownership" in denied.stderr
    assert config.read_bytes() == original


def test_real_whitespace_failure_is_not_made_green(repositories):
    repos, _ = repositories
    root, _ = repos[0]
    (root / "README.md").write_text("# After  \n")
    result = WorkspaceTestTool().execute({"command": "git diff --check", "verbose": False}, str(root))
    assert result.is_error()
    assert result.exit_code != 0
    assert "trailing whitespace" in result.error


def test_neighbor_prefix_and_symlink_test_paths_are_rejected(repositories):
    repos, _ = repositories
    root, _ = repos[0]
    neighbor, _ = repos[1]
    (root / "escape").symlink_to(neighbor, target_is_directory=True)
    for path in ("../assigned-neighbor", str(neighbor), "escape"):
        result = WorkspaceTestTool().execute({"command": "git diff --check", "path": path}, str(root))
        assert result.is_blocked()
        assert result.blocker == "Test path outside workspace"


def test_environment_is_copied_and_existing_pairs_are_preserved(tmp_path):
    parent = {"PATH": "bin", "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "color.ui",
              "GIT_CONFIG_VALUE_0": "false", "GIT_CONFIG_PARAMETERS": "'safe.directory=*'", "SUDO_UID": "0"}
    original = dict(parent)
    child = workspace_git_environment(tmp_path, base_env=parent)
    assert parent == original
    assert child["GIT_CONFIG_COUNT"] == "3"
    assert child["GIT_CONFIG_KEY_0"] == "color.ui"
    assert child["GIT_CONFIG_VALUE_0"] == "false"
    assert child["GIT_CONFIG_KEY_1"] == "safe.directory"
    assert child["GIT_CONFIG_VALUE_1"] == ""
    assert child["GIT_CONFIG_VALUE_2"] == str(tmp_path.resolve())
    assert "GIT_CONFIG_PARAMETERS" not in child
    assert "SUDO_UID" not in child


@pytest.mark.parametrize("count", ["-1", "129", "a", "9999", "１", "+1"])
def test_malformed_config_counts_are_rejected(tmp_path, count):
    with pytest.raises(ValueError):
        workspace_git_environment(tmp_path, base_env={"GIT_CONFIG_COUNT": count})


def test_incomplete_config_pair_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        workspace_git_environment(tmp_path, base_env={"GIT_CONFIG_COUNT": "1"})


@pytest.mark.parametrize("path", ["", "*", "/", "/tmp/*", "bad\x00path"])
def test_broad_or_invalid_workspace_is_rejected(path):
    with pytest.raises(ValueError):
        workspace_git_environment(path, base_env={})


def test_symlink_cannot_resolve_to_wildcard_trust(tmp_path):
    target = tmp_path / "*"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError):
        workspace_git_environment(alias, base_env={})
