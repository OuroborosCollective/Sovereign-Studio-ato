from __future__ import annotations

from pathlib import Path

import pytest

from backend.agent_runtime.durable_workflow import (
    CanonicalReadback,
    DurableWorkflowError,
    ExecutionVerdict,
    PermissionDecision,
    ReadbackVerdict,
    StepKind,
    WorkflowBinding,
    WorkflowDefinition,
    WorkflowSnapshot,
    WorkflowState,
    WorkflowStep,
    apply_canonical_readback,
    approve_permission,
    canonical_sha256,
    create_execution_receipt,
    create_permission_request,
    resume_snapshot,
)


REPOSITORY = "OuroborosCollective/Sovereign-Studio-ato"
REVISION = "a" * 40
OTHER_REVISION = "b" * 40
ZERO = "0" * 64


def _definition() -> WorkflowDefinition:
    step = WorkflowStep(
        step_id="github-write",
        kind=StepKind.TOOL_MUTATION,
        allowed_from=(WorkflowState.AUTHORIZED,),
        allowed_to=(WorkflowState.SUCCEEDED_UNVERIFIED, WorkflowState.BLOCKED),
        permission_required=True,
        capability="github-write",
        timeout_seconds=300,
        max_attempts=2,
        idempotency_key="github-write-once",
        required_readback_kinds=("github-pr",),
    )
    return WorkflowDefinition.create(workflow_id="release-workflow", steps=(step,))


def _binding(definition: WorkflowDefinition, **overrides: str) -> WorkflowBinding:
    values = {
        "workflow_run_id": "run-1113-contract",
        "workflow_definition_hash": definition.definition_hash,
        "owner_identity": "owner-42",
        "tenant_or_org_identity": "OuroborosCollective",
        "repository_identity": REPOSITORY,
        "workspace_id": "workspace-42",
        "base_revision": REVISION,
        "head_revision": REVISION,
    }
    values.update(overrides)
    return WorkflowBinding(**values)


def _permission(*, definition: WorkflowDefinition | None = None, binding: WorkflowBinding | None = None):
    definition = definition or _definition()
    binding = binding or _binding(definition)
    return create_permission_request(
        binding=binding,
        definition=definition,
        step_id="github-write",
        tool_name="github-write",
        parameters={"operation": "create_pr", "title": "Bound change"},
        expected_changed_paths=("backend/agent_runtime/durable_workflow.py",),
        valid_until_epoch=2_000,
        max_attempts=1,
    )


def _approved_permission():
    return approve_permission(_permission(), approver_identity="owner-42", approval_source="owner-ui", observed_epoch=1_000)


def _execution(permission=None):
    permission = permission or _approved_permission()
    definition = _definition()
    return create_execution_receipt(
        permission=permission,
        definition=definition,
        observed_epoch=1_100,
        observed_revision=REVISION,
        parameters={"operation": "create_pr", "title": "Bound change"},
        attempt_number=1,
        exit_status=0,
        output_hash=canonical_sha256({"exit": 0}),
        changed_paths=("backend/agent_runtime/durable_workflow.py",),
        patch_hash=canonical_sha256({"patch": "bounded"}),
    )


def test_definition_binding_and_permission_hashes_are_deterministic() -> None:
    first = _definition()
    second = _definition()
    assert first.definition_hash == second.definition_hash
    request = _permission(definition=first)
    assert request.decision is PermissionDecision.REQUESTED
    assert request.verify()
    assert request.parameters_hash == canonical_sha256({"operation": "create_pr", "title": "Bound change"})


def test_permission_hash_changes_for_cross_tenant_repo_workspace_and_revision() -> None:
    definition = _definition()
    baseline = _permission(definition=definition)
    for field, value in (
        ("tenant_or_org_identity", "other-org"),
        ("repository_identity", "other/repository"),
        ("workspace_id", "other-workspace"),
        ("head_revision", OTHER_REVISION),
    ):
        candidate = _permission(definition=definition, binding=_binding(definition, **{field: value}))
        assert candidate.receipt_hash != baseline.receipt_hash


