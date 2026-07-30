"""Provider-neutral orchestration contracts for the Sovereign Agent Runtime.

This module is a clean-room, standard-library-only implementation of the
runtime concepts Sovereign Studio ATO needs: deterministic hooks and policies,
typed tool-registry snapshots, explicit-tick triggers, provenance-bound
multimodal inputs, stream hash chains and event-derived conversation views.

It deliberately does not own provider transport, background threads, clocks,
UUID generation, persistence or model reasoning. Callers supply all runtime
identities and timestamps explicitly; existing Sovereign adapters remain the
only effect boundary and evidence producer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from types import MappingProxyType
from typing import Any, Callable, Literal, Mapping, Sequence

from .contracts import sanitize_agent_text

ZERO_SHA256 = "0" * 64
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}$")
_MIME_RE = re.compile(r"^[a-z0-9][a-z0-9.+-]{0,63}/[a-z0-9][a-z0-9.+-]{0,127}$")

RuntimeEffect = Literal["read", "workspace-write", "external-write"]
PolicyDecisionValue = Literal["DENY", "ASK_OWNER", "ALLOW"]
HookDecisionValue = Literal["CONTINUE", "DENY", "ASK_OWNER"]
HookPhase = Literal[
    "BEFORE_RUN",
    "BEFORE_INPUT",
    "BEFORE_MODEL",
    "AFTER_MODEL",
    "BEFORE_TOOL",
    "AFTER_TOOL",
    "AFTER_RUN",
    "ON_ERROR",
]
InputPartKind = Literal["text", "image", "audio", "video", "document", "artifact"]
StreamEventKind = Literal[
    "run_started",
    "input_accepted",
    "model_started",
    "text_delta",
    "tool_call",
    "tool_result",
    "evidence",
    "approval_required",
    "run_completed",
    "run_failed",
]

_ALLOWED_INPUT_KINDS = {"text", "image", "audio", "video", "document", "artifact"}
_ALLOWED_STREAM_KINDS = {
    "run_started",
    "input_accepted",
    "model_started",
    "text_delta",
    "tool_call",
    "tool_result",
    "evidence",
    "approval_required",
    "run_completed",
    "run_failed",
}
_FORBIDDEN_STREAM_KINDS = {"thought", "thought_delta", "reasoning", "reasoning_delta", "chain_of_thought"}
_ALLOWED_HOOK_PHASES = {
    "BEFORE_RUN",
    "BEFORE_INPUT",
    "BEFORE_MODEL",
    "AFTER_MODEL",
    "BEFORE_TOOL",
    "AFTER_TOOL",
    "AFTER_RUN",
    "ON_ERROR",
}
_ALLOWED_POLICY_DECISIONS = {"DENY", "ASK_OWNER", "ALLOW"}
_ALLOWED_HOOK_DECISIONS = {"CONTINUE", "DENY", "ASK_OWNER"}


class ProviderNeutralRuntimeError(ValueError):
    """Raised when a provider-neutral runtime contract is invalid."""


def _bounded(value: Any, maximum: int) -> str:
    return sanitize_agent_text(str(value or ""), maximum)


def _bounded_stream_text(value: Any, maximum: int) -> str:
    """Sanitize a bounded text delta while preserving both edge markers."""
    start_marker = "\u0002"
    end_marker = "\u0003"
    raw = str(value or "")
    bounded_raw = raw[:maximum]
    wrapped = f"{start_marker}{bounded_raw}{end_marker}"
    sanitized = sanitize_agent_text(wrapped, maximum + 2)
    if sanitized.startswith(start_marker) and sanitized.endswith(end_marker):
        return sanitized[1:-1]
    raise ProviderNeutralRuntimeError("stream text sanitizer marker integrity failed")


def _validate_id(label: str, value: str, *, required: bool = True) -> str:
    text = str(value or "").strip()
    if not text and not required:
        return ""
    if not _ID_RE.fullmatch(text):
        raise ProviderNeutralRuntimeError(f"{label} must be a bounded canonical identifier")
    return text


def _canonicalize(value: Any) -> Any:
    """Return a JSON-safe, integer-only canonical representation."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        raise ProviderNeutralRuntimeError("floating-point values are forbidden in canonical runtime evidence")
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise ProviderNeutralRuntimeError("raw bytes are forbidden in canonical runtime evidence")
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value.keys()):
            raise ProviderNeutralRuntimeError("canonical mappings require string keys")
        return {key: _canonicalize(value[key]) for key in sorted(value.keys())}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _canonicalize(value.to_dict())
    raise ProviderNeutralRuntimeError(f"unsupported canonical value type: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(_canonicalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _is_exact_int(value: Any) -> bool:
    return type(value) is int


def _freeze_canonical(value: Any) -> Any:
    canonical = _canonicalize(value)
    if isinstance(canonical, dict):
        return MappingProxyType({key: _freeze_canonical(item) for key, item in canonical.items()})
    if isinstance(canonical, list):
        return tuple(_freeze_canonical(item) for item in canonical)
    return canonical


def _snapshot_mapping(label: str, value: Mapping[str, Any]) -> Mapping[str, Any]:
    frozen = _freeze_canonical(value)
    if not isinstance(frozen, Mapping):
        raise ProviderNeutralRuntimeError(f"{label} must be a canonical mapping")
    return frozen


def _validate_schema_value(value: Any, schema: Mapping[str, Any], *, path: str = "parameters") -> None:
    """Validate the bounded JSON-Schema subset emitted by registered tools."""
    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(value, Mapping):
            raise ProviderNeutralRuntimeError(f"{path} must be an object")
        properties = schema.get("properties") or {}
        if not isinstance(properties, Mapping):
            raise ProviderNeutralRuntimeError(f"{path} schema properties must be an object")
        required = schema.get("required") or ()
        if not isinstance(required, (list, tuple)):
            raise ProviderNeutralRuntimeError(f"{path} schema required must be an array")
        missing = [name for name in required if name not in value]
        if missing:
            raise ProviderNeutralRuntimeError(f"{path} is missing required properties: {', '.join(missing)}")
        if schema.get("additionalProperties") is False:
            extras = sorted(set(value) - set(properties))
            if extras:
                raise ProviderNeutralRuntimeError(f"{path} contains additional properties: {', '.join(extras)}")
        for name, item in value.items():
            child_schema = properties.get(name)
            if isinstance(child_schema, Mapping):
                _validate_schema_value(item, child_schema, path=f"{path}.{name}")
        return
    if expected_type == "string" and not isinstance(value, str):
        raise ProviderNeutralRuntimeError(f"{path} must be a string")
    if expected_type == "boolean" and type(value) is not bool:
        raise ProviderNeutralRuntimeError(f"{path} must be a boolean")
    if expected_type == "integer" and not _is_exact_int(value):
        raise ProviderNeutralRuntimeError(f"{path} must be an integer")
    if expected_type == "array":
        if not isinstance(value, (list, tuple)):
            raise ProviderNeutralRuntimeError(f"{path} must be an array")
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value):
                _validate_schema_value(item, item_schema, path=f"{path}[{index}]")
    if "enum" in schema and value not in schema["enum"]:
        raise ProviderNeutralRuntimeError(f"{path} is not an allowed enum value")


