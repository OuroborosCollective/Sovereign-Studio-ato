from __future__ import annotations

from pathlib import Path
import sys

import pytest

try:
    import flask  # noqa: F401
except ModuleNotFoundError:  # Lightweight MCP validation image.
    flask = None  # type: ignore[assignment]

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

if flask is not None:
    from llm_provider_runtime import _provider_canary_payload  # noqa: E402
else:
    _provider_canary_payload = None


def test_canary_payload_contract_is_present_without_optional_flask() -> None:
    runtime = (BACKEND / "llm_provider_runtime.py").read_text("utf-8")
    assert "def _provider_canary_payload(" in runtime
    assert '"max_completion_tokens": 256' in runtime
    assert '"reasoning_effort": "low"' in runtime
    assert '"include_reasoning": False' in runtime


@pytest.mark.skipif(flask is None, reason="Flask is validated in the full backend CI image")
def test_groq_gpt_oss_canary_reserves_final_answer_budget() -> None:
    payload = _provider_canary_payload(
        "sovereign-groq-openai-gpt-oss-20b-301e7b07",
        provider_prefix="groq",
        upstream_model_id="openai/gpt-oss-20b",
    )

    assert payload["model"] == "sovereign-groq-openai-gpt-oss-20b-301e7b07"
    assert payload["messages"] == [{"role": "user", "content": "Reply with OK."}]
    assert payload["max_completion_tokens"] == 256
    assert payload["reasoning_effort"] == "low"
    assert payload["include_reasoning"] is False
    assert payload["stream"] is False
    assert "max_tokens" not in payload
    assert "api_key" not in payload


@pytest.mark.skipif(flask is None, reason="Flask is validated in the full backend CI image")
def test_non_reasoning_provider_keeps_generic_completion_contract() -> None:
    payload = _provider_canary_payload(
        "sovereign-balanced",
        provider_prefix="openai",
        upstream_model_id="gpt-5.4-mini",
    )

    assert payload["max_tokens"] == 64
    assert payload["temperature"] == 0
    assert payload["stream"] is False
    assert "max_completion_tokens" not in payload
    assert "reasoning_effort" not in payload
    assert "include_reasoning" not in payload
