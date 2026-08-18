from __future__ import annotations

from pathlib import Path
import sys

import pytest

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from agent_runtime.fleet_attempts import (
    ATTEMPT_SCHEMA_VERSION,
    FleetWorkerAttempt,
    create_worker_attempt,
    evidence_matches_active_attempt,
    require_active_attempt,
    validate_active_worker_event,
)
from agent_runtime.fleet_supervisor import (
    FleetContractError,
    FleetTask,
    build_fleet_plan,
    create_worker_assignment,
)


BASE = "a" * 40
HEAD = "b" * 40
RECEIPT = "c" * 64


def assignment(*, task_id: str = "task-attempt", run_id: str = "run-attempt") -> object:
    selected = FleetTask(
        task_id=task_id,
        source_type="issue",
        source_id="1522",
        expected_base_revision=BASE,
        expected_head_revision=HEAD,
        independence_proven=True,
    )
    plan = build_fleet_plan(
        integration_id="fleet-attempt-tests",
        repository="OuroborosCollective/Sovereign-Studio-ato",
        base_revision=BASE,
        architecture_receipt_hashes=[RECEIPT],
        tasks=[selected],
    )
    return create_worker_assignment(
        plan,
        lane_id="lane-01",
        task_id=task_id,
        controller_run_id=run_id,
        workspace_id="job-attempt",
        workspace_branch="sovereign/fleet-attempt",
        run_envelope_hash=RECEIPT,
        capability_manifest_hash=RECEIPT,
    )


def test_attempt_identity_is_deterministic_and_sequence_bound() -> None:
    selected = assignment()
    first = create_worker_attempt(selected, attempt_sequence=1)
    first_replay = create_worker_attempt(selected, attempt_sequence=1)
    second = create_worker_attempt(selected, attempt_sequence=2)

    assert first == first_replay
    assert first.attempt_id.startswith("attempt-")
    assert first.attempt_hash == first_replay.attempt_hash
    assert first.attempt_hash != second.attempt_hash
    assert first.attempt_id != second.attempt_id
    assert first.to_dict()["schemaVersion"] == ATTEMPT_SCHEMA_VERSION


def test_attempt_round_trip_rejects_hash_or_identity_tampering() -> None:
    first = create_worker_attempt(assignment(), attempt_sequence=1)
    assert FleetWorkerAttempt.from_dict(first.to_dict()) == first

    tampered = dict(first.to_dict())
    tampered["attemptSequence"] = 2
    with pytest.raises(FleetContractError, match="attempt hash"):
        FleetWorkerAttempt.from_dict(tampered)

    tampered_id = dict(first.to_dict())
    tampered_id["attemptId"] = "attempt-" + ("0" * 24)
    with pytest.raises(FleetContractError, match="attempt id"):
        FleetWorkerAttempt.from_dict(tampered_id)


@pytest.mark.parametrize("invalid", [0, -1, True, 1.5, "1"])
def test_attempt_sequence_is_positive_integer(invalid: object) -> None:
    with pytest.raises(FleetContractError, match="attempt_sequence"):
        create_worker_attempt(assignment(), attempt_sequence=invalid)  # type: ignore[arg-type]


def test_old_completion_cannot_advance_new_retry() -> None:
    selected = assignment()
    first = create_worker_attempt(selected, attempt_sequence=1)
    second = create_worker_attempt(selected, attempt_sequence=2)

    with pytest.raises(FleetContractError, match="stale worker attempt"):
        validate_active_worker_event(
            selected,
            first,
            second,
            event_type="WORKER_COMPLETED_UNVERIFIED",
            summary="late completion from superseded retry",
            evidence_refs=[RECEIPT],
        )

    event = validate_active_worker_event(
        selected,
        second,
        second,
        event_type="WORKER_COMPLETED_UNVERIFIED",
        summary="current attempt completion remains unverified",
        evidence_refs=[RECEIPT],
    )
    assert event["attemptId"] == second.attempt_id
    assert event["attemptSequence"] == 2
    assert event["status"] == "COMPLETED_UNVERIFIED"
    assert event["authoritative"] is False
    assert event["livenessOnly"] is False