@dataclass(frozen=True)
class RuntimeContext:
    """All execution identity supplied by the caller; no hidden clock or UUID."""

    run_id: str
    owner_id: str
    revision: str
    tick: int
    epoch_ms: int
    call_id: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_id("run_id", self.run_id)
        _validate_id("owner_id", self.owner_id)
        _validate_id("call_id", self.call_id, required=False)
        if not _REVISION_RE.fullmatch(self.revision):
            raise ProviderNeutralRuntimeError("revision must be an exact lowercase 40-character commit SHA")
        if not _is_exact_int(self.tick) or self.tick < 0:
            raise ProviderNeutralRuntimeError("tick must be a non-negative integer")
        if not _is_exact_int(self.epoch_ms) or self.epoch_ms < 0:
            raise ProviderNeutralRuntimeError("epoch_ms must be a non-negative integer")
        object.__setattr__(self, "metadata", _snapshot_mapping("metadata", self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "ownerId": self.owner_id,
            "revision": self.revision,
            "tick": self.tick,
            "epochMs": self.epoch_ms,
            "callId": self.call_id,
            "metadata": _canonicalize(self.metadata),
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.to_dict())


@dataclass(frozen=True)
class RuntimeInputPart:
    """One text part or one immutable artifact reference.

    Binary payloads never enter this contract. Upload/storage adapters must first
    persist and hash an artifact, then pass only its bounded identity here.
    """

    kind: InputPartKind
    text: str = ""
    artifact_id: str = ""
    sha256: str = ""
    mime_type: str = ""
    size_bytes: int = 0
    source: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        if self.kind not in _ALLOWED_INPUT_KINDS:
            raise ProviderNeutralRuntimeError("unsupported input part kind")
        if self.kind == "text":
            if not self.text.strip():
                raise ProviderNeutralRuntimeError("text input requires non-empty text")
            if any((self.artifact_id, self.sha256, self.mime_type, self.size_bytes)):
                raise ProviderNeutralRuntimeError("text input may not carry artifact fields")
        else:
            _validate_id("artifact_id", self.artifact_id)
            if not _SHA256_RE.fullmatch(self.sha256):
                raise ProviderNeutralRuntimeError("artifact reference requires a lowercase SHA-256")
            if not _MIME_RE.fullmatch(self.mime_type):
                raise ProviderNeutralRuntimeError("artifact reference requires a canonical MIME type")
            if not _is_exact_int(self.size_bytes) or self.size_bytes <= 0:
                raise ProviderNeutralRuntimeError("artifact reference requires a positive integer size")
            if self.text:
                raise ProviderNeutralRuntimeError("artifact input may not embed raw text or bytes")
        if len(self.text.encode("utf-8")) > 1_000_000:
            raise ProviderNeutralRuntimeError("text input exceeds one megabyte")
        if len(self.description) > 1_000:
            raise ProviderNeutralRuntimeError("input description exceeds 1000 characters")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "text": _bounded(self.text, 1_000_000) if self.kind == "text" else "",
            "artifactId": self.artifact_id,
            "sha256": self.sha256,
            "mimeType": self.mime_type,
            "sizeBytes": self.size_bytes,
            "source": _bounded(self.source, 500),
            "description": _bounded(self.description, 1_000),
        }

    def _binding_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "text": self.text if self.kind == "text" else "",
            "artifactId": self.artifact_id,
            "sha256": self.sha256,
            "mimeType": self.mime_type,
            "sizeBytes": self.size_bytes,
            "source": self.source,
            "description": self.description,
        }


