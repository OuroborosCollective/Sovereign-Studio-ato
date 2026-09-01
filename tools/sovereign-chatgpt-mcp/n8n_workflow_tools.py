from __future__ import annotations

from typing import Any, Literal

from mcp.types import ToolAnnotations

from n8n_workflow_runtime import CIEvidenceWatchSpec


N8NWorkflowLane = Literal["sovereign", "aurion"]
N8NWorkflowOperation = Literal[
    "inventory",
    "create_draft",
    "update_draft",
    "activate",
    "pause",
]

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
EXTERNAL_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=True,
)

_BROKER: Any = None
_REGISTERED = False


def _spec_payload(spec: CIEvidenceWatchSpec | None) -> dict[str, Any] | None:
    if spec is None:
        return None
    return spec.model_dump(mode="json")


def n8n_workflow_plan(
    lane_id: N8NWorkflowLane,
    operation: N8NWorkflowOperation,
    workflow_id: str | None = None,
    spec: CIEvidenceWatchSpec | None = None,
) -> dict[str, Any]:
    """Plan one allowlisted n8n workflow operation without mutating n8n."""
    if _BROKER is None:
        raise RuntimeError("n8n workflow tools are not registered")
    return _BROKER.call(
        "n8n_workflow_plan",
        {
            "lane_id": lane_id,
            "operation": operation,
            "workflow_id": workflow_id,
            "spec": _spec_payload(spec),
        },
        timeout=60,
    )


def n8n_workflow_apply(
    lane_id: N8NWorkflowLane,
    operation: N8NWorkflowOperation,
    confirmation_sha256: str,
    owner_approved: bool,
    workflow_id: str | None = None,
    spec: CIEvidenceWatchSpec | None = None,
) -> dict[str, Any]:
    """Apply one confirmed n8n plan through the owner-gated host command queue."""
    if _BROKER is None:
        raise RuntimeError("n8n workflow tools are not registered")
    return _BROKER.call(
        "n8n_workflow_apply",
        {
            "lane_id": lane_id,
            "operation": operation,
            "workflow_id": workflow_id,
            "spec": _spec_payload(spec),
            "confirmation_sha256": confirmation_sha256,
            "owner_approved": owner_approved,
        },
        timeout=180,
    )


def register(mcp: Any, broker: Any) -> None:
    global _BROKER, _REGISTERED
    _BROKER = broker
    if _REGISTERED:
        return
    mcp.tool(annotations=READ_ONLY)(n8n_workflow_plan)
    mcp.tool(annotations=EXTERNAL_WRITE)(n8n_workflow_apply)
    _REGISTERED = True
