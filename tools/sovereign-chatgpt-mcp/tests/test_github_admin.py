from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any
import zipfile

import pytest

from github_admin import GitHubAdminRuntime
from github_installation_auth import GitHubAppInstallationAuth


@dataclass
class FakeResponse:
    status_code: int
    payload: Any = None
    text: str = ""
    body: bytes | None = None

    @property
    def content(self) -> bytes:
        if self.body is not None:
            return self.body
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

    def post(self, url, headers=None, json=None, timeout=None):
        return self.request("POST", url, headers=headers, json=json, timeout=timeout)


class FakeSelfUpdate:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def schedule(self, *, expected_revision: str, reason: str = "") -> dict[str, Any]:
        self.calls.append({"expected_revision": expected_revision, "reason": reason})
        return {"ok": True, "status": "SCHEDULED", "expected_revision": expected_revision}


def _pull(
    head: str,
    *,
    draft: bool = False,
    mergeable: bool = True,
    base: str = "main",
    state: str = "open",
    head_ref: str = "sovereign/change",
    head_repo: str = "OuroborosCollective/Sovereign-Studio-ato",
    title: str = "Test PR",
    body: str = "Test body",
    merged_at: str | None = None,
) -> dict[str, Any]:
    return {
        "number": 7,
        "node_id": "PR_node_7",
        "title": title,
        "body": body,
        "state": state,
        "draft": draft,
        "mergeable": mergeable,
        "mergeable_state": "clean",
        "merged_at": merged_at,
        "head": {"sha": head, "ref": head_ref, "repo": {"full_name": head_repo}},
        "base": {"ref": base},
        "html_url": "https://github.com/example/repo/pull/7",
    }


def _green_checks() -> tuple[FakeResponse, FakeResponse]:
    return (
        FakeResponse(200, {"check_runs": [{"name": "tests", "status": "completed", "conclusion": "success"}]}),
        FakeResponse(200, {"state": "success", "statuses": []}),
    )


def _android_pending_checks(extra_pending: str = "") -> tuple[FakeResponse, FakeResponse]:
    check_runs = [
        {"name": "Agent Runtime Tests", "status": "completed", "conclusion": "success"},
        {"name": "Android Build Verification", "status": "in_progress", "conclusion": None},
        {"name": "Android standard validation", "status": "in_progress", "conclusion": None},
    ]
    if extra_pending:
        check_runs.append({"name": extra_pending, "status": "queued", "conclusion": None})
    return FakeResponse(200, {"check_runs": check_runs}), FakeResponse(200, {"state": "success", "statuses": []})


def _runtime(monkeypatch, routes):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("SOVEREIGN_MCP_REPOSITORY", "OuroborosCollective/Sovereign-Studio-ato")
    monkeypatch.setattr(GitHubAdminRuntime, "_governance_mode", staticmethod(lambda: "enforced"))
    update = FakeSelfUpdate()
    session = FakeSession(routes)
    return GitHubAdminRuntime(update, session=session), update, session


def test_github_admin_uses_ephemeral_installation_auth_without_persistent_token(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("SOVEREIGN_MCP_REPOSITORY", "OuroborosCollective/Sovereign-Studio-ato")
    monkeypatch.setenv("SOVEREIGN_MCP_GITHUB_APP_ID", "123")
    monkeypatch.setenv("SOVEREIGN_MCP_GITHUB_APP_INSTALLATION_ID", "456")
    private_key = tmp_path / "github-app.pem"
    private_key.write_text("test-key-material", encoding="utf-8")
    private_key.chmod(0o600)
    monkeypatch.setenv("SOVEREIGN_MCP_GITHUB_APP_PRIVATE_KEY_FILE", str(private_key))
    monkeypatch.setattr(GitHubAdminRuntime, "_governance_mode", staticmethod(lambda: "enforced"))
    monkeypatch.setattr(GitHubAppInstallationAuth, "_app_jwt", lambda self: "ephemeral-app-jwt")
    installation_token = "installation-token-for-test"
    session = FakeSession({
        ("POST", "/app/installations/456/access_tokens"): [
            FakeResponse(201, {"token": installation_token})
        ],
        ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7"): [
            FakeResponse(200, _pull("a" * 40))
        ],
    })
    runtime = GitHubAdminRuntime(FakeSelfUpdate(), session=session)

    pull = runtime._pull(7)

    assert pull["number"] == 7
    assert runtime.token == ""
    assert session.calls[0]["path"] == "/app/installations/456/access_tokens"
    assert session.calls[0]["json"] == {"repositories": ["Sovereign-Studio-ato"]}
    assert session.calls[1]["headers"]["Authorization"] == f"Bearer {installation_token}"
    assert not hasattr(runtime.github_auth, "token_value")