@dataclass(frozen=True)
class RuntimeInputEnvelope:
    parts: tuple[RuntimeInputPart, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.parts:
            raise ProviderNeutralRuntimeError("runtime input requires at least one part")
        if len(self.parts) > 64:
            raise ProviderNeutralRuntimeError("runtime input exceeds 64 parts")
        object.__setattr__(self, "parts", tuple(self.parts))
        object.__setattr__(self, "metadata", _snapshot_mapping("metadata", self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "parts": [part.to_dict() for part in self.parts],
            "metadata": _canonicalize(self.metadata),
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256({
            "parts": [part._binding_dict() for part in self.parts],
            "metadata": _canonicalize(self.metadata),
        })


@dataclass(frozen=True)
class ToolDescriptor:
    name: str
    description: str
    input_schema: Mapping[str, Any]
    effect: RuntimeEffect = "read"
    capabilities: tuple[str, ...] = ()
    transport: str = "local"
    provider: str = "sovereign"

    def __post_init__(self) -> None:
        _validate_id("tool name", self.name)
        if self.effect not in {"read", "workspace-write", "external-write"}:
            raise ProviderNeutralRuntimeError("unsupported tool effect")
        normalized_capabilities = tuple(sorted(set(self.capabilities)))
        for capability in normalized_capabilities:
            _validate_id("capability", capability)
        object.__setattr__(self, "capabilities", normalized_capabilities)
        object.__setattr__(self, "input_schema", _snapshot_mapping("input_schema", self.input_schema))
        _validate_id("transport", self.transport)
        _validate_id("provider", self.provider)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": _bounded(self.description, 2_000),
            "inputSchema": _canonicalize(self.input_schema),
            "effect": self.effect,
            "capabilities": sorted(set(self.capabilities)),
            "transport": self.transport,
            "provider": self.provider,
        }

    @property
    def contract_sha256(self) -> str:
        return canonical_sha256(self.to_dict())


def tool_registry_snapshot(tools: Sequence[ToolDescriptor]) -> dict[str, Any]:
    normalized = sorted((tool.to_dict() for tool in tools), key=lambda item: item["name"])
    names = [item["name"] for item in normalized]
    if len(names) != len(set(names)):
        raise ProviderNeutralRuntimeError("tool registry contains duplicate names")
    return {
        "schemaVersion": "sovereign.provider-neutral-tool-registry.v1",
        "toolCount": len(normalized),
        "toolNamesSha256": canonical_sha256(names),
        "registrySha256": canonical_sha256(normalized),
        "tools": normalized,
    }


@dataclass(frozen=True)
class PolicyRule:
    rule_id: str
    decision: PolicyDecisionValue
    reason: str
    priority: int = 0
    tool_name: str = ""
    tool_prefix: str = ""
    effect: RuntimeEffect | str = ""
    capability: str = ""

    def __post_init__(self) -> None:
        _validate_id("rule_id", self.rule_id)
        if self.decision not in _ALLOWED_POLICY_DECISIONS:
            raise ProviderNeutralRuntimeError("unsupported policy decision")
        if not isinstance(self.priority, int):
            raise ProviderNeutralRuntimeError("policy priority must be an integer")
        selectors = [bool(self.tool_name), bool(self.tool_prefix), bool(self.effect), bool(self.capability)]
        if sum(selectors) > 1:
            raise ProviderNeutralRuntimeError("policy rule may use at most one selector")
        if self.tool_name:
            _validate_id("tool_name", self.tool_name)
        if self.tool_prefix:
            _validate_id("tool_prefix", self.tool_prefix)
        if self.effect and self.effect not in {"read", "workspace-write", "external-write"}:
            raise ProviderNeutralRuntimeError("unsupported policy effect")
        if self.capability:
            _validate_id("capability", self.capability)

    def selector_rank(self) -> int:
        if self.tool_name:
            return 0
        if self.tool_prefix:
            return 1
        if self.effect:
            return 2
        if self.capability:
            return 3
        return 4

    def matches(self, tool: ToolDescriptor) -> bool:
        if self.tool_name:
            return tool.name == self.tool_name
        if self.tool_prefix:
            return tool.name.startswith(self.tool_prefix)
        if self.effect:
            return tool.effect == self.effect
        if self.capability:
            return self.capability in tool.capabilities
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "ruleId": self.rule_id,
            "decision": self.decision,
            "reason": _bounded(self.reason, 1_000),
            "priority": self.priority,
            "toolName": self.tool_name,
            "toolPrefix": self.tool_prefix,
            "effect": self.effect,
            "capability": self.capability,
        }


@dataclass(frozen=True)
class PolicyEvaluation:
    decision: PolicyDecisionValue
    reason: str
    rule_id: str
    evidence_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "ruleId": self.rule_id,
            "evidenceSha256": self.evidence_sha256,
        }


def evaluate_tool_policy(rules: Sequence[PolicyRule], tool: ToolDescriptor) -> PolicyEvaluation:
    decision_rank = {"DENY": 0, "ASK_OWNER": 1, "ALLOW": 2}
    ordered = sorted(
        rules,
        key=lambda rule: (
            rule.selector_rank(),
            decision_rank[rule.decision],
            -rule.priority,
            rule.rule_id,
        ),
    )
    selected = next((rule for rule in ordered if rule.matches(tool)), None)
    if selected is None:
        payload = {
            "decision": "DENY",
            "reason": "No matching allow rule; provider-neutral policy defaults to deny.",
            "ruleId": "default-deny",
            "tool": tool.to_dict(),
        }
        return PolicyEvaluation("DENY", payload["reason"], "default-deny", canonical_sha256(payload))
    payload = {"rule": selected.to_dict(), "tool": tool.to_dict()}
    return PolicyEvaluation(
        selected.decision,
        _bounded(selected.reason, 1_000) or f"Policy {selected.rule_id} returned {selected.decision}.",
        selected.rule_id,
        canonical_sha256(payload),
    )


