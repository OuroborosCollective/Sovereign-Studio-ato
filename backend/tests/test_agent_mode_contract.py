from pathlib import Path

import pytest

from agent_runtime import cognitive_swarm_routes as routes
from llm_execution_resolver import ExecutionResolution, FREE_SINGLE_AGENT_PROFILE, FREE_SWARM_PROFILE


def _free_swarm_resolution() -> ExecutionResolution:
    routes_list = tuple({"id": f"free-{index}"} for index in range(7))
    return ExecutionResolution(
        profile_id=FREE_SWARM_PROFILE,
        primary_route=routes_list[0],
        agent_route=routes_list[1],
        candidate_routes=routes_list,
        max_foreground_agents=1,
        max_background_agents=6,
        repository_execution_allowed=True,
        paid_purchase_verified=False,
        paid_entitlement_verified=True,
        paid_entitlement_source="existing_credit_balance",
        provider_funded_credits=0,
        requested_mode="free",
        reason="free_swarm_ready_with_seven_independent_verified_quota_scopes",
    )


def test_agent_mode_normalization_is_bounded():
    assert routes._normalize_agent_mode("single") == "single"
    assert routes._normalize_agent_mode("SWARM") == "swarm"
    assert routes._normalize_agent_mode("") == "auto"
    with pytest.raises(ValueError, match="agentMode must be auto, single or swarm"):
        routes._normalize_agent_mode("background-chaos")


def test_explicit_single_agent_projects_free_swarm_capacity_to_one_agent():
    projected = routes._single_agent_resolution(_free_swarm_resolution())
    assert projected.profile_id == FREE_SINGLE_AGENT_PROFILE
    assert projected.primary_route["id"] == "free-0"
    assert projected.agent_route["id"] == "free-0"
    assert projected.max_foreground_agents == 1
    assert projected.max_background_agents == 0
    assert [route["id"] for route in projected.candidate_routes] == [f"free-{index}" for index in range(7)]


def test_user_route_exposes_single_default_and_explicit_swarm_feature():
    source = Path(routes.__file__).read_text(encoding="utf-8")
    assert '"agentModes": ["single", "swarm"]' in source
    assert '"defaultAgentMode": "single"' in source
    assert '"swarmRequiresExplicitOptIn": True' in source
    assert 'agent_mode=str(body.get("agentMode") or "auto")' in source
    assert 'blocker="SWARM_CAPACITY_NOT_READY"' in source
    assert 'next_action="USE_SINGLE_AGENT_OR_RETRY_SWARM_WHEN_CAPACITY_READY"' in source
