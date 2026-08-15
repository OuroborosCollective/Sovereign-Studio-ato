from __future__ import annotations

from pathlib import Path
import sys

import pytest

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from agent_runtime.fleet_supervisor import (
    FleetContractError,
    FleetTask,
    build_fleet_plan,
    build_fleet_projection,
    create_worker_assignment,
    evaluate_fleet_verdict,
    pair_conflicts,
    validate_worker_event,
)


BASE = "a" * 40
HEAD = "b" * 40
RECEIPT = "c" * 64


def task(task_id: str, **overrides: object) -> FleetTask:
    data = {
        "task_id": task_id,
        "source_type": "issue",
        "source_id": task_id.removeprefix("task-"),
        "expected_base_revision": BASE,
        "independence_proven": True,
    }
    data.update(overrides)
    return FleetTask(**data)


@pytest.mark.parametrize(
    ("left", "right", "code"),
    [
        ({"changed_paths": ("src/a.py",)}, {"changed_paths": ("src/a.py",)}, "DIRECT_PATH_CONFLICT"),
        ({"changed_paths": ("src/a.py",)}, {"changed_paths": ("src/a.py", "src/b.py")}, "DIRECT_PATH_CONFLICT"),
        ({"canonical_owners": ("backend",)}, {"canonical_owners": ("backend",)}, "CANONICAL_OWNER_CONFLICT"),
        ({"invariant_scopes": ("auth",)}, {"invariant_scopes": ("auth",)}, "INVARIANT_SCOPE_CONFLICT"),
        ({"mutation_resources": ("postgres",)}, {"mutation_resources": ("postgres",)}, "MUTATION_RESOURCE_CONFLICT"),
        ({"lock_scopes": ("workspace",)}, {"lock_scopes": ("workspace",)}, "LOCK_SCOPE_CONFLICT"),
        ({"changed_paths": ("a",), "independence_proven": False}, {"canonical_owners": ("b",)}, "UNPROVEN_INDEPENDENCE"),
        ({"independence_proven": False}, {}, "UNPROVEN_INDEPENDENCE"),
        ({}, {"independence_proven": False}, "UNPROVEN_INDEPENDENCE"),
        ({"lock_scopes": ("mcp",), "independence_proven": False}, {"lock_scopes": ("mcp",)}, "LOCK_SCOPE_CONFLICT"),
    ],
)
def test_conflict_matrix_is_fail_closed(left: dict[str, object], right: dict[str, object], code: str) -> None:
    conflicts = pair_conflicts(task("task-left", **left), task("task-right", **right))

    assert code in {conflict.code for conflict in conflicts}


@pytest.mark.parametrize(
    ("first_path", "second_path"),
    [
        ("src/a.py", "src/b.py"),
        ("docs/a.md", "docs/b.md"),
        ("frontend/a.tsx", "backend/b.py"),
        ("tools/a.py", "scripts/b.py"),
        ("tests/a.py", "tests/b.py"),
    ],
)
def test_parallel_matrix_requires_explicit_non_overlap(first_path: str, second_path: str) -> None:
    plan = build_fleet_plan(
        integration_id="fleet-test",
        repository="OuroborosCollective/Sovereign-Studio-ato",
        base_revision=BASE,
        architecture_receipt_hashes=[RECEIPT],
        max_parallel_lanes=2,
        tasks=[
            task("task-first", changed_paths=(first_path,)),
            task("task-second", changed_paths=(second_path,)),
        ],
    )

    assert len(plan.lanes) == 1
    assert plan.lanes[0].parallel_safe is True
    assert set(plan.lanes[0].task_ids) == {"task-first", "task-second"}


def test_unknown_semantics_are_serialized_and_hash_bound() -> None:
    plan = build_fleet_plan(
        integration_id="fleet-serial",
        repository="OuroborosCollective/Sovereign-Studio-ato",
        base_revision=BASE,
        tasks=[
            task("task-first", independence_proven=False),
            task("task-second", independence_proven=False),
        ],
    )

    assert len(plan.lanes) == 2
    assert "UNPROVEN_INDEPENDENCE" in plan.risk_codes
    assert build_fleet_projection(plan.to_dict(), observed_main_revision=BASE)["planHash"] == plan.plan_hash


def test_dependency_cycle_is_rejected() -> None:
    with pytest.raises(FleetContractError, match="cycle"):
        build_fleet_plan(
            integration_id="fleet-cycle",
            repository="OuroborosCollective/Sovereign-Studio-ato",
            base_revision=BASE,
            tasks=[
                task("task-first", depends_on=("task-second",)),
                task("task-second", depends_on=("task-first",)),
            ],
        )


