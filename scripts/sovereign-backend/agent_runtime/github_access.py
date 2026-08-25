"""Repo-scoped, one-shot GitHub credential preflight for the user Agent runtime.

The raw credential is never persisted or returned. This preflight proves only
that GitHub accepts the credential for the exact target repository and that the
repository reports effective write authority. The later git push / Draft-PR
creation remains the authoritative mutation check.
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
import binascii
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


class GitHubRepositoryReadBlocked(PermissionError):
    """The requested path or decoded content is unsafe to expose to a browser."""


class GitHubRepositoryReadBinary(RuntimeError):
    """The immutable blob is not valid previewable UTF-8 text."""


class GitHubRepositoryReadUpstreamError(RuntimeError):
    """GitHub returned a malformed or contradictory repository-file payload."""


_SCOPE_REVISION = re.compile(r"^[0-9a-f]{40}$")
_SCOPE_PURPOSE = re.compile(r"^[a-z][a-z0-9._:-]{2,95}$")
_SCOPE_TTL_SECONDS = 600
_REPOSITORY_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
_SENSITIVE_REPOSITORY_FILE = re.compile(
    r"(?:^|/)(?:\.env(?:\.[^/]*)?|\.npmrc|\.pypirc|\.netrc|\.git-credentials|"
    r"id_(?:rsa|dsa|ecdsa|ed25519)(?:\.pub)?|"
    r"(?:credentials?|secrets?)(?:\.(?:json|ya?ml|toml|ini|cfg|conf|txt))?)(?:$|/)|"
    r"\.(?:pem|key|p12|pfx|jks|keystore|kdbx)$",
    re.IGNORECASE,
)
_SECRET_CONTENT_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b", re.IGNORECASE),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b", re.IGNORECASE),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{10,}\b", re.IGNORECASE),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAuthorization:\s*(?:Bearer\s+)?[^\s\r\n]{12,}", re.IGNORECASE),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(
        r"(?im)^\s*(?:export\s+)?[A-Z][A-Z0-9_]{1,80}"
        r"(?:TOKEN|PASSWORD|PASSWD|SECRET|API_KEY|PRIVATE_KEY)"
        r"\s*=\s*['\"]?[^'\"\s]{8,}"
    ),
    re.compile(
        r"""(?im)(?:^|[,{])\s*["']?[A-Za-z0-9_.-]*(?:token|password|passwd|secret|"""
        r"""api[_-]?key|private[_-]?key|access[_-]?key)[A-Za-z0-9_.-]*["']?"""
        r"""\s*[:=]\s*["']?(?!\s*(?:$|null\b|none\b|false\b|true\b|\$\{|<))"""
        r"""[^\s,'"}#]{6,}"""
    ),
)
MAX_REPOSITORY_FILE_BYTES = 100_000


def ensure_repository_preview_path_safe(path: str) -> None:
    """Reject repository paths whose contents must never enter a browser preview."""

    if _SENSITIVE_REPOSITORY_FILE.search(path):
        raise GitHubRepositoryReadBlocked("repository_file_sensitive_path_blocked")


def decode_repository_preview_bytes(path: str, content_bytes: bytes) -> str:
    """Decode one observed byte buffer and fail closed on binary or secret content."""

    ensure_repository_preview_path_safe(path)
    try:
        text = content_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GitHubRepositoryReadBinary("repository_file_binary_unsupported") from exc
    if "\x00" in text:
        raise GitHubRepositoryReadBinary("repository_file_binary_unsupported")
    if any(pattern.search(text) for pattern in _SECRET_CONTENT_PATTERNS):
        raise GitHubRepositoryReadBlocked("repository_file_secret_content_blocked")
    return text


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


def resolve_request_github_token(
    raw_token: object,
    *,
    user_id: str,
    get_session_github_token: Callable[[str], str | None] | None,
) -> str | None:
    """Resolve one request-local GitHub credential without persisting it.

    An explicitly supplied credential is authoritative: malformed explicit input
    must fail closed instead of silently falling back to a server-held OAuth
    session. When the browser deliberately sends no token, the backend may use
    the authenticated user's server-held credential for this request only.
    """

    if raw_token is not None:
        token = normalize_ephemeral_github_token(raw_token)
        if token is None:
            raise ValueError("githubAccessToken has an invalid format")
        return token
    if get_session_github_token is None:
        return None
    try:
        return normalize_ephemeral_github_token(get_session_github_token(user_id))
    except Exception:
        return None


