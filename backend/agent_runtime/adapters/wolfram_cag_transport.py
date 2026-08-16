"""Canonical, secret-safe Wolfram CAG Component transport (fail-closed).

This module implements the foundational transport contract for the four
Wolfram CAG Component APIs required by issue #1459:

    wolfram.cag.hints     -> Wolfram Language Hints API
    wolfram.cag.compute   -> Wolfram Language Computation API
    wolfram.cag.results   -> Wolfram|Alpha Results API
    wolfram.cag.context   -> Wolfram|Alpha Context API

Design rules (see #1457 / #1459):

- Server-side credential resolution only. No browser/chat secrets ever cross
  this boundary, and no secret value is returned, logged or hashed.
- Fixed base URLs / endpoint IDs. There is no free model URL and no free
  Wolfram execution outside the explicitly allowed Computation contract.
- Explicit timeouts, output limits and request-size limits, all testable.
- Strict Content-Type / schema / status validation. A 2xx without a valid
  schema is never accepted as success.
- Normalized error families: AUTH, ENTITLEMENT, QUOTA, RATE_LIMIT, TIMEOUT,
  UPSTREAM, SCHEMA, RESULT_UNAVAILABLE.
- A CAG response can never directly mutate GitHub, Docker, DB, PatchMon or a
  deployment; every capability is read-only compute/knowledge.

Truth boundary
--------------
Until real Wolfram account/API provisioning evidence exists (issue #1458),
every component honestly resolves to ``NOT_ENTITLED`` and no transport call is
permitted. This is the intended fail-closed behaviour: provider success is not
product success, and the absence of entitlement evidence is itself the truth.
This module intentionally performs NO live HTTP: live execution is gated
behind a real ``CagEntitlementVerdict`` that only issue #1458 can populate.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

# ---------------------------------------------------------------------------
# Fixed transport constants. These are endpoint identities, not free URLs.
# ---------------------------------------------------------------------------

CAG_CONTRACT_VERSION = "wolfram-cag-transport.v1"

# Canonical base hosts for the four provisioned Component APIs. These are
# fixed identities; callers may not override them with arbitrary URLs.
CAG_BASE_HOSTS: Mapping[str, str] = {
    "wolfram.cag.hints": "https://www.wolframcloud.com",
    "wolfram.cag.compute": "https://www.wolframcloud.com",
    "wolfram.cag.results": "https://api.wolframalpha.com",
    "wolfram.cag.context": "https://api.wolframalpha.com",
}

DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_MAX_OUTPUT_BYTES = 1_000_000
DEFAULT_MAX_REQUEST_BYTES = 64_000
DEFAULT_MAX_RETRIES = 2

_HASH = re.compile(r"^[0-9a-f]{64}$")
_COMPONENT_ID = re.compile(r"^wolfram\.cag\.(hints|compute|results|context)$")
_SAFE_SUMMARY = re.compile(r"[\x00-\x1f]")  # control chars disallowed in summaries


class CagErrorFamily(str, Enum):
    AUTH = "AUTH"
    ENTITLEMENT = "ENTITLEMENT"
    QUOTA = "QUOTA"
    RATE_LIMIT = "RATE_LIMIT"
    TIMEOUT = "TIMEOUT"
    UPSTREAM = "UPSTREAM"
    SCHEMA = "SCHEMA"
    RESULT_UNAVAILABLE = "RESULT_UNAVAILABLE"


class CagComponentStatus(str, Enum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_ENTITLED = "NOT_ENTITLED"
    UNKNOWN = "UNKNOWN"


class CagVerdict(str, Enum):
    # A transport receipt may only carry these bounded verdicts. A CAG result
    # is never allowed to self-assert VERIFIED; that is reserved for the
    # Sovereign Evidence/Judge lane (#1460).
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    UNAVAILABLE = "UNAVAILABLE"


class CagTransportError(ValueError):
    """Raised for contract violations (bad request shape, forbidden params)."""

    def __init__(self, message: str, family: CagErrorFamily = CagErrorFamily.SCHEMA) -> None:
        super().__init__(message)
        self.family = family


class CagEntitlementState(str, Enum):
    # Entitlement is resolved server-side from #1458 evidence. Until then the
    # only honest state is NOT_ENTITLED.
    ENTITLED = "ENTITLED"
    NOT_ENTITLED = "NOT_ENTITLED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class CagEntitlementVerdict:
    """Secret-free entitlement evidence bound to a component.

    ``auth_evidence_hash`` is a SHA-256 over a redacted, secret-free
    representation of the last successful auth/entitlement canary. It MUST NOT
    contain a credential value. ``terms_version_date`` records the contractual
    terms snapshot date so downstream lanes can fail-closed on stale terms.
    """

    component_id: str
    state: CagEntitlementState
    auth_evidence_hash: str = ""
    terms_version_date: str = ""
    quota_class: str = "UNKNOWN"
    commercial_use_allowed: bool | None = None

    def validate(self) -> None:
        if not _COMPONENT_ID.fullmatch(self.component_id):
            raise CagTransportError("invalid component id", CagErrorFamily.SCHEMA)
        if self.auth_evidence_hash and not _HASH.fullmatch(self.auth_evidence_hash):
            raise CagTransportError("auth evidence must be a SHA-256 hash", CagErrorFamily.SCHEMA)
        if self.state is CagEntitlementState.ENTITLED and not self.auth_evidence_hash:
            raise CagTransportError(
                "ENTITLED requires secret-free auth evidence hash",
                CagErrorFamily.ENTITLEMENT,
            )

    def is_usable(self) -> bool:
        try:
            self.validate()
        except CagTransportError:
            return False
        return self.state is CagEntitlementState.ENTITLED and bool(self.auth_evidence_hash)


@dataclass(frozen=True, slots=True)
class CagEndpointContract:
    capability_id: str
    component_id: str
    endpoint_id: str
    method: str
    base_host: str
    read_only: bool
    allows_free_execution: bool


CAG_CAPABILITY_MAP: Mapping[str, CagEndpointContract] = {
    "wolfram.cag.hints": CagEndpointContract(
        "wolfram.cag.hints", "wolfram.cag.hints", "cag.hints.query", "GET",
        CAG_BASE_HOSTS["wolfram.cag.hints"], True, False,
    ),
    "wolfram.cag.compute": CagEndpointContract(
        "wolfram.cag.compute", "wolfram.cag.compute", "cag.compute.evaluate", "POST",
        CAG_BASE_HOSTS["wolfram.cag.compute"], True, False,
    ),
    "wolfram.cag.results": CagEndpointContract(
        "wolfram.cag.results", "wolfram.cag.results", "cag.results.query", "GET",
        CAG_BASE_HOSTS["wolfram.cag.results"], True, False,
    ),
    "wolfram.cag.context": CagEndpointContract(
        "wolfram.cag.context", "wolfram.cag.context", "cag.context.query", "GET",
        CAG_BASE_HOSTS["wolfram.cag.context"], True, False,
    ),
}

# Capabilities projected into the existing Sovereign capability surface. No new
# registry is created; this map is the bounded CAG projection of #1165.
CAG_CAPABILITY_IDS = tuple(CAG_CAPABILITY_MAP.keys())


@dataclass(frozen=True, slots=True)
class CagRequestV1:
    """Typed, bounded request contract for a single CAG component call."""

    capability_id: str
    input_text: str
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES
    request_id: str = ""
    # Optional redacted provenance; never a credential.
    sovereign_run_id: str = ""

    def validate(self) -> CagEndpointContract:
        contract = CAG_CAPABILITY_MAP.get(self.capability_id)
        if contract is None:
            raise CagTransportError("unknown CAG capability", CagErrorFamily.SCHEMA)
        if not isinstance(self.input_text, str) or not self.input_text.strip():
            raise CagTransportError("non-empty input text is required", CagErrorFamily.SCHEMA)
        if len(self.input_text.encode("utf-8")) > DEFAULT_MAX_REQUEST_BYTES:
            raise CagTransportError("input exceeds max request size", CagErrorFamily.SCHEMA)
        if self.timeout_seconds <= 0 or self.timeout_seconds > 60:
            raise CagTransportError("timeout must be in (0, 60] seconds", CagErrorFamily.SCHEMA)
        if self.max_output_bytes <= 0 or self.max_output_bytes > DEFAULT_MAX_OUTPUT_BYTES:
            raise CagTransportError("output limit out of bounds", CagErrorFamily.SCHEMA)
        return contract

    @property
    def input_hash(self) -> str:
        payload = {
            "schemaVersion": CAG_CONTRACT_VERSION,
            "capabilityId": self.capability_id,
            "inputText": self.input_text,
            "timeoutSeconds": self.timeout_seconds,
            "maxOutputBytes": self.max_output_bytes,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class CagTransportReceipt:
    """Secret-free, hash/revision-bound transport evidence for one CAG call.

    A receipt never carries a credential, never self-asserts VERIFIED, and
    never proves repository/runtime/deployment truth. It is bounded transport
    evidence that the Sovereign Evidence/Judge lane (#1460) consumes.
    """

    capability_id: str
    contract_version: str
    endpoint_id: str
    request_hash: str
    response_status: int
    response_hash: str
    response_uuid: str
    component_status: CagComponentStatus
    verdict: CagVerdict
    error_family: CagErrorFamily | None
    latency_ms: int
    quota_class: str
    bounded_summary: str = ""
    truth_notice: str = (
        "CAG output is supplemental compute/knowledge evidence. It cannot "
        "verify repository, runtime, deployment, PatchMon, ARE or Kappa truth."
    )

    def validate(self) -> None:
        if self.capability_id not in CAG_CAPABILITY_MAP:
            raise CagTransportError("receipt references unknown capability", CagErrorFamily.SCHEMA)
        if not _HASH.fullmatch(self.request_hash) or not _HASH.fullmatch(self.response_hash):
            raise CagTransportError("receipt hashes must be SHA-256", CagErrorFamily.SCHEMA)
        if self.verdict is CagVerdict.SUPPORTED and self.component_status is not CagComponentStatus.READY:
            raise CagTransportError(
                "SUPPORTED requires READY component status", CagErrorFamily.SCHEMA
            )
        if _SAFE_SUMMARY.search(self.bounded_summary or ""):
            raise CagTransportError("summary must not contain control characters", CagErrorFamily.SCHEMA)


def _secret_free_response_hash(response_payload: Mapping[str, object]) -> str:
    """Canonicalize a redacted response into a stable SHA-256.

    Credential-bearing fields are stripped before hashing so a secret can never
    leak into a receipt or log. Only known, safe metadata keys are retained.
    """
    safe_keys = ("success", "result", "expression", "output", "units", "assumptions", "datatypes")
    redacted: dict[str, object] = {}
    for key in safe_keys:
        if key in response_payload:
            redacted[key] = response_payload[key]
    return hashlib.sha256(
        json.dumps(redacted, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def resolve_component_status(
    capability_id: str,
    entitlement: CagEntitlementVerdict | None,
) -> CagComponentStatus:
    """Honest component status. Without real entitlement evidence -> NOT_ENTITLED."""
    if capability_id not in CAG_CAPABILITY_MAP:
        raise CagTransportError("unknown CAG capability", CagErrorFamily.SCHEMA)
    if entitlement is None:
        return CagComponentStatus.NOT_ENTITLED
    try:
        entitlement.validate()
    except CagTransportError:
        return CagComponentStatus.UNKNOWN
    if entitlement.component_id != capability_id:
        return CagComponentStatus.NOT_ENTITLED
    if not entitlement.is_usable():
        return (
            CagComponentStatus.NOT_ENTITLED
            if entitlement.state is CagEntitlementState.NOT_ENTITLED
            else CagComponentStatus.UNKNOWN
        )
    return CagComponentStatus.READY


def authorize_cag_call(
    request: CagRequestV1,
    entitlement: CagEntitlementVerdict | None,
) -> CagEndpointContract:
    """Authorize a bounded CAG call. Returns the contract or raises closed.

    The transport performs NO live HTTP here. Live execution is only permitted
    once ``resolve_component_status`` returns READY, which requires real
    entitlement evidence from issue #1458. Until then every call is blocked
    fail-closed.
    """
    contract = request.validate()
    status = resolve_component_status(request.capability_id, entitlement)
    if status is not CagComponentStatus.READY:
        raise CagTransportError(
            f"CAG component not ready: {status.value}",
            CagErrorFamily.ENTITLEMENT,
        )
    # Defense in depth: a CAG capability must never mutate or execute freely.
    if not contract.read_only or contract.allows_free_execution:
        raise CagTransportError("CAG contracts must be read-only and bounded", CagErrorFamily.SCHEMA)
    return contract


def classify_http_status(status: int) -> CagErrorFamily:
    """Map an upstream HTTP status to a normalized error family.

    401/403 -> AUTH, 402 -> QUOTA, 404 -> RESULT_UNAVAILABLE,
    429 -> RATE_LIMIT, 5xx -> UPSTREAM, anything else unexpected -> UPSTREAM.
    """
    if status in (401, 403):
        return CagErrorFamily.AUTH
    if status == 402:
        return CagErrorFamily.QUOTA
    if status == 404:
        return CagErrorFamily.RESULT_UNAVAILABLE
    if status == 429:
        return CagErrorFamily.RATE_LIMIT
    if 500 <= status < 600:
        return CagErrorFamily.UPSTREAM
    return CagErrorFamily.UPSTREAM


def validate_response_schema(
    capability_id: str,
    status: int,
    content_type: str,
    body: Mapping[str, object],
) -> None:
    """Strict response validation. A 2xx without a valid schema is not success."""
    if capability_id not in CAG_CAPABILITY_MAP:
        raise CagTransportError("unknown capability for schema check", CagErrorFamily.SCHEMA)
    if not (200 <= status < 300):
        raise CagTransportError(
            f"non-2xx status {status}", classify_http_status(status)
        )
    if "application/json" not in content_type.lower():
        raise CagTransportError("CAG responses must be JSON", CagErrorFamily.SCHEMA)
    if not isinstance(body, Mapping):
        raise CagTransportError("response body must be a JSON object", CagErrorFamily.SCHEMA)
    required = "success" if capability_id in ("wolfram.cag.results", "wolfram.cag.context") else "result"
    if required not in body:
        raise CagTransportError(
            f"2xx response missing required '{required}' field",
            CagErrorFamily.SCHEMA,
        )


def build_receipt(
    request: CagRequestV1,
    *,
    response_status: int,
    response_body: Mapping[str, object],
    response_uuid: str,
    component_status: CagComponentStatus,
    verdict: CagVerdict,
    latency_ms: int,
    quota_class: str,
    error_family: CagErrorFamily | None = None,
    bounded_summary: str = "",
) -> CagTransportReceipt:
    """Build a validated, secret-free transport receipt from a call result."""
    contract = request.validate()
    response_hash = _secret_free_response_hash(response_body)
    receipt = CagTransportReceipt(
        capability_id=request.capability_id,
        contract_version=CAG_CONTRACT_VERSION,
        endpoint_id=contract.endpoint_id,
        request_hash=request.input_hash,
        response_status=response_status,
        response_hash=response_hash,
        response_uuid=response_uuid,
        component_status=component_status,
        verdict=verdict,
        error_family=error_family,
        latency_ms=latency_ms,
        quota_class=quota_class or "UNKNOWN",
        bounded_summary=bounded_summary,
    )
    receipt.validate()
    return receipt


def not_entitled_receipt(request: CagRequestV1) -> CagTransportReceipt:
    """The honest receipt returned when no provisioning evidence exists.

    This is the canonical fail-closed path for issue #1459: until #1458
    provisions real evidence, every CAG call resolves here. It is real,
    deterministic, secret-free evidence that the component is NOT_ENTITLED.
    """
    request.validate()
    return build_receipt(
        request,
        response_status=0,
        response_body={},
        response_uuid="",
        component_status=CagComponentStatus.NOT_ENTITLED,
        verdict=CagVerdict.UNAVAILABLE,
        latency_ms=0,
        quota_class="UNKNOWN",
        error_family=CagErrorFamily.ENTITLEMENT,
        bounded_summary="no provisioning evidence; component not entitled",
    )