def test_worker_completion_never_becomes_verification() -> None:
    plan = build_fleet_plan(
        integration_id="fleet-worker",
        repository="OuroborosCollective/Sovereign-Studio-ato",
        base_revision=BASE,
        tasks=[task("task-worker", expected_head_revision=HEAD)],
    )
    assignment = create_worker_assignment(
        plan,
        lane_id="lane-01",
        task_id="task-worker",
        controller_run_id="run-worker",
        workspace_id="job-worker",
        workspace_branch="sovereign/chatgpt/worker",
        run_envelope_hash=RECEIPT,
        capability_manifest_hash=RECEIPT,
    )

    event = validate_worker_event(
        assignment,
        event_type="WORKER_COMPLETED_UNVERIFIED",
        summary="worker changed files and reported bounded evidence",
        evidence_refs=[RECEIPT],
    )

    assert event["status"] == "COMPLETED_UNVERIFIED"
    with pytest.raises(FleetContractError):
        validate_worker_event(
            assignment,
            event_type="WORKER_RUNTIME_VERIFIED",
            summary="this must never be accepted",
        )


def test_exact_head_verdict_requires_exact_ci_and_readback() -> None:
    selected = task(
        "task-verdict",
        expected_head_revision=HEAD,
        required_gates=("unit", "lint"),
    )
    plan = build_fleet_plan(
        integration_id="fleet-verdict",
        repository="OuroborosCollective/Sovereign-Studio-ato",
        base_revision=BASE,
        tasks=[selected],
    )
    assignment = create_worker_assignment(
        plan,
        lane_id="lane-01",
        task_id="task-verdict",
        controller_run_id="run-verdict",
        workspace_id="job-verdict",
        workspace_branch="sovereign/chatgpt/verdict",
        run_envelope_hash=RECEIPT,
        capability_manifest_hash=RECEIPT,
    )

    waiting = evaluate_fleet_verdict(
        selected,
        assignment=assignment,
        observed_base_revision=BASE,
        observed_head_revision=HEAD,
        workspace_head_revision=HEAD,
        check_receipts=[{"gate": "unit", "status": "success", "headSha": HEAD}],
    )
    review_waiting = evaluate_fleet_verdict(
        selected,
        assignment=assignment,
        observed_base_revision=BASE,
        observed_head_revision=HEAD,
        workspace_head_revision=HEAD,
        check_receipts=[
            {"gate": "unit", "status": "success", "headSha": HEAD},
            {"gate": "lint", "status": "success", "headSha": HEAD},
        ],
    )
    cross_waiting = evaluate_fleet_verdict(
        selected,
        assignment=assignment,
        observed_base_revision=BASE,
        observed_head_revision=HEAD,
        workspace_head_revision=HEAD,
        check_receipts=[
            {"gate": "unit", "status": "success", "headSha": HEAD},
            {"gate": "lint", "status": "success", "headSha": HEAD},
        ],
        review_receipts=[{
            "reviewerId": "reviewer-independent",
            "independent": True,
            "status": "approved",
            "headSha": HEAD,
            "receiptSha256": RECEIPT,
        }],
    )
    candidate = evaluate_fleet_verdict(
        selected,
        assignment=assignment,
        observed_base_revision=BASE,
        observed_head_revision=HEAD,
        workspace_head_revision=HEAD,
        check_receipts=[
            {"gate": "unit", "status": "success", "headSha": HEAD},
            {"gate": "lint", "status": "success", "headSha": HEAD},
        ],
        review_receipts=[{
            "reviewerId": "reviewer-independent",
            "independent": True,
            "status": "approved",
            "headSha": HEAD,
            "receiptSha256": RECEIPT,
        }],
        cross_task_receipts=[{
            "status": "passed",
            "headSha": HEAD,
            "conflictsResolved": True,
            "receiptSha256": RECEIPT,
        }],
    )

    assert waiting["status"] == "CI_WAITING"
    assert review_waiting["status"] == "REVIEW_WAITING"
    assert cross_waiting["status"] == "CROSS_TASK_WAITING"
    assert candidate["status"] == "MERGE_CANDIDATE"
    assert candidate["mergeAuthorized"] is False