def test_github_admin_fails_closed_without_token_or_app_configuration(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("SOVEREIGN_MCP_GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("SOVEREIGN_MCP_GITHUB_APP_INSTALLATION_ID", raising=False)
    monkeypatch.delenv("SOVEREIGN_MCP_GITHUB_APP_PRIVATE_KEY_FILE", raising=False)
    monkeypatch.setenv("SOVEREIGN_MCP_REPOSITORY", "OuroborosCollective/Sovereign-Studio-ato")
    runtime = GitHubAdminRuntime(FakeSelfUpdate(), session=FakeSession({}))

    with pytest.raises(RuntimeError, match="GitHub-App-Installation-Authentisierung"):
        runtime._pull(7)


def _zip_log(name: str, text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, text)
    return buffer.getvalue()


def test_workflow_failure_evidence_uses_exact_head_artifact_content(monkeypatch) -> None:
    head = "a" * 40
    run_id = 123
    artifact_id = 456
    log = "\n".join(
        (
            "FAILED tests/test_llm_boundary_ledger.py::test_current_review_ledger_is_complete_and_fresh",
            "MISSING_CANDIDATE:llm-boundary:96acea8d186b6cf800854b8f",
            "1 failed, 531 passed, 12 skipped in 41.23s",
        )
    )
    runtime, _update, _session = _runtime(
        monkeypatch,
        {
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/actions/runs/{run_id}"): [
                FakeResponse(200, {"id": run_id, "name": "Sovereign MCP", "head_sha": head, "conclusion": "failure"})
            ],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/actions/runs/{run_id}/jobs"): [
                FakeResponse(
                    200,
                    {
                        "jobs": [
                            {
                                "id": 77,
                                "name": "Validate MCP operator",
                                "conclusion": "failure",
                                "steps": [{"name": "Run tests", "conclusion": "failure"}],
                            }
                        ]
                    },
                )
            ],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/actions/runs/{run_id}/artifacts"): [
                FakeResponse(
                    200,
                    {
                        "artifacts": [
                            {
                                "id": artifact_id,
                                "name": "mcp-pytest-123",
                                "size_in_bytes": 1200,
                                "expired": False,
                                "updated_at": "2026-08-02T02:05:48Z",
                            }
                        ]
                    },
                )
            ],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/actions/artifacts/{artifact_id}/zip"): [
                FakeResponse(200, body=_zip_log("mcp-pytest.log", log))
            ],
        },
    )

    result = runtime.workflow_failure_evidence_extract(run_id=run_id, expected_head_sha=head)

    assert result["failureFamily"] == "LLM_BOUNDARY_LEDGER_DRIFT"
    assert result["causalCandidate"] == "llm-boundary:96acea8d186b6cf800854b8f"
    assert result["failedTests"] == 1
    assert result["passedTests"] == 531
    assert result["skippedTests"] == 12
    assert result["repairSurface"] == "config/architecture/llm-tool-boundary-review-ledger.json"
    assert result["rawLogsReturned"] is False
    assert "text" not in result


def test_governance_mode_uses_explicit_broker_path_and_fails_closed(monkeypatch, tmp_path) -> None:
    mode_path = tmp_path / "sovereign-governance-mode.json"
    mode_path.write_text(
        '{"schemaVersion":"sovereign.governance-mode.v1","mode":"acceleration"}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("SOVEREIGN_MCP_GOVERNANCE_MODE_PATH", str(mode_path))

    assert GitHubAdminRuntime._governance_mode() == "acceleration"

    mode_path.unlink()
    with pytest.raises(RuntimeError, match="GOVERNANCE_MODE_PATH_INVALID"):
        GitHubAdminRuntime._governance_mode()

    monkeypatch.setenv("SOVEREIGN_MCP_GOVERNANCE_MODE_PATH", "relative/governance.json")
    with pytest.raises(RuntimeError, match="GOVERNANCE_MODE_PATH_INVALID"):
        GitHubAdminRuntime._governance_mode()


def test_acceleration_preserves_all_check_failures_as_advisory_evidence(monkeypatch) -> None:
    monkeypatch.setattr(GitHubAdminRuntime, "_governance_mode", staticmethod(lambda: "acceleration"))

    result = GitHubAdminRuntime._effective_check_state(
        {
            "ok": False,
            "has_check_evidence": False,
            "failed": ["Validate MCP operator", "Compile Check"],
            "pending": ["no_check_evidence_reported", "Type-check, tests, build"],
        }
    )

    assert result == {
        "ok": True,
        "failed": [],
        "pending": [],
        "advisory_failed": ["Validate MCP operator", "Compile Check"],
        "advisory_pending": ["no_check_evidence_reported", "Type-check, tests, build"],
    }


def test_pr_changed_paths_binds_files_to_same_head_before_and_after_read(monkeypatch) -> None:
    head = "a" * 40
    runtime, _update, _session = _runtime(
        monkeypatch,
        {
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7"): [
                FakeResponse(200, _pull(head)),
                FakeResponse(200, _pull(head)),
            ],
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7/files"): [
                FakeResponse(200, [
                    {"filename": "backend/agent_runtime/fleet_supervisor.py"},
                    {"filename": "backend/tests/test_fleet_supervisor.py"},
                ])
            ],
        },
    )

    result = runtime.pr_changed_paths(pr_number=7)

    assert result["ok"] is True
    assert result["head_sha"] == head
    assert result["paths_complete"] is True
    assert result["readback_verified"] is True
    assert result["changed_paths"] == [
        "backend/agent_runtime/fleet_supervisor.py",
        "backend/tests/test_fleet_supervisor.py",
    ]


