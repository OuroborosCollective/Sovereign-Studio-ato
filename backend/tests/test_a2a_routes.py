from __future__ import annotations

from functools import wraps
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from typing import Any

from flask import Flask, request

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from agent_runtime import a2a_routes as routes_runtime
from agent_runtime.a2a_routes import register_a2a_routes


USER_ID = "00000000-0000-0000-0000-000000000001"
A2A_HEADERS = {"A2A-Version": "1.0"}


def _run(
    status: str = "COMPLETED",
    *,
    run_id: str = "run-a2a-route",
    updated_at: str = "2026-07-17T18:00:00Z",
) -> SimpleNamespace:
    return SimpleNamespace(
        run_id=run_id,
        user_id=USER_ID,
        job_id=None,
        session_key="session-a2a-route",
        a2a_context_id="context-a2a-route",
        status=status,
        source="agents-sdk",
        evidence_id="evidence-a2a-route",
        trace_id="trace-a2a-route",
        reason=f"Persisted route run is {status}.",
        next_action="NO_FURTHER_ACTION_REQUIRED" if status == "COMPLETED" else "WAIT_FOR_AGENT",
        mission_summary="Inspect persisted A2A route evidence.",
        mission_digest="a" * 64,
        max_active_specialists=4,
        max_iterations=12,
        iteration_count=1,
        lease_active=False,
        resume_task_id=None,
        updated_at=updated_at,
    )


