import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "sovereign-toolchain" / "deploy" / "install-on-vps.sh"
INSTALL_PATHS = (
    "tools/sovereign-toolchain",
    "tools/sovereign-legacy-mcp-common",
)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "tests@example.invalid")
    _git(repo, "config", "user.name", "Sovereign Tests")

    tracked = {
        "tools/sovereign-toolchain/source.txt": "toolchain\n",
        "tools/sovereign-legacy-mcp-common/source.txt": "common\n",
        "tools/sovereign-chatgpt-mcp/deploy/install-on-vps.sh": "unrelated\n",
    }
    for relative, content in tracked.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "fixture")
    return repo


def _tracked_install_dirty(repo: Path) -> str:
    return _git(
        repo,
        "status",
        "--porcelain",
        "--untracked-files=no",
        "--",
        *INSTALL_PATHS,
    ).stdout


def _worktree_identity(source_dir: Path) -> tuple[Path | None, str]:
    root = subprocess.run(
        ["git", "-C", str(source_dir), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    inside = subprocess.run(
        ["git", "-C", str(source_dir), "rev-parse", "--is-inside-work-tree"],
        check=False,
        capture_output=True,
        text=True,
    )
    resolved_root = Path(root.stdout.strip()).resolve() if root.returncode == 0 and root.stdout.strip() else None
    return resolved_root, inside.stdout.strip() if inside.returncode == 0 else ""


def test_revision_bound_toolchain_installer_is_tracked_executable() -> None:
    assert INSTALLER.stat().st_mode & stat.S_IXUSR


def test_installer_contract_accepts_git_linked_worktrees_without_weakening_identity(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    linked = tmp_path / "linked"
    _git(repo, "worktree", "add", "--detach", str(linked), "HEAD")

    assert (linked / ".git").is_file()
    linked_root, linked_inside = _worktree_identity(linked / "tools/sovereign-toolchain")
    assert linked_root == linked.resolve()
    assert linked_inside == "true"

    plain = tmp_path / "plain"
    (plain / "tools/sovereign-toolchain").mkdir(parents=True)
    plain_root, plain_inside = _worktree_identity(plain / "tools/sovereign-toolchain")
    assert plain_root is None
    assert plain_inside == ""

    installer = INSTALLER.read_text("utf-8")
    assert 'rev-parse --is-inside-work-tree' in installer
    assert '"$SOURCE_IN_WORK_TREE" == "true"' in installer
    assert '-d "$SOURCE_REPOSITORY_ROOT/.git"' not in installer
    assert 'SOURCE_REVISION="$(git -C "$SOURCE_DIR" rev-parse HEAD' in installer
    assert '[[ "$SOURCE_REVISION" == "$EXPECTED_REVISION" ]]' in installer


def test_installer_contract_scopes_tracked_dirty_check_to_materialized_sources() -> None:
    installer = INSTALLER.read_text("utf-8")

    assert 'TRACKED_INSTALL_DIRTY="$(' in installer
    assert 'git -C "$SOURCE_REPOSITORY_ROOT" status \\' in installer
    assert "--untracked-files=no \\" in installer
    assert "tools/sovereign-toolchain \\" in installer
    assert "tools/sovereign-legacy-mcp-common" in installer
    assert 'fail "revision-bound toolchain source has tracked modifications"' in installer
    assert 'status --porcelain --untracked-files=no 2>/dev/null)' not in installer


def test_unrelated_tracked_modification_does_not_trip_install_dirty_guard(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    unrelated = repo / "tools/sovereign-chatgpt-mcp/deploy/install-on-vps.sh"
    unrelated.write_text("changed outside installed sources\n", encoding="utf-8")

    assert _tracked_install_dirty(repo) == ""


@pytest.mark.parametrize(
    "relative",
    [
        "tools/sovereign-toolchain/source.txt",
        "tools/sovereign-legacy-mcp-common/source.txt",
    ],
)
def test_tracked_modification_inside_installed_source_trips_guard(
    tmp_path: Path,
    relative: str,
) -> None:
    repo = _repository(tmp_path)
    dirty = repo / relative
    dirty.write_text("changed installed source\n", encoding="utf-8")

    output = _tracked_install_dirty(repo)
    assert relative in output
