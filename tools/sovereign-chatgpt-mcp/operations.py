from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class OperationsRuntime:
    def __init__(self) -> None:
        self.deploy_script = Path(os.getenv("SOVEREIGN_MCP_DEPLOY_SCRIPT", "/opt/sovereign-chatgpt-tools/bin/deploy-sovereign-backend"))
        self.rollback_script = Path(os.getenv("SOVEREIGN_MCP_ROLLBACK_SCRIPT", "/opt/sovereign-chatgpt-tools/bin/rollback-sovereign-backend"))

    @staticmethod
    def _run(script: Path, args: list[str]) -> dict[str, Any]:
        completed = subprocess.run(
            [str(script), *args],
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
            env={**os.environ, "PATH": os.environ.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")},
        )
        return {
            "ok": completed.returncode == 0,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-24000:],
            "stderr": completed.stderr[-24000:],
        }

    def deploy_verified_release(self, *, image_digest: str, expected_revision: str, confirmation_revision: str) -> dict[str, Any]:
        if os.getenv("SOVEREIGN_MCP_ENABLE_DEPLOY", "0") != "1":
            return {"ok": False, "status": "BLOCKED", "blocker": "Deploy-Writes sind nicht aktiviert"}
        if not IMAGE_DIGEST_RE.fullmatch(image_digest):
            raise ValueError("image_digest muss ein vollständiger sha256-Digest sein")
        if not COMMIT_SHA_RE.fullmatch(expected_revision):
            raise ValueError("expected_revision muss ein vollständiger Commit-SHA sein")
        if confirmation_revision != expected_revision:
            return {"ok": False, "status": "BLOCKED", "blocker": "Bestätigung stimmt nicht mit expected_revision überein"}
        if not self.deploy_script.is_file() or not os.access(self.deploy_script, os.X_OK):
            return {"ok": False, "status": "BLOCKED", "blocker": f"Fixes Deploy-Skript fehlt: {self.deploy_script}"}
        result = self._run(self.deploy_script, [image_digest, expected_revision])
        return {**result, "status": "DEPLOYED" if result["ok"] else "FAILED", "image_digest": image_digest, "expected_revision": expected_revision}

    def rollback_release(self, *, target_image_digest: str, confirmation_digest: str) -> dict[str, Any]:
        if os.getenv("SOVEREIGN_MCP_ENABLE_DEPLOY", "0") != "1":
            return {"ok": False, "status": "BLOCKED", "blocker": "Deploy-Writes sind nicht aktiviert"}
        if not IMAGE_DIGEST_RE.fullmatch(target_image_digest):
            raise ValueError("target_image_digest muss ein vollständiger sha256-Digest sein")
        if confirmation_digest != target_image_digest:
            return {"ok": False, "status": "BLOCKED", "blocker": "Bestätigungs-Digest stimmt nicht"}
        if not self.rollback_script.is_file() or not os.access(self.rollback_script, os.X_OK):
            return {"ok": False, "status": "BLOCKED", "blocker": f"Fixes Rollback-Skript fehlt: {self.rollback_script}"}
        result = self._run(self.rollback_script, [target_image_digest])
        return {**result, "status": "ROLLED_BACK" if result["ok"] else "FAILED", "target_image_digest": target_image_digest}
