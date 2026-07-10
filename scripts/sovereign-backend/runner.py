"""Dedicated process entry point for the Sovereign local runner."""

from __future__ import annotations

import os
import signal
import threading

from agent_runtime.sovereign_local_runner import (
    register_sovereign_runner,
    stop_sovereign_runner,
)


def main() -> int:
    if os.getenv("SOVEREIGN_RUNNER_ENABLED", "false").lower() != "true":
        print("[runner] Refusing to start without SOVEREIGN_RUNNER_ENABLED=true")
        return 2

    workspace_root = os.getenv(
        "SOVEREIGN_AGENT_WORKSPACE_ROOT",
        "/tmp/sovereign-agent/workspaces",
    )
    daemon = register_sovereign_runner(workspace_root=workspace_root)
    if daemon is None:
        return 1

    stopped = threading.Event()

    def request_stop(_signum, _frame):
        stopped.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        while daemon.is_alive() and not stopped.wait(1):
            pass
        return 0 if daemon.is_alive() or stopped.is_set() else 1
    finally:
        stop_sovereign_runner()


if __name__ == "__main__":
    raise SystemExit(main())