def test_pr_changed_paths_fails_closed_when_head_moves_during_file_read(monkeypatch) -> None:
    before = "a" * 40
    after = "b" * 40
    runtime, _update, _session = _runtime(
        monkeypatch,
        {
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7"): [
                FakeResponse(200, _pull(before)),
                FakeResponse(200, _pull(after)),
            ],
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7/files"): [
                FakeResponse(200, [{"filename": "src/app.tsx"}])
            ],
        },
    )

    result = runtime.pr_changed_paths(pr_number=7)

    assert result["ok"] is False
    assert result["status"] == "PR_HEAD_CHANGED_DURING_PATH_READ"
    assert result["paths_complete"] is False
    assert result["readback_verified"] is False
    assert result["changed_paths"] == []


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

    assert result["head_ref"] == "sovereign/change"
    assert result["checks"]["ok"] is False
    assert result["checks"]["has_check_evidence"] is False
    assert "no_check_evidence_reported" in result["checks"]["pending"]


def test_pr_status_uses_latest_check_run_per_name(monkeypatch) -> None:
    head = "1" * 40
    runtime, _update, _session = _runtime(
        monkeypatch,
        {
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7"): [FakeResponse(200, _pull(head))],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/commits/{head}/check-runs"): [
                FakeResponse(
                    200,
                    {
                        "check_runs": [
                            {"id": 10, "name": "Revision Guardian", "status": "completed", "conclusion": "failure"},
                            {"id": 20, "name": "Revision Guardian", "status": "completed", "conclusion": "success"},
                        ]
                    },
                )
            ],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/commits/{head}/status"): [
                FakeResponse(200, {"state": "success", "statuses": []})
            ],
        },
    )

    result = runtime.pr_status(pr_number=7)

    assert result["checks"]["ok"] is True
    assert result["checks"]["failed"] == []
    assert result["checks"]["checks"] == [
        {"name": "Revision Guardian", "status": "completed", "conclusion": "success"}
    ]


def test_pr_status_blocks_when_latest_check_run_is_failed(monkeypatch) -> None:
    head = "2" * 40
    runtime, _update, _session = _runtime(
        monkeypatch,
        {
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7"): [FakeResponse(200, _pull(head))],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/commits/{head}/check-runs"): [
                FakeResponse(
                    200,
                    {
                        "check_runs": [
                            {"id": 10, "name": "Revision Guardian", "status": "completed", "conclusion": "success"},
                            {"id": 20, "name": "Revision Guardian", "status": "completed", "conclusion": "failure"},
                        ]
                    },
                )
            ],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/commits/{head}/status"): [
                FakeResponse(200, {"state": "failure", "statuses": []})
            ],
        },
    )

    result = runtime.pr_status(pr_number=7)

    assert result["checks"]["ok"] is False
    assert result["checks"]["failed"] == ["Revision Guardian"]
    assert result["checks"]["checks"] == [
        {"name": "Revision Guardian", "status": "completed", "conclusion": "failure"}
    ]


def test_merge_requires_exact_head_green_checks_and_defers_mcp_release_to_main_workflow(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PR_MERGE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_SELF_UPDATE", "1")
    head = "b" * 40
    main_sha = "a" * 40
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
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/git/ref/heads/main"): [
                FakeResponse(200, {"object": {"sha": main_sha}})
            ],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/compare/{main_sha}...{head}"): [
                FakeResponse(200, {"status": "ahead", "merge_base_commit": {"sha": main_sha}})
            ],
            ("PUT", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7/merge"): [
                FakeResponse(200, {"merged": True, "sha": merge_sha, "message": "merged"})
            ],
        },
    )

    result = runtime.merge_pr(
        pr_number=7,
        expected_head_sha=head,
        merge_method="squash",
        self_update_after_merge=True,
    )

    assert result["status"] == "MERGED"
    assert result["merge_commit_sha"] == merge_sha
    assert result["touches_private_mcp"] is True
    assert result["revision_relation"]["contains_current_main"] is True
    assert result["self_update"] == {
        "ok": True,
        "status": "DEFERRED_TO_MAIN_MCP_WORKFLOW",
        "expected_revision": merge_sha,
        "workflow": "sovereign-chatgpt-mcp.yml",
        "direct_self_update_requested": True,
        "direct_self_update_scheduled": False,
        "reason": "immutable_image_must_be_published_and_verified_before_install",
    }
    assert update.calls == []


def test_merge_blocks_when_head_does_not_contain_current_main(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PR_MERGE", "1")
    head = "b" * 40
    main_sha = "a" * 40
    check_runs, legacy = _green_checks()
    runtime, _update, session = _runtime(
        monkeypatch,
        {
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7"): [
                FakeResponse(200, _pull(head))
            ],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/commits/{head}/check-runs"): [check_runs],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/commits/{head}/status"): [legacy],
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7/files"): [
                FakeResponse(200, [{"filename": "backend/agent_runtime/cognitive_run_store.py"}])
            ],
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/git/ref/heads/main"): [
                FakeResponse(200, {"object": {"sha": main_sha}})
            ],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/compare/{main_sha}...{head}"): [
                FakeResponse(200, {"status": "diverged", "merge_base_commit": {"sha": "9" * 40}})
            ],
        },
    )

    result = runtime.merge_pr(pr_number=7, expected_head_sha=head)

    assert result["status"] == "BLOCKED"
    assert result["failure_family"] == "PR_HEAD_BEHIND_MAIN"
    assert result["revision_relation"]["contains_current_main"] is False
    assert not any(call["path"].endswith("/merge") for call in session.calls)


