from __future__ import annotations

import io
import subprocess
import zipfile
from typing import Any

import pytest

import runtime as runtime_module


class FakeResponse:
    def __init__(self, status_code: int, *, payload: Any = None, body: bytes = b"") -> None:
        self.status_code = status_code
        self._payload = payload
        self._body = body

    def json(self) -> Any:
        return self._payload

    def iter_content(self, chunk_size: int = 1024 * 1024):
        for offset in range(0, len(self._body), chunk_size):
            yield self._body[offset : offset + chunk_size]


def command_result(argv: list[str], *, ok: bool = True, exit_code: int = 0) -> dict[str, Any]:
    return {
        "argv": argv,
        "exit_code": exit_code,
        "stdout": "ok" if ok else "",
        "stderr": "" if ok else "killed",
        "duration_ms": 1,
        "ok": ok,
    }


def test_dependency_install_is_delegated_without_starting_pnpm(repo_runtime, monkeypatch) -> None:
    runtime, workspace_id, repo = repo_runtime
    calls: list[list[str]] = []

    def fake_run(argv, *, cwd, timeout=None, env=None):
        calls.append(list(argv))
        raise AssertionError("local dependency process must not start")

    monkeypatch.setattr(runtime, "_run", fake_run)

    result = runtime.install_dependencies(workspace_id)

    assert result["ok"] is False
    assert result["status"] == "REMOTE_CI_REQUIRED"
    assert result["failure_family"] == "LOCAL_DEPENDENCY_INSTALL_FORBIDDEN"
    assert result["execution_mode"] == "github_actions"
    assert result["local_process_started"] is False
    assert calls == []


def test_node_checks_are_delegated_without_local_execution(repo_runtime, monkeypatch) -> None:
    runtime, workspace_id, repo = repo_runtime
    target = repo / "src/example.test.ts"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("export {};\n", "utf-8")
    calls: list[list[str]] = []

    def fake_run(argv, *, cwd, timeout=None, env=None):
        calls.append(list(argv))
        raise AssertionError("local Node check must not start")

    monkeypatch.setattr(runtime, "_run", fake_run)

    for check, check_target in (
        ("typecheck", ""),
        ("audit", ""),
        ("build_web", ""),
        ("vitest", "src/example.test.ts"),
    ):
        result = runtime.run_check(workspace_id, check, check_target)
        assert result["ok"] is False
        assert result["status"] == "REMOTE_CI_REQUIRED"
        assert result["failure_family"] == "LOCAL_NODE_EXECUTION_FORBIDDEN"
        assert result["local_process_started"] is False
    assert calls == []


def test_frontend_draft_pr_is_created_without_local_node_execution(repo_runtime, monkeypatch) -> None:
    runtime, workspace_id, repo = repo_runtime
    (repo / "src/menu.tsx").write_text("export const label = 'New';\n", "utf-8")
    original_run = runtime._run
    calls: list[list[str]] = []

    def guarded_run(argv, *, cwd, timeout=None, env=None):
        calls.append(list(argv))
        if argv[:2] == ["git", "push"]:
            return command_result(list(argv))
        assert argv[0] != "pnpm"
        return original_run(argv, cwd=cwd, timeout=timeout, env=env)

    monkeypatch.setattr(runtime, "_run", guarded_run)
    monkeypatch.setattr(
        runtime_module.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(200, payload=[]),
    )
    monkeypatch.setattr(
        runtime_module.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(
            201,
            payload={
                "number": 999,
                "draft": True,
                "html_url": "https://github.test/example/pull/999",
                "head": {"sha": "a" * 40},
            },
        ),
    )

    result = runtime.create_draft_pr(
        workspace_id,
        title="Delegate frontend validation",
        body="CI owns Node dependency resolution.",
        commit_message="Delegate frontend validation",
    )

    assert result["draft"] is True
    assert result["number"] == 999
    assert result["remote_validation"]["required"] is True
    assert result["remote_validation"]["execution_mode"] == "github_actions"
    assert result["remote_validation"]["local_dependency_install_allowed"] is False
    assert not any(call and call[0] == "pnpm" for call in calls)


