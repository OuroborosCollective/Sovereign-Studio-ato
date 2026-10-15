"""PostgreSQL persistence boundary for durable workflow receipts.

Callers provide a real transaction-capable database connection.  The store never
accepts client identity fields as authority and never updates or deletes a
receipt; PostgreSQL triggers enforce the latter independently.
"""

from __future__ import annotations

import json
from typing import Any

from .durable_workflow import ExecutionReceipt, PermissionDecision, PermissionReceipt, WorkflowBinding, canonical_sha256, permission_receipt_from_dict
from .revocation_closure import PermissionAuthorityHead, RevocationReceipt, create_revocation_transition


class DurableWorkflowStoreError(RuntimeError):
    """Raised when a receipt is structurally invalid for persistence."""


def _body(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def persist_workflow_run(conn: Any, binding: WorkflowBinding) -> None:
    """Persist one immutable, server-resolved workflow identity."""
    body = binding.canonical()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO durable_workflow_runs (
                workflow_run_id, workflow_schema_version, workflow_definition_hash,
                owner_identity, tenant_or_org_identity, repository_identity, workspace_id,
                base_revision, head_revision, merge_revision, integration_id,
                issue_number, pull_request_number, canonical_body
            ) VALUES (%s, 'sovereign.durable-workflow.v1', %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                binding.workflow_run_id, binding.workflow_definition_hash,
                binding.owner_identity, binding.tenant_or_org_identity,
                binding.repository_identity, binding.workspace_id, binding.base_revision,
                binding.head_revision, binding.merge_revision, binding.integration_id,
                binding.issue_number, binding.pull_request_number, _body(body),
            ),
        )
    conn.commit()


def append_permission_receipt(conn: Any, *, receipt: PermissionReceipt, sequence: int) -> None:
    """Append a cryptographically self-verifying permission decision."""
    if sequence < 0 or not receipt.verify():
        raise DurableWorkflowStoreError("permission receipt is not persistable")
    body = receipt.canonical() | {"receipt_hash": receipt.receipt_hash}
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO workflow_permission_receipts (
                receipt_hash, workflow_run_id, receipt_sequence, permission_id, step_id,
                tool_name, capability, parameters_hash, base_revision, valid_until_epoch,
                max_attempts, decision, predecessor_receipt_hash, canonical_body
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                receipt.receipt_hash, receipt.binding.workflow_run_id, sequence,
                receipt.permission_id, receipt.step_id, receipt.tool_name, receipt.capability,
                receipt.parameters_hash, receipt.binding.base_revision, receipt.valid_until_epoch,
                receipt.max_attempts, receipt.decision.value, receipt.predecessor_receipt_hash,
                _body(body),
            ),
        )
    conn.commit()


def read_latest_permission_receipt(conn: Any, *, permission_id: str) -> tuple[PermissionReceipt, int] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT receipt_sequence, canonical_body
            FROM workflow_permission_receipts
            WHERE permission_id = %s
            ORDER BY receipt_sequence DESC, receipt_hash DESC
            LIMIT 1
            """,
            (permission_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    body = row.get("canonical_body") if isinstance(row, dict) else row[1]
    if isinstance(body, str):
        body = json.loads(body)
    if not isinstance(body, dict):
        raise DurableWorkflowStoreError("permission receipt canonical body is unreadable")
    receipt = permission_receipt_from_dict(body)
    sequence = int(row.get("receipt_sequence") if isinstance(row, dict) else row[0])
    return receipt, sequence


def read_permission_authority_head(conn: Any, *, permission_id: str) -> PermissionAuthorityHead | None:
    latest = read_latest_permission_receipt(conn, permission_id=permission_id)
    if latest is None:
        return None
    receipt, sequence = latest
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


def bind_repository_job_permission(
    conn: Any,
    *,
    job_id: str,
    approved_receipt: PermissionReceipt,
) -> str:
    if not approved_receipt.verify() or approved_receipt.decision != PermissionDecision.APPROVED:
        raise DurableWorkflowStoreError("repository job binding requires APPROVED permission")
    payload = {
        "schema_version": "sovereign.repository-job-permission-binding.v1",
        "job_id": str(job_id),
        "workflow_run_id": approved_receipt.binding.workflow_run_id,
        "permission_id": approved_receipt.permission_id,
        "approved_receipt_hash": approved_receipt.receipt_hash,
    }
    binding_hash = canonical_sha256(payload)
    body = payload | {"binding_hash": binding_hash}
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO repository_job_permission_bindings (
                job_id, workflow_run_id, permission_id,
                approved_receipt_hash, binding_hash, canonical_body
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                job_id,
                approved_receipt.binding.workflow_run_id,
                approved_receipt.permission_id,
                approved_receipt.receipt_hash,
                binding_hash,
                _body(body),
            ),
        )
    conn.commit()
    return binding_hash


def read_repository_job_permission_binding(conn: Any, *, job_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT canonical_body
            FROM repository_job_permission_bindings
            WHERE job_id = %s
            LIMIT 1
            """,
            (job_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    body = row.get("canonical_body") if isinstance(row, dict) else row[0]
    if isinstance(body, str):
        body = json.loads(body)
    if not isinstance(body, dict):
        raise DurableWorkflowStoreError("repository permission binding is unreadable")
    material = dict(body)
    observed = str(material.pop("binding_hash", ""))
    if canonical_sha256(material) != observed:
        raise DurableWorkflowStoreError("repository permission binding hash is contradicted")
    return dict(body)


def append_execution_receipt(conn: Any, *, receipt: ExecutionReceipt, sequence: int) -> None:
    """Append a self-verifying execution observation; never update an earlier verdict."""
    if sequence < 0 or not receipt.verify():
        raise DurableWorkflowStoreError("execution receipt is not persistable")
    body = receipt.canonical() | {"execution_hash": receipt.execution_hash}
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO workflow_execution_receipts (
                execution_hash, workflow_run_id, execution_sequence, execution_id,
                permission_receipt_hash, step_id, attempt_number, parameters_hash,
                observed_revision, idempotency_key, output_hash, patch_hash, verdict,
                readback_hash, previous_execution_hash, canonical_body
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                receipt.execution_hash, receipt.binding.workflow_run_id, sequence,
                receipt.execution_id, receipt.permission_receipt_hash, receipt.step_id,
                receipt.attempt_number, receipt.parameters_hash, receipt.observed_revision,
                receipt.idempotency_key, receipt.output_hash, receipt.patch_hash,
                receipt.verdict.value, receipt.readback_hash, receipt.previous_execution_hash,
                _body(body),
            ),
        )
    conn.commit()


__all__ = [
    "DurableWorkflowStoreError", "persist_workflow_run", "append_permission_receipt", "append_execution_receipt",
    "read_latest_permission_receipt", "read_permission_authority_head",
    "bind_repository_job_permission", "read_repository_job_permission_binding",
]
