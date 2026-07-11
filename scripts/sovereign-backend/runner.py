"""Quarantined entry point for the unfinished Sovereign local runner.

The previous embedded worker is not production-safe yet. It must not be enabled
until atomic claims, persistent evidence, safe tool execution, and terminal error
handling are covered by CI and a real canary.
"""

from __future__ import annotations


def main() -> int:
    print(
        "[runner] QUARANTINED: the sovereign-local-runner is intentionally disabled "
        "until the dedicated worker contract is fully tested."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
