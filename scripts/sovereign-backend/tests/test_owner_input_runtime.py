from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import types

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

flask_stub = types.ModuleType("flask")
flask_stub.jsonify = lambda *args, **kwargs: {"args": args, **kwargs}
flask_stub.make_response = lambda value: value
flask_stub.request = types.SimpleNamespace(headers={}, remote_addr=None)
sys.modules.setdefault("flask", flask_stub)

import owner_input_runtime as runtime
from agent_runtime import cognitive_swarm_agents as swarm_runtime


def _install_agents_sdk_routing_stubs(monkeypatch) -> None:
    agents_module = types.ModuleType("agents")
    models_module = types.ModuleType("agents.models")
    provider_module = types.ModuleType("agents.models.openai_provider")
    model_settings_module = types.ModuleType("agents.model_settings")
    run_config_module = types.ModuleType("agents.run_config")

    class OpenAIProvider:
        def __init__(self, *, api_key, base_url, use_responses):
            self.api_key = api_key
            self.base_url = base_url
            self.use_responses = use_responses

    class RunConfig:
        def __init__(
            self,
            *,
            model,
            model_provider,
            model_settings,
            tracing_disabled,
            trace_include_sensitive_data,
        ):
            self.model = model
            self.model_provider = model_provider
            self.model_settings = model_settings
            self.tracing_disabled = tracing_disabled
            self.trace_include_sensitive_data = trace_include_sensitive_data

    class ModelSettings:
        def __init__(self, *, max_tokens, include_usage):
            self.max_tokens = max_tokens
            self.include_usage = include_usage

    provider_module.OpenAIProvider = OpenAIProvider
    model_settings_module.ModelSettings = ModelSettings
    run_config_module.RunConfig = RunConfig
    monkeypatch.setitem(sys.modules, "agents", agents_module)
    monkeypatch.setitem(sys.modules, "agents.models", models_module)
    monkeypatch.setitem(sys.modules, "agents.models.openai_provider", provider_module)
    monkeypatch.setitem(sys.modules, "agents.model_settings", model_settings_module)
    monkeypatch.setitem(sys.modules, "agents.run_config", run_config_module)


def test_allowlisted_target_is_derived_from_configured_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(tmp_path))

    targets = runtime._target_map()

    assert set(targets) == {
        "openai_api_key",
        "litellm_provider_key",
        "revolver_provider_key",
        "proven_learning_confirmation",
    }

    openai_target = targets["openai_api_key"]
    assert openai_target["path"] == (tmp_path / "openai_api_key.txt").resolve()
    assert openai_target["label"] == "OpenAI Provider für LiteLLM"
    assert openai_target["fieldLabel"] == "OpenAI API-Key"
    assert openai_target["maxBytes"] == 8192

    provider_target = targets["litellm_provider_key"]
    assert provider_target["path"] == (tmp_path / "litellm_provider_key.txt").resolve()
    assert provider_target["label"] == "Einmaliger Fremdprovider-Zugang für LiteLLM"
    assert provider_target["fieldLabel"] == "Provider API-Key"
    assert provider_target["maxBytes"] == 8192

    revolver_target = targets["revolver_provider_key"]
    assert revolver_target["path"] == (tmp_path / "revolver_provider_key.txt").resolve()
    assert revolver_target["label"] == "Einmaliger Free-Revolver Provider-Zugang"
    assert revolver_target["fieldLabel"] == "Free-Provider API-Key"
    assert revolver_target["maxBytes"] == 8192

    learning_target = targets["proven_learning_confirmation"]
    assert learning_target["path"] == (tmp_path / "proven_learning_confirmation.txt").resolve()
    assert learning_target["fieldLabel"] == "Exakten 64-stelligen Plan-Hash eingeben"
    assert learning_target["maxBytes"] == 80
    assert learning_target["kind"] == "approval_receipt"


def test_atomic_write_is_bounded_mode_0600_and_leaves_no_temporary_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(tmp_path))
    target = runtime._target_map()["openai_api_key"]

    runtime._atomic_write(target, "one-time-provider-value")

    path = tmp_path / "openai_api_key.txt"
    assert path.read_text("utf-8") == "one-time-provider-value"
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert list(tmp_path.glob(".*.tmp")) == []


