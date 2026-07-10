"""Quarantined Sovereign local runner compatibility module.

The previous implementation was an unfinished production experiment. It could be
started once per Gunicorn process, claimed jobs non-atomically, executed tools with
insufficient isolation, and could leave jobs permanently in ``running`` after a
failed terminal database update.

The web backend imports these functions during startup. They intentionally keep
that import contract while performing no background work. A replacement must be a
dedicated process with atomic database claims, persistent evidence, safe tools,
leases/heartbeats, recovery, and focused CI coverage before this quarantine is
removed.
"""

from __future__ import annotations

from typing import Any

QUARANTINE_REASON = (
    "sovereign-local-runner is quarantined until the dedicated worker contract "
    "is fully implemented and verified"
)


def call_llm_for_next_action(*_args: Any, **_kwargs: Any) -> tuple[None, str]:
    """Refuse LLM execution while the runner is quarantined."""

    return None, QUARANTINE_REASON


def execute_tool_call(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    """Return a truthful blocker instead of executing an autonomous tool."""

    return {
        "tool": "quarantined",
        "status": "blocked",
        "output": "",
        "error": "",
        "blocker": QUARANTINE_REASON,
        "events": [],
    }


def register_sovereign_runner(
    workspace_root: str | None = None,
) -> None:
    """Preserve the startup API without creating a worker thread."""

    _ = workspace_root
    print(f"[runner] QUARANTINED: {QUARANTINE_REASON}")
    return None


def stop_sovereign_runner() -> None:
    """Compatibility no-op: no runner is started while quarantined."""

    return None
