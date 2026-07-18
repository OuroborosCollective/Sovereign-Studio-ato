"""Flask HTTP+JSON/SSE routes for the Sovereign A2A 1.0 adapter.

A2A is transport only. The injected ``start_run`` and ``resume_run`` callbacks
execute the existing OpenAI Agents SDK paths, while task snapshots and stream
updates are read from the persisted Sovereign truth chain.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from functools import wraps
from typing import Any
import uuid

from flask import Response, jsonify, request, stream_with_context
from google.protobuf.timestamp_pb2 import Timestamp

from a2a.types import ListTasksResponse

from .a2a_adapter import (
    A2A_MEDIA_TYPE,
    A2A_PROTOCOL_VERSION,
    build_sovereign_agent_card,
    is_terminal_or_interrupted,
    is_terminal_run_status,
    message_to_dict,
    mission_from_a2a_request,
    parse_send_message,
    run_statuses_for_task_state,
    send_message_response,
    status_stream_response,
    status_update_from_event,
    task_from_run,
    task_history_from_events,
    task_stream_response,
)
from .cognitive_run_store import (
    count_agent_runs,
    list_agent_runs,
    read_agent_events,
    read_agent_run,
)
from .cognitive_swarm_manifest import manifest_payload


ConnectionFactory = Callable[[], Any]
StartRun = Callable[..., tuple[dict[str, object], int]]
ResumeRun = Callable[..., tuple[dict[str, object], int]]
ServiceUserResolver = Callable[[], str | None]
_A2A_TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")


def _close_connection(conn: Any) -> None:
    close = getattr(conn, "close", None)
    if callable(close):
        close()


def _protocol_error() -> tuple[Response, int] | None:
    supplied = str(request.headers.get("A2A-Version") or "").strip()
    if supplied == A2A_PROTOCOL_VERSION:
        return None
    return _a2a_error(
        "VERSION_NOT_SUPPORTED",
        f"A2A-Version must be {A2A_PROTOCOL_VERSION}.",
        400,
        status_name="FAILED_PRECONDITION",
        metadata={
            "requestedVersion": supplied or "0.3",
            "supportedVersion": A2A_PROTOCOL_VERSION,
        },
    )


def _a2a_json(message: Any, status_code: int = 200) -> tuple[Response, int]:
    response = jsonify(message_to_dict(message))
    response.headers["Content-Type"] = A2A_MEDIA_TYPE
    response.headers["A2A-Version"] = A2A_PROTOCOL_VERSION
    response.headers["Cache-Control"] = "no-store"
    return response, status_code


def _a2a_error(
    reason: str,
    message: str,
    status_code: int,
    *,
    status_name: str | None = None,
    metadata: Mapping[str, object] | None = None,
    field_errors: list[dict[str, str]] | None = None,
) -> tuple[Response, int]:
    normalized_reason = str(reason or "UNKNOWN_ERROR").strip().upper()[:120]
    normalized_status = status_name or {
        400: "INVALID_ARGUMENT",
        401: "UNAUTHENTICATED",
        403: "PERMISSION_DENIED",
        404: "NOT_FOUND",
        409: "ABORTED",
        429: "RESOURCE_EXHAUSTED",
        500: "INTERNAL",
        502: "UNAVAILABLE",
        503: "UNAVAILABLE",
        504: "DEADLINE_EXCEEDED",
    }.get(int(status_code), "UNKNOWN")
    details: list[dict[str, object]] = [{
        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
        "reason": normalized_reason,
        "domain": "a2a-protocol.org",
        "metadata": {
            str(key): str(value)[:500]
            for key, value in (metadata or {}).items()
            if value is not None
        },
    }]
    if field_errors:
        details.append({
            "@type": "type.googleapis.com/google.rpc.BadRequest",
            "fieldViolations": [
                {
                    "field": str(item.get("field") or "")[:200],
                    "description": str(item.get("description") or "")[:500],
                }
                for item in field_errors
            ],
        })
    response = jsonify({
        "error": {
            "code": int(status_code),
            "status": normalized_status,
            "message": str(message or "A2A request failed.")[:1000],
            "details": details,
        }
    })
    response.headers["Content-Type"] = A2A_MEDIA_TYPE
    response.headers["A2A-Version"] = A2A_PROTOCOL_VERSION
    response.headers["Cache-Control"] = "no-store"
    return response, status_code


def _read_run(get_connection: ConnectionFactory, *, user_id: str, run_id: str):
    conn = get_connection()
    try:
        return read_agent_run(conn, user_id=user_id, run_id=run_id)
    finally:
        _close_connection(conn)


def _read_events(
    get_connection: ConnectionFactory,
    *,
    user_id: str,
    run_id: str,
) -> tuple[dict[str, object], ...]:
    conn = get_connection()
    try:
        return read_agent_events(conn, user_id=user_id, run_id=run_id, limit=1000)
    finally:
        _close_connection(conn)


def _a2a_context_id(request_message: Any) -> str:
    value = str(request_message.message.context_id or "").strip()
    if len(value) > 500:
        raise ValueError("A2A contextId exceeds the bounded input limit")
    return value or f"context-{uuid.uuid4().hex}"


def _persisted_a2a_context(run: object) -> str:
    return str(
        getattr(run, "a2a_context_id", None)
        or getattr(run, "session_key", "")
        or f"context-{getattr(run, 'run_id', '')}"
    )


def _validate_follow_up_context(request_message: Any, run: object) -> str:
    supplied = str(request_message.message.context_id or "").strip()
    if len(supplied) > 500:
        raise ValueError("A2A contextId exceeds the bounded input limit")
    persisted = _persisted_a2a_context(run)
    if supplied and supplied != persisted:
        raise ValueError("A2A contextId does not match the persisted task context")
    return persisted


def _follow_up_evidence(mission: str, evidence: str) -> str:
    payload = (
        "A2A follow-up message:\n"
        f"{mission.strip()}\n\n"
        "Additional runtime evidence:\n"
        f"{evidence.strip() or '[no additional evidence supplied]'}"
    )
    if len(payload) > 250_000:
        raise ValueError("A2A follow-up evidence exceeds the bounded input limit")
    return payload


def _resume_precondition_error(run: object) -> tuple[Response, int] | None:
    run_id = str(getattr(run, "run_id", "") or "")
    if bool(getattr(run, "lease_active", False)):
        return _a2a_error(
            "INVALID_REQUEST",
            "The task already has an active resume lease.",
            400,
            status_name="INVALID_ARGUMENT",
            metadata={"taskId": run_id},
        )
    status = str(getattr(run, "status", "") or "").upper()
    if status not in {"BLOCKED", "FAILED_RECOVERABLE"}:
        reason = (
            "INVALID_REQUEST"
            if status in {
                "RECEIVED",
                "SCOPING",
                "PLANNED",
                "QUEUED",
                "ASSIGNED",
                "RUNNING",
                "WAITING_FOR_TOOL",
                "WAITING_FOR_AGENT",
                "VERIFYING",
            }
            else "UNSUPPORTED_OPERATION"
        )
        message = (
            "The persisted task is still active and cannot be resumed concurrently."
            if reason == "INVALID_REQUEST"
            else "The persisted task is not eligible for another message."
        )
        return _a2a_error(
            reason,
            message,
            400,
            status_name="INVALID_ARGUMENT" if reason == "INVALID_REQUEST" else "FAILED_PRECONDITION",
            metadata={"taskId": run_id, "sovereignStatus": status},
        )
    if int(getattr(run, "iteration_count", 0) or 0) >= int(
        getattr(run, "max_iterations", 0) or 0
    ):
        return _a2a_error(
            "UNSUPPORTED_OPERATION",
            "The persisted task exhausted its bounded iteration budget.",
            400,
            status_name="FAILED_PRECONDITION",
            metadata={"taskId": run_id},
        )
    return None


def _execution_result_has_persisted_state(payload: Mapping[str, object]) -> bool:
    return bool(payload.get("status") and payload.get("evidenceId"))


def _execution_failure_response(
    payload: Mapping[str, object],
    status_code: int,
    *,
    fallback_message: str,
) -> tuple[Response, int]:
    safe_status = int(status_code) if 400 <= int(status_code) <= 599 else 500
    message = str(
        payload.get("error")
        or payload.get("reason")
        or payload.get("blocker")
        or fallback_message
    )[:1000]
    if safe_status < 500:
        return _a2a_error(
            "INVALID_REQUEST",
            message,
            400,
            status_name="INVALID_ARGUMENT",
        )
    return _a2a_error(
        "INTERNAL_ERROR",
        message,
        500,
        status_name="INTERNAL",
    )


def _resume_result_has_persisted_state(payload: Mapping[str, object]) -> bool:
    return bool(
        payload.get("resumed")
        and _execution_result_has_persisted_state(payload)
    )


def _resume_failure_response(
    payload: Mapping[str, object],
    status_code: int,
    *,
    run_id: str,
) -> tuple[Response, int]:
    safe_status = int(status_code) if 400 <= int(status_code) <= 599 else 503
    blocker = str(payload.get("blocker") or "").strip()
    message = str(
        payload.get("error")
        or payload.get("reason")
        or blocker
        or "The persisted task could not be resumed."
    )[:1000]
    if safe_status == 404:
        return _a2a_error(
            "TASK_NOT_FOUND",
            "The specified task does not exist or is not accessible.",
            404,
            metadata={"taskId": run_id},
        )
    if blocker in {"RUN_NOT_RESUMABLE", "RUN_ITERATION_LIMIT_EXHAUSTED"}:
        return _a2a_error(
            "UNSUPPORTED_OPERATION",
            message,
            400,
            status_name="FAILED_PRECONDITION",
            metadata={"taskId": run_id, "blocker": blocker},
        )
    if safe_status < 500:
        return _a2a_error(
            "INVALID_REQUEST",
            message,
            400,
            status_name="INVALID_ARGUMENT",
            metadata={"taskId": run_id, "blocker": blocker},
        )
    return _a2a_error(
        "INTERNAL_ERROR",
        message,
        500,
        status_name="INTERNAL",
        metadata={"taskId": run_id, "blocker": blocker},
    )


def _task_filter_digest(
    *,
    context_id: str,
    status_name: str,
    status_after: str,
    history_length: int,
    include_artifacts: bool,
) -> str:
    payload = json.dumps(
        {
            "contextId": context_id,
            "status": status_name,
            "statusTimestampAfter": status_after,
            "historyLength": history_length,
            "includeArtifacts": include_artifacts,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _decode_page_token(
    value: str,
    *,
    expected_filter_digest: str,
) -> tuple[str | None, str | None]:
    normalized = str(value or "").strip()
    if not normalized:
        return None, None
    try:
        padding = "=" * (-len(normalized) % 4)
        decoded = base64.urlsafe_b64decode((normalized + padding).encode("ascii")).decode("utf-8")
        payload = json.loads(decoded)
        updated_at = str(payload["updatedAt"])
        run_id = str(payload["runId"])
        filter_digest = str(payload["filterDigest"])
    except (KeyError, TypeError, ValueError, UnicodeError, binascii.Error, json.JSONDecodeError) as exc:
        raise ValueError("pageToken is invalid") from exc
    if filter_digest != expected_filter_digest:
        raise ValueError("pageToken does not match the active task filters")
    if not updated_at or not run_id:
        raise ValueError("pageToken cursor is incomplete")
    if not _A2A_TASK_ID_PATTERN.fullmatch(run_id):
        raise ValueError("pageToken task cursor is invalid")
    timestamp = Timestamp()
    try:
        timestamp.FromJsonString(updated_at.replace("+00:00", "Z"))
    except ValueError as exc:
        raise ValueError("pageToken timestamp cursor is invalid") from exc
    return timestamp.ToJsonString(), run_id


def _encode_page_token(run: object, *, filter_digest: str) -> str:
    payload = json.dumps(
        {
            "updatedAt": str(getattr(run, "updated_at", "") or ""),
            "runId": str(getattr(run, "run_id", "") or ""),
            "filterDigest": filter_digest,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def _parse_history_length(value: str | None, *, default: int) -> int:
    if value is None:
        return default
    try:
        requested = int(value)
    except ValueError as exc:
        raise ValueError("historyLength must be a non-negative integer") from exc
    if requested < 0:
        raise ValueError("historyLength must be a non-negative integer")
    return min(requested, 50)


def _parse_boolean(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError("includeArtifacts must be true or false")


def _parse_status_after(value: str | None) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    timestamp = Timestamp()
    try:
        timestamp.FromJsonString(normalized)
    except ValueError as exc:
        raise ValueError("statusTimestampAfter must be an ISO 8601 UTC timestamp") from exc
    return timestamp.ToJsonString()


def _task_with_history(
    *,
    get_connection: ConnectionFactory,
    user_id: str,
    run: object,
    history_length: int,
    include_artifact: bool,
):
    context_id = str(
        getattr(run, "a2a_context_id", None)
        or getattr(run, "session_key", "")
        or f"context-{getattr(run, 'run_id', '')}"
    )
    events = (
        _read_events(
            get_connection,
            user_id=user_id,
            run_id=str(getattr(run, "run_id", "")),
        )
        if history_length > 0
        else ()
    )
    history = task_history_from_events(
        events,
        context_id=context_id,
        run_status=getattr(run, "status", ""),
        limit=history_length,
    )
    return task_from_run(
        run,
        include_artifact=include_artifact,
        history=history,
    )


def _poll_interval_seconds() -> float:
    try:
        configured = float(os.getenv("SOVEREIGN_A2A_POLL_SECONDS", "0.25"))
    except ValueError:
        configured = 0.25
    return max(0.1, min(configured, 2.0))


def _stream_window_seconds() -> int:
    try:
        configured = int(os.getenv("SOVEREIGN_A2A_STREAM_WINDOW_SECONDS", "900"))
    except ValueError:
        configured = 900
    return max(30, min(configured, 3600))


def _sse(message: Any) -> str:
    payload = json.dumps(
        message_to_dict(message),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"data: {payload}\n\n"


def _stream_persisted_run(
    *,
    get_connection: ConnectionFactory,
    user_id: str,
    run_id: str,
    initial_run: object,
    worker_done: threading.Event | None = None,
    initial_event_ids: set[str] | None = None,
) -> Iterator[str]:
    context_id = str(
        getattr(initial_run, "a2a_context_id", None)
        or getattr(initial_run, "session_key", "")
        or f"context-{run_id}"
    )
    seen_event_ids: set[str] = set(initial_event_ids or ())
    last_snapshot = (
        str(getattr(initial_run, "status", "") or ""),
        str(getattr(initial_run, "evidence_id", "") or ""),
    )
    deadline = time.monotonic() + _stream_window_seconds()

    yield _sse(task_stream_response(task_from_run(initial_run, include_artifact=False)))

    while time.monotonic() < deadline:
        run = _read_run(get_connection, user_id=user_id, run_id=run_id)
        if run is None:
            return

        for event in _read_events(get_connection, user_id=user_id, run_id=run_id):
            event_id = str(event.get("event_id") or "")
            if not event_id or event_id in seen_event_ids:
                continue
            seen_event_ids.add(event_id)
            update = status_update_from_event(
                event,
                context_id=context_id,
                run_status=run.status,
            )
            yield _sse(status_stream_response(update))

        snapshot_key = (run.status, run.evidence_id)
        if snapshot_key != last_snapshot:
            last_snapshot = snapshot_key
            yield _sse(task_stream_response(task_from_run(run, include_artifact=True)))

        if is_terminal_or_interrupted(run.status):
            if worker_done is None or worker_done.is_set() or is_terminal_run_status(run.status):
                return
        if worker_done is not None and worker_done.is_set():
            return
        time.sleep(_poll_interval_seconds())

    final_run = _read_run(get_connection, user_id=user_id, run_id=run_id)
    if final_run is not None:
        yield _sse(task_stream_response(task_from_run(final_run, include_artifact=True)))


def _a2a_principal_guard(require_session, service_user_resolver: ServiceUserResolver | None):
    """Accept a normal owner session or the bounded internal owner service principal."""

    def decorate(handler):
        session_handler = require_session(handler)

        @wraps(handler)
        def guarded(*args, **kwargs):
            service_user_id = service_user_resolver() if service_user_resolver else None
            if service_user_id:
                request.session_user_id = service_user_id
                return handler(*args, **kwargs)
            return session_handler(*args, **kwargs)

        return guarded

    return decorate


def register_a2a_routes(
    app,
    *,
    require_session,
    get_connection: ConnectionFactory,
    start_run: StartRun,
    resume_run: ResumeRun,
    service_user_resolver: ServiceUserResolver | None = None,
) -> None:
    require_a2a_principal = _a2a_principal_guard(require_session, service_user_resolver)
    @app.route("/.well-known/agent-card.json", methods=["GET"])
    def sovereign_a2a_agent_card():
        base_url = os.getenv("SOVEREIGN_PUBLIC_BASE_URL", "").strip() or request.url_root.rstrip("/")
        card = build_sovereign_agent_card(
            base_url=base_url,
            manifest=manifest_payload(),
            version=os.getenv("SOVEREIGN_RELEASE_VERSION", "1.0.0").strip() or "1.0.0",
        )
        response = jsonify(message_to_dict(card))
        response.headers["Cache-Control"] = "public, max-age=300"
        return response

    @app.route("/a2a/v1/message:send", methods=["POST"])
    @require_a2a_principal
    def sovereign_a2a_send_message():
        version_error = _protocol_error()
        if version_error:
            return version_error
        try:
            request_message = parse_send_message(request.get_json(force=True) or {})
            mission, evidence, model = mission_from_a2a_request(request_message)
        except (TypeError, ValueError) as exc:
            return _a2a_error("INVALID_REQUEST", str(exc), 400)

        user_id = str(getattr(request, "session_user_id", "") or "")
        requested_task_id = str(request_message.message.task_id or "").strip()
        trace_id = f"trace-{uuid.uuid4().hex}"
        existing_run = None
        baseline_evidence_id = ""

        if requested_task_id:
            existing_run = _read_run(
                get_connection,
                user_id=user_id,
                run_id=requested_task_id,
            )
            if existing_run is None:
                return _a2a_error(
                    "TASK_NOT_FOUND",
                    "The specified task does not exist or is not accessible.",
                    404,
                    metadata={"taskId": requested_task_id},
                )
            precondition_error = _resume_precondition_error(existing_run)
            if precondition_error:
                return precondition_error
            try:
                _validate_follow_up_context(request_message, existing_run)
                follow_up_evidence = _follow_up_evidence(mission, evidence)
            except ValueError as exc:
                return _a2a_error("INVALID_REQUEST", str(exc), 400)
            run_id = requested_task_id
            session_key = ""
            a2a_context_id = _persisted_a2a_context(existing_run)
            baseline_evidence_id = str(existing_run.evidence_id or "")
        else:
            try:
                a2a_context_id = _a2a_context_id(request_message)
            except ValueError as exc:
                return _a2a_error("INVALID_REQUEST", str(exc), 400)
            run_id = f"run-{uuid.uuid4().hex}"
            session_key = f"session-{uuid.uuid4().hex}"
            follow_up_evidence = ""

        worker_done = threading.Event()
        worker_result: dict[str, object] = {}

        def execute() -> None:
            try:
                if requested_task_id:
                    payload, status_code = resume_run(
                        get_connection=get_connection,
                        user_id=user_id,
                        run_id=run_id,
                        evidence=follow_up_evidence,
                        model=model,
                        trace_id=trace_id,
                    )
                else:
                    payload, status_code = start_run(
                        get_connection=get_connection,
                        user_id=user_id,
                        mission=mission,
                        evidence=evidence,
                        model=model,
                        run_id=run_id,
                        session_key=session_key,
                        a2a_context_id=a2a_context_id,
                        trace_id=trace_id,
                    )
                worker_result["payload"] = payload
                worker_result["statusCode"] = status_code
            except Exception as exc:
                worker_result["errorType"] = type(exc).__name__
            finally:
                worker_done.set()

        threading.Thread(
            target=execute,
            name=f"sovereign-a2a-send-{run_id[-12:]}",
            daemon=True,
        ).start()

        run = existing_run
        persistence_deadline = time.monotonic() + 10.0
        while time.monotonic() < persistence_deadline:
            current_run = _read_run(
                get_connection,
                user_id=user_id,
                run_id=run_id,
            )
            if current_run is not None:
                run = current_run
                if not requested_task_id or str(current_run.evidence_id or "") != baseline_evidence_id:
                    break
            if worker_done.is_set():
                break
            time.sleep(0.02)

        raw_status = worker_result.get("statusCode")
        raw_payload = worker_result.get("payload")
        safe_payload = raw_payload if isinstance(raw_payload, Mapping) else {}
        if (
            requested_task_id
            and worker_done.is_set()
            and isinstance(raw_status, int)
            and raw_status >= 400
            and not _resume_result_has_persisted_state(safe_payload)
        ):
            return _resume_failure_response(
                safe_payload,
                raw_status,
                run_id=run_id,
            )

        if run is None:
            return _execution_failure_response(
                safe_payload,
                int(raw_status) if isinstance(raw_status, int) else 500,
                fallback_message="The Agents SDK run did not produce persisted truth-chain state.",
            )
        if requested_task_id and str(run.evidence_id or "") == baseline_evidence_id:
            return _a2a_error(
                "INTERNAL_ERROR",
                "The persisted task resume claim was not recorded before the response deadline.",
                500,
                status_name="INTERNAL",
                metadata={"taskId": run_id},
            )
        return _a2a_json(send_message_response(task_from_run(run)))

    @app.route("/a2a/v1/message:stream", methods=["POST"])
    @require_a2a_principal
    def sovereign_a2a_stream_message():
        version_error = _protocol_error()
        if version_error:
            return version_error
        try:
            request_message = parse_send_message(request.get_json(force=True) or {})
            mission, evidence, model = mission_from_a2a_request(request_message)
        except (TypeError, ValueError) as exc:
            return _a2a_error("INVALID_REQUEST", str(exc), 400)

        user_id = str(getattr(request, "session_user_id", "") or "")
        requested_task_id = str(request_message.message.task_id or "").strip()
        trace_id = f"trace-{uuid.uuid4().hex}"
        existing_run = None
        initial_event_ids: set[str] = set()

        if requested_task_id:
            existing_run = _read_run(
                get_connection,
                user_id=user_id,
                run_id=requested_task_id,
            )
            if existing_run is None:
                return _a2a_error(
                    "TASK_NOT_FOUND",
                    "The specified task does not exist or is not accessible.",
                    404,
                    metadata={"taskId": requested_task_id},
                )
            precondition_error = _resume_precondition_error(existing_run)
            if precondition_error:
                return precondition_error
            try:
                _validate_follow_up_context(request_message, existing_run)
                follow_up_evidence = _follow_up_evidence(mission, evidence)
            except ValueError as exc:
                return _a2a_error("INVALID_REQUEST", str(exc), 400)
            run_id = requested_task_id
            initial_event_ids = {
                str(event.get("event_id") or "")
                for event in _read_events(
                    get_connection,
                    user_id=user_id,
                    run_id=run_id,
                )
                if event.get("event_id")
            }
            session_key = ""
            a2a_context_id = _persisted_a2a_context(existing_run)
        else:
            try:
                a2a_context_id = _a2a_context_id(request_message)
            except ValueError as exc:
                return _a2a_error("INVALID_REQUEST", str(exc), 400)
            run_id = f"run-{uuid.uuid4().hex}"
            session_key = f"session-{uuid.uuid4().hex}"
            follow_up_evidence = ""

        worker_done = threading.Event()
        worker_result: dict[str, object] = {}

        def execute() -> None:
            try:
                if requested_task_id:
                    payload, status_code = resume_run(
                        get_connection=get_connection,
                        user_id=user_id,
                        run_id=run_id,
                        evidence=follow_up_evidence,
                        model=model,
                        trace_id=trace_id,
                    )
                else:
                    payload, status_code = start_run(
                        get_connection=get_connection,
                        user_id=user_id,
                        mission=mission,
                        evidence=evidence,
                        model=model,
                        run_id=run_id,
                        session_key=session_key,
                        a2a_context_id=a2a_context_id,
                        trace_id=trace_id,
                    )
                worker_result["payload"] = payload
                worker_result["statusCode"] = status_code
            except Exception as exc:  # shared helpers own bounded failure persistence
                worker_result["errorType"] = type(exc).__name__
            finally:
                worker_done.set()

        thread = threading.Thread(
            target=execute,
            name=f"sovereign-a2a-{run_id[-12:]}",
            daemon=True,
        )
        thread.start()

        initial_run = existing_run
        if requested_task_id and existing_run is not None:
            baseline_evidence_id = str(existing_run.evidence_id or "")
            claim_deadline = time.monotonic() + 1.0
            while time.monotonic() < claim_deadline:
                current_run = _read_run(
                    get_connection,
                    user_id=user_id,
                    run_id=run_id,
                )
                if current_run is not None:
                    initial_run = current_run
                    if str(current_run.evidence_id or "") != baseline_evidence_id:
                        break
                if worker_done.is_set():
                    break
                time.sleep(0.02)
            if worker_done.is_set():
                raw_status = worker_result.get("statusCode")
                raw_payload = worker_result.get("payload")
                safe_payload = raw_payload if isinstance(raw_payload, Mapping) else {}
                if (
                    isinstance(raw_status, int)
                    and raw_status >= 400
                    and not _resume_result_has_persisted_state(safe_payload)
                ):
                    return _resume_failure_response(
                        safe_payload,
                        raw_status,
                        run_id=run_id,
                    )
        else:
            persistence_deadline = time.monotonic() + 10.0
            while time.monotonic() < persistence_deadline:
                initial_run = _read_run(
                    get_connection,
                    user_id=user_id,
                    run_id=run_id,
                )
                if initial_run is not None:
                    break
                if worker_done.is_set():
                    break
                time.sleep(0.05)

        if worker_done.is_set():
            raw_status = worker_result.get("statusCode")
            raw_payload = worker_result.get("payload")
            safe_payload = raw_payload if isinstance(raw_payload, Mapping) else {}
            if (
                isinstance(raw_status, int)
                and raw_status >= 400
                and not _execution_result_has_persisted_state(safe_payload)
            ):
                return _execution_failure_response(
                    safe_payload,
                    raw_status,
                    fallback_message="The Agents SDK run could not persist a final task state.",
                )

        if initial_run is None:
            raw_status = worker_result.get("statusCode")
            raw_payload = worker_result.get("payload")
            safe_payload = raw_payload if isinstance(raw_payload, Mapping) else {}
            return _execution_failure_response(
                safe_payload,
                int(raw_status) if isinstance(raw_status, int) else 500,
                fallback_message="The Agents SDK run could not be persisted before streaming.",
            )

        response = Response(
            stream_with_context(_stream_persisted_run(
                get_connection=get_connection,
                user_id=user_id,
                run_id=run_id,
                initial_run=initial_run,
                worker_done=worker_done,
                initial_event_ids=initial_event_ids,
            )),
            status=200,
            content_type="text/event-stream",
        )
        response.headers["A2A-Version"] = A2A_PROTOCOL_VERSION
        response.headers["Cache-Control"] = "no-cache, no-transform"
        response.headers["X-Accel-Buffering"] = "no"
        return response

    @app.route("/a2a/v1/tasks/<run_id>", methods=["GET"])
    @require_a2a_principal
    def sovereign_a2a_get_task(run_id: str):
        version_error = _protocol_error()
        if version_error:
            return version_error
        try:
            history_length = _parse_history_length(
                request.args.get("historyLength"),
                default=50,
            )
        except ValueError as exc:
            return _a2a_error(
                "INVALID_REQUEST",
                str(exc),
                400,
                field_errors=[{
                    "field": "historyLength",
                    "description": str(exc),
                }],
            )
        user_id = str(getattr(request, "session_user_id", "") or "")
        run = _read_run(get_connection, user_id=user_id, run_id=run_id)
        if run is None:
            return _a2a_error(
                "TASK_NOT_FOUND",
                "The specified task does not exist or is not accessible.",
                404,
                metadata={"taskId": run_id},
            )
        return _a2a_json(_task_with_history(
            get_connection=get_connection,
            user_id=user_id,
            run=run,
            history_length=history_length,
            include_artifact=True,
        ))

    @app.route("/a2a/v1/tasks", methods=["GET"])
    @require_a2a_principal
    def sovereign_a2a_list_tasks():
        version_error = _protocol_error()
        if version_error:
            return version_error

        raw_page_size = request.args.get("pageSize")
        try:
            page_size = 50 if raw_page_size is None else int(raw_page_size)
        except ValueError:
            page_size = 0
        if not 1 <= page_size <= 100:
            return _a2a_error(
                "INVALID_REQUEST",
                "pageSize must be an integer between 1 and 100.",
                400,
                field_errors=[{
                    "field": "pageSize",
                    "description": "Must be an integer between 1 and 100.",
                }],
            )

        context_id = str(request.args.get("contextId") or "").strip()
        if len(context_id) > 500:
            return _a2a_error(
                "INVALID_REQUEST",
                "contextId exceeds the bounded input limit.",
                400,
                field_errors=[{
                    "field": "contextId",
                    "description": "Must not exceed 500 characters.",
                }],
            )
        status_name = str(request.args.get("status") or "").strip().upper()
        try:
            statuses = (
                ()
                if status_name in {"", "TASK_STATE_UNSPECIFIED"}
                else run_statuses_for_task_state(status_name)
            )
            history_length = _parse_history_length(
                request.args.get("historyLength"),
                default=0,
            )
            include_artifacts = _parse_boolean(
                request.args.get("includeArtifacts"),
                default=False,
            )
            status_after = _parse_status_after(
                request.args.get("statusTimestampAfter")
            )
        except ValueError as exc:
            return _a2a_error(
                "INVALID_REQUEST",
                str(exc),
                400,
            )

        no_status_matches = bool(status_name) and status_name != "TASK_STATE_UNSPECIFIED" and not statuses
        filter_digest = _task_filter_digest(
            context_id=context_id,
            status_name=status_name,
            status_after=status_after,
            history_length=history_length,
            include_artifacts=include_artifacts,
        )
        try:
            cursor_updated_at, cursor_run_id = _decode_page_token(
                str(request.args.get("pageToken") or ""),
                expected_filter_digest=filter_digest,
            )
        except ValueError as exc:
            return _a2a_error(
                "INVALID_REQUEST",
                str(exc),
                400,
                field_errors=[{
                    "field": "pageToken",
                    "description": str(exc),
                }],
            )

        user_id = str(getattr(request, "session_user_id", "") or "")
        if no_status_matches:
            total_size = 0
            runs = ()
        else:
            conn = get_connection()
            try:
                total_size = count_agent_runs(
                    conn,
                    user_id=user_id,
                    context_id=context_id or None,
                    statuses=statuses,
                    status_after=status_after or None,
                )
                runs = list_agent_runs(
                    conn,
                    user_id=user_id,
                    limit=page_size + 1,
                    context_id=context_id or None,
                    statuses=statuses,
                    status_after=status_after or None,
                    cursor_updated_at=cursor_updated_at,
                    cursor_run_id=cursor_run_id,
                )
            finally:
                _close_connection(conn)

        has_more = len(runs) > page_size
        page_runs = tuple(runs[:page_size])
        tasks = [
            _task_with_history(
                get_connection=get_connection,
                user_id=user_id,
                run=run,
                history_length=history_length,
                include_artifact=include_artifacts,
            )
            for run in page_runs
        ]
        next_page_token = (
            _encode_page_token(page_runs[-1], filter_digest=filter_digest)
            if has_more and page_runs
            else ""
        )
        response_message = ListTasksResponse(
            tasks=tasks,
            next_page_token=next_page_token,
            page_size=page_size,
            total_size=total_size,
        )
        response_payload = message_to_dict(response_message)
        response_payload["nextPageToken"] = next_page_token
        response_payload["pageSize"] = page_size
        response_payload["totalSize"] = total_size
        response = jsonify(response_payload)
        response.headers["Content-Type"] = A2A_MEDIA_TYPE
        response.headers["A2A-Version"] = A2A_PROTOCOL_VERSION
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.route("/a2a/v1/tasks/<run_id>:subscribe", methods=["GET", "POST"])
    @require_a2a_principal
    def sovereign_a2a_subscribe_task(run_id: str):
        version_error = _protocol_error()
        if version_error:
            return version_error
        user_id = str(getattr(request, "session_user_id", "") or "")
        run = _read_run(get_connection, user_id=user_id, run_id=run_id)
        if run is None:
            return _a2a_error(
                "TASK_NOT_FOUND",
                "The specified task does not exist or is not accessible.",
                404,
                metadata={"taskId": run_id},
            )
        if is_terminal_run_status(run.status):
            return _a2a_error(
                "UNSUPPORTED_OPERATION",
                "A terminal task cannot be subscribed to.",
                400,
                status_name="FAILED_PRECONDITION",
                metadata={"taskId": run_id},
            )
        initial_event_ids = {
            str(event.get("event_id") or "")
            for event in _read_events(
                get_connection,
                user_id=user_id,
                run_id=run_id,
            )
            if event.get("event_id")
        }
        response = Response(
            stream_with_context(_stream_persisted_run(
                get_connection=get_connection,
                user_id=user_id,
                run_id=run_id,
                initial_run=run,
                initial_event_ids=initial_event_ids,
            )),
            status=200,
            content_type="text/event-stream",
        )
        response.headers["A2A-Version"] = A2A_PROTOCOL_VERSION
        response.headers["Cache-Control"] = "no-cache, no-transform"
        response.headers["X-Accel-Buffering"] = "no"
        return response

    @app.route("/a2a/v1/tasks/<run_id>:cancel", methods=["POST"])
    @require_a2a_principal
    def sovereign_a2a_cancel_task(run_id: str):
        version_error = _protocol_error()
        if version_error:
            return version_error
        user_id = str(getattr(request, "session_user_id", "") or "")
        run = _read_run(get_connection, user_id=user_id, run_id=run_id)
        if run is None:
            return _a2a_error(
                "TASK_NOT_FOUND",
                "The specified task does not exist or is not accessible.",
                404,
                metadata={"taskId": run_id},
            )
        return _a2a_error(
            "TASK_NOT_CANCELABLE",
            "No evidence-backed cancellation transition exists for this persisted run.",
            400,
            status_name="FAILED_PRECONDITION",
            metadata={"taskId": run_id},
        )