def test_merge_allows_stale_main_ancestry_only_when_governance_is_advisory(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PR_MERGE", "1")
    head = "6" * 40
    main_sha = "a" * 40
    merge_sha = "7" * 40
    checks = FakeResponse(
        200,
        {
            "check_runs": [
                {"id": 10, "name": "Release Gate", "status": "completed", "conclusion": "success"},
                {"id": 11, "name": "Agent Runtime Tests", "status": "completed", "conclusion": "success"},
                {"id": 12, "name": "continuity-ledger", "status": "completed", "conclusion": "failure"},
                {"id": 13, "name": "Revision Guardian", "status": "completed", "conclusion": "failure"},
                {"id": 14, "name": "Revision Guardian Evidence", "status": "completed", "conclusion": "failure"},
                {"id": 15, "name": "Boundary ledger drift preflight", "status": "completed", "conclusion": "failure"},
                {"id": 16, "name": "Validate MCP operator", "status": "completed", "conclusion": "failure"},
                {"id": 17, "name": "Compile Check", "status": "completed", "conclusion": "failure"},
                {"id": 18, "name": "Type-check, tests, build", "status": "in_progress", "conclusion": None},
            ]
        },
    )
    runtime, _update, _session = _runtime(
        monkeypatch,
        {
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7"): [FakeResponse(200, _pull(head))],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/commits/{head}/check-runs"): [checks],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/commits/{head}/status"): [FakeResponse(200, {"state": "failure", "statuses": []})],
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7/files"): [
                FakeResponse(200, [{"filename": "backend/agent_runtime/cognitive_run_store.py"}])
            ],
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/git/ref/heads/main"): [
                FakeResponse(200, {"object": {"sha": main_sha}})
            ],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/compare/{main_sha}...{head}"): [
                FakeResponse(200, {"status": "diverged", "merge_base_commit": {"sha": "9" * 40}})
            ],
            ("PUT", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7/merge"): [
                FakeResponse(200, {"merged": True, "sha": merge_sha, "message": "merged"})
            ],
        },
    )
    monkeypatch.setattr(GitHubAdminRuntime, "_governance_mode", staticmethod(lambda: "acceleration"))

    result = runtime.merge_pr(pr_number=7, expected_head_sha=head)

    assert result["status"] == "MERGED"
    assert result["governance_mode"] == "acceleration"
    assert result["revision_relation"]["contains_current_main"] is False
    assert result["advisory_failed_checks"] == [
        "continuity-ledger",
        "Revision Guardian",
        "Revision Guardian Evidence",
        "Boundary ledger drift preflight",
        "Validate MCP operator",
        "Compile Check",
    ]
    assert result["advisory_pending_checks"] == ["Type-check, tests, build"]


