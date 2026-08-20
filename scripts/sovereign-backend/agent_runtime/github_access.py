"""Repo-scoped, one-shot GitHub credential preflight for the user Agent runtime.

The raw credential is never persisted or returned. This preflight proves only
that GitHub accepts the credential for the exact target repository and that the
repository reports effective write authority. The later git push / Draft-PR
creation remains the authoritative mutation check.
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import hmac
import json
import re
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from .git_workspace import normalize_ephemeral_github_token


@dataclass(frozen=True)
class GitHubAccessValidation:
    ok: bool
    can_write: bool
    code: str
    message: str


@dataclass(frozen=True)
class GitHubAccessScope:
    owner: str
    repo: str
    branch: str
    revision: str
    purpose: str


_SCOPE_REVISION = re.compile(r"^[0-9a-f]{40}$")
_SCOPE_PURPOSE = re.compile(r"^[a-z][a-z0-9._:-]{2,95}$")
_SCOPE_TTL_SECONDS = 600


def _scope_target(repository: object) -> tuple[str, str] | None:
    parsed = urlparse(str(repository or "").strip())
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        return None
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) != 2:
        return None
    owner, repo = parts
    repo = repo.removesuffix(".git")
    if not owner or not repo or "/" in owner or "/" in repo:
        return None
    return owner, repo


def _scope_message(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _scope_signing_key(secret: object) -> bytes | None:
    source = str(secret or "").encode("utf-8")
    if not source:
        return None
    return hashlib.sha256(b"sovereign-github-access-scope-v1\\x00" + source).digest()


def issue_github_access_scope(
    *,
    user_id: object,
    repository: object,
    branch: object,
    revision: object,
    purpose: object,
    secret: object,
    now: int | None = None,
) -> str:
    """Issue a short-lived, signed GitHub repository scope without storing the credential."""

    target = _scope_target(repository)
    normalized_user = str(user_id or "").strip()
    normalized_branch = str(branch or "").strip()
    normalized_revision = str(revision or "").strip().lower()
    normalized_purpose = str(purpose or "").strip().lower()
    signing_key = _scope_signing_key(secret)
    if target is None or not normalized_user or not normalized_branch or "\n" in normalized_branch:
        raise ValueError("github_access_scope_target_invalid")
    if not _SCOPE_REVISION.fullmatch(normalized_revision):
        raise ValueError("github_access_scope_revision_invalid")
    if not _SCOPE_PURPOSE.fullmatch(normalized_purpose):
        raise ValueError("github_access_scope_purpose_invalid")
    if signing_key is None:
        raise RuntimeError("github_access_scope_secret_unavailable")
    owner, repo = target
    payload: dict[str, object] = {
        "branch": normalized_branch,
        "iat": int(time.time() if now is None else now),
        "owner": owner,
        "purpose": normalized_purpose,
        "repo": repo,
        "revision": normalized_revision,
        "userId": normalized_user,
    }
    encoded = base64.urlsafe_b64encode(_scope_message(payload)).decode("ascii").rstrip("=")
    signature = hmac.new(signing_key, encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"v1.{encoded}.{signature}"


def verify_github_access_scope(
    scope: object,
    *,
    user_id: object,
    secret: object,
    purpose: object,
    now: int | None = None,
    ttl_seconds: int = _SCOPE_TTL_SECONDS,
) -> GitHubAccessScope | None:
    """Verify scope signature, short expiry and session identity before credential validation."""

    try:
        version, encoded, supplied_signature = str(scope or "").split(".", 2)
        signing_key = _scope_signing_key(secret)
        if version != "v1" or signing_key is None or not re.fullmatch(r"[0-9a-f]{64}", supplied_signature):
            return None
        expected_signature = hmac.new(signing_key, encoded.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return None
        decoded = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        payload = json.loads(decoded.decode("utf-8"))
        if not isinstance(payload, dict):
            return None
        issued_at = payload.get("iat")
        current = int(time.time() if now is None else now)
        if not isinstance(issued_at, int) or issued_at > current + 30 or current - issued_at > max(1, int(ttl_seconds)):
            return None
        if not hmac.compare_digest(str(payload.get("userId") or ""), str(user_id or "").strip()):
            return None
        repository = f"https://github.com/{payload.get('owner')}/{payload.get('repo')}"
        target = _scope_target(repository)
        revision = str(payload.get("revision") or "").lower()
        branch = str(payload.get("branch") or "").strip()
        scope_purpose = str(payload.get("purpose") or "").strip().lower()
        expected_purpose = str(purpose or "").strip().lower()
        if (
            target is None
            or not _SCOPE_REVISION.fullmatch(revision)
            or not branch
            or "\n" in branch
            or not _SCOPE_PURPOSE.fullmatch(scope_purpose)
            or not _SCOPE_PURPOSE.fullmatch(expected_purpose)
            or not hmac.compare_digest(scope_purpose, expected_purpose)
        ):
            return None
        return GitHubAccessScope(
            owner=target[0],
            repo=target[1],
            branch=branch,
            revision=revision,
            purpose=scope_purpose,
        )
    except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None


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
