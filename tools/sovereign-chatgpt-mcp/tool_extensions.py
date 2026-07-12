from __future__ import annotations

from typing import Any

from mcp.types import ToolAnnotations

_BROKER: Any = None
_REGISTERED = False

NETWORK_READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
EXTERNAL_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)


def repository_dispatch_workflow(
    workflow: str,
    ref: str = "main",
    inputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Dispatch one allowlisted GitHub Actions workflow without accepting secret-shaped inputs."""
    if _BROKER is None:
        raise RuntimeError("Workflow tools are not registered")
    return _BROKER.call(
        "github_workflow_dispatch",
        {"workflow": workflow, "ref": ref, "inputs": inputs or {}},
        timeout=60,
    )


def repository_workflow_run_status(run_id: int) -> dict[str, Any]:
    """Read workflow, job and failed-step evidence for one GitHub Actions run."""
    if _BROKER is None:
        raise RuntimeError("Workflow tools are not registered")
    return _BROKER.call("github_workflow_run_status", {"run_id": run_id}, timeout=60)


def register(mcp: Any, broker: Any) -> None:
    global _BROKER, _REGISTERED
    _BROKER = broker
    if _REGISTERED:
        return
    mcp.tool(annotations=EXTERNAL_WRITE)(repository_dispatch_workflow)
    mcp.tool(annotations=NETWORK_READ)(repository_workflow_run_status)
    _REGISTERED = True