def test_merge_pr_series_orders_oldest_first_and_revalidates_after_each_main_advance(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PR_MERGE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    runtime, _update, _session = _runtime(monkeypatch, {})

    head_newer = "7" * 40
    head_older = "8" * 40
    synced_newer = "9" * 40
    main_state = {"sha": "a" * 40}
    pulls = {
        7: {
            **_pull(head_newer, head_ref="sovereign/newer"),
            "number": 7,
            "created_at": "2026-08-06T02:00:00Z",
        },
        8: {
            **_pull(head_older, head_ref="sovereign/older"),
            "number": 8,
            "created_at": "2026-08-06T01:00:00Z",
        },
    }
    merge_calls: list[tuple[int, str]] = []
    update_calls: list[int] = []

    monkeypatch.setattr(runtime, "_pull", lambda number: pulls[number])

    def relation(head_sha: str) -> dict[str, Any]:
        contains = head_sha in {head_older, synced_newer}
        return {
            "main_sha": main_state["sha"],
            "head_sha": head_sha,
            "relation": "ahead" if contains else "diverged",
            "merge_base_sha": main_state["sha"] if contains else "0" * 40,
            "contains_current_main": contains,
        }

    monkeypatch.setattr(runtime, "_main_revision_relation", relation)
    monkeypatch.setattr(runtime, "_verify_update_branch_commit", lambda **kwargs: {"ok": True})
    monkeypatch.setattr(runtime, "_changed_files", lambda number: [f"backend/pr-{number}.py"])
    monkeypatch.setattr(
        runtime,
        "_wait_for_series_checks",
        lambda **kwargs: {"ok": True, "status": "CHECKS_GREEN", "ignored_pending_checks": []},
    )

    def fake_request(method, path, **kwargs):
        if method == "PUT" and path.endswith("/pulls/7/update-branch"):
            update_calls.append(7)
            pulls[7] = {**pulls[7], "head": {**pulls[7]["head"], "sha": synced_newer}}
            return {"message": "Updating pull request branch."}
        raise AssertionError(f"unexpected request: {method} {path}")

    monkeypatch.setattr(runtime, "_request", fake_request)

    def fake_merge_pr(*, pr_number: int, expected_head_sha: str, **kwargs):
        merge_calls.append((pr_number, expected_head_sha))
        merge_sha = ("b" if pr_number == 8 else "c") * 40
        main_state["sha"] = merge_sha
        return {
            "ok": True,
            "status": "MERGED",
            "merge_commit_sha": merge_sha,
            "changed_files": [f"backend/pr-{pr_number}.py"],
        }

    monkeypatch.setattr(runtime, "merge_pr", fake_merge_pr)
    monkeypatch.setattr(runtime, "_main_head_sha", lambda: main_state["sha"])

    result = runtime.merge_pr_series(
        pull_requests=[
            {"pr_number": 7, "expected_head_sha": head_newer},
            {"pr_number": 8, "expected_head_sha": head_older},
        ],
        owner_approved=True,
        poll_seconds=2,
        wait_seconds_per_pr=30,
    )

    assert result["status"] == "PR_SERIES_MERGED"
    assert result["ordered_pr_numbers"] == [8, 7]
    assert merge_calls == [(8, head_older), (7, synced_newer)]
    assert update_calls == [7]
    assert result["final_main_sha"] == "c" * 40
    assert result["blind_merge_performed"] is False
    assert result["skipped"] == []
    assert result["all_merged"] is True
    assert result["candidate_failures_are_quarantined"] is True


def test_merge_pr_series_does_not_update_stale_branches_in_acceleration(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PR_MERGE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    runtime, _update, _session = _runtime(monkeypatch, {})
    monkeypatch.setattr(GitHubAdminRuntime, "_governance_mode", staticmethod(lambda: "acceleration"))
    head = "5" * 40
    main_state = {"sha": "a" * 40}
    pull = {
        **_pull(head, head_ref="sovereign/acceleration"),
        "number": 7,
        "created_at": "2026-08-06T01:00:00Z",
    }
    monkeypatch.setattr(runtime, "_pull", lambda number: pull)
    monkeypatch.setattr(
        runtime,
        "_main_revision_relation",
        lambda current: {
            "main_sha": main_state["sha"],
            "head_sha": current,
            "relation": "diverged",
            "merge_base_sha": "0" * 40,
            "contains_current_main": False,
        },
    )
    monkeypatch.setattr(runtime, "_changed_files", lambda number: ["backend/pr-7.py"])
    monkeypatch.setattr(
        runtime,
        "_wait_for_series_checks",
        lambda **kwargs: {"ok": True, "status": "CHECKS_GREEN", "ignored_pending_checks": []},
    )
    monkeypatch.setattr(
        runtime,
        "_request",
        lambda method, path, **kwargs: (_ for _ in ()).throw(AssertionError(f"unexpected request: {method} {path}")),
    )

    def fake_merge_pr(*, pr_number: int, expected_head_sha: str, **kwargs):
        assert expected_head_sha == head
        main_state["sha"] = "b" * 40
        return {
            "ok": True,
            "status": "MERGED",
            "merge_commit_sha": main_state["sha"],
            "changed_files": ["backend/pr-7.py"],
        }

    monkeypatch.setattr(runtime, "merge_pr", fake_merge_pr)
    monkeypatch.setattr(runtime, "_main_head_sha", lambda: main_state["sha"])

    result = runtime.merge_pr_series(
        pull_requests=[{"pr_number": 7, "expected_head_sha": head}],
        owner_approved=True,
        poll_seconds=2,
        wait_seconds_per_pr=30,
    )

    assert result["status"] == "PR_SERIES_MERGED"
    assert result["completed"][0]["synchronization"]["status"] == "CURRENT_MAIN_ANCESTRY_ADVISORY"
    assert result["completed"][0]["merged_head_sha"] == head


def test_merge_pr_series_quarantines_bad_middle_pr_and_continues(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PR_MERGE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    runtime, _update, _session = _runtime(monkeypatch, {})
    first_head = "1" * 40
    second_head = "2" * 40
    changed_second_head = "3" * 40
    third_head = "4" * 40
    calls = {7: 0, 8: 0, 9: 0}
    main_state = {"sha": "a" * 40}
    merge_calls: list[int] = []

    def fake_pull(number: int) -> dict[str, Any]:
        calls[number] += 1
        heads = {7: first_head, 8: second_head, 9: third_head}
        head = heads[number]
        if number == 8 and calls[number] > 1:
            head = changed_second_head
        return {
            **_pull(head, head_ref=f"sovereign/pr-{number}"),
            "number": number,
            "created_at": f"2026-08-06T0{number - 6}:00:00Z",
        }

    monkeypatch.setattr(runtime, "_pull", fake_pull)
    monkeypatch.setattr(
        runtime,
        "_main_revision_relation",
        lambda head: {
            "main_sha": main_state["sha"],
            "head_sha": head,
            "relation": "ahead",
            "merge_base_sha": main_state["sha"],
            "contains_current_main": True,
        },
    )
    monkeypatch.setattr(runtime, "_changed_files", lambda number: [f"backend/pr-{number}.py"])
    monkeypatch.setattr(runtime, "_wait_for_series_checks", lambda **kwargs: {"ok": True, "status": "CHECKS_GREEN"})

    def fake_merge_pr(*, pr_number: int, **kwargs):
        merge_calls.append(pr_number)
        main_state["sha"] = ("b" if pr_number == 7 else "c") * 40
        return {
            "ok": True,
            "status": "MERGED",
            "merge_commit_sha": main_state["sha"],
            "changed_files": [f"backend/pr-{pr_number}.py"],
        }

    monkeypatch.setattr(runtime, "merge_pr", fake_merge_pr)
    monkeypatch.setattr(runtime, "_main_head_sha", lambda: main_state["sha"])

    result = runtime.merge_pr_series(
        pull_requests=[
            {"pr_number": 7, "expected_head_sha": first_head},
            {"pr_number": 8, "expected_head_sha": second_head},
            {"pr_number": 9, "expected_head_sha": third_head},
        ],
        owner_approved=True,
        poll_seconds=2,
        wait_seconds_per_pr=30,
    )

    assert result["status"] == "PR_SERIES_COMPLETED_WITH_SKIPS"
    assert merge_calls == [7, 9]
    assert [item["pr_number"] for item in result["completed"]] == [7, 9]
    assert result["skipped_count"] == 1
    assert result["skipped"][0]["pr_number"] == 8
    assert result["skipped"][0]["failure_family"] == "PR_SERIES_HEAD_CHANGED_BEFORE_TURN"
    assert result["skipped"][0]["quarantined"] is True
    assert result["final_main_sha"] == "c" * 40
    assert result["already_merged_prs_are_never_rolled_back"] is True


def test_close_pr_requires_exact_head_owner_approval_and_verifies_readback(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PR_MERGE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    head = "9" * 40
    check_runs, legacy = _green_checks()
    runtime, _update, session = _runtime(
        monkeypatch,
        {
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7"): [
                FakeResponse(200, _pull(head, draft=True)),
                FakeResponse(200, _pull(head, draft=True, state="closed")),
            ],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/commits/{head}/check-runs"): [check_runs],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/commits/{head}/status"): [legacy],
            ("PATCH", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7"): [
                FakeResponse(200, _pull(head, draft=True, state="closed"))
            ],
        },
    )

    result = runtime.close_pr(
        pr_number=7,
        expected_head_sha=head,
        closure_reason="redundant",
        owner_approved=True,
    )

    assert result["status"] == "CLOSED"
    assert result["head_sha"] == head
    assert result["closure_reason"] == "redundant"
    assert result["merge_performed"] is False
    patch_call = next(call for call in session.calls if call["method"] == "PATCH")
    assert patch_call["json"] == {"state": "closed"}
    assert not any(call["path"].endswith("/merge") for call in session.calls)


def test_close_pr_blocks_without_private_owner_approval(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PR_MERGE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    runtime, _update, session = _runtime(monkeypatch, {})

    result = runtime.close_pr(
        pr_number=7,
        expected_head_sha="8" * 40,
        closure_reason="superseded",
        owner_approved=False,
    )

    assert result["status"] == "BLOCKED"
    assert "Owner-Freigabe" in result["blocker"]
    assert session.calls == []


def test_update_pr_requires_exact_head_and_verifies_readback(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PR_MERGE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    head = "7" * 40
    updated = _pull(head, title="Updated title", body="Updated body")
    runtime, _update, session = _runtime(
        monkeypatch,
        {
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7"): [
                FakeResponse(200, _pull(head)),
                FakeResponse(200, updated),
            ],
            ("PATCH", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7"): [
                FakeResponse(200, updated)
            ],
        },
    )

    result = runtime.update_pr(
        pr_number=7,
        expected_head_sha=head,
        title="Updated title",
        body="Updated body",
        owner_approved=True,
    )

    assert result["status"] == "UPDATED"
    patch_call = next(call for call in session.calls if call["method"] == "PATCH")
    assert patch_call["json"] == {"title": "Updated title", "body": "Updated body"}


def test_reopen_pr_blocks_merged_and_reopens_closed_unmerged(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PR_MERGE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    head = "6" * 40
    runtime, _update, session = _runtime(
        monkeypatch,
        {
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7"): [
                FakeResponse(200, _pull(head, state="closed")),
                FakeResponse(200, _pull(head, state="open")),
            ],
            ("PATCH", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7"): [
                FakeResponse(200, _pull(head, state="open"))
            ],
        },
    )

    result = runtime.reopen_pr(pr_number=7, expected_head_sha=head, owner_approved=True)

    assert result["status"] == "REOPENED"
    assert any(call["method"] == "PATCH" and call["json"] == {"state": "open"} for call in session.calls)


def test_delete_pr_branch_never_deletes_main_default_or_base(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PR_MERGE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    head = "5" * 40
    runtime, _update, session = _runtime(
        monkeypatch,
        {
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7"): [
                FakeResponse(200, _pull(head, state="closed", head_ref="main", base="main"))
            ],
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato"): [
                FakeResponse(200, {"default_branch": "main"})
            ],
        },
    )

    result = runtime.delete_pr_branch(pr_number=7, expected_head_sha=head, owner_approved=True)

    assert result["status"] == "BLOCKED"
    assert result["failure_family"] == "PROTECTED_BRANCH_DELETE_FORBIDDEN"
    assert not any(call["method"] == "DELETE" for call in session.calls)


def test_delete_pr_branch_requires_closed_exact_ref_and_verifies_deletion(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PR_MERGE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    head = "4" * 40
    encoded = "sovereign%2Fsafe-change"
    ref_path = f"/repos/OuroborosCollective/Sovereign-Studio-ato/git/ref/heads/{encoded}"
    delete_path = f"/repos/OuroborosCollective/Sovereign-Studio-ato/git/refs/heads/{encoded}"
    runtime, _update, session = _runtime(
        monkeypatch,
        {
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7"): [
                FakeResponse(200, _pull(head, state="closed", head_ref="sovereign/safe-change"))
            ],
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato"): [
                FakeResponse(200, {"default_branch": "main"})
            ],
            ("GET", ref_path): [
                FakeResponse(200, {"object": {"sha": head}}),
                FakeResponse(404, None),
            ],
            ("DELETE", delete_path): [FakeResponse(204, None)],
        },
    )

    result = runtime.delete_pr_branch(pr_number=7, expected_head_sha=head, owner_approved=True)

    assert result["status"] == "BRANCH_DELETED"
    assert result["branch"] == "sovereign/safe-change"
    assert result["readback_deleted"] is True
    assert any(call["method"] == "DELETE" for call in session.calls)


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


def test_owner_approved_merge_marks_draft_ready_and_ignores_only_unrelated_android_pending(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PR_MERGE", "1")
    head = "e" * 40
    main_sha = "a" * 40
    merge_sha = "f" * 40
    first_checks, first_legacy = _android_pending_checks()
    second_checks, second_legacy = _android_pending_checks()
    runtime, update, session = _runtime(
        monkeypatch,
        {
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7"): [
                FakeResponse(200, _pull(head, draft=True)),
                FakeResponse(200, _pull(head, draft=True)),
                FakeResponse(200, _pull(head, draft=False)),
            ],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/commits/{head}/check-runs"): [
                first_checks,
                second_checks,
            ],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/commits/{head}/status"): [
                first_legacy,
                second_legacy,
            ],
            ("POST", "/graphql"): [
                FakeResponse(200, {"data": {"markPullRequestReadyForReview": {"pullRequest": {"id": "PR_node_7", "isDraft": False}}}})
            ],
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7/files"): [
                FakeResponse(200, [{"filename": "backend/agent_runtime/cognitive_run_store.py"}])
            ],
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/git/ref/heads/main"): [
                FakeResponse(200, {"object": {"sha": main_sha}})
            ],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/compare/{main_sha}...{head}"): [
                FakeResponse(200, {"status": "ahead", "merge_base_commit": {"sha": main_sha}})
            ],
            ("PUT", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7/merge"): [
                FakeResponse(200, {"merged": True, "sha": merge_sha, "message": "merged"})
            ],
        },
    )

    result = runtime.merge_pr(
        pr_number=7,
        expected_head_sha=head,
        owner_approved=True,
        mark_ready_if_draft=True,
        allow_unrelated_android_pending=True,
        self_update_after_merge=False,
    )

    assert result["status"] == "MERGED"
    assert result["ready_transition"]["status"] == "READY_FOR_REVIEW"
    assert set(result["ignored_pending_checks"]) == {
        "Android Build Verification",
        "Android standard validation",
    }
    assert result["owner_approved"] is True
    assert update.calls == []
    assert any(call["path"] == "/graphql" for call in session.calls)


