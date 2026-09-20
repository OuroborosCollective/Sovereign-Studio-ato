from __future__ import annotations

from pathlib import Path
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.cag_self_healing import (
    FailureFamily,
    SelfHealingContractError,
    SelfHealingObservation,
    authority_allows,
    build_agent_zero_repair_mission,
    build_cag_verification_code,
    build_repair_contract,
    cag_agrees_with_local_verdict,
    detect_failures,
    failure_mask,
    failures_from_mask,
    parse_cag_failure_mask,
    transition_order_valid,
)


REVISION = "a" * 40
SHA = "b" * 64


def observation(**overrides) -> SelfHealingObservation:
    values = {
        "job_id": "agent-test-job",
        "job_status": "running",
        "external_ref_class": "agent-zero-a2a",
        "observed_endpoint_path": "/a2a/",
        "expected_endpoint_path": "/a2a/",
        "event_stages": (
            "agent_job_created",
            "repository_execution_contract_bound",
            "agent_zero_repository_access_delegated",
            "agent_zero_a2a_submit_queued",
            "agent_zero_a2a_submitted",
        ),
        "handoff_timed_out": False,
        "task_readback_available": False,
        "workspace_changes_present": False,
        "billing_mode": "free",
        "billing_settlement_count": 0,
        "billing_provider_cost_micros": 0,
        "billing_charged_cost_micros": 0,
        "billing_credit_delta_micros": 0,
        "billing_settled": False,
        "source_revision": REVISION,
    }
    values.update(overrides)
    return SelfHealingObservation(**values)


def test_healthy_agent_zero_free_path_has_no_failure() -> None:
    item = observation()
    assert detect_failures(item) == ()
    assert failure_mask(()) == 0
    assert cag_agrees_with_local_verdict(item, "0") is True
    code = build_cag_verification_code(item)
    assert "Total[{" in code
    assert "/a2a/" in code
    assert "agent-zero-a2a" in code
    assert "Authorization" not in code


@pytest.mark.parametrize(
    ("item", "family"),
    [
        (observation(external_ref_class="unexpected-executor"), FailureFamily.EXECUTOR_MISMATCH),
        (observation(observed_endpoint_path="/a2a"), FailureFamily.ENDPOINT_ROUTE_MISMATCH),
        (observation(handoff_timed_out=True), FailureFamily.HANDOFF_TIMEOUT_WITH_READBACK),
        (
            observation(
                event_stages=(
                    "agent_job_created",
                    "repository_execution_contract_bound",
                    "repository_ready_for_draft_pr",
                )
            ),
            FailureFamily.JOB_STATE_TRANSITION_VIOLATION,
        ),
        (
            observation(
                billing_settlement_count=1,
                billing_provider_cost_micros=100,
                billing_charged_cost_micros=400,
                billing_credit_delta_micros=-400,
                billing_settled=True,
            ),
            FailureFamily.BILLING_ROUTE_MISMATCH,
        ),
    ],
)
def test_each_v1_failure_family_is_deterministically_detectable(
    item: SelfHealingObservation,
    family: FailureFamily,
) -> None:
    failures = detect_failures(item)
    assert family in failures
    mask = failure_mask(failures)
    assert family in failures_from_mask(mask)
    assert cag_agrees_with_local_verdict(item, str(mask)) is True


def test_transition_contract_requires_agent_zero_evidence_before_draft_ready() -> None:
    assert transition_order_valid(
        (
            "agent_job_created",
            "repository_execution_contract_bound",
            "agent_zero_repository_access_delegated",
            "agent_zero_a2a_submit_queued",
            "agent_zero_a2a_submitted",
            "repository_ready_for_draft_pr",
        )
    )
    assert not transition_order_valid(
        (
            "agent_job_created",
            "repository_execution_contract_bound",
            "repository_ready_for_draft_pr",
        )
    )


def test_cag_mask_parser_fails_closed_and_divergence_is_rejected() -> None:
    item = observation(observed_endpoint_path="/wrong")
    assert parse_cag_failure_mask("2") == 2
    assert parse_cag_failure_mask("Out[1]=2") == 2
    assert parse_cag_failure_mask("Out[42]= 2") == 2
    assert cag_agrees_with_local_verdict(item, "2") is True
    assert cag_agrees_with_local_verdict(item, "Out[1]=2") is True
    assert cag_agrees_with_local_verdict(item, "0") is False
    with pytest.raises(SelfHealingContractError):
        parse_cag_failure_mask("SUPPORTED")
    with pytest.raises(SelfHealingContractError):
        parse_cag_failure_mask("During evaluation...\\nOut[1]=2")
    with pytest.raises(SelfHealingContractError):
        parse_cag_failure_mask("999999")


