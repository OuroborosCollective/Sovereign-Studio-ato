"""GitHub authentication for MCP repository operations.

The preferred path is an ephemeral GitHub App installation token. When the App
configuration is unavailable, the runtime may fall back to one owner-managed PAT
stored in a protected VPS file. The protected value is read only for the active
outbound request or Git subprocess and is never returned by MCP tools.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import base64
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time
from typing import Callable, Iterator

import requests


_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_TOKEN_TTL_SECONDS = 540
_CLOCK_SKEW_SECONDS = 60
_DEFAULT_OWNER_TOKEN_FILE = Path("/opt/sovereign-owner-managed/github_owner_token.txt")
_MAX_OWNER_TOKEN_BYTES = 8192


def _owner_token_file() -> Path:
    configured = os.getenv("SOVEREIGN_MCP_GITHUB_TOKEN_FILE", "").strip()
    path = Path(configured) if configured else _DEFAULT_OWNER_TOKEN_FILE
    if not path.is_absolute():
        raise RuntimeError("SOVEREIGN_MCP_GITHUB_TOKEN_FILE ist ungültig")
    return path


def _read_owner_token() -> str:
    path = _owner_token_file()
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise RuntimeError("Owner-verwalteter GitHub-Zugriffsschlüssel ist nicht konfiguriert") from exc
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink() or metadata.st_mode & 0o077:
        raise RuntimeError("Owner-verwalteter GitHub-Zugriffsschlüssel verletzt den sicheren Dateivertrag")
    if metadata.st_size < 20 or metadata.st_size > _MAX_OWNER_TOKEN_BYTES:
        raise RuntimeError("Owner-verwalteter GitHub-Zugriffsschlüssel hat eine ungültige Größe")
    try:
        token = path.read_text("utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeError("Owner-verwalteter GitHub-Zugriffsschlüssel ist nicht lesbar") from exc
    if len(token) < 20 or len(token.encode("utf-8")) > _MAX_OWNER_TOKEN_BYTES or any(
        character.isspace() for character in token
    ):
        raise RuntimeError("Owner-verwalteter GitHub-Zugriffsschlüssel hat ein ungültiges Format")
    return token


@dataclass(frozen=True)
class GitHubAppInstallationConfig:
    """Validated non-token configuration for one repository installation."""

    app_id: str
    installation_id: int
    private_key_file: Path
    repository: str

    @classmethod
    def from_env(cls, *, repository: str) -> "GitHubAppInstallationConfig":
        app_id = os.getenv("SOVEREIGN_MCP_GITHUB_APP_ID", "").strip()
        installation_text = os.getenv("SOVEREIGN_MCP_GITHUB_APP_INSTALLATION_ID", "").strip()
        key_path_text = os.getenv("SOVEREIGN_MCP_GITHUB_APP_PRIVATE_KEY_FILE", "").strip()
        if not app_id.isdecimal() or int(app_id) <= 0:
            raise RuntimeError("SOVEREIGN_MCP_GITHUB_APP_ID ist ungültig")
        if not installation_text.isdecimal() or int(installation_text) <= 0:
            raise RuntimeError("SOVEREIGN_MCP_GITHUB_APP_INSTALLATION_ID ist ungültig")
        if not _REPOSITORY_RE.fullmatch(repository):
            raise RuntimeError("SOVEREIGN_MCP_REPOSITORY ist ungültig")
        key_path = Path(key_path_text)
        if not key_path_text or not key_path.is_absolute():
            raise RuntimeError("SOVEREIGN_MCP_GITHUB_APP_PRIVATE_KEY_FILE ist ungültig")
        try:
            metadata = key_path.lstat()
        except OSError as exc:
            raise RuntimeError("GitHub-App-Private-Key-Datei ist nicht lesbar") from exc
        if not key_path.is_file() or key_path.is_symlink() or metadata.st_mode & 0o022:
            raise RuntimeError("GitHub-App-Private-Key-Datei verletzt den sicheren Dateivertrag")
        return cls(
            app_id=app_id,
            installation_id=int(installation_text),
            private_key_file=key_path,
            repository=repository,
        )


class UnavailableGitHubInstallationAuth:
    """Use the protected owner PAT file when GitHub App configuration is unavailable."""

    @contextmanager
    def token(self) -> Iterator[str]:
        issued = _read_owner_token()
        try:
            yield issued
        finally:
            issued = ""

    @contextmanager
    def headers(self) -> Iterator[dict[str, str]]:
        with self.token() as token:
            yield {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }


class GitHubAppInstallationAuth:
    """Issue one short-lived, repository-scoped installation token per use context."""

    def __init__(
        self,
        config: GitHubAppInstallationConfig,
        *,
        session: requests.Session | None = None,
        now: Callable[[], float] | None = None,
    ) -> None:
        self.config = config
        self._session = session or requests.Session()
        self._now = now or time.time

    @staticmethod
    def _base64url(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    def _app_jwt(self) -> str:
        openssl = shutil.which("openssl")
        if not openssl:
            raise RuntimeError("OpenSSL für GitHub-App-JWT ist nicht verfügbar")
        now = int(self._now())
        header = self._base64url(
            json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode("utf-8")
        )
        claims = self._base64url(
            json.dumps(
                {
                    "iat": now - _CLOCK_SKEW_SECONDS,
                    "exp": now + _TOKEN_TTL_SECONDS,
                    "iss": self.config.app_id,
                },
                separators=(",", ":"),
            ).encode("utf-8")
        )
        signing_input = f"{header}.{claims}".encode("ascii")
        try:
            signed = subprocess.run(
                [openssl, "dgst", "-sha256", "-sign", str(self.config.private_key_file)],
                input=signing_input,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError("GitHub-App-JWT konnte nicht erzeugt werden") from exc
        if signed.returncode != 0 or not signed.stdout:
            raise RuntimeError("GitHub-App-JWT konnte nicht erzeugt werden")
        return f"{header}.{claims}.{self._base64url(signed.stdout)}"

    def _issue_token(self) -> str:
        app_jwt = self._app_jwt()
        repository_name = self.config.repository.split("/", 1)[1]
        try:
            response = self._session.post(
                f"https://api.github.com/app/installations/{self.config.installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {app_jwt}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                json={"repositories": [repository_name]},
                timeout=20,
            )
        except requests.RequestException as exc:
            raise RuntimeError("GitHub-App-Installation-Token konnte nicht angefordert werden") from exc
        if response.status_code != 201:
            raise RuntimeError(f"GitHub-App-Installation-Token abgelehnt: HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("GitHub-App-Installation-Token-Antwort ist ungültig") from exc
        token = str(payload.get("token") or "").strip() if isinstance(payload, dict) else ""
        if not token:
            raise RuntimeError("GitHub-App-Installation-Token fehlt")
        return token

    @contextmanager
    def token(self) -> Iterator[str]:
        """Yield one ephemeral installation token and drop the reference on exit."""
        issued = self._issue_token()
        try:
            yield issued
        finally:
            # Python strings cannot be wiped in place. Do not retain this value in
            # object state, files, logs, subprocess output, or MCP responses.
            issued = ""

    @contextmanager
    def headers(self) -> Iterator[dict[str, str]]:
        """Yield GitHub API headers for exactly one outbound request scope."""
        with self.token() as token:
            yield {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