def test_owner_override_blocks_when_pr_touches_android_surface(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PR_MERGE", "1")
    head = "1" * 40
    checks, legacy = _android_pending_checks()
    runtime, _update, _session = _runtime(
        monkeypatch,
        {
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7"): [FakeResponse(200, _pull(head))],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/commits/{head}/check-runs"): [checks],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/commits/{head}/status"): [legacy],
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7/files"): [
                FakeResponse(200, [{"filename": "android/app/build.gradle"}])
            ],
        },
    )

    result = runtime.merge_pr(
        pr_number=7,
        expected_head_sha=head,
        owner_approved=True,
        allow_unrelated_android_pending=True,
    )

    assert result["status"] == "BLOCKED"
    assert "Android-relevanten" in result["blocker"]


def test_owner_override_blocks_non_android_pending_gate(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PR_MERGE", "1")
    head = "2" * 40
    checks, legacy = _android_pending_checks("Backend Contract Tests")
    runtime, _update, _session = _runtime(
        monkeypatch,
        {
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7"): [FakeResponse(200, _pull(head))],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/commits/{head}/check-runs"): [checks],
            ("GET", f"/repos/OuroborosCollective/Sovereign-Studio-ato/commits/{head}/status"): [legacy],
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/pulls/7/files"): [
                FakeResponse(200, [{"filename": "backend/agent_runtime/cognitive_run_store.py"}])
            ],
        },
    )

    result = runtime.merge_pr(
        pr_number=7,
        expected_head_sha=head,
        owner_approved=True,
        allow_unrelated_android_pending=True,
    )

    assert result["status"] == "BLOCKED"
    assert result["remaining_pending"] == ["Backend Contract Tests"]


