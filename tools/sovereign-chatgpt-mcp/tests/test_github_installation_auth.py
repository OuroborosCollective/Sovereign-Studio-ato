from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
import pytest

from github_installation_auth import GitHubAppInstallationAuth, GitHubAppInstallationConfig


class FakeResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        return self._payload


class RecordingSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.response


def private_key_file(tmp_path: Path) -> Path:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path = tmp_path / "github-app.pem"
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    path.chmod(0o640)
    return path


def config(tmp_path: Path) -> GitHubAppInstallationConfig:
    return GitHubAppInstallationConfig(
        app_id="123456",
        installation_id=153170343,
        private_key_file=private_key_file(tmp_path),
        repository="OuroborosCollective/Sovereign-Studio-ato",
    )


def test_issues_repository_scoped_token_only_inside_context(tmp_path: Path) -> None:
    session = RecordingSession(FakeResponse(201, {"token": "installation-token-never-persisted"}))
    auth = GitHubAppInstallationAuth(config(tmp_path), session=session, now=lambda: 2_000_000_000)

    with auth.token() as token:
        assert token == "installation-token-never-persisted"

    assert set(auth.__dict__) == {"config", "_session", "_now"}
    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["url"] == "https://api.github.com/app/installations/153170343/access_tokens"
    assert call["json"] == {"repositories": ["Sovereign-Studio-ato"]}
    auth_header = str(dict(call["headers"]).get("Authorization") or "")
    encoded_jwt = auth_header.removeprefix("Bearer ")
    claims = jwt.decode(encoded_jwt, options={"verify_signature": False})
    assert claims == {"iat": 1_999_999_940, "exp": 2_000_000_540, "iss": "123456"}
    assert "installation-token-never-persisted" not in auth.__dict__.values()


def test_rejects_non_created_installation_token_response_without_returning_secret(tmp_path: Path) -> None:
    session = RecordingSession(FakeResponse(403, {"message": "forbidden"}))
    auth = GitHubAppInstallationAuth(config(tmp_path), session=session)

    with pytest.raises(RuntimeError, match="HTTP 403"):
        with auth.headers():
            raise AssertionError("headers must not be yielded after a denied token request")


def test_env_contract_rejects_world_writable_private_key(monkeypatch, tmp_path: Path) -> None:
    path = private_key_file(tmp_path)
    path.chmod(0o666)
    monkeypatch.setenv("SOVEREIGN_MCP_GITHUB_APP_ID", "123456")
    monkeypatch.setenv("SOVEREIGN_MCP_GITHUB_APP_INSTALLATION_ID", "153170343")
    monkeypatch.setenv("SOVEREIGN_MCP_GITHUB_APP_PRIVATE_KEY_FILE", str(path))

    with pytest.raises(RuntimeError, match="sicheren Dateivertrag"):
        GitHubAppInstallationConfig.from_env(repository="OuroborosCollective/Sovereign-Studio-ato")


def test_private_key_is_not_encoded_into_installation_request_payload(tmp_path: Path) -> None:
    session = RecordingSession(FakeResponse(201, {"token": "short-lived"}))
    auth = GitHubAppInstallationAuth(config(tmp_path), session=session)

    with auth.headers() as headers:
        assert headers["Authorization"] == "Bearer short-lived"

    payload = session.calls[0]["json"]
    assert payload == {"repositories": ["Sovereign-Studio-ato"]}
    assert "token" not in payload
    assert "private_key" not in payload
