"""Bounded A2A live evidence client for the Sovereign truth chain."""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

import requests

from owner_input_client import ControllerRuntimeClient

A2A_VERSION = "1.0"
A2A_MEDIA_TYPE = "application/a2a+json"
RUN_ID_RE = re.compile(r"^run-[0-9a-f]{32}$")
TERMINAL_STATES = frozenset({
    "TASK_STATE_COMPLETED",
    "TASK_STATE_FAILED",
    "TASK_STATE_CANCELED",
    "TASK_STATE_INPUT_REQUIRED",
    "TASK_STATE_REJECTED",
    "TASK_STATE_AUTH_REQUIRED",
})
STATUS_MAP = {
    "RECEIVED": "TASK_STATE_SUBMITTED",
    "SCOPING": "TASK_STATE_SUBMITTED",
    "PLANNED": "TASK_STATE_SUBMITTED",
    "QUEUED": "TASK_STATE_SUBMITTED",
    "ASSIGNED": "TASK_STATE_SUBMITTED",
    "RUNNING": "TASK_STATE_WORKING",
    "WAITING_FOR_TOOL": "TASK_STATE_WORKING",
    "WAITING_FOR_AGENT": "TASK_STATE_WORKING",
    "VERIFYING": "TASK_STATE_WORKING",
    "WAITING_FOR_OWNER": "TASK_STATE_INPUT_REQUIRED",
    "BLOCKED": "TASK_STATE_INPUT_REQUIRED",
    "FAILED_RECOVERABLE": "TASK_STATE_INPUT_REQUIRED",
    "READY_FOR_DRAFT_PR": "TASK_STATE_INPUT_REQUIRED",
    "DRAFT_PR_CREATED": "TASK_STATE_COMPLETED",
    "COMPLETED": "TASK_STATE_COMPLETED",
    "FAILED_FINAL": "TASK_STATE_FAILED",
}


