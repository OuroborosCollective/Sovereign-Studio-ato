import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

BACKEND = Path(__file__).resolve().parents[1]
PRODUCTION_BACKEND = BACKEND.parent / "scripts" / "sovereign-backend"
sys.path.insert(0, str(BACKEND))

import agent_runtime.cognitive_swarm_agents as swarm_module
from agent_runtime.cognitive_output_budget import assess_output_budget_evidence
from agent_runtime.cognitive_swarm_agents import MissionIntent, SwarmExecutionError


def _length_result(*, final_output: object = "", completion: int = 64, reasoning: int = 62):
    return SimpleNamespace(
        final_output=final_output,
        raw_responses=[
            {
                "choices": [{"finish_reason": "length"}],
                "usage": {
                    "completion_tokens": completion,
                    "completion_tokens_details": {"reasoning_tokens": reasoning},
                },
            }
        ],
    )


def test_output_budget_evidence_detects_explicit_length_without_raw_output() -> None:
    evidence = assess_output_budget_evidence(
        _length_result(),
        output_token_limit=128,
    )

    assert evidence == {
        "schemaVersion": "sovereign.output-budget-diagnostic.v1",
        "budgetExhausted": True,
        "finishReason": "length",
        "completionTokens": 64,
        "reasoningTokens": 62,
        "outputTokenLimit": 128,
        "explicitLengthFinish": True,
        "fullReasoningBudgetObserved": False,
        "rawOutputPersisted": False,
        "truthVerdict": "NOT_ASSERTED",
    }


def test_output_budget_evidence_does_not_turn_reasoning_usage_into_failure_when_result_stops() -> None:
    result = SimpleNamespace(
        raw_responses=[
            {
                "choices": [{"finish_reason": "stop"}],
                "usage": {
                    "completion_tokens": 79,
                    "completion_tokens_details": {"reasoning_tokens": 59},
                },
            }
        ]
    )

    evidence = assess_output_budget_evidence(result, output_token_limit=128)

    assert evidence["budgetExhausted"] is False
    assert evidence["finishReason"] == "stop"
    assert evidence["reasoningTokens"] == 59
    assert evidence["rawOutputPersisted"] is False


def test_model_behavior_length_failure_is_classified_as_budget_exhaustion() -> None:
    ModelBehaviorError = type("ModelBehaviorError", (Exception,), {})
    exc = ModelBehaviorError("raw provider output must not persist")
    exc.response = {
        "choices": [{"finish_reason": "length"}],
        "usage": {
            "completion_tokens": 2048,
            "completion_tokens_details": {"reasoning_tokens": 1900},
        },
    }

    failure = swarm_module.classify_swarm_exception(
        exc,
        stage="dispatcher",
        transport="openrouter",
    )

    assert failure.family == "AGENTS_OUTPUT_BUDGET_EXHAUSTED"
    assert failure.next_action == "RETRY_WITH_BOUNDED_OUTPUT_BUDGET_INCREASE"
    assert failure.retryable is True
    payload = failure.safe_payload()
    assert payload["outputBudgetEvidence"]["finishReason"] == "length"
    assert payload["outputBudgetEvidence"]["reasoningTokens"] == 1900
    assert payload["outputBudgetEvidence"]["rawOutputPersisted"] is False
    assert "raw provider output" not in str(payload)


