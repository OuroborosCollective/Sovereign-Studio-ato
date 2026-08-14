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
    WORKER_EVENT_TYPES,
    WORKER_LIFECYCLE_STATES,
    build_fleet_plan,
    build_fleet_projection,
    create_worker_assignment,
    evaluate_fleet_verdict,
    pair_conflicts,
    transition_worker_lifecycle,
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


def _assignment() -> object:
    plan = build_fleet_plan(
        integration_id="fleet-events",
        repository="OuroborosCollective/Sovereign-Studio-ato",
        base_revision=BASE,
        tasks=[task("task-events", expected_head_revision=HEAD)],
    )
    return create_worker_assignment(
        plan,
        lane_id="lane-01",
        task_id="task-events",
        controller_run_id="run-events",
        workspace_id="job-events",
        workspace_branch="sovereign/chatgpt/worker",
        run_envelope_hash=RECEIPT,
        capability_manifest_hash=RECEIPT,
    )


def test_full_worker_event_vocabulary_is_accepted_and_neutral() -> None:
    assignment = _assignment()
    for event_type in WORKER_EVENT_TYPES:
        event = validate_worker_event(
            assignment,
            event_type=event_type,
            summary=f"event {event_type}",
        )
        assert event["eventType"] == event_type
        assert "VERIFIED" not in event["status"] or event["status"] == "COMPLETED_UNVERIFIED"


def test_worker_event_rejects_verification_and_authoritative_claims() -> None:
    assignment = _assignment()
    for forbidden in ("WORKER_RUNTIME_VERIFIED", "WORKER_VERIFIED", "MERGED", "DEPLOYED"):
        with pytest.raises(FleetContractError):
            validate_worker_event(assignment, event_type=forbidden, summary="must be rejected")


def test_worker_event_binds_sequence_base_head_and_predecessor() -> None:
    assignment = _assignment()
    event = validate_worker_event(
        assignment,
        event_type="WORKSPACE_BOUND",
        summary="worker bound to prepared workspace",
        evidence_refs=[RECEIPT],
        sequence=3,
        base_revision=BASE,
        head_revision=HEAD,
        predecessor_hash=RECEIPT,
    )
    assert event["sequence"] == 3
    assert event["baseRevision"] == BASE
    assert event["headRevision"] == HEAD
    assert event["predecessorHash"] == RECEIPT


def test_worker_event_hash_chains_predecessor_and_sequence() -> None:
    assignment = _assignment()
    first = validate_worker_event(
        assignment,
        event_type="WORKER_STARTED",
        summary="started",
        sequence=1,
        base_revision=BASE,
    )
    second = validate_worker_event(
        assignment,
        event_type="WORKSPACE_BOUND",
        summary="bound",
        sequence=2,
        base_revision=BASE,
        predecessor_hash=first["eventHash"],
    )
    # Changing the predecessor must change the chained event hash (tamper-evident stream).
    tampered = validate_worker_event(
        assignment,
        event_type="WORKSPACE_BOUND",
        summary="bound",
        sequence=2,
        base_revision=BASE,
        predecessor_hash=RECEIPT,
    )
    assert second["eventHash"] != tampered["eventHash"]
    assert second["predecessorHash"] == first["eventHash"]


def test_worker_event_rejects_bad_sequence_and_revisions() -> None:
    assignment = _assignment()
    for bad_sequence in (-1, "1", True, 1.0):
        with pytest.raises(FleetContractError):
            validate_worker_event(assignment, event_type="WORKER_STARTED", summary="s", sequence=bad_sequence)
    for bad_revision in ("short", "z" * 41):
        with pytest.raises(FleetContractError):
            validate_worker_event(assignment, event_type="WORKER_STARTED", summary="s", base_revision=bad_revision)


def test_worker_event_keeps_legacy_caller_identity_when_no_binding_supplied() -> None:
    assignment = _assignment()
    legacy = validate_worker_event(
        assignment,
        event_type="WORKER_COMPLETED_UNVERIFIED",
        summary="legacy minimal call",
        evidence_refs=[RECEIPT],
    )
    assert legacy["status"] == "COMPLETED_UNVERIFIED"
    assert "sequence" not in legacy
    assert "baseRevision" not in legacy
    assert "predecessorHash" not in legacy


def test_lifecycle_transitions_follow_the_planned_path() -> None:
    assert transition_worker_lifecycle("PLANNED", "WORKER_READY") == "READY"
    assert transition_worker_lifecycle("READY", "WORKER_STARTED") == "RUNNING"
    assert transition_worker_lifecycle("RUNNING", "PR_READY_UNVERIFIED") == "VERIFYING"
    assert transition_worker_lifecycle("VERIFYING", "WORKER_COMPLETED_UNVERIFIED") == "COMPLETED_UNVERIFIED"


def test_lifecycle_rejects_illegal_and_authoritative_transitions() -> None:
    # Cannot skip straight to completion/verification.
    with pytest.raises(FleetContractError):
        transition_worker_lifecycle("PLANNED", "WORKER_COMPLETED_UNVERIFIED")
    with pytest.raises(FleetContractError):
        transition_worker_lifecycle("READY", "PR_READY_UNVERIFIED")
    # No event can reach a verified/merged state.
    for state in WORKER_LIFECYCLE_STATES:
        with pytest.raises(FleetContractError):
            transition_worker_lifecycle(state, "WORKER_RUNTIME_VERIFIED")
    # Terminal states admit no further transition.
    with pytest.raises(FleetContractError):
        transition_worker_lifecycle("COMPLETED_UNVERIFIED", "WORKER_READY")
    with pytest.raises(FleetContractError):
        transition_worker_lifecycle("FAILED", "WORKER_STARTED")
    # Unknown state and event.
    with pytest.raises(FleetContractError):
        transition_worker_lifecycle("RUNTIME_VERIFIED", "WORKER_STARTED")
    with pytest.raises(FleetContractError):
        transition_worker_lifecycle("RUNNING", "TOTALLY_MADE_UP")


def test_lifecycle_side_effect_events_only_allowed_while_running() -> None:
    assert transition_worker_lifecycle("RUNNING", "PATCH_PREPARED") == "RUNNING"
    assert transition_worker_lifecycle("RUNNING", "TEST_RESULT_RECORDED") == "RUNNING"
    assert transition_worker_lifecycle("RUNNING", "EVIDENCE_REFERENCE_ADDED") == "RUNNING"
    with pytest.raises(FleetContractError):
        transition_worker_lifecycle("READY", "PATCH_PREPARED")
    with pytest.raises(FleetContractError):
        transition_worker_lifecycle("ASSIGNED", "EVIDENCE_REFERENCE_ADDED")
