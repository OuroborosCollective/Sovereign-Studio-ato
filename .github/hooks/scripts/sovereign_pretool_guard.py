#!/usr/bin/env python3
"""Fail-closed guard for a small set of repository-forbidden local command patterns.

The hook never logs tool arguments or secret-shaped values. It only returns an
allow/deny decision to Copilot's preToolUse hook contract.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, Iterable


DENY_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:sudo(?:\s+-\S+)*\s+)?(?:ba)?sh\b",
            re.IGNORECASE,
        ),
        "Remote download piped directly into a shell is forbidden by repository policy.",
    ),
    (
        re.compile(r"\bdocker\s+cp\s+\S+\s+\S+:\S*", re.IGNORECASE),
        "Copying local files directly into a running container is not an allowed release path.",
    ),
    (
        re.compile(
            r"\bdocker\s+exec\b[^\n]*\b(?:apt|apt-get|apk|yum|dnf|pip|pip3|npm|pnpm|yarn)\b[^\n]*\b(?:install|add)\b",
            re.IGNORECASE,
        ),
        "Installing packages inside a running container is forbidden by repository policy.",
    ),
)


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _strings(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            yield from _strings(nested)


def _decision(payload: dict[str, Any]) -> dict[str, str]:
    tool_name = str(payload.get("toolName", ""))
    if tool_name not in {"bash", "powershell"}:
        return {"permissionDecision": "allow"}

    command_surface = "\n".join(_strings(payload.get("toolArgs", {})))
    for pattern, reason in DENY_RULES:
        if pattern.search(command_surface):
            return {
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
    return {"permissionDecision": "allow"}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input must be an object")
        decision = _decision(payload)
    except Exception:
        decision = {
            "permissionDecision": "deny",
            "permissionDecisionReason": "Malformed preToolUse input; failing closed.",
        }
    json.dump(decision, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