def test_secret_payload_unknown_step_and_mutating_step_without_readback_fail_closed() -> None:
    definition = _definition()
    with pytest.raises(DurableWorkflowError, match="secret-shaped"):
        create_permission_request(
            binding=_binding(definition), definition=definition, step_id="github-write", tool_name="github-write",
            parameters={"authorization": "Bearer do-not-store"}, expected_changed_paths=(), valid_until_epoch=2_000, max_attempts=1,
        )
    with pytest.raises(DurableWorkflowError, match="unknown workflow step"):
        create_permission_request(
            binding=_binding(definition), definition=definition, step_id="unknown-step", tool_name="github-write",
            parameters={}, expected_changed_paths=(), valid_until_epoch=2_000, max_attempts=1,
        )
    with pytest.raises(DurableWorkflowError, match="require an authoritative readback"):
        WorkflowStep(
            step_id="unsafe-write", kind=StepKind.TOOL_MUTATION,
            allowed_from=(WorkflowState.READY,), allowed_to=(WorkflowState.RUNNING,), permission_required=True,
            capability="write", timeout_seconds=1, max_attempts=1, idempotency_key="unsafe",
        )


def test_unapproved_expired_or_payload_changed_permission_cannot_execute() -> None:
    requested = _permission()
    with pytest.raises(DurableWorkflowError, match="approved permission"):
        _execution(requested)
    expired = approve_permission(requested, approver_identity="owner-42", approval_source="owner-ui", observed_epoch=1_000)
    with pytest.raises(DurableWorkflowError, match="has expired"):
        create_execution_receipt(
            permission=expired, definition=_definition(), observed_epoch=2_001, observed_revision=REVISION,
            parameters={"operation": "create_pr", "title": "Bound change"}, attempt_number=1, exit_status=0,
            output_hash=canonical_sha256({"exit": 0}), changed_paths=("backend/agent_runtime/durable_workflow.py",),
            patch_hash=canonical_sha256({"patch": "bounded"}),
        )
    approved = _approved_permission()
    with pytest.raises(DurableWorkflowError, match="parameters differ"):
        create_execution_receipt(
            permission=approved, definition=_definition(), observed_epoch=1_100, observed_revision=REVISION,
            parameters={"operation": "create_pr", "title": "changed after approval"}, attempt_number=1, exit_status=0,
            output_hash=canonical_sha256({"exit": 0}), changed_paths=("backend/agent_runtime/durable_workflow.py",),
            patch_hash=canonical_sha256({"patch": "bounded"}),
        )


def test_execution_success_is_unverified_until_authorized_readback_matches() -> None:
    execution, state = _execution()
    assert execution.verdict is ExecutionVerdict.SUCCEEDED_UNVERIFIED
    assert state is WorkflowState.SUCCEEDED_UNVERIFIED
    readback = CanonicalReadback(
        source="github-api", repository_identity=REPOSITORY, observed_revision=REVISION,
        kind="github-pr", result_hash=canonical_sha256({"pr": 1, "head": REVISION}), verdict=ReadbackVerdict.VERIFIED,
    )
    verified, terminal_state = apply_canonical_readback(execution, permission=_approved_permission(), readback=readback)
    assert verified.verdict is ExecutionVerdict.VERIFIED
    assert terminal_state is WorkflowState.VERIFIED
    assert verified.verify()


def test_cross_repository_cross_revision_and_wrong_readback_kind_are_rejected() -> None:
    permission = _approved_permission()
    execution, _ = _execution(permission)
    with pytest.raises(DurableWorkflowError, match="repository differs"):
        apply_canonical_readback(
            execution, permission=permission,
            readback=CanonicalReadback("github-api", "other/repository", REVISION, "github-pr", canonical_sha256({"ok": True}), ReadbackVerdict.VERIFIED),
        )
    with pytest.raises(DurableWorkflowError, match="revision differs"):
        apply_canonical_readback(
            execution, permission=permission,
            readback=CanonicalReadback("github-api", REPOSITORY, OTHER_REVISION, "github-pr", canonical_sha256({"ok": True}), ReadbackVerdict.VERIFIED),
        )
    with pytest.raises(DurableWorkflowError, match="not authorized"):
        apply_canonical_readback(
            execution, permission=permission,
            readback=CanonicalReadback("github-api", REPOSITORY, REVISION, "ci-run", canonical_sha256({"ok": True}), ReadbackVerdict.VERIFIED),
        )