def test_atomic_write_rejects_empty_and_oversized_values(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(tmp_path))
    target = runtime._target_map()["openai_api_key"]

    with pytest.raises(ValueError, match="fehlt"):
        runtime._atomic_write(target, "")
    with pytest.raises(ValueError, match="überschreitet"):
        runtime._atomic_write({**target, "maxBytes": 3}, "four")


def test_agents_sdk_loads_only_internal_litellm_service_key(monkeypatch, tmp_path: Path) -> None:
    _install_agents_sdk_routing_stubs(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "direct-provider-key-must-be-replaced")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("LITELLM_BASE_URL", "http://litellm:4000")
    path = tmp_path / "litellm_master_key.txt"
    path.write_text("internal-litellm-service-key", "utf-8")
    path.chmod(0o600)

    assert swarm_runtime.ensure_openai_runtime_key() is True, (
        swarm_runtime._AGENTS_SDK_VERSION,
        swarm_runtime._RUN_CONFIG_ERROR,
    )
    assert "OPENAI_API_KEY" not in os.environ
    assert "OPENAI_BASE_URL" not in os.environ
    assert type(swarm_runtime._RUN_CONFIG).__name__ == "RunConfig"
    assert swarm_runtime._RUN_CONFIG.model == "sovereign-fast"
    assert type(swarm_runtime._RUN_CONFIG.model_provider).__name__ == "OpenAIProvider"
    assert type(swarm_runtime._RUN_CONFIG.model_settings).__name__ == "ModelSettings"
    assert swarm_runtime._RUN_CONFIG.model_settings.max_tokens == 2048
    assert swarm_runtime._RUN_CONFIG.model_settings.include_usage is True
    assert swarm_runtime._RUN_CONFIG.tracing_disabled is True
    assert swarm_runtime._RUN_CONFIG.trace_include_sensitive_data is False


def test_agents_sdk_runner_receives_explicit_litellm_run_config(monkeypatch, tmp_path: Path) -> None:
    _install_agents_sdk_routing_stubs(monkeypatch)
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("LITELLM_BASE_URL", "http://litellm:4000")
    path = tmp_path / "litellm_master_key.txt"
    path.write_text("internal-litellm-service-key", "utf-8")
    path.chmod(0o600)
    assert swarm_runtime.ensure_openai_runtime_key() is True, (
        swarm_runtime._AGENTS_SDK_VERSION,
        swarm_runtime._RUN_CONFIG_ERROR,
    )

    captured: dict[str, object] = {}

    class CapturingRunner:
        @staticmethod
        async def run(agent, prompt, *, run_config, max_turns):
            captured["agent"] = agent
            captured["prompt"] = prompt
            captured["run_config"] = run_config
            captured["max_turns"] = max_turns
            return "ok"

    result = asyncio.run(
        swarm_runtime._run_stage(CapturingRunner, "agent", "prompt", stage="test")
    )

    assert result == "ok"
    assert captured == {
        "agent": "agent",
        "prompt": "prompt",
        "run_config": swarm_runtime._RUN_CONFIG,
        "max_turns": 1,
    }


def test_agents_sdk_litellm_key_rejects_symlink_escape(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "direct-provider-key-must-be-removed")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("LITELLM_BASE_URL", "http://litellm:4000")
    outside = tmp_path.parent / f"{tmp_path.name}-outside-litellm-value.txt"
    outside.write_text("internal-litellm-service-key", "utf-8")
    (tmp_path / "litellm_master_key.txt").symlink_to(outside)

    assert swarm_runtime.ensure_openai_runtime_key() is False
    assert "OPENAI_API_KEY" not in os.environ
    assert "OPENAI_BASE_URL" not in os.environ


def test_agents_sdk_litellm_key_rejects_group_or_world_readable_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("LITELLM_BASE_URL", "http://litellm:4000")
    path = tmp_path / "litellm_master_key.txt"
    path.write_text("internal-litellm-service-key", "utf-8")
    path.chmod(0o644)

    assert swarm_runtime.ensure_openai_runtime_key() is False
    assert "OPENAI_API_KEY" not in os.environ
    assert "OPENAI_BASE_URL" not in os.environ


