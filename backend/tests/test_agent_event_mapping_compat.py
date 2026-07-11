from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime import SovereignAgentEvent, ToolEvent  # noqa: E402


def test_sovereign_agent_event_exposes_read_only_mapping_view() -> None:
    event = SovereignAgentEvent(
        stage="agent_tool_done",
        level="success",
        message="Real runtime evidence recorded.",
        at=123,
    )

    assert event.get("stage") == "agent_tool_done"
    assert event.get("missing", "fallback") == "fallback"
    assert event.to_dict() == {
        "stage": "agent_tool_done",
        "level": "success",
        "message": "Real runtime evidence recorded.",
        "at": 123,
    }


def test_tool_event_get_uses_sanitized_dictionary_contract() -> None:
    event = ToolEvent(
        stage="tool_completed",
        level="success",
        message="token=abcdefghijklmnopqrstuvwxyz1234567890",
        tool_name="git_status",
        at=456,
    )

    assert event.get("stage") == "tool_completed"
    assert event.get("tool_name") == "git_status"
    assert "abcdefghijklmnopqrstuvwxyz1234567890" not in event.get("message")
