from __future__ import annotations

import server


BASE = "a" * 40
HEAD_ONE = "b" * 40
HEAD_TWO = "c" * 40
ARCHITECTURE_RECEIPT = "d" * 64


def test_fleet_registry_keeps_existing_status_tools_and_adds_evidence_tools() -> None:
    names = {tool.name for tool in server.mcp._tool_manager.list_tools()}

    assert "fleet_plan_read" in names
    assert "fleet_status" in names
    assert "fleet_lane_status" in names
    assert "fleet_blockers" in names
    assert "fleet_evidence_gaps" in names
    assert "repository_pr_changed_paths" in names
    assert "fleet_verdict_preview" in names


def test_fleet_plan_read_binds_exact_pr_paths_to_architecture_classification(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    captured: dict[str, object] = {}

    def broker_call(action: str, arguments: dict[str, object], timeout: int = 0):
        del timeout
        calls.append((action, dict(arguments)))
        pr_number = int(arguments.get("pr_number") or 0)
        head = HEAD_ONE if pr_number == 7 else HEAD_TWO
        if action == "github_pr_status":
            return {"ok": True, "status": "VERIFIED", "head_sha": head, "readback_verified": True}
        if action == "github_pr_changed_paths":
            paths = ["src/features/product/runtime/agent.ts"] if pr_number == 7 else ["docs/architecture/fleet.md"]
            return {
                "ok": True,
                "status": "PR_CHANGED_PATHS_VERIFIED",
                "head_sha": head,
                "changed_paths": paths,
                "changed_file_count": len(paths),
                "paths_complete": True,
                "readback_verified": True,
            }
        raise AssertionError(action)

    def preview(payload: dict[str, object]):
        captured.update(payload)
        return {"ok": True, "status": "FLEET_PLAN_PREVIEW", "plan": payload}

    monkeypatch.setattr(server.broker, "call", broker_call)
    monkeypatch.setattr(server.controller_runtime, "fleet_plan_preview", preview)

    result = server.fleet_plan_read(
        integration_id="integration-evidence-fleet",
        base_revision=BASE,
        pr_numbers=[7, 8],
        architecture_receipt_hashes=[ARCHITECTURE_RECEIPT],
        max_parallel_lanes=2,
    )

    tasks = captured["tasks"]
    assert isinstance(tasks, list)
    assert len(tasks) == 2
    by_id = {item["taskId"]: item for item in tasks}
    assert by_id["pr-7"]["changedPaths"] == ["src/features/product/runtime/agent.ts"]
    assert "frontend_runtime" in by_id["pr-7"]["architectureDomains"]
    assert by_id["pr-7"]["independenceProven"] is True
    assert by_id["pr-8"]["changedPaths"] == ["docs/architecture/fleet.md"]
    assert "documentation" in by_id["pr-8"]["architectureDomains"]
    assert by_id["pr-8"]["independenceProven"] is True
    assert len([action for action, _ in calls if action == "github_pr_changed_paths"]) == 2
    assert result["sourceReadbacks"][0]["changedPathReadbackVerified"] is True


def test_fleet_plan_read_serializes_incomplete_or_stale_path_evidence(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def broker_call(action: str, arguments: dict[str, object], timeout: int = 0):
        del arguments, timeout
        if action == "github_pr_status":
            return {"ok": True, "status": "VERIFIED", "head_sha": HEAD_ONE, "readback_verified": True}
        if action == "github_pr_changed_paths":
            return {
                "ok": True,
                "status": "PR_CHANGED_PATHS_TRUNCATED",
                "head_sha": HEAD_ONE,
                "changed_paths": ["src/app.tsx"],
                "changed_file_count": 65,
                "paths_complete": False,
                "readback_verified": True,
            }
        raise AssertionError(action)

    def preview(payload: dict[str, object]):
        captured.update(payload)
        return {"ok": True, "status": "FLEET_PLAN_PREVIEW", "plan": payload}

    monkeypatch.setattr(server.broker, "call", broker_call)
    monkeypatch.setattr(server.controller_runtime, "fleet_plan_preview", preview)

    server.fleet_plan_read(
        integration_id="integration-serialized-fleet",
        base_revision=BASE,
        pr_numbers=[7],
        architecture_receipt_hashes=[ARCHITECTURE_RECEIPT],
        max_parallel_lanes=2,
    )

    task = captured["tasks"][0]
    assert task["changedPaths"] == []
    assert task["independenceProven"] is False
    assert "CHANGED_PATHS_INCOMPLETE_OR_STALE_SERIALIZED" in task["reasonCodes"]
