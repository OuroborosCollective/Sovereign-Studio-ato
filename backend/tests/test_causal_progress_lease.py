from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.agent_run_receipts import ReceiptContractError  # noqa: E402
from agent_runtime.causal_progress_lease import (  # noqa: E402
    ZERO_SHA256,
    assess_causal_progress_lease,
    build_causal_progress_receipt,
    validate_causal_progress_chain,
    workspace_readback_is_new,
)


REVISION = "a" * 40
H1 = "1" * 64
H2 = "2" * 64
H3 = "3" * 64


def _baseline(*, current: str = H1):
    return build_causal_progress_receipt(
        sequence=0,
        job_id="job-1",
        workspace_id="workspace-1",
        a2a_task_id="task-1",
        repository="https://github.com/OuroborosCollective/Sovereign-Studio-ato",
        repository_revision=REVISION,
        progress_kind="REPOSITORY_MATERIALIZED",
        previous_workspace_readback_sha256=ZERO_SHA256,
        current_workspace_readback_sha256=current,
        previous_receipt_sha256=ZERO_SHA256,
    )


def _delta(previous, *, current: str = H2):
    return build_causal_progress_receipt(
        sequence=previous.sequence + 1,
        job_id=previous.job_id,
        workspace_id=previous.workspace_id,
        a2a_task_id=previous.a2a_task_id,
        repository=previous.repository,
        repository_revision=previous.repository_revision,
        progress_kind="WORKSPACE_DELTA",
        previous_workspace_readback_sha256=previous.current_workspace_readback_sha256,
        current_workspace_readback_sha256=current,
        previous_receipt_sha256=previous.receipt_sha256,
    )


def test_receipt_hash_is_deterministic_and_chain_is_predecessor_bound():
    first = _baseline()
    second = _delta(first)

    replay = _baseline()
    assert replay.receipt_sha256 == first.receipt_sha256
    assert validate_causal_progress_chain((first.to_dict(), second.to_dict())) == (first, second)


def test_identical_workspace_state_is_not_new_progress():
    first = _baseline()

    with pytest.raises(ReceiptContractError, match="identical workspace state"):
        build_causal_progress_receipt(
            sequence=1,
            job_id=first.job_id,
            workspace_id=first.workspace_id,
            a2a_task_id=first.a2a_task_id,
            repository=first.repository,
            repository_revision=first.repository_revision,
            progress_kind="WORKSPACE_DELTA",
            previous_workspace_readback_sha256=first.current_workspace_readback_sha256,
            current_workspace_readback_sha256=first.current_workspace_readback_sha256,
            previous_receipt_sha256=first.receipt_sha256,
        )


def test_previously_seen_workspace_state_cannot_renew_after_oscillation():
    first = _baseline()
    second = _delta(first)

    assert workspace_readback_is_new(H3, (first, second)) is True
    assert workspace_readback_is_new(H1, (first, second)) is False


def test_chain_rejects_validly_hashed_but_wrong_predecessor():
    first = _baseline()
    second = build_causal_progress_receipt(
        sequence=1,
        job_id=first.job_id,
        workspace_id=first.workspace_id,
        a2a_task_id=first.a2a_task_id,
        repository=first.repository,
        repository_revision=first.repository_revision,
        progress_kind="WORKSPACE_DELTA",
        previous_workspace_readback_sha256=first.current_workspace_readback_sha256,
        current_workspace_readback_sha256=H2,
        previous_receipt_sha256="9" * 64,
    )

    with pytest.raises(ReceiptContractError, match="predecessor receipt mismatch"):
        validate_causal_progress_chain((first, second))


def test_chain_rejects_binding_change():
    first = _baseline()
    second = build_causal_progress_receipt(
        sequence=1,
        job_id=first.job_id,
        workspace_id=first.workspace_id,
        a2a_task_id="task-other",
        repository=first.repository,
        repository_revision=first.repository_revision,
        progress_kind="WORKSPACE_DELTA",
        previous_workspace_readback_sha256=first.current_workspace_readback_sha256,
        current_workspace_readback_sha256=H2,
        previous_receipt_sha256=first.receipt_sha256,
    )

    with pytest.raises(ReceiptContractError, match="binding changed"):
        validate_causal_progress_chain((first, second))


def test_no_progress_inside_lease_does_not_claim_verified_progress():
    decision = assess_causal_progress_lease(
        now_epoch_ms=100_000,
        started_epoch_ms=0,
        last_material_progress_epoch_ms=0,
        max_no_progress_seconds=300,
        absolute_deadline_seconds=3600,
        material_progress_observed=False,
    )

    assert decision.verdict == "NO_PROGRESS"


def test_material_progress_can_continue_within_absolute_deadline():
    decision = assess_causal_progress_lease(
        now_epoch_ms=400_000,
        started_epoch_ms=0,
        last_material_progress_epoch_ms=390_000,
        max_no_progress_seconds=300,
        absolute_deadline_seconds=3600,
        material_progress_observed=True,
    )

    assert decision.verdict == "CONTINUE_VERIFIED"


def test_no_progress_lease_expires_even_if_remote_task_is_still_live():
    decision = assess_causal_progress_lease(
        now_epoch_ms=301_000,
        started_epoch_ms=0,
        last_material_progress_epoch_ms=0,
        max_no_progress_seconds=300,
        absolute_deadline_seconds=3600,
        material_progress_observed=False,
    )

    assert decision.verdict == "STALLED"
    assert "no new material" in decision.reason


def test_absolute_deadline_cannot_be_extended_by_fresh_progress():
    decision = assess_causal_progress_lease(
        now_epoch_ms=3_600_000,
        started_epoch_ms=0,
        last_material_progress_epoch_ms=3_599_000,
        max_no_progress_seconds=300,
        absolute_deadline_seconds=3600,
        material_progress_observed=True,
    )

    assert decision.verdict == "STALLED"
    assert "absolute" in decision.reason
