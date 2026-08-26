#!/usr/bin/env python3
"""Host-only bridge from controller activations to real desktop workers.

The backend is intentionally not given Docker authority. It writes one exact,
private activation document. This reconciler observes those documents on the
host and starts/removes the digest-bound desktop worker through the existing
DesktopWorkerRuntime contract.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import time

from desktop_worker import DesktopWorkerError, DesktopWorkerRuntime

ACTIVATION_ROOT = Path(os.getenv("SOVEREIGN_DESKTOP_ACTIVATION_ROOT", "/opt/sovereign-desktop-activations"))
INTERVAL_SECONDS = max(1.0, min(float(os.getenv("SOVEREIGN_DESKTOP_RECONCILE_INTERVAL_SECONDS", "1.0")), 10.0))
_STOP = False


def _stop(_signum, _frame) -> None:
    global _STOP
    _STOP = True


def _activation_id(path: Path) -> str | None:
    if path.suffix != ".json" or path.is_symlink():
        return None
    value = path.stem.lower()
    return value if len(value) == 64 and all(ch in "0123456789abcdef" for ch in value) else None


def _wall_time(path: Path) -> int:
    try:
        payload = json.loads(path.read_text("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return 0
    value = payload.get("wallTimeSeconds") if isinstance(payload, dict) else None
    return value if isinstance(value, int) and 60 <= value <= 86400 else 0


def reconcile_once(runtime: DesktopWorkerRuntime) -> dict[str, int]:
    counts = {"started": 0, "ready": 0, "removed": 0, "blocked": 0}
    now = time.time()
    for path in sorted(ACTIVATION_ROOT.glob("*.json")):
        activation_id = _activation_id(path)
        if activation_id is None:
            continue
        wall_time = _wall_time(path)
        try:
            age = max(0.0, now - path.stat().st_mtime)
        except OSError:
            continue
        if wall_time and age > wall_time:
            try:
                runtime.remove(activation_id=activation_id)
                counts["removed"] += 1
            except Exception:
                counts["blocked"] += 1
            continue
        try:
            readback = runtime.readback(activation_id=activation_id)
            if readback.get("ok") is True and readback.get("running") is True:
                canary = runtime.canary(activation_id=activation_id)
                if canary.get("ok") is True:
                    counts["ready"] += 1
                else:
                    counts["blocked"] += 1
                continue
            started = runtime.start(activation_id=activation_id)
            if started.get("ok") is True:
                counts["started"] += 1
            else:
                counts["blocked"] += 1
        except (DesktopWorkerError, OSError, ValueError):
            counts["blocked"] += 1
    return counts


def main() -> int:
    if os.geteuid() != 0:
        raise SystemExit("desktop activation reconciler requires host root")
    if ACTIVATION_ROOT.is_symlink() or not ACTIVATION_ROOT.is_dir():
        raise SystemExit("desktop activation root is unavailable")
    runtime = DesktopWorkerRuntime(activation_root=str(ACTIVATION_ROOT))
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    while not _STOP:
        reconcile_once(runtime)
        time.sleep(INTERVAL_SECONDS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
