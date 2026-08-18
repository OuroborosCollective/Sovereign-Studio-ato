from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".git").exists():
            return candidate
        # Snapshot checkouts may ship without .git; accept the canonical
        # backend mirror structure as the repository marker.
        if (candidate / "backend" / "agent_runtime").is_dir() and (
            candidate / "scripts" / "sovereign-backend"
        ).is_dir():
            return candidate
    raise AssertionError("repository root not found")


def test_runtime_worker_event_callsites_cannot_bypass_active_attempt_gate() -> None:
    root = _repo_root()
    runtime_roots = (
        root / "backend/agent_runtime",
        root / "scripts/sovereign-backend/agent_runtime",
    )
    allowed = {"fleet_supervisor.py", "fleet_attempts.py"}
    bypasses: list[str] = []

    for runtime_root in runtime_roots:
        for path in runtime_root.rglob("*.py"):
            if path.name in allowed or "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            if "validate_worker_event" in text:
                bypasses.append(path.relative_to(root).as_posix())

    assert bypasses == [], (
        "production worker-event code must use fleet_attempts.validate_active_worker_event; "
        f"raw validate_worker_event bypasses found: {bypasses}"
    )
