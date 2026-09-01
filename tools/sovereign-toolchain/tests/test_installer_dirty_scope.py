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
