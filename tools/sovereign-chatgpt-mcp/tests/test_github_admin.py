from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

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
        self.calls.append({"method": method, "path": path, "headers": headers, "params": params, "json": json})
        key = (method, path)
        if key not in self.routes or not self.routes[key]:
            raise AssertionError(f"Unexpected GitHub request: {key}")
        return self.routes[key].pop(0)


class FakeSelfUpdate:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def schedule(self, *, expected_revision: str, reason: str = "") -> dict[str, Any]:
        self.calls.append({"expected_revision": expected_revision, "reason": reason})
        return {"ok": True, "status": "SCHEDULED", "expected_revision": expected_revision}


def _pull(head: str, *, draft: bool = False, mergeable: bool = True, base: str = "main") -> dict[str, Any]:
    return {
        "number": 7,
        "title": "Test PR",
        "state": "open",
        "draft": draft,
        "mergeable": mergeable,
        "mergeable_state": "clean",
        "head": {"sha": head},
        "base": {"ref": base},
        "html_url": "https://github.com/example/repo/pull/7",
    }


def _green_checks() -> tuple[FakeResponse, FakeResponse]:
    return (
        FakeResponse(200, {"check_runs": [{"name": "tests", "status": "completed", "conclusion": "success"}]}),
        FakeResponse(200, {"state": "success", "statuses": []}),
    )


def _runtime(monkeypatch, routes):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("SOVEREIGN_MCP_REPOSITORY", "OuroborosCollective/Sovereign-Studio-ato")
    update = FakeSelfUpdate()
    session = FakeSession(routes)
    return GitHubAdminRuntime(update, session=session), update, session


def test_pr_status_requires_real_check_evidence(monkeypatch) -> None:
    head = "a" * 40
    runtime, _update, _session = _runtime(
        monkeypatch,
        {
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7"): [FakeResponse(200, _pull(head))],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/commits/{head}/check-runs"): [FakeResponse(200, {"check_runs": []})],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/commits/{head}/status"): [FakeResponse(200, {"state": "pending", "statuses": []})],
        },
    )

    result = runtime.pr_status(pr_number=7)

    assert result["checks"]["ok"] is False
    assert result["checks"]["has_check_evidence"] is False
    assert "no_check_evidence_reported" in result["checks"]["pending"]


def test_merge_requires_exact_head_green_checks_and_schedules_mcp_reload(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PR_MERGE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_SELF_UPDATE", "1")
    head = "b" * 40
    merge_sha = "c" * 40
    check_runs, legacy = _green_checks()
    runtime, update, _session = _runtime(
        monkeypatch,
        {
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7"): [FakeResponse(200, _pull(head))],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/commits/{head}/check-runs"): [check_runs],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/commits/{head}/status"): [legacy],
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7/files"): [
                FakeResponse(200, [{"filename": "tools/sovereign-chatgpt-mcp/server.py"}])
            ],
            ("PUT", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7/merge"): [
                FakeResponse(200, {"merged": True, "sha": merge_sha, "message": "merged"})
            ],
        },
    )

    result = runtime.merge_pr(pr_number=7, expected_head_sha=head, merge_method="squash")

    assert result["status"] == "MERGED"
    assert result["merge_commit_sha"] == merge_sha
    assert result["touches_private_mcp"] is True
    assert update.calls == [{"expected_revision": merge_sha, "reason": "merged_pr_7"}]


def test_merge_blocks_draft_even_when_checks_are_green(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PR_MERGE", "1")
    head = "d" * 40
    check_runs, legacy = _green_checks()
    runtime, _update, _session = _runtime(
        monkeypatch,
        {
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7"): [FakeResponse(200, _pull(head, draft=True))],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/commits/{head}/check-runs"): [check_runs],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/commits/{head}/status"): [legacy],
        },
    )

    result = runtime.merge_pr(pr_number=7, expected_head_sha=head)

    assert result["status"] == "BLOCKED"
    assert "Draft" in result["blocker"]