def read_github_repository_file(
    raw_token: object,
    *,
    owner: object,
    repo: object,
    revision: object,
    path: object,
    max_bytes: int = MAX_REPOSITORY_FILE_BYTES,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, object]:
    """Read one immutable, scoped text blob without exposing credential material."""

    safe_owner = str(owner or "").strip()
    safe_repo = str(repo or "").strip().removesuffix(".git")
    safe_revision = str(revision or "").strip().lower()
    raw_path = str(path or "")
    safe_path = raw_path
    if not _REPOSITORY_COMPONENT.fullmatch(safe_owner) or not _REPOSITORY_COMPONENT.fullmatch(safe_repo):
        raise ValueError("repository_target_invalid")
    if not _SCOPE_REVISION.fullmatch(safe_revision):
        raise ValueError("repository_revision_invalid")
    if (
        not safe_path
        or raw_path != raw_path.strip()
        or safe_path.startswith("/")
        or "\\" in safe_path
        or "\x00" in safe_path
        or any(segment in ("", ".", "..") for segment in safe_path.split("/"))
    ):
        raise ValueError("repository_file_path_invalid")
    ensure_repository_preview_path_safe(safe_path)
    try:
        bounded_max_bytes = max(1, min(int(max_bytes), MAX_REPOSITORY_FILE_BYTES))
    except (TypeError, ValueError) as exc:
        raise ValueError("repository_file_max_bytes_invalid") from exc

    token = None
    if raw_token is not None:
        token = normalize_ephemeral_github_token(raw_token)
        if token is None:
            raise ValueError("github_access_token_invalid")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "sovereign-agent-runtime",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        (
            f"https://api.github.com/repos/{quote(safe_owner, safe='')}/{quote(safe_repo, safe='')}"
            f"/contents/{quote(safe_path, safe='/')}?ref={quote(safe_revision, safe='')}"
        ),
        method="GET",
        headers=headers,
    )
    try:
        with opener(request, timeout=30) as response:  # nosec B310 - fixed GitHub API origin.
            payload = json.loads(response.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise GitHubRepositoryReadUpstreamError("repository_file_payload_invalid") from exc
    if not isinstance(payload, dict) or payload.get("type") != "file":
        raise GitHubRepositoryReadUpstreamError("repository_file_payload_invalid")
    if str(payload.get("encoding") or "").lower() != "base64":
        raise GitHubRepositoryReadUpstreamError("repository_file_encoding_unsupported")
    encoded_content = payload.get("content")
    if not isinstance(encoded_content, str):
        raise GitHubRepositoryReadUpstreamError("repository_file_content_missing")
    try:
        content_bytes = base64.b64decode("".join(encoded_content.split()), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise GitHubRepositoryReadUpstreamError("repository_file_content_invalid") from exc
    blob_sha = str(payload.get("sha") or "").strip().lower()
    if not _SCOPE_REVISION.fullmatch(blob_sha):
        raise GitHubRepositoryReadUpstreamError("repository_file_blob_identity_invalid")
    git_blob_payload = b"blob " + str(len(content_bytes)).encode("ascii") + b"\x00" + content_bytes
    observed_blob_sha = hashlib.sha1(git_blob_payload, usedforsecurity=False).hexdigest()
    if not hmac.compare_digest(blob_sha, observed_blob_sha):
        raise GitHubRepositoryReadUpstreamError("repository_file_blob_identity_mismatch")
    full_text = decode_repository_preview_bytes(safe_path, content_bytes)

    truncated = len(content_bytes) > bounded_max_bytes
    # The full blob has already passed strict UTF-8 validation. When a bounded
    # byte prefix ends inside one code point, drop only that partial character;
    # the explicit truncated flag makes the intentionally incomplete preview clear.
    visible_text = (
        content_bytes[:bounded_max_bytes].decode("utf-8", errors="ignore")
        if truncated
        else full_text
    )
    return {
        "path": safe_path,
        "revision": safe_revision,
        "sha": blob_sha,
        "bytes": len(content_bytes),
        "content": visible_text,
        "truncated": truncated,
    }


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
