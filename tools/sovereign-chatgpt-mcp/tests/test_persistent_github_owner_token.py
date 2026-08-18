from __future__ import annotations

from pathlib import Path
import stat

import pytest

from github_installation_auth import UnavailableGitHubInstallationAuth


ROOT = Path(__file__).resolve().parents[1]
OWNER_TOKEN_PATH = "/opt/sovereign-owner-managed/github_owner_token.txt"


def test_owner_managed_github_token_file_is_used_only_as_protected_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token_file = tmp_path / "github_owner_token.txt"
    token = "github_pat_fixture_only_0123456789abcdef"
    token_file.write_text(token, "utf-8")
    token_file.chmod(0o600)
    monkeypatch.setenv("SOVEREIGN_MCP_GITHUB_TOKEN_FILE", str(token_file))

    auth = UnavailableGitHubInstallationAuth()
    with auth.token() as issued:
        assert issued == token
    with auth.headers() as headers:
        assert headers["Authorization"] == f"Bearer {token}"
        assert headers["Accept"] == "application/vnd.github+json"

    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600


def test_owner_managed_github_token_file_rejects_unsafe_permissions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token_file = tmp_path / "github_owner_token.txt"
    token_file.write_text("github_pat_fixture_only_0123456789abcdef", "utf-8")
    token_file.chmod(0o644)
    monkeypatch.setenv("SOVEREIGN_MCP_GITHUB_TOKEN_FILE", str(token_file))

    with pytest.raises(RuntimeError, match="sicheren Dateivertrag"):
        with UnavailableGitHubInstallationAuth().token():
            pass


def test_self_update_and_backend_bind_the_same_persistent_owner_token_contract() -> None:
    updater = (ROOT / "deploy" / "self-update-chatgpt-mcp.sh").read_text("utf-8")
    backend_compose = (ROOT.parents[1] / "scripts" / "sovereign-backend" / "docker-compose.yml").read_text("utf-8")

    assert OWNER_TOKEN_PATH in updater
    assert OWNER_TOKEN_PATH in backend_compose
    assert 'SOVEREIGN_OWNER_INPUT_TARGETS_JSON:' in backend_compose
    assert '"github_token"' in backend_compose
    assert 'git checkout --detach --force "$EXPECTED_REVISION"' in updater
    assert 'CHECKED_OUT_REVISION="$(git rev-parse HEAD)"' in updater
    assert 'neither GitHub App nor protected owner GitHub token produced a credential' in updater
