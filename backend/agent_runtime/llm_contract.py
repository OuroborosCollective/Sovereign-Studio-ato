"""Provider-neutral schema, revision and hash contracts for routed LLM calls.

The contract is pure and fail-closed. It performs no provider, network,
database, filesystem, clock or random access. OpenRouter paid routes and direct
FreeLLM routes use the same request envelope and response verifier while their
billing and readiness truth remains separate.

A schema-valid response proves only structural conformance. Semantic truth is
VERIFIED only when every declared semantic requirement has an OBSERVED,
hash-bound observation. Provider responses, prompts and secrets are never
stored in receipts; only canonical hashes and bounded finding codes are kept.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from types import MappingProxyType
from typing import Any, Final, Mapping, Sequence

from llm_transport import (
    route_is_direct_freellm,
    route_is_openrouter_paid,
    route_provider_model,
    route_snapshot_hashes,
    route_transport,
)

from .provider_neutral_runtime import canonical_sha256

LLM_OUTPUT_CONTRACT_SCHEMA: Final[str] = "sovereign.llm-output-contract.v1"
LLM_ROUTE_BINDING_SCHEMA: Final[str] = "sovereign.llm-route-binding.v1"
LLM_REQUEST_ENVELOPE_SCHEMA: Final[str] = "sovereign.llm-request-envelope.v1"
LLM_RESPONSE_RECEIPT_SCHEMA: Final[str] = "sovereign.llm-response-receipt.v1"

ROUTE_CLASS_OPENROUTER_PAID: Final[str] = "OPENROUTER_PAID"
ROUTE_CLASS_FREELLM_FREE: Final[str] = "FREELLM_FREE"
ZERO_SHA256: Final[str] = "0" * 64

_SHA40_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_SHA64_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_.:-]{1,119}$")
_ALLOWED_SCHEMA_TYPES: Final[frozenset[str]] = frozenset(
    {"object", "array", "string", "integer", "boolean", "null"}
)
_ALLOWED_SCHEMA_KEYS: Final[frozenset[str]] = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "minimum",
        "maximum",
        "description",
    }
)
_ALLOWED_ASSERTIONS: Final[frozenset[str]] = frozenset(
    {"OBSERVED", "CONTRADICTED", "UNAVAILABLE"}
)


class LlmContractError(ValueError):
    """One LLM contract input violated a deterministic truth boundary."""


def _identifier(value: str, *, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _IDENTIFIER_RE.fullmatch(normalized):
        raise LlmContractError(f"{label} must be a canonical identifier")
    return normalized


def _sha40(value: str, *, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _SHA40_RE.fullmatch(normalized):
        raise LlmContractError(f"{label} must be an exact lowercase Git SHA-40")
    return normalized


def _sha64(value: str, *, label: str, allow_zero: bool = True) -> str:
    normalized = str(value or "").strip().lower()
    if not _SHA64_RE.fullmatch(normalized):
        raise LlmContractError(f"{label} must be a lowercase SHA-256")
    if not allow_zero and normalized == ZERO_SHA256:
        raise LlmContractError(f"{label} may not be the zero SHA-256")
    return normalized


def _bounded_text(value: Any, maximum: int) -> str:
    text = str(value or "").strip()
    return text[:maximum]


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _exact_int(value: Any) -> bool:
    return type(value) is int


def _canonical_schema(schema: Mapping[str, Any], *, path: str = "$") -> dict[str, Any]:
    if not isinstance(schema, Mapping):
        raise LlmContractError(f"schema at {path} must be an object")
    unknown = sorted(set(schema) - _ALLOWED_SCHEMA_KEYS)
    if unknown:
        raise LlmContractError(f"unsupported schema keywords at {path}: {', '.join(unknown)}")
    schema_type = str(schema.get("type") or "").strip()
    if schema_type not in _ALLOWED_SCHEMA_TYPES:
        raise LlmContractError(f"schema at {path} requires one supported explicit type")

    canonical: dict[str, Any] = {"type": schema_type}
    description = schema.get("description")
    if description is not None:
        canonical["description"] = _bounded_text(description, 1_000)

    enum = schema.get("enum")
    if enum is not None:
        if not isinstance(enum, (list, tuple)) or not enum:
            raise LlmContractError(f"enum at {path} must be a non-empty array")
        normalized_enum: list[Any] = []
        for item in enum:
            if item is None or isinstance(item, (str, bool)) or _exact_int(item):
                normalized_enum.append(item)
            else:
                raise LlmContractError(f"enum at {path} contains a non-canonical value")
        canonical["enum"] = normalized_enum

    for key in ("minLength", "maxLength", "minItems", "maxItems", "minimum", "maximum"):
        if key in schema:
            value = schema[key]
            if not _exact_int(value) or value < 0:
                raise LlmContractError(f"{key} at {path} must be a non-negative integer")
            canonical[key] = value

    if schema_type == "object":
        properties = schema.get("properties")
        if not isinstance(properties, Mapping):
            raise LlmContractError(f"object schema at {path} requires properties")
        canonical_properties: dict[str, Any] = {}
        for raw_name in sorted(properties):
            if not isinstance(raw_name, str) or not raw_name:
                raise LlmContractError(f"property names at {path} must be non-empty strings")
            canonical_properties[raw_name] = _canonical_schema(
                properties[raw_name], path=f"{path}.{raw_name}"
            )
        required = schema.get("required", ())
        if not isinstance(required, (list, tuple)):
            raise LlmContractError(f"required at {path} must be an array")
        required_names = tuple(sorted({str(item) for item in required}))
        if any(name not in canonical_properties for name in required_names):
            raise LlmContractError(f"required at {path} references an unknown property")
        if schema.get("additionalProperties") is not False:
            raise LlmContractError(
                f"object schema at {path} must set additionalProperties=false"
            )
        canonical["properties"] = canonical_properties
        canonical["required"] = list(required_names)
        canonical["additionalProperties"] = False
    elif schema_type == "array":
        items = schema.get("items")
        if not isinstance(items, Mapping):
            raise LlmContractError(f"array schema at {path} requires items")
        canonical["items"] = _canonical_schema(items, path=f"{path}[]")
    elif "properties" in schema or "required" in schema or "items" in schema:
        raise LlmContractError(f"schema keywords do not match type at {path}")

    if canonical.get("maxLength", 0) and canonical.get("minLength", 0) > canonical["maxLength"]:
        raise LlmContractError(f"minLength exceeds maxLength at {path}")
    if canonical.get("maxItems", 0) and canonical.get("minItems", 0) > canonical["maxItems"]:
        raise LlmContractError(f"minItems exceeds maxItems at {path}")
    if "maximum" in canonical and canonical.get("minimum", 0) > canonical["maximum"]:
        raise LlmContractError(f"minimum exceeds maximum at {path}")
    return canonical


def _validate_value(value: Any, schema: Mapping[str, Any], *, path: str = "$") -> None:
    schema_type = schema["type"]
    if schema_type == "object":
        if not isinstance(value, Mapping):
            raise LlmContractError(f"response value at {path} must be an object")
        properties = schema["properties"]
        missing = [name for name in schema["required"] if name not in value]
        if missing:
            raise LlmContractError(
                f"response value at {path} is missing required properties: {', '.join(missing)}"
            )
        extras = sorted(set(value) - set(properties))
        if extras:
            raise LlmContractError(
                f"response value at {path} contains additional properties: {', '.join(extras)}"
            )
        for name, item in value.items():
            _validate_value(item, properties[name], path=f"{path}.{name}")
    elif schema_type == "array":
        if not isinstance(value, (list, tuple)):
            raise LlmContractError(f"response value at {path} must be an array")
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise LlmContractError(f"response array at {path} is shorter than minItems")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise LlmContractError(f"response array at {path} exceeds maxItems")
        for index, item in enumerate(value):
            _validate_value(item, schema["items"], path=f"{path}[{index}]")
    elif schema_type == "string":
        if not isinstance(value, str):
            raise LlmContractError(f"response value at {path} must be a string")
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise LlmContractError(f"response string at {path} is shorter than minLength")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise LlmContractError(f"response string at {path} exceeds maxLength")
    elif schema_type == "integer":
        if not _exact_int(value):
            raise LlmContractError(f"response value at {path} must be an integer")
        if "minimum" in schema and value < schema["minimum"]:
            raise LlmContractError(f"response integer at {path} is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise LlmContractError(f"response integer at {path} exceeds maximum")
    elif schema_type == "boolean":
        if type(value) is not bool:
            raise LlmContractError(f"response value at {path} must be a boolean")
    elif schema_type == "null":
        if value is not None:
            raise LlmContractError(f"response value at {path} must be null")
    else:  # pragma: no cover - guarded by schema construction
        raise LlmContractError(f"unsupported response schema type at {path}")

    if "enum" in schema and value not in schema["enum"]:
        raise LlmContractError(f"response value at {path} is not an allowed enum value")


def _response_payload(response: Any) -> Any:
    if isinstance(response, str):
        text = response.strip()
        fenced = re.fullmatch(
            r"```(?:json)?\s*(.*?)\s*```",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if fenced:
            text = fenced.group(1).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LlmContractError("model response is not valid JSON") from exc
    if hasattr(response, "model_dump") and callable(response.model_dump):
        return response.model_dump()
    if isinstance(response, Mapping):
        return dict(response)
    raise LlmContractError("model response is not a supported structured value")


@dataclass(frozen=True, slots=True)
class LlmOutputContract:
    contract_id: str
    version: int
    json_schema: Mapping[str, Any]
    semantic_requirement_ids: tuple[str, ...] = ()
    schema_version: str = LLM_OUTPUT_CONTRACT_SCHEMA
    contract_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        contract_id = _identifier(self.contract_id, label="contract_id")
        if not _exact_int(self.version) or self.version < 1:
            raise LlmContractError("contract version must be a positive integer")
        canonical_schema = _canonical_schema(self.json_schema)
        if canonical_schema["type"] != "object":
            raise LlmContractError("LLM output contract root schema must be an object")
        requirements = tuple(
            sorted({_identifier(item, label="semantic_requirement_id") for item in self.semantic_requirement_ids})
        )
        if self.schema_version != LLM_OUTPUT_CONTRACT_SCHEMA:
            raise LlmContractError("unsupported LLM output contract schema version")
        object.__setattr__(self, "contract_id", contract_id)
        object.__setattr__(self, "json_schema", _freeze(canonical_schema))
        object.__setattr__(self, "semantic_requirement_ids", requirements)
        object.__setattr__(self, "contract_sha256", canonical_sha256(self.canonical_body()))

    def canonical_body(self) -> dict[str, Any]:
        return {
            "contractId": self.contract_id,
            "version": self.version,
            "jsonSchema": _plain(self.json_schema),
            "semanticRequirementIds": list(self.semantic_requirement_ids),
            "schemaVersion": self.schema_version,
        }

    def response_format(self) -> dict[str, Any]:
        """Return an OpenAI-compatible optional provider JSON-schema hint.

        Local verification remains mandatory because a provider hint is not
        runtime evidence and some FreeLLM routes may ignore it.
        """
        return {
            "type": "json_schema",
            "json_schema": {
                "name": self.contract_id.replace(".", "_").replace(":", "_"),
                "strict": True,
                "schema": _plain(self.json_schema),
            },
        }


@dataclass(frozen=True, slots=True)
class LlmRouteBinding:
    source_revision: str
    route_id: str
    transport: str
    route_class: str
    provider_model: str
    route_snapshot_sha256: str
    price_snapshot_sha256: str
    schema_version: str = LLM_ROUTE_BINDING_SCHEMA
    binding_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        revision = _sha40(self.source_revision, label="source_revision")
        route_id = _bounded_text(self.route_id, 240)
        provider_model = _bounded_text(self.provider_model, 240)
        if not route_id or not provider_model:
            raise LlmContractError("route_id and provider_model are required")
        transport = str(self.transport or "").strip().lower()
        if transport not in {"openrouter", "freellm"}:
            raise LlmContractError("transport must be openrouter or freellm")
        route_class = str(self.route_class or "").strip().upper()
        expected_class = (
            ROUTE_CLASS_OPENROUTER_PAID
            if transport == "openrouter"
            else ROUTE_CLASS_FREELLM_FREE
        )
        if route_class != expected_class:
            raise LlmContractError("route_class does not match transport")
        route_hash = _sha64(
            self.route_snapshot_sha256,
            label="route_snapshot_sha256",
            allow_zero=False,
        )
        price_hash = _sha64(self.price_snapshot_sha256, label="price_snapshot_sha256")
        if route_class == ROUTE_CLASS_OPENROUTER_PAID and price_hash == ZERO_SHA256:
            raise LlmContractError("OpenRouter paid route binding requires a price snapshot hash")
        if route_class == ROUTE_CLASS_FREELLM_FREE and price_hash != ZERO_SHA256:
            raise LlmContractError("FreeLLM route binding must not carry paid price evidence")
        if self.schema_version != LLM_ROUTE_BINDING_SCHEMA:
            raise LlmContractError("unsupported LLM route binding schema version")
        object.__setattr__(self, "source_revision", revision)
        object.__setattr__(self, "route_id", route_id)
        object.__setattr__(self, "provider_model", provider_model)
        object.__setattr__(self, "transport", transport)
        object.__setattr__(self, "route_class", route_class)
        object.__setattr__(self, "route_snapshot_sha256", route_hash)
        object.__setattr__(self, "price_snapshot_sha256", price_hash)
        object.__setattr__(self, "binding_sha256", canonical_sha256(self.canonical_body()))

    def canonical_body(self) -> dict[str, Any]:
        return {
            "sourceRevision": self.source_revision,
            "routeId": self.route_id,
            "transport": self.transport,
            "routeClass": self.route_class,
            "providerModel": self.provider_model,
            "routeSnapshotSha256": self.route_snapshot_sha256,
            "priceSnapshotSha256": self.price_snapshot_sha256,
            "schemaVersion": self.schema_version,
        }


def build_route_binding(route: Mapping[str, Any], *, source_revision: str) -> LlmRouteBinding:
    normalized_route = dict(route)
    if route_is_openrouter_paid(normalized_route):
        route_class = ROUTE_CLASS_OPENROUTER_PAID
    elif route_is_direct_freellm(normalized_route):
        route_class = ROUTE_CLASS_FREELLM_FREE
    else:
        raise LlmContractError("route is not an active verified OpenRouter-paid or direct FreeLLM route")
    route_hash, price_hash = route_snapshot_hashes(normalized_route)
    return LlmRouteBinding(
        source_revision=source_revision,
        route_id=str(normalized_route.get("id") or ""),
        transport=route_transport(normalized_route),
        route_class=route_class,
        provider_model=route_provider_model(normalized_route),
        route_snapshot_sha256=route_hash,
        price_snapshot_sha256=(
            price_hash if route_class == ROUTE_CLASS_OPENROUTER_PAID else ZERO_SHA256
        ),
    )


@dataclass(frozen=True, slots=True)
class LlmRequestEnvelope:
    operation_identity: str
    route_binding: LlmRouteBinding
    prompt_sha256: str
    context_sha256: str
    output_contract_sha256: str
    schema_version: str = LLM_REQUEST_ENVELOPE_SCHEMA
    request_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        operation = _identifier(self.operation_identity, label="operation_identity")
        if not isinstance(self.route_binding, LlmRouteBinding):
            raise LlmContractError("route_binding must be an LlmRouteBinding")
        prompt_hash = _sha64(self.prompt_sha256, label="prompt_sha256", allow_zero=False)
        context_hash = _sha64(self.context_sha256, label="context_sha256")
        contract_hash = _sha64(
            self.output_contract_sha256,
            label="output_contract_sha256",
            allow_zero=False,
        )
        if self.schema_version != LLM_REQUEST_ENVELOPE_SCHEMA:
            raise LlmContractError("unsupported LLM request envelope schema version")
        object.__setattr__(self, "operation_identity", operation)
        object.__setattr__(self, "prompt_sha256", prompt_hash)
        object.__setattr__(self, "context_sha256", context_hash)
        object.__setattr__(self, "output_contract_sha256", contract_hash)
        object.__setattr__(self, "request_sha256", canonical_sha256(self.canonical_body()))

    def canonical_body(self) -> dict[str, Any]:
        return {
            "operationIdentity": self.operation_identity,
            "routeBinding": self.route_binding.canonical_body(),
            "routeBindingSha256": self.route_binding.binding_sha256,
            "promptSha256": self.prompt_sha256,
            "contextSha256": self.context_sha256,
            "outputContractSha256": self.output_contract_sha256,
            "schemaVersion": self.schema_version,
        }


def build_request_envelope(
    *,
    operation_identity: str,
    route_binding: LlmRouteBinding,
    prompt: str,
    contract: LlmOutputContract,
    context: Mapping[str, Any] | None = None,
) -> LlmRequestEnvelope:
    prompt_text = str(prompt or "")
    if not prompt_text.strip():
        raise LlmContractError("prompt must not be empty")
    if len(prompt_text.encode("utf-8")) > 2_000_000:
        raise LlmContractError("prompt exceeds the two-megabyte contract bound")
    return LlmRequestEnvelope(
        operation_identity=operation_identity,
        route_binding=route_binding,
        prompt_sha256=hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
        context_sha256=canonical_sha256(dict(context or {})),
        output_contract_sha256=contract.contract_sha256,
    )


def compile_contract_prompt(
    *,
    envelope: LlmRequestEnvelope,
    contract: LlmOutputContract,
    prompt: str,
) -> str:
    if envelope.output_contract_sha256 != contract.contract_sha256:
        raise LlmContractError("request envelope is bound to a different output contract")
    metadata = {
        "requestSha256": envelope.request_sha256,
        "sourceRevision": envelope.route_binding.source_revision,
        "routeBindingSha256": envelope.route_binding.binding_sha256,
        "outputContractSha256": contract.contract_sha256,
        "outputSchema": _plain(contract.json_schema),
    }
    return (
        "SOVEREIGN_LLM_CONTRACT\n"
        + json.dumps(metadata, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        + "\nReturn exactly one JSON value matching outputSchema. Do not add markdown or commentary.\n"
        + str(prompt or "")
    )


@dataclass(frozen=True, slots=True)
class LlmSemanticObservation:
    requirement_id: str
    assertion: str
    source: str
    value_sha256: str
    observation_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        requirement = _identifier(self.requirement_id, label="requirement_id")
        assertion = str(self.assertion or "").strip().upper()
        if assertion not in _ALLOWED_ASSERTIONS:
            raise LlmContractError("unsupported semantic observation assertion")
        source = _identifier(self.source, label="source")
        value_hash = _sha64(self.value_sha256, label="value_sha256", allow_zero=False)
        object.__setattr__(self, "requirement_id", requirement)
        object.__setattr__(self, "assertion", assertion)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "value_sha256", value_hash)
        object.__setattr__(self, "observation_sha256", canonical_sha256(self.canonical_body()))

    def canonical_body(self) -> dict[str, Any]:
        return {
            "requirementId": self.requirement_id,
            "assertion": self.assertion,
            "source": self.source,
            "valueSha256": self.value_sha256,
        }


@dataclass(frozen=True, slots=True)
class LlmResponseReceipt:
    verdict: str
    verification_scope: str
    request_sha256: str
    route_binding_sha256: str
    source_revision: str
    output_contract_sha256: str
    contract_output_sha256: str
    observation_sha256s: tuple[str, ...]
    satisfied_requirements: tuple[str, ...]
    missing_requirements: tuple[str, ...]
    contradicted_requirements: tuple[str, ...]
    finding_codes: tuple[str, ...]
    schema_version: str = LLM_RESPONSE_RECEIPT_SCHEMA
    receipt_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        verdict = str(self.verdict or "").strip().upper()
        if verdict not in {"VERIFIED", "CONTRADICTED", "BLOCKED_BY_MISSING_EVIDENCE"}:
            raise LlmContractError("unsupported LLM response verdict")
        scope = str(self.verification_scope or "").strip().upper()
        if scope not in {"SCHEMA_ONLY", "SCHEMA_AND_SEMANTICS"}:
            raise LlmContractError("unsupported LLM response verification scope")
        object.__setattr__(self, "verdict", verdict)
        object.__setattr__(self, "verification_scope", scope)
        object.__setattr__(self, "request_sha256", _sha64(self.request_sha256, label="request_sha256"))
        object.__setattr__(
            self,
            "route_binding_sha256",
            _sha64(self.route_binding_sha256, label="route_binding_sha256"),
        )
        object.__setattr__(self, "source_revision", _sha40(self.source_revision, label="source_revision"))
        object.__setattr__(
            self,
            "output_contract_sha256",
            _sha64(self.output_contract_sha256, label="output_contract_sha256"),
        )
        object.__setattr__(
            self,
            "contract_output_sha256",
            _sha64(self.contract_output_sha256, label="contract_output_sha256"),
        )
        object.__setattr__(
            self,
            "observation_sha256s",
            tuple(sorted({_sha64(item, label="observation_sha256") for item in self.observation_sha256s})),
        )
        for field_name in (
            "satisfied_requirements",
            "missing_requirements",
            "contradicted_requirements",
            "finding_codes",
        ):
            normalized = tuple(
                sorted({_identifier(item, label=field_name) for item in getattr(self, field_name)})
            )
            object.__setattr__(self, field_name, normalized)
        if self.schema_version != LLM_RESPONSE_RECEIPT_SCHEMA:
            raise LlmContractError("unsupported LLM response receipt schema version")
        if verdict == "VERIFIED" and (self.missing_requirements or self.contradicted_requirements):
            raise LlmContractError("VERIFIED receipt cannot contain missing or contradictory requirements")
        if verdict == "CONTRADICTED" and not self.contradicted_requirements:
            raise LlmContractError("CONTRADICTED receipt requires a contradiction")
        if verdict == "BLOCKED_BY_MISSING_EVIDENCE" and not self.missing_requirements:
            raise LlmContractError("blocked receipt requires missing requirements")
        object.__setattr__(self, "receipt_sha256", canonical_sha256(self.canonical_body()))

    def canonical_body(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "verificationScope": self.verification_scope,
            "requestSha256": self.request_sha256,
            "routeBindingSha256": self.route_binding_sha256,
            "sourceRevision": self.source_revision,
            "outputContractSha256": self.output_contract_sha256,
            "contractOutputSha256": self.contract_output_sha256,
            "observationSha256s": list(self.observation_sha256s),
            "satisfiedRequirements": list(self.satisfied_requirements),
            "missingRequirements": list(self.missing_requirements),
            "contradictedRequirements": list(self.contradicted_requirements),
            "findingCodes": list(self.finding_codes),
            "schemaVersion": self.schema_version,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_body(), "receiptSha256": self.receipt_sha256}


@dataclass(frozen=True, slots=True)
class LlmContractVerification:
    accepted: bool
    payload: Mapping[str, Any] | None
    receipt: LlmResponseReceipt


def verify_llm_response(
    *,
    envelope: LlmRequestEnvelope,
    contract: LlmOutputContract,
    response: Any,
    observations: Sequence[LlmSemanticObservation] = (),
) -> LlmContractVerification:
    if envelope.output_contract_sha256 != contract.contract_sha256:
        raise LlmContractError("request envelope is bound to a different output contract")

    findings: set[str] = set()
    parsed: Any = None
    schema_valid = False
    try:
        parsed = _response_payload(response)
        _validate_value(parsed, contract.json_schema)
        output_hash = canonical_sha256(parsed)
        schema_valid = True
        findings.add("schema_valid")
    except LlmContractError:
        output_hash = ZERO_SHA256
        findings.add("schema_invalid")

    observation_hashes = tuple(item.observation_sha256 for item in observations)
    satisfied: set[str] = set()
    missing: set[str] = set()
    contradicted: set[str] = set()
    required = set(contract.semantic_requirement_ids)

    if not schema_valid:
        contradicted.add("output_schema")
        verdict = "CONTRADICTED"
    else:
        by_requirement: dict[str, list[LlmSemanticObservation]] = {}
        for observation in observations:
            if observation.requirement_id not in required:
                findings.add("undeclared_semantic_observation")
                continue
            by_requirement.setdefault(observation.requirement_id, []).append(observation)
        for requirement_id in required:
            candidates = by_requirement.get(requirement_id, [])
            if not candidates:
                missing.add(requirement_id)
                findings.add("semantic_observation_missing")
                continue
            if any(item.assertion == "CONTRADICTED" for item in candidates):
                contradicted.add(requirement_id)
                findings.add("semantic_observation_contradicted")
            elif any(item.assertion == "OBSERVED" for item in candidates):
                satisfied.add(requirement_id)
            else:
                missing.add(requirement_id)
                findings.add("semantic_observation_unavailable")
        if contradicted:
            verdict = "CONTRADICTED"
        elif missing:
            verdict = "BLOCKED_BY_MISSING_EVIDENCE"
        else:
            verdict = "VERIFIED"

    scope = "SCHEMA_AND_SEMANTICS" if required else "SCHEMA_ONLY"
    receipt = LlmResponseReceipt(
        verdict=verdict,
        verification_scope=scope,
        request_sha256=envelope.request_sha256,
        route_binding_sha256=envelope.route_binding.binding_sha256,
        source_revision=envelope.route_binding.source_revision,
        output_contract_sha256=contract.contract_sha256,
        contract_output_sha256=output_hash,
        observation_sha256s=observation_hashes,
        satisfied_requirements=tuple(satisfied),
        missing_requirements=tuple(missing),
        contradicted_requirements=tuple(contradicted),
        finding_codes=tuple(findings),
    )
    payload = _freeze(parsed) if schema_valid and isinstance(parsed, Mapping) else None
    return LlmContractVerification(
        accepted=receipt.verdict == "VERIFIED",
        payload=payload,
        receipt=receipt,
    )


__all__ = [
    "LLM_OUTPUT_CONTRACT_SCHEMA",
    "LLM_REQUEST_ENVELOPE_SCHEMA",
    "LLM_RESPONSE_RECEIPT_SCHEMA",
    "LLM_ROUTE_BINDING_SCHEMA",
    "ROUTE_CLASS_FREELLM_FREE",
    "ROUTE_CLASS_OPENROUTER_PAID",
    "ZERO_SHA256",
    "LlmContractError",
    "LlmContractVerification",
    "LlmOutputContract",
    "LlmRequestEnvelope",
    "LlmResponseReceipt",
    "LlmRouteBinding",
    "LlmSemanticObservation",
    "build_request_envelope",
    "build_route_binding",
    "compile_contract_prompt",
    "verify_llm_response",
]
