from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import urllib.parse
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

import requests

SUPPLEMENTAL_ONLY = "SUPPLEMENTAL_ONLY"


class WolframAdapterStatus(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"
    AVAILABLE_READ_ONLY = "AVAILABLE_READ_ONLY"
    SUCCEEDED_UNVERIFIED = "SUCCEEDED_UNVERIFIED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class WolframCapability:
    capability_id: str
    tool_name: str
    read_only: bool


WOLFRAM_CAPABILITY_MAP: Mapping[str, WolframCapability] = {
    "wolfram.context.search": WolframCapability("wolfram.context.search", "WolframContext", True),
    "wolfram.alpha.query": WolframCapability("wolfram.alpha.query", "WolframAlpha", True),
    "wolfram.language.inspect": WolframCapability("wolfram.language.inspect", "CodeInspector", True),
    "wolfram.tests.read": WolframCapability("wolfram.tests.read", "TestReport", True),
    "wolfram.symbol.read": WolframCapability("wolfram.symbol.read", "SymbolDefinition", True),
    "wolfram.notebook.read": WolframCapability("wolfram.notebook.read", "ReadNotebook", True),
}

_FORBIDDEN_TOOLS = {
    "WriteNotebook",
    "WolframLanguageEvaluator",
    "PacletInstall",
    "PacletUpdate",
    "RunProcess",
    "StartProcess",
}


@dataclass(frozen=True, slots=True)
class WolframAdapterAttestation:
    installation_revision: str
    mcp_server_identity_hash: str
    paclet_version: str
    wolfram_version: str
    runtime_mode: str
    input_schema_hash: str
    output_schema_hash: str
    license_attested: bool

    def is_read_only_ready(self) -> bool:
        return all(
            (
                self.installation_revision,
                self.mcp_server_identity_hash,
                self.paclet_version,
                self.wolfram_version,
                self.input_schema_hash,
                self.output_schema_hash,
            )
        ) and self.license_attested and self.runtime_mode in {"LocalReadOnly", "CloudReadOnly"}


def authorize_wolfram_tool(
    *,
    capability_id: str,
    requested_tool_name: str,
    attestation: WolframAdapterAttestation | None,
) -> WolframAdapterStatus:
    """Authorize an explicit read-only mapping; names never imply capability."""
    if requested_tool_name in _FORBIDDEN_TOOLS:
        return WolframAdapterStatus.BLOCKED
    capability = WOLFRAM_CAPABILITY_MAP.get(capability_id)
    if capability is None or capability.tool_name != requested_tool_name or not capability.read_only:
        return WolframAdapterStatus.BLOCKED
    if attestation is None or not attestation.is_read_only_ready():
        return WolframAdapterStatus.UNAVAILABLE
    return WolframAdapterStatus.AVAILABLE_READ_ONLY


def normalize_wolfram_result(result_hash: str, summary: str) -> dict[str, str]:
    if not result_hash or not summary:
        raise ValueError("result hash and bounded summary are required")
    return {
        "adapterMode": SUPPLEMENTAL_ONLY,
        "status": WolframAdapterStatus.SUCCEEDED_UNVERIFIED.value,
        "resultHash": result_hash,
        "summary": summary,
        "truthNotice": "Wolfram output is supplemental and cannot verify repository, runtime, deployment, ARE or Kappa truth.",
    }


# ---------------------------------------------------------------------------
# Wolfram CAG component adapters (issue #1459)
#
# Canonical, server-side transport contracts for the four Wolfram Component
# APIs: Wolfram Language Hints, Wolfram Language Computation, Wolfram|Alpha
# Results and Wolfram|Alpha Context. These capabilities project into the
# existing capability map in this module; no second registry is created.
# Issue #1165 remains owner of the generic AgentTools/MCP read-only path; this
# lane only adds direct, bounded CAG HTTP/API ability and must not become a
# second general Wolfram runtime.
# ---------------------------------------------------------------------------

CAG_SUPPLEMENTAL_ONLY = SUPPLEMENTAL_ONLY


class WolframCagStatus(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"
    NOT_ENTITLED = "NOT_ENTITLED"
    AVAILABLE = "AVAILABLE"
    SUCCEEDED_UNVERIFIED = "SUCCEEDED_UNVERIFIED"
    BLOCKED = "BLOCKED"


class WolframCagErrorFamily(str, Enum):
    AUTH = "AUTH"
    ENTITLEMENT = "ENTITLEMENT"
    QUOTA = "QUOTA"
    RATE_LIMIT = "RATE_LIMIT"
    TIMEOUT = "TIMEOUT"
    UPSTREAM = "UPSTREAM"
    SCHEMA = "SCHEMA"
    RESULT_UNAVAILABLE = "RESULT_UNAVAILABLE"


class WolframCagRetryDecision(str, Enum):
    SAFE_TO_RETRY = "SAFE_TO_RETRY"
    DO_NOT_RETRY = "DO_NOT_RETRY"


# Components never mutate; CAG transport results are supplemental only.
class WolframCagError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        family: WolframCagErrorFamily,
        status: int | None = None,
        retryable: bool | None = None,
        response_uuid: str = "",
        request_id: str = "",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.family = family
        self.status = status
        if retryable is None:
            retryable = cag_retry_decision(family, 1, 1) is WolframCagRetryDecision.SAFE_TO_RETRY
        self.retryable = retryable
        self.response_uuid = response_uuid
        self.request_id = request_id

    def public_payload(self) -> dict[str, str]:
        # Only structural, non-secret metadata is exposed. Credential material,
        # bodies and headers are never surfaced here.
        payload: dict[str, str] = {
            "family": self.family.value,
            "message": self.message,
            "retryable": "true" if self.retryable else "false",
        }
        if self.status is not None:
            payload["status"] = str(self.status)
        if self.response_uuid:
            payload["responseUuid"] = self.response_uuid
        if self.request_id:
            payload["requestId"] = self.request_id
        return payload


@dataclass(frozen=True, slots=True)
class WolframCagComponent:
    capability_id: str
    component: str
    base_url: str
    endpoint_id: str
    method: str
    expected_content_type: str
    timeout_seconds: int
    max_output_bytes: int
    max_request_bytes: int
    max_retries: int
    mutates: bool = False

    def __post_init__(self) -> None:
        if self.mutates:
            raise WolframCagError(
                "CAG component contracts are read-only by design",
                family=WolframCagErrorFamily.SCHEMA,
            )


WOLFRAM_CAG_COMPONENT_MAP: Mapping[str, WolframCagComponent] = {
    "wolfram.cag.hints": WolframCagComponent(
        capability_id="wolfram.cag.hints",
        component="WolframLanguageHints",
        base_url="https://services.wolfram.com/api/cag/v1/WolframLanguageHints",
        endpoint_id="cag.hints",
        method="POST",
        expected_content_type="application/json",
        timeout_seconds=15,
        max_output_bytes=256 * 1024,
        max_request_bytes=64 * 1024,
        max_retries=2,
    ),
    "wolfram.cag.compute": WolframCagComponent(
        capability_id="wolfram.cag.compute",
        component="WolframLanguageComputation",
        base_url="https://services.wolfram.com/api/cag/v1/WolframLanguageCompute",
        endpoint_id="cag.compute",
        method="POST",
        expected_content_type="application/json",
        timeout_seconds=30,
        max_output_bytes=512 * 1024,
        max_request_bytes=128 * 1024,
        max_retries=1,
    ),
    "wolfram.cag.results": WolframCagComponent(
        capability_id="wolfram.cag.results",
        component="WolframAlphaResults",
        base_url="https://services.wolfram.com/api/cag/v1/WolframAlphaResult",
        endpoint_id="cag.results",
        method="GET",
        expected_content_type="text/plain",
        timeout_seconds=20,
        max_output_bytes=512 * 1024,
        max_request_bytes=8 * 1024,
        max_retries=2,
    ),
    "wolfram.cag.context": WolframCagComponent(
        capability_id="wolfram.cag.context",
        component="WolframAlphaContext",
        base_url="https://services.wolfram.com/api/cag/v1/WolframAlphaContext",
        endpoint_id="cag.context",
        method="POST",
        expected_content_type="application/json",
        timeout_seconds=20,
        max_output_bytes=256 * 1024,
        max_request_bytes=16 * 1024,
        max_retries=2,
    ),
}


# Keys that must never be embedded into a CAG request payload or path params.
_FORBIDDEN_PAYLOAD_KEYS = {
    "url",
    "endpoint",
    "token",
    "authorization",
    "apikey",
    "api_key",
    "secret",
    "password",
    "credential",
}


@dataclass(frozen=True, slots=True)
class WolframCagCredential:
    """Server-side resolved credential projection.

    Only a non-reversible hash and an entitlement flag ever leave the resolver.
    Raw secret material is intentionally absent from this structure so that it
    can never be logged, returned or persisted as evidence.
    """

    credential_hash: str
    entitled: bool
    provider: str

    def __post_init__(self) -> None:
        if any(
            key in (self.credential_hash, self.provider)
            for key in ("", None)
        ):
            raise WolframCagError(
                "credential hash and provider are required",
                family=WolframCagErrorFamily.AUTH,
            )


DEFAULT_WOLFRAM_CAG_API_KEY_FILE = "/opt/sovereign-owner-managed/wolfram_cag_api_key.txt"
MAX_WOLFRAM_CAG_API_KEY_BYTES = 8192


def read_cag_secret_file(path: str = DEFAULT_WOLFRAM_CAG_API_KEY_FILE) -> str:
    """Read the one fixed owner-managed CAG credential file fail-closed.

    The path is intentionally not caller-selectable: production code may only
    read the owner-managed location. The owner-input runtime writes this file
    with mode ``0600``. Symlinks, non-regular files, empty/oversized values or
    broader permissions are rejected before any provider call.
    """
    selected = str(path or "").strip()
    if selected != DEFAULT_WOLFRAM_CAG_API_KEY_FILE:
        raise WolframCagError(
            "CAG credential file path is not allowlisted",
            family=WolframCagErrorFamily.AUTH,
        )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(selected, flags)
    except OSError as exc:
        raise WolframCagError(
            "CAG credential file is unavailable",
            family=WolframCagErrorFamily.AUTH,
        ) from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise WolframCagError(
                "CAG credential source is not a regular file",
                family=WolframCagErrorFamily.AUTH,
            )
        if metadata.st_size <= 0 or metadata.st_size > MAX_WOLFRAM_CAG_API_KEY_BYTES:
            raise WolframCagError(
                "CAG credential file size is invalid",
                family=WolframCagErrorFamily.AUTH,
            )
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise WolframCagError(
                "CAG credential file permissions are too broad",
                family=WolframCagErrorFamily.AUTH,
            )
        raw = os.read(descriptor, MAX_WOLFRAM_CAG_API_KEY_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(raw) > MAX_WOLFRAM_CAG_API_KEY_BYTES:
        raise WolframCagError(
            "CAG credential file exceeds the byte limit",
            family=WolframCagErrorFamily.AUTH,
        )
    try:
        secret_value = raw.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise WolframCagError(
            "CAG credential file is not UTF-8",
            family=WolframCagErrorFamily.AUTH,
        ) from exc
    if not secret_value or "\x00" in secret_value:
        raise WolframCagError(
            "CAG credential file is empty or invalid",
            family=WolframCagErrorFamily.AUTH,
        )
    return secret_value


def _resolve_cag_secret_value(*, capability_id: str, credential_resolver=None) -> tuple[str, str] | None:
    if capability_id not in WOLFRAM_CAG_COMPONENT_MAP:
        raise WolframCagError(
            "unknown CAG capability",
            family=WolframCagErrorFamily.SCHEMA,
        )
    if credential_resolver is not None:
        resolved = credential_resolver(capability_id=capability_id)
        if resolved is None:
            return None
        secret_value, provider = resolved
        selected = str(secret_value or "").strip()
        if not selected:
            return None
        return selected, str(provider or "wolfram").strip() or "wolfram"

    configured_file = os.getenv("WOLFRAM_CAG_API_KEY_FILE", "").strip()
    if configured_file:
        # A configured pointer must resolve to the one fixed owner-managed path.
        secret_value = read_cag_secret_file(configured_file)
        return secret_value, "wolfram-owner-file"

    # Backward-compatible server-side alias for pre-owner-input deployments.
    legacy = str(os.getenv("WOLFRAM_CAG_APP_ID") or "").strip()
    if legacy:
        return legacy, "wolfram-legacy-env"
    return None


def resolve_cag_credentials(
    *,
    capability_id: str,
    credential_resolver=None,
) -> WolframCagCredential | None:
    """Resolve only a non-reversible credential projection server-side.

    The owner-managed file is preferred. ``WOLFRAM_CAG_APP_ID`` remains a
    compatibility fallback only. Raw credential material never leaves this
    resolver; live transport resolves it again just-in-time and verifies the
    hash before placing it in the provider Authorization header.
    """
    resolved = _resolve_cag_secret_value(
        capability_id=capability_id,
        credential_resolver=credential_resolver,
    )
    if resolved is None:
        return None
    secret_value, provider = resolved
    credential_hash = hashlib.sha256(secret_value.encode("utf-8")).hexdigest()
    return WolframCagCredential(
        credential_hash=credential_hash,
        entitled=True,
        provider=provider,
    )


def provision_cag_component(
    *,
    capability_id: str,
    credential: WolframCagCredential | None,
) -> WolframCagStatus:
    """Honest provision state: UNAVAILABLE when not configured, NOT_ENTITLED
    when configured but not entitled, AVAILABLE when entitled."""
    if capability_id not in WOLFRAM_CAG_COMPONENT_MAP:
        return WolframCagStatus.BLOCKED
    if credential is None:
        return WolframCagStatus.UNAVAILABLE
    if not credential.entitled:
        return WolframCagStatus.NOT_ENTITLED
    return WolframCagStatus.AVAILABLE


_CAG_HASH = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class WolframCagRequest:
    capability_id: str
    body_hash: str
    query_hash: str = ""
    response_schema_hash: str = ""
    idempotency_key: str = ""
    requested_output_bytes: int = 0
    # Declared byte size of the request body + query payload the caller will
    # send to the component transport. Carried explicitly (not derivable from
    # ``body_hash``) so the per-component ``max_request_bytes`` limit is
    # enforceable and testable before any network call is made.
    request_size_bytes: int = 0

    def validate(self) -> WolframCagComponent:
        component = WOLFRAM_CAG_COMPONENT_MAP.get(self.capability_id)
        if component is None:
            raise WolframCagError(
                "unknown CAG capability",
                family=WolframCagErrorFamily.SCHEMA,
            )
        for value in (self.body_hash, self.query_hash, self.response_schema_hash):
            if value and not _CAG_HASH.fullmatch(value):
                raise WolframCagError(
                    "request hashes must be lowercase SHA-256",
                    family=WolframCagErrorFamily.SCHEMA,
                )
        if any(key.lower() in _FORBIDDEN_PAYLOAD_KEYS for key in (self.idempotency_key,)):
            raise WolframCagError(
                "free URL or credential parameters are forbidden",
                family=WolframCagErrorFamily.SCHEMA,
            )
        if self.requested_output_bytes < 0:
            raise WolframCagError(
                "output budget must be non-negative",
                family=WolframCagErrorFamily.SCHEMA,
            )
        effective_output = self.requested_output_bytes or component.max_output_bytes
        if effective_output > component.max_output_bytes:
            raise WolframCagError(
                "requested output exceeds component limit",
                family=WolframCagErrorFamily.SCHEMA,
            )
        if self.request_size_bytes < 0:
            raise WolframCagError(
                "request size must be non-negative",
                family=WolframCagErrorFamily.SCHEMA,
            )
        if self.request_size_bytes > component.max_request_bytes:
            raise WolframCagError(
                "request payload exceeds component limit",
                family=WolframCagErrorFamily.SCHEMA,
            )
        return component

    @property
    def request_hash(self) -> str:
        payload = {
            "schemaVersion": "sovereign-wolfram-cag-request.v1",
            "capabilityId": self.capability_id,
            "bodyHash": self.body_hash,
            "queryHash": self.query_hash,
            "responseSchemaHash": self.response_schema_hash,
            "idempotencyKey": self.idempotency_key,
            "requestedOutputBytes": self.requested_output_bytes,
            "requestSizeBytes": self.request_size_bytes,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class CagHttpOutcome:
    status: int
    content_type: str
    body: bytes
    response_uuid: str
    request_id: str
    rate_limit_remaining: str
    quota_remaining: str
    timed_out: bool


@dataclass(frozen=True, slots=True)
class WolframCagReceipt:
    capability_id: str
    component: str
    base_url: str
    endpoint_id: str
    request_hash: str
    credential_hash: str
    response_status: int
    response_hash: str
    response_uuid: str
    request_id: str
    rate_limit_remaining: str
    quota_remaining: str
    response_schema_hash: str
    status: WolframCagStatus
    truth_notice: str = (
        "Wolfram CAG output is supplemental and cannot verify repository, "
        "runtime, deployment, ARE or Kappa truth; it cannot mutate GitHub, "
        "Docker, DB, PatchMon or deployment state."
    )

    def validate(self) -> None:
        if not _CAG_HASH.fullmatch(self.credential_hash):
            raise WolframCagError(
                "credential hash must be SHA-256",
                family=WolframCagErrorFamily.SCHEMA,
            )
        for value in (self.request_hash, self.response_hash):
            if not _CAG_HASH.fullmatch(value):
                raise WolframCagError(
                    "receipt identities must be SHA-256 values",
                    family=WolframCagErrorFamily.SCHEMA,
                )
        if self.status is not WolframCagStatus.SUCCEEDED_UNVERIFIED:
            raise WolframCagError(
                "transport receipts can only be SUCCEEDED_UNVERIFIED",
                family=WolframCagErrorFamily.SCHEMA,
            )


def classify_cag_status(
    *,
    status: int | None,
    timed_out: bool,
) -> WolframCagErrorFamily:
    """Map a raw HTTP status / timeout into a single, distinguishable error
    family. ``status is None`` denotes a transport-level failure."""
    if timed_out:
        return WolframCagErrorFamily.TIMEOUT
    if status is None:
        return WolframCagErrorFamily.UPSTREAM
    if status in (401, 403):
        return WolframCagErrorFamily.AUTH
    if status == 402:
        return WolframCagErrorFamily.ENTITLEMENT
    if status == 429:
        return WolframCagErrorFamily.RATE_LIMIT
    if status == 501:
        return WolframCagErrorFamily.RESULT_UNAVAILABLE
    if status in (503, 504):
        return WolframCagErrorFamily.UPSTREAM
    if 400 <= status < 500:
        return WolframCagErrorFamily.SCHEMA
    if status >= 500:
        return WolframCagErrorFamily.UPSTREAM
    return WolframCagErrorFamily.UPSTREAM


def cag_retry_decision(
    family: WolframCagErrorFamily,
    attempt: int,
    max_retries: int,
) -> WolframCagRetryDecision:
    """Bounded retry only for safely classified transient families."""
    if attempt > max_retries:
        return WolframCagRetryDecision.DO_NOT_RETRY
    if family in (
        WolframCagErrorFamily.TIMEOUT,
        WolframCagErrorFamily.RATE_LIMIT,
        WolframCagErrorFamily.UPSTREAM,
    ):
        return WolframCagRetryDecision.SAFE_TO_RETRY
    return WolframCagRetryDecision.DO_NOT_RETRY


def is_wolfram_capability(capability_id: str) -> bool:
    """Project CAG capabilities into the existing Wolfram capability namespace
    instead of creating a second registry."""
    return capability_id in WOLFRAM_CAPABILITY_MAP or capability_id in WOLFRAM_CAG_COMPONENT_MAP


def _normalize_header(value: str | None) -> str:
    if not value:
        return ""
    return value.strip()


_CAG_REQUIRED_PAYLOAD_KEYS: Mapping[str, frozenset[str]] = {
    "wolfram.cag.hints": frozenset({"context"}),
    "wolfram.cag.compute": frozenset({"code"}),
    "wolfram.cag.results": frozenset({"input"}),
    "wolfram.cag.context": frozenset({"context"}),
}
_CAG_ALLOWED_PAYLOAD_KEYS: Mapping[str, frozenset[str]] = {
    "wolfram.cag.hints": frozenset({"context"}),
    "wolfram.cag.compute": frozenset({"code", "line", "maxChars", "timeConstraint"}),
    "wolfram.cag.results": frozenset({"input"}),
    "wolfram.cag.context": frozenset({"context", "count"}),
}


def _normalize_live_cag_payload(capability_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    component = WOLFRAM_CAG_COMPONENT_MAP.get(capability_id)
    if component is None:
        raise WolframCagError("unknown CAG capability", family=WolframCagErrorFamily.SCHEMA)
    if not isinstance(payload, Mapping):
        raise WolframCagError("CAG payload must be an object", family=WolframCagErrorFamily.SCHEMA)
    keys = {str(key) for key in payload.keys()}
    if any(key.casefold() in _FORBIDDEN_PAYLOAD_KEYS for key in keys):
        raise WolframCagError("credential-shaped CAG payload fields are forbidden", family=WolframCagErrorFamily.SCHEMA)
    allowed = _CAG_ALLOWED_PAYLOAD_KEYS[capability_id]
    required = _CAG_REQUIRED_PAYLOAD_KEYS[capability_id]
    if not required.issubset(keys) or not keys.issubset(allowed):
        raise WolframCagError("CAG payload does not match the component contract", family=WolframCagErrorFamily.SCHEMA)
    normalized: dict[str, Any] = {}
    for key in sorted(keys):
        value = payload[key]
        if isinstance(value, bool) or value is None or isinstance(value, (dict, list, tuple, set)):
            raise WolframCagError("CAG payload contains an unsupported value type", family=WolframCagErrorFamily.SCHEMA)
        if not isinstance(value, (str, int, float)):
            raise WolframCagError("CAG payload contains an unsupported value type", family=WolframCagErrorFamily.SCHEMA)
        if isinstance(value, str):
            value = value.strip()
            if key in required and not value:
                raise WolframCagError("required CAG payload text is empty", family=WolframCagErrorFamily.SCHEMA)
        normalized[key] = value
    return normalized


def _live_cag_schema_validator(body: bytes, content_type: str, component: WolframCagComponent) -> bool:
    normalized_type = _normalize_header(content_type).casefold()
    if component.expected_content_type == "text/plain":
        if "text/plain" not in normalized_type or not body.strip():
            return False
        try:
            body.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return True
    if "application/json" not in normalized_type:
        return False
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict) or "result" not in payload:
        return False
    if "success" in payload and not isinstance(payload["success"], bool):
        return False
    if "code" in payload and (isinstance(payload["code"], bool) or not isinstance(payload["code"], int)):
        return False
    if "uuid" in payload and not isinstance(payload["uuid"], str):
        return False
    return True


def _bounded_cag_response_body(response: Any, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=16 * 1024):
        if not chunk:
            continue
        total += len(chunk)
        if total > limit:
            raise WolframCagError("CAG response exceeds output limit", family=WolframCagErrorFamily.SCHEMA, status=int(response.status_code))
        chunks.append(bytes(chunk))
    return b"".join(chunks)


def execute_live_cag_request(
    *,
    capability_id: str,
    payload: Mapping[str, Any],
    credential_resolver=None,
    session: Any | None = None,
) -> WolframCagReceipt:
    """Execute one live CAG request through the current official v1 contract.

    Raw credentials are resolved twice: once to create the secret-free
    credential fingerprint and again immediately before the HTTP request. The
    two hashes must match, so a concurrent rotation fails closed instead of
    sending a credential under a stale evidence identity. The raw value is
    placed only in ``Authorization`` and is never returned by this function.
    """
    component = WOLFRAM_CAG_COMPONENT_MAP.get(capability_id)
    if component is None:
        raise WolframCagError("unknown CAG capability", family=WolframCagErrorFamily.SCHEMA)
    normalized_payload = _normalize_live_cag_payload(capability_id, payload)
    if component.method == "GET":
        request_bytes = urllib.parse.urlencode(normalized_payload).encode("utf-8")
        body_bytes = b""
        query_hash = hashlib.sha256(request_bytes).hexdigest()
    else:
        body_bytes = json.dumps(normalized_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        request_bytes = body_bytes
        query_hash = ""
    if len(request_bytes) > component.max_request_bytes:
        raise WolframCagError("request payload exceeds component limit", family=WolframCagErrorFamily.SCHEMA)
    schema_identity = {
        "capabilityId": capability_id,
        "method": component.method,
        "contentType": component.expected_content_type,
        "endpoint": component.endpoint_id,
        "contract": "wolfram-cag-v1-2026-08-21",
    }
    response_schema_hash = hashlib.sha256(
        json.dumps(schema_identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    request = WolframCagRequest(
        capability_id=capability_id,
        body_hash=hashlib.sha256(body_bytes).hexdigest(),
        query_hash=query_hash,
        response_schema_hash=response_schema_hash,
        request_size_bytes=len(request_bytes),
    )
    credential = resolve_cag_credentials(
        capability_id=capability_id,
        credential_resolver=credential_resolver,
    )
    if credential is None:
        raise WolframCagError("CAG component not provisioned", family=WolframCagErrorFamily.RESULT_UNAVAILABLE)
    http = session or requests.Session()

    def transport(*, request, component, credential, credential_secret):
        if credential_secret is not None:
            raise WolframCagError("raw credential must not cross the executor boundary", family=WolframCagErrorFamily.AUTH)
        resolved = _resolve_cag_secret_value(
            capability_id=request.capability_id,
            credential_resolver=credential_resolver,
        )
        if resolved is None:
            raise WolframCagError("CAG credential disappeared before transport", family=WolframCagErrorFamily.AUTH)
        live_secret, _provider = resolved
        live_hash = hashlib.sha256(live_secret.encode("utf-8")).hexdigest()
        if live_hash != credential.credential_hash:
            raise WolframCagError("CAG credential changed before transport", family=WolframCagErrorFamily.AUTH)
        headers = {
            "Authorization": live_secret,
            "Accept": component.expected_content_type,
        }
        kwargs: dict[str, Any] = {
            "headers": headers,
            "timeout": component.timeout_seconds,
            "allow_redirects": False,
            "stream": True,
        }
        if component.method == "GET":
            kwargs["params"] = normalized_payload
        else:
            headers["Content-Type"] = "application/json"
            kwargs["data"] = body_bytes
        try:
            response = http.request(component.method, component.base_url, **kwargs)
        except requests.Timeout as exc:
            raise TimeoutError("CAG provider request timed out") from exc
        except requests.RequestException as exc:
            raise WolframCagError("CAG provider transport failed", family=WolframCagErrorFamily.UPSTREAM) from exc
        try:
            response_body = _bounded_cag_response_body(response, component.max_output_bytes)
            content_type = str(response.headers.get("Content-Type") or "")
            response_uuid = str(response.headers.get("X-Wolfram-UUID") or "")
            if "application/json" in content_type.casefold() and response_body:
                try:
                    parsed = json.loads(response_body)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    parsed = None
                if isinstance(parsed, dict) and isinstance(parsed.get("uuid"), str):
                    response_uuid = parsed["uuid"].strip()
            return CagHttpOutcome(
                status=int(response.status_code),
                content_type=content_type,
                body=response_body,
                response_uuid=response_uuid,
                request_id=str(response.headers.get("X-Request-Id") or response.headers.get("X-Wolfram-Request-Id") or ""),
                rate_limit_remaining=str(response.headers.get("X-RateLimit-Remaining") or ""),
                quota_remaining=str(response.headers.get("X-Quota-Remaining") or ""),
                timed_out=False,
            )
        finally:
            response.close()

    return execute_cag_request(
        request,
        credential=credential,
        transport=transport,
        schema_validator=_live_cag_schema_validator,
    )


def execute_cag_request(
    request: WolframCagRequest,
    *,
    credential: WolframCagCredential | None,
    transport,
    schema_validator,
) -> WolframCagReceipt:
    """Execute a bounded CAG transport call.

    ``transport(request, component, credential, credential_secret)`` is an
    adapter boundary returning a ``CagHttpOutcome``. This low-level executor
    intentionally passes ``credential_secret=None``; the live transport
    resolves the owner-managed credential just-in-time at the final HTTP
    boundary and verifies it against ``credential_hash``. Strict validation:
    a 2xx without a valid schema or content type is never accepted as success.
    """
    component = request.validate()
    provision = provision_cag_component(
        capability_id=request.capability_id,
        credential=credential,
    )
    if provision is WolframCagStatus.UNAVAILABLE:
        raise WolframCagError(
            "CAG component not provisioned",
            family=WolframCagErrorFamily.RESULT_UNAVAILABLE,
        )
    if provision is WolframCagStatus.NOT_ENTITLED:
        raise WolframCagError(
            "CAG component not entitled",
            family=WolframCagErrorFamily.ENTITLEMENT,
        )
    if provision is WolframCagStatus.BLOCKED:
        raise WolframCagError(
            "CAG component blocked",
            family=WolframCagErrorFamily.SCHEMA,
        )

    attempt = 0
    last_error: WolframCagError | None = None
    outcome: CagHttpOutcome | None = None
    while attempt <= component.max_retries:
        attempt += 1
        try:
            outcome = transport(
                request=request,
                component=component,
                credential=credential,
                credential_secret=None,
            )
        except TimeoutError as exc:
            family = WolframCagErrorFamily.TIMEOUT
            last_error = WolframCagError("CAG provider request timed out", family=family)
            if cag_retry_decision(family, attempt, component.max_retries) is WolframCagRetryDecision.SAFE_TO_RETRY:
                continue
            raise last_error from exc
        except WolframCagError as exc:
            last_error = exc
            if cag_retry_decision(exc.family, attempt, component.max_retries) is WolframCagRetryDecision.SAFE_TO_RETRY:
                continue
            raise
        if outcome is None:
            family = WolframCagErrorFamily.UPSTREAM
            last_error = WolframCagError("transport returned no outcome", family=family)
            if cag_retry_decision(family, attempt, component.max_retries) is WolframCagRetryDecision.SAFE_TO_RETRY:
                continue
            raise last_error

        if outcome.timed_out:
            family = WolframCagErrorFamily.TIMEOUT
            last_error = WolframCagError(
                "CAG request timed out",
                family=family,
                status=outcome.status,
                response_uuid=outcome.response_uuid,
                request_id=outcome.request_id,
            )
            if cag_retry_decision(family, attempt, component.max_retries) is WolframCagRetryDecision.SAFE_TO_RETRY:
                continue
            raise last_error

        status = outcome.status
        if not (200 <= status < 300):
            family = classify_cag_status(status=status, timed_out=False)
            last_error = WolframCagError(
                f"CAG transport returned status {status}",
                family=family,
                status=status,
                response_uuid=outcome.response_uuid,
                request_id=outcome.request_id,
            )
            if cag_retry_decision(family, attempt, component.max_retries) is WolframCagRetryDecision.SAFE_TO_RETRY:
                continue
            raise last_error

        # Strict content-type validation.
        if component.expected_content_type not in _normalize_header(outcome.content_type).lower():
            raise WolframCagError(
                "CAG response content-type does not match component contract",
                family=WolframCagErrorFamily.SCHEMA,
                status=status,
                response_uuid=outcome.response_uuid,
                request_id=outcome.request_id,
            )

        # Output size limit.
        if len(outcome.body) > component.max_output_bytes:
            raise WolframCagError(
                "CAG response exceeds output limit",
                family=WolframCagErrorFamily.SCHEMA,
                status=status,
                response_uuid=outcome.response_uuid,
                request_id=outcome.request_id,
            )

        # 2xx without a valid schema is never accepted as success.
        if not schema_validator(outcome.body, outcome.content_type, component):
            raise WolframCagError(
                "CAG response failed schema validation",
                family=WolframCagErrorFamily.SCHEMA,
                status=status,
                response_uuid=outcome.response_uuid,
                request_id=outcome.request_id,
            )

        response_hash = hashlib.sha256(outcome.body).hexdigest()
        receipt = WolframCagReceipt(
            capability_id=request.capability_id,
            component=component.component,
            base_url=component.base_url,
            endpoint_id=component.endpoint_id,
            request_hash=request.request_hash,
            credential_hash=credential.credential_hash if credential else "",
            response_status=status,
            response_hash=response_hash,
            response_uuid=outcome.response_uuid,
            request_id=outcome.request_id,
            rate_limit_remaining=outcome.rate_limit_remaining,
            quota_remaining=outcome.quota_remaining,
            response_schema_hash=request.response_schema_hash,
            status=WolframCagStatus.SUCCEEDED_UNVERIFIED,
        )
        receipt.validate()
        return receipt

    if last_error is not None:
        raise last_error
    raise WolframCagError(
        "CAG transport exhausted retries without outcome",
        family=WolframCagErrorFamily.UPSTREAM,
    )
