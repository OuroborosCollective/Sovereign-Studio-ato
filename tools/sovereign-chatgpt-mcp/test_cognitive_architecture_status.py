from pathlib import Path
import sys

MCP_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(MCP_ROOT))

import server


class FakeControllerRuntime:
    def list_runs(self, limit: int = 20):
        assert limit == 5
        return {
            "runs": [
                {
                    "run_id": "run-0123456789abcdef0123456789abcdef",
                    "status": "RUNNING",
                    "source": "agents-sdk",
                    "iteration_count": 2,
                    "max_iterations": 12,
                    "lease_active": True,
                    "next_action": "WAIT_FOR_AGENT",
                    "reason": "evidence-backed run",
                    "mission_summary": "m" * 800,
                    "updated_at": "2026-07-15T18:55:37Z",
                }
            ]
        }

    def run_status(self, run_id: str):
        assert run_id == "run-0123456789abcdef0123456789abcdef"
        return {
            "run": {
                "run_id": run_id,
                "status": "RUNNING",
                "source": "agents-sdk",
                "iteration_count": 2,
                "max_iterations": 12,
                "next_action": "WAIT_FOR_AGENT",
                "mission_summary": "bounded mission",
            },
            "tasks": [
                {
                    "task_id": "task-1",
                    "agent_id": "data_storage",
                    "status": "RUNNING",
                    "summary": "Inspecting persisted database evidence.",
                }
            ],
            "events": [
                {
                    "agent_id": "dispatcher",
                    "type": "run_state_changed",
                    "status": "RUNNING",
                    "summary": "Dispatcher created the persisted work plan.",
                    "next_action": "WAIT_FOR_AGENT",
                }
            ],
            "failures": [],
            "approvals": [],
        }


class FailingControllerRuntime:
    def list_runs(self, limit: int = 20):
        raise TimeoutError("raw backend error must not escape")


def test_controller_run_evidence_is_bounded_and_structured(monkeypatch) -> None:
    monkeypatch.setattr(server, "controller_runtime", FakeControllerRuntime())

    evidence = server._controller_run_evidence(True)

    assert evidence["ok"] is True
    assert evidence["status"] == "CONTROLLER_EVIDENCE_READY"
    assert evidence["runs"][0]["runId"] == "run-0123456789abcdef0123456789abcdef"
    assert len(evidence["runs"][0]["missionSummary"]) == 420
    assert evidence["latestRun"]["tasks"][0]["agentId"] == "data_storage"
    assert evidence["latestRun"]["events"][0]["agentId"] == "dispatcher"


def test_controller_run_evidence_fails_closed_without_backend_or_on_error(monkeypatch) -> None:
    unconfigured = server._controller_run_evidence(False)
    assert unconfigured == {
        "ok": False,
        "status": "BACKEND_ENDPOINT_NOT_CONFIGURED",
        "runs": [],
        "latestRun": None,
    }

    monkeypatch.setattr(server, "controller_runtime", FailingControllerRuntime())
    failed = server._controller_run_evidence(True)
    assert failed["ok"] is False
    assert failed["status"] == "CONTROLLER_EVIDENCE_UNAVAILABLE"
    assert failed["error"] == "TimeoutError"
    assert "raw backend error" not in str(failed)