@dataclass(frozen=True)
class HookDecision:
    decision: HookDecisionValue = "CONTINUE"
    reason: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.decision not in _ALLOWED_HOOK_DECISIONS:
            raise ProviderNeutralRuntimeError("unsupported hook decision")
        object.__setattr__(self, "metadata", _snapshot_mapping("metadata", self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reason": _bounded(self.reason, 1_000),
            "metadata": _canonicalize(self.metadata),
        }


HookCallback = Callable[[RuntimeContext, Mapping[str, Any]], HookDecision | None]


@dataclass(frozen=True)
class HookRegistration:
    hook_id: str
    phase: HookPhase
    callback: HookCallback
    priority: int = 0
    sequence: int = 0

    def __post_init__(self) -> None:
        _validate_id("hook_id", self.hook_id)
        if self.phase not in _ALLOWED_HOOK_PHASES:
            raise ProviderNeutralRuntimeError("unsupported hook phase")
        if not callable(self.callback):
            raise ProviderNeutralRuntimeError("hook callback must be callable")
        if not isinstance(self.priority, int) or not isinstance(self.sequence, int):
            raise ProviderNeutralRuntimeError("hook priority and sequence must be integers")


@dataclass(frozen=True)
class HookReceipt:
    hook_id: str
    phase: HookPhase
    sequence: int
    decision: HookDecisionValue
    reason: str
    context_sha256: str
    input_sha256: str
    output_sha256: str
    receipt_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "hookId": self.hook_id,
            "phase": self.phase,
            "sequence": self.sequence,
            "decision": self.decision,
            "reason": self.reason,
            "contextSha256": self.context_sha256,
            "inputSha256": self.input_sha256,
            "outputSha256": self.output_sha256,
            "receiptSha256": self.receipt_sha256,
        }


@dataclass(frozen=True)
class HookEvaluation:
    decision: HookDecisionValue
    reason: str
    receipts: tuple[HookReceipt, ...]

    @property
    def allowed(self) -> bool:
        return self.decision == "CONTINUE"


class HookPipeline:
    """Deterministically ordered hooks with fail-closed exception handling."""

    def __init__(self, registrations: Sequence[HookRegistration] = ()) -> None:
        self._registrations: list[HookRegistration] = []
        for registration in registrations:
            self.register(
                registration.hook_id,
                registration.phase,
                registration.callback,
                priority=registration.priority,
            )

    def register(self, hook_id: str, phase: HookPhase, callback: HookCallback, *, priority: int = 0) -> None:
        if any(item.hook_id == hook_id for item in self._registrations):
            raise ProviderNeutralRuntimeError(f"duplicate hook id: {hook_id}")
        self._registrations.append(
            HookRegistration(
                hook_id=hook_id,
                phase=phase,
                callback=callback,
                priority=priority,
                sequence=len(self._registrations),
            )
        )

    def registry_snapshot(self) -> dict[str, Any]:
        hooks = [
            {
                "hookId": item.hook_id,
                "phase": item.phase,
                "priority": item.priority,
                "sequence": item.sequence,
            }
            for item in sorted(self._registrations, key=lambda item: item.sequence)
        ]
        return {
            "schemaVersion": "sovereign.provider-neutral-hook-registry.v1",
            "hookCount": len(hooks),
            "registrySha256": canonical_sha256(hooks),
            "hooks": hooks,
        }

    def run(
        self,
        phase: HookPhase,
        context: RuntimeContext,
        payload: Mapping[str, Any],
    ) -> HookEvaluation:
        if phase not in _ALLOWED_HOOK_PHASES:
            raise ProviderNeutralRuntimeError("unsupported hook phase")
        safe_payload = _snapshot_mapping("hook payload", payload)
        input_sha256 = canonical_sha256(safe_payload)
        receipts: list[HookReceipt] = []
        ordered = sorted(
            (item for item in self._registrations if item.phase == phase),
            key=lambda item: (-item.priority, item.sequence, item.hook_id),
        )
        for item in ordered:
            try:
                raw = item.callback(context, safe_payload)
                decision = raw if raw is not None else HookDecision()
                if not isinstance(decision, HookDecision):
                    raise ProviderNeutralRuntimeError("hook returned an unsupported result")
            except Exception as exc:
                decision = HookDecision(
                    decision="DENY",
                    reason=f"Hook {item.hook_id} failed closed: {_bounded(exc, 400)}",
                    metadata={"failureFamily": "HOOK_CALLBACK_FAILED"},
                )
            output = decision.to_dict()
            base = {
                "hookId": item.hook_id,
                "phase": phase,
                "sequence": item.sequence,
                "decision": decision.decision,
                "reason": _bounded(decision.reason, 1_000),
                "contextSha256": context.sha256,
                "inputSha256": input_sha256,
                "outputSha256": canonical_sha256(output),
            }
            receipt = HookReceipt(
                hook_id=item.hook_id,
                phase=phase,
                sequence=item.sequence,
                decision=decision.decision,
                reason=base["reason"],
                context_sha256=context.sha256,
                input_sha256=input_sha256,
                output_sha256=base["outputSha256"],
                receipt_sha256=canonical_sha256(base),
            )
            receipts.append(receipt)
            if decision.decision != "CONTINUE":
                return HookEvaluation(decision.decision, receipt.reason, tuple(receipts))
        return HookEvaluation("CONTINUE", "All registered hooks continued.", tuple(receipts))


@dataclass(frozen=True)
class RuntimeStreamEvent:
    sequence: int
    kind: StreamEventKind
    run_id: str
    call_id: str
    tick: int
    epoch_ms: int
    payload: Mapping[str, Any]
    previous_sha256: str
    event_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "kind": self.kind,
            "runId": self.run_id,
            "callId": self.call_id,
            "tick": self.tick,
            "epochMs": self.epoch_ms,
            "payload": _canonicalize(self.payload),
            "previousSha256": self.previous_sha256,
            "eventSha256": self.event_sha256,
        }


