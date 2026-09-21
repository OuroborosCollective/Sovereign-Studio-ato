from agent_runtime.causal_progress_lease import (
    CausalProgressContractError,
    CausalProgressLeaseV1,
    CausalProgressReceiptV1,
)


REV_A = "a" * 40
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def test_progress_receipt_is_deterministic_and_predecessor_bound():
    left = CausalProgressReceiptV1.build(
        job_id="job-1",
        workspace_id="workspace-1",
        a2a_task_id="task-1",
        repository="OuroborosCollective/Sovereign-Studio-ato",
        repository_revision=REV_A,
        progress_kind="WORKSPACE_DELTA",
        previous_workspace_readback_sha256=SHA_B,
        current_workspace_readback_sha256=SHA_C,
        previous_receipt_sha256=SHA_A,
        observed_epoch_ms=1_000,
    )
    right = CausalProgressReceiptV1.from_dict(left.to_dict())
    assert right == left
    changed = CausalProgressReceiptV1.build(
        job_id="job-1",
        workspace_id="workspace-1",
        a2a_task_id="task-1",
        repository="OuroborosCollective/Sovereign-Studio-ato",
        repository_revision=REV_A,
        progress_kind="WORKSPACE_DELTA",
        previous_workspace_readback_sha256=SHA_B,
        current_workspace_readback_sha256=SHA_C,
        previous_receipt_sha256=SHA_B,
        observed_epoch_ms=1_000,
    )
    assert changed.receipt_sha256 != left.receipt_sha256


def test_progress_receipt_rejects_tampered_hash():
    receipt = CausalProgressReceiptV1.build(
        job_id="job-1",
        workspace_id="workspace-1",
        a2a_task_id="task-1",
        repository="repo",
        repository_revision=REV_A,
        progress_kind="REPOSITORY_MATERIALIZED",
        previous_workspace_readback_sha256="",
        current_workspace_readback_sha256=SHA_B,
        observed_epoch_ms=1,
    )
    raw = receipt.to_dict()
    raw["receiptSha256"] = SHA_C
    try:
        CausalProgressReceiptV1.from_dict(raw)
    except CausalProgressContractError:
        pass
    else:
        raise AssertionError("tampered receipt must fail closed")


def test_lease_requires_recent_material_progress_not_heartbeat():
    lease = CausalProgressLeaseV1.evaluate(
        job_id="job-1",
        a2a_task_id="task-1",
        source_revision=REV_A,
        last_progress_receipt_sha256=SHA_B,
        last_material_progress_epoch_ms=10_000,
        max_no_progress_seconds=30,
        absolute_deadline_epoch_ms=120_000,
        observed_epoch_ms=20_000,
    )
    assert lease.verdict == "CONTINUE_VERIFIED"

    stale = CausalProgressLeaseV1.evaluate(
        job_id="job-1",
        a2a_task_id="task-1",
        source_revision=REV_A,
        last_progress_receipt_sha256=SHA_B,
        last_material_progress_epoch_ms=10_000,
        max_no_progress_seconds=30,
        absolute_deadline_epoch_ms=120_000,
        observed_epoch_ms=40_000,
    )
    assert stale.verdict == "STALLED"


def test_lease_absolute_deadline_wins_even_with_recent_progress():
    lease = CausalProgressLeaseV1.evaluate(
        job_id="job-1",
        a2a_task_id="task-1",
        source_revision=REV_A,
        last_progress_receipt_sha256=SHA_B,
        last_material_progress_epoch_ms=99_999,
        max_no_progress_seconds=30,
        absolute_deadline_epoch_ms=100_000,
        observed_epoch_ms=100_000,
    )
    assert lease.verdict == "STALLED"
    assert "absolute" in lease.reason


def test_lease_missing_or_contradicted_evidence_never_goes_green():
    missing = CausalProgressLeaseV1.evaluate(
        job_id="job-1",
        a2a_task_id="task-1",
        source_revision=REV_A,
        last_progress_receipt_sha256="",
        last_material_progress_epoch_ms=0,
        max_no_progress_seconds=30,
        absolute_deadline_epoch_ms=100_000,
        observed_epoch_ms=1_000,
        evidence_available=False,
    )
    assert missing.verdict == "UNVERIFIED"

    contradicted = CausalProgressLeaseV1.evaluate(
        job_id="job-1",
        a2a_task_id="task-1",
        source_revision=REV_A,
        last_progress_receipt_sha256=SHA_B,
        last_material_progress_epoch_ms=1,
        max_no_progress_seconds=30,
        absolute_deadline_epoch_ms=100_000,
        observed_epoch_ms=2,
        contradicted=True,
    )
    assert contradicted.verdict == "CONTRADICTED"


def test_progress_receipt_rejects_non_git_repository_revision():
    try:
        CausalProgressReceiptV1.build(
            job_id="job-1", workspace_id="workspace-1", a2a_task_id="task-1",
            repository="repo", repository_revision=SHA_A,
            progress_kind="REPOSITORY_MATERIALIZED",
            previous_workspace_readback_sha256="",
            current_workspace_readback_sha256=SHA_B,
            observed_epoch_ms=1,
        )
    except CausalProgressContractError:
        pass
    else:
        raise AssertionError("progress receipts must bind a full Git SHA, not an arbitrary digest")


def test_future_progress_epoch_is_contradicted():
    lease = CausalProgressLeaseV1.evaluate(
        job_id="job-1", a2a_task_id="task-1", source_revision=REV_A,
        last_progress_receipt_sha256=SHA_B,
        last_material_progress_epoch_ms=20_000,
        max_no_progress_seconds=30,
        absolute_deadline_epoch_ms=100_000,
        observed_epoch_ms=10_000,
    )
    assert lease.verdict == "CONTRADICTED"
