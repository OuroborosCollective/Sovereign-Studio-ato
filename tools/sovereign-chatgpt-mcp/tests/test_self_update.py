from __future__ import annotations

import json
from pathlib import Path

from self_update import SelfUpdateRuntime


def test_self_update_is_disabled_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SOVEREIGN_MCP_ENABLE_SELF_UPDATE", raising=False)
    runtime = SelfUpdateRuntime()
    result = runtime.schedule(expected_revision="a" * 40)
    assert result["status"] == "BLOCKED"


def test_self_update_schedules_exact_revision(tmp_path: Path, monkeypatch) -> None:
    request = tmp_path / "request.json"
    status = tmp_path / "status.json"
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_SELF_UPDATE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_SELF_UPDATE_REQUEST", str(request))
    monkeypatch.setenv("SOVEREIGN_MCP_SELF_UPDATE_STATUS", str(status))
    monkeypatch.setenv("SOVEREIGN_MCP_SELF_UPDATE_SERVICE", "test-self-update.service")

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr("self_update.subprocess.run", lambda *args, **kwargs: Completed())
    runtime = SelfUpdateRuntime()
    result = runtime.schedule(expected_revision="b" * 40, reason="repair extension")

    assert result["status"] == "SCHEDULED"
    payload = json.loads(request.read_text("utf-8"))
    assert payload["expected_revision"] == "b" * 40
    assert payload["reason"] == "repair extension"


def test_self_update_status_reads_persisted_result(tmp_path: Path, monkeypatch) -> None:
    status = tmp_path / "status.json"
    status.write_text(json.dumps({"ok": True, "status": "UPDATED", "revision": "c" * 40}), "utf-8")
    monkeypatch.setenv("SOVEREIGN_MCP_SELF_UPDATE_STATUS", str(status))
    result = SelfUpdateRuntime().status()
    assert result["status"] == "UPDATED"
    assert result["revision"] == "c" * 40
