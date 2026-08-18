from __future__ import annotations

from pathlib import Path
import sys

import pytest

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from agent_runtime.fleet_attempts import create_worker_attempt, validate_active_worker_event
from agent_runtime.fleet_supervisor import FleetContractError, FleetTask, build_fleet_plan, create_worker_assignment

BASE = "a" * 40
HEAD = "b" * 40
RECEIPT = "c" * 64


def _assignment() -> object:
    task = FleetTask(
        task_id="task-secret-guard",
        source_type="issue",
        source_id="1522",
        expected_base_revision=BASE,
        expected_head_revision=HEAD,
        independence_proven=True,
    )
    plan = build_fleet_plan(
        integration_id="fleet-secret-guard",
        repository="OuroborosCollective/Sovereign-Studio-ato",
        base_revision=BASE,
        tasks=[task],
    )
    return create_worker_assignment(
        plan,
        lane_id="lane-01",
        task_id="task-secret-guard",
        controller_run_id="run-secret-guard",
        workspace_id="job-secret-guard",
        workspace_branch="sovereign/fleet-secret-guard",
        run_envelope_hash=RECEIPT,
        capability_manifest_hash=RECEIPT,
    )


def test_heartbeat_rejects_secret_shaped_summary() -> None:
    selected = _assignment()
    attempt = create_worker_attempt(selected, attempt_sequence=1)
    with pytest.raises(FleetContractError, match="secret-shaped"):
        validate_active_worker_event(
            selected,
            attempt,
            attempt,
            event_type="WORKER_HEARTBEAT",
            summary="authorization: bearer must-never-be-persisted",
        )
