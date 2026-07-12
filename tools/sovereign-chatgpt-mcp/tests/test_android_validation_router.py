from __future__ import annotations

from pathlib import Path
from typing import Any

from android_validation_router import install


class FakeAndroidRuntime:
    def __init__(self, *, local_ok: bool = True, scan_ok: bool = True) -> None:
        self.local_ok = local_ok
        self.scan_ok = scan_ok
        self.calls: list[tuple[str, str]] = []
        self.scan_calls: list[str] = []

    def run_suite(self, workspace_id: str, profile: str = "fast") -> dict[str, Any]:
        self.calls.append((workspace_id, profile))
        return {
            "ok": self.local_ok,
            "status": "PASS" if self.local_ok else "FAIL",
            "workspace_id": workspace_id,
            "profile": profile,
        }

    def scan(self, workspace_id: str) -> dict[str, Any]:
        self.scan_calls.append(workspace_id)
        return {
            "ok": self.scan_ok,
            "status": "RELEASE_READY" if self.scan_ok else "BLOCKED",
            "findings": [] if self.scan_ok else [{"family": "test_blocker"}],
        }


class FakeOperatorRuntime:
    def __init__(self, metadata: dict[str, Any], *, command_ok: bool = True) -> None:
        self.metadata = metadata
        self.command_ok = command_ok
        self.commands: list[list[str]] = []
        self.recorded: list[tuple[str, str, bool]] = []

    def _repo(self, workspace_id: str) -> Path:
        assert workspace_id == "job-test"
        return Path("/tmp/fake-android-workspace")

    def _run(self, argv: list[str], *, cwd: Path, timeout: int = 0) -> dict[str, Any]:
        assert cwd == Path("/tmp/fake-android-workspace")
        self.commands.append(list(argv))
        return {
            "ok": self.command_ok,
            "exit_code": 0 if self.command_ok else 1,
            "stdout": "ok" if self.command_ok else "",
            "stderr": "" if self.command_ok else "failed",
            "duration_ms": 1,
        }

    def _record_check(self, workspace_id: str, key: str, result: dict[str, Any]) -> None:
        self.recorded.append((workspace_id, key, bool(result.get("ok"))))

    def _read_metadata(self, workspace_id: str) -> dict[str, Any]:
        assert workspace_id == "job-test"
        return self.metadata


class FakeBroker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], int]] = []

    def call(self, action: str, arguments: dict[str, Any], timeout: int = 0) -> dict[str, Any]:
        self.calls.append((action, arguments, timeout))
        return {
            "ok": True,
            "status": "DISPATCHED",
            "workflow": arguments["workflow"],
            "ref": arguments["ref"],
        }


def test_fast_profile_remains_local(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_ANDROID_NATIVE_BUILD_MODE", "github_actions")
    android = FakeAndroidRuntime()
    operator = FakeOperatorRuntime({})
    broker = FakeBroker()
    install(android, operator, broker)

    result = android.run_suite("job-test", "fast")

    assert result["status"] == "PASS"
    assert android.calls == [("job-test", "fast")]
    assert android.scan_calls == []
    assert operator.commands == []
    assert broker.calls == []


def test_standard_profile_dispatches_published_branch_and_never_runs_local_gradle(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_ANDROID_NATIVE_BUILD_MODE", "github_actions")
    monkeypatch.setenv("SOVEREIGN_ANDROID_VALIDATION_WORKFLOW", "android-release.yml")
    android = FakeAndroidRuntime()
    broker = FakeBroker()
    metadata = {
        "branch": "sovereign/chatgpt/123-android-fix",
        "draft_pr": {
            "number": 77,
            "head_sha": "a" * 40,
            "url": "https://github.com/example/repo/pull/77",
        },
    }
    operator = FakeOperatorRuntime(metadata)
    install(android, operator, broker)

    result = android.run_suite("job-test", "standard")

    assert result["status"] == "DISPATCHED"
    assert result["execution_mode"] == "github_actions"
    assert result["ref"] == metadata["branch"]
    assert result["local_preflight"]["signing_secrets_required_locally"] is False
    assert android.calls == []
    assert android.scan_calls == ["job-test"]
    assert operator.commands == [
        ["git", "diff", "--check"],
        ["pnpm", "run", "type-check"],
        ["pnpm", "run", "build:web"],
    ]
    assert broker.calls == [
        (
            "github_workflow_dispatch",
            {
                "workflow": "android-release.yml",
                "ref": metadata["branch"],
                "inputs": {"validation_profile": "standard"},
            },
            60,
        )
    ]


def test_release_profile_blocks_before_gradle_when_workspace_branch_is_not_published(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_ANDROID_NATIVE_BUILD_MODE", "local")
    android = FakeAndroidRuntime()
    operator = FakeOperatorRuntime({"branch": "sovereign/chatgpt/unpublished"})
    broker = FakeBroker()
    install(android, operator, broker)

    result = android.run_suite("job-test", "release")

    assert result["status"] == "REMOTE_REF_REQUIRED"
    assert result["next_action"] == "repository_create_draft_pr_then_rerun_android_validation_suite"
    assert android.calls == []
    assert operator.commands == [
        ["git", "diff", "--check"],
        ["pnpm", "run", "type-check"],
        ["pnpm", "run", "build:web"],
    ]
    assert broker.calls == []


def test_native_dispatch_stops_when_secrets_free_preflight_fails(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_ANDROID_NATIVE_BUILD_MODE", "github_actions")
    android = FakeAndroidRuntime(scan_ok=False)
    operator = FakeOperatorRuntime(
        {
            "branch": "sovereign/chatgpt/123-android-fix",
            "draft_pr": {"number": 77, "head_sha": "a" * 40},
        }
    )
    broker = FakeBroker()
    install(android, operator, broker)

    result = android.run_suite("job-test", "release")

    assert result["status"] == "LOCAL_PREFLIGHT_FAILED"
    assert result["local_preflight"]["static_scan"]["status"] == "BLOCKED"
    assert android.calls == []
    assert broker.calls == []