def test_restart_resume_waits_for_external_effect_readback_and_never_replays_blindly() -> None:
    permission = _approved_permission()
    execution, _ = _execution(permission)
    snapshot = WorkflowSnapshot(
        binding=permission.binding, state=WorkflowState.SUCCEEDED_UNVERIFIED, current_step_id="github-write",
        attempt_number=1, last_permission_hash=permission.receipt_hash, last_execution_hash=execution.execution_hash,
    )
    assert resume_snapshot(snapshot=snapshot, execution=execution, external_readback=None) is WorkflowState.WAITING_FOR_EXTERNAL_EVIDENCE
    contradictory = CanonicalReadback("github-api", "other/repository", REVISION, "github-pr", canonical_sha256({"ok": True}), ReadbackVerdict.VERIFIED)
    assert resume_snapshot(snapshot=snapshot, execution=execution, external_readback=contradictory) is WorkflowState.CONTRADICTED


def test_tampering_and_changed_effect_surface_are_rejected() -> None:
    permission = _approved_permission()
    with pytest.raises(DurableWorkflowError, match="changed paths differ"):
        create_execution_receipt(
            permission=permission, definition=_definition(), observed_epoch=1_100, observed_revision=REVISION,
            parameters={"operation": "create_pr", "title": "Bound change"}, attempt_number=1, exit_status=0,
            output_hash=canonical_sha256({"exit": 0}), changed_paths=("backend/agent_runtime/other.py",),
            patch_hash=canonical_sha256({"patch": "bounded"}), previous_execution_hash=ZERO,
        )


def test_migrations_are_append_only_and_source_mirror_are_byte_identical() -> None:
    root = Path(__file__).resolve().parents[2]
    source = root / "backend/migrations/057_durable_workflow_permission_receipts.sql"
    mirror = root / "scripts/sovereign-backend/migrations/057_durable_workflow_permission_receipts.sql"
    assert source.read_bytes() == mirror.read_bytes()
    migration = source.read_text("utf-8")
    for table in ("durable_workflow_runs", "workflow_permission_receipts", "workflow_execution_receipts"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration
    assert "BEFORE UPDATE ON workflow_permission_receipts" in migration
    assert "BEFORE DELETE ON workflow_execution_receipts" in migration
    assert "UNIQUE (workflow_run_id, idempotency_key, attempt_number)" in migration
    assert "SUCCEEDED_UNVERIFIED" in migration and "VERIFIED" in migration


def test_versioned_architecture_documentation_covers_truth_boundaries() -> None:
    root = Path(__file__).resolve().parents[2]
    document = (root / "docs/architecture/DURABLE_WORKFLOW_PERMISSION_RECEIPTS.v1.md").read_text("utf-8")
    for required in (
        "sovereign.durable-workflow.v1",
        "sovereign.permission-receipt.v1",
        "sovereign.execution-receipt.v1",
        "SUCCEEDED_UNVERIFIED",
        "VERIFIED",
        "CONTRADICTED",
        "append-only",
    ):
        assert required in document


def test_source_and_deployment_runtime_are_byte_identical_and_exclude_dynamic_execution() -> None:
    root = Path(__file__).resolve().parents[2]
    source = root / "backend/agent_runtime/durable_workflow.py"
    mirror = root / "scripts/sovereign-backend/agent_runtime/durable_workflow.py"
    store = root / "backend/agent_runtime/durable_workflow_store.py"
    store_mirror = root / "scripts/sovereign-backend/agent_runtime/durable_workflow_store.py"
    assert source.read_bytes() == mirror.read_bytes()
    assert store.read_bytes() == store_mirror.read_bytes()
    source_text = source.read_text("utf-8")
    store_text = store.read_text("utf-8")
    assert "eval(" not in source_text
    assert "exec(" not in source_text
    assert "UPDATE " not in store_text
    assert "DELETE " not in store_text
