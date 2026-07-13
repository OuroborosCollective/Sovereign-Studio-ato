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


def test_dependency_install_uses_bounded_phases_and_real_resolution(repo_runtime, monkeypatch) -> None:
    runtime, workspace_id, repo = repo_runtime
    (repo / "patch_capacitor.mjs").write_text("console.log('postinstall');\n", "utf-8")
    calls: list[list[str]] = []

    def fake_run(argv, *, cwd, timeout=None, env=None):
        assert cwd == repo
        calls.append(list(argv))
        return command_result(list(argv))

    monkeypatch.setattr(runtime, "_run", fake_run)

    result = runtime.install_dependencies(workspace_id)

    assert result["ok"] is True
    assert result["status"] == "INSTALLED"
    assert calls[0] == [
        "pnpm",
        "install",
        "--frozen-lockfile",
        "--ignore-scripts",
        "--child-concurrency=1",
        "--network-concurrency=4",
    ]
    assert calls[1] == ["node", "patch_capacitor.mjs"]
    assert calls[2][0:2] == ["node", "-e"]
    assert [phase["name"] for phase in result["phases"]] == [
        "lockfile_install",
        "repository_postinstall",
        "dependency_resolution",
    ]


def test_dependency_install_never_claims_success_after_signal_kill(repo_runtime, monkeypatch) -> None:
    runtime, workspace_id, repo = repo_runtime
    calls: list[list[str]] = []

    def fake_run(argv, *, cwd, timeout=None, env=None):
        assert cwd == repo
        calls.append(list(argv))
        return command_result(list(argv), ok=False, exit_code=-9)

    monkeypatch.setattr(runtime, "_run", fake_run)

    result = runtime.install_dependencies(workspace_id)

    assert result["ok"] is False
    assert result["status"] == "INSTALL_FAILED"
    assert result["phases"][0]["exit_code"] == -9
    assert len(calls) == 1


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