def test_failed_workflow_rerun_uses_failed_jobs_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_WORKFLOW_CONTROL", "1")
    head = "e" * 40
    runtime, _update, session = _runtime(
        monkeypatch,
        {
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7"): [FakeResponse(200, _pull(head))],
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/actions/runs"): [
                FakeResponse(200, {"workflow_runs": [{"id": 91, "name": "Android", "conclusion": "failure"}]})
            ],
            ("POST", "/repos/OuroborosCollective/Sovereign-Studio-ato/actions/runs/91/rerun-failed-jobs"): [
                FakeResponse(201, {})
            ],
        },
    )

    result = runtime.rerun_failed_workflows(pr_number=7)

    assert result["status"] == "RERUN_REQUESTED"
    assert result["restarted"][0]["run_id"] == 91
    assert any(call["path"].endswith("/rerun-failed-jobs") for call in session.calls)


def test_allowlisted_android_workflow_can_be_dispatched_without_secret_inputs(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_WORKFLOW_CONTROL", "1")
    runtime, _update, session = _runtime(
        monkeypatch,
        {
            ("POST", "/repos/OuroborosCollective/Sovereign-Studio-ato/actions/workflows/android-release.yml/dispatches"): [
                FakeResponse(
                    200,
                    {
                        "workflow_run_id": 1234,
                        "run_url": "https://api.github.com/repos/OuroborosCollective/Sovereign-Studio-ato/actions/runs/1234",
                        "html_url": "https://github.com/OuroborosCollective/Sovereign-Studio-ato/actions/runs/1234",
                    },
                )
            ]
        },
    )

    result = runtime.dispatch_workflow(
        workflow="android-release.yml",
        ref="main",
        inputs={"version_code": "101", "version_name": "3.1.0"},
    )

    assert result["status"] == "DISPATCHED"
    assert result["run_id"] == 1234
    assert result["url"].endswith("/actions/runs/1234")
    assert session.calls[0]["headers"]["X-GitHub-Api-Version"] == "2026-03-10"
    assert session.calls[0]["json"]["inputs"]["version_code"] == "101"


def test_workflow_dispatch_blocks_when_github_omits_run_evidence(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_WORKFLOW_CONTROL", "1")
    runtime, _update, _session = _runtime(
        monkeypatch,
        {
            ("POST", "/repos/OuroborosCollective/Sovereign-Studio-ato/actions/workflows/android-release.yml/dispatches"): [
                FakeResponse(200, {"workflow_run_id": 0, "run_url": "", "html_url": ""})
            ]
        },
    )

    with pytest.raises(RuntimeError, match="Workflow-Run-Evidence"):
        runtime.dispatch_workflow(workflow="android-release.yml", ref="main", inputs={})


def test_workflow_dispatch_rejects_secret_shaped_inputs(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_WORKFLOW_CONTROL", "1")
    runtime, _update, _session = _runtime(monkeypatch, {})

    with pytest.raises(ValueError, match="Secrets"):
        runtime.dispatch_workflow(
            workflow="android-release.yml",
            ref="main",
            inputs={"keystore_password": "never"},
        )


def test_workflow_run_status_returns_failed_step_evidence(monkeypatch) -> None:
    runtime, _update, _session = _runtime(
        monkeypatch,
        {
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/actions/runs/99"): [
                FakeResponse(200, {"name": "Android", "head_sha": "f" * 40, "status": "completed", "conclusion": "failure", "html_url": "https://example/run/99"})
            ],
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/actions/runs/99/jobs"): [
                FakeResponse(200, {"jobs": [{"id": 5, "name": "build", "status": "completed", "conclusion": "failure", "steps": [{"name": "Compile", "conclusion": "failure"}]}]})
            ],
        },
    )

    result = runtime.workflow_run_status(run_id=99)

    assert result["conclusion"] == "failure"
    assert result["jobs"][0]["failed_steps"] == ["Compile"]
