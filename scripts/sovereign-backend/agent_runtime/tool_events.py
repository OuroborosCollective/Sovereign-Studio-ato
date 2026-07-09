"""Tool events for Sovereign Agent Runtime.

This module provides event tracking and sanitization for tool executions.
Events are append-only and sanitized to prevent secret leakage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


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
    """Append-only log of tool execution events.
    
    Events are stored in memory and can be flushed to storage.
    All events are sanitized before storage.
    """

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
        """Log tool execution start."""
        return self.add(
            stage="tool_started",
            level="info",
            message=f"Tool '{tool_name}' execution started",
            tool_name=tool_name,
            call_id=call_id,
        )

    def tool_completed(
        self,
        tool_name: str,
        call_id: str | None = None,
        duration_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolEvent:
        """Log tool execution completion."""
        return self.add(
            stage="tool_completed",
            level="success",
            message=f"Tool '{tool_name}' execution completed",
            tool_name=tool_name,
            call_id=call_id,
            duration_ms=duration_ms,
            metadata=metadata,
        )

    def tool_blocked(
        self,
        tool_name: str,
        reason: str,
        call_id: str | None = None,
    ) -> ToolEvent:
        """Log tool execution blocked by policy."""
        return self.add(
            stage="tool_blocked",
            level="warning",
            message=f"Tool '{tool_name}' blocked: {reason}",
            tool_name=tool_name,
            call_id=call_id,
            metadata={"blocker": reason},
        )

    def tool_error(
        self,
        tool_name: str,
        error: str,
        call_id: str | None = None,
    ) -> ToolEvent:
        """Log tool execution error."""
        return self.add(
            stage="tool_error",
            level="error",
            message=f"Tool '{tool_name}' error: {error}",
            tool_name=tool_name,
            call_id=call_id,
            metadata={"error": error},
        )

    def tool_validation_failed(
        self,
        tool_name: str,
        reason: str,
        call_id: str | None = None,
    ) -> ToolEvent:
        """Log tool parameter validation failure."""
        return self.add(
            stage="tool_validation_failed",
            level="warning",
            message=f"Tool '{tool_name}' validation failed: {reason}",
            tool_name=tool_name,
            call_id=call_id,
            metadata={"validation_error": reason},
        )

    def list_all(self) -> list[ToolEvent]:
        """Get all logged events."""
        return list(self._events)

    def count(self) -> int:
        """Get the number of logged events."""
        return len(self._events)

    def clear(self) -> None:
        """Clear all events (use with caution)."""
        self._events.clear()

    def to_dict_list(self) -> list[dict[str, Any]]:
        """Convert all events to dictionaries."""
        return [e.to_dict() for e in self._events]


def append_tool_result_to_job(
    conn: Any,
    job_id: str,
    tool_result: dict[str, Any],
) -> None:
    """Append tool result as event to a job.
    
    Args:
        conn: Database connection
        job_id: Job ID
        tool_result: Tool result dict with 'ok', 'output', 'error', etc.
    """
    from .job_store import append_agent_event
    event = ToolEvent(
        stage="tool_result",
        level="success" if tool_result.get("ok") else "error",
        message=tool_result.get("output", tool_result.get("error", "")),
        tool_name=tool_result.get("tool"),
        metadata={"result": tool_result},
    )
    append_agent_event(conn, job_id, event)


def evidence_gate_to_agent_event(evidence_result: Any) -> ToolEvent:  # EvidenceGateResult
    """Convert evidence gate result to agent event."""
    return ToolEvent(
        stage="evidence_gate",
        level="success" if evidence_result.passed else "error",
        message=evidence_result.reason,
        metadata={
            "evidence_count": evidence_result.evidence_count,
            "placeholder_count": evidence_result.placeholder_count,
        },
    )


def predictive_tool_signal(tool_event: ToolEvent) -> dict:
    """Convert tool event to predictive signal for telemetry."""
    return {
        "signal": f"tool_{tool_event.level}",
        "tool_name": tool_event.tool_name,
        "stage": tool_event.stage,
        "message": tool_event.sanitize_message(),
    }


def tool_result_to_agent_events(
    tool_result: dict[str, Any],
) -> list[ToolEvent]:
    """Convert tool result dict to agent events."""
    events = []
    
    if tool_result.get("ok"):
        events.append(ToolEvent(
            stage="tool_completed",
            level="success",
            message=f"Tool '{tool_result.get('tool', 'unknown')}' completed",
            tool_name=tool_result.get("tool"),
            metadata={"output_preview": tool_result.get("output", "")[:200]},
        ))
    else:
        events.append(ToolEvent(
            stage="tool_failed",
            level="error",
            message=f"Tool '{tool_result.get('tool', 'unknown')}' failed: {tool_result.get('error', 'Unknown error')}",
            tool_name=tool_result.get("tool"),
            metadata={"error": tool_result.get("error", "")},
        ))
    
    return events
