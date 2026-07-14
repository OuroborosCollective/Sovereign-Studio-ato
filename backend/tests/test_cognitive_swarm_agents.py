import asyncio
from pathlib import Path
import sys

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from agent_runtime.cognitive_swarm_agents import (
    SKILL_PATH,
    SwarmExecutionError,
    agents_sdk_status,
    build_cognitive_swarm,
    classify_swarm_exception,
    run_cognitive_swarm,
)


def test_agents_sdk_topology_contains_eight_core_agents_plus_bounded_specialists_or_fails_closed() -> None:
    status = agents_sdk_status()
    if status["available"] is False:
        with pytest.raises(RuntimeError, match="openai-agents"):
            build_cognitive_swarm(model="gpt-5.6")
        return

    swarm = build_cognitive_swarm(model="gpt-5.6")
    assert swarm.agent_count == 12
    assert swarm.dispatcher.name == "The Dispatcher"
    assert len(swarm.workers) == 6
    assert len(swarm.specialists) == 4
    assert swarm.judge.name == "The Judge"


def test_provider_failures_are_classified_without_raw_error_text() -> None:
    class ProviderFailure(Exception):
        status_code = 429
        request_id = "req-safe-123"

    failure = classify_swarm_exception(
        ProviderFailure("sensitive provider message must never persist"),
        stage="dispatcher",
    )

    assert isinstance(failure, SwarmExecutionError)
    assert failure.family == "OPENAI_RATE_LIMITED"
    assert failure.stage == "dispatcher"
    assert failure.retryable is True
    assert failure.http_status == 429
    assert failure.request_id == "req-safe-123"
    payload = failure.safe_payload()
    assert payload["rawErrorPersisted"] is False
    assert "sensitive provider message" not in str(payload)


def test_structured_output_failure_has_bounded_recovery_family() -> None:
    ModelBehaviorError = type("ModelBehaviorError", (Exception,), {})
    failure = classify_swarm_exception(ModelBehaviorError("raw output"), stage="loop-1:judge")
    assert failure.family == "AGENTS_STRUCTURED_OUTPUT_INVALID"
    assert failure.next_action == "RETRY_WITH_BOUNDED_SCHEMA_DIAGNOSTICS"
    assert failure.safe_payload()["failureStage"] == "loop-1:judge"


def test_routes_persist_only_bounded_failure_metadata() -> None:
    routes = (BACKEND / "agent_runtime" / "cognitive_swarm_routes.py").read_text("utf-8")

    assert "SwarmExecutionError" in routes
    assert "failure = exc.safe_payload()" in routes
    assert '"rawErrorPersisted": False' in routes
    assert '"failureStage": failure_stage' in routes
    assert '"blocker": failure_family' in routes
    assert "evidence_payload=failure" in routes
    assert "family=failure_family" in routes
    assert "Agents SDK execution failed without a validated final verdict." not in routes


def test_repo_local_skill_bundle_is_present_and_bounded() -> None:
    content = SKILL_PATH.read_text("utf-8")
    assert content.startswith("---")
    assert "name: sovereign-cognitive-architecture" in content
    assert "Never auto-merge" in content
    assert "Missing evidence is a blocker" in content


def test_swarm_fails_closed_without_openai_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = asyncio.run(run_cognitive_swarm("Inspect the current runtime evidence."))
    assert result["ok"] is False
    assert result["status"] == "BLOCKED"
    assert "OPENAI_API_KEY" in result["blocker"]
    assert result["manifest"]["agentCount"] == 20
    assert result["manifest"]["coreAgentCount"] == 8
    assert result["manifest"]["maxActiveSpecialists"] == 4
