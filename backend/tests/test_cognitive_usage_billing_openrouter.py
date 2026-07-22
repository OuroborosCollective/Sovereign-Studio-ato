from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from agent_runtime.cognitive_usage_billing import AgentBillingError, AgentStageBilling
from llm_cost_policy import route_billing_policy
from llm_transport import OPENROUTER_BASE_URL


def _route(route_id: str, model: str, *, input_price: float, output_price: float) -> dict:
    return {
        "id": route_id,
        "model_id": f"sovereign-openrouter:{model}",
        "model_name": model,
        "provider": "openrouter",
        "runtime_kind": "openrouter",
        "base_url": OPENROUTER_BASE_URL,
        "disabled": False,
        "config": {
            "transport": "openrouter",
            "direct": True,
            "providerModel": model,
            "executionProfile": "paid_swarm_6",
            "billingCategory": "standard",
            "billingClass": "standard",
            "fundingMode": "provider_priced",
            "markupMultiplier": 4,
            "inputUsdPerMillion": input_price,
            "cachedInputUsdPerMillion": input_price,
            "outputUsdPerMillion": output_price,
            "pricingVerified": True,
            "pricingSource": "openrouter:/api/v1/models",
            "catalogVerified": True,
            "transportCanaryVerified": True,
            "selectable": True,
            "supportedExecutionRoles": ["main", "swarm_agents"],
            "providerPolicy": {
                "require_parameters": True,
                "allow_fallbacks": False,
                "data_collection": "deny",
                "zdr": True,
            },
        },
    }


def test_stage_billing_uses_main_for_dispatch_and_judge_and_agent_model_for_workers() -> None:
    main = _route(
        "main",
        "openai/gpt-5.4-mini",
        input_price=0.75,
        output_price=4.5,
    )
    agents = _route(
        "agents",
        "anthropic/claude-haiku-4.5",
        input_price=1.0,
        output_price=5.0,
    )
    billing = AgentStageBilling.__new__(AgentStageBilling)
    billing.main_route = main
    billing.main_policy = route_billing_policy(main)
    billing.agent_route = agents
    billing.agent_policy = route_billing_policy(agents)

    dispatcher = billing._profile_for_stage("dispatcher")
    worker = billing._profile_for_stage("loop-1:worker:backend")
    judge = billing._profile_for_stage("loop-1:judge")

    assert dispatcher["billingRole"] == "main"
    assert dispatcher["providerModel"] == "openai/gpt-5.4-mini"
    assert worker["billingRole"] == "swarm_agents"
    assert worker["providerModel"] == "anthropic/claude-haiku-4.5"
    assert worker["policy"]["outputUsdPerMillion"] == 5
    assert judge["billingRole"] == "main"
    assert judge["providerModel"] == "openai/gpt-5.4-mini"


def test_worker_and_main_reservation_bounds_use_separate_request_limits() -> None:
    assert AgentStageBilling.request_upper_bound("dispatcher") == 1
    assert AgentStageBilling.request_upper_bound("loop-2:judge") == 1
    assert AgentStageBilling.request_upper_bound("loop-2:worker:security") == 6


def test_user_visible_billing_error_never_exposes_markup_or_provider_cost() -> None:
    payload = AgentBillingError(
        "PAID_CREDITS_REQUIRED",
        required_credits=12,
        available_credits=3,
    ).safe_payload()

    assert payload["requiredCredits"] == 12
    assert payload["availableProviderFundedCredits"] == 3
    assert "markupMultiplier" not in payload
    assert "providerCost" not in payload
