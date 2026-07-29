"""Contract tests for the provider-neutral Sovereign agent runtime."""

from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.provider_neutral_runtime import (
    ZERO_SHA256,
    DeterministicTrigger,
    HookDecision,
    HookPipeline,
    PolicyRule,
    ProviderNeutralRuntimeError,
    ProviderNeutralRuntimeKernel,
    RuntimeContext,
    RuntimeInputEnvelope,
    RuntimeInputPart,
    ToolDescriptor,
    append_stream_event,
    build_stream_event,
    build_text_delta_stream,
    canonical_sha256,
    descriptor_from_registry,
    evaluate_tool_policy,
    project_conversation,
    tool_registry_snapshot,
    validate_stream_chain,
)
from agent_runtime.tool_runner import ToolRunner
from agent_runtime.tools.base import ToolBase, ToolRegistry, ToolResult


REVISION = "a" * 40


def context(*, call_id: str = "call-1", tick: int = 100, epoch_ms: int = 1_000) -> RuntimeContext:
    return RuntimeContext(
        run_id="run-1",
        owner_id="owner-1",
        revision=REVISION,
        tick=tick,
        epoch_ms=epoch_ms,
        call_id=call_id,
    )


def descriptor(
    name: str = "read_file",
    *,
    effect: str = "read",
    capabilities: tuple[str, ...] = ("repository",),
) -> ToolDescriptor:
    return ToolDescriptor(
        name=name,
        description="Bounded test tool",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        effect=effect,  # type: ignore[arg-type]
        capabilities=capabilities,
    )


class CountingTool(ToolBase):
    name = "counting"
    description = "Count deterministic invocations"
    parameters = {"value": {"type": "integer", "required": True}}

    def __init__(self) -> None:
        self.calls = 0

    def execute(self, params: dict, workspace_path: str | None = None) -> ToolResult:
        self.calls += 1
        return ToolResult(
            status="done",
            output=f"value={params['value']}",
            metadata={"calls": self.calls},
        )


def test_canonical_hash_is_key_order_independent_and_float_free() -> None:
    assert canonical_sha256({"b": 2, "a": 1}) == canonical_sha256({"a": 1, "b": 2})
    with pytest.raises(ProviderNeutralRuntimeError, match="floating-point"):
        canonical_sha256({"value": 1.5})


def test_runtime_context_requires_explicit_revision_tick_epoch_and_call_identity() -> None:
    assert context().sha256 == context().sha256
    with pytest.raises(ProviderNeutralRuntimeError, match="revision"):
        RuntimeContext("run-1", "owner-1", "main", 0, 0, "call-1")
    with pytest.raises(ProviderNeutralRuntimeError, match="call_id"):
        ProviderNeutralRuntimeKernel(
            policy_rules=(PolicyRule("allow", "ALLOW", "allowed"),)
        ).authorize_tool(context=context(call_id=""), tool=descriptor(), parameters={})


def test_multimodal_input_accepts_only_provenance_bound_references() -> None:
    image = RuntimeInputPart(
        kind="image",
        artifact_id="artifact-1",
        sha256="b" * 64,
        mime_type="image/png",
        size_bytes=512,
        source="private-r2",
    )
    envelope = RuntimeInputEnvelope(
        parts=(RuntimeInputPart(kind="text", text="Inspect this image."), image)
    )
    assert envelope.to_dict()["parts"][1]["artifactId"] == "artifact-1"
    with pytest.raises(ProviderNeutralRuntimeError, match="SHA-256"):
        RuntimeInputPart(
            kind="document",
            artifact_id="document-1",
            mime_type="application/pdf",
            size_bytes=512,
        )
    with pytest.raises(ProviderNeutralRuntimeError, match="raw bytes"):
        canonical_sha256({"payload": b"not-allowed"})


def test_tool_registry_snapshot_is_sorted_and_duplicate_safe() -> None:
    first = descriptor("zeta")
    second = descriptor("alpha")
    one = tool_registry_snapshot((first, second))
    two = tool_registry_snapshot((second, first))
    assert one["registrySha256"] == two["registrySha256"]
    assert [item["name"] for item in one["tools"]] == ["alpha", "zeta"]
    with pytest.raises(ProviderNeutralRuntimeError, match="duplicate"):
        tool_registry_snapshot((first, first))


