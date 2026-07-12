from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class SelfUpdateRuntime:
    def __init__(self) -> None:
        self.request_path = Path(
            os.getenv(
                "SOVEREIGN_MCP_SELF_UPDATE_REQUEST",
                "/run/sovereign-chatgpt-broker/self-update.request.json",
            )
        )
        self.status_path = Path(
            os.getenv(
                "SOVEREIGN_MCP_SELF_UPDATE_STATUS",
                "/var/lib/sovereign-chatgpt-self-update/status.json",
            )
        )
        self.service_name = os.getenv(
            "SOVEREIGN_MCP_SELF_UPDATE_SERVICE",
            "sovereign-chatgpt-mcp-self-update.service",
        ).strip()

    @staticmethod
    def _enabled() -> bool:
        return os.getenv("SOVEREIGN_MCP_ENABLE_SELF_UPDATE", "0").strip() == "1"

    def schedule(self, *, expected_revision: str, reason: str = "") -> dict[str, Any]:
        if not self._enabled():
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "Privates MCP-Selbstupdate ist nicht aktiviert",
            }
        revision = str(expected_revision or "").strip().lower()
        if not COMMIT_SHA_RE.fullmatch(revision):
            raise ValueError("expected_revision muss ein vollständiger Commit-SHA sein")

        payload = {
            "expected_revision": revision,
            "reason": str(reason or "")[:500],
        }
        self.request_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.request_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", "utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self.request_path)

        completed = subprocess.run(
            ["systemctl", "start", self.service_name],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if completed.returncode != 0:
            return {
                "ok": False,
                "status": "FAILED",
                "blocker": completed.stderr[-2000:] or "Self-update service could not start",
                "expected_revision": revision,
            }
        return {
            "ok": True,
            "status": "SCHEDULED",
            "expected_revision": revision,
            "service": self.service_name,
            "next_action": "poll_mcp_self_update_status_then_retry_original_operation",
        }

    def status(self) -> dict[str, Any]:
        if not self.status_path.is_file():
            return {
                "ok": False,
                "status": "NOT_RUN",
                "status_path": str(self.status_path),
            }
        try:
            payload = json.loads(self.status_path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "ok": False,
                "status": "FAILED",
                "blocker": f"Self-update status is invalid: {exc}",
            }
        if not isinstance(payload, dict):
            return {"ok": False, "status": "FAILED", "blocker": "Self-update status is not an object"}
        return payload
