import asyncio
from pathlib import Path
import sys

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from agent_runtime.cognitive_swarm_agents import (
    SKILL_PATH,
    agents_sdk_status,
    build_cognitive_swarm,
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