def build_stream_event(
    *,
    sequence: int,
    kind: str,
    context: RuntimeContext,
    payload: Mapping[str, Any],
    previous_sha256: str = ZERO_SHA256,
) -> RuntimeStreamEvent:
    normalized_kind = str(kind).strip().lower()
    if normalized_kind in _FORBIDDEN_STREAM_KINDS:
        raise ProviderNeutralRuntimeError("model reasoning or chain-of-thought may not enter the stream contract")
    if normalized_kind not in _ALLOWED_STREAM_KINDS:
        raise ProviderNeutralRuntimeError("unsupported stream event kind")
    if not _is_exact_int(sequence) or sequence < 0:
        raise ProviderNeutralRuntimeError("stream sequence must be a non-negative integer")
    if not _SHA256_RE.fullmatch(previous_sha256):
        raise ProviderNeutralRuntimeError("previous stream hash must be SHA-256")
    safe_payload = _snapshot_mapping("stream payload", payload)
    base = {
        "sequence": sequence,
        "kind": normalized_kind,
        "runId": context.run_id,
        "callId": context.call_id,
        "tick": context.tick,
        "epochMs": context.epoch_ms,
        "payload": safe_payload,
        "previousSha256": previous_sha256,
    }
    return RuntimeStreamEvent(
        sequence=sequence,
        kind=normalized_kind,  # type: ignore[arg-type]
        run_id=context.run_id,
        call_id=context.call_id,
        tick=context.tick,
        epoch_ms=context.epoch_ms,
        payload=safe_payload,
        previous_sha256=previous_sha256,
        event_sha256=canonical_sha256(base),
    )


def validate_stream_chain(events: Sequence[RuntimeStreamEvent]) -> bool:
    if not events or events[0].kind != "run_started":
        return False
    previous = ZERO_SHA256
    terminal_seen = False
    prior_kind = ""
    for expected_sequence, event in enumerate(events):
        if terminal_seen:
            return False
        if event.kind == "run_started" and expected_sequence != 0:
            return False
        if event.kind == "input_accepted" and prior_kind != "run_started":
            return False
        if event.kind in {"model_started", "text_delta", "tool_call"} and prior_kind not in {
            "input_accepted", "model_started", "text_delta", "tool_result", "evidence"
        }:
            return False
        if event.kind == "tool_result" and prior_kind != "tool_call":
            return False
        if event.kind in {"run_completed", "run_failed"} and prior_kind not in {
            "input_accepted", "model_started", "text_delta", "tool_result", "evidence", "approval_required"
        }:
            return False
        rebuilt = build_stream_event(
            sequence=event.sequence,
            kind=event.kind,
            context=RuntimeContext(
                run_id=event.run_id,
                owner_id="stream-validator",
                revision="0" * 40,
                tick=event.tick,
                epoch_ms=event.epoch_ms,
                call_id=event.call_id,
            ),
            payload=event.payload,
            previous_sha256=event.previous_sha256,
        )
        # owner and revision intentionally do not enter stream event identity.
        if event.sequence != expected_sequence or event.previous_sha256 != previous or rebuilt.event_sha256 != event.event_sha256:
            return False
        previous = event.event_sha256
        if event.kind in {"run_completed", "run_failed"}:
            terminal_seen = True
        prior_kind = event.kind
    return True


@dataclass(frozen=True)
class DeterministicTrigger:
    trigger_id: str
    interval_ticks: int
    offset_tick: int = 0
    enabled: bool = True
    max_fires: int = 0

    def __post_init__(self) -> None:
        _validate_id("trigger_id", self.trigger_id)
        if not _is_exact_int(self.interval_ticks) or self.interval_ticks <= 0:
            raise ProviderNeutralRuntimeError("interval_ticks must be a positive integer")
        if not _is_exact_int(self.offset_tick) or self.offset_tick < 0:
            raise ProviderNeutralRuntimeError("offset_tick must be a non-negative integer")
        if type(self.enabled) is not bool:
            raise ProviderNeutralRuntimeError("enabled must be a boolean")
        if not _is_exact_int(self.max_fires) or self.max_fires < 0:
            raise ProviderNeutralRuntimeError("max_fires must be a non-negative integer")

    def due(self, *, tick: int, fired_count: int = 0) -> bool:
        if not self.enabled:
            return False
        if not _is_exact_int(tick) or tick < 0 or not _is_exact_int(fired_count) or fired_count < 0:
            raise ProviderNeutralRuntimeError("trigger tick and fired_count must be non-negative integers")
        if self.max_fires and fired_count >= self.max_fires:
            return False
        return tick >= self.offset_tick and (tick - self.offset_tick) % self.interval_ticks == 0

    def receipt(self, *, tick: int, fired_count: int = 0) -> dict[str, Any]:
        payload = {
            "triggerId": self.trigger_id,
            "intervalTicks": self.interval_ticks,
            "offsetTick": self.offset_tick,
            "enabled": self.enabled,
            "maxFires": self.max_fires,
            "tick": tick,
            "firedCount": fired_count,
            "due": self.due(tick=tick, fired_count=fired_count),
        }
        return {**payload, "receiptSha256": canonical_sha256(payload)}


@dataclass(frozen=True)
class ToolAuthorization:
    decision: PolicyDecisionValue
    reason: str
    policy: PolicyEvaluation
    hook_receipts: tuple[HookReceipt, ...]
    input_sha256: str
    evidence_sha256: str

    @property
    def allowed(self) -> bool:
        return self.decision == "ALLOW"

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "policy": self.policy.to_dict(),
            "hookReceipts": [item.to_dict() for item in self.hook_receipts],
            "inputSha256": self.input_sha256,
            "evidenceSha256": self.evidence_sha256,
        }


@dataclass(frozen=True)
class ProviderNeutralToolExecution:
    status: Literal["done", "blocked", "approval-required", "error"]
    authorization: ToolAuthorization
    result: Mapping[str, Any]
    events: tuple[RuntimeStreamEvent, ...]
    hook_receipts: tuple[HookReceipt, ...]
    evidence_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "result", _snapshot_mapping("tool result", self.result))
        object.__setattr__(self, "events", tuple(self.events))
        object.__setattr__(self, "hook_receipts", tuple(self.hook_receipts))

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "authorization": self.authorization.to_dict(),
            "result": _canonicalize(self.result),
            "events": [event.to_dict() for event in self.events],
            "hookReceipts": [item.to_dict() for item in self.hook_receipts],
            "evidenceSha256": self.evidence_sha256,
        }


