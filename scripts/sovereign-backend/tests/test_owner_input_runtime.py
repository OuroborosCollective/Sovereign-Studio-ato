from __future__ import annotations

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

    target = targets["openhands_api_key"]
    assert target["path"] == (tmp_path / "openhands_api_key.txt").resolve()
    assert target["maxBytes"] == 8192

    openai_target = targets["openai_api_key"]
    assert openai_target["path"] == (tmp_path / "openai_api_key.txt").resolve()
    assert openai_target["fieldLabel"] == "OpenAI API-Key"
    assert openai_target["maxBytes"] == 8192


def test_atomic_write_is_bounded_mode_0600_and_leaves_no_temporary_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(tmp_path))
    target = runtime._target_map()["openhands_api_key"]

    runtime._atomic_write(target, "one-time-provider-value")

    path = tmp_path / "openhands_api_key.txt"
    assert path.read_text("utf-8") == "one-time-provider-value"
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert list(tmp_path.glob(".*.tmp")) == []


def test_atomic_write_rejects_empty_and_oversized_values(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(tmp_path))
    target = runtime._target_map()["openhands_api_key"]

    with pytest.raises(ValueError, match="fehlt"):
        runtime._atomic_write(target, "")
    with pytest.raises(ValueError, match="überschreitet"):
        runtime._atomic_write({**target, "maxBytes": 3}, "four")


def test_openai_agents_key_loads_only_from_owner_managed_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(tmp_path))
    target = runtime._target_map()["openai_api_key"]
    runtime._atomic_write(target, "test-runtime-key-value")

    assert swarm_runtime.ensure_openai_runtime_key() is True
    assert os.environ["OPENAI_API_KEY"] == "test-runtime-key-value"


def test_openai_agents_key_rejects_symlink_escape(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(tmp_path))
    outside = tmp_path.parent / f"{tmp_path.name}-outside-openai-value.txt"
    outside.write_text("test-runtime-key-value", "utf-8")
    (tmp_path / "openai_api_key.txt").symlink_to(outside)

    assert swarm_runtime.ensure_openai_runtime_key() is False
    assert "OPENAI_API_KEY" not in os.environ


def test_openai_agents_key_rejects_group_or_world_readable_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(tmp_path))
    path = tmp_path / "openai_api_key.txt"
    path.write_text("test-runtime-key-value", "utf-8")
    path.chmod(0o644)

    assert swarm_runtime.ensure_openai_runtime_key() is False
    assert "OPENAI_API_KEY" not in os.environ


def test_raw_payment_card_numbers_are_rejected_but_provider_tokens_are_not() -> None:
    assert runtime._contains_payment_card_number("4242 4242 4242 4242") is True
    assert runtime._contains_payment_card_bytes(b"4242 4242 4242 4242") is True
    assert runtime._contains_payment_card_number("tok_provider_9f42b1d0") is False
    assert runtime._contains_payment_card_bytes(b"tok_provider_9f42b1d0") is False
    assert runtime._comment_is_safe("Bitte für den OpenHands-Lauf verwenden.") is True
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