def test_existing_workspace_pr_is_updated_instead_of_duplicated(repo_runtime, monkeypatch) -> None:
    runtime, workspace_id, repo = repo_runtime
    metadata = runtime._read_metadata(workspace_id)
    branch = metadata["branch"]
    (repo / "README.md").write_text("updated\n", "utf-8")
    original_run = runtime._run
    calls: list[list[str]] = []
    patches: list[dict[str, Any]] = []

    def guarded_run(argv, *, cwd, timeout=None, env=None):
        calls.append(list(argv))
        if argv[:2] == ["git", "push"]:
            return command_result(list(argv))
        return original_run(argv, cwd=cwd, timeout=timeout, env=env)

    def fake_get(*args, **kwargs):
        return FakeResponse(
            200,
            payload=[{
                "number": 901,
                "draft": True,
                "head": {"ref": branch, "sha": "b" * 40},
                "base": {"ref": "main"},
            }],
        )

    def fake_patch(*args, **kwargs):
        patches.append(kwargs["json"])
        return FakeResponse(
            200,
            payload={
                "number": 901,
                "draft": True,
                "html_url": "https://github.test/example/pull/901",
                "head": {"sha": "c" * 40},
            },
        )

    monkeypatch.setattr(runtime, "_run", guarded_run)
    monkeypatch.setattr(runtime_module.requests, "get", fake_get)
    monkeypatch.setattr(runtime_module.requests, "patch", fake_patch)

    result = runtime.create_draft_pr(
        workspace_id,
        title="Update existing PR",
        body="No duplicate PR.",
        commit_message="Update existing PR",
    )

    assert result["status"] == "DRAFT_PR_UPDATED"
    assert result["created"] is False
    assert result["number"] == 901
    assert patches == [{"title": "Update existing PR", "body": "No duplicate PR.", "state": "open"}]
    assert any(call[:2] == ["git", "push"] for call in calls)


def test_other_open_draft_blocks_before_git_mutation(repo_runtime, monkeypatch) -> None:
    runtime, workspace_id, repo = repo_runtime
    (repo / "README.md").write_text("blocked\n", "utf-8")
    original_run = runtime._run
    mutation_calls: list[list[str]] = []

    def guarded_run(argv, *, cwd, timeout=None, env=None):
        if argv[:2] in (["git", "add"], ["git", "commit"], ["git", "push"]):
            mutation_calls.append(list(argv))
        return original_run(argv, cwd=cwd, timeout=timeout, env=env)

    monkeypatch.setattr(runtime, "_run", guarded_run)
    monkeypatch.setattr(
        runtime_module.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(
            200,
            payload=[{
                "number": 900,
                "draft": True,
                "head": {"ref": "sovereign/other"},
                "base": {"ref": "main"},
            }],
        ),
    )

    try:
        runtime.create_draft_pr(
            workspace_id,
            title="Must block",
            body="Must block.",
            commit_message="Must block",
        )
    except RuntimeError as exc:
        assert "OPEN_DRAFT_PR_EXISTS" in str(exc)
    else:
        raise AssertionError("parallel Draft PR must be blocked")

    assert mutation_calls == []