@dataclass(frozen=True)
class ConversationProjection:
    run_id: str
    event_count: int
    terminal_status: str
    last_event_sha256: str
    text: str
    tool_calls: tuple[str, ...]
    evidence_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "eventCount": self.event_count,
            "terminalStatus": self.terminal_status,
            "lastEventSha256": self.last_event_sha256,
            "text": self.text,
            "toolCalls": list(self.tool_calls),
            "evidenceSha256": self.evidence_sha256,
        }


def project_conversation(events: Sequence[RuntimeStreamEvent]) -> ConversationProjection:
    if not events:
        raise ProviderNeutralRuntimeError("conversation projection requires events")
    if not validate_stream_chain(events):
        raise ProviderNeutralRuntimeError("conversation event hash chain is invalid")
    run_ids = {event.run_id for event in events}
    if len(run_ids) != 1:
        raise ProviderNeutralRuntimeError("conversation projection may cover only one run")
    text = "".join(
        str(event.payload.get("text") or "")
        for event in events
        if event.kind == "text_delta"
    )
    tool_calls = tuple(
        str(event.payload.get("tool") or "")
        for event in events
        if event.kind == "tool_call" and event.payload.get("tool")
    )
    terminal = "open"
    if events[-1].kind == "run_completed":
        terminal = "completed"
    elif events[-1].kind == "run_failed":
        terminal = "failed"
    payload = {
        "runId": events[0].run_id,
        "eventCount": len(events),
        "terminalStatus": terminal,
        "lastEventSha256": events[-1].event_sha256,
        "text": _bounded(text, 1_000_000),
        "toolCalls": list(tool_calls),
    }
    return ConversationProjection(
        run_id=events[0].run_id,
        event_count=len(events),
        terminal_status=terminal,
        last_event_sha256=events[-1].event_sha256,
        text=payload["text"],
        tool_calls=tool_calls,
        evidence_sha256=canonical_sha256(payload),
    )


def _tool_result_mapping(result: Any) -> Mapping[str, Any]:
    if hasattr(result, "to_dict") and callable(result.to_dict):
        raw = result.to_dict()
    elif isinstance(result, Mapping):
        raw = dict(result)
    else:
        raw = {"status": "error", "error": "Unsupported tool result shape"}
    return _canonicalize(raw)


@dataclass(frozen=True)
class RuntimePreparation:
    status: Literal["ready", "blocked", "approval-required"]
    context_sha256: str
    input_sha256: str
    registry_snapshot: Mapping[str, Any]
    hook_receipts: tuple[HookReceipt, ...]
    events: tuple[RuntimeStreamEvent, ...]
    reason: str
    evidence_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "contextSha256": self.context_sha256,
            "inputSha256": self.input_sha256,
            "registrySnapshot": _canonicalize(self.registry_snapshot),
            "hookReceipts": [item.to_dict() for item in self.hook_receipts],
            "events": [event.to_dict() for event in self.events],
            "reason": self.reason,
            "evidenceSha256": self.evidence_sha256,
        }


def append_stream_event(
    events: Sequence[RuntimeStreamEvent],
    *,
    kind: str,
    context: RuntimeContext,
    payload: Mapping[str, Any],
) -> tuple[RuntimeStreamEvent, ...]:
    if events and not validate_stream_chain(events):
        raise ProviderNeutralRuntimeError("previous stream events have an invalid hash chain")
    if events and events[-1].kind in {"run_completed", "run_failed"}:
        raise ProviderNeutralRuntimeError("terminal run streams may not accept additional events")
    previous = events[-1].event_sha256 if events else ZERO_SHA256
    event = build_stream_event(
        sequence=len(events),
        kind=kind,
        context=context,
        payload=payload,
        previous_sha256=previous,
    )
    return tuple(events) + (event,)


def build_text_delta_stream(
    *,
    context: RuntimeContext,
    chunks: Sequence[str],
    previous_events: Sequence[RuntimeStreamEvent] = (),
) -> tuple[RuntimeStreamEvent, ...]:
    events = tuple(previous_events)
    if events and not validate_stream_chain(events):
        raise ProviderNeutralRuntimeError("previous stream events have an invalid hash chain")
    for chunk in chunks:
        text = _bounded_stream_text(chunk, 100_000)
        if not text:
            continue
        events = append_stream_event(events, kind="text_delta", context=context, payload={"text": text})
    return events


