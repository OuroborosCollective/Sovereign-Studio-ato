"""Repo-scoped, one-shot GitHub credential preflight for the user Agent runtime.

The raw credential is never persisted or returned. This preflight proves only
that GitHub accepts the credential for the exact target repository and that the
repository reports effective write authority. The later git push / Draft-PR
creation remains the authoritative mutation check.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .git_workspace import normalize_ephemeral_github_token


@dataclass(frozen=True)
class GitHubAccessValidation:
    ok: bool
    can_write: bool
    code: str
    message: str


def _has_effective_write_permission(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    permissions = payload.get("permissions")
    if not isinstance(permissions, dict):
        return False
    return any(permissions.get(name) is True for name in ("push", "maintain", "admin"))


def validate_github_access_for_repo(
    raw_token: object,
    *,
    owner: str,
    repo: str,
    opener: Callable[..., Any] = urlopen,
) -> GitHubAccessValidation:
    """Validate one ephemeral credential against the exact repository, without writes."""

    token = normalize_ephemeral_github_token(raw_token)
    if token is None:
        return GitHubAccessValidation(False, False, "invalid_format", "GitHub-Zugang hat ein ungültiges Token-Format.")

    safe_owner = owner.strip()
    safe_repo = repo.strip().removesuffix(".git")
    if not safe_owner or not safe_repo or "/" in safe_owner or "/" in safe_repo:
        return GitHubAccessValidation(False, False, "invalid_target", "Repo-Ziel fehlt oder ist ungültig.")

    request = Request(
        f"https://api.github.com/repos/{quote(safe_owner, safe='')}/{quote(safe_repo, safe='')}",
        method="GET",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "sovereign-agent-runtime",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with opener(request, timeout=30) as response:  # nosec B310 - fixed GitHub API origin.
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 401:
            return GitHubAccessValidation(False, False, "credential_rejected", "GitHub hat diesen Zugang nicht authentifiziert. Token auf Ablauf, Widerruf oder Tippfehler prüfen.")
        if exc.code == 404:
            return GitHubAccessValidation(False, False, "repo_unavailable", "GitHub-Zugang kann dieses Repository nicht lesen oder das Repository ist für diesen Zugang nicht freigegeben.")
        if exc.code == 403:
            return GitHubAccessValidation(False, False, "repo_forbidden", "GitHub hat den Zugriff auf dieses Repository für diesen Zugang verweigert.")
        return GitHubAccessValidation(False, False, "github_http_error", f"GitHub-Zugangsprüfung schlug mit HTTP {exc.code} fehl.")
    except (URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return GitHubAccessValidation(False, False, "github_unavailable", "GitHub-Zugangsprüfung ist momentan nicht verlässlich erreichbar.")

    if not _has_effective_write_permission(payload):
        return GitHubAccessValidation(False, False, "write_permission_missing", "GitHub akzeptiert den Zugang für dieses Repository, meldet aber keinen effektiven Schreibzugriff.")

    return GitHubAccessValidation(True, True, "ready", "GitHub-Zugang wurde serverseitig für dieses Repository bestätigt.")
