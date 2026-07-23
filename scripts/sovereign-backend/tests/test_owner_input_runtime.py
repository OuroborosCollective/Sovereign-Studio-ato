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


def test_allowlisted_target_is_derived_from_configured_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(tmp_path))

    targets = runtime._target_map()

    assert {
        "openrouter_api_key",
        "revolver_provider_key",
        "proven_learning_confirmation",
    }.issubset(set(targets))
    assert "openai_api_key" not in targets
    assert "litellm_provider_key" not in targets
    groq_target = targets["freellm_provider_groq_key"]
    assert groq_target["path"] == (
        tmp_path / "freellm-provider-keys" / "groq.key"
    ).resolve()
    assert groq_target["fieldLabel"] == "Groq API-Key"
    assert groq_target["maxBytes"] == 8192

    openrouter_target = targets["openrouter_api_key"]
    assert openrouter_target["path"] == (tmp_path / "openrouter_api_key.txt").resolve()
    assert openrouter_target["fieldLabel"] == "OpenRouter API-Key"
    assert openrouter_target["maxBytes"] == 8192

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
    target = runtime._target_map()["openrouter_api_key"]

    runtime._atomic_write(target, "one-time-provider-value")

    path = tmp_path / "openrouter_api_key.txt"
    assert path.read_text("utf-8") == "one-time-provider-value"
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert list(tmp_path.glob(".*.tmp")) == []


def test_atomic_write_rejects_empty_and_oversized_values(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(tmp_path))
    target = runtime._target_map()["openrouter_api_key"]

    with pytest.raises(ValueError, match="fehlt"):
        runtime._atomic_write(target, "")
    with pytest.raises(ValueError, match="überschreitet"):
        runtime._atomic_write({**target, "maxBytes": 3}, "four")


def test_agents_sdk_fails_closed_without_explicit_direct_route_run_config() -> None:
    class NeverCalledRunner:
        @staticmethod
        async def run(agent, prompt, *, run_config, max_turns):
            raise AssertionError("provider execution must not start")

    with pytest.raises(swarm_runtime.SwarmExecutionError) as captured:
        asyncio.run(
            swarm_runtime._run_stage(
                NeverCalledRunner,
                "agent",
                "prompt",
                stage="test",
            )
        )
    assert captured.value.family == "AGENTS_DIRECT_ROUTE_REQUIRED"
    assert captured.value.next_action == "RESOLVE_DATABASE_OPENROUTER_OR_FREELLM_ROUTE"


def test_agents_sdk_runner_receives_explicit_direct_route_run_config() -> None:
    captured: dict[str, object] = {}
    direct_run_config = object()

    class CapturingRunner:
        @staticmethod
        async def run(agent, prompt, *, run_config, max_turns):
            captured["agent"] = agent
            captured["prompt"] = prompt
            captured["run_config"] = run_config
            captured["max_turns"] = max_turns
            return "ok"

    result = asyncio.run(
        swarm_runtime._run_stage(
            CapturingRunner,
            "agent",
            "prompt",
            stage="test",
            run_config=direct_run_config,
            transport="openrouter",
        )
    )

    assert result == "ok"
    assert captured == {
        "agent": "agent",
        "prompt": "prompt",
        "run_config": direct_run_config,
        "max_turns": 1,
    }


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
