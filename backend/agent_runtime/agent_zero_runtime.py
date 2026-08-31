"""Owner-scoped Agent Zero capability expansion for Sovereign.

Agent Zero is deliberately an external capability worker, never a Sovereign truth
or effect authority. The adapter can use Agent Zero skills, browser/Playwright,
memory and sandbox tools, but every result remains non-authoritative external
evidence. GitHub/VPS/database/deploy/payment/account effects stay in Sovereign.

The Agent Zero API key is read request-locally from the protected owner-input
filesystem and is never persisted, logged, returned or embedded in tool arguments.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import hmac
import importlib
import json
import os
from pathlib import Path
import re
from threading import Lock
from typing import Any, Callable, Final, Mapping
from urllib.parse import urlsplit
import uuid

import requests

from .cognitive_run_store import record_external_action_event
from .contracts import sanitize_agent_text


ConnectionFactory = Callable[[], Any]

_AGENT_ZERO_DEFAULT_BASE_URL: Final[str] = "https://agent-zero-xrev.srv1491137.hstgr.cloud"
_AGENT_ZERO_KEY_FILENAME: Final[str] = "agent_zero_api_key.txt"
_AGENT_ZERO_KEY_MIN_BYTES: Final[int] = 16
_AGENT_ZERO_KEY_MAX_BYTES: Final[int] = 8192
_AGENT_ZERO_RESPONSE_LIMIT: Final[int] = 8000
_AGENT_ZERO_LOG_LENGTH: Final[int] = 120
_AGENT_ZERO_PROJECT_PREFIX: Final[str] = "sovereign-u-"

_ALLOWED_CAPABILITIES: Final[frozenset[str]] = frozenset({
    "skills",
    "browser",
    "playwright",
    "memory_recall",
    "memory_remember",
    "sleep_remember",
    "code_execution",
    "research",
    "computer",
    "mcp",
})

_ROLE_CAPABILITIES: Final[dict[str, frozenset[str]]] = {
    "free_single_agent": _ALLOWED_CAPABILITIES,
    "data_storage": frozenset({"skills", "memory_recall", "research"}),
    "business_core": frozenset({"skills", "memory_recall", "research"}),
    "endpoint_bridge": frozenset({"skills", "research", "mcp"}),
    "chat_cognitive": frozenset({
        "skills", "memory_recall", "memory_remember", "sleep_remember", "research",
    }),
    "ui_accessibility": frozenset({"skills", "browser", "playwright", "computer", "research"}),
    "predictive_qa": frozenset({"skills", "browser", "playwright", "code_execution", "research"}),
}

_KNOWN_TOOL_NAMES: Final[tuple[str, ...]] = (
    "skills_tool",
    "browser_agent",
    "browser",
    "memory_load",
    "memory_save",
    "memory_delete",
    "memory_forget",
    "code_execution_tool",
    "search_engine",
    "document_query",
    "a2a_chat",
    "computer_use",
    "computer",
    "mcp_tool",
    "mcp",
)


class AgentZeroRuntimeError(RuntimeError):
    """Secret-safe external capability failure."""

    def __init__(self, family: str, next_action: str, *, http_status: int | None = None) -> None:
        super().__init__(family)
        self.family = str(family)[:160]
        self.next_action = str(next_action)[:240]
        self.http_status = int(http_status) if isinstance(http_status, int) else None

    def safe_payload(self) -> dict[str, object]:
        return {
            "ok": False,
            "runtime": "agent-zero",
            "failureFamily": self.family,
            "nextAction": self.next_action,
            "httpStatus": self.http_status,
            "authoritative": False,
            "secretValuesReturned": False,
        }


@dataclass(frozen=True, slots=True)
class AgentZeroRuntimeConfig:
    base_url: str
    protected_key_path: Path
    timeout_seconds: int
    agent_profile: str = ""

    @classmethod
    def from_env(cls) -> "AgentZeroRuntimeConfig":
        raw_base = str(
            os.getenv("SOVEREIGN_AGENT_ZERO_BASE_URL", _AGENT_ZERO_DEFAULT_BASE_URL)
        ).strip().rstrip("/")
        try:
            parsed = urlsplit(raw_base)
        except ValueError as exc:
            raise AgentZeroRuntimeError(
                "AGENT_ZERO_BASE_URL_INVALID",
                "CONFIGURE_HTTPS_AGENT_ZERO_BASE_URL",
            ) from exc
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise AgentZeroRuntimeError(
                "AGENT_ZERO_BASE_URL_INVALID",
                "CONFIGURE_HTTPS_AGENT_ZERO_BASE_URL",
            )

        root = Path(
            os.getenv("SOVEREIGN_OWNER_INPUT_ROOT", "/opt/sovereign-owner-managed")
        ).resolve()
        configured = str(
            os.getenv(
                "SOVEREIGN_AGENT_ZERO_API_KEY_FILE",
                str(root / _AGENT_ZERO_KEY_FILENAME),
            )
        ).strip()
        key_candidate = Path(configured)
        if key_candidate.is_symlink():
            raise AgentZeroRuntimeError(
                "AGENT_ZERO_KEY_FILE_REJECTED",
                "ROTATE_AGENT_ZERO_KEY_THROUGH_OWNER_INPUT",
            )
        resolved = key_candidate.resolve()
        if resolved.parent != root or resolved.name != _AGENT_ZERO_KEY_FILENAME:
            raise AgentZeroRuntimeError(
                "AGENT_ZERO_KEY_FILE_REJECTED",
                "USE_PROTECTED_OWNER_INPUT_AGENT_ZERO_KEY",
            )
        try:
            timeout = int(os.getenv("SOVEREIGN_AGENT_ZERO_TIMEOUT_SECONDS", "120"))
        except ValueError as exc:
            raise AgentZeroRuntimeError(
                "AGENT_ZERO_TIMEOUT_INVALID",
                "CONFIGURE_BOUNDED_AGENT_ZERO_TIMEOUT",
            ) from exc
        if not 10 <= timeout <= 300:
            raise AgentZeroRuntimeError(
                "AGENT_ZERO_TIMEOUT_INVALID",
                "CONFIGURE_BOUNDED_AGENT_ZERO_TIMEOUT",
            )
        profile = str(os.getenv("SOVEREIGN_AGENT_ZERO_AGENT_PROFILE", "")).strip()
        if len(profile) > 120 or (profile and not re.fullmatch(r"[A-Za-z0-9._-]+", profile)):
            raise AgentZeroRuntimeError(
                "AGENT_ZERO_AGENT_PROFILE_INVALID",
                "CONFIGURE_SAFE_AGENT_ZERO_PROFILE",
            )
        return cls(
            base_url=raw_base,
            protected_key_path=resolved,
            timeout_seconds=timeout,
            agent_profile=profile,
        )

    def read_protected_key(self) -> str:
        path = self.protected_key_path
        if path.is_symlink() or not path.is_file():
            raise AgentZeroRuntimeError(
                "AGENT_ZERO_KEY_FILE_MISSING",
                "PROVIDE_ROTATED_AGENT_ZERO_KEY_THROUGH_OWNER_INPUT",
            )
        protected = bytearray()
        try:
            try:
                mode = path.stat().st_mode
                if mode & 0o077:
                    raise AgentZeroRuntimeError(
                        "AGENT_ZERO_KEY_FILE_PERMISSIONS_INVALID",
                        "CHMOD_600_AGENT_ZERO_PROTECTED_KEY",
                    )
                protected = bytearray(path.read_bytes())
            except AgentZeroRuntimeError:
                raise
            except OSError as exc:
                raise AgentZeroRuntimeError(
                    "AGENT_ZERO_KEY_FILE_UNREADABLE",
                    "VERIFY_AGENT_ZERO_PROTECTED_KEY_FILE",
                ) from exc
            if not _AGENT_ZERO_KEY_MIN_BYTES <= len(protected) <= _AGENT_ZERO_KEY_MAX_BYTES:
                raise AgentZeroRuntimeError(
                    "AGENT_ZERO_KEY_VALUE_INVALID",
                    "ROTATE_AGENT_ZERO_KEY_THROUGH_OWNER_INPUT",
                )
            try:
                value = protected.decode("utf-8").strip()
            except UnicodeDecodeError as exc:
                raise AgentZeroRuntimeError(
                    "AGENT_ZERO_KEY_VALUE_INVALID",
                    "ROTATE_AGENT_ZERO_KEY_THROUGH_OWNER_INPUT",
                ) from exc
            if len(value) < _AGENT_ZERO_KEY_MIN_BYTES or any(marker in value for marker in ("\x00", "\n", "\r")):
                raise AgentZeroRuntimeError(
                    "AGENT_ZERO_KEY_VALUE_INVALID",
                    "ROTATE_AGENT_ZERO_KEY_THROUGH_OWNER_INPUT",
                )
            return value
        finally:
            for index in range(len(protected)):
                protected[index] = 0


@dataclass(frozen=True, slots=True)
class AgentZeroCapabilityResult:
    ok: bool
    capability: str
    external_identity: str
    project_ref: str
    context_ref: str
    response: str
    response_sha256: str
    observed_tool_names: tuple[str, ...]
    expected_tool_evidence_met: bool
    sleep_skill_evidence: bool
    artifact_sha256: str | None
    artifact_bytes: int
    billing_boundary: str = "OWNER_SCOPED_EXTERNAL_AGENT_ZERO_MODEL"

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "runtime": "agent-zero",
            "capability": self.capability,
            "externalIdentity": self.external_identity,
            "projectRef": self.project_ref,
            "contextRef": self.context_ref,
            "response": self.response,
            "responseSha256": self.response_sha256,
            "observedToolNames": list(self.observed_tool_names),
            "expectedToolEvidenceMet": self.expected_tool_evidence_met,
            "sleepSkillEvidence": self.sleep_skill_evidence,
            "artifactSha256": self.artifact_sha256,
            "artifactBytes": self.artifact_bytes,
            "authoritative": False,
            "runStateMutationAllowed": False,
            "externalEffectsAllowed": ["read", "agent-zero-sandbox-write"],
            "billingBoundary": self.billing_boundary,
            "generalUserAllowed": False,
            "secretValuesReturned": False,
        }


def _project_ref_for_user(user_id: str) -> str:
    normalized = str(user_id or "").strip()
    if not normalized:
        raise AgentZeroRuntimeError(
            "AGENT_ZERO_USER_ID_MISSING",
            "USE_AUTHENTICATED_SOVEREIGN_USER",
        )
    digest = hashlib.sha256(f"sovereign-agent-zero-project-v1:{normalized}".encode("utf-8")).hexdigest()
    return f"{_AGENT_ZERO_PROJECT_PREFIX}{digest[:20]}"


def _bounded_instruction(value: str) -> str:
    raw = str(value or "")
    clean = sanitize_agent_text(raw, 6000)
    if not clean:
        raise AgentZeroRuntimeError(
            "AGENT_ZERO_INSTRUCTION_MISSING",
            "SUPPLY_BOUNDED_CAPABILITY_INSTRUCTION",
        )
    if clean != raw.strip():
        raise AgentZeroRuntimeError(
            "AGENT_ZERO_INSTRUCTION_SECRET_DETECTED",
            "REMOVE_SECRET_MATERIAL_FROM_AGENT_ZERO_INSTRUCTION",
        )
    return clean


def _capability_prompt(capability: str, instruction: str, artifact_path: str | None) -> str:
    common = (
        "You are an external capability worker inside Sovereign Studio ATO, not an authority. "
        "Use Agent Zero capabilities only inside your own Agent Zero runtime/project. "
        "Sovereign remains the sole authority for identity, credits/billing, approvals, GitHub writes, "
        "VPS/host changes, databases, deployments, payments, account changes, evidence verdicts and completion. "
        "Never request, reveal, copy or infer credentials. Never push, open/merge PRs, deploy, mutate a database, "
        "change a remote account, purchase anything, or claim Sovereign success. "
        "Prefer a relevant SKILL.md: use skills_tool to search/load the relevant skill before specialized work. "
        "Browser/computer work is read-only navigation/inspection/screenshot work; do not submit state-changing forms. "
        "Memory is advisory working memory only and must never be presented as current truth without fresh evidence. "
        "Finish bounded work and clean up browser tabs/processes you started. "
    )
    specific = {
        "skills": (
            "Use skills_tool to discover and load the most relevant installed SKILL.md for the request. "
            "Report which skill was actually loaded and what it enables; do not invent missing skills."
        ),
        "browser": (
            "Load the browser-automation skill with skills_tool, use the built-in browser/Playwright capability for "
            "rendered-page inspection, and produce a final screenshot artifact."
        ),
        "playwright": (
            "Load browser-automation via skills_tool and perform the requested rendered-page interaction with the "
            "Playwright-backed Agent Zero browser. Produce a final screenshot artifact."
        ),
        "memory_recall": (
            "Use memory_load for relevant Agent Zero project memories. Clearly label recalled memory as advisory and "
            "separate it from fresh observations."
        ),
        "memory_remember": (
            "Use memory_save only for non-secret, reusable advisory context from this request. Never save credentials, "
            "tokens, payment data or an unverified success claim."
        ),
        "sleep_remember": (
            "Use skills_tool to search for an installed sleep/rem-sleep/remember/memory-consolidation SKILL.md. "
            "If no matching installed skill exists, say capability not installed and do not emulate it. If it exists, "
            "load it and use memory_load/memory_save only as directed by that installed skill."
        ),
        "code_execution": (
            "Use code_execution_tool only inside the Agent Zero sandbox for bounded computation or inspection. "
            "Do not access Docker sockets, host mounts, credentials or remote effect APIs."
        ),
        "research": (
            "Use search_engine and/or document_query for bounded research, and distinguish source observation from inference."
        ),
        "computer": (
            "Use the installed Agent Zero computer/browser capability only for read-only visual interaction inside its "
            "sandbox. Do not perform account, payment, deployment or remote mutation effects."
        ),
        "mcp": (
            "Use only an already-installed read-only MCP capability when it is relevant. Do not invoke remote mutation "
            "tools or grant Agent Zero authority over Sovereign effects."
        ),
    }[capability]
    screenshot = (
        f" Save the final browser screenshot exactly to {artifact_path}."
        if artifact_path
        else ""
    )
    return f"{common}\nCapability contract: {specific}{screenshot}\n\nSovereign request:\n{instruction}"


def _context_id(payload: Mapping[str, Any]) -> str:
    for key in ("context_id", "contextId"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for nested_key in ("data", "result"):
        nested = payload.get(nested_key)
        if isinstance(nested, Mapping):
            value = _context_id(nested)
            if value:
                return value
    return ""


def _response_text(payload: Mapping[str, Any]) -> str:
    for key in ("response", "message", "answer", "content"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return sanitize_agent_text(value, _AGENT_ZERO_RESPONSE_LIMIT)
        if isinstance(value, Mapping):
            nested = _response_text(value)
            if nested:
                return nested
    for nested_key in ("data", "result"):
        nested = payload.get(nested_key)
        if isinstance(nested, Mapping):
            value = _response_text(nested)
            if value:
                return value
    return "Agent Zero returned no bounded text response."


def _normalize_tool_name(value: object) -> str | None:
    text = str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")
    if not text or len(text) > 160:
        return None
    for known in _KNOWN_TOOL_NAMES:
        normalized = known.casefold().replace("-", "_")
        if text == normalized or text.endswith(f".{normalized}") or text.endswith(f":{normalized}"):
            return known
    return None


def _collect_tool_evidence(value: object, *, depth: int = 0) -> tuple[set[str], bool]:
    if depth > 8:
        return set(), False
    tools: set[str] = set()
    sleep_skill_evidence = False
    if isinstance(value, Mapping):
        local_tool = None
        for name_key in ("tool_name", "toolName", "function_name", "functionName"):
            normalized = _normalize_tool_name(value.get(name_key))
            if normalized:
                tools.add(normalized)
                local_tool = normalized
        if local_tool == "skills_tool":
            for evidence_key in ("tool_result", "toolResult", "result", "output", "skill", "loaded_skill"):
                if evidence_key not in value:
                    continue
                evidence_text = str(value.get(evidence_key) or "").casefold()
                if any(marker in evidence_text for marker in ("rem-sleep", "sleep", "remember", "memory-consolid")):
                    sleep_skill_evidence = True
                    break
        for key, item in value.items():
            key_text = str(key or "").casefold()
            if any(marker in key_text for marker in ("tool", "function")):
                if isinstance(item, str):
                    normalized = _normalize_tool_name(item)
                    if normalized:
                        tools.add(normalized)
                elif isinstance(item, Mapping):
                    for name_key in ("name", "tool_name", "toolName", "function"):
                        normalized = _normalize_tool_name(item.get(name_key))
                        if normalized:
                            tools.add(normalized)
            child_tools, child_sleep = _collect_tool_evidence(item, depth=depth + 1)
            tools.update(child_tools)
            sleep_skill_evidence = sleep_skill_evidence or child_sleep
            if (
                "skill" in key_text
                and any(marker in str(item or "").casefold() for marker in ("rem-sleep", "sleep", "remember", "memory-consolid"))
                and "skills_tool" in tools
            ):
                sleep_skill_evidence = True
        return tools, sleep_skill_evidence
    if isinstance(value, (list, tuple)):
        for item in value[:500]:
            child_tools, child_sleep = _collect_tool_evidence(item, depth=depth + 1)
            tools.update(child_tools)
            sleep_skill_evidence = sleep_skill_evidence or child_sleep
    return tools, sleep_skill_evidence


def _browser_tool_observed(tools: set[str]) -> bool:
    return bool({"browser", "browser_agent", "computer_use", "computer"} & tools)


def _expected_evidence_met(
    capability: str,
    tools: set[str],
    *,
    artifact_sha256: str | None,
    sleep_skill_evidence: bool,
) -> bool:
    if capability == "skills":
        return "skills_tool" in tools
    if capability in {"browser", "playwright"}:
        return "skills_tool" in tools and _browser_tool_observed(tools) and bool(artifact_sha256)
    if capability == "memory_recall":
        return "memory_load" in tools
    if capability == "memory_remember":
        return "memory_save" in tools
    if capability == "sleep_remember":
        return (
            "skills_tool" in tools
            and sleep_skill_evidence
            and bool({"memory_load", "memory_save"} & tools)
        )
    if capability == "code_execution":
        return "code_execution_tool" in tools
    if capability == "research":
        return bool({"search_engine", "document_query"} & tools)
    if capability == "computer":
        return _browser_tool_observed(tools)
    if capability == "mcp":
        return bool({"mcp", "mcp_tool"} & tools)
    return False


def _extract_file_base64(payload: object, requested_path: str) -> str:
    basename = Path(requested_path).name
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if str(key) in {requested_path, basename} and isinstance(value, str):
                return value
        for key in ("files", "data", "result"):
            nested = payload.get(key)
            found = _extract_file_base64(nested, requested_path)
            if found:
                return found
    if isinstance(payload, list):
        for item in payload[:50]:
            if isinstance(item, Mapping):
                name = str(item.get("path") or item.get("filename") or item.get("name") or "")
                data = item.get("base64") or item.get("content") or item.get("data")
                if (name in {requested_path, basename}) and isinstance(data, str):
                    return data
    return ""


class AgentZeroClient:
    def __init__(self, config: AgentZeroRuntimeConfig, *, user_id: str) -> None:
        self.config = config
        self.project_ref = _project_ref_for_user(user_id)

    def protected_key_ready(self) -> bool:
        try:
            value = self.config.read_protected_key()
            return bool(value)
        except AgentZeroRuntimeError:
            return False

    def _request(
        self,
        method: str,
        api_name: str,
        *,
        json_data: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        key = self.config.read_protected_key()
        url = f"{self.config.base_url}/api/{api_name}"
        try:
            response = requests.request(
                method,
                url,
                headers={
                    "X-API-KEY": key,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=json_data,
                params=params,
                timeout=self.config.timeout_seconds,
                allow_redirects=False,
            )
        except requests.Timeout as exc:
            raise AgentZeroRuntimeError(
                "AGENT_ZERO_TIMEOUT",
                "RETRY_AGENT_ZERO_CAPABILITY_FROM_PERSISTED_SOVEREIGN_RUN",
            ) from exc
        except requests.RequestException as exc:
            raise AgentZeroRuntimeError(
                "AGENT_ZERO_CONNECTION_FAILED",
                "VERIFY_AGENT_ZERO_RUNTIME_AND_NETWORK",
            ) from exc
        if not 200 <= response.status_code < 300:
            family = (
                "AGENT_ZERO_AUTHENTICATION_FAILED"
                if response.status_code in {401, 403}
                else "AGENT_ZERO_RATE_LIMITED"
                if response.status_code == 429
                else "AGENT_ZERO_UPSTREAM_UNAVAILABLE"
                if response.status_code >= 500
                else "AGENT_ZERO_REQUEST_REJECTED"
            )
            raise AgentZeroRuntimeError(
                family,
                "VERIFY_AGENT_ZERO_EXTERNAL_API_AND_ROTATED_KEY",
                http_status=response.status_code,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise AgentZeroRuntimeError(
                "AGENT_ZERO_RESPONSE_INVALID",
                "VERIFY_AGENT_ZERO_EXTERNAL_API_CONTRACT",
                http_status=response.status_code,
            ) from exc
        if not isinstance(payload, dict):
            raise AgentZeroRuntimeError(
                "AGENT_ZERO_RESPONSE_INVALID",
                "VERIFY_AGENT_ZERO_EXTERNAL_API_CONTRACT",
                http_status=response.status_code,
            )
        return payload

    def invoke(self, capability: str, instruction: str) -> AgentZeroCapabilityResult:
        normalized_capability = str(capability or "").strip().casefold().replace("-", "_")
        if normalized_capability not in _ALLOWED_CAPABILITIES:
            raise AgentZeroRuntimeError(
                "AGENT_ZERO_CAPABILITY_NOT_ALLOWED",
                "SELECT_ALLOWLISTED_AGENT_ZERO_CAPABILITY",
            )
        clean_instruction = _bounded_instruction(instruction)
        call_id = str(uuid.uuid4())
        artifact_path = (
            f"/a0/usr/sovereign/evidence/{call_id}/browser-final.png"
            if normalized_capability in {"browser", "playwright"}
            else None
        )
        body: dict[str, Any] = {
            "message": _capability_prompt(normalized_capability, clean_instruction, artifact_path),
            "lifetime_hours": 1,
            "project_name": self.project_ref,
        }
        if self.config.agent_profile:
            body["agent_profile"] = self.config.agent_profile
        message_payload = self._request("POST", "api_message", json_data=body)
        context_id = _context_id(message_payload)
        if not context_id:
            raise AgentZeroRuntimeError(
                "AGENT_ZERO_CONTEXT_EVIDENCE_MISSING",
                "VERIFY_AGENT_ZERO_CONTEXT_ID_RESPONSE",
            )
        log_payload = self._request(
            "GET",
            "api_log_get",
            params={"context_id": context_id, "length": str(_AGENT_ZERO_LOG_LENGTH)},
        )
        tools, sleep_skill_evidence = _collect_tool_evidence(log_payload)
        artifact_sha256: str | None = None
        artifact_bytes = 0
        if artifact_path:
            files_payload = self._request(
                "POST",
                "api_files_get",
                json_data={"paths": [artifact_path]},
            )
            encoded = _extract_file_base64(files_payload, artifact_path)
            if encoded:
                try:
                    raw = base64.b64decode(encoded, validate=True)
                except (ValueError, TypeError):
                    raw = b""
                if raw.startswith(b"\x89PNG\r\n\x1a\n") and len(raw) <= 20_000_000:
                    artifact_sha256 = hashlib.sha256(raw).hexdigest()
                    artifact_bytes = len(raw)
        response_text = _response_text(message_payload)
        response_sha256 = hashlib.sha256(response_text.encode("utf-8")).hexdigest()
        context_ref = "a0ctx-" + hashlib.sha256(context_id.encode("utf-8")).hexdigest()[:24]
        external_identity = "a0-" + hashlib.sha256(
            f"{self.project_ref}|{context_id}|{call_id}".encode("utf-8")
        ).hexdigest()[:32]
        evidence_met = _expected_evidence_met(
            normalized_capability,
            tools,
            artifact_sha256=artifact_sha256,
            sleep_skill_evidence=sleep_skill_evidence,
        )
        return AgentZeroCapabilityResult(
            ok=evidence_met,
            capability=normalized_capability,
            external_identity=external_identity,
            project_ref=self.project_ref,
            context_ref=context_ref,
            response=response_text,
            response_sha256=response_sha256,
            observed_tool_names=tuple(sorted(tools)),
            expected_tool_evidence_met=evidence_met,
            sleep_skill_evidence=sleep_skill_evidence,
            artifact_sha256=artifact_sha256,
            artifact_bytes=artifact_bytes,
        )


def _close(conn: Any) -> None:
    close = getattr(conn, "close", None)
    if callable(close):
        close()


def _owner_user_allowed(get_connection: ConnectionFactory, user_id: str) -> bool:
    normalized_user = str(user_id or "").strip()
    if not normalized_user:
        return False
    configured_id = str(os.getenv("SOVEREIGN_OWNER_ADMIN_ID", "")).strip()
    configured_email = str(os.getenv("SOVEREIGN_OWNER_ADMIN_EMAIL", "")).strip().casefold()
    if configured_id:
        return hmac.compare_digest(normalized_user, configured_id)
    if not configured_email:
        return False
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT email FROM admin_users WHERE id=%s::uuid LIMIT 1",
                (normalized_user,),
            )
            row = cur.fetchone()
        email = str((row or {}).get("email") or "").strip().casefold()
        return bool(email and hmac.compare_digest(email, configured_email))
    finally:
        _close(conn)


@dataclass
class BoundAgentZeroCapabilityToolset:
    """Expose bounded Agent Zero capabilities to the routed Sovereign model."""

    get_connection: ConnectionFactory
    user_id: str
    run_id: str
    client: AgentZeroClient
    _calls_by_role: dict[str, int] = field(default_factory=dict)
    _calls_by_capability: dict[str, int] = field(default_factory=dict)
    _verified_by_capability: dict[str, int] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    @classmethod
    def from_env_if_ready(
        cls,
        *,
        get_connection: ConnectionFactory,
        user_id: str,
        run_id: str,
    ) -> "BoundAgentZeroCapabilityToolset | None":
        if not _owner_user_allowed(get_connection, user_id):
            return None
        try:
            config = AgentZeroRuntimeConfig.from_env()
            client = AgentZeroClient(config, user_id=user_id)
        except AgentZeroRuntimeError:
            return None
        if not client.protected_key_ready():
            return None
        return cls(
            get_connection=get_connection,
            user_id=str(user_id),
            run_id=str(run_id),
            client=client,
        )

    def allowed_capabilities(self, role: str) -> tuple[str, ...]:
        return tuple(sorted(_ROLE_CAPABILITIES.get(str(role or ""), frozenset())))

    def _record(self, role: str, capability: str, verified: bool) -> None:
        with self._lock:
            self._calls_by_role[role] = self._calls_by_role.get(role, 0) + 1
            self._calls_by_capability[capability] = self._calls_by_capability.get(capability, 0) + 1
            if verified:
                self._verified_by_capability[capability] = self._verified_by_capability.get(capability, 0) + 1

    def _persist_external_evidence(self, result: AgentZeroCapabilityResult) -> None:
        conn = self.get_connection()
        try:
            record_external_action_event(
                conn,
                user_id=self.user_id,
                run_id=self.run_id,
                source="agent-zero",
                external_identity=result.external_identity,
                event_type=f"agent_zero_{result.capability}",
                summary=(
                    f"Agent Zero capability {result.capability} returned "
                    f"{'verified tool evidence' if result.expected_tool_evidence_met else 'insufficient tool evidence'}."
                ),
                payload={
                    "capability": result.capability,
                    "projectRef": result.project_ref,
                    "contextRef": result.context_ref,
                    "responseSha256": result.response_sha256,
                    "observedToolNames": list(result.observed_tool_names),
                    "expectedToolEvidenceMet": result.expected_tool_evidence_met,
                    "sleepSkillEvidence": result.sleep_skill_evidence,
                    "artifactSha256": result.artifact_sha256,
                    "artifactBytes": result.artifact_bytes,
                    "authoritative": False,
                    "runStateMutationAllowed": False,
                    "billingBoundary": result.billing_boundary,
                    "generalUserAllowed": False,
                    "secretValuesReturned": False,
                },
            )
        finally:
            _close(conn)

    def tools_for_role(self, role: str) -> list[Any]:
        allowed = frozenset(self.allowed_capabilities(role))
        if not allowed:
            return []
        module = importlib.import_module("agents")
        function_tool = getattr(module, "function_tool", None)
        if not callable(function_tool):
            raise RuntimeError("OpenAI Agents SDK function_tool API is unavailable")

        def use_agent_zero_capability(capability: str, instruction: str) -> str:
            """Use one owner-scoped Agent Zero skill/browser/memory/sandbox capability as non-authoritative evidence."""
            normalized = str(capability or "").strip().casefold().replace("-", "_")
            if normalized not in allowed:
                raise ValueError(
                    "Agent Zero capability is outside this worker role. Allowed: "
                    + ", ".join(sorted(allowed))
                )
            try:
                result = self.client.invoke(normalized, instruction)
            except AgentZeroRuntimeError as exc:
                self._record(role, normalized, False)
                return json.dumps(exc.safe_payload(), ensure_ascii=False, sort_keys=True)
            self._persist_external_evidence(result)
            self._record(role, normalized, result.expected_tool_evidence_met)
            return json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True)

        return [function_tool(use_agent_zero_capability)]

    def summary(self) -> dict[str, object]:
        with self._lock:
            return {
                "runtime": "agent-zero",
                "ownerScoped": True,
                "generalUserAllowed": False,
                "projectRef": self.client.project_ref,
                "callsByRole": dict(self._calls_by_role),
                "callsByCapability": dict(self._calls_by_capability),
                "verifiedByCapability": dict(self._verified_by_capability),
                "authoritative": False,
                "billingBoundary": "OWNER_SCOPED_EXTERNAL_AGENT_ZERO_MODEL",
                "secretValuesReturned": False,
            }
