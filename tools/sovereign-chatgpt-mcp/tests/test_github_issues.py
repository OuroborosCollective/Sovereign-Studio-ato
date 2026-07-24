from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from command_contract import is_mutating_action
from github_admin import GitHubAdminRuntime


@dataclass
class FakeResponse:
    status_code: int
    payload: Any = None
    text: str = ""

    @property
    def content(self) -> bytes:
        if self.status_code == 204 or self.payload is None:
            return b""
        return b"json"

    def json(self) -> Any:
        return self.payload


class FakeSession:
    def __init__(self, routes: dict[tuple[str, str], list[FakeResponse]]) -> None:
        self.routes = {key: list(values) for key, values in routes.items()}
        self.calls: list[dict[str, Any]] = []

    def request(self, method, url, headers=None, params=None, json=None, timeout=None):
        path = url.removeprefix("https://api.github.com")
        self.calls.append({"method": method, "path": path, "params": params, "json": json})
        key = (method, path)
        if key not in self.routes or not self.routes[key]:
            raise AssertionError(f"Unexpected GitHub request: {key}")
        return self.routes[key].pop(0)


class FakeSelfUpdate:
    def schedule(self, *, expected_revision: str, reason: str = "") -> dict[str, Any]:
        raise AssertionError("Issue operations must not schedule an MCP update directly")


def _issue(
    number: int,
    *,
    state: str = "open",
    state_reason: str | None = None,
    updated_at: str = "2026-07-24T10:00:00Z",
    body: str = "Current issue body",
) -> dict[str, Any]:
    return {
        "number": number,
        "title": f"Issue {number}",
        "body": body,
        "state": state,
        "state_reason": state_reason,
        "labels": [{"name": "bug", "color": "d73a4a", "description": "Something is broken"}],
        "user": {"login": "owner", "type": "User", "html_url": "https://github.com/owner"},
        "assignees": [],
        "comments": 2,
        "locked": False,
        "created_at": "2026-07-20T09:00:00Z",
        "updated_at": updated_at,
        "closed_at": "2026-07-24T11:00:00Z" if state == "closed" else None,
        "html_url": f"https://github.com/OuroborosCollective/Sovereign-Studio-ato/issues/{number}",
    }


def _runtime(monkeypatch, routes):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("SOVEREIGN_MCP_REPOSITORY", "OuroborosCollective/Sovereign-Studio-ato")
    session = FakeSession(routes)
    return GitHubAdminRuntime(FakeSelfUpdate(), session=session), session


def test_issue_list_filters_pull_requests_and_returns_authenticated_readback(monkeypatch) -> None:
    repository_path = "/repos/OuroborosCollective/Sovereign-Studio-ato"
    pull = {**_issue(90), "pull_request": {"url": f"{repository_path}/pulls/90"}}
    runtime, session = _runtime(
        monkeypatch,
        {
            ("GET", f"{repository_path}/issues"): [FakeResponse(200, [pull, _issue(12), _issue(11)])],
        },
    )

    result = runtime.list_issues(limit=2)

    assert result["status"] == "ISSUES_VERIFIED"
    assert result["readbackVerified"] is True
    assert result["count"] == 2
    assert [item["number"] for item in result["issues"]] == [12, 11]
    assert session.calls[0]["params"]["state"] == "open"
    assert session.calls[0]["params"]["sort"] == "updated"


def test_issue_read_returns_full_current_body_and_updated_at(monkeypatch) -> None:
    repository_path = "/repos/OuroborosCollective/Sovereign-Studio-ato"
    runtime, _session = _runtime(
        monkeypatch,
        {
            ("GET", f"{repository_path}/issues/12"): [
                FakeResponse(200, _issue(12, body="Exact Markdown body", updated_at="2026-07-24T12:34:56Z"))
            ],
        },
    )

    result = runtime.read_issue(issue_number=12)

    assert result["status"] == "ISSUE_VERIFIED"
    assert result["readbackVerified"] is True
    assert result["issue"]["body"] == "Exact Markdown body"
    assert result["issue"]["updatedAt"] == "2026-07-24T12:34:56Z"


def test_issue_close_blocks_when_readback_is_stale_without_patch(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PR_MERGE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    repository_path = "/repos/OuroborosCollective/Sovereign-Studio-ato"
    runtime, session = _runtime(
        monkeypatch,
        {
            ("GET", f"{repository_path}/issues/12"): [
                FakeResponse(200, _issue(12, updated_at="2026-07-24T12:00:01Z"))
            ],
        },
    )

    result = runtime.close_issue(
        issue_number=12,
        expected_updated_at="2026-07-24T12:00:00Z",
        owner_approved=True,
    )

    assert result["status"] == "BLOCKED"
    assert result["failure_family"] == "ISSUE_STALE_READBACK"
    assert result["readback_verified"] is True
    assert not any(call["method"] == "PATCH" for call in session.calls)


def test_issue_close_requires_owner_and_verifies_completed_readback(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PR_MERGE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    repository_path = "/repos/OuroborosCollective/Sovereign-Studio-ato"
    initial = _issue(12, updated_at="2026-07-24T12:00:00Z")
    closed = _issue(
        12,
        state="closed",
        state_reason="completed",
        updated_at="2026-07-24T12:00:02Z",
    )
    runtime, session = _runtime(
        monkeypatch,
        {
            ("GET", f"{repository_path}/issues/12"): [FakeResponse(200, initial), FakeResponse(200, closed)],
            ("PATCH", f"{repository_path}/issues/12"): [FakeResponse(200, closed)],
        },
    )

    result = runtime.close_issue(
        issue_number=12,
        expected_updated_at="2026-07-24T12:00:00Z",
        owner_approved=True,
    )

    assert result["status"] == "ISSUE_CLOSED"
    assert result["state"] == "closed"
    assert result["stateReason"] == "completed"
    assert result["mutationPerformed"] is True
    assert result["readback_verified"] is True
    patch = next(call for call in session.calls if call["method"] == "PATCH")
    assert patch["json"] == {"state": "closed", "state_reason": "completed"}
    assert is_mutating_action("github_issue_close") is True
