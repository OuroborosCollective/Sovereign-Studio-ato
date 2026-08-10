from __future__ import annotations

from pathlib import Path
import sys

import pytest

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from agent_runtime.cognitive_swarm_agents import (
    DispatchPlan,
    SwarmExecutionError,
    _parse_text_contract_output,
)


def _dispatch_json() -> str:
    return (
        '{"mission":"bounded mission","ordered_work":['
        '"data_storage: inspect data",'
        '"business_core: inspect core",'
        '"endpoint_bridge: inspect endpoints",'
        '"chat_cognitive: inspect cognition",'
        '"ui_accessibility: inspect ui",'
        '"predictive_qa: verify"'
        '],"required_evidence":[],"initial_blockers":[]}'
    )


def test_free_swarm_text_contract_accepts_strict_json_and_fenced_json() -> None:
    parsed = _parse_text_contract_output(_dispatch_json(), DispatchPlan, stage="dispatcher")
    fenced = _parse_text_contract_output(
        "```json\n" + _dispatch_json() + "\n```",
        DispatchPlan,
        stage="dispatcher",
    )

    assert isinstance(parsed, DispatchPlan)
    assert isinstance(fenced, DispatchPlan)
    assert len(parsed.ordered_work) == 6
    assert parsed.ordered_work[0] == "data_storage: inspect data"


def test_free_swarm_text_contract_rejects_prose_or_invalid_shape() -> None:
    with pytest.raises(SwarmExecutionError) as prose:
        _parse_text_contract_output(
            "I have completed the work and everything is green.",
            DispatchPlan,
            stage="dispatcher",
        )
    assert prose.value.family == "AGENTS_TEXT_CONTRACT_INVALID"

    with pytest.raises(SwarmExecutionError) as invalid:
        _parse_text_contract_output(
            '{"mission":"bounded mission","ordered_work":[]}',
            DispatchPlan,
            stage="dispatcher",
        )
    assert invalid.value.family == "AGENTS_TEXT_CONTRACT_INVALID"


def test_free_swarm_source_requires_one_transport_and_explicit_worker_routes() -> None:
    source = (RUNTIME_ROOT / "agent_runtime" / "cognitive_swarm_agents.py").read_text("utf-8")

    assert 'transports not in ({"openrouter"}, {"freellm"})' in source
    assert 'text_contract = transports == {"freellm"}' in source
    assert "worker_routes: dict[str, dict[str, Any]] | None = None" in source
    assert "worker_runtimes[role].run_config" in source
    assert "selected_worker_models[contract.role]" in source
    assert "AGENTS_TEXT_CONTRACT_INVALID" in source
