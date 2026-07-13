from __future__ import annotations

import io
import zipfile
from typing import Any

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
        "post",
        lambda *args, **kwargs: FakeResponse(
            201,
            payload={
                "number": 999,
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
