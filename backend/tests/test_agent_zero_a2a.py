from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.agent_zero_a2a import (  # noqa: E402
    AgentZeroA2AClient,
    AgentZeroA2AError,
    AgentZeroA2ASubmitOutcomeUnknown,
    AgentZeroA2ATaskLost,
)
from agent_runtime.agent_zero_runtime import AgentZeroRuntimeConfig  # noqa: E402


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def _config(monkeypatch, tmp_path: Path, token: str = "agent-zero-a2a-test-token-0123456789") -> AgentZeroRuntimeConfig:
    root = tmp_path / "owner"
    root.mkdir()
    key_file = root / "agent_zero_api_key.txt"
    key_file.write_text(token, encoding="utf-8")
    key_file.chmod(0o600)
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(root))
    monkeypatch.setenv("SOVEREIGN_AGENT_ZERO_API_KEY_FILE", str(key_file))
    monkeypatch.setenv("SOVEREIGN_AGENT_ZERO_BASE_URL", "https://agent-zero.example.invalid")
    return AgentZeroRuntimeConfig.from_env()


def test_submit_sets_both_auth_headers_keeps_secret_out_of_body_and_is_nonblocking(monkeypatch, tmp_path: Path):
    token = "agent-zero-a2a-test-token-0123456789"
    config = _config(monkeypatch, tmp_path, token)
    calls: list[dict] = []

    def fake_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return FakeResponse({
            "jsonrpc": "2.0",
            "id": kwargs["json"]["id"],
            "result": {"id": "task-123", "status": {"state": "submitted"}},
        })

    monkeypatch.setattr("agent_runtime.agent_zero_a2a.requests.post", fake_post)
    task = AgentZeroA2AClient(config).submit_repository_task(
        workspace_id="agent-workspace-123",
        mission="Implement the bounded repository change and leave publication to Sovereign.",
    )

    assert task.task_id == "task-123"
    assert task.state == "submitted"
    assert calls[0]["url"] == "https://agent-zero.example.invalid/a2a"
    assert calls[0]["headers"]["Authorization"] == f"Bearer {token}"
    assert calls[0]["headers"]["X-API-KEY"] == token
    assert token not in str(calls[0]["json"])
    assert calls[0]["json"]["method"] == "message/send"
    assert calls[0]["json"]["params"]["message"]["kind"] == "message"
    assert calls[0]["json"]["params"]["configuration"]["blocking"] is False
    assert calls[0]["json"]["params"]["configuration"]["acceptedOutputModes"] == ["text", "text/plain"]
    prompt = calls[0]["json"]["params"]["message"]["parts"][0]["text"]
    assert "/a0/sovereign-workspaces/agent-workspace-123/repo" in prompt
    assert "Do not clone" in prompt
    assert "Do not push to GitHub" in prompt


def test_tasks_get_validates_exact_task_identity_and_state(monkeypatch, tmp_path: Path):
    config = _config(monkeypatch, tmp_path)

    def fake_post(_url, **kwargs):
        assert kwargs["json"]["method"] == "tasks/get"
        assert kwargs["json"]["params"] == {"id": "task-expected"}
        return FakeResponse({
            "jsonrpc": "2.0",
            "id": kwargs["json"]["id"],
            "result": {"id": "task-expected", "status": {"state": "completed"}},
        })

    monkeypatch.setattr("agent_runtime.agent_zero_a2a.requests.post", fake_post)
    task = AgentZeroA2AClient(config).get_task("task-expected")

    assert task.task_id == "task-expected"
    assert task.completed is True


def test_tasks_get_rejects_mismatched_task_identity(monkeypatch, tmp_path: Path):
    config = _config(monkeypatch, tmp_path)

    def fake_post(_url, **kwargs):
        return FakeResponse({
            "jsonrpc": "2.0",
            "id": kwargs["json"]["id"],
            "result": {"id": "task-other", "status": {"state": "working"}},
        })

    monkeypatch.setattr("agent_runtime.agent_zero_a2a.requests.post", fake_post)
    with pytest.raises(AgentZeroA2AError) as error:
        AgentZeroA2AClient(config).get_task("task-expected")

    assert error.value.family == "AGENT_ZERO_A2A_TASK_ID_MISMATCH"


def test_tasks_get_404_is_task_lost(monkeypatch, tmp_path: Path):
    config = _config(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "agent_runtime.agent_zero_a2a.requests.post",
        lambda *_args, **_kwargs: FakeResponse({}, status_code=404),
    )

    with pytest.raises(AgentZeroA2ATaskLost) as error:
        AgentZeroA2AClient(config).get_task("task-lost")

    assert error.value.family == "AGENT_ZERO_A2A_TASK_LOST"


def test_submit_timeout_is_ambiguous_and_never_downgraded_to_retry(monkeypatch, tmp_path: Path):
    config = _config(monkeypatch, tmp_path)

    def fake_post(*_args, **_kwargs):
        raise requests.Timeout("unknown submit outcome")

    monkeypatch.setattr("agent_runtime.agent_zero_a2a.requests.post", fake_post)
    with pytest.raises(AgentZeroA2ASubmitOutcomeUnknown) as error:
        AgentZeroA2AClient(config).submit_repository_task(
            workspace_id="agent-workspace-123",
            mission="Implement one bounded change.",
        )

    assert error.value.family == "AGENT_ZERO_A2A_SUBMIT_OUTCOME_UNKNOWN"
    assert error.value.next_action == "DO_NOT_RESUBMIT_UNTIL_TASK_ACCEPTANCE_CAN_BE_PROVEN"


def test_invalid_task_id_is_rejected_before_transport(monkeypatch, tmp_path: Path):
    config = _config(monkeypatch, tmp_path)
    called = False

    def fake_post(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("transport must not run")

    monkeypatch.setattr("agent_runtime.agent_zero_a2a.requests.post", fake_post)
    with pytest.raises(AgentZeroA2AError) as error:
        AgentZeroA2AClient(config).get_task("task id with spaces")

    assert error.value.family == "AGENT_ZERO_A2A_TASK_ID_INVALID"
    assert called is False
