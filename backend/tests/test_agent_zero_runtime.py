from __future__ import annotations

import base64
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.agent_zero_runtime import (  # noqa: E402
    AgentZeroClient,
    AgentZeroRuntimeConfig,
    AgentZeroRuntimeError,
    _collect_tool_evidence,
    _expected_evidence_met,
    _project_ref_for_user,
)


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def _config(monkeypatch, tmp_path: Path, protected_value: str = "agent-zero-test-value-0123456789") -> AgentZeroRuntimeConfig:
    root = tmp_path / "owner"
    root.mkdir()
    key_file = root / "agent_zero_api_key.txt"
    key_file.write_text(protected_value, encoding="utf-8")
    key_file.chmod(0o600)
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(root))
    monkeypatch.setenv("SOVEREIGN_AGENT_ZERO_API_KEY_FILE", str(key_file))
    monkeypatch.setenv("SOVEREIGN_AGENT_ZERO_BASE_URL", "https://agent-zero.example.invalid")
    return AgentZeroRuntimeConfig.from_env()


def test_config_reads_only_protected_owner_value(monkeypatch, tmp_path: Path):
    protected_value = "agent-zero-test-value-0123456789"
    config = _config(monkeypatch, tmp_path, protected_value)

    assert config.read_protected_key() == protected_value
    assert protected_value not in repr(config)
    assert config.protected_key_path.name == "agent_zero_api_key.txt"


def test_config_rejects_insecure_key_permissions(monkeypatch, tmp_path: Path):
    config = _config(monkeypatch, tmp_path)
    config.protected_key_path.chmod(0o644)

    with pytest.raises(AgentZeroRuntimeError) as error:
        config.read_protected_key()

    assert error.value.family == "AGENT_ZERO_KEY_FILE_PERMISSIONS_INVALID"


def test_config_rejects_non_https_base(monkeypatch, tmp_path: Path):
    _config(monkeypatch, tmp_path)
    monkeypatch.setenv("SOVEREIGN_AGENT_ZERO_BASE_URL", "http://agent-zero.example.invalid")

    with pytest.raises(AgentZeroRuntimeError) as error:
        AgentZeroRuntimeConfig.from_env()

    assert error.value.family == "AGENT_ZERO_BASE_URL_INVALID"


def test_project_ref_is_deterministic_and_pseudonymous():
    user_id = "11111111-2222-3333-4444-555555555555"

    first = _project_ref_for_user(user_id)
    second = _project_ref_for_user(user_id)

    assert first == second
    assert first.startswith("sovereign-u-")
    assert user_id not in first


def test_browser_requires_skill_tool_browser_tool_and_real_png_readback(monkeypatch, tmp_path: Path):
    config = _config(monkeypatch, tmp_path)
    png = b"\x89PNG\r\n\x1a\n" + b"evidence"
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if url.endswith("/api/api_message"):
            return FakeResponse({"context_id": "ctx-browser-1", "response": "Browser inspection finished."})
        if url.endswith("/api/api_log_get"):
            return FakeResponse({
                "log": {
                    "items": [
                        {"tool_name": "skills_tool", "tool_result": {"skill": "browser-automation"}},
                        {"tool_name": "browser_agent", "status": "done"},
                    ]
                }
            })
        if url.endswith("/api/api_files_get"):
            requested = kwargs["json"]["paths"][0]
            return FakeResponse({requested: base64.b64encode(png).decode("ascii")})
        raise AssertionError(url)

    monkeypatch.setattr("agent_runtime.agent_zero_runtime.requests.request", fake_request)
    result = AgentZeroClient(config, user_id="owner-user").invoke(
        "playwright",
        "Inspect https://example.com and report the rendered title.",
    )

    assert result.ok is True
    assert result.expected_tool_evidence_met is True
    assert "skills_tool" in result.observed_tool_names
    assert "browser_agent" in result.observed_tool_names
    assert result.artifact_bytes == len(png)
    assert result.artifact_sha256
    assert result.context_ref.startswith("a0ctx-")
    assert "ctx-browser-1" not in result.context_ref
    assert all("X-API-KEY" in call[2]["headers"] for call in calls)
    assert all(config.read_protected_key() not in str(call[2].get("json")) for call in calls)


def test_memory_remember_requires_observed_memory_save(monkeypatch, tmp_path: Path):
    config = _config(monkeypatch, tmp_path)

    def fake_request(method, url, **kwargs):
        if url.endswith("/api/api_message"):
            return FakeResponse({"context_id": "ctx-memory-1", "response": "Stored advisory memory."})
        if url.endswith("/api/api_log_get"):
            return FakeResponse({"log": {"items": [{"tool_name": "memory_save"}]}})
        raise AssertionError(url)

    monkeypatch.setattr("agent_runtime.agent_zero_runtime.requests.request", fake_request)
    result = AgentZeroClient(config, user_id="owner-user").invoke(
        "memory_remember",
        "Remember that this project prefers evidence-first validation.",
    )

    assert result.ok is True
    assert result.observed_tool_names == ("memory_save",)
    assert result.billing_boundary == "OWNER_SCOPED_EXTERNAL_AGENT_ZERO_MODEL"
    assert result.to_dict()["authoritative"] is False
    assert result.to_dict()["generalUserAllowed"] is False


def test_sleep_remember_does_not_fake_missing_addon_evidence():
    tools, sleep_skill = _collect_tool_evidence({
        "log": {
            "items": [
                {"tool_name": "skills_tool", "status": "done"},
                {"tool_name": "memory_save", "status": "done"},
            ]
        }
    })

    assert sleep_skill is False
    assert _expected_evidence_met(
        "sleep_remember",
        tools,
        artifact_sha256=None,
        sleep_skill_evidence=sleep_skill,
    ) is False


def test_sleep_remember_accepts_only_skill_plus_memory_tool_evidence():
    tools, sleep_skill = _collect_tool_evidence({
        "log": {
            "items": [
                {
                    "tool_name": "skills_tool",
                    "tool_result": {"loaded_skill": "rem-sleep"},
                },
                {"tool_name": "memory_load", "status": "done"},
            ]
        }
    })

    assert sleep_skill is True
    assert _expected_evidence_met(
        "sleep_remember",
        tools,
        artifact_sha256=None,
        sleep_skill_evidence=sleep_skill,
    ) is True


def test_secret_shaped_instruction_is_blocked_before_agent_zero(monkeypatch, tmp_path: Path):
    config = _config(monkeypatch, tmp_path)
    client = AgentZeroClient(config, user_id="owner-user")
    secret_shaped = "pass" + "word" + "=" + "super" + "-secret-value"

    with pytest.raises(AgentZeroRuntimeError) as error:
        client.invoke("research", "Inspect the service with " + secret_shaped)

    assert error.value.family == "AGENT_ZERO_INSTRUCTION_SECRET_DETECTED"