class ProviderNeutralRuntimeKernel:
    """Pure orchestration around existing Sovereign effect adapters."""

    def __init__(
        self,
        *,
        policy_rules: Sequence[PolicyRule] = (),
        hooks: HookPipeline | None = None,
    ) -> None:
        self.policy_rules = tuple(policy_rules)
        self.hooks = hooks or HookPipeline()

    def prepare_run(
        self,
        *,
        context: RuntimeContext,
        envelope: RuntimeInputEnvelope,
        tools: Sequence[ToolDescriptor],
    ) -> RuntimePreparation:
        registry = tool_registry_snapshot(tools)
        events: tuple[RuntimeStreamEvent, ...] = ()
        events = append_stream_event(
            events,
            kind="run_started",
            context=context,
            payload={
                "contextSha256": context.sha256,
                "ownerId": context.owner_id,
                "revision": context.revision,
                "inputSha256": envelope.sha256,
                "registrySha256": registry["registrySha256"],
            },
        )
        before_run = self.hooks.run(
            "BEFORE_RUN",
            context,
            {
                "inputSha256": envelope.sha256,
                "registrySha256": registry["registrySha256"],
                "toolCount": registry["toolCount"],
            },
        )
        receipts = before_run.receipts
        decision = before_run.decision
        reason = before_run.reason
        if decision == "CONTINUE":
            before_input = self.hooks.run(
                "BEFORE_INPUT",
                context,
                {"input": envelope.to_dict(), "inputSha256": envelope.sha256},
            )
            receipts += before_input.receipts
            decision = before_input.decision
            reason = before_input.reason
        if decision == "CONTINUE":
            status: Literal["ready", "blocked", "approval-required"] = "ready"
            reason = "Provider-neutral runtime input accepted."
            events = append_stream_event(
                events,
                kind="input_accepted",
                context=context,
                payload={"inputSha256": envelope.sha256, "partCount": len(envelope.parts)},
            )
        elif decision == "ASK_OWNER":
            status = "approval-required"
            events = append_stream_event(
                events,
                kind="approval_required",
                context=context,
                payload={"phase": "run-preparation", "reason": reason},
            )
        else:
            status = "blocked"
            events = append_stream_event(
                events,
                kind="run_failed",
                context=context,
                payload={"failureFamily": "RUNTIME_PREPARATION_BLOCKED", "reason": reason},
            )
        payload = {
            "status": status,
            "contextSha256": context.sha256,
            "inputSha256": envelope.sha256,
            "registrySnapshot": registry,
            "hookReceipts": [item.to_dict() for item in receipts],
            "events": [event.to_dict() for event in events],
            "reason": reason,
        }
        return RuntimePreparation(
            status=status,
            context_sha256=context.sha256,
            input_sha256=envelope.sha256,
            registry_snapshot=registry,
            hook_receipts=receipts,
            events=events,
            reason=_bounded(reason, 1_000),
            evidence_sha256=canonical_sha256(payload),
        )

    def authorize_tool(
        self,
        *,
        context: RuntimeContext,
        tool: ToolDescriptor,
        parameters: Mapping[str, Any],
    ) -> ToolAuthorization:
        if not context.call_id:
            raise ProviderNeutralRuntimeError("tool authorization requires an explicit call_id")
        safe_parameters = _canonicalize(parameters)
        input_sha256 = canonical_sha256(
            {"context": context.to_dict(), "tool": tool.to_dict(), "parameters": safe_parameters}
        )
        policy = evaluate_tool_policy(self.policy_rules, tool)
        hook_receipts: tuple[HookReceipt, ...] = ()
        decision = policy.decision
        reason = policy.reason
        if decision == "ALLOW":
            hooks = self.hooks.run(
                "BEFORE_TOOL",
                context,
                {"tool": tool.to_dict(), "parameters": safe_parameters, "policy": policy.to_dict()},
            )
            hook_receipts = hooks.receipts
            if hooks.decision == "DENY":
                decision = "DENY"
                reason = hooks.reason
            elif hooks.decision == "ASK_OWNER":
                decision = "ASK_OWNER"
                reason = hooks.reason
        payload = {
            "decision": decision,
            "reason": reason,
            "policy": policy.to_dict(),
            "hookReceipts": [item.to_dict() for item in hook_receipts],
            "inputSha256": input_sha256,
        }
        return ToolAuthorization(
            decision=decision,
            reason=_bounded(reason, 1_000),
            policy=policy,
            hook_receipts=hook_receipts,
            input_sha256=input_sha256,
            evidence_sha256=canonical_sha256(payload),
        )

    def execute_registered_tool(
        self,
        *,
        context: RuntimeContext,
        tool: ToolDescriptor,
        parameters: Mapping[str, Any],
        registry: Any,
        workspace_path: str | None = None,
        previous_events: Sequence[RuntimeStreamEvent] = (),
    ) -> ProviderNeutralToolExecution:
        registered_tool = descriptor_from_registry(registry, tool.name)
        if (
            tool.effect != registered_tool.effect
            or tuple(sorted(set(tool.capabilities))) != registered_tool.capabilities
        ):
            raise ProviderNeutralRuntimeError(
                "supplied tool authorization metadata does not match the registry-owned contract"
            )
        tool = registered_tool
        parameter_snapshot = _snapshot_mapping("tool parameters", parameters)
        _validate_schema_value(parameter_snapshot, tool.input_schema)
        authorization = self.authorize_tool(context=context, tool=tool, parameters=parameter_snapshot)
        events = list(previous_events)
        if events and not validate_stream_chain(events):
            raise ProviderNeutralRuntimeError("previous stream events have an invalid hash chain")
        if any(event.run_id != context.run_id for event in events):
            raise ProviderNeutralRuntimeError("previous stream events belong to a different run")
        if events:
            start_payload = events[0].payload
            if start_payload.get("ownerId") != context.owner_id or start_payload.get("revision") != context.revision:
                raise ProviderNeutralRuntimeError("previous stream events belong to a different owner or revision")
        if events and events[-1].kind in {"run_completed", "run_failed"}:
            raise ProviderNeutralRuntimeError("terminal run streams may not execute additional tools")
        previous = events[-1].event_sha256 if events else ZERO_SHA256

        def append(kind: str, payload: Mapping[str, Any]) -> None:
            nonlocal previous
            event = build_stream_event(
                sequence=len(events),
                kind=kind,
                context=context,
                payload=payload,
                previous_sha256=previous,
            )
            events.append(event)
            previous = event.event_sha256

        if not events:
            append(
                "run_started",
                {
                    "contextSha256": context.sha256,
                    "ownerId": context.owner_id,
                    "revision": context.revision,
                    "inputSha256": canonical_sha256(parameter_snapshot),
                    "registrySha256": canonical_sha256(tool.to_dict()),
                },
            )
            append(
                "input_accepted",
                {"inputSha256": canonical_sha256(parameter_snapshot), "partCount": 1},
            )

        if authorization.decision == "DENY":
            append("evidence", {"decision": "DENY", "reason": authorization.reason})
            result = {"status": "blocked", "blocker": authorization.reason, "tool": tool.name}
            payload = {
                "status": "blocked",
                "authorization": authorization.to_dict(),
                "result": result,
                "events": [event.to_dict() for event in events],
            }
            return ProviderNeutralToolExecution(
                status="blocked",
                authorization=authorization,
                result=result,
                events=tuple(events),
                hook_receipts=authorization.hook_receipts,
                evidence_sha256=canonical_sha256(payload),
            )
        if authorization.decision == "ASK_OWNER":
            append("approval_required", {"tool": tool.name, "reason": authorization.reason})
            result = {"status": "approval-required", "reason": authorization.reason, "tool": tool.name}
            payload = {
                "status": "approval-required",
                "authorization": authorization.to_dict(),
                "result": result,
                "events": [event.to_dict() for event in events],
            }
            return ProviderNeutralToolExecution(
                status="approval-required",
                authorization=authorization,
                result=result,
                events=tuple(events),
                hook_receipts=authorization.hook_receipts,
                evidence_sha256=canonical_sha256(payload),
            )

        append(
            "tool_call",
            {
                "tool": tool.name,
                "effect": tool.effect,
                "contractSha256": tool.contract_sha256,
                "parametersSha256": canonical_sha256(parameter_snapshot),
            },
        )
        try:
            raw_result = registry.execute_tool(
                tool_name=tool.name,
                params=dict(parameter_snapshot),
                workspace_path=workspace_path,
            )
            result = _tool_result_mapping(raw_result)
            status_text = str(result.get("status") or "")
            status: Literal["done", "blocked", "approval-required", "error"]
            status = "done" if status_text == "done" else "blocked" if status_text == "blocked" else "error"
        except Exception as exc:
            result = {
                "status": "error",
                "tool": tool.name,
                "error": _bounded(exc, 1_000),
                "failureFamily": "TOOL_EXECUTION_EXCEPTION",
            }
            status = "error"

        append(
            "tool_result",
            {
                "tool": tool.name,
                "status": status,
                "resultSha256": canonical_sha256(result),
            },
        )
        after_hooks = self.hooks.run(
            "AFTER_TOOL" if status != "error" else "ON_ERROR",
            context,
            {"tool": tool.to_dict(), "result": result, "status": status},
        )
        if after_hooks.decision != "CONTINUE":
            result = {
                **dict(result),
                "postHookDecision": after_hooks.decision,
                "postHookReason": after_hooks.reason,
                "effectAlreadyExecuted": True,
                "postExecutionApprovalSupported": False,
            }
            append(
                "evidence",
                {
                    "tool": tool.name,
                    "decision": after_hooks.decision,
                    "reason": after_hooks.reason,
                    "effectAlreadyExecuted": True,
                },
            )
        all_receipts = authorization.hook_receipts + after_hooks.receipts
        payload = {
            "status": status,
            "authorization": authorization.to_dict(),
            "result": result,
            "events": [event.to_dict() for event in events],
            "hookReceipts": [item.to_dict() for item in all_receipts],
        }
        return ProviderNeutralToolExecution(
            status=status,
            authorization=authorization,
            result=result,
            events=tuple(events),
            hook_receipts=all_receipts,
            evidence_sha256=canonical_sha256(payload),
        )