def test_failed_workflow_rerun_uses_failed_jobs_endpoint(monkeypatch) -> None:
    monkeypatch.delenv("SOVEREIGN_MCP_ENABLE_WORKFLOW_CONTROL", raising=False)
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
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


def test_private_owner_mode_can_dispatch_any_safe_repository_workflow(monkeypatch) -> None:
    monkeypatch.delenv("SOVEREIGN_MCP_ENABLE_WORKFLOW_CONTROL", raising=False)
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    runtime, _update, session = _runtime(
        monkeypatch,
        {
            ("POST", "/repos/OuroborosCollective/Sovereign-Studio-ato/actions/workflows/sovereign-backend-image.yml/dispatches"): [
                FakeResponse(
                    200,
                    {
                        "workflow_run_id": 4321,
                        "run_url": "https://api.github.com/repos/OuroborosCollective/Sovereign-Studio-ato/actions/runs/4321",
                        "html_url": "https://github.com/OuroborosCollective/Sovereign-Studio-ato/actions/runs/4321",
                    },
                )
            ]
        },
    )

    result = runtime.dispatch_workflow(
        workflow="sovereign-backend-image.yml",
        ref="main",
        inputs={},
    )

    assert result["status"] == "DISPATCHED"
    assert result["run_id"] == 4321
    assert session.calls[0]["path"].endswith("/sovereign-backend-image.yml/dispatches")


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


