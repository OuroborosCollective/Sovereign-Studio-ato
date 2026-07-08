"""Bridge internal ToolResult objects into Sovereign Agent job state.

This is the backend-side predictive nerve path: tools emit concrete results,
results become agent events and job evidence, and future predictive/runtime gates
can follow those states instead of reading UI text.
"""

from __future__ import annotations

from .contracts import SovereignAgentEvent, sanitize_agent_text
from .evidence_gate import EvidenceGateResult, evaluate_tool_result_evidence, evidence_gate_signal
from .job_store import append_agent_event, update_agent_job_state
from .tools.base import ToolResult


def tool_result_to_agent_events(result: ToolResult) -> tuple[SovereignAgentEvent, ...]:
    if result.events:
        return tuple(
            SovereignAgentEvent(
                stage=sanitize_agent_text(event.stage, 80),
                level=event.level,
                message=sanitize_agent_text(event.message, 1200),
                at=event.at,
            )
            for event in result.events
        )
    level = "success" if result.status == "done" else "warning" if result.status == "blocked" else "error"
    return (
        SovereignAgentEvent(
            stage=f"agent_{result.tool}_tool_{result.status}",
            level=level,
            message=result.blocker or result.test_summary or result.diff_summary or f"{result.tool} tool {result.status}.",
        ),
    )


def evidence_gate_to_agent_event(gate: EvidenceGateResult) -> SovereignAgentEvent:
    level = "success" if gate.can_prepare_draft_pr else "info" if gate.allowed else "warning"
    return SovereignAgentEvent(
        stage=f"agent_evidence_{gate.decision}",
        level=level,
        message=gate.summary,
    )


def derive_job_status_from_evidence_gate(gate: EvidenceGateResult) -> str:
    if not gate.allowed and gate.decision == "block":
        return "blocked"
    if gate.can_prepare_draft_pr:
        return "validating"
    return "running"


def append_tool_result_to_job(conn, job_id: str, result: ToolResult) -> EvidenceGateResult:
    gate = evaluate_tool_result_evidence(result)
    for event in tool_result_to_agent_events(result):
        append_agent_event(conn, job_id, event)
    append_agent_event(conn, job_id, evidence_gate_to_agent_event(gate))
    update_agent_job_state(
        conn,
        job_id=job_id,
        status=derive_job_status_from_evidence_gate(gate),
        changed_files=result.changed_files or None,
        diff_summary=result.diff_summary,
        test_summary=result.test_summary,
        blocker=gate.summary if gate.decision == "block" else None,
    )
    return gate


def predictive_tool_signal(result: ToolResult, gate: EvidenceGateResult | None = None) -> dict:
    evaluated_gate = gate or evaluate_tool_result_evidence(result)
    return {
        "tool": result.tool,
        "status": result.status,
        "allowed": result.allowed,
        "signal": result.predictive_signal,
        "changedFiles": list(result.changed_files),
        "hasDiff": bool(result.diff_summary),
        "hasTests": bool(result.test_summary),
        "blocker": result.blocker,
        "evidence": evidence_gate_signal(evaluated_gate),
    }
