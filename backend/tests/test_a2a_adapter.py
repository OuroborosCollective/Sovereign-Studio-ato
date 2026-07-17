from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from a2a.types import Role, TaskState

from agent_runtime.a2a_adapter import (
    A2A_PROTOCOL_VERSION,
    build_sovereign_agent_card,
    message_to_dict,
    mission_from_a2a_request,
    parse_send_message,
    run_statuses_for_task_state,
    status_update_from_event,
    task_from_run,
    task_history_from_events,
)


ROOT = Path(__file__).resolve().parents[2]


def _run(status: str = "RUNNING") -> SimpleNamespace:
    return SimpleNamespace(
        run_id="run-a2a-test",
        user_id="00000000-0000-0000-0000-000000000001",
        job_id=None,
        session_key="session-a2a-test",
        a2a_context_id="context-a2a-test",
        status=status,
        source="agents-sdk",
        evidence_id="evidence-a2a-test",
        trace_id="trace-a2a-test",
        reason=f"Persisted run state is {status}.",
        next_action="WAIT_FOR_AGENT" if status == "RUNNING" else "NO_FURTHER_ACTION_REQUIRED",
        mission_summary="Inspect the persisted truth chain.",
        mission_digest="a" * 64,
        max_active_specialists=4,
        max_iterations=12,
        iteration_count=1,
        lease_active=False,
        resume_task_id=None,
        updated_at="2026-07-17T18:00:00Z",
    )


def test_parse_a2a_message_maps_only_transport_fields_to_existing_run_contract() -> None:
    request_message = parse_send_message({
        "message": {
            "messageId": "message-a2a-test",
            "contextId": "context-a2a-test",
            "role": "ROLE_USER",
            "parts": [{"text": "Prüfe die echte Runtime-Evidence.", "mediaType": "text/plain"}],
            "metadata": {"evidence": "persisted evidence", "model": "sovereign-fast"},
        }
    })

    assert request_message.message.role == Role.ROLE_USER
    mission, evidence, model = mission_from_a2a_request(request_message)
    assert mission == "Prüfe die echte Runtime-Evidence."
    assert evidence == "persisted evidence"
    assert model == "sovereign-fast"


def test_agent_card_advertises_a2a_1_0_http_json_without_push_notifications() -> None:
    card = build_sovereign_agent_card(
        base_url="https://studio.example",
        manifest={
            "agents": [
                {
                    "role": "judge",
                    "name": "The Judge",
                    "responsibility": "Reject unsupported claims.",
                }
            ]
        },
    )
    payload = message_to_dict(card)

    assert payload["supportedInterfaces"] == [{
        "url": "https://studio.example/a2a/v1",
        "protocolBinding": "HTTP+JSON",
        "protocolVersion": A2A_PROTOCOL_VERSION,
    }]
    assert payload["capabilities"]["streaming"] is True
    assert payload["capabilities"].get("pushNotifications", False) is False
    assert payload["securitySchemes"]["bearerAuth"]["httpAuthSecurityScheme"]["scheme"] == "Bearer"
    assert payload["securitySchemes"]["bearerAuth"]["httpAuthSecurityScheme"]["bearerFormat"] == "JWT"
    assert any(skill["id"] == "sovereign-judge" for skill in payload["skills"]) 


def test_persisted_run_status_is_the_only_a2a_task_state_authority() -> None:
    assert task_from_run(_run("RECEIVED")).status.state == TaskState.TASK_STATE_SUBMITTED
    assert task_from_run(_run("RUNNING")).status.state == TaskState.TASK_STATE_WORKING
    assert task_from_run(_run("BLOCKED")).status.state == TaskState.TASK_STATE_INPUT_REQUIRED
    assert task_from_run(_run("FAILED_FINAL")).status.state == TaskState.TASK_STATE_FAILED
    assert task_from_run(_run("COMPLETED")).status.state == TaskState.TASK_STATE_COMPLETED


def test_worker_completed_event_does_not_complete_a_still_running_task() -> None:
    event = {
        "event_id": "event-worker-completed",
        "run_id": "run-a2a-test",
        "agent_id": "business_core",
        "type": "agent_completed",
        "status": "COMPLETED",
        "source": "agents-sdk",
        "summary": "Worker completed one bounded pass.",
        "evidence_id": "evidence-worker-completed",
        "trace_id": "trace-a2a-test",
        "created_at": "2026-07-17T18:00:00Z",
        "next_action": "WAIT_FOR_PARALLEL_WORKER_PASS",
    }

    update = status_update_from_event(
        event,
        context_id="context-a2a-test",
        run_status="RUNNING",
    )
    payload = message_to_dict(update)

    assert update.status.state == TaskState.TASK_STATE_WORKING
    assert payload["metadata"]["sovereignStatus"] == "RUNNING"
    assert payload["metadata"]["agentEventStatus"] == "COMPLETED"


def test_a2a_status_message_ids_are_deterministic() -> None:
    first = task_from_run(_run("RUNNING"))
    second = task_from_run(_run("RUNNING"))
    assert first.status.message.message_id == second.status.message.message_id


def test_task_timestamps_and_history_come_only_from_persisted_evidence() -> None:
    run = _run("RUNNING")
    events = [{
        "event_id": "event-history",
        "run_id": run.run_id,
        "agent_id": "dispatcher",
        "type": "agent_started",
        "status": "RUNNING",
        "source": "agents-sdk",
        "summary": "Dispatcher started from persisted evidence.",
        "evidence_id": "evidence-history",
        "trace_id": run.trace_id,
        "created_at": "2026-07-17T18:00:01Z",
        "next_action": "WAIT_FOR_DISPATCH_PLAN",
    }]
    history = task_history_from_events(
        events,
        context_id=run.a2a_context_id,
        run_status=run.status,
        limit=1,
    )
    payload = message_to_dict(task_from_run(run, history=history))

    assert payload["status"]["timestamp"] == "2026-07-17T18:00:00Z"
    assert payload["history"][0]["parts"][0]["text"]

    run.updated_at = "not-a-timestamp"
    malformed = message_to_dict(task_from_run(run))
    assert "timestamp" not in malformed["status"]


def test_a2a_status_filters_map_to_existing_truth_chain_states() -> None:
    assert "RUNNING" in run_statuses_for_task_state("TASK_STATE_WORKING")
    assert "COMPLETED" in run_statuses_for_task_state("TASK_STATE_COMPLETED")
    assert run_statuses_for_task_state("TASK_STATE_CANCELED") == ()


def test_backend_and_packaged_runtime_a2a_files_remain_identical() -> None:
    for relative in ("a2a_adapter.py", "a2a_routes.py"):
        backend = (ROOT / "backend" / "agent_runtime" / relative).read_text("utf-8")
        packaged = (
            ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / relative
        ).read_text("utf-8")
        assert backend == packaged
