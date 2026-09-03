import json
import os
from contextlib import contextmanager
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sovereign-legacy-mcp-common"))
sys.path.insert(0, str(ROOT / "sovereign-toolchain" / "src"))

import github_app_auth
from sovereign_toolchain import core
from sovereign_toolchain.core import GitHubClient


@contextmanager
def environment(values: dict[str, str | None]):
    previous = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_persistent_github_token_does_not_enable_toolchain_client() -> None:
    with environment(
        {
            "GITHUB_TOKEN": "persistent-token-must-not-be-used",
            "SOVEREIGN_MCP_GITHUB_APP_ID": None,
            "SOVEREIGN_MCP_GITHUB_APP_INSTALLATION_ID": None,
            "SOVEREIGN_MCP_GITHUB_APP_PRIVATE_KEY_FILE": None,
            "SOVEREIGN_MCP_REPOSITORY": None,
            "CREDENTIALS_DIRECTORY": None,
        }
    ), pytest.raises(RuntimeError, match="SOVEREIGN_MCP_GITHUB_APP_ID is invalid"):
        GitHubClient()


def test_toolchain_core_uses_shared_app_only_adapter() -> None:
    source = (ROOT / "sovereign-toolchain" / "src" / "sovereign_toolchain" / "core.py").read_text("utf-8")
    assert "GitHubAppInstallationAuth" in source
    assert "GitHubAppInstallationConfig" in source
    assert 'os.getenv("GITHUB_TOKEN"' not in source
    assert "with self.auth.token() as issued" in source


@pytest.mark.parametrize(
    ("repository", "repository_name"),
    [
        ("OuroborosCollective/Sovereign-Studio-ato", "Sovereign-Studio-ato"),
        ("OuroborosCollective/Echoes_of_Aurion", "Echoes_of_Aurion"),
    ],
)
def test_lane_repository_is_the_only_repository_in_token_json(
    monkeypatch,
    repository: str,
    repository_name: str,
) -> None:
    base_config = core.GitHubAppInstallationConfig(
        app_id="1",
        installation_id=2,
        private_key_file=Path("/unused-test-key.pem"),
        repository="OuroborosCollective/Sovereign-Studio-ato",
    )
    token_requests: list[dict[str, object]] = []

    class Response:
        status_code = 201

        @staticmethod
        def json() -> dict[str, str]:
            return {"token": "installation-token-for-test"}

    class CapturingClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            pass

        def post(self, url, *, headers, json):
            token_requests.append({"url": url, "headers": headers, "json": json})
            return Response()

    monkeypatch.setenv("ALLOWED_REPOS", (
        "OuroborosCollective/Sovereign-Studio-ato,"
        "OuroborosCollective/Echoes_of_Aurion"
    ))
    monkeypatch.delenv(core._GITHUB_READ_ONLY_ENV, raising=False)
    monkeypatch.setattr(
        core.GitHubAppInstallationConfig,
        "from_env",
        classmethod(lambda cls: base_config),
    )
    monkeypatch.setattr(github_app_auth.httpx, "Client", CapturingClient)

    client = GitHubClient(repository)
    assert type(client.auth) is core.GitHubAppInstallationAuth
    monkeypatch.setattr(client.auth, "_app_jwt", lambda: "signed-app-jwt")
    with client.auth.token() as issued:
        assert issued == "installation-token-for-test"

    assert client.auth.config is not base_config
    assert base_config.repository == "OuroborosCollective/Sovereign-Studio-ato"
    assert client.auth.config.repository == repository
    assert [request["json"] for request in token_requests] == [
        {"repositories": [repository_name]}
    ]


@pytest.mark.parametrize(
    ("repository", "repository_name"),
    [
        ("OuroborosCollective/Sovereign-Studio-ato", "Sovereign-Studio-ato"),
        ("OuroborosCollective/Echoes_of_Aurion", "Echoes_of_Aurion"),
    ],
)
def test_evidence_client_requests_only_read_permissions(
    monkeypatch,
    repository: str,
    repository_name: str,
) -> None:
    base_config = core.GitHubAppInstallationConfig(
        app_id="1",
        installation_id=2,
        private_key_file=Path("/unused-test-key.pem"),
        repository="OuroborosCollective/Sovereign-Studio-ato",
    )
    requests = []

    class Response:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            pass

        @staticmethod
        def read() -> bytes:
            return b'{"token":"installation-token-for-test"}'

    def urlopen(request, *, timeout):
        requests.append(request)
        assert timeout == 20
        return Response()

    monkeypatch.setenv("ALLOWED_REPOS", (
        "OuroborosCollective/Sovereign-Studio-ato,"
        "OuroborosCollective/Echoes_of_Aurion"
    ))
    monkeypatch.setenv(core._GITHUB_READ_ONLY_ENV, "1")
    monkeypatch.setattr(
        core.GitHubAppInstallationConfig,
        "from_env",
        classmethod(lambda cls: base_config),
    )
    monkeypatch.setattr(core.urllib.request, "urlopen", urlopen)

    client = GitHubClient(repository)
    assert type(client.auth) is core._ReadOnlyGitHubAppInstallationAuth
    monkeypatch.setattr(client.auth, "_app_jwt", lambda: "signed-app-jwt")
    with client.auth.token() as issued:
        assert issued == "installation-token-for-test"

    assert client.auth.config.repository == repository
    assert len(requests) == 1
    assert json.loads(requests[0].data.decode("utf-8")) == {
        "repositories": [repository_name],
        "permissions": {"actions": "read", "contents": "read"},
    }


