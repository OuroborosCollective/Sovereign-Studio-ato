"""PostgreSQL persistence boundary for durable workflow receipts.

Callers provide a real transaction-capable database connection.  The store never
accepts client identity fields as authority and never updates or deletes a
receipt; PostgreSQL triggers enforce the latter independently.
"""

from __future__ import annotations

import json
from typing import Any

from .durable_workflow import ExecutionReceipt, PermissionReceipt, WorkflowBinding


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
]
