from __future__ import annotations

from typing import Any

from android_validation_router import install


class FakeAndroidRuntime:
    def __init__(self, *, fast_ok: bool = True) -> None:
        self.fast_ok = fast_ok
        self.calls: list[tuple[str, str]] = []

    def run_suite(self, workspace_id: str, profile: str = "fast") -> dict[str, Any]:
        self.calls.append((workspace_id, profile))
        return {
            "ok": self.fast_ok,
            "status": "PASS" if self.fast_ok else "FAIL",
            "workspace_id": workspace_id,
            "profile": profile,
        }


class FakeOperatorRuntime:
    def __init__(self, metadata: dict[str, Any]) -> None:
        self.metadata = metadata

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
    broker = FakeBroker()
    install(android, FakeOperatorRuntime({}), broker)

    result = android.run_suite("job-test", "fast")

    assert result["status"] == "PASS"
    assert android.calls == [("job-test", "fast")]
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
    install(android, FakeOperatorRuntime(metadata), broker)

    result = android.run_suite("job-test", "standard")

    assert result["status"] == "DISPATCHED"
    assert result["execution_mode"] == "github_actions"
    assert result["ref"] == metadata["branch"]
    assert android.calls == [("job-test", "fast")]
    assert broker.calls == [
        (
            "github_workflow_dispatch",
            {
                "workflow": "android-release.yml",
                "ref": metadata["branch"],
                "inputs": {},
            },
            60,
        )
    ]


def test_release_profile_blocks_before_gradle_when_workspace_branch_is_not_published(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_ANDROID_NATIVE_BUILD_MODE", "github_actions")
    android = FakeAndroidRuntime()
    broker = FakeBroker()
    install(
        android,
        FakeOperatorRuntime({"branch": "sovereign/chatgpt/unpublished"}),
        broker,
    )

    result = android.run_suite("job-test", "release")

    assert result["status"] == "REMOTE_REF_REQUIRED"
    assert result["next_action"] == "repository_create_draft_pr_then_rerun_android_validation_suite"
    assert android.calls == [("job-test", "fast")]
    assert broker.calls == []


def test_native_dispatch_stops_when_fast_preflight_fails(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_ANDROID_NATIVE_BUILD_MODE", "github_actions")
    android = FakeAndroidRuntime(fast_ok=False)
    broker = FakeBroker()
    install(
        android,
        FakeOperatorRuntime(
            {
                "branch": "sovereign/chatgpt/123-android-fix",
                "draft_pr": {"number": 77, "head_sha": "a" * 40},
            }
        ),
        broker,
    )

    result = android.run_suite("job-test", "release")

    assert result["status"] == "LOCAL_PREFLIGHT_FAILED"
    assert android.calls == [("job-test", "fast")]
    assert broker.calls == []
