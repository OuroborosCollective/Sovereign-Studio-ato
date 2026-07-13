from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from agent_runtime.cognitive_swarm_manifest import (
    AGENTS,
    DOUBLE_LOOP_PHASES,
    WORKER_ROLES,
    manifest_payload,
    validate_manifest,
)


def test_cognitive_swarm_manifest_is_exactly_eight_roles() -> None:
    validate_manifest()
    assert len(AGENTS) == 8
    assert AGENTS[0].role == "dispatcher"
    assert AGENTS[-1].role == "judge"
    assert tuple(agent.role for agent in AGENTS[1:7]) == WORKER_ROLES
    assert len(WORKER_ROLES) == 6


def test_only_judge_can_declare_release_readiness() -> None:
    assert all(agent.may_release is False for agent in AGENTS[:-1])
    assert AGENTS[-1].may_release is True
    assert AGENTS[-1].may_mutate is False


def test_double_loop_contract_cannot_skip_refinement() -> None:
    assert DOUBLE_LOOP_PHASES == (
        "dispatcher_plan",
        "worker_pass_one",
        "judge_checkpoint_one",
        "worker_refinement_pass_two",
        "judge_final_verdict",
    )


def test_manifest_payload_is_draft_pr_only() -> None:
    payload = manifest_payload()
    assert payload["agentCount"] == 8
    assert payload["releaseMode"] == "draft_pr_only"
    assert payload["autoMerge"] is False
    assert payload["runtimeTruthRequired"] is True
