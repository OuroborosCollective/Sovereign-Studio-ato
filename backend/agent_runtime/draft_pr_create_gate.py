"""Draft PR create gate for Sovereign Agent Runtime.

This gate is the explicit server-side transition from a prepared Draft-PR-ready
state to a real GitHub Draft PR. It never auto-merges and never treats the UI or
a returned URL as truth. A live create is successful only after GitHub readback
proves the PR is open + draft, its base/head branches match, its head SHA equals
the commit published from the isolated workspace, and the check/status surfaces
for that exact SHA were read successfully.
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
DraftPrCiState = Literal["none", "pending", "success", "failure"]

_SAFE_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_-]{0,119}$")
_GITHUB_PR_URL = re.compile(r"^https://github\.com/[^/]+/[^/]+/pull/[0-9]+$")
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SECRET_PATTERNS = (
    re.compile(r"github_pat_[A-Za-z0-9_]{10,}", re.IGNORECASE),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{10,}", re.IGNORECASE),
    re.compile(r"sk-proj-[A-Za-z0-9_-]{10,}", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9_-]{10,}", re.IGNORECASE),
    re.compile(r"Authorization:\s*(?:Bearer\s+)?[^\s\n]+", re.IGNORECASE),
    re.compile(r"(?:token|password|secret|api[_-]?key)\s*[=:]\s*[^\s\n]+", re.IGNORECASE),
)
_FAILED_CHECK_CONCLUSIONS = frozenset({
    "action_required",
    "cancelled",
    "failure",
    "startup_failure",
    "stale",
    "timed_out",
})


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
class DraftPrPublicationEvidence:
    pr_url: str
    pr_number: int
    published_head_sha: str
    readback_head_sha: str
    draft_verified: bool
    state: str
    head_branch: str
    base_branch: str
    readback_verified: bool
    checks_readback_verified: bool
    ci_state: DraftPrCiState
    check_run_count: int
    checks_pending_count: int
    checks_success_count: int
    checks_failure_count: int
    status_context_count: int


@dataclass(frozen=True)
class DraftPrCreateResult:
    allowed: bool
    status: DraftPrCreateStatus
    pr_url: str | None = None
    head_sha: str | None = None
    published_head_sha: str | None = None
    readback_head_sha: str | None = None
    pr_number: int | None = None
    draft_verified: bool = False
    pr_state_verified: str | None = None
    head_branch: str | None = None
    base_branch: str | None = None
    readback_verified: bool = False
    checks_readback_verified: bool = False
    ci_state: DraftPrCiState | None = None
    check_run_count: int = 0
    checks_pending_count: int = 0
    checks_success_count: int = 0
    checks_failure_count: int = 0
    status_context_count: int = 0
    blocker: str | None = None
    summary: str = "Draft PR create blocked."
    predictive_signal: str = "agent_draft_pr_create_blocked"


class DraftPrCreator(Protocol):
    def create_draft_pr(
        self,
        request: DraftPrCreateRequest,
        token: str,
    ) -> DraftPrPublicationEvidence | str | tuple[str, str]:
        """Create a GitHub Draft PR. Production returns verified readback evidence."""


class DraftPrPublicationError(RuntimeError):
    """A PR side effect exists but its required readback could not be verified."""

    def __init__(self, message: str, *, pr_url: str | None = None, head_sha: str | None = None) -> None:
        super().__init__(message)
        self.pr_url = pr_url if _valid_pr_url(pr_url) else None
        self.head_sha = head_sha if head_sha and _COMMIT_SHA.fullmatch(head_sha) else None


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


def _pr_number_from_url(value: str | None) -> int | None:
    if not _valid_pr_url(value):
        return None
    try:
        number = int(str(value).rstrip("/").rsplit("/", 1)[-1])
    except ValueError:
        return None
    return number if number > 0 else None


def _github_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "sovereign-agent-runtime",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _github_json(url: str, token: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = _github_headers(token)
    if data is not None:
        headers["Content-Type"] = "application/json"
    http_request = Request(url, data=data, method=method, headers=headers)
    with urlopen(http_request, timeout=30) as response:  # nosec B310 - callers construct validated api.github.com URLs.
        return json.loads(response.read().decode("utf-8"))


def _ci_state(
    *,
    check_run_count: int,
    pending_count: int,
    failure_count: int,
    status_context_count: int,
    combined_status: str,
) -> DraftPrCiState:
    state = combined_status.strip().lower()
    if failure_count > 0 or state in {"failure", "error"}:
        return "failure"
    if pending_count > 0:
        return "pending"
    if check_run_count == 0 and status_context_count == 0:
        return "none"
    if state == "pending":
        return "pending"
    return "success"


class GitHubApiDraftPrCreator:
    """Publish one verified workspace branch and create/recover one verified Draft PR."""

    def _existing_draft_pr(
        self,
        request: DraftPrCreateRequest,
        token: str,
        owner: str,
        repo: str,
    ) -> tuple[str, int] | None:
        query = urlencode({
            "state": "open",
            "head": f"{owner}:{request.head_branch}",
            "base": request.base_branch or "main",
            "per_page": "10",
        })
        data = _github_json(
            f"https://api.github.com/repos/{owner}/{repo}/pulls?{query}",
            token,
        )
        if not isinstance(data, list):
            raise ValueError("GitHub existing pull request lookup returned an invalid response")
        for item in data:
            if not isinstance(item, dict):
                continue
            url = str(item.get("html_url") or "")
            number = item.get("number")
            if not _valid_pr_url(url) or not isinstance(number, int) or number <= 0:
                continue
            if item.get("draft") is not True:
                raise ValueError("An open non-draft pull request already exists for the prepared branch")
            return url, number
        return None

    def _check_runs(self, owner: str, repo: str, head_sha: str, token: str) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        expected_total: int | None = None
        for page in range(1, 11):
            query = urlencode({"per_page": "100", "page": str(page)})
            data = _github_json(
                f"https://api.github.com/repos/{owner}/{repo}/commits/{head_sha}/check-runs?{query}",
                token,
            )
            if not isinstance(data, dict):
                raise ValueError("GitHub check-runs readback returned an invalid response")
            total = data.get("total_count")
            page_runs = data.get("check_runs")
            if not isinstance(total, int) or total < 0 or not isinstance(page_runs, list):
                raise ValueError("GitHub check-runs readback contract invalid")
            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                raise ValueError("GitHub check-runs changed during bounded readback")
            runs.extend(item for item in page_runs if isinstance(item, dict))
            if len(runs) >= total:
                break
            if not page_runs:
                raise ValueError("GitHub check-runs pagination ended before total_count")
        if expected_total is None or len(runs) != expected_total:
            raise ValueError("GitHub check-runs exceed bounded readback or are incomplete")
        return runs

    def _readback_evidence(
        self,
        request: DraftPrCreateRequest,
        token: str,
        owner: str,
        repo: str,
        *,
        pr_url: str,
        pr_number: int,
        expected_head_sha: str | None,
    ) -> DraftPrPublicationEvidence:
        try:
            data = _github_json(
                f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
                token,
            )
            if not isinstance(data, dict):
                raise ValueError("GitHub pull request readback returned an invalid response")
            readback_url = str(data.get("html_url") or "")
            state = str(data.get("state") or "").strip().lower()
            head = data.get("head")
            base = data.get("base")
            if not isinstance(head, dict) or not isinstance(base, dict):
                raise ValueError("GitHub pull request branch readback is missing")
            head_branch = str(head.get("ref") or "")
            base_branch = str(base.get("ref") or "")
            readback_head_sha = str(head.get("sha") or "").strip().lower()
            head_repo = head.get("repo") if isinstance(head.get("repo"), dict) else {}
            base_repo = base.get("repo") if isinstance(base.get("repo"), dict) else {}
            expected_full_name = f"{owner}/{repo}".lower()
            if (
                readback_url != pr_url
                or data.get("draft") is not True
                or state != "open"
                or head_branch != (request.head_branch or "")
                or base_branch != (request.base_branch or "main")
                or not _COMMIT_SHA.fullmatch(readback_head_sha)
                or str(head_repo.get("full_name") or "").lower() != expected_full_name
                or str(base_repo.get("full_name") or "").lower() != expected_full_name
            ):
                raise ValueError("GitHub Draft PR identity readback mismatch")
            if expected_head_sha is not None and readback_head_sha != expected_head_sha:
                raise ValueError("Published workspace SHA does not match GitHub Draft PR head SHA")

            check_runs = self._check_runs(owner, repo, readback_head_sha, token)
            status_data = _github_json(
                f"https://api.github.com/repos/{owner}/{repo}/commits/{readback_head_sha}/status?per_page=100",
                token,
            )
            if not isinstance(status_data, dict):
                raise ValueError("GitHub combined status readback returned an invalid response")
            statuses = status_data.get("statuses")
            total_count = status_data.get("total_count")
            combined_status = str(status_data.get("state") or "").strip().lower()
            if (
                not isinstance(statuses, list)
                or not isinstance(total_count, int)
                or total_count < 0
                or combined_status not in {"error", "failure", "pending", "success"}
            ):
                raise ValueError("GitHub combined status readback contract invalid")

            pending_count = sum(1 for item in check_runs if str(item.get("status") or "") != "completed")
            failure_count = sum(
                1
                for item in check_runs
                if str(item.get("status") or "") == "completed"
                and str(item.get("conclusion") or "").lower() in _FAILED_CHECK_CONCLUSIONS
            )
            success_count = max(0, len(check_runs) - pending_count - failure_count)
            ci_state = _ci_state(
                check_run_count=len(check_runs),
                pending_count=pending_count,
                failure_count=failure_count,
                status_context_count=total_count,
                combined_status=combined_status,
            )
            return DraftPrPublicationEvidence(
                pr_url=pr_url,
                pr_number=pr_number,
                published_head_sha=expected_head_sha or readback_head_sha,
                readback_head_sha=readback_head_sha,
                draft_verified=True,
                state=state,
                head_branch=head_branch,
                base_branch=base_branch,
                readback_verified=True,
                checks_readback_verified=True,
                ci_state=ci_state,
                check_run_count=len(check_runs),
                checks_pending_count=pending_count,
                checks_success_count=success_count,
                checks_failure_count=failure_count,
                status_context_count=total_count,
            )
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise DraftPrPublicationError(
                sanitize_agent_text(str(exc), 300) or "GitHub Draft PR readback failed",
                pr_url=pr_url,
                head_sha=expected_head_sha,
            ) from exc

    def verify_existing_draft_pr(
        self,
        request: DraftPrCreateRequest,
        token: str,
    ) -> DraftPrPublicationEvidence:
        owner_repo = _repo_owner_name(request.repo_url)
        pr_number = _pr_number_from_url(request.existing_pr_url)
        if not owner_repo or pr_number is None or not request.existing_pr_url:
            raise ValueError("existing Draft PR identity is invalid")
        owner, repo = owner_repo
        return self._readback_evidence(
            request,
            token,
            owner,
            repo,
            pr_url=request.existing_pr_url,
            pr_number=pr_number,
            expected_head_sha=None,
        )

    def create_draft_pr(
        self,
        request: DraftPrCreateRequest,
        token: str,
    ) -> DraftPrPublicationEvidence:
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
        published_head_sha = publication.commit_sha.strip().lower()
        if not _COMMIT_SHA.fullmatch(published_head_sha):
            raise ValueError("workspace branch publication returned an invalid commit SHA")

        owner, repo = owner_repo
        existing = self._existing_draft_pr(request, token, owner, repo)
        if existing:
            pr_url, pr_number = existing
            return self._readback_evidence(
                request,
                token,
                owner,
                repo,
                pr_url=pr_url,
                pr_number=pr_number,
                expected_head_sha=published_head_sha,
            )

        api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
        payload = {
            "title": request.title,
            "head": request.head_branch,
            "base": request.base_branch,
            "body": request.body or "",
            "draft": True,
            "maintainer_can_modify": True,
        }
        try:
            data = _github_json(api_url, token, method="POST", payload=payload)
        except HTTPError as exc:
            if exc.code != 422:
                raise
            existing = self._existing_draft_pr(request, token, owner, repo)
            if not existing:
                raise
            pr_url, pr_number = existing
        else:
            if not isinstance(data, dict):
                raise ValueError("GitHub Draft PR create returned an invalid response")
            pr_url = str(data.get("html_url") or "")
            pr_number = data.get("number")
            if not _valid_pr_url(pr_url) or not isinstance(pr_number, int) or pr_number <= 0:
                raise ValueError("GitHub did not return a valid pull request identity")

        return self._readback_evidence(
            request,
            token,
            owner,
            repo,
            pr_url=pr_url,
            pr_number=pr_number,
            expected_head_sha=published_head_sha,
        )


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
        if not _repo_owner_name(request.repo_url):
            blockers.append("repo_url must be a GitHub HTTPS URL")
        if not _safe_branch(request.head_branch):
            blockers.append("head branch is unsafe or missing")
        if not _safe_branch(request.base_branch):
            blockers.append("base branch is unsafe or missing")
        return tuple(dict.fromkeys(blockers))
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


def _result_from_evidence(evidence: DraftPrPublicationEvidence, *, summary: str) -> DraftPrCreateResult:
    return DraftPrCreateResult(
        allowed=(
            evidence.readback_verified
            and evidence.checks_readback_verified
            and evidence.draft_verified
            and evidence.state == "open"
            and evidence.published_head_sha == evidence.readback_head_sha
        ),
        status="created" if (
            evidence.readback_verified
            and evidence.checks_readback_verified
            and evidence.draft_verified
            and evidence.state == "open"
            and evidence.published_head_sha == evidence.readback_head_sha
        ) else "blocked",
        pr_url=evidence.pr_url,
        head_sha=evidence.readback_head_sha,
        published_head_sha=evidence.published_head_sha,
        readback_head_sha=evidence.readback_head_sha,
        pr_number=evidence.pr_number,
        draft_verified=evidence.draft_verified,
        pr_state_verified=evidence.state,
        head_branch=evidence.head_branch,
        base_branch=evidence.base_branch,
        readback_verified=evidence.readback_verified,
        checks_readback_verified=evidence.checks_readback_verified,
        ci_state=evidence.ci_state,
        check_run_count=evidence.check_run_count,
        checks_pending_count=evidence.checks_pending_count,
        checks_success_count=evidence.checks_success_count,
        checks_failure_count=evidence.checks_failure_count,
        status_context_count=evidence.status_context_count,
        blocker=None,
        summary=summary,
        predictive_signal="agent_draft_pr_created",
    )


def create_draft_pr_for_job(
    job: StoredSovereignAgentJob,
    *,
    creator: DraftPrCreator | None = None,
    token: str | None = None,
) -> DraftPrCreateResult:
    request = draft_pr_create_request_from_job(job)
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
        if request.pr_state == "created" and _valid_pr_url(request.existing_pr_url):
            verifier = getattr(active_creator, "verify_existing_draft_pr", None)
            if callable(verifier):
                verified = verifier(request, safe_token)
                if not isinstance(verified, DraftPrPublicationEvidence):
                    raise ValueError("Draft PR verifier did not return publication evidence")
                return _result_from_evidence(verified, summary="Existing GitHub Draft PR re-verified.")
            # Compatibility only for injected unit-test creators. Production's
            # GitHubApiDraftPrCreator always performs live readback.
            return DraftPrCreateResult(
                allowed=True,
                status="created",
                pr_url=request.existing_pr_url,
                summary="Draft PR already created (injected creator without live readback).",
                predictive_signal="agent_draft_pr_created_unverified_test_creator",
            )

        created = active_creator.create_draft_pr(request, safe_token)
        if isinstance(created, DraftPrPublicationEvidence):
            return _result_from_evidence(created, summary="GitHub Draft PR created and read back.")
        # Compatibility only for injected unit-test creators. The production
        # creator never returns this legacy shape, and the browser rejects it.
        if isinstance(created, tuple):
            pr_url, published_head_sha = created
        else:
            pr_url, published_head_sha = created, None
        if published_head_sha and not _COMMIT_SHA.fullmatch(published_head_sha):
            raise ValueError("GitHub publication returned an invalid head SHA")
    except DraftPrPublicationError as exc:
        return DraftPrCreateResult(
            allowed=False,
            status="blocked",
            pr_url=exc.pr_url,
            head_sha=exc.head_sha,
            published_head_sha=exc.head_sha,
            blocker=sanitize_agent_text(str(exc), 400),
            summary="Draft PR exists or may exist, but GitHub readback did not verify it.",
            predictive_signal="agent_draft_pr_create_readback_blocked",
        )
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
        head_sha=published_head_sha,
        published_head_sha=published_head_sha,
        summary="Draft PR created by injected legacy creator without production readback.",
        predictive_signal="agent_draft_pr_created_unverified_test_creator",
    )


def draft_pr_create_signal(result: DraftPrCreateResult) -> dict[str, Any]:
    return {
        "allowed": result.allowed,
        "status": result.status,
        "prUrl": result.pr_url,
        "headSha": result.head_sha,
        "publishedHeadSha": result.published_head_sha,
        "readbackHeadSha": result.readback_head_sha,
        "prNumber": result.pr_number,
        "draftVerified": result.draft_verified,
        "prStateVerified": result.pr_state_verified,
        "headBranch": result.head_branch,
        "baseBranch": result.base_branch,
        "readbackVerified": result.readback_verified,
        "checksReadbackVerified": result.checks_readback_verified,
        "ciState": result.ci_state,
        "checkRunCount": result.check_run_count,
        "checksPendingCount": result.checks_pending_count,
        "checksSuccessCount": result.checks_success_count,
        "checksFailureCount": result.checks_failure_count,
        "statusContextCount": result.status_context_count,
        "blocker": result.blocker,
        "summary": result.summary,
        "signal": result.predictive_signal,
    }
