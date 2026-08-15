"""Strict command-request gateway for the NocoDB operator projection.

Issue #1174 acceptance: a UI button may at most produce a typed
``OperatorCommandRequestV1``. The gateway normalizes, validates against the
strict schema, binds owner/principal **server-side** (never trusting
client-supplied identities), and refuses to execute anything. Validated requests
are handed off as opaque ``GatewayCommand`` objects that downstream canonical
lanes (#1113 permission / #1118 tool policy / #1119 CAS-lock / #1120 identity /
#1100 readback) must consume. The gateway itself has no execution authority.

Security posture (fail closed):
- rejects any request carrying secret-shaped values anywhere in its strings;
- rejects unknown schema versions (no implicit forward-compat);
- rejects missing/empty source receipt hashes and base hash for mutations;
- never trusts client-supplied owner/principal fields inside the payload; the
  bound principal is injected by the gateway from the authenticated caller.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..contracts import sanitize_agent_text

SCHEMA_VERSION = "operator-command-request.v1"
_EFFECT_CLASSES = ("INSPECT", "BOUNDED_MUTATION")
_HASH_RE = "^(?:[0-9a-f]{40}|[0-9a-f]{64}|sha256:[0-9a-f]{64})$"
_SAFE_TOKEN_RE = "^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,255}$"
_MAX_REASON = 4000
_MAX_PARAMS = 64

_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent / "contracts" / "operator_command_request.v1.schema.json"
)


def load_schema() -> dict[str, Any]:
    """Load the strict JSON schema. Pure file read; no network."""
    return json.loads(_SCHEMA_PATH.read_text("utf-8"))


class OperatorCommandGatewayError(ValueError):
    """Base error for gateway rejection. A rejection is a valid result."""


class CommandRejected(OperatorCommandGatewayError):
    """The request did not satisfy the strict contract."""


class SecretRejected(OperatorCommandGatewayError):
    """The request carried secret-shaped content."""


@dataclass(frozen=True)
class OperatorCommandRequestV1:
    schemaVersion: str
    operatorProjectionRevision: str
    sourceReceiptHashes: tuple[str, ...]
    requestedCapabilityId: str
    targetResourceId: str
    expectedBaseHash: str
    normalizedParameters: dict[str, Any]
    requestedEffectClass: str
    reasonCode: str


@dataclass(frozen=True)
class BoundPrincipal:
    """Server-side identity binding. Never read from the client payload."""

    principal: str
    owner: str

    def __post_init__(self) -> None:
        for name, value in (("principal", self.principal), ("owner", self.owner)):
            if not isinstance(value, str) or not value.strip():
                raise OperatorCommandGatewayError(f"bound {name} must be a non-empty string")
            if value != sanitize_agent_text(value, len(value) + 8):
                raise OperatorCommandGatewayError(f"bound {name} is secret-shaped")


@dataclass(frozen=True)
class GatewayCommand:
    """Opaque, server-bound command ready for canonical lane handoff.

    Carries no execution authority and no client-supplied identity. ``commandHash``
    is a deterministic receipt over the bound request so downstream lanes can
    verify they consumed exactly what the gateway accepted.
    """

    schemaVersion: str
    requestedCapabilityId: str
    targetResourceId: str
    requestedEffectClass: str
    expectedBaseHash: str
    sourceReceiptHashes: tuple[str, ...]
    normalizedParameters: dict[str, Any]
    reasonCode: str
    boundPrincipal: BoundPrincipal
    operatorProjectionRevision: str
    commandHash: str
    routedTo: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schemaVersion,
            "requestedCapabilityId": self.requestedCapabilityId,
            "targetResourceId": self.targetResourceId,
            "requestedEffectClass": self.requestedEffectClass,
            "expectedBaseHash": self.expectedBaseHash,
            "sourceReceiptHashes": list(self.sourceReceiptHashes),
            "normalizedParameters": dict(self.normalizedParameters),
            "reasonCode": self.reasonCode,
            "boundPrincipal": self.boundPrincipal.principal,
            "boundOwner": self.boundPrincipal.owner,
            "operatorProjectionRevision": self.operatorProjectionRevision,
            "commandHash": self.commandHash,
            "routedTo": list(self.routedTo),
        }


# Canonical lane routing the gateway advertises. It performs none of these; it
# only declares the mandatory downstream chain a consumer must follow (#1174).
CANONICAL_LANE_CHAIN: tuple[str, ...] = (
    "context-tool-policy",  # #1118
    "permission-workflow",  # #1113
    "cas-resource-lock",  # #1119
    "identity-egress",  # #1120
    "target-readback",  # #1100
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _command_hash(request: OperatorCommandRequestV1, principal: BoundPrincipal) -> str:
    payload = {
        "schemaVersion": request.schemaVersion,
        "operatorProjectionRevision": request.operatorProjectionRevision,
        "sourceReceiptHashes": list(request.sourceReceiptHashes),
        "requestedCapabilityId": request.requestedCapabilityId,
        "targetResourceId": request.targetResourceId,
        "expectedBaseHash": request.expectedBaseHash,
        "normalizedParameters": request.normalizedParameters,
        "requestedEffectClass": request.requestedEffectClass,
        "reasonCode": request.reasonCode,
        "boundPrincipal": principal.principal,
        "boundOwner": principal.owner,
    }
    return "sha256:" + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _check_secret_shaped(*values: Any) -> None:
    for value in values:
        if not isinstance(value, str):
            continue
        if "[redacted]" in sanitize_agent_text(value, len(value) + 8):
            raise SecretRejected("operator command request contains secret-shaped content")


def _validate_strings(request: OperatorCommandRequestV1) -> None:
    import re

    if request.schemaVersion != SCHEMA_VERSION:
        raise CommandRejected(f"unsupported schemaVersion: {request.schemaVersion!r}")
    if request.requestedEffectClass not in _EFFECT_CLASSES:
        raise CommandRejected(f"invalid requestedEffectClass: {request.requestedEffectClass!r}")
    if not re.fullmatch(_HASH_RE, request.operatorProjectionRevision):
        raise CommandRejected("operatorProjectionRevision must be a bound hash/revision")
    if not re.fullmatch(_HASH_RE, request.expectedBaseHash):
        raise CommandRejected("expectedBaseHash must be a bound hash")
    if not re.fullmatch(_SAFE_TOKEN_RE, request.requestedCapabilityId):
        raise CommandRejected("requestedCapabilityId is not a safe token")
    if not re.fullmatch(_SAFE_TOKEN_RE, request.targetResourceId):
        raise CommandRejected("targetResourceId is not a safe token")
    if not request.reasonCode or len(request.reasonCode) > _MAX_REASON:
        raise CommandRejected("reasonCode must be 1..4000 chars")
    if len(request.sourceReceiptHashes) == 0:
        raise CommandRejected("sourceReceiptHashes must not be empty")
    for h in request.sourceReceiptHashes:
        if not re.fullmatch(_HASH_RE, h):
            raise CommandRejected(f"sourceReceiptHash is not a bound hash: {h!r}")
    if request.requestedEffectClass == "BOUNDED_MUTATION":
        if not request.expectedBaseHash:
            raise CommandRejected("BOUNDED_MUTATION requires expectedBaseHash")


def _validate_parameters(params: Any) -> dict[str, Any]:
    if not isinstance(params, Mapping):
        raise CommandRejected("normalizedParameters must be an object")
    if len(params) > _MAX_PARAMS:
        raise CommandRejected("normalizedParameters exceeds 64 keys")
    out: dict[str, Any] = {}
    for key, value in params.items():
        key = str(key)
        if not key:
            raise CommandRejected("normalizedParameters has empty key")
        if not isinstance(value, (str, int, float, bool)) and value is not None:
            raise CommandRejected(
                f"normalizedParameters[{key!r}] must be string/number/boolean/null"
            )
        out[key] = value
    return out


def parse_request(payload: Mapping[str, Any]) -> OperatorCommandRequestV1:
    """Parse and structurally validate a client payload without trusting it."""
    if not isinstance(payload, Mapping):
        raise CommandRejected("operator command request must be a JSON object")
    # additionalProperties: false -> reject unknown keys defensively.
    allowed = {
        "schemaVersion",
        "operatorProjectionRevision",
        "sourceReceiptHashes",
        "requestedCapabilityId",
        "targetResourceId",
        "expectedBaseHash",
        "normalizedParameters",
        "requestedEffectClass",
        "reasonCode",
    }
    unknown = set(payload) - allowed
    if unknown:
        raise CommandRejected(f"unknown fields: {sorted(unknown)}")
    try:
        request = OperatorCommandRequestV1(
            schemaVersion=str(payload.get("schemaVersion", "")),
            operatorProjectionRevision=str(payload.get("operatorProjectionRevision", "")),
            sourceReceiptHashes=tuple(str(h) for h in (payload.get("sourceReceiptHashes") or [])),
            requestedCapabilityId=str(payload.get("requestedCapabilityId", "")),
            targetResourceId=str(payload.get("targetResourceId", "")),
            expectedBaseHash=str(payload.get("expectedBaseHash", "")),
            normalizedParameters=dict(payload.get("normalizedParameters") or {}),
            requestedEffectClass=str(payload.get("requestedEffectClass", "")),
            reasonCode=str(payload.get("reasonCode", "")),
        )
    except Exception as exc:  # pragma: no cover - defensive
        raise CommandRejected(f"malformed request: {exc}") from exc

    # Secret scan across every string field before any further trust.
    _check_secret_shaped(
        request.requestedCapabilityId,
        request.targetResourceId,
        request.reasonCode,
        request.expectedBaseHash,
        request.operatorProjectionRevision,
    )
    request = OperatorCommandRequestV1(
        request.schemaVersion,
        request.operatorProjectionRevision,
        request.sourceReceiptHashes,
        request.requestedCapabilityId,
        request.targetResourceId,
        request.expectedBaseHash,
        _validate_parameters(request.normalizedParameters),
        request.requestedEffectClass,
        request.reasonCode,
    )
    _validate_strings(request)
    # Deep secret scan over parameter string values.
    for value in request.normalizedParameters.values():
        if isinstance(value, str):
            _check_secret_shaped(value)
    return request


def gateway_accept(
    payload: Mapping[str, Any],
    bound_principal: BoundPrincipal,
) -> GatewayCommand:
    """Validate a client request and bind it to an authenticated principal.

    This is the only entry point that yields a ``GatewayCommand``. It never
    executes the requested effect; it only produces a server-bound receipt for
    the canonical lane chain to consume.
    """
    request = parse_request(payload)
    command_hash = _command_hash(request, bound_principal)
    return GatewayCommand(
        schemaVersion=request.schemaVersion,
        requestedCapabilityId=request.requestedCapabilityId,
        targetResourceId=request.targetResourceId,
        requestedEffectClass=request.requestedEffectClass,
        expectedBaseHash=request.expectedBaseHash,
        sourceReceiptHashes=request.sourceReceiptHashes,
        normalizedParameters=dict(request.normalizedParameters),
        reasonCode=request.reasonCode,
        boundPrincipal=bound_principal,
        operatorProjectionRevision=request.operatorProjectionRevision,
        commandHash=command_hash,
        routedTo=CANONICAL_LANE_CHAIN,
    )


__all__ = [
    "SCHEMA_VERSION",
    "CANONICAL_LANE_CHAIN",
    "BoundPrincipal",
    "OperatorCommandRequestV1",
    "GatewayCommand",
    "CommandRejected",
    "SecretRejected",
    "OperatorCommandGatewayError",
    "load_schema",
    "parse_request",
    "gateway_accept",
]