def test_agents_sdk_rejects_public_or_direct_provider_base_url(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "direct-provider-key-must-be-removed")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("LITELLM_BASE_URL", "https://api.openai.com")
    path = tmp_path / "litellm_master_key.txt"
    path.write_text("internal-litellm-service-key", "utf-8")
    path.chmod(0o600)

    assert swarm_runtime.ensure_openai_runtime_key() is False
    assert "OPENAI_API_KEY" not in os.environ
    assert "OPENAI_BASE_URL" not in os.environ


def test_agents_sdk_resolves_read_only_completion_without_draft_pr() -> None:
    read_only = swarm_runtime.JudgeVerdict(
        loop=2,
        verdict="accepted",
        blockers=[],
        accepted_evidence=["runtime evidence complete"],
        rejected_claims=[],
        required_next_actions=[],
        draft_pr_ready=False,
        mission_complete=True,
        human_approval_required=False,
    )
    draft_pr = read_only.model_copy(update={
        "draft_pr_ready": True,
        "mission_complete": False,
    })
    blocked = read_only.model_copy(update={"blockers": ["missing evidence"]})

    assert swarm_runtime._resolved_swarm_status(read_only) == (True, "COMPLETED")
    assert swarm_runtime._resolved_swarm_status(draft_pr) == (True, "READY_FOR_DRAFT_PR")
    assert swarm_runtime._resolved_swarm_status(blocked) == (False, "BLOCKED")


def test_raw_payment_card_numbers_are_rejected_but_provider_tokens_are_not() -> None:
    assert runtime._contains_payment_card_number("4242 4242 4242 4242") is True
    assert runtime._contains_payment_card_bytes(b"4242 4242 4242 4242") is True
    assert runtime._contains_payment_card_number("tok_provider_9f42b1d0") is False
    assert runtime._contains_payment_card_bytes(b"tok_provider_9f42b1d0") is False
    assert runtime._comment_is_safe("Bitte für den Agents-SDK-Lauf verwenden.") is True
    assert runtime._comment_is_safe("Karte 4242 4242 4242 4242") is False
    assert runtime._comment_is_safe("ghp_abcdefghijklmnopqrstuvwxyz123456") is False


def test_only_explicitly_configured_owner_matches(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_ADMIN_ID", "owner-id")
    monkeypatch.delenv("SOVEREIGN_OWNER_ADMIN_EMAIL", raising=False)
    assert runtime._owner_matches({"id": "owner-id", "role": "user"}) is True
    assert runtime._owner_matches({"id": "other", "role": "superadmin"}) is False

    monkeypatch.delenv("SOVEREIGN_OWNER_ADMIN_ID", raising=False)
    monkeypatch.setenv("SOVEREIGN_OWNER_ADMIN_EMAIL", "owner@example.test")
    assert runtime._owner_matches({"email": "OWNER@example.test", "role": "user"}) is True

    monkeypatch.delenv("SOVEREIGN_OWNER_ADMIN_EMAIL", raising=False)
    assert runtime._owner_matches({"role": "superadmin"}) is False
    assert runtime._owner_matches({"role": "admin"}) is False


def test_owner_page_keeps_value_out_of_storage_and_clears_transport_field() -> None:
    page = runtime._OWNER_PAGE

    assert 'id="yesButton"' in page
    assert 'id="noButton"' in page
    assert 'id="comment"' in page
    assert 'id="protectedValue" type="password"' in page
    assert "localStorage" not in page
    assert "sessionStorage" not in page
    assert "application/octet-stream" in page
    assert "new TextEncoder().encode" in page
    assert "encoded.fill(0)" in page
    assert "JSON.stringify" not in page
    assert "byId('protectedValue').value=''" in page
    assert "cache:'no-store'" in page
    assert "new URLSearchParams(window.location.search).get('request_id')" in page
    assert "requests.find(item=>item.id===requestedId)" in page
    assert "credentials:'same-origin'" in page
    assert "mode:'same-origin'" in page
    assert "redirect:'error'" in page
    assert "HTTPS-Übertragung nicht bestätigt" in page