def _require_session(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        request.session_user_id = USER_ID
        return handler(*args, **kwargs)
    return wrapped


def _message_payload(
    *,
    task_id: str = "",
    context_id: str = "context-a2a-route",
    text: str = "Inspect the persisted Sovereign truth chain.",
) -> dict[str, object]:
    message: dict[str, object] = {
        "messageId": "message-a2a-route",
        "contextId": context_id,
        "role": "ROLE_USER",
        "parts": [
            {
                "text": text,
                "mediaType": "text/plain",
            }
        ],
        "metadata": {"model": "sovereign-fast"},
    }
    if task_id:
        message["taskId"] = task_id
    return {"message": message}


def _app(start_run, resume_run=None) -> Flask:
    app = Flask(__name__)
    register_a2a_routes(
        app,
        require_session=_require_session,
        get_connection=lambda: None,
        start_run=start_run,
        resume_run=resume_run or (lambda **kwargs: ({"blocker": "RUN_NOT_RESUMABLE"}, 409)),
    )
    return app


def test_agent_card_is_public_and_advertises_the_rest_interface() -> None:
    app = _app(lambda **kwargs: ({}, 200))
    response = app.test_client().get("/.well-known/agent-card.json")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["supportedInterfaces"][0]["protocolVersion"] == "1.0"
    assert payload["supportedInterfaces"][0]["url"].endswith("/a2a/v1")
    assert payload["capabilities"]["streaming"] is True


def test_a2a_rest_routes_reject_missing_version_header_before_execution() -> None:
    called = False

    def start_run(**kwargs):
        nonlocal called
        called = True
        return {}, 200

    response = _app(start_run).test_client().post(
        "/a2a/v1/message:send",
        json=_message_payload(),
    )

    assert response.status_code == 400
    error = response.get_json()["error"]
    assert error["code"] == 400
    assert error["status"] == "FAILED_PRECONDITION"
    assert error["details"][0]["reason"] == "VERSION_NOT_SUPPORTED"
    assert error["details"][0]["domain"] == "a2a-protocol.org"
    assert response.headers["A2A-Version"] == "1.0"
    assert called is False


def test_message_send_uses_shared_agents_sdk_start_callback_and_persisted_task(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    persisted = _run("BLOCKED")
    monkeypatch.setattr(routes_runtime, "_read_run", lambda *args, **kwargs: persisted)

    def start_run(**kwargs):
        captured.update(kwargs)
        return {"runId": kwargs["run_id"], "status": "BLOCKED"}, 503

    response = _app(start_run).test_client().post(
        "/a2a/v1/message:send",
        headers=A2A_HEADERS,
        json=_message_payload(),
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert response.content_type.startswith("application/a2a+json")
    assert captured["user_id"] == USER_ID
    assert captured["mission"] == "Inspect the persisted Sovereign truth chain."
    assert captured["model"] == "sovereign-fast"
    assert captured["session_key"].startswith("session-")
    assert captured["a2a_context_id"] == "context-a2a-route"
    assert payload["task"]["id"] == "run-a2a-route"
    assert payload["task"]["contextId"] == "context-a2a-route"
    assert payload["task"]["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"


def test_task_subscription_streams_only_persisted_run_and_event_evidence(monkeypatch) -> None:
    initial = _run("RUNNING")
    persisted = _run("COMPLETED")
    event = {
        "event_id": "event-a2a-route",
        "run_id": persisted.run_id,
        "task_id": None,
        "agent_id": "judge",
        "type": "run_state_changed",
        "status": "COMPLETED",
        "source": "agents-sdk",
        "summary": persisted.reason,
        "evidence_id": persisted.evidence_id,
        "trace_id": persisted.trace_id,
        "created_at": "2026-07-17T18:00:00Z",
        "next_action": persisted.next_action,
    }
    runs = iter((initial, persisted))
    monkeypatch.setattr(routes_runtime, "_read_run", lambda *args, **kwargs: next(runs, persisted))
    monkeypatch.setattr(routes_runtime, "_read_events", lambda *args, **kwargs: (event,))

    response = _app(lambda **kwargs: ({}, 200)).test_client().get(
        f"/a2a/v1/tasks/{persisted.run_id}:subscribe",
        headers=A2A_HEADERS,
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert response.content_type.startswith("text/event-stream")
    assert response.headers["A2A-Version"] == "1.0"
    assert body.count("data: ") >= 2
    assert "TASK_STATE_COMPLETED" in body
    assert persisted.evidence_id in body
    assert "rawModelOutputPersisted" in body


def test_task_list_uses_filter_bound_cursor_and_omits_artifacts_by_default(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    runs = (
        _run(run_id="run-list-3", updated_at="2026-07-17T18:03:00Z"),
        _run(run_id="run-list-2", updated_at="2026-07-17T18:02:00Z"),
        _run(run_id="run-list-1", updated_at="2026-07-17T18:01:00Z"),
    )
    monkeypatch.setattr(routes_runtime, "count_agent_runs", lambda *args, **kwargs: 3)

    def list_runs(*args, **kwargs):
        captured.update(kwargs)
        return runs

    monkeypatch.setattr(routes_runtime, "list_agent_runs", list_runs)
    monkeypatch.setattr(routes_runtime, "_read_events", lambda *args, **kwargs: ())
    client = _app(lambda **kwargs: ({}, 200)).test_client()

    response = client.get(
        "/a2a/v1/tasks?contextId=context-a2a-route&status=TASK_STATE_COMPLETED&pageSize=2",
        headers=A2A_HEADERS,
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["pageSize"] == 2
    assert payload["totalSize"] == 3
    assert len(payload["tasks"]) == 2
    assert payload["nextPageToken"]
    assert all("artifacts" not in task for task in payload["tasks"])
    assert captured["context_id"] == "context-a2a-route"
    assert "COMPLETED" in captured["statuses"]
    assert captured["limit"] == 3

    mismatched = client.get(
        "/a2a/v1/tasks?contextId=other-context&status=TASK_STATE_COMPLETED&pageSize=2"
        f"&pageToken={payload['nextPageToken']}",
        headers=A2A_HEADERS,
    )
    mismatch_error = mismatched.get_json()["error"]
    assert mismatched.status_code == 400
    assert mismatch_error["details"][0]["reason"] == "INVALID_REQUEST"
    assert "active task filters" in mismatch_error["message"]


def test_follow_up_message_resumes_existing_task_without_creating_new_run(monkeypatch) -> None:
    existing = _run("BLOCKED")
    completed = _run("COMPLETED")
    completed.evidence_id = "evidence-a2a-follow-up-completed"
    runs = iter((existing, completed))
    captured: dict[str, Any] = {}
    start_called = False

    def start_run(**kwargs):
        nonlocal start_called
        start_called = True
        return {}, 200

    def resume_run(**kwargs):
        captured.update(kwargs)
        return {"resumed": True, "runId": kwargs["run_id"]}, 200

    monkeypatch.setattr(
        routes_runtime,
        "_read_run",
        lambda *args, **kwargs: next(runs, completed),
    )

    response = _app(start_run, resume_run).test_client().post(
        "/a2a/v1/message:send",
        headers=A2A_HEADERS,
        json=_message_payload(
            task_id=existing.run_id,
            text="Continue with the newly supplied runtime evidence.",
        ),
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert start_called is False
    assert captured["run_id"] == existing.run_id
    assert captured["user_id"] == USER_ID
    assert "A2A follow-up message" in captured["evidence"]
    assert "newly supplied runtime evidence" in captured["evidence"]
    assert payload["task"]["id"] == existing.run_id
    assert payload["task"]["status"]["state"] == "TASK_STATE_COMPLETED"


def test_follow_up_message_rejects_active_run_before_resume(monkeypatch) -> None:
    existing = _run("RUNNING")
    resumed = False
    monkeypatch.setattr(routes_runtime, "_read_run", lambda *args, **kwargs: existing)

    def resume_run(**kwargs):
        nonlocal resumed
        resumed = True
        return {"resumed": True}, 200

    response = _app(lambda **kwargs: ({}, 200), resume_run).test_client().post(
        "/a2a/v1/message:send",
        headers=A2A_HEADERS,
        json=_message_payload(task_id=existing.run_id),
    )
    error = response.get_json()["error"]

    assert response.status_code == 400
    assert resumed is False
    assert error["code"] == 400
    assert error["status"] == "INVALID_ARGUMENT"
    assert "cannot be resumed concurrently" in error["message"]


def test_follow_up_message_rejects_context_mismatch_before_resume(monkeypatch) -> None:
    existing = _run("BLOCKED")
    resumed = False
    monkeypatch.setattr(routes_runtime, "_read_run", lambda *args, **kwargs: existing)

    def resume_run(**kwargs):
        nonlocal resumed
        resumed = True
        return {"resumed": True}, 200

    response = _app(lambda **kwargs: ({}, 200), resume_run).test_client().post(
        "/a2a/v1/message:send",
        headers=A2A_HEADERS,
        json=_message_payload(
            task_id=existing.run_id,
            context_id="different-context",
        ),
    )
    error = response.get_json()["error"]

    assert response.status_code == 400
    assert resumed is False
    assert error["details"][0]["reason"] == "INVALID_REQUEST"
    assert "does not match" in error["message"]


def test_follow_up_resume_persistence_failure_returns_agent_unavailable(monkeypatch) -> None:
    existing = _run("BLOCKED")
    monkeypatch.setattr(routes_runtime, "_read_run", lambda *args, **kwargs: existing)

    response = _app(
        lambda **kwargs: ({}, 200),
        lambda **kwargs: ({
            "resumed": True,
            "blocker": "AGENT_RUN_FAILURE_PERSISTENCE_UNAVAILABLE",
        }, 502),
    ).test_client().post(
        "/a2a/v1/message:send",
        headers=A2A_HEADERS,
        json=_message_payload(task_id=existing.run_id),
    )
    error = response.get_json()["error"]

    assert response.status_code == 500
    assert error["code"] == 500
    assert error["status"] == "INTERNAL"
    assert error["details"][0]["reason"] == "INTERNAL_ERROR"


def test_stream_waits_through_pre_claim_blocked_state_while_resume_worker_is_active(monkeypatch) -> None:
    blocked = _run("BLOCKED")
    running = _run("RUNNING")
    running.evidence_id = "evidence-resume-claimed"
    completed = _run("COMPLETED")
    completed.evidence_id = "evidence-resume-completed"
    runs = iter((blocked, running, completed))
    worker_done = threading.Event()

    monkeypatch.setattr(
        routes_runtime,
        "_read_run",
        lambda *args, **kwargs: next(runs, completed),
    )
    monkeypatch.setattr(routes_runtime, "_read_events", lambda *args, **kwargs: ())
    monkeypatch.setattr(routes_runtime.time, "sleep", lambda _seconds: None)

    chunks = list(routes_runtime._stream_persisted_run(
        get_connection=lambda: None,
        user_id=USER_ID,
        run_id=blocked.run_id,
        initial_run=blocked,
        worker_done=worker_done,
    ))
    body = "".join(chunks)

    assert "TASK_STATE_INPUT_REQUIRED" in body
    assert "TASK_STATE_WORKING" in body
    assert "TASK_STATE_COMPLETED" in body


def test_follow_up_stream_resumes_same_task_and_streams_new_snapshot(monkeypatch) -> None:
    existing = _run("BLOCKED")
    completed = _run("COMPLETED")
    completed.evidence_id = "evidence-a2a-follow-up-stream-completed"
    runs = iter((existing, completed, completed))
    captured: dict[str, Any] = {}
    start_called = False

    def start_run(**kwargs):
        nonlocal start_called
        start_called = True
        return {}, 200

    def resume_run(**kwargs):
        captured.update(kwargs)
        return {"resumed": True, "runId": kwargs["run_id"]}, 200

    monkeypatch.setattr(
        routes_runtime,
        "_read_run",
        lambda *args, **kwargs: next(runs, completed),
    )
    monkeypatch.setattr(routes_runtime, "_read_events", lambda *args, **kwargs: ())

    response = _app(start_run, resume_run).test_client().post(
        "/a2a/v1/message:stream",
        headers=A2A_HEADERS,
        json=_message_payload(
            task_id=existing.run_id,
            text="Resume this task and stream the persisted result.",
        ),
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert start_called is False
    assert captured["run_id"] == existing.run_id
    assert "TASK_STATE_COMPLETED" in body


def test_invalid_cursor_timestamp_is_rejected_before_database_access(monkeypatch) -> None:
    database_called = False

    def count_runs(*args, **kwargs):
        nonlocal database_called
        database_called = True
        return 0

    monkeypatch.setattr(routes_runtime, "count_agent_runs", count_runs)
    filter_digest = routes_runtime._task_filter_digest(
        context_id="",
        status_name="",
        status_after="",
        history_length=0,
        include_artifacts=False,
    )
    token = routes_runtime.base64.urlsafe_b64encode(
        routes_runtime.json.dumps({
            "updatedAt": "not-a-timestamp",
            "runId": "run-valid-cursor",
            "filterDigest": filter_digest,
        }).encode("utf-8")
    ).decode("ascii").rstrip("=")

    response = _app(lambda **kwargs: ({}, 200)).test_client().get(
        f"/a2a/v1/tasks?pageToken={token}",
        headers=A2A_HEADERS,
    )
    error = response.get_json()["error"]

    assert response.status_code == 400
    assert database_called is False
    assert error["details"][0]["reason"] == "INVALID_REQUEST"
    assert "timestamp cursor" in error["message"]


def test_terminal_task_subscription_returns_protocol_error(monkeypatch) -> None:
    persisted = _run("COMPLETED")
    monkeypatch.setattr(routes_runtime, "_read_run", lambda *args, **kwargs: persisted)

    response = _app(lambda **kwargs: ({}, 200)).test_client().get(
        f"/a2a/v1/tasks/{persisted.run_id}:subscribe",
        headers=A2A_HEADERS,
    )
    error = response.get_json()["error"]

    assert response.status_code == 400
    assert error["status"] == "FAILED_PRECONDITION"
    assert error["details"][0]["reason"] == "UNSUPPORTED_OPERATION"


def test_rejected_start_returns_actual_validation_error_not_fake_persistence_failure(monkeypatch) -> None:
    monkeypatch.setattr(routes_runtime, "_read_run", lambda *args, **kwargs: None)

    response = _app(
        lambda **kwargs: ({"error": "model is not allowlisted"}, 400)
    ).test_client().post(
        "/a2a/v1/message:send",
        headers=A2A_HEADERS,
        json=_message_payload(),
    )
    error = response.get_json()["error"]

    assert response.status_code == 400
    assert error["details"][0]["reason"] == "INVALID_REQUEST"
    assert error["message"] == "model is not allowlisted"


def test_message_send_returns_persisted_task_before_worker_finishes(monkeypatch) -> None:
    received = _run("RECEIVED")
    worker_entered = threading.Event()
    release_worker = threading.Event()
    worker_finished = threading.Event()

    def start_run(**kwargs):
        worker_entered.set()
        release_worker.wait(timeout=2)
        worker_finished.set()
        return {
            "status": "COMPLETED",
            "evidenceId": "evidence-completed",
        }, 200

    monkeypatch.setattr(routes_runtime, "_read_run", lambda *args, **kwargs: received)

    response = _app(start_run).test_client().post(
        "/a2a/v1/message:send",
        headers=A2A_HEADERS,
        json=_message_payload(),
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert worker_entered.is_set()
    assert worker_finished.is_set() is False
    assert payload["task"]["status"]["state"] == "TASK_STATE_SUBMITTED"

    release_worker.set()
    assert worker_finished.wait(timeout=2)


def test_message_stream_runs_the_same_callback_and_returns_sse(monkeypatch) -> None:
    persisted = _run("COMPLETED")
    captured: dict[str, Any] = {}
    monkeypatch.setattr(routes_runtime, "_read_run", lambda *args, **kwargs: persisted)
    monkeypatch.setattr(routes_runtime, "_read_events", lambda *args, **kwargs: ())

    def start_run(**kwargs):
        captured.update(kwargs)
        return {"runId": kwargs["run_id"], "status": "COMPLETED"}, 200

    response = _app(start_run).test_client().post(
        "/a2a/v1/message:stream",
        headers=A2A_HEADERS,
        json=_message_payload(),
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert response.content_type.startswith("text/event-stream")
    assert captured["mission"] == "Inspect the persisted Sovereign truth chain."
    assert "TASK_STATE_COMPLETED" in body