def test_old_heartbeat_cannot_renew_new_retry() -> None:
    selected = assignment()
    first = create_worker_attempt(selected, attempt_sequence=1)
    second = create_worker_attempt(selected, attempt_sequence=2)

    with pytest.raises(FleetContractError, match="stale worker attempt"):
        validate_active_worker_event(
            selected,
            first,
            second,
            event_type="WORKER_HEARTBEAT",
            summary="late heartbeat",
            lifecycle_state="RUNNING",
        )

    heartbeat = validate_active_worker_event(
        selected,
        second,
        second,
        event_type="WORKER_HEARTBEAT",
        summary="active liveness pulse",
        lifecycle_state="RUNNING",
        sequence=7,
        base_revision=BASE,
        head_revision=HEAD,
    )
    assert heartbeat["eventType"] == "WORKER_HEARTBEAT"
    assert heartbeat["status"] == "RUNNING"
    assert heartbeat["livenessOnly"] is True
    assert heartbeat["authoritative"] is False
    assert heartbeat["evidenceRefs"] == []


@pytest.mark.parametrize("terminal_state", ["COMPLETED_UNVERIFIED", "FAILED"])
def test_heartbeat_is_rejected_after_terminal_lifecycle(terminal_state: str) -> None:
    selected = assignment()
    active = create_worker_attempt(selected, attempt_sequence=1)
    with pytest.raises(FleetContractError, match="active non-terminal"):
        validate_active_worker_event(
            selected,
            active,
            active,
            event_type="WORKER_HEARTBEAT",
            summary="must not revive terminal attempt",
            lifecycle_state=terminal_state,
        )


def test_wrong_assignment_or_future_attempt_is_rejected() -> None:
    selected = assignment(task_id="task-attempt")
    other = assignment(task_id="task-other", run_id="run-other")
    first = create_worker_attempt(selected, attempt_sequence=1)
    future = create_worker_attempt(selected, attempt_sequence=2)

    with pytest.raises(FleetContractError, match="supplied assignment"):
        require_active_attempt(first, first, other)
    with pytest.raises(FleetContractError, match="future worker attempt"):
        require_active_attempt(future, first, selected)


def test_attempt_one_evidence_cannot_satisfy_attempt_two() -> None:
    selected = assignment()
    first = create_worker_attempt(selected, attempt_sequence=1)
    second = create_worker_attempt(selected, attempt_sequence=2)
    receipt = {
        "attemptId": first.attempt_id,
        "attemptSequence": first.attempt_sequence,
        "attemptHash": first.attempt_hash,
        "assignmentHash": first.assignment_hash,
        "receiptSha256": RECEIPT,
    }

    assert evidence_matches_active_attempt(receipt, first) is True
    assert evidence_matches_active_attempt(receipt, second) is False
    assert evidence_matches_active_attempt({"receiptSha256": RECEIPT}, second) is False


def test_exact_event_replay_is_idempotent_by_hash() -> None:
    selected = assignment()
    active = create_worker_attempt(selected, attempt_sequence=1)
    kwargs = {
        "event_type": "TEST_RESULT_RECORDED",
        "summary": "bounded deterministic test evidence",
        "evidence_refs": [RECEIPT],
        "sequence": 4,
        "base_revision": BASE,
        "head_revision": HEAD,
    }
    left = validate_active_worker_event(selected, active, active, **kwargs)
    right = validate_active_worker_event(selected, active, active, **kwargs)

    assert left["eventId"] == right["eventId"]
    assert left["eventHash"] == right["eventHash"]


def test_worker_attempt_path_preserves_non_authority() -> None:
    selected = assignment()
    active = create_worker_attempt(selected, attempt_sequence=1)
    with pytest.raises(FleetContractError):
        validate_active_worker_event(
            selected,
            active,
            active,
            event_type="WORKER_RUNTIME_VERIFIED",
            summary="worker must never claim runtime truth",
        )


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".git").exists():
            return candidate
    raise AssertionError("repository root not found")


def test_attempt_persistence_migration_is_mirrored_and_indexed() -> None:
    root = _repo_root()
    canonical = root / "backend/migrations/054_fleet_worker_attempt_identity.sql"
    mirror = root / "scripts/sovereign-backend/migrations/054_fleet_worker_attempt_identity.sql"
    assert canonical.read_bytes() == mirror.read_bytes()
    sql = canonical.read_text(encoding="utf-8")

    for table in ("agent_events", "agent_tool_calls", "agent_evidence", "agent_failures", "agent_handoffs"):
        assert f"ALTER TABLE {table}" in sql
        assert f"idx_{table}_run_task_attempt" in sql
    assert "ADD COLUMN IF NOT EXISTS attempt_id TEXT" in sql
    assert "ADD COLUMN IF NOT EXISTS attempt_sequence INTEGER" in sql
    assert "ADD COLUMN IF NOT EXISTS attempt_hash CHAR(64)" in sql
    assert "ADD COLUMN IF NOT EXISTS assignment_hash CHAR(64)" in sql
    assert "Historical NULL attempt columns remain valid history" in sql
