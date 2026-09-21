from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from backend.agent_runtime.causal_progress_lease import CausalProgressReceiptV1  # noqa: E402
from backend.agent_runtime.durable_workflow import (  # noqa: E402
    PermissionDecision,
    StepKind,
    WorkflowBinding,
    WorkflowDefinition,
    WorkflowState,
    WorkflowStep,
    approve_permission,
    canonical_sha256,
    create_permission_request,
)
from backend.agent_runtime.revocation_closure import (  # noqa: E402
    PermissionAuthorityHead,
    RevocationClosureError,
    RevocationClosureVerdict,
    create_revocation_transition,
    evaluate_closure,
    require_live_permission,
)


def _approved():
    step = WorkflowStep(
        step_id="repository-a2a-submit",
        kind=StepKind.TOOL_MUTATION,
        allowed_from=(WorkflowState.READY,),
        allowed_to=(WorkflowState.RUNNING,),
        permission_required=True,
        capability="repository.external-submit",
        timeout_seconds=300,
        max_attempts=2,
        idempotency_key="repository-submit:test",
        required_readback_kinds=("agent_zero_a2a_task",),
    )
    definition = WorkflowDefinition.create(workflow_id="repository-test", steps=(step,))
    binding = WorkflowBinding(
        workflow_run_id="repo-run-agent-test",
        workflow_definition_hash=definition.definition_hash,
        owner_identity="owner-test",
        tenant_or_org_identity="owner-test",
        repository_identity="https://github.com/OuroborosCollective/Sovereign-Studio-ato",
        workspace_id="agent-test",
        base_revision="1" * 40,
        head_revision="1" * 40,
    )
    requested = create_permission_request(
        binding=binding,
        definition=definition,
        step_id=step.step_id,
        tool_name="agent-zero-a2a-submit",
        parameters={"job_id": "agent-test"},
        expected_changed_paths=(),
        valid_until_epoch=5000,
        max_attempts=2,
    )
    return approve_permission(
        requested,
        approver_identity="owner-test",
        approval_source="unit-test",
        observed_epoch=1000,
    )


def _head(receipt, sequence):
    payload = {
        "permission_id": receipt.permission_id,
        "workflow_run_id": receipt.binding.workflow_run_id,
        "receipt_hash": receipt.receipt_hash,
        "receipt_sequence": sequence,
        "decision": receipt.decision.value,
    }
    return PermissionAuthorityHead(
        permission_id=receipt.permission_id,
        workflow_run_id=receipt.binding.workflow_run_id,
        receipt_hash=receipt.receipt_hash,
        receipt_sequence=sequence,
        decision=receipt.decision,
        readback_hash=canonical_sha256(payload),
    )


def test_newer_revoked_head_invalidates_approved_effect_authority():
    approved = _approved()
    revoked_permission, revocation = create_revocation_transition(
        approved,
        revocation_sequence=2,
        revocation_epoch_ms=2000,
        reason_code="OWNER_REVOKED",
        revoker_identity="owner-test",
    )
    with pytest.raises(RevocationClosureError):
        require_live_permission(approved, _head(revoked_permission, 2))
    assert revocation.predecessor_receipt_hash == approved.receipt_hash
    assert revocation.revoked_permission_receipt_hash == revoked_permission.receipt_hash


def test_live_approved_head_is_authoritative():
    approved = _approved()
    head = _head(approved, 1)
    assert require_live_permission(approved, head) == head


def test_closure_is_partial_when_effect_paths_are_uncovered():
    approved = _approved()
    revoked_permission, revocation = create_revocation_transition(
        approved,
        revocation_sequence=2,
        revocation_epoch_ms=2000,
        reason_code="OWNER_REVOKED",
        revoker_identity="owner-test",
    )
    receipt = evaluate_closure(
        revocation=revocation,
        head=_head(revoked_permission, 2),
        affected_job_ids=("agent-test",),
        affected_effect_paths=("repository-submit",),
        uncovered_effect_paths=("remote-agent-termination",),
    )
    assert receipt.verdict == RevocationClosureVerdict.REVOCATION_PARTIAL
    assert receipt.verify()


def test_scpl_progress_after_revocation_blocks_closed_verified():
    approved = _approved()
    revoked_permission, revocation = create_revocation_transition(
        approved,
        revocation_sequence=2,
        revocation_epoch_ms=2000,
        reason_code="OWNER_REVOKED",
        revoker_identity="owner-test",
    )
    progress = CausalProgressReceiptV1.build(
        job_id="agent-test",
        workspace_id="agent-test",
        a2a_task_id="task-1",
        repository=approved.binding.repository_identity,
        repository_revision=approved.binding.base_revision,
        progress_kind="WORKSPACE_DELTA",
        previous_workspace_readback_sha256="a" * 64,
        current_workspace_readback_sha256="b" * 64,
        previous_receipt_sha256="c" * 64,
        observed_epoch_ms=2001,
    )
    receipt = evaluate_closure(
        revocation=revocation,
        head=_head(revoked_permission, 2),
        progress_receipts=(progress.to_dict(),),
        affected_job_ids=("agent-test",),
        affected_effect_paths=("repository-submit",),
    )
    assert receipt.verdict == RevocationClosureVerdict.POST_REVOCATION_EFFECT_OBSERVED


def test_scpl_progress_before_revocation_allows_local_closed_verdict():
    approved = _approved()
    progress = CausalProgressReceiptV1.build(
        job_id="agent-test",
        workspace_id="agent-test",
        a2a_task_id="task-1",
        repository=approved.binding.repository_identity,
        repository_revision=approved.binding.base_revision,
        progress_kind="WORKSPACE_DELTA",
        previous_workspace_readback_sha256="a" * 64,
        current_workspace_readback_sha256="b" * 64,
        previous_receipt_sha256="c" * 64,
        observed_epoch_ms=1999,
    )
    revoked_permission, revocation = create_revocation_transition(
        approved,
        revocation_sequence=2,
        revocation_epoch_ms=2000,
        reason_code="OWNER_REVOKED",
        revoker_identity="owner-test",
        progress_head_sha256=progress.receipt_sha256,
    )
    receipt = evaluate_closure(
        revocation=revocation,
        head=_head(revoked_permission, 2),
        progress_receipts=(progress.to_dict(),),
        affected_job_ids=("agent-test",),
        affected_effect_paths=("repository-submit",),
    )
    assert receipt.verdict == RevocationClosureVerdict.REVOCATION_CLOSED_VERIFIED
