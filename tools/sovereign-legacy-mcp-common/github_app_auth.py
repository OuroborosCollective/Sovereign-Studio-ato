"""Ephemeral GitHub App installation authentication for legacy Sovereign MCP services.

This module intentionally has no GITHUB_TOKEN, PAT, environment-file token, or
owner-token fallback. Each API operation mints one short-lived installation token
and discards its local reference when the request context exits.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
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
from typing import AsyncIterator, Callable

import httpx


_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_TOKEN_TTL_SECONDS = 540
_CLOCK_SKEW_SECONDS = 60


@dataclass(frozen=True)
class GitHubAppInstallationConfig:
    """Validated non-secret configuration for exactly one GitHub repository."""

    app_id: str
    installation_id: int
    private_key_file: Path
    repository: str

    @classmethod
    def from_env(cls) -> "GitHubAppInstallationConfig":
        app_id = os.getenv("SOVEREIGN_MCP_GITHUB_APP_ID", "").strip()
        installation_text = os.getenv("SOVEREIGN_MCP_GITHUB_APP_INSTALLATION_ID", "").strip()
        key_path_text = os.getenv("SOVEREIGN_MCP_GITHUB_APP_PRIVATE_KEY_FILE", "").strip()
        if not key_path_text:
            credentials_directory = os.getenv("CREDENTIALS_DIRECTORY", "").strip()
            if credentials_directory:
                key_path_text = str(Path(credentials_directory) / "github-app-private-key.pem")
        repository = os.getenv("SOVEREIGN_MCP_REPOSITORY", "").strip()
        if not app_id.isdecimal() or int(app_id) <= 0:
            raise RuntimeError("SOVEREIGN_MCP_GITHUB_APP_ID is invalid")
        if not installation_text.isdecimal() or int(installation_text) <= 0:
            raise RuntimeError("SOVEREIGN_MCP_GITHUB_APP_INSTALLATION_ID is invalid")
        if not _REPOSITORY_RE.fullmatch(repository):
            raise RuntimeError("SOVEREIGN_MCP_REPOSITORY is invalid")
        key_path = Path(key_path_text)
        if not key_path_text or not key_path.is_absolute():
            raise RuntimeError("SOVEREIGN_MCP_GITHUB_APP_PRIVATE_KEY_FILE is invalid")
        try:
            metadata = key_path.lstat()
        except OSError as exc:
            raise RuntimeError("GitHub App private key file is unreadable") from exc
        if (
            not stat.S_ISREG(metadata.st_mode)
            or key_path.is_symlink()
            or stat.S_IMODE(metadata.st_mode) & 0o077
            or metadata.st_size <= 0
        ):
            raise RuntimeError("GitHub App private key file violates the security contract")
        return cls(
            app_id=app_id,
            installation_id=int(installation_text),
            private_key_file=key_path,
            repository=repository,
        )


class GitHubAppInstallationAuth:
    """Mint one short-lived repository-scoped GitHub App installation token per use."""

    def __init__(
        self,
        config: GitHubAppInstallationConfig,
        *,
        now: Callable[[], float] | None = None,
    ) -> None:
        self.config = config
        self._now = now or time.time

    @staticmethod
    def _base64url(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    def _app_jwt(self) -> str:
        openssl = shutil.which("openssl")
        if not openssl:
            raise RuntimeError("OpenSSL is unavailable for GitHub App JWT signing")
        now = int(self._now())
        header = self._base64url(
            json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode("utf-8")
        )
        claims = self._base64url(
            json.dumps(
                {"iat": now - _CLOCK_SKEW_SECONDS, "exp": now + _TOKEN_TTL_SECONDS, "iss": self.config.app_id},
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
            raise RuntimeError("GitHub App JWT could not be generated") from exc
        if signed.returncode != 0 or not signed.stdout:
            raise RuntimeError("GitHub App JWT could not be generated")
        return f"{header}.{claims}.{self._base64url(signed.stdout)}"

    async def _issue_token(self) -> str:
        app_jwt = self._app_jwt()
        repository_name = self.config.repository.split("/", 1)[1]
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    f"https://api.github.com/app/installations/{self.config.installation_id}/access_tokens",
                    headers={
                        "Authorization": f"Bearer {app_jwt}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    json={"repositories": [repository_name]},
                )
        except httpx.HTTPError as exc:
            raise RuntimeError("GitHub App installation token request failed") from exc
        if response.status_code != 201:
            raise RuntimeError(f"GitHub App installation token request rejected: HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("GitHub App installation token response is invalid") from exc
        token = str(payload.get("token") or "").strip() if isinstance(payload, dict) else ""
        if len(token) < 20 or any(character.isspace() for character in token):
            raise RuntimeError("GitHub App installation token response is invalid")
        return token

    @asynccontextmanager
    async def headers(self) -> AsyncIterator[dict[str, str]]:
        """Yield headers for one API operation and discard the token reference afterwards."""

        issued = await self._issue_token()
        try:
            yield {
                "Authorization": f"Bearer {issued}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        finally:
            issued = ""