def test_policy_defaults_to_deny() -> None:
    result = evaluate_tool_policy((), descriptor())
    assert result.decision == "DENY"
    assert result.rule_id == "default-deny"


def test_policy_precedence_is_exact_then_prefix_then_effect_capability_global() -> None:
    tool = descriptor("repository_write", effect="workspace-write")
    rules = (
        PolicyRule("global-allow", "ALLOW", "global"),
        PolicyRule("effect-allow", "ALLOW", "writes", effect="workspace-write"),
        PolicyRule("prefix-ask", "ASK_OWNER", "confirm repository tools", tool_prefix="repository_"),
        PolicyRule("exact-deny", "DENY", "protected exact tool", tool_name="repository_write"),
    )
    result = evaluate_tool_policy(rules, tool)
    assert result.decision == "DENY"
    assert result.rule_id == "exact-deny"


def test_policy_deny_wins_inside_same_selector_bucket() -> None:
    tool = descriptor("repository_read")
    rules = (
        PolicyRule("exact-allow", "ALLOW", "allow", tool_name=tool.name, priority=100),
        PolicyRule("exact-deny", "DENY", "deny", tool_name=tool.name, priority=-100),
    )
    assert evaluate_tool_policy(rules, tool).rule_id == "exact-deny"


def test_hook_order_is_priority_then_registration_sequence() -> None:
    seen: list[str] = []
    pipeline = HookPipeline()
    pipeline.register("low", "BEFORE_TOOL", lambda _ctx, _payload: seen.append("low") or HookDecision(), priority=1)
    pipeline.register("high-a", "BEFORE_TOOL", lambda _ctx, _payload: seen.append("high-a") or HookDecision(), priority=10)
    pipeline.register("high-b", "BEFORE_TOOL", lambda _ctx, _payload: seen.append("high-b") or HookDecision(), priority=10)

    result = pipeline.run("BEFORE_TOOL", context(), {"tool": "read_file"})
    assert result.allowed is True
    assert seen == ["high-a", "high-b", "low"]
    assert len({receipt.receipt_sha256 for receipt in result.receipts}) == 3


def test_hook_exception_fails_closed() -> None:
    pipeline = HookPipeline()

    def broken(_ctx, _payload):
        raise RuntimeError("boom")

    pipeline.register("broken", "BEFORE_TOOL", broken)
    result = pipeline.run("BEFORE_TOOL", context(), {"tool": "read_file"})
    assert result.decision == "DENY"
    assert "failed closed" in result.reason


def test_run_preparation_binds_input_registry_hooks_and_stream_chain() -> None:
    pipeline = HookPipeline()
    pipeline.register("run-guard", "BEFORE_RUN", lambda _ctx, _payload: HookDecision())
    pipeline.register("input-guard", "BEFORE_INPUT", lambda _ctx, _payload: HookDecision())
    kernel = ProviderNeutralRuntimeKernel(hooks=pipeline)
    envelope = RuntimeInputEnvelope(parts=(RuntimeInputPart(kind="text", text="Hello"),))
    prepared = kernel.prepare_run(context=context(), envelope=envelope, tools=(descriptor(),))
    assert prepared.status == "ready"
    assert [event.kind for event in prepared.events] == ["run_started", "input_accepted"]
    assert validate_stream_chain(prepared.events) is True
    assert len(prepared.hook_receipts) == 2


def test_stream_hash_chain_rejects_reasoning_and_detects_tampering() -> None:
    first = build_stream_event(
        sequence=0,
        kind="run_started",
        context=context(),
        payload={"source": "runtime"},
    )
    second = build_stream_event(
        sequence=1,
        kind="text_delta",
        context=context(),
        payload={"text": "hello"},
        previous_sha256=first.event_sha256,
    )
    assert validate_stream_chain((first, second)) is True
    assert validate_stream_chain((first, replace(second, previous_sha256=ZERO_SHA256))) is False
    with pytest.raises(ProviderNeutralRuntimeError, match="chain-of-thought"):
        build_stream_event(sequence=0, kind="reasoning", context=context(), payload={"text": "hidden"})


