from __future__ import annotations

import functools
from typing import Any

from mcp.types import CallToolResult
from pydantic import BaseModel, ConfigDict


class ToolOutputEnvelope(BaseModel):
    """Compatibility output contract for legacy dict and widget tools.

    Existing top-level fields remain available through ``extra='allow'`` while
    every tool receives the same machine-readable control fields.
    """

    model_config = ConfigDict(extra="allow")

    schemaVersion: str
    ok: bool
    status: str
    failureFamily: str | None
    blocker: str | None
    mutationPerformed: bool
    nextAction: str | None
    evidence: dict[str, Any]
    data: dict[str, Any]
    secretValuesReturned: bool


class ExternalWriteOutput(ToolOutputEnvelope):
    """Stricter contract for network, host, repository and database mutations."""

    operationId: str | None
    requestedEffect: str
    observedEffect: str
    ownerApproved: bool
    expectedRevision: str | None
    actualRevision: str | None
    readbackVerified: bool


_FAILURE_STATUS_MARKERS = (
    "BLOCKED",
    "FAILED",
    "FAILURE",
    "ERROR",
    "REJECTED",
    "DENIED",
    "INCOMPLETE",
    "UNAVAILABLE",
)


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _status_is_ok(status: str) -> bool:
    normalized = status.strip().upper()
    return not any(marker in normalized for marker in _FAILURE_STATUS_MARKERS)


def normalize_tool_output(result: Any, *, external_write: bool = False) -> Any:
    """Add the stable envelope without removing legacy result fields."""

    if isinstance(result, CallToolResult):
        structured = result.structuredContent
        normalized = _normalize_payload(
            structured if structured is not None else {},
            external_write=external_write,
        )
        return result.model_copy(update={"structuredContent": normalized})
    return _normalize_payload(result, external_write=external_write)


def _normalize_payload(result: Any, *, external_write: bool = False) -> dict[str, Any]:
    if isinstance(result, BaseModel):
        raw: Any = result.model_dump(mode="json", by_alias=True)
    elif isinstance(result, dict):
        raw = dict(result)
    else:
        raw = {"data": {"result": result}}

    payload: dict[str, Any] = dict(raw)
    status = str(payload.get("status") or "COMPLETED").strip() or "COMPLETED"
    explicit_ok = payload.get("ok")
    ok = explicit_ok if isinstance(explicit_ok, bool) else _status_is_ok(status)

    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {} if evidence is None else {"value": evidence}
    data = payload.get("data")
    if not isinstance(data, dict):
        data = {} if data is None else {"value": data}

    explicit_mutation = payload.get("mutationPerformed", payload.get("mutation_performed"))
    if isinstance(explicit_mutation, bool):
        mutation_performed = explicit_mutation
    else:
        mutation_performed = external_write and status.upper() in {
            "MERGED",
            "CLOSED",
            "REOPENED",
            "UPDATED",
            "BRANCH_DELETED",
            "DRAFT_PR_CREATED",
            "DRAFT_PR_UPDATED",
            "DISPATCHED",
            "RERUN_REQUESTED",
            "SCHEDULED",
        }

    payload.update(
        {
            "schemaVersion": str(payload.get("schemaVersion") or "sovereign.tool-output-envelope.v1"),
            "ok": bool(ok),
            "status": status,
            "failureFamily": _string_or_none(
                payload.get("failureFamily") or payload.get("failure_family")
            ),
            "blocker": _string_or_none(payload.get("blocker") or payload.get("error")),
            "mutationPerformed": bool(mutation_performed),
            "nextAction": _string_or_none(
                payload.get("nextAction") or payload.get("next_action")
            ),
            "evidence": evidence,
            "data": data,
            "secretValuesReturned": bool(
                payload.get("secretValuesReturned", payload.get("secret_values_returned", False))
            ),
        }
    )
    if external_write:
        operation_id = (
            payload.get("operationId")
            or payload.get("operation_id")
            or payload.get("request_id")
            or payload.get("run_id")
            or payload.get("job_id")
            or payload.get("pr_number")
        )
        readback_verified = bool(
            payload.get("readbackVerified")
            or payload.get("readback_verified")
            or payload.get("readback_deleted")
            or status.upper() in {"CLOSED", "REOPENED", "UPDATED", "BRANCH_DELETED"}
        )
        payload.update(
            {
                "operationId": _string_or_none(operation_id),
                "requestedEffect": "external-write",
                "observedEffect": "external-write" if mutation_performed else "none",
                "ownerApproved": bool(
                    payload.get("ownerApproved", payload.get("owner_approved", False))
                ),
                "expectedRevision": _string_or_none(
                    payload.get("expectedRevision")
                    or payload.get("expected_revision")
                    or payload.get("expected_head_sha")
                ),
                "actualRevision": _string_or_none(
                    payload.get("actualRevision")
                    or payload.get("actual_revision")
                    or payload.get("merge_commit_sha")
                    or payload.get("head_sha")
                    or payload.get("revision")
                ),
                "readbackVerified": readback_verified,
            }
        )
    return payload