def test_workspace_sync_fast_forwards_exact_pr_head_and_restores_local_changes(repo_runtime, monkeypatch) -> None:
    runtime, workspace_id, repo = repo_runtime
    metadata = runtime._read_metadata(workspace_id)
    branch = metadata["branch"]
    remote = repo.parent / "remote.git"
    writer = repo.parent / "writer"

    subprocess.run(["git", "checkout", "-b", branch], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=repo, check=True)
    subprocess.run(["git", "push", "--set-upstream", "origin", branch], cwd=repo, check=True, capture_output=True)

    subprocess.run(["git", "clone", str(remote), str(writer)], check=True, capture_output=True)
    subprocess.run(["git", "checkout", branch], cwd=writer, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Remote Test"], cwd=writer, check=True)
    subprocess.run(["git", "config", "user.email", "remote@example.invalid"], cwd=writer, check=True)
    (writer / "README.md").write_text("remote head\n", "utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=writer, check=True)
    subprocess.run(["git", "commit", "-m", "advance remote"], cwd=writer, check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", branch], cwd=writer, check=True, capture_output=True)
    remote_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=writer,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    (repo / "LOCAL.txt").write_text("preserve me\n", "utf-8")
    monkeypatch.setattr(
        runtime_module.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(
            200,
            payload={
                "number": 901,
                "state": "open",
                "head": {
                    "ref": branch,
                    "sha": remote_head,
                    "repo": {"full_name": runtime.config.repository},
                },
                "base": {"ref": "main"},
            },
        ),
    )

    result = runtime.sync_workspace_to_pr_head(
        workspace_id,
        pr_number=901,
        expected_pr_head_sha=remote_head,
    )

    actual_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert result["status"] == "WORKSPACE_SYNCED_TO_PR_HEAD"
    assert result["strategy"] == "fast_forward"
    assert result["remote_pr_head_sha"] == remote_head
    assert result["workspace_head_sha"] == remote_head
    assert actual_head == remote_head
    assert (repo / "LOCAL.txt").read_text("utf-8") == "preserve me\n"
    assert result["local_changes_restored"] is True
    assert result["force_push_used"] is False
    assert result["main_mutated"] is False
    assert result["remote_mutation_performed"] is False


def test_workspace_sync_rejects_changed_pr_head_before_git_mutation(repo_runtime, monkeypatch) -> None:
    runtime, workspace_id, _repo = repo_runtime
    metadata = runtime._read_metadata(workspace_id)
    branch = metadata["branch"]
    git_calls: list[list[str]] = []

    monkeypatch.setattr(
        runtime_module.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(
            200,
            payload={
                "number": 901,
                "state": "open",
                "head": {
                    "ref": branch,
                    "sha": "b" * 40,
                    "repo": {"full_name": runtime.config.repository},
                },
                "base": {"ref": "main"},
            },
        ),
    )
    monkeypatch.setattr(
        runtime,
        "_run",
        lambda argv, **kwargs: git_calls.append(list(argv)) or command_result(list(argv)),
    )

    with pytest.raises(RuntimeError, match="PR_HEAD_CHANGED"):
        runtime.sync_workspace_to_pr_head(
            workspace_id,
            pr_number=901,
            expected_pr_head_sha="a" * 40,
        )

    assert git_calls == []


def test_workspace_sync_never_accepts_main_or_base_branch(repo_runtime, monkeypatch) -> None:
    runtime, workspace_id, _repo = repo_runtime
    metadata = runtime._read_metadata(workspace_id)
    metadata["branch"] = "main"
    runtime._write_metadata(workspace_id, metadata)
    monkeypatch.setattr(
        runtime_module.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network call must not start")),
    )

    with pytest.raises(RuntimeError, match="PROTECTED_BRANCH_SYNC_FORBIDDEN"):
        runtime.sync_workspace_to_pr_head(
            workspace_id,
            pr_number=901,
            expected_pr_head_sha="a" * 40,
        )


def test_workflow_artifact_import_binds_artifact_to_confirmed_run(repo_runtime, monkeypatch) -> None:
    runtime, workspace_id, repo = repo_runtime
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("release/SovereignStudio-release.apk", b"real-artifact-bytes")
    archive_bytes = archive_buffer.getvalue()
    calls: list[str] = []

    def fake_get(url, **kwargs):
        calls.append(url)
        if url.endswith("/actions/artifacts/501"):
            return FakeResponse(
                200,
                payload={
                    "id": 501,
                    "name": "SovereignStudio-release-apk-v3.0.0",
                    "expired": False,
                    "workflow_run": {"id": 99},
                    "archive_download_url": "https://api.github.test/artifacts/501/zip",
                },
            )
        if url == "https://api.github.test/artifacts/501/zip":
            return FakeResponse(200, body=archive_bytes)
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(runtime_module.requests, "get", fake_get)

    result = runtime.import_workflow_artifact(workspace_id, 99, 501)

    assert result["ok"] is True
    assert result["status"] == "IMPORTED"
    assert result["run_id"] == 99
    assert result["artifact_id"] == 501
    assert len(result["inspectable_artifacts"]) == 1
    imported_path = repo / result["inspectable_artifacts"][0]["path"]
    assert imported_path.read_bytes() == b"real-artifact-bytes"
    assert ".sovereign-artifacts" not in runtime.git_diff(workspace_id)["status"]
    assert calls == [
        "https://api.github.com/repos/OuroborosCollective/Sovereign-Studio-ato/actions/artifacts/501",
        "https://api.github.test/artifacts/501/zip",
    ]