def test_runtime_verification_binds_to_merge_commit_not_pr_head() -> None:
    merge_sha = "d" * 40
    selected = task(
        "task-runtime",
        expected_head_revision=HEAD,
        required_gates=("unit",),
    )
    plan = build_fleet_plan(
        integration_id="fleet-runtime",
        repository="OuroborosCollective/Sovereign-Studio-ato",
        base_revision=BASE,
        tasks=[selected],
    )
    assignment = create_worker_assignment(
        plan,
        lane_id="lane-01",
        task_id="task-runtime",
        controller_run_id="run-runtime",
        workspace_id="job-runtime",
        workspace_branch="sovereign/chatgpt/runtime",
        run_envelope_hash=RECEIPT,
        capability_manifest_hash=RECEIPT,
    )
    verdict = evaluate_fleet_verdict(
        selected,
        assignment=assignment,
        observed_base_revision=BASE,
        observed_head_revision=HEAD,
        workspace_head_revision=HEAD,
        check_receipts=[{"gate": "unit", "status": "success", "headSha": HEAD}],
        review_receipts=[{
            "reviewerId": "reviewer-runtime",
            "independent": True,
            "status": "approved",
            "headSha": HEAD,
            "receiptSha256": RECEIPT,
        }],
        cross_task_receipts=[{
            "status": "passed",
            "headSha": HEAD,
            "conflictsResolved": True,
            "receiptSha256": RECEIPT,
        }],
        merge_readback={
            "merged": True,
            "readbackVerified": True,
            "headSha": HEAD,
            "mergeCommitSha": merge_sha,
        },
        runtime_readback={
            "deployedRevision": merge_sha,
            "imageDigest": "sha256:" + ("e" * 64),
            "patchmonHealthy": True,
            "functionVerified": True,
        },
    )

    assert verdict["status"] == "RUNTIME_VERIFIED"
    assert verdict["mergeRevision"] == merge_sha
    assert verdict["runtimeClaimed"] is True


def test_projection_marks_stale_main_as_command_blocker() -> None:
    plan = build_fleet_plan(
        integration_id="fleet-projection",
        repository="OuroborosCollective/Sovereign-Studio-ato",
        base_revision=BASE,
        tasks=[task("task-projection")],
    )

    projection = build_fleet_projection(plan, observed_main_revision=HEAD)

    assert projection["stale"] is True
    assert projection["commandsBlocked"] is True
    assert "MAIN_HEAD_STALE_OR_UNAVAILABLE" in projection["evidenceGaps"]


def _full_verdict_setup(task_id: str, required_gates: tuple[str, ...]):
    """Build a task, plan and assignment that reach the cross-task evidence stage."""
    selected = task(task_id, expected_head_revision=HEAD, required_gates=required_gates)
    plan = build_fleet_plan(
        integration_id=f"fleet-{task_id}",
        repository="OuroborosCollective/Sovereign-Studio-ato",
        base_revision=BASE,
        tasks=[selected],
    )
    assignment = create_worker_assignment(
        plan,
        lane_id="lane-01",
        task_id=task_id,
        controller_run_id=f"run-{task_id}",
        workspace_id=f"job-{task_id}",
        workspace_branch=f"sovereign/chatgpt/{task_id}",
        run_envelope_hash=RECEIPT,
        capability_manifest_hash=RECEIPT,
    )
    return selected, assignment


def _green_reviews() -> list[dict[str, object]]:
    return [{
        "reviewerId": "reviewer-independent",
        "independent": True,
        "status": "approved",
        "headSha": HEAD,
        "receiptSha256": RECEIPT,
    }]


def _green_cross() -> list[dict[str, object]]:
    return [{
        "status": "passed",
        "headSha": HEAD,
        "conflictsResolved": True,
        "receiptSha256": RECEIPT,
    }]


def test_stale_green_check_is_stale_head_not_ci_failed() -> None:
    """A green check bound to a different SHA is a stale-head contradiction, not CI failure."""
    selected, assignment = _full_verdict_setup("task-stale-head", required_gates=("unit",))
    stale_sha = "9" * 40

    verdict = evaluate_fleet_verdict(
        selected,
        assignment=assignment,
        observed_base_revision=BASE,
        observed_head_revision=HEAD,
        workspace_head_revision=HEAD,
        check_receipts=[{"gate": "unit", "status": "success", "headSha": stale_sha}],
    )

    assert verdict["status"] == "STALE_HEAD"
    assert "CHECK_STALE_HEAD:unit" in verdict["contradictions"]
    assert "CHECK_NOT_EXACT_SUCCESS:unit" not in verdict["evidenceGaps"]
    assert verdict["gateContractDrift"] is False


def test_stale_green_plus_missing_gate_surfaces_contradiction_while_waiting() -> None:
    """A stale green cannot hide behind another gate still waiting; both must surface."""
    selected, assignment = _full_verdict_setup("task-stale-and-wait", required_gates=("unit", "lint"))
    stale_sha = "9" * 40

    verdict = evaluate_fleet_verdict(
        selected,
        assignment=assignment,
        observed_base_revision=BASE,
        observed_head_revision=HEAD,
        workspace_head_revision=HEAD,
        check_receipts=[
            {"gate": "unit", "status": "success", "headSha": stale_sha},
            # 'lint' has no receipt yet
        ],
    )

    assert verdict["status"] == "CI_WAITING"
    assert "CHECK_MISSING:lint" in verdict["evidenceGaps"]
    assert "CHECK_STALE_HEAD:unit" in verdict["contradictions"]


