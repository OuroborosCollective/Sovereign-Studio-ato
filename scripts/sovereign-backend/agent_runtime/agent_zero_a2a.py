"""Nonblocking Agent Zero A2A transport for one Sovereign repository job.

This module is deliberately narrower than ``agent_zero_runtime``.  It does not
participate in the cognitive swarm and it does not grant Agent Zero any Sovereign
authority.  It submits exactly one bounded A2A task and later reads that task.
The protected Agent Zero token is transported only in headers.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Final, Mapping
import uuid

import requests

from .agent_zero_runtime import AgentZeroRuntimeConfig, AgentZeroRuntimeError
from .contracts import sanitize_agent_text


_A2A_TASK_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")
_A2A_WORKSPACE_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._-]{1,160}$")
_A2A_CALL_TIMEOUT_SECONDS: Final[int] = 30
_AGENT_ZERO_WORKSPACE_ROOT: Final[str] = "/a0/sovereign-workspaces"

_A2A_ACTIVE_STATES: Final[frozenset[str]] = frozenset({"submitted", "working"})
_A2A_COMPLETED_STATES: Final[frozenset[str]] = frozenset({"completed"})
_A2A_INTERRUPTED_STATES: Final[frozenset[str]] = frozenset({
    "input_required",
    "auth_required",
})
_A2A_FAILED_STATES: Final[frozenset[str]] = frozenset({
    "failed",
    "canceled",
    "rejected",
})


class AgentZeroA2AError(RuntimeError):
    """Secret-safe A2A transport/contract failure."""

    def __init__(self, family: str, next_action: str, *, http_status: int | None = None) -> None:
        super().__init__(family)
        self.family = str(family)[:160]
        self.next_action = str(next_action)[:240]
        self.http_status = int(http_status) if isinstance(http_status, int) else None


class AgentZeroA2ASubmitOutcomeUnknown(AgentZeroA2AError):
    """The client cannot prove whether ``message/send`` created a task."""


class AgentZeroA2ATaskLost(AgentZeroA2AError):
    """A previously persisted task id no longer exists in Agent Zero."""


@dataclass(frozen=True, slots=True)
class AgentZeroA2ATask:
    task_id: str
    state: str

    @property
    def active(self) -> bool:
        return self.state in _A2A_ACTIVE_STATES

    @property
    def completed(self) -> bool:
        return self.state in _A2A_COMPLETED_STATES

    @property
    def interrupted(self) -> bool:
        return self.state in _A2A_INTERRUPTED_STATES

    @property
    def failed(self) -> bool:
        return self.state in _A2A_FAILED_STATES


def _normalize_task_id(value: object) -> str:
    task_id = str(value or "").strip()
    if not _A2A_TASK_ID_RE.fullmatch(task_id):
        raise AgentZeroA2AError(
            "AGENT_ZERO_A2A_TASK_ID_INVALID",
            "VERIFY_AGENT_ZERO_A2A_TASK_ID_CONTRACT",
        )
    return task_id


def _normalize_state(value: object) -> str:
    state = str(value or "").strip().lower().replace("-", "_")
    state = state.removeprefix("task_state_")
    if state not in (_A2A_ACTIVE_STATES | _A2A_COMPLETED_STATES | _A2A_INTERRUPTED_STATES | _A2A_FAILED_STATES):
        raise AgentZeroA2AError(
            "AGENT_ZERO_A2A_TASK_STATE_INVALID",
            "VERIFY_AGENT_ZERO_A2A_TASK_STATE_CONTRACT",
        )
    return state


def _task_payload(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AgentZeroA2AError(
            "AGENT_ZERO_A2A_RESPONSE_INVALID",
            "VERIFY_AGENT_ZERO_A2A_RESPONSE_CONTRACT",
        )
    nested = value.get("task")
    return nested if isinstance(nested, Mapping) else value


def _parse_task(value: object) -> AgentZeroA2ATask:
    task = _task_payload(value)
    task_id = _normalize_task_id(task.get("id") or task.get("taskId") or task.get("task_id"))
    status = task.get("status")
    state_value = status.get("state") if isinstance(status, Mapping) else task.get("state")
    return AgentZeroA2ATask(task_id=task_id, state=_normalize_state(state_value))


def build_repository_task_prompt(*, workspace_id: str, mission: str) -> str:
    """Build the bounded single-task contract for the shared workspace."""

    normalized_workspace = str(workspace_id or "").strip()
    if not _A2A_WORKSPACE_ID_RE.fullmatch(normalized_workspace):
        raise AgentZeroA2AError(
            "AGENT_ZERO_A2A_WORKSPACE_ID_INVALID",
            "USE_PERSISTED_SOVEREIGN_WORKSPACE_ID",
        )
    clean_mission = sanitize_agent_text(str(mission or ""), 8000)
    if not clean_mission or clean_mission != str(mission or "").strip():
        raise AgentZeroA2AError(
            "AGENT_ZERO_A2A_MISSION_INVALID",
            "REMOVE_SECRET_OR_UNBOUNDED_MISSION_TEXT",
        )
    workspace = f"{_AGENT_ZERO_WORKSPACE_ROOT}/{normalized_workspace}/repo"
    return (
        "You are exactly one Agent Zero implementation task for Sovereign Studio ATO.\n"
        f"Use only this already-cloned shared repository workspace: {workspace}\n"
        "Do not clone or replace the repository. Do not push to GitHub, create or merge a PR, deploy, "
        "mutate a database, inspect or disclose secrets, or claim Sovereign evidence/success. "
        "You may read and modify files only inside the stated workspace and may run local implementation tools/tests there. "
        "Keep the change bounded to the mission. Leave all GitHub publication, evidence verdicts and completion decisions to Sovereign.\n\n"
        f"Mission:\n{clean_mission}"
    )


class AgentZeroA2AClient:
    """Minimal JSON-RPC A2A client for ``message/send`` and ``tasks/get``."""

    def __init__(self, config: AgentZeroRuntimeConfig) -> None:
        self.config = config

    @classmethod
    def from_env(cls) -> "AgentZeroA2AClient":
        try:
            return cls(AgentZeroRuntimeConfig.from_env())
        except AgentZeroRuntimeError as exc:
            raise AgentZeroA2AError(exc.family, exc.next_action, http_status=exc.http_status) from exc

    def _headers(self) -> dict[str, str]:
        try:
            token = self.config.read_protected_key()
        except AgentZeroRuntimeError as exc:
            raise AgentZeroA2AError(exc.family, exc.next_action, http_status=exc.http_status) from exc
        return {
            "Authorization": f"Bearer {token}",
            "X-API-KEY": token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    @property
    def endpoint(self) -> str:
        return f"{self.config.base_url.rstrip('/')}/a2a"

    def _post_rpc(self, payload: dict[str, Any], *, submit: bool) -> Mapping[str, Any]:
        try:
            response = requests.post(
                self.endpoint,
                headers=self._headers(),
                json=payload,
                timeout=min(self.config.timeout_seconds, _A2A_CALL_TIMEOUT_SECONDS),
                allow_redirects=False,
            )
        except (requests.Timeout, requests.ConnectionError, requests.RequestException) as exc:
            if submit:
                raise AgentZeroA2ASubmitOutcomeUnknown(
                    "AGENT_ZERO_A2A_SUBMIT_OUTCOME_UNKNOWN",
                    "DO_NOT_RESUBMIT_UNTIL_TASK_ACCEPTANCE_CAN_BE_PROVEN",
                ) from exc
            raise AgentZeroA2AError(
                "AGENT_ZERO_A2A_READ_UNAVAILABLE",
                "RETRY_TASK_READBACK_WITHOUT_RESUBMITTING",
            ) from exc

        if response.status_code == 404 and not submit:
            raise AgentZeroA2ATaskLost(
                "AGENT_ZERO_A2A_TASK_LOST",
                "USE_SINGLE_ATOMIC_RESTART_RECOVERY",
                http_status=404,
            )
        if not 200 <= response.status_code < 300:
            family = (
                "AGENT_ZERO_A2A_AUTHENTICATION_FAILED"
                if response.status_code in {401, 403}
                else "AGENT_ZERO_A2A_UPSTREAM_UNAVAILABLE"
                if response.status_code >= 500
                else "AGENT_ZERO_A2A_REQUEST_REJECTED"
            )
            raise AgentZeroA2AError(
                family,
                "VERIFY_AGENT_ZERO_A2A_RUNTIME_AND_CONTRACT",
                http_status=response.status_code,
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise AgentZeroA2AError(
                "AGENT_ZERO_A2A_RESPONSE_INVALID",
                "VERIFY_AGENT_ZERO_A2A_JSON_RESPONSE",
                http_status=response.status_code,
            ) from exc
        if not isinstance(body, Mapping):
            raise AgentZeroA2AError(
                "AGENT_ZERO_A2A_RESPONSE_INVALID",
                "VERIFY_AGENT_ZERO_A2A_JSON_RESPONSE",
                http_status=response.status_code,
            )
        error = body.get("error")
        if isinstance(error, Mapping):
            message = str(error.get("message") or "").casefold()
            if not submit and "not found" in message:
                raise AgentZeroA2ATaskLost(
                    "AGENT_ZERO_A2A_TASK_LOST",
                    "USE_SINGLE_ATOMIC_RESTART_RECOVERY",
                    http_status=response.status_code,
                )
            raise AgentZeroA2AError(
                "AGENT_ZERO_A2A_RPC_ERROR",
                "VERIFY_AGENT_ZERO_A2A_JSON_RPC_CONTRACT",
                http_status=response.status_code,
            )
        result = body.get("result")
        if not isinstance(result, Mapping):
            raise AgentZeroA2AError(
                "AGENT_ZERO_A2A_RESPONSE_INVALID",
                "VERIFY_AGENT_ZERO_A2A_RESULT_CONTRACT",
                http_status=response.status_code,
            )
        return result

    def submit_repository_task(self, *, workspace_id: str, mission: str) -> AgentZeroA2ATask:
        prompt = build_repository_task_prompt(workspace_id=workspace_id, mission=mission)
        call_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": call_id,
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": f"sovereign-{call_id}",
                    "kind": "message",
                    "role": "user",
                    "parts": [{"kind": "text", "text": prompt}],
                },
                "configuration": {
                    "acceptedOutputModes": ["text", "text/plain"],
                    "blocking": False,
                },
            },
        }
        return _parse_task(self._post_rpc(payload, submit=True))

    def get_task(self, task_id: str) -> AgentZeroA2ATask:
        normalized_task_id = _normalize_task_id(task_id)
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tasks/get",
            "params": {"id": normalized_task_id},
        }
        task = _parse_task(self._post_rpc(payload, submit=False))
        if task.task_id != normalized_task_id:
            raise AgentZeroA2AError(
                "AGENT_ZERO_A2A_TASK_ID_MISMATCH",
                "FAIL_CLOSED_ON_A2A_TASK_IDENTITY_MISMATCH",
            )
        return task