class A2ARuntimeClient(ControllerRuntimeClient):
    """Transport A2A messages and compare them with controller evidence."""

    def _a2a_headers(self, authorized: bool = True) -> dict[str, str]:
        headers = {
            "A2A-Version": A2A_VERSION,
            "Accept": f"{A2A_MEDIA_TYPE}, application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if authorized:
            headers.update(self._headers())
            headers["A2A-Version"] = A2A_VERSION
            headers["Accept"] = f"{A2A_MEDIA_TYPE}, application/json, text/event-stream"
        return headers

    def _json_request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        expected: tuple[int, ...] = (200,),
        authorized: bool = True,
        timeout: int = 60,
    ) -> tuple[dict[str, Any], requests.Response]:
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                headers=self._a2a_headers(authorized),
                json=body,
                timeout=max(1, min(int(timeout), 1200)),
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"A2A backend unavailable: {type(exc).__name__}") from exc
        if response.status_code not in expected:
            reason = ""
            try:
                error_payload = response.json()
            except ValueError:
                error_payload = {}
            if isinstance(error_payload, dict):
                error = error_payload.get("error")
                if isinstance(error, dict):
                    details = error.get("details")
                    if isinstance(details, list) and details and isinstance(details[0], dict):
                        reason = str(details[0].get("reason") or "").strip()
                    if not reason:
                        reason = str(error.get("status") or "").strip()
            suffix = f" ({reason[:120]})" if reason else ""
            raise RuntimeError(
                f"A2A backend returned HTTP {response.status_code}{suffix}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("A2A backend returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("A2A backend returned a non-object payload")
        return payload, response

    @staticmethod
    def _message(
        text: str,
        *,
        context_id: str,
        task_id: str = "",
        evidence: str = "",
    ) -> dict[str, Any]:
        message: dict[str, Any] = {
            "messageId": f"message-{uuid.uuid4().hex}",
            "contextId": context_id,
            "role": "ROLE_USER",
            "parts": [{"text": text[:20_000], "mediaType": "text/plain"}],
            # A transport canary must not force a model alias. The backend owns
            # the currently allowlisted Agents SDK default and rejects aliases
            # that are healthy in LiteLLM but not enabled for this runtime.
            "metadata": {"evidence": evidence[:250_000]},
        }
        if task_id:
            message["taskId"] = task_id
        return {"message": message}

    @staticmethod
    def _task(payload: dict[str, Any]) -> dict[str, Any]:
        task = payload.get("task")
        if isinstance(task, dict):
            return task
        if (
            isinstance(payload.get("id"), str)
            and isinstance(payload.get("contextId"), str)
            and isinstance(payload.get("status"), dict)
        ):
            return payload
        raise RuntimeError("A2A response has no task")

    @staticmethod
    def _state(task: dict[str, Any]) -> str:
        status = task.get("status") if isinstance(task.get("status"), dict) else {}
        return str(status.get("state") or "")

    def _get_task(self, run_id: str) -> dict[str, Any]:
        payload, response = self._json_request(
            "GET", f"/a2a/v1/tasks/{run_id}?historyLength=50", timeout=30
        )
        if response.headers.get("A2A-Version") != A2A_VERSION:
            raise RuntimeError("A2A task read did not confirm protocol version")
        return self._task(payload)

    def _stream(self, run_id: str, timeout: int = 240) -> dict[str, Any]:
        try:
            response = self.session.request(
                "GET",
                f"{self.base_url}/a2a/v1/tasks/{run_id}:subscribe",
                headers=self._a2a_headers(),
                stream=True,
                timeout=max(10, min(int(timeout), 600)),
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"A2A stream unavailable: {type(exc).__name__}") from exc
        if response.status_code == 400:
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            details = ((payload.get("error") or {}).get("details") or []) if isinstance(payload, dict) else []
            reason = str(details[0].get("reason") or "") if details and isinstance(details[0], dict) else ""
            if reason == "UNSUPPORTED_OPERATION":
                return {"eventCount": 0, "states": [], "terminalBeforeSubscribe": True}
        if response.status_code != 200:
            raise RuntimeError(f"A2A stream returned HTTP {response.status_code}")
        if response.headers.get("A2A-Version") != A2A_VERSION:
            raise RuntimeError("A2A stream did not confirm protocol version")
        states: list[str] = []
        event_count = 0
        for raw_line in response.iter_lines(decode_unicode=True):
            line = str(raw_line or "").strip()
            if not line.startswith("data: "):
                continue
            try:
                event = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            event_count += 1
            task = event.get("task") if isinstance(event.get("task"), dict) else {}
            update = event.get("statusUpdate") if isinstance(event.get("statusUpdate"), dict) else {}
            status = task.get("status") if isinstance(task.get("status"), dict) else {}
            if not status and isinstance(update.get("status"), dict):
                status = update["status"]
            state = str(status.get("state") or "")
            if state and (not states or states[-1] != state):
                states.append(state)
            if state in TERMINAL_STATES:
                break
        return {"eventCount": event_count, "states": states[-20:], "terminalBeforeSubscribe": False}

    def _await_final(self, run_id: str, timeout: int = 300) -> tuple[dict[str, Any], dict[str, Any]]:
        deadline = time.monotonic() + max(10, min(int(timeout), 600))
        task: dict[str, Any] = {}
        controller: dict[str, Any] = {}
        while time.monotonic() < deadline:
            task = self._get_task(run_id)
            controller = self.run_status(run_id)
            run = controller.get("run") if isinstance(controller.get("run"), dict) else {}
            controller_status = str(run.get("status") or "")
            if self._state(task) in TERMINAL_STATES or controller_status in {
                "BLOCKED", "FAILED_RECOVERABLE", "FAILED_FINAL", "WAITING_FOR_OWNER",
                "READY_FOR_DRAFT_PR", "DRAFT_PR_CREATED", "COMPLETED",
            }:
                return task, controller
            time.sleep(0.5)
        return task, controller

    def live_canary(self, expected_revision: str = "") -> dict[str, Any]:
        revision = str(expected_revision or "").strip()
        if revision and not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("expected_revision must be a full commit SHA")
        card, card_response = self._json_request(
            "GET", "/.well-known/agent-card.json", authorized=False, timeout=30
        )
        interfaces = card.get("supportedInterfaces") if isinstance(card.get("supportedInterfaces"), list) else []
        interface = interfaces[0] if interfaces and isinstance(interfaces[0], dict) else {}
        capabilities = card.get("capabilities") if isinstance(card.get("capabilities"), dict) else {}
        card_verified = bool(
            card_response.status_code == 200
            and str(interface.get("protocolVersion") or "") == A2A_VERSION
            and str(interface.get("url") or "").endswith("/a2a/v1")
            and capabilities.get("streaming") is True
        )
        if not card_verified:
            raise RuntimeError("A2A AgentCard contract is incomplete")

        context_id = f"context-canary-{uuid.uuid4().hex}"
        initial, response = self._json_request(
            "POST",
            "/a2a/v1/message:send",
            body=self._message(
                "Evaluate this transport canary from persisted evidence only. Do not change the repository or runtime. Completion requires protocol, access, task identity, event persistence and streaming evidence for one run. Stay blocked while correlation evidence is missing.",
                context_id=context_id,
                evidence=(
                    "AgentCard protocol 1.0 and streaming were observed. "
                    f"Expected revision: {revision or 'not supplied'}. "
                    "Task correlation is pending."
                ),
            ),
            timeout=60,
        )
        if response.headers.get("A2A-Version") != A2A_VERSION:
            raise RuntimeError("A2A message send did not confirm protocol version")
        initial_task = self._task(initial)
        run_id = str(initial_task.get("id") or "")
        if not RUN_ID_RE.fullmatch(run_id):
            raise RuntimeError("A2A start did not return a valid task id")
        if str(initial_task.get("contextId") or "") != context_id:
            raise RuntimeError("A2A start did not preserve the context id")

        unauthenticated = self.session.request(
            "GET",
            f"{self.base_url}/a2a/v1/tasks/{run_id}",
            headers=self._a2a_headers(False),
            timeout=30,
        )
        owner_scope_verified = unauthenticated.status_code == 401
        if not owner_scope_verified:
            raise RuntimeError("A2A task access boundary is not enforced")

        stream_evidence: dict[str, Any] = self._stream(run_id)
        final_task, controller = self._await_final(run_id)
        run = controller.get("run") if isinstance(controller.get("run"), dict) else {}
        events = controller.get("events") if isinstance(controller.get("events"), list) else []
        controller_status = str(run.get("status") or "")
        context_snapshot = run.get("context_snapshot") if isinstance(run.get("context_snapshot"), dict) else {}
        same_run = bool(
            str(final_task.get("id") or "") == run_id
            and str(run.get("run_id") or "") == run_id
            and str(final_task.get("contextId") or "") == context_id
            and str(context_snapshot.get("a2aContextId") or "") == context_id
        )
        projected = STATUS_MAP.get(controller_status) == self._state(final_task)
        persisted_events = bool(events)

        resume_attempted = controller_status in {"BLOCKED", "FAILED_RECOVERABLE"}
        resume_verified = False
        if resume_attempted:
            before_iteration = int(run.get("iteration_count") or 0)
            correlation = json.dumps({
                "agentCardProtocol": A2A_VERSION,
                "accessBoundary": owner_scope_verified,
                "sameRun": same_run,
                "eventCount": len(events),
                "streamEventCount": int(stream_evidence.get("eventCount") or 0),
                "streamStates": stream_evidence.get("states") or [],
                "expectedRevision": revision or None,
            }, sort_keys=True)
            follow_up, follow_response = self._json_request(
                "POST",
                "/a2a/v1/message:send",
                body=self._message(
                    "Continue the same task with the observed transport evidence. Keep the run read-only.",
                    context_id=context_id,
                    task_id=run_id,
                    evidence=correlation,
                ),
                timeout=60,
            )
            if follow_response.headers.get("A2A-Version") != A2A_VERSION:
                raise RuntimeError("A2A resume did not confirm protocol version")
            if str(self._task(follow_up).get("id") or "") != run_id:
                raise RuntimeError("A2A resume returned a different task id")
            resume_stream = self._stream(run_id)
            final_task, controller = self._await_final(run_id)
            run = controller.get("run") if isinstance(controller.get("run"), dict) else {}
            events = controller.get("events") if isinstance(controller.get("events"), list) else []
            resume_verified = bool(
                int(run.get("iteration_count") or 0) > before_iteration
                and any(isinstance(item, dict) and item.get("type") == "run_resumed" for item in events)
            )
            stream_evidence = {"initial": stream_evidence, "resume": resume_stream}

        final_status = str(run.get("status") or "")
        final_state = self._state(final_task)
        same_run = bool(
            str(final_task.get("id") or "") == run_id
            and str(run.get("run_id") or "") == run_id
            and str(final_task.get("contextId") or "") == context_id
        )
        projected = STATUS_MAP.get(final_status) == final_state
        stream_observed = bool(
            stream_evidence.get("eventCount")
            or stream_evidence.get("terminalBeforeSubscribe")
            or (isinstance(stream_evidence.get("initial"), dict) and (
                stream_evidence["initial"].get("eventCount")
                or stream_evidence["initial"].get("terminalBeforeSubscribe")
            ))
            or (isinstance(stream_evidence.get("resume"), dict) and (
                stream_evidence["resume"].get("eventCount")
                or stream_evidence["resume"].get("terminalBeforeSubscribe")
            ))
        )
        ok = bool(card_verified and owner_scope_verified and same_run and projected and persisted_events and stream_observed)
        return {
            "ok": ok,
            "status": "A2A_LIVE_CANARY_VERIFIED" if ok else "A2A_LIVE_CANARY_INCOMPLETE",
            "protocolVersion": A2A_VERSION,
            "agentCardVerified": card_verified,
            "ownerScopeVerified": owner_scope_verified,
            "runId": run_id,
            "contextId": context_id,
            "samePersistedRunVerified": same_run,
            "statusProjectionVerified": projected,
            "persistedEventCount": len(events),
            "streamEvidence": stream_evidence,
            "resumeAttempted": resume_attempted,
            "resumeVerified": resume_verified,
            "finalControllerStatus": final_status,
            "finalA2ATaskState": final_state,
            "expectedRevision": revision or None,
            "repositoryMutationPerformed": False,
            "protectedValuesReturned": False,
            "rawModelOutputReturned": False,
        }