def test_exact_head_failed_check_is_ci_failed() -> None:
    """A check that genuinely failed at the exact head is CI_FAILED, not STALE_HEAD."""
    selected, assignment = _full_verdict_setup("task-ci-failed", required_gates=("unit",))

    verdict = evaluate_fleet_verdict(
        selected,
        assignment=assignment,
        observed_base_revision=BASE,
        observed_head_revision=HEAD,
        workspace_head_revision=HEAD,
        check_receipts=[{"gate": "unit", "status": "failure", "headSha": HEAD}],
    )

    assert verdict["status"] == "CI_FAILED"
    assert "CHECK_FAILED:unit" in verdict["evidenceGaps"]


def test_observed_required_gate_contract_drift_blocks_merge() -> None:
    """When the live required-check contract differs from the plan, merge is blocked.

    All arbitrated gates (including the newly required one) have exact-head receipts, so
    the verdict reaches the merge stage where the un-reconciled contract blocks it.
    """
    selected, assignment = _full_verdict_setup("task-drift", required_gates=("unit", "lint"))
    receipts = [
        {"gate": "unit", "status": "success", "headSha": HEAD},
        {"gate": "lint", "status": "success", "headSha": HEAD},
        {"gate": "audit", "status": "success", "headSha": HEAD},
    ]

    verdict = evaluate_fleet_verdict(
        selected,
        assignment=assignment,
        observed_base_revision=BASE,
        observed_head_revision=HEAD,
        workspace_head_revision=HEAD,
        check_receipts=receipts,
        review_receipts=_green_reviews(),
        cross_task_receipts=_green_cross(),
        observed_required_gates=("unit", "lint", "audit"),
    )

    assert verdict["status"] == "BLOCKED_MISSING_EVIDENCE"
    assert verdict["gateContractDrift"] is True
    assert "REQUIRED_GATE_CONTRACT_DRIFT" in verdict["contradictions"]
    assert "REQUIRED_GATE_CONTRACT_NOT_RECONCILED" in verdict["evidenceGaps"]
    assert verdict["mergeAuthorized"] is False
    # The newly required gate is arbitrated, so it is not silently skipped.
    assert "audit" in verdict["arbitratedGates"]
    assert "audit" in verdict["observedRequiredGates"]


def test_observed_required_gate_contract_reconciled_allows_merge_candidate() -> None:
    """When the live contract matches the plan and all receipts exist, merge proceeds."""
    selected, assignment = _full_verdict_setup("task-reconciled", required_gates=("unit", "lint"))
    receipts = [
        {"gate": "unit", "status": "success", "headSha": HEAD},
        {"gate": "lint", "status": "success", "headSha": HEAD},
    ]

    verdict = evaluate_fleet_verdict(
        selected,
        assignment=assignment,
        observed_base_revision=BASE,
        observed_head_revision=HEAD,
        workspace_head_revision=HEAD,
        check_receipts=receipts,
        review_receipts=_green_reviews(),
        cross_task_receipts=_green_cross(),
        observed_required_gates=("unit", "lint"),
    )

    assert verdict["status"] == "MERGE_CANDIDATE"
    assert verdict["gateContractDrift"] is False
    assert verdict["mergeAuthorized"] is False


def test_newly_required_gate_without_receipt_waits_for_evidence() -> None:
    """A gate newly required by the live contract, with no receipt, blocks as waiting."""
    selected, assignment = _full_verdict_setup("task-new-gate", required_gates=("unit",))

    verdict = evaluate_fleet_verdict(
        selected,
        assignment=assignment,
        observed_base_revision=BASE,
        observed_head_revision=HEAD,
        workspace_head_revision=HEAD,
        check_receipts=[{"gate": "unit", "status": "success", "headSha": HEAD}],
        observed_required_gates=("unit", "audit"),
    )

    assert verdict["status"] == "CI_WAITING"
    assert "CHECK_MISSING:audit" in verdict["evidenceGaps"]
    assert verdict["gateContractDrift"] is True
    assert "audit" in verdict["arbitratedGates"]


def test_no_observed_contract_falls_back_to_planned_gates() -> None:
    """Without a read-back contract the verdict arbitrates only over planned gates."""
    selected, assignment = _full_verdict_setup("task-no-readback", required_gates=("unit",))

    verdict = evaluate_fleet_verdict(
        selected,
        assignment=assignment,
        observed_base_revision=BASE,
        observed_head_revision=HEAD,
        workspace_head_revision=HEAD,
        check_receipts=[{"gate": "unit", "status": "success", "headSha": HEAD}],
    )

    assert verdict["gateContractDrift"] is False
    assert verdict["arbitratedGates"] == ["unit"]
    assert verdict["observedRequiredGates"] == []