def test_text_delta_stream_and_conversation_are_event_projections_not_state_truth() -> None:
    events = append_stream_event((), kind="run_started", context=context(), payload={})
    events = build_text_delta_stream(context=context(), chunks=("small ", "heart"), previous_events=events)
    events = append_stream_event(events, kind="run_completed", context=context(), payload={"evidence": "verified"})
    projection = project_conversation(events)
    assert projection.text == "small heart"
    assert projection.terminal_status == "completed"
    assert projection.last_event_sha256 == events[-1].event_sha256


def test_deterministic_trigger_uses_explicit_ticks_only() -> None:
    trigger = DeterministicTrigger("health-lane", interval_ticks=10, offset_tick=5, max_fires=2)
    assert trigger.due(tick=5, fired_count=0) is True
    assert trigger.due(tick=15, fired_count=1) is True
    assert trigger.due(tick=25, fired_count=2) is False
    assert trigger.due(tick=16, fired_count=1) is False
    assert len(trigger.receipt(tick=15, fired_count=1)["receiptSha256"]) == 64


def test_blocked_tool_does_not_reach_effect_adapter() -> None:
    registry = ToolRegistry()
    tool = CountingTool()
    registry.register(tool)
    kernel = ProviderNeutralRuntimeKernel(policy_rules=())
    result = kernel.execute_registered_tool(
        context=context(),
        tool=descriptor("counting"),
        parameters={"value": 1},
        registry=registry,
    )
    assert result.status == "blocked"
    assert tool.calls == 0
    assert result.events[0].kind == "evidence"


def test_owner_approval_policy_does_not_reach_effect_adapter() -> None:
    registry = ToolRegistry()
    tool = CountingTool()
    registry.register(tool)
    kernel = ProviderNeutralRuntimeKernel(
        policy_rules=(PolicyRule("ask-counting", "ASK_OWNER", "owner confirmation", tool_name="counting"),)
    )
    result = kernel.execute_registered_tool(
        context=context(),
        tool=descriptor("counting"),
        parameters={"value": 1},
        registry=registry,
    )
    assert result.status == "approval-required"
    assert tool.calls == 0
    assert result.events[0].kind == "approval_required"


def test_allowed_tool_runs_once_through_existing_registry_with_hash_evidence() -> None:
    registry = ToolRegistry()
    tool = CountingTool()
    registry.register(tool)
    kernel = ProviderNeutralRuntimeKernel(
        policy_rules=(PolicyRule("allow-counting", "ALLOW", "bounded local call", tool_name="counting"),)
    )
    result = kernel.execute_registered_tool(
        context=context(),
        tool=descriptor("counting"),
        parameters={"value": 7},
        registry=registry,
    )
    assert result.status == "done"
    assert tool.calls == 1
    assert [event.kind for event in result.events] == ["tool_call", "tool_result"]
    assert validate_stream_chain(result.events) is True
    assert len(result.evidence_sha256) == 64


def test_tool_runner_exposes_provider_neutral_entry_without_changing_legacy_path() -> None:
    runner = ToolRunner()
    registry = ToolRegistry()
    counting = CountingTool()
    registry.register(counting)
    runner.registry = registry
    kernel = ProviderNeutralRuntimeKernel(
        policy_rules=(PolicyRule("allow-counting", "ALLOW", "bounded", tool_name="counting"),)
    )
    tool = descriptor_from_registry(
        registry,
        "counting",
        effect="read",
        capabilities=("test",),
    )
    result = runner.execute_provider_neutral(
        kernel=kernel,
        context=context(),
        descriptor=tool,
        parameters={"value": 9},
    )
    assert result.status == "done"
    assert counting.calls == 1


def test_runtime_module_has_no_hidden_clock_uuid_or_provider_imports() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "agent_runtime"
        / "provider_neutral_runtime.py"
    ).read_text(encoding="utf-8")
    forbidden_imports = ("import time", "from time", "import uuid", "from uuid")
    assert not any(item in source for item in forbidden_imports)
    assert "google.genai" not in source
    assert "google_genai" not in source
    assert "gemini" not in source.lower()
    assert "antigravity" not in source.lower()
