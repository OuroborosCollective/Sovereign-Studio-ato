"""A2A 1.0 transport mapping for the persisted Sovereign Agents SDK truth chain.

This module does not own a run state machine. It maps the existing
``agent_runs`` and ``agent_events`` truth into A2A protobuf messages and maps an
incoming A2A message into the existing Agents SDK mission input.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any, Final

from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.struct_pb2 import Struct
from google.protobuf.timestamp_pb2 import Timestamp

from a2a.helpers.proto_helpers import get_message_text
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentProvider,
    AgentSkill,
    Artifact,
    HTTPAuthSecurityScheme,
    Message,
    Part,
    Role,
    SendMessageRequest,
    SecurityRequirement,
    SecurityScheme,
    SendMessageResponse,
    StreamResponse,
    StringList,
    Task,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)


A2A_PROTOCOL_VERSION: Final[str] = "1.0"
A2A_PROTOCOL_BINDING: Final[str] = "HTTP+JSON"
A2A_MEDIA_TYPE: Final[str] = "application/a2a+json"
A2A_INPUT_MODES: Final[tuple[str, ...]] = ("text/plain", "application/json")
A2A_OUTPUT_MODES: Final[tuple[str, ...]] = ("application/json", "text/plain")

_SUBMITTED_STATUSES: Final[frozenset[str]] = frozenset({
    "RECEIVED",
    "SCOPING",
    "PLANNED",
    "QUEUED",
    "ASSIGNED",
})
_WORKING_STATUSES: Final[frozenset[str]] = frozenset({
    "RUNNING",
    "WAITING_FOR_TOOL",
    "WAITING_FOR_AGENT",
    "VERIFYING",
})
_INPUT_REQUIRED_STATUSES: Final[frozenset[str]] = frozenset({
    "WAITING_FOR_OWNER",
    "BLOCKED",
    "FAILED_RECOVERABLE",
    "READY_FOR_DRAFT_PR",
})
_COMPLETED_STATUSES: Final[frozenset[str]] = frozenset({
    "DRAFT_PR_CREATED",
    "COMPLETED",
})
_FAILED_STATUSES: Final[frozenset[str]] = frozenset({"FAILED_FINAL"})
_A2A_TERMINAL_OR_INTERRUPTED: Final[frozenset[int]] = frozenset({
    TaskState.TASK_STATE_COMPLETED,
    TaskState.TASK_STATE_FAILED,
    TaskState.TASK_STATE_CANCELED,
    TaskState.TASK_STATE_INPUT_REQUIRED,
    TaskState.TASK_STATE_REJECTED,
    TaskState.TASK_STATE_AUTH_REQUIRED,
})


def _value(source: object, key: str, default: object = "") -> object:
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _bounded(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _metadata(values: Mapping[str, object]) -> Struct:
    safe = {
        str(key): value
        for key, value in values.items()
        if value is not None and isinstance(value, (str, int, float, bool, list, dict))
    }
    result = Struct()
    result.update(safe)
    return result


def message_to_dict(
    message: Any,
    *,
    include_defaults: bool = False,
) -> dict[str, Any]:
    """Serialize one A2A protobuf with canonical JSON field names."""

    return MessageToDict(
        message,
        preserving_proto_field_name=False,
        use_integers_for_enums=False,
        always_print_fields_with_no_presence=include_defaults,
    )


def parse_send_message(payload: Mapping[str, object]) -> SendMessageRequest:
    request_message = SendMessageRequest()
    ParseDict(dict(payload), request_message, ignore_unknown_fields=False)
    if not request_message.message.message_id:
        raise ValueError("A2A messageId is required")
    if request_message.message.role != Role.ROLE_USER:
        raise ValueError("A2A inbound message role must be ROLE_USER")
    return request_message


def mission_from_a2a_request(request_message: SendMessageRequest) -> tuple[str, str, str | None]:
    """Map an A2A user message to the existing mission/evidence/model contract."""

    mission = get_message_text(request_message.message, delimiter="\n").strip()
    if not mission:
        raise ValueError("A2A message must contain at least one non-empty text part")

    metadata = MessageToDict(request_message.metadata) if request_message.HasField("metadata") else {}
    message_metadata = (
        MessageToDict(request_message.message.metadata)
        if request_message.message.HasField("metadata")
        else {}
    )
    evidence = _bounded(metadata.get("evidence") or message_metadata.get("evidence"), 250_000)
    requested_model = _bounded(metadata.get("model") or message_metadata.get("model"), 160) or None
    return mission, evidence, requested_model


def build_sovereign_agent_card(
    *,
    base_url: str,
    manifest: Mapping[str, object],
    version: str = "1.0.0",
) -> AgentCard:
    normalized_base = base_url.strip().rstrip("/")
    if not normalized_base.startswith(("https://", "http://")):
        raise ValueError("A2A base_url must be absolute")

    skills: list[AgentSkill] = [
        AgentSkill(
            id="sovereign-orchestration",
            name="Sovereign Agents SDK Orchestration",
            description=(
                "Routes one bounded mission through a verified direct OpenRouter or FreeLLM route, "
                "the OpenAI Agents SDK, MCP tools and the persisted Sovereign truth chain."
            ),
            tags=["agents-sdk", "openrouter", "freellm", "mcp", "truth-chain"],
            input_modes=list(A2A_INPUT_MODES),
            output_modes=list(A2A_OUTPUT_MODES),
        ),
        AgentSkill(
            id="sovereign-runtime-evidence",
            name="Runtime Evidence Transport",
            description=(
                "Returns only persisted run, task, event, approval and Draft-PR evidence; "
                "unsupported success claims remain blocked."
            ),
            tags=["runtime-evidence", "draft-pr-only", "no-auto-merge"],
            input_modes=list(A2A_INPUT_MODES),
            output_modes=list(A2A_OUTPUT_MODES),
        ),
    ]

    core_agents = manifest.get("agents") if isinstance(manifest, Mapping) else None
    if isinstance(core_agents, Sequence) and not isinstance(core_agents, (str, bytes)):
        for item in core_agents:
            if not isinstance(item, Mapping):
                continue
            role = _bounded(item.get("role"), 120)
            name = _bounded(item.get("name"), 160)
            responsibility = _bounded(item.get("responsibility"), 1000)
            if role and name and responsibility:
                skills.append(AgentSkill(
                    id=f"sovereign-{role.replace('_', '-')}",
                    name=name,
                    description=responsibility,
                    tags=["sovereign-role", role],
                    input_modes=list(A2A_INPUT_MODES),
                    output_modes=list(A2A_OUTPUT_MODES),
                ))

    return AgentCard(
        name="Sovereign Studio ATO",
        description=(
            "Evidence-bounded agent orchestration for OuroborosCollective/Sovereign-Studio-ato. "
            "A2A transports messages and task updates; the existing truth chain remains authoritative."
        ),
        supported_interfaces=[AgentInterface(
            url=f"{normalized_base}/a2a/v1",
            protocol_binding=A2A_PROTOCOL_BINDING,
            protocol_version=A2A_PROTOCOL_VERSION,
        )],
        provider=AgentProvider(
            organization="OuroborosCollective",
            url="https://github.com/OuroborosCollective",
        ),
        version=version,
        capabilities=AgentCapabilities(
            streaming=True,
            push_notifications=False,
            extended_agent_card=False,
        ),
        security_schemes={
            "bearerAuth": SecurityScheme(
                http_auth_security_scheme=HTTPAuthSecurityScheme(
                    description="Existing Sovereign authenticated session or Bearer JWT.",
                    scheme="Bearer",
                    bearer_format="JWT",
                )
            )
        },
        security_requirements=[
            SecurityRequirement(schemes={"bearerAuth": StringList(list=[])})
        ],
        default_input_modes=list(A2A_INPUT_MODES),
        default_output_modes=list(A2A_OUTPUT_MODES),
        skills=skills,
    )


def task_state_from_run_status(status: object) -> int:
    normalized = _bounded(status, 80).upper()
    if normalized in _SUBMITTED_STATUSES:
        return TaskState.TASK_STATE_SUBMITTED
    if normalized in _WORKING_STATUSES:
        return TaskState.TASK_STATE_WORKING
    if normalized in _INPUT_REQUIRED_STATUSES:
        return TaskState.TASK_STATE_INPUT_REQUIRED
    if normalized in _COMPLETED_STATUSES:
        return TaskState.TASK_STATE_COMPLETED
    if normalized in _FAILED_STATUSES:
        return TaskState.TASK_STATE_FAILED
    return TaskState.TASK_STATE_UNSPECIFIED


def is_terminal_or_interrupted(status: object) -> bool:
    return task_state_from_run_status(status) in _A2A_TERMINAL_OR_INTERRUPTED


def is_terminal_run_status(status: object) -> bool:
    return task_state_from_run_status(status) in {
        TaskState.TASK_STATE_COMPLETED,
        TaskState.TASK_STATE_FAILED,
        TaskState.TASK_STATE_CANCELED,
        TaskState.TASK_STATE_REJECTED,
    }


def run_statuses_for_task_state(state_name: str) -> tuple[str, ...]:
    normalized = _bounded(state_name, 80).upper()
    mapping = {
        "TASK_STATE_SUBMITTED": tuple(sorted(_SUBMITTED_STATUSES)),
        "TASK_STATE_WORKING": tuple(sorted(_WORKING_STATUSES)),
        "TASK_STATE_INPUT_REQUIRED": tuple(sorted(_INPUT_REQUIRED_STATUSES)),
        "TASK_STATE_COMPLETED": tuple(sorted(_COMPLETED_STATUSES)),
        "TASK_STATE_FAILED": tuple(sorted(_FAILED_STATUSES)),
        "TASK_STATE_CANCELED": (),
        "TASK_STATE_REJECTED": (),
        "TASK_STATE_AUTH_REQUIRED": (),
    }
    if normalized not in mapping:
        raise ValueError("status is not a valid A2A TaskState")
    return mapping[normalized]


def _timestamp_from_value(value: object) -> Timestamp | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    normalized = (
        str(isoformat())
        if callable(isoformat)
        else str(value or "").strip()
    )
    if not normalized:
        return None
    timestamp = Timestamp()
    try:
        timestamp.FromJsonString(normalized.replace("+00:00", "Z"))
    except ValueError:
        return None
    return timestamp


def _status_message(
    *,
    run_id: str,
    context_id: str,
    summary: str,
    next_action: str,
    agent_id: str,
    event_type: str,
) -> Message:
    payload = {
        "summary": _bounded(summary, 2000),
        "nextAction": _bounded(next_action, 1000),
        "agentId": _bounded(agent_id, 160),
        "eventType": _bounded(event_type, 120),
        "rawModelOutputPersisted": False,
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]
    return Message(
        message_id=f"a2a-status-{digest}",
        context_id=context_id,
        task_id=run_id,
        role=Role.ROLE_AGENT,
        parts=[Part(
            text=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            media_type="application/json",
        )],
        metadata=_metadata({"source": "sovereign-truth-chain"}),
    )


def task_from_run(
    run: object,
    *,
    include_artifact: bool = True,
    history: Sequence[Message] = (),
) -> Task:
    run_id = _bounded(_value(run, "run_id", _value(run, "runId")), 160)
    if not run_id:
        raise ValueError("run id is required for A2A task mapping")
    context_id = _bounded(
        _value(run, "a2a_context_id")
        or _value(run, "a2aContextId")
        or _value(run, "session_key")
        or _value(run, "sessionKey")
        or f"context-{run_id}",
        500,
    )
    status = _bounded(_value(run, "status"), 80).upper()
    reason = _bounded(_value(run, "reason"), 2000)
    next_action = _bounded(_value(run, "next_action", _value(run, "nextAction")), 1000)
    source = _bounded(_value(run, "source"), 120)
    evidence_id = _bounded(_value(run, "evidence_id", _value(run, "evidenceId")), 160)
    trace_id = _bounded(_value(run, "trace_id", _value(run, "traceId")), 160)
    job_id = _bounded(_value(run, "job_id", _value(run, "jobId")), 160)

    task_status = TaskStatus(
        state=task_state_from_run_status(status),
        message=_status_message(
            run_id=run_id,
            context_id=context_id,
            summary=reason or f"Sovereign run is {status or 'UNSPECIFIED'}.",
            next_action=next_action,
            agent_id="truth_chain",
            event_type="run_snapshot",
        ),
    )
    status_timestamp = _timestamp_from_value(
        _value(run, "updated_at", _value(run, "updatedAt"))
    )
    if status_timestamp is not None:
        task_status.timestamp.CopyFrom(status_timestamp)
    task = Task(
        id=run_id,
        context_id=context_id,
        status=task_status,
        history=list(history),
        metadata=_metadata({
            "sovereignStatus": status,
            "source": source,
            "evidenceId": evidence_id,
            "traceId": trace_id,
            "jobId": job_id,
            "autoMerge": False,
            "truthChainAuthoritative": True,
        }),
    )
    if include_artifact and task_status.state in {
        TaskState.TASK_STATE_COMPLETED,
        TaskState.TASK_STATE_FAILED,
        TaskState.TASK_STATE_INPUT_REQUIRED,
        TaskState.TASK_STATE_REJECTED,
    }:
        result_payload = {
            "runId": run_id,
            "status": status,
            "reason": reason,
            "nextAction": next_action,
            "evidenceId": evidence_id,
            "traceId": trace_id,
            "jobId": job_id or None,
            "autoMerge": False,
        }
        task.artifacts.append(Artifact(
            artifact_id=f"artifact-{run_id}",
            name="Sovereign truth-chain result",
            description="Bounded persisted run result; no raw model chain-of-thought is included.",
            parts=[Part(
                text=json.dumps(result_payload, ensure_ascii=False, sort_keys=True),
                media_type="application/json",
            )],
            metadata=_metadata({"source": "sovereign-truth-chain"}),
        ))
    return task


def status_update_from_event(
    event: Mapping[str, object],
    *,
    context_id: str,
    run_status: object | None = None,
) -> TaskStatusUpdateEvent:
    run_id = _bounded(event.get("run_id") or event.get("runId"), 160)
    if not run_id:
        raise ValueError("event run id is required")
    event_status = _bounded(event.get("status"), 80).upper()
    event_type = _bounded(event.get("type") or event.get("eventType"), 120)
    if event_type in {
        "run_received",
        "implementation_job_linked",
        "run_resumed",
        "run_state_changed",
        "owner_approval_requested",
    }:
        status = event_status or _bounded(run_status, 80).upper()
    else:
        status = "VERIFYING" if event_status == "VERIFYING" else "RUNNING"
    task_status = TaskStatus(
        state=task_state_from_run_status(status),
        message=_status_message(
            run_id=run_id,
            context_id=context_id,
            summary=_bounded(event.get("summary"), 2000),
            next_action=_bounded(event.get("next_action") or event.get("nextAction"), 1000),
            agent_id=_bounded(event.get("agent_id") or event.get("agentId"), 160),
            event_type=event_type,
        ),
    )
    timestamp = _timestamp_from_value(event.get("created_at") or event.get("createdAt"))
    if timestamp is not None:
        task_status.timestamp.CopyFrom(timestamp)

    return TaskStatusUpdateEvent(
        task_id=run_id,
        context_id=context_id,
        status=task_status,
        metadata=_metadata({
            "eventId": _bounded(event.get("event_id") or event.get("eventId"), 160),
            "evidenceId": _bounded(event.get("evidence_id") or event.get("evidenceId"), 160),
            "traceId": _bounded(event.get("trace_id") or event.get("traceId"), 160),
            "source": _bounded(event.get("source"), 120),
            "sovereignStatus": status,
            "agentEventStatus": event_status,
            "truthChainAuthoritative": True,
        }),
    )


def task_history_from_events(
    events: Sequence[Mapping[str, object]],
    *,
    context_id: str,
    run_status: object,
    limit: int,
) -> list[Message]:
    safe_limit = max(0, min(int(limit), 50))
    if safe_limit == 0:
        return []
    selected = list(events)[-safe_limit:]
    return [
        status_update_from_event(
            event,
            context_id=context_id,
            run_status=run_status,
        ).status.message
        for event in selected
    ]


def send_message_response(task: Task) -> SendMessageResponse:
    return SendMessageResponse(task=task)


def task_stream_response(task: Task) -> StreamResponse:
    return StreamResponse(task=task)


def status_stream_response(event: TaskStatusUpdateEvent) -> StreamResponse:
    return StreamResponse(status_update=event)
