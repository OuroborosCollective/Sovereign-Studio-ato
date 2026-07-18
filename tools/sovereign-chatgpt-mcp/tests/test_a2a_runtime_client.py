from __future__ import annotations

import json
from typing import Any

import pytest

from a2a_runtime_client import A2ARuntimeClient


RUN_ID = "run-11111111111111111111111111111111"
CONTEXT_ID = "context-canary-fixed"


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        lines: list[str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self._lines = lines or []

    def json(self) -> dict[str, Any]:
        return self._payload

    def iter_lines(self, decode_unicode: bool = False):
        del decode_unicode
        return iter(self._lines)


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def request(self, method, url, headers=None, json=None, timeout=None, stream=False):
        self.calls.append({
            "method": method,
            "url": url,
            "headers": headers,
            "json": json,
            "timeout": timeout,
            "stream": stream,
        })
        if not self.responses:
            raise AssertionError("Unexpected request")
        return self.responses.pop(0)


def _task(state: str) -> dict[str, Any]:
    return {
        "task": {
            "id": RUN_ID,
            "contextId": CONTEXT_ID,
            "status": {"state": state},
        }
    }


def _controller(status: str, iteration: int, *, resumed: bool = False) -> dict[str, Any]:
    events = [{"type": "run_received", "run_id": RUN_ID}]
    if resumed:
        events.append({"type": "run_resumed", "run_id": RUN_ID})
    return {
        "ok": True,
        "run": {
            "run_id": RUN_ID,
            "status": status,
            "iteration_count": iteration,
            "context_snapshot": {"a2aContextId": CONTEXT_ID},
        },
        "events": events,
        "tasks": [],
        "failures": [],
        "approvals": [],
    }


def test_live_canary_correlates_start_stream_task_controller_and_resume(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "bridge-key")
    monkeypatch.setenv("SOVEREIGN_BACKEND_INTERNAL_URL", "http://backend:8787")
    monkeypatch.setattr("a2a_runtime_client.uuid.uuid4", lambda: type("U", (), {"hex": "fixed"})())
    blocked_line = "data: " + json.dumps(_task("TASK_STATE_INPUT_REQUIRED"))
    completed_line = "data: " + json.dumps(_task("TASK_STATE_COMPLETED"))
    session = FakeSession([
        FakeResponse(200, {
            "supportedInterfaces": [{"protocolVersion": "1.0", "url": "https://example/a2a/v1"}],
            "capabilities": {"streaming": True},
        }),
        FakeResponse(200, _task("TASK_STATE_SUBMITTED"), headers={"A2A-Version": "1.0"}),
        FakeResponse(401, {"error": "session required"}),
        FakeResponse(200, {}, headers={"A2A-Version": "1.0"}, lines=[blocked_line]),
        FakeResponse(200, _task("TASK_STATE_INPUT_REQUIRED"), headers={"A2A-Version": "1.0"}),
        FakeResponse(200, _controller("BLOCKED", 1)),
        FakeResponse(200, _task("TASK_STATE_WORKING"), headers={"A2A-Version": "1.0"}),
        FakeResponse(200, {}, headers={"A2A-Version": "1.0"}, lines=[completed_line]),
        FakeResponse(200, _task("TASK_STATE_COMPLETED"), headers={"A2A-Version": "1.0"}),
        FakeResponse(200, _controller("COMPLETED", 2, resumed=True)),
    ])
    client = A2ARuntimeClient(session=session)

    result = client.live_canary("a" * 40)

    assert result["ok"] is True
    assert result["runId"] == RUN_ID
    assert result["samePersistedRunVerified"] is True
    assert result["ownerScopeVerified"] is True
    assert result["resumeAttempted"] is True
    assert result["resumeVerified"] is True
    assert result["finalControllerStatus"] == "COMPLETED"
    assert result["protectedValuesReturned"] is False
    assert session.calls[2]["headers"].get("X-Sovereign-Owner-Request-Key") is None
    assert session.calls[6]["json"]["message"]["taskId"] == RUN_ID


def test_live_canary_rejects_invalid_revision_before_network(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "bridge-key")
    session = FakeSession([])
    client = A2ARuntimeClient(session=session)

    with pytest.raises(ValueError, match="full commit SHA"):
        client.live_canary("main")
    assert session.calls == []
