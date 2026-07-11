"""Compatibility mapping view for runtime event dataclasses.

Some older runner and telemetry code treats events as dictionaries and calls
``event.get(...)``. The canonical runtime keeps typed dataclasses, so this
module adds a narrow read-only mapping view without changing stored truth.
"""

from __future__ import annotations

from typing import Any

from .contracts import SovereignAgentEvent
from .tool_events import ToolEvent


def _sovereign_event_to_dict(event: SovereignAgentEvent) -> dict[str, Any]:
    return {
        "stage": event.stage,
        "level": event.level,
        "message": event.message,
        "at": event.at,
    }


def _event_get(event: Any, key: str, default: Any = None) -> Any:
    payload = event.to_dict()
    return payload.get(key, default)


def install_event_mapping_compat() -> None:
    """Install a read-only ``to_dict``/``get`` compatibility boundary once."""

    if not hasattr(SovereignAgentEvent, "to_dict"):
        setattr(SovereignAgentEvent, "to_dict", _sovereign_event_to_dict)
    if not hasattr(SovereignAgentEvent, "get"):
        setattr(SovereignAgentEvent, "get", _event_get)
    if not hasattr(ToolEvent, "get"):
        setattr(ToolEvent, "get", _event_get)
