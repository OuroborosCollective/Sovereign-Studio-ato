"""Ephemeral GitHub App installation authentication for MCP repository operations.

The GitHub App private key remains a read-only container secret.  A repository-scoped
installation token is minted only while an outbound GitHub request or Git subprocess
is active; it is never written to a workspace, response, log, or object attribute.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import re
import time
from typing import Callable, Iterator

import jwt
import requests


_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_TOKEN_TTL_SECONDS = 540
_CLOCK_SKEW_SECONDS = 60


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
    """Fail closed when a read-only MCP process has no GitHub App configuration."""

    @contextmanager
    def token(self) -> Iterator[str]:
        raise RuntimeError("GitHub-App-Installation-Authentisierung ist nicht konfiguriert")
        yield ""  # pragma: no cover

    @contextmanager
    def headers(self) -> Iterator[dict[str, str]]:
        with self.token() as token:
            yield {"Authorization": f"Bearer {token}"}


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

    def _app_jwt(self) -> str:
        try:
            private_key = self.config.private_key_file.read_bytes()
        except OSError as exc:
            raise RuntimeError("GitHub-App-Private-Key-Datei ist nicht lesbar") from exc
        if not private_key:
            raise RuntimeError("GitHub-App-Private-Key-Datei ist leer")
        now = int(self._now())
        try:
            return str(
                jwt.encode(
                    {
                        "iat": now - _CLOCK_SKEW_SECONDS,
                        "exp": now + _TOKEN_TTL_SECONDS,
                        "iss": self.config.app_id,
                    },
                    private_key,
                    algorithm="RS256",
                )
            )
        except Exception as exc:
            raise RuntimeError("GitHub-App-JWT konnte nicht erzeugt werden") from exc

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
            # Python strings cannot be wiped in place.  Do not retain this value in
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