def descriptor_from_registry(
    registry: Any,
    tool_name: str,
    *,
    effect: RuntimeEffect | None = None,
    capabilities: Sequence[str] | None = None,
    transport: str = "local",
) -> ToolDescriptor:
    tool = registry.get(tool_name)
    if tool is None:
        raise ProviderNeutralRuntimeError(f"unknown registered tool: {tool_name}")
    contract_reader = getattr(registry, "get_contract_metadata", None)
    if not callable(contract_reader):
        raise ProviderNeutralRuntimeError("tool registry does not expose owned contract metadata")
    contract = contract_reader(tool_name)
    if not isinstance(contract, Mapping):
        raise ProviderNeutralRuntimeError("registered tool contract metadata is unavailable")
    registered_effect = str(contract.get("effect") or "")
    registered_capabilities = tuple(sorted(set(contract.get("capabilities") or ())))
    if registered_effect not in {"read", "workspace-write", "external-write"}:
        raise ProviderNeutralRuntimeError("registered tool effect is invalid")
    if effect is not None and effect != registered_effect:
        raise ProviderNeutralRuntimeError("caller effect does not match the registered tool contract")
    if capabilities is not None and tuple(sorted(set(capabilities))) != registered_capabilities:
        raise ProviderNeutralRuntimeError("caller capabilities do not match the registered tool contract")

    raw_parameters = getattr(tool, "parameters", {}) or {}
    if not isinstance(raw_parameters, Mapping):
        raise ProviderNeutralRuntimeError("registered tool parameters must be a mapping")
    properties: dict[str, Any] = {}
    required: list[str] = []
    for parameter_name in sorted(raw_parameters):
        raw_spec = raw_parameters[parameter_name]
        if not isinstance(parameter_name, str) or not isinstance(raw_spec, Mapping):
            raise ProviderNeutralRuntimeError("registered tool parameter schemas are invalid")
        spec = dict(_canonicalize(raw_spec))
        if spec.pop("required", False) is True:
            required.append(parameter_name)
        properties[parameter_name] = spec
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return ToolDescriptor(
        name=tool_name,
        description=str(getattr(tool, "description", "") or ""),
        input_schema=schema,
        effect=registered_effect,  # type: ignore[arg-type]
        capabilities=registered_capabilities,
        transport=transport,
        provider="sovereign",
    )
