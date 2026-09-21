from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.causal_progress_lease import (  # noqa: E402
    CausalProgressContractError,
    CausalProgressLeaseV1,
    CausalProgressReceiptV1,
    latest_progress_receipt,
    seen_workspace_readbacks,
)


def _receipt(*, current: str, previous_workspace: str = "", previous_receipt: str = "", at: int = 1_000):
    return CausalProgressReceiptV1.build(
        job_id="job-1",
        workspace_id="workspace-1",
        a2a_task_id="task-1",
        repository="https://github.com/OuroborosCollective/Sovereign-Studio-ato",
        repository_revision="a" * 40,
        progress_kind="WORKSPACE_DELTA",
        previous_workspace_readback_sha256=previous_workspace,
        current_workspace_readback_sha256=current,
        previous_receipt_sha256=previous_receipt,
        observed_at_epoch_ms=at,
    )


def test_progress_receipt_is_deterministic_and_predecessor_bound():
    first = _receipt(current="1" * 64)
    same = _receipt(current="1" * 64)
    second = _receipt(
        current="2" * 64,
        previous_workspace=first.current_workspace_readback_sha256,
        previous_receipt=first.receipt_sha256,
        at=2_000,
    )
    assert first.receipt_sha256 == same.receipt_sha256
    assert second.receipt_sha256 != first.receipt_sha256
    assert latest_progress_receipt(
        (first, second),
        job_id="job-1",
        workspace_id="workspace-1",
        a2a_task_id="task-1",
        repository_revision="a" * 40,
    ) == second


def test_identical_workspace_state_cannot_renew_progress():
    try:
        _receipt(current="1" * 64, previous_workspace="1" * 64)
    except CausalProgressContractError as exc:
        assert "not material progress" in str(exc)
    else:
        raise AssertionError("identical workspace state must not renew SCPL")


def test_seen_workspace_states_prevent_oscillation_from_earning_new_progress():
    first = _receipt(current="1" * 64)
    second = _receipt(
        current="2" * 64,
        previous_workspace=first.current_workspace_readback_sha256,
        previous_receipt=first.receipt_sha256,
        at=2_000,
    )
    assert seen_workspace_readbacks((first, second)) == frozenset({"1" * 64, "2" * 64})


def test_lease_uses_material_progress_not_heartbeat_time():
    receipt = _receipt(current="1" * 64, at=10_000)
    lease = CausalProgressLeaseV1.evaluate(
        job_id="job-1",
        a2a_task_id="task-1",
        source_revision="a" * 40,
        latest_receipt=receipt,
        created_at_epoch_ms=0,
        observed_at_epoch_ms=309_999,
        max_no_progress_seconds=300,
        absolute_deadline_epoch_ms=10_000_000,
        readback_available=True,
    )
    assert lease.verdict == "CONTINUE_VERIFIED"

    stalled = CausalProgressLeaseV1.evaluate(
        job_id="job-1",
        a2a_task_id="task-1",
        source_revision="a" * 40,
        latest_receipt=receipt,
        created_at_epoch_ms=0,
        observed_at_epoch_ms=310_000,
        max_no_progress_seconds=300,
        absolute_deadline_epoch_ms=10_000_000,
        readback_available=True,
    )
    assert stalled.verdict == "NO_PROGRESS"


def test_absolute_deadline_cannot_be_renewed_by_progress():
    receipt = _receipt(current="1" * 64, at=9_900)
    lease = CausalProgressLeaseV1.evaluate(
        job_id="job-1",
        a2a_task_id="task-1",
        source_revision="a" * 40,
        latest_receipt=receipt,
        created_at_epoch_ms=0,
        observed_at_epoch_ms=10_000,
        max_no_progress_seconds=300,
        absolute_deadline_epoch_ms=10_000,
        readback_available=True,
    )
    assert lease.verdict == "STALLED"


def test_unavailable_material_readback_never_becomes_positive_progress():
    lease = CausalProgressLeaseV1.evaluate(
        job_id="job-1",
        a2a_task_id="task-1",
        source_revision="a" * 40,
        latest_receipt=None,
        created_at_epoch_ms=1_000,
        observed_at_epoch_ms=2_000,
        max_no_progress_seconds=300,
        absolute_deadline_epoch_ms=10_000,
        readback_available=False,
    )
    assert lease.verdict == "UNVERIFIED"
