"""Tool events for Sovereign Agent Runtime.

This module provides event tracking and sanitization for tool executions.
Events are append-only and sanitized to prevent secret leakage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .evidence_gate import EvidenceGateInput, EvidenceGateResult, evaluate_agent_evidence, evaluate_tool_result_evidence, evidence_gate_signal


@dataclass
class ToolEvent:
    """A single tool execution event.

    Events are immutable once created and sanitized.
    No raw tokens, secrets, or auth headers are stored.
    """
    stage: str
    level: str  # info | warning | error | success
    message: str
    tool_name: str | None = None
    call_id: str | None = None
    duration_ms: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    at: int = field(default_factory=lambda: int(datetime.now(timezone.utc).timestamp() * 1000))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "stage": self.stage,
            "level": self.level,
            "message": self.sanitize_message(),
            "tool_name": self.tool_name,
            "call_id": self.call_id,
            "duration_ms": self.duration_ms,
            "metadata": self._sanitize_metadata(),
            "at": self.at,
        }

    def sanitize_message(self) -> str:
        """Remove secret-like content from message."""
        return _sanitize_text(self.message)

    def _sanitize_metadata(self) -> dict[str, Any]:
        """Remove secrets from metadata."""
        return {k: _sanitize_text(str(v)) for k, v in self.metadata.items()}


def _sanitize_text(text: str) -> str:
    """Sanitize text by masking secret-like values."""
    if not text:
        return ""

    import re

    patterns = [
        (r'(token["\']?\s*[:=]\s*)["\']?[\w-]{20,}["\']?', r'\1[REDACTED]'),
        (r'(password["\']?\s*[:=]\s*)["\']?[^\s"\']{8,}["\']?', r'\1[REDACTED]'),
        (r'(api_?key["\']?\s*[:=]\s*)["\']?[\w-]{20,}["\']?', r'\1[REDACTED]'),
        (r'(secret["\']?\s*[:=]\s*)["\']?[^\s"\']{8,}["\']?', r'\1[REDACTED]'),
        (r'(bearer\s+)[\w.-]{20,}', r'\1[REDACTED]'),
        (r'(gh[pso]_[a-zA-Z0-9]{36,})', r'[GITHUB_TOKEN_REDACTED]'),
        (r'(sk-[a-zA-Z0-9]{32,})', r'[OPENAI_KEY_REDACTED]'),
    ]

    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return text


class ToolEventLog:
    """Append-only log of tool execution events."""

    def __init__(self):
        self._events: list[ToolEvent] = []

    def add(
        self,
        stage: str,
        level: str,
        message: str,
        tool_name: str | None = None,
        call_id: str | None = None,
        duration_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolEvent:
        """Add an event to the log."""
        event = ToolEvent(
            stage=stage,
            level=level,
            message=message,
            tool_name=tool_name,
            call_id=call_id,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )
        self._events.append(event)
        return event

    def tool_started(self, tool_name: str, call_id: str | None = None) -> ToolEvent:
        return self.add("tool_started", "info", f"Tool '{tool_name}' execution started", tool_name, call_id)

    def tool_completed(
        self,
        tool_name: str,
        call_id: str | None = None,
        duration_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolEvent:
        return self.add(
            "tool_completed",
            "success",
            f"Tool '{tool_name}' execution completed",
            tool_name,
            call_id,
            duration_ms,
            metadata,
        )

    def tool_blocked(self, tool_name: str, reason: str, call_id: str | None = None) -> ToolEvent:
        return self.add(
            "tool_blocked",
            "warning",
            f"Tool '{tool_name}' blocked: {reason}",
            tool_name,
            call_id,
            metadata={"blocker": reason},
        )

    def tool_error(self, tool_name: str, error: str, call_id: str | None = None) -> ToolEvent:
        return self.add(
            "tool_error",
            "error",
            f"Tool '{tool_name}' error: {error}",
            tool_name,
            call_id,
            metadata={"error": error},
        )

    def tool_validation_failed(self, tool_name: str, reason: str, call_id: str | None = None) -> ToolEvent:
        return self.add(
            "tool_validation_failed",
            "warning",
            f"Tool '{tool_name}' validation failed: {reason}",
            tool_name,
            call_id,
            metadata={"validation_error": reason},
        )

    def list_all(self) -> list[ToolEvent]:
        return list(self._events)

    def count(self) -> int:
        return len(self._events)

    def clear(self) -> None:
        self._events.clear()

    def to_dict_list(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self._events]


def _as_tool_dict(tool_result: Any) -> dict[str, Any]:
    if hasattr(tool_result, "to_dict"):
        return tool_result.to_dict()
    if isinstance(tool_result, dict):
        return tool_result
    return {"ok": False, "tool": "unknown", "error": "Unsupported tool result shape"}


def _tool_output(tool_result: Any) -> str | None:
    if isinstance(tool_result, dict):
        return tool_result.get("output") or tool_result.get("stdout")
    return getattr(tool_result, "output", None) or getattr(tool_result, "stdout", None)


def _tool_error(tool_result: Any) -> str | None:
    if isinstance(tool_result, dict):
        return tool_result.get("error") or tool_result.get("stderr") or tool_result.get("blocker")
    return getattr(tool_result, "error", None) or getattr(tool_result, "stderr", None) or getattr(tool_result, "blocker", None)


def _tool_status(tool_result: Any) -> str:
    if isinstance(tool_result, dict):
        if tool_result.get("blocked"):
            return "blocked"
        return "done" if tool_result.get("ok") else "error"
    return str(getattr(tool_result, "status", "error"))


def _evidence_from_tool_result(tool_result: Any) -> EvidenceGateResult:
    status = _tool_status(tool_result)
    changed_files = tuple(getattr(tool_result, "changed_files", ()) or _as_tool_dict(tool_result).get("changed_files", ()) or ())
    diff_summary = getattr(tool_result, "diff_summary", None) or _as_tool_dict(tool_result).get("diff_summary")
    test_summary = getattr(tool_result, "test_summary", None) or _as_tool_dict(tool_result).get("test_summary")
    if status in ("blocked", "error"):
        gate = evaluate_tool_result_evidence(_tool_output(tool_result), _tool_error(tool_result))
    else:
        gate = evaluate_agent_evidence(EvidenceGateInput(
            changed_files=changed_files,
            diff_summary=diff_summary,
            test_summary=test_summary,
            tool_status=status,
        ))
    setattr(gate, "allowed", gate.passed)
    return gate


def append_tool_result_to_job(conn: Any, job_id: str, tool_result: Any) -> EvidenceGateResult:
    """Append tool result as event to a job and return its EvidenceGateResult."""
    from .contracts import SovereignAgentEvent
    from .job_store import append_agent_event, update_agent_job_state

    payload = _as_tool_dict(tool_result)
    status = _tool_status(tool_result)
    level = "success" if status == "done" else "warning" if status == "blocked" else "error"
    message = payload.get("output") or payload.get("error") or payload.get("blocker") or f"Tool {payload.get('tool', 'unknown')} {status}"
    append_agent_event(conn, job_id, SovereignAgentEvent(
        stage=f"agent_tool_{status}",
        level=level,  # type: ignore[arg-type]
        message=_sanitize_text(str(message))[:1200],
    ))

    gate = _evidence_from_tool_result(tool_result)
    tool_failed = status in ("blocked", "error")
    evidence_pending = status == "done" and not gate.passed
    evidence_message = (
        gate.reason
        if gate.passed or tool_failed
        else f"Evidence pending after successful intermediate tool execution: {gate.reason}"
    )
    append_agent_event(conn, job_id, SovereignAgentEvent(
        stage="agent_evidence_gate" if not evidence_pending else "agent_evidence_pending",
        level="success" if gate.passed else "warning" if tool_failed else "info",
        message=_sanitize_text(evidence_message)[:1200],
    ))

    next_status = (
        "validating"
        if gate.passed and gate.can_prepare_draft_pr
        else "blocked"
        if tool_failed
        else "running"
    )
    next_blocker = None if gate.passed else gate.reason
    update_agent_job_state(
        conn,
        job_id=job_id,
        status=next_status,
        changed_files=getattr(tool_result, "changed_files", None) or None,
        diff_summary=getattr(tool_result, "diff_summary", None),
        test_summary=getattr(tool_result, "test_summary", None),
        blocker=next_blocker,
        clear_blocker=gate.passed,
    )
    return gate


def evidence_gate_to_agent_event(evidence_result: Any) -> ToolEvent:
    return ToolEvent(
        stage="evidence_gate",
        level="success" if evidence_result.passed else "error",
        message=evidence_result.reason,
        metadata={
            "evidence_count": evidence_result.evidence_count,
            "placeholder_count": evidence_result.placeholder_count,
        },
    )


def predictive_tool_signal(tool_result: Any, evidence_result: Any | None = None) -> dict:
    payload = _as_tool_dict(tool_result)
    signal = payload.get("predictive_signal") or f"tool_{payload.get('status', 'result')}"
    result = {
        "signal": signal,
        "tool": payload.get("tool"),
        "status": payload.get("status"),
        "changedFiles": payload.get("changed_files", []),
        "hasDiff": bool(payload.get("diff_summary")),
        "hasTests": bool(payload.get("test_summary")),
        "blocker": payload.get("blocker"),
    }
    if evidence_result is not None:
        result["evidence"] = evidence_gate_signal(evidence_result)
    return result


def tool_result_to_agent_events(tool_result: Any) -> list[ToolEvent]:
    payload = _as_tool_dict(tool_result)
    ok = bool(payload.get("ok"))
    if ok:
        return [ToolEvent(
            stage="tool_completed",
            level="success",
            message=f"Tool '{payload.get('tool', 'unknown')}' completed",
            tool_name=payload.get("tool"),
            metadata={"output_preview": str(payload.get("output", ""))[:200]},
        )]
    return [ToolEvent(
        stage="tool_failed",
        level="error",
        message=f"Tool '{payload.get('tool', 'unknown')}' failed: {payload.get('error', 'Unknown error')}",
        tool_name=payload.get("tool"),
        metadata={"error": payload.get("error", "")},
    )]