def test_repair_contract_keeps_agent_zero_as_only_code_executor() -> None:
    item = observation(observed_endpoint_path="/wrong")
    failures = detect_failures(item)
    contract = build_repair_contract(
        observation=item,
        failures=failures,
        cag_request_sha256=SHA,
        cag_response_sha256="c" * 64,
        cag_result_sha256="d" * 64,
        controller_repository="OuroborosCollective/Sovereign-Studio-ato",
    )
    assert contract["failureFamily"] == "ENDPOINT_ROUTE_MISMATCH"
    assert contract["requiredExecutor"] == "agent-zero-a2a"
    assert contract["authorityRequirement"] == "AUTO_BOUNDED_CODE_REPAIR"
    assert "automatic-merge" in contract["forbiddenEffects"]
    assert contract["sourceRevision"] == REVISION
    mission = build_agent_zero_repair_mission(contract)
    assert "Agent Zero" in mission
    assert "automatic merge" not in mission.lower()
    assert contract["repairContractSha256"] in mission


def test_readback_timeout_never_generates_a_code_repair_mission() -> None:
    item = observation(handoff_timed_out=True, task_readback_available=True)
    contract = build_repair_contract(
        observation=item,
        failures=detect_failures(item),
        cag_request_sha256=SHA,
        cag_response_sha256="c" * 64,
        cag_result_sha256="d" * 64,
        controller_repository="OuroborosCollective/Sovereign-Studio-ato",
    )
    assert contract["actionKind"] == "readback-only"
    assert contract["authorityRequirement"] == "AUTO_SAFE"
    assert contract["targetFiles"] == []
    with pytest.raises(SelfHealingContractError, match="readback-only"):
        build_agent_zero_repair_mission(contract)


def test_multiple_failure_families_never_collapse_into_one_automatic_repair() -> None:
    item = observation(
        external_ref_class="unexpected-executor",
        observed_endpoint_path="/wrong",
    )
    failures = detect_failures(item)
    assert len(failures) == 2
    with pytest.raises(SelfHealingContractError, match="exactly one"):
        build_repair_contract(
            observation=item,
            failures=failures,
            cag_request_sha256=SHA,
            cag_response_sha256="c" * 64,
            cag_result_sha256="d" * 64,
            controller_repository="OuroborosCollective/Sovereign-Studio-ato",
        )


def test_scoped_standing_authority_is_revocable_expiring_and_level_bounded() -> None:
    allowed = [family.value for family in FailureFamily]
    assert authority_allows(
        mode="AUTO_SAFE",
        allowed_failure_families=allowed,
        failure_family=FailureFamily.HANDOFF_TIMEOUT_WITH_READBACK,
        paused=False,
        expired=False,
    )
    assert not authority_allows(
        mode="AUTO_SAFE",
        allowed_failure_families=allowed,
        failure_family=FailureFamily.ENDPOINT_ROUTE_MISMATCH,
        paused=False,
        expired=False,
    )
    assert authority_allows(
        mode="AUTO_BOUNDED_CODE_REPAIR",
        allowed_failure_families=allowed,
        failure_family=FailureFamily.ENDPOINT_ROUTE_MISMATCH,
        paused=False,
        expired=False,
    )
    assert not authority_allows(
        mode="AUTO_BOUNDED_CODE_REPAIR",
        allowed_failure_families=allowed,
        failure_family=FailureFamily.ENDPOINT_ROUTE_MISMATCH,
        paused=True,
        expired=False,
    )
    assert not authority_allows(
        mode="AUTO_BOUNDED_CODE_REPAIR",
        allowed_failure_families=allowed,
        failure_family=FailureFamily.ENDPOINT_ROUTE_MISMATCH,
        paused=False,
        expired=True,
    )


def test_migration_encodes_consent_rate_limit_incident_and_receipt_boundaries() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / ".."
        / "scripts"
        / "sovereign-backend"
        / "migrations"
        / "064_cag_self_healing_controller.sql"
    ).resolve().read_text("utf-8")
    assert "sovereign_self_healing_authority" in migration
    assert "AUTO_BOUNDED_CODE_REPAIR" in migration
    assert "max_auto_repairs_per_hour BETWEEN 1 AND 10" in migration
    assert "expires_at TIMESTAMPTZ NOT NULL" in migration
    assert "sovereign_self_healing_incidents" in migration
    assert "CAG_VERIFYING" in migration
    assert "REPAIR_CLAIMED" in migration
    assert "sovereign_self_healing_action_receipts" in migration
    for family in FailureFamily:
        assert family.value in migration


def test_daily_budget_and_manual_approval_migration_is_bounded() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / ".."
        / "scripts"
        / "sovereign-backend"
        / "migrations"
        / "065_self_healing_daily_budget_manual_approval.sql"
    ).resolve().read_text("utf-8")
    assert "max_auto_repairs_per_day INTEGER NOT NULL DEFAULT 3" in migration
    assert "max_auto_repairs_per_day BETWEEN 1 AND 30" in migration
    assert "sovereign_self_healing_manual_approvals" in migration
    assert "consumed_at IS NULL" in migration
    assert "idx_self_healing_manual_approval_active" in migration
