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


# --- Fleet 4/4: status projection extension (#1309) --------------------------------


def _verdict_plan_and_assignment(*, required_gates=("unit", "lint")):
    selected = task(
        "task-proj",
        expected_head_revision=HEAD,
        required_gates=tuple(required_gates),
    )
    plan = build_fleet_plan(
        integration_id="fleet-projection-1309",
        repository="OuroborosCollective/Sovereign-Studio-ato",
        base_revision=BASE,
        tasks=[selected],
    )
    assignment = create_worker_assignment(
        plan,
        lane_id="lane-01",
        task_id="task-proj",
        controller_run_id="run-proj",
        workspace_id="job-proj",
        workspace_branch="sovereign/chatgpt/proj",
        run_envelope_hash=RECEIPT,
        capability_manifest_hash=RECEIPT,
    )
    return selected, plan, assignment


def test_projection_surfaces_verdict_gates_blockers_and_aggregate_counts() -> None:
    selected, plan, assignment = _verdict_plan_and_assignment()
    verdict = evaluate_fleet_verdict(
        selected,
        assignment=assignment,
        observed_base_revision=BASE,
        observed_head_revision=HEAD,
        workspace_head_revision=HEAD,
        check_receipts=[{"gate": "unit", "status": "success", "headSha": HEAD}],
    )
    assert verdict["status"] == "CI_WAITING"

    projection = build_fleet_projection(
        plan,
        assignments=[assignment.to_dict()],
        verdicts=[verdict],
        observed_main_revision=BASE,
    )

    assert projection["schemaVersion"] == "sovereign.fleet.v1"
    assert projection["readOnly"] is True
    assert projection["mutationPerformed"] is False
    assert projection["stale"] is False
    assert projection["commandsBlocked"] is False
    assert projection["integrationId"] == "fleet-projection-1309"
    assert projection["repository"] == "OuroborosCollective/Sovereign-Studio-ato"

    task_state = projection["tasks"][0]
    assert task_state["verdictStatus"] == "CI_WAITING"
    # arbitrated required gates surfaced (unit satisfied, lint still missing)
    assert "unit" in task_state["requiredGates"]
    assert "lint" in task_state["requiredGates"]
    assert "lint" in task_state["missingGates"]
    assert "CHECK_MISSING:lint" in projection["evidenceGaps"]

    lane = projection["lanes"][0]
    assert lane["status"] == "ACTIVE"
    assert lane["fleetVerdict"] == "CI_WAITING"
    assert "lint" in lane["missingGates"]

    counts = projection["aggregateCounts"]
    assert counts["lanes"] == 1
    assert counts["tasks"] == 1
    assert counts["missingEvidence"] == len(projection["evidenceGaps"])
    assert counts["blocked"] == 0

    # projection is rebuildable and hash-bound to its source receipt
    assert projection["projectionBuiltFromReceiptHashes"] == [verdict["verdictHash"]]
    rebuilt = build_fleet_projection(
        plan,
        assignments=[assignment.to_dict()],
        verdicts=[verdict],
        observed_main_revision=BASE,
    )
    assert rebuilt["projectionHash"] == projection["projectionHash"]


def test_projection_surfaces_blocker_codes_and_blocks_lane_without_overblocking_fleet() -> None:
    selected, plan, assignment = _verdict_plan_and_assignment()
    # Drift observed base -> BLOCKED_BASE_DRIFT with a blocker gap code
    verdict = evaluate_fleet_verdict(
        selected,
        assignment=assignment,
        observed_base_revision=HEAD,
        observed_head_revision=HEAD,
        workspace_head_revision=HEAD,
    )
    assert verdict["status"] == "BLOCKED_BASE_DRIFT"

    projection = build_fleet_projection(
        plan,
        assignments=[assignment.to_dict()],
        verdicts=[verdict],
        observed_main_revision=BASE,
    )

    task_state = projection["tasks"][0]
    assert task_state["verdictStatus"] == "BLOCKED_BASE_DRIFT"
    assert "BLOCKED_BASE_DRIFT" in task_state["blockerCodes"]
    assert "EXACT_BASE_MISMATCH" in task_state["blockerCodes"]

    lane = projection["lanes"][0]
    assert lane["status"] == "BLOCKED"
    assert "BLOCKED_BASE_DRIFT" in lane["blockerCodes"]

    assert "BLOCKED_BASE_DRIFT" in projection["activeBlockers"]
    assert projection["aggregateCounts"]["blocked"] == 1

    # A single lane's contradiction must NOT over-block the whole fleet: main head still
    # matches the plan base, so fleet-wide commands stay eligible.
    assert projection["stale"] is False
    assert projection["commandsBlocked"] is False
    assert projection["status"] == "FLEET_PROJECTED"


def test_projection_collects_verdict_contradictions() -> None:
    selected, plan, assignment = _verdict_plan_and_assignment()
    # Both required gates pass, but the independent review is not proven exact
    # (receipt hash is malformed) -> CONTRADICTED with a contradiction code.
    verdict = evaluate_fleet_verdict(
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
            "reviewerId": "reviewer-bad",
            "independent": True,
            "status": "approved",
            "headSha": HEAD,
            "receiptSha256": "not-a-valid-hash",
        }],
    )
    assert verdict["status"] == "CONTRADICTED"
    assert "INDEPENDENT_REVIEW_NOT_EXACT_OR_NOT_PROVEN" in verdict["contradictions"]

    projection = build_fleet_projection(
        plan,
        assignments=[assignment.to_dict()],
        verdicts=[verdict],
        observed_main_revision=BASE,
    )

    assert projection["aggregateCounts"]["contradicted"] == 1
    assert projection["contradictions"] == verdict["contradictions"]
    assert projection["tasks"][0]["verdictStatus"] == "CONTRADICTED"
    # CONTRADICTED blocks its lane
    assert projection["lanes"][0]["status"] == "BLOCKED"
    # but does not stale the whole fleet while main head still matches base
    assert projection["stale"] is False


def test_projection_is_deterministic_across_dict_and_object_inputs() -> None:
    selected, plan, assignment = _verdict_plan_and_assignment()
    verdict = evaluate_fleet_verdict(
        selected,
        assignment=assignment,
        observed_base_revision=BASE,
        observed_head_revision=HEAD,
        workspace_head_revision=HEAD,
        check_receipts=[{"gate": "unit", "status": "success", "headSha": HEAD}],
    )

    from_object = build_fleet_projection(
        plan,
        assignments=[assignment.to_dict()],
        verdicts=[verdict],
        observed_main_revision=BASE,
    )
    from_dict = build_fleet_projection(
        plan.to_dict(),
        assignments=[assignment.to_dict()],
        verdicts=[verdict],
        observed_main_revision=BASE,
    )
    assert from_object == from_dict
    assert from_object["planHash"] == plan.plan_hash
    assert from_object["projectionHash"] == from_dict["projectionHash"]