def test_read_only_process_flag_is_exact_and_fail_closed(monkeypatch) -> None:
    base_config = core.GitHubAppInstallationConfig(
        app_id="1",
        installation_id=2,
        private_key_file=Path("/unused-test-key.pem"),
        repository="OuroborosCollective/Sovereign-Studio-ato",
    )
    monkeypatch.setenv("ALLOWED_REPOS", "OuroborosCollective/Sovereign-Studio-ato")
    monkeypatch.setenv(core._GITHUB_READ_ONLY_ENV, "true")
    monkeypatch.setattr(
        core.GitHubAppInstallationConfig,
        "from_env",
        classmethod(lambda cls: base_config),
    )

    with pytest.raises(RuntimeError, match=core._GITHUB_READ_ONLY_ENV):
        GitHubClient("OuroborosCollective/Sovereign-Studio-ato")


def test_unallowlisted_repository_cannot_be_selected_explicitly_or_from_env(monkeypatch) -> None:
    free_repository = "OuroborosCollective/Free"
    free_config = core.GitHubAppInstallationConfig(
        app_id="1",
        installation_id=2,
        private_key_file=Path("/unused-test-key.pem"),
        repository=free_repository,
    )
    monkeypatch.setenv("ALLOWED_REPOS", (
        "OuroborosCollective/Sovereign-Studio-ato,"
        "OuroborosCollective/Echoes_of_Aurion"
    ))
    monkeypatch.setattr(
        core.GitHubAppInstallationConfig,
        "from_env",
        classmethod(lambda cls: free_config),
    )

    with pytest.raises(PermissionError):
        GitHubClient(free_repository)
    with pytest.raises(PermissionError):
        GitHubClient()


def test_repository_selection_is_exact(monkeypatch) -> None:
    base_config = core.GitHubAppInstallationConfig(
        app_id="1",
        installation_id=2,
        private_key_file=Path("/unused-test-key.pem"),
        repository="OuroborosCollective/Sovereign-Studio-ato",
    )
    monkeypatch.setenv("ALLOWED_REPOS", (
        "OuroborosCollective/Sovereign-Studio-ato,"
        "OuroborosCollective/Echoes_of_Aurion"
    ))
    monkeypatch.setattr(
        core.GitHubAppInstallationConfig,
        "from_env",
        classmethod(lambda cls: base_config),
    )

    with pytest.raises(PermissionError):
        GitHubClient(" OuroborosCollective/Sovereign-Studio-ato")
    with pytest.raises(PermissionError):
        GitHubClient("OuroborosCollective/Sovereign-Studio-ato/extra")


def test_runtime_imports_fastmcp_from_locked_mcp_sdk() -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("mcp")
    from sovereign_toolchain.app import app

    assert app is not None


def test_streamable_mcp_is_fail_closed_and_served_with_exact_key() -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("mcp")
    from fastapi.testclient import TestClient
    from sovereign_toolchain.app import app

    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "toolchain-route-contract", "version": "1"},
        },
    }
    with TestClient(app, base_url="http://127.0.0.1:8001") as client:
        with environment({"TOOLCHAIN_API_KEY": None}):
            assert client.post(
                "/mcp/",
                json=request,
                headers={"Accept": "application/json, text/event-stream"},
            ).status_code == 503

        with environment({"TOOLCHAIN_API_KEY": "test-toolchain-capability"}):
            assert client.post(
                "/mcp/",
                json=request,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "X-Toolchain-Key": "wrong",
                },
            ).status_code == 401
            response = client.post(
                "/mcp/",
                json=request,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "X-Toolchain-Key": "test-toolchain-capability",
                },
            )

            assert response.status_code == 200
            assert "result" in response.json()
