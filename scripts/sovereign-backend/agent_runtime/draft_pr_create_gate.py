"""Draft PR create gate for Sovereign Agent Runtime.

This gate is the explicit server-side transition from a prepared Draft-PR-ready
state to a real GitHub Draft PR URL. It never auto-merges and never treats the UI
as truth. If the server cannot safely create a real PR, it returns a blocker.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .contracts import sanitize_agent_text
from .git_workspace import publish_workspace_branch, resolve_server_github_token
from .job_store import StoredSovereignAgentJob

DraftPrCreateStatus = Literal["created", "blocked"]

_SAFE_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_-]{0,119}$")
_GITHUB_PR_URL = re.compile(r"^https://github\.com/[^/]+/[^/]+/pull/[0-9]+$")
_SECRET_PATTERNS = (
    re.compile(r"github_pat_[A-Za-z0-9_]{10,}", re.IGNORECASE),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{10,}", re.IGNORECASE),
    re.compile(r"sk-proj-[A-Za-z0-9_-]{10,}", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9_-]{10,}", re.IGNORECASE),
    re.compile(r"Authorization:\s*(?:Bearer\s+)?[^\s\n]+", re.IGNORECASE),
    re.compile(r"(?:token|password|secret|api[_-]?key)\s*[=:]\s*[^\s\n]+", re.IGNORECASE),
)


@dataclass(frozen=True)
class DraftPrCreateRequest:
    job_id: str
    repo_url: str
    head_branch: str | None
    base_branch: str | None
    title: str | None
    body: str | None
    pr_state: str | None
    changed_files: tuple[str, ...] = ()
    diff_summary: str | None = None
    test_summary: str | None = None
    existing_pr_url: str | None = None
    workspace_id: str | None = None


@dataclass(frozen=True)
class DraftPrCreateResult:
    allowed: bool
    status: DraftPrCreateStatus
    pr_url: str | None = None
    blocker: str | None = None
    summary: str = "Draft PR create blocked."
    predictive_signal: str = "agent_draft_pr_create_blocked"


class DraftPrCreator(Protocol):
    def create_draft_pr(self, request: DraftPrCreateRequest, token: str) -> str:
        """Create a GitHub Draft PR and return its html_url."""


def _safe_branch(value: str | None) -> bool:
    if not value:
        return False
    return bool(_SAFE_BRANCH.fullmatch(value)) and ".." not in value and not value.endswith("/") and "//" not in value


def _contains_secret(*values: str | None) -> bool:
    text = "\n".join(value or "" for value in values)
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


def _repo_owner_name(repo_url: str) -> tuple[str, str] | None:
    parsed = urlparse(repo_url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        return None
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        return None
    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    if not owner or not repo:
        return None
    return owner, repo


def _server_github_token() -> str | None:
    return resolve_server_github_token()


def _valid_pr_url(value: str | None) -> bool:
    return bool(value and _GITHUB_PR_URL.fullmatch(value.strip()))


class GitHubApiDraftPrCreator:
    """Publish the verified workspace branch and create or recover one Draft PR."""

    def _existing_draft_pr(self, request: DraftPrCreateRequest, token: str, owner: str, repo: str) -> str | None:
        query = urlencode({
            "state": "open",
            "head": f"{owner}:{request.head_branch}",
            "base": request.base_branch or "main",
            "per_page": "10",
        })
        http_request = Request(
            f"https://api.github.com/repos/{owner}/{repo}/pulls?{query}",
            method="GET",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "sovereign-agent-runtime",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urlopen(http_request, timeout=30) as response:  # nosec B310 - validated GitHub API URL.
            data = json.loads(response.read().decode("utf-8"))
        if not isinstance(data, list):
            raise ValueError("GitHub existing pull request lookup returned an invalid response")
        for item in data:
            if not isinstance(item, dict):
                continue
            url = str(item.get("html_url") or "")
            if not _valid_pr_url(url):
                continue
            if item.get("draft") is not True:
                raise ValueError("An open non-draft pull request already exists for the prepared branch")
            return url
        return None

    def create_draft_pr(self, request: DraftPrCreateRequest, token: str) -> str:
        owner_repo = _repo_owner_name(request.repo_url)
        if not owner_repo:
            raise ValueError("repo_url must be a GitHub HTTPS URL")
        if not request.workspace_id:
            raise ValueError("workspace id is required for Draft PR branch publication")
        publication = publish_workspace_branch(
            request.workspace_id,
            repo_url=request.repo_url,
            base_branch=request.base_branch or "main",
            head_branch=request.head_branch or "",
            commit_message=request.title or "Sovereign changes",
            changed_files=request.changed_files,
            token=token,
        )
        if publication.status != "done" or not publication.commit_sha:
            raise RuntimeError(publication.blocker or "workspace branch publication failed")
        owner, repo = owner_repo
        existing = self._existing_draft_pr(request, token, owner, repo)
        if existing:
            return existing
        payload = json.dumps({
            "title": request.title,
            "head": request.head_branch,
            "base": request.base_branch,
            "body": request.body or "",
            "draft": True,
            "maintainer_can_modify": True,
        }).encode("utf-8")
        api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
        http_request = Request(
            api_url,
            data=payload,
            method="POST",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "sovereign-agent-runtime",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urlopen(http_request, timeout=30) as response:  # nosec B310 - GitHub API URL is constructed from validated repo URL.
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code != 422:
                raise
            existing = self._existing_draft_pr(request, token, owner, repo)
            if not existing:
                raise
            return existing
        url = str(data.get("html_url") or "")
        if not _valid_pr_url(url):
            raise ValueError("GitHub did not return a valid pull request URL")
        return url


def draft_pr_create_request_from_job(job: StoredSovereignAgentJob) -> DraftPrCreateRequest:
    body = None
    if isinstance(job.draft_pr_preparation, dict):
        body = job.draft_pr_preparation.get("body") or job.draft_pr_preparation.get("prBody")
    return DraftPrCreateRequest(
        job_id=job.job_id,
        repo_url=job.repo_url,
        head_branch=job.branch_name,
        base_branch=job.target_branch or job.branch,
        title=job.commit_message,
        body=body,
        pr_state=job.pr_state,
        changed_files=job.changed_files,
        diff_summary=job.diff_summary,
        test_summary=job.test_summary,
        existing_pr_url=job.pr_url or job.draft_pr_url,
        workspace_id=job.workspace_id,
    )


def validate_draft_pr_create_request(request: DraftPrCreateRequest) -> tuple[str, ...]:
    blockers: list[str] = []
    if request.pr_state == "created" and _valid_pr_url(request.existing_pr_url):
        return ()
    if request.pr_state != "ready":
        blockers.append("Draft PR create requires pr_state=ready")
    if not _repo_owner_name(request.repo_url):
        blockers.append("repo_url must be a GitHub HTTPS URL")
    if not _safe_branch(request.head_branch):
        blockers.append("head branch is unsafe or missing")
    if not _safe_branch(request.base_branch):
        blockers.append("base branch is unsafe or missing")
    if request.head_branch and request.base_branch and request.head_branch == request.base_branch:
        blockers.append("head branch must differ from base branch")
    if not request.title or len(request.title.strip()) < 3:
        blockers.append("Draft PR title is required")
    if not request.workspace_id:
        blockers.append("Draft PR create requires workspace evidence")
    if not request.changed_files:
        blockers.append("Draft PR create requires changed file evidence")
    if not request.diff_summary:
        blockers.append("Draft PR create requires diff summary evidence")
    if not request.test_summary:
        blockers.append("Draft PR create requires test summary evidence")
    if _contains_secret(
        request.repo_url,
        request.head_branch,
        request.base_branch,
        request.title,
        request.body,
        request.diff_summary,
        request.test_summary,
        "\n".join(request.changed_files),
    ):
        blockers.append("Draft PR create payload contains secret-like material")
    return tuple(dict.fromkeys(blockers))


def create_draft_pr_for_job(
    job: StoredSovereignAgentJob,
    *,
    creator: DraftPrCreator | None = None,
    token: str | None = None,
) -> DraftPrCreateResult:
    request = draft_pr_create_request_from_job(job)
    if request.pr_state == "created" and _valid_pr_url(request.existing_pr_url):
        return DraftPrCreateResult(
            allowed=True,
            status="created",
            pr_url=request.existing_pr_url,
            summary="Draft PR already created.",
            predictive_signal="agent_draft_pr_created",
        )

    blockers = list(validate_draft_pr_create_request(request))
    if blockers:
        return DraftPrCreateResult(
            allowed=False,
            status="blocked",
            blocker="; ".join(blockers),
            summary="Draft PR create blocked by runtime validation.",
            predictive_signal="agent_draft_pr_create_blocked",
        )

    safe_token = token or _server_github_token()
    if not safe_token:
        return DraftPrCreateResult(
            allowed=False,
            status="blocked",
            blocker="server GitHub credentials missing for Draft PR create",
            summary="Draft PR create blocked because the server has no GitHub credential configured.",
            predictive_signal="agent_draft_pr_create_credentials_missing",
        )

    active_creator = creator or GitHubApiDraftPrCreator()
    try:
        pr_url = active_creator.create_draft_pr(request, safe_token)
    except HTTPError as exc:
        return DraftPrCreateResult(
            allowed=False,
            status="blocked",
            blocker=f"GitHub Draft PR create failed with status {exc.code}",
            summary="Draft PR create blocked by GitHub API response.",
            predictive_signal="agent_draft_pr_create_blocked",
        )
    except (URLError, TimeoutError, ValueError, RuntimeError) as exc:
        return DraftPrCreateResult(
            allowed=False,
            status="blocked",
            blocker=sanitize_agent_text(str(exc), 400),
            summary="Draft PR create blocked by runtime exception.",
            predictive_signal="agent_draft_pr_create_blocked",
        )

    if not _valid_pr_url(pr_url):
        return DraftPrCreateResult(
            allowed=False,
            status="blocked",
            blocker="GitHub did not return a valid pull request URL",
            summary="Draft PR create blocked by invalid GitHub result.",
            predictive_signal="agent_draft_pr_create_blocked",
        )

    return DraftPrCreateResult(
        allowed=True,
        status="created",
        pr_url=pr_url,
        summary="GitHub Draft PR created.",
        predictive_signal="agent_draft_pr_created",
    )


def draft_pr_create_signal(result: DraftPrCreateResult) -> dict[str, Any]:
    return {
        "allowed": result.allowed,
        "status": result.status,
        "prUrl": result.pr_url,
        "blocker": result.blocker,
        "summary": result.summary,
        "signal": result.predictive_signal,
    }