def test_apply_main_ruleset_creates_active_fail_closed_contract_and_verifies_readback(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PR_MERGE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    repository_path = "/repos/OuroborosCollective/Sovereign-Studio-ato"
    readback = {
        "id": 42,
        "name": "Sovereign Main Revision Green Gate",
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": True,
                    "required_status_checks": [
                        {"context": "Release Gate"},
                        {"context": "Agent Runtime Tests"},
                        {"context": "continuity-ledger"},
                        {"context": "Revision Guardian"},
                    ]
                },
            },
        ],
        "_links": {"html": {"href": "https://github.com/OuroborosCollective/Sovereign-Studio-ato/rules/42"}},
    }
    runtime, _update, session = _runtime(
        monkeypatch,
        {
            ("GET", repository_path): [FakeResponse(200, {"default_branch": "main"})],
            ("GET", f"{repository_path}/rulesets"): [FakeResponse(200, [])],
            ("POST", f"{repository_path}/rulesets"): [FakeResponse(201, {"id": 42})],
            ("GET", f"{repository_path}/rulesets/42"): [FakeResponse(200, readback)],
        },
    )

    result = runtime.apply_main_ruleset(owner_approved=True)

    assert result["status"] == "RULESET_CREATED"
    assert result["readback_verified"] is True
    assert result["required_status_checks"] == [
        "Release Gate",
        "Agent Runtime Tests",
        "continuity-ledger",
        "Revision Guardian",
    ]
    post_call = next(call for call in session.calls if call["method"] == "POST")
    assert post_call["json"]["bypass_actors"] == []
    assert post_call["json"]["conditions"]["ref_name"]["include"] == ["refs/heads/main"]
    required = next(rule for rule in post_call["json"]["rules"] if rule["type"] == "required_status_checks")
    assert required["parameters"]["strict_required_status_checks_policy"] is True
    assert {item["context"] for item in required["parameters"]["required_status_checks"]} == {
        "Release Gate",
        "Agent Runtime Tests",
        "continuity-ledger",
        "Revision Guardian",
    }


def test_apply_main_ruleset_acceleration_drops_all_status_check_blockers(monkeypatch) -> None:
    monkeypatch.delenv("SOVEREIGN_MCP_ENABLE_PR_MERGE", raising=False)
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    repository_path = "/repos/OuroborosCollective/Sovereign-Studio-ato"
    readback = {
        "id": 43,
        "name": "Sovereign Main Revision Green Gate",
        "target": "branch",
        "enforcement": "disabled",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
        ],
        "_links": {"html": {"href": "https://github.com/OuroborosCollective/Sovereign-Studio-ato/rules/43"}},
    }
    runtime, _update, session = _runtime(
        monkeypatch,
        {
            ("GET", repository_path): [FakeResponse(200, {"default_branch": "main"})],
            ("GET", f"{repository_path}/rulesets"): [FakeResponse(200, [{"id": 43, "name": "Sovereign Main Revision Green Gate"}])],
            ("PUT", f"{repository_path}/rulesets/43"): [FakeResponse(200, {"id": 43})],
            ("GET", f"{repository_path}/rulesets/43"): [FakeResponse(200, readback)],
        },
    )
    monkeypatch.setattr(GitHubAdminRuntime, "_governance_mode", staticmethod(lambda: "acceleration"))

    result = runtime.apply_main_ruleset(owner_approved=True)

    assert result["status"] == "RULESET_UPDATED"
    assert result["governance_mode"] == "acceleration"
    assert result["strict_required_status_checks_policy"] is False
    assert result["required_status_checks"] == []
    assert result["enforcement"] == "disabled"
    put_call = next(call for call in session.calls if call["method"] == "PUT")
    assert not any(rule["type"] == "required_status_checks" for rule in put_call["json"]["rules"])
    assert put_call["json"]["enforcement"] == "disabled"


def test_apply_main_ruleset_blocks_without_owner_approval(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PR_MERGE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    runtime, _update, session = _runtime(monkeypatch, {})

    result = runtime.apply_main_ruleset(owner_approved=False)

    assert result["status"] == "BLOCKED"
    assert session.calls == []


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
            ("GET", "/repos/OuroborosCollective/Sovereign-Studio-ato/actions/runs/99/artifacts"): [
                FakeResponse(200, {"artifacts": [{"id": 501, "name": "failed-evidence", "size_in_bytes": 42, "expired": False, "created_at": "2026-07-13T00:00:00Z", "updated_at": "2026-07-13T00:00:01Z"}]})
            ],
        },
    )

    result = runtime.workflow_run_status(run_id=99)

    assert result["ok"] is False
    assert result["status"] == "FAIL"
    assert result["validation_complete"] is True
    assert result["passed"] is False
    assert result["conclusion"] == "failure"
    assert result["jobs"][0]["failed_steps"] == ["Compile"]
    assert result["artifacts"][0]["id"] == 501