def _has_strict_output_schema(schema: Any) -> bool:
    return bool(
        isinstance(schema, dict)
        and schema.get("type") == "object"
        and isinstance(schema.get("required"), list)
        and schema["required"]
    )


def _wrap_sync(fn: Any, *, external_write: bool) -> Any:
    @functools.wraps(fn)
    def wrapped(**kwargs: Any) -> Any:
        return normalize_tool_output(fn(**kwargs), external_write=external_write)

    setattr(wrapped, "__sovereign_output_contract_wrapped__", True)
    return wrapped


def _wrap_async(fn: Any, *, external_write: bool) -> Any:
    @functools.wraps(fn)
    async def wrapped(**kwargs: Any) -> Any:
        return normalize_tool_output(await fn(**kwargs), external_write=external_write)

    setattr(wrapped, "__sovereign_output_contract_wrapped__", True)
    return wrapped


def install_output_contracts(mcp: Any) -> dict[str, Any]:
    """Install strict fallback contracts after every FastMCP tool is registered."""

    compatibility_schema = ToolOutputEnvelope.model_json_schema()
    external_schema = ExternalWriteOutput.model_json_schema()
    total = 0
    strict = 0
    compatibility_upgraded = 0
    external_upgraded = 0
    for tool in mcp._tool_manager.list_tools():
        total += 1
        existing_schema = getattr(tool, "output_schema", None)
        if _has_strict_output_schema(existing_schema):
            strict += 1
            continue
        if getattr(tool.fn, "__sovereign_output_contract_wrapped__", False):
            compatibility_upgraded += 1
            continue

        annotations = getattr(tool, "annotations", None)
        external_write = bool(
            not getattr(annotations, "readOnlyHint", False)
            and (
                getattr(annotations, "destructiveHint", False)
                or getattr(annotations, "openWorldHint", False)
            )
        )
        output_model = ExternalWriteOutput if external_write else ToolOutputEnvelope
        output_schema = external_schema if external_write else compatibility_schema
        tool.fn = (
            _wrap_async(tool.fn, external_write=external_write)
            if bool(tool.is_async)
            else _wrap_sync(tool.fn, external_write=external_write)
        )
        tool.fn_metadata.output_model = output_model
        tool.fn_metadata.output_schema = output_schema
        tool.fn_metadata.wrap_output = False
        tool.__dict__.pop("output_schema", None)
        contract_name = "external-write-envelope-v1" if external_write else "compatibility-envelope-v1"
        tool.meta = {
            **(tool.meta or {}),
            "sovereign/outputContract": contract_name,
        }
        if external_write:
            external_upgraded += 1
        else:
            compatibility_upgraded += 1

    upgraded = compatibility_upgraded + external_upgraded
    return {
        "schemaVersion": "sovereign.output-contract-install.v1",
        "ok": total == strict + upgraded,
        "status": "OUTPUT_CONTRACTS_READY",
        "toolCount": total,
        "strictToolCount": strict,
        "externalWriteEnvelopeToolCount": external_upgraded,
        "compatibilityEnvelopeToolCount": compatibility_upgraded,
        "missingOutputSchemaCount": 0,
        "mutationPerformed": False,
        "secretValuesReturned": False,
    }