def test_free_single_agent_empty_length_result_uses_budget_failure_family(monkeypatch) -> None:
    class FakeAgent:
        def __init__(self, **kwargs):
            self.model = kwargs["model"]

    class FakeRunner:
        @staticmethod
        async def run(agent, prompt, *, run_config, max_turns):
            return _length_result(completion=2048, reasoning=1900)

    monkeypatch.setattr(swarm_module, "_require_agents_sdk", lambda: (FakeAgent, FakeRunner))
    monkeypatch.setattr(
        swarm_module,
        "build_route_run_config",
        lambda route, output_token_limit: SimpleNamespace(
            model="auto",
            transport="freellm",
            run_config=object(),
        ),
    )
    intent = MissionIntent(
        mode="conversation",
        normalized_goal="Explain the current route.",
        requires_online_tools=False,
        requires_repository_workspace=False,
        learning_scope=[],
        confidence=1.0,
    )

    with pytest.raises(SwarmExecutionError) as captured:
        asyncio.run(
            swarm_module.run_free_single_agent(
                "Explain the current route.",
                model="auto",
                intent=intent,
                route={"id": "free-auto"},
            )
        )

    assert captured.value.family == "AGENTS_OUTPUT_BUDGET_EXHAUSTED"
    assert captured.value.next_action == "RETRY_WITH_BOUNDED_OUTPUT_BUDGET_INCREASE"
    assert captured.value.safe_payload()["outputBudgetEvidence"]["completionTokens"] == 2048


def test_free_single_agent_partial_length_result_is_returned_but_marked_truncated(monkeypatch) -> None:
    class FakeAgent:
        def __init__(self, **kwargs):
            self.model = kwargs["model"]

    class FakeRunner:
        @staticmethod
        async def run(agent, prompt, *, run_config, max_turns):
            return _length_result(
                final_output="Partial bounded answer",
                completion=2048,
                reasoning=1900,
            )

    monkeypatch.setattr(swarm_module, "_require_agents_sdk", lambda: (FakeAgent, FakeRunner))
    monkeypatch.setattr(
        swarm_module,
        "build_route_run_config",
        lambda route, output_token_limit: SimpleNamespace(
            model="auto",
            transport="freellm",
            run_config=object(),
        ),
    )
    intent = MissionIntent(
        mode="conversation",
        normalized_goal="Explain the current route.",
        requires_online_tools=False,
        requires_repository_workspace=False,
        learning_scope=[],
        confidence=1.0,
    )

    result = asyncio.run(
        swarm_module.run_free_single_agent(
            "Explain the current route.",
            model="auto",
            intent=intent,
            route={"id": "free-auto"},
        )
    )

    assert result["ok"] is True
    assert result["result"]["assistant_text"] == "Partial bounded answer"
    assert result["result"]["response_truncated"] is True


def test_sdk_and_billing_share_reasoning_inclusive_output_ceiling():
    from agent_runtime.cognitive_usage_billing import AgentStageBilling
    from agent_runtime.cognitive_output_budget import AGENT_OUTPUT_TOKEN_LIMIT

    billing = AgentStageBilling.__new__(AgentStageBilling)
    assert billing.output_token_limit == swarm_module._AGENT_OUTPUT_TOKEN_LIMIT == AGENT_OUTPUT_TOKEN_LIMIT == 8192
    partial = SimpleNamespace(usage={
        "completion_tokens": 8192,
        "completion_tokens_details": {"reasoning_tokens": 8100},
    })
    failure = swarm_module._output_budget_failure(partial, stage="dispatcher-output")
    assert failure is not None
    assert failure.safe_payload()["outputBudgetEvidence"]["outputTokenLimit"] == 8192
    shorter = SimpleNamespace(usage={
        "completion_tokens": 2048,
        "completion_tokens_details": {"reasoning_tokens": 1900},
    })
    assert swarm_module._output_budget_failure(shorter, stage="dispatcher-output") is None


def test_production_image_mirrors_output_budget_guard() -> None:
    source_guard = BACKEND / "agent_runtime" / "cognitive_output_budget.py"
    production_guard = PRODUCTION_BACKEND / "agent_runtime" / "cognitive_output_budget.py"
    source_agents = BACKEND / "agent_runtime" / "cognitive_swarm_agents.py"
    production_agents = PRODUCTION_BACKEND / "agent_runtime" / "cognitive_swarm_agents.py"

    assert production_guard.read_bytes() == source_guard.read_bytes()
    assert production_agents.read_bytes() == source_agents.read_bytes()
    assert b"AGENTS_OUTPUT_BUDGET_EXHAUSTED" in production_agents.read_bytes()
