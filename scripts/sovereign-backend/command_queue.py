from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from command_contract import is_mutating_action

MAX_QUEUE_MESSAGE_BYTES = 1_200_000
DEFAULT_QUEUE_ROOT = "/opt/sovereign-chatgpt-tools/command-queue"
_REQUEST_ID = re.compile(r"^[0-9a-f]{32}$")


class HostCommandQueueClient:
    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or os.getenv("SOVEREIGN_MCP_COMMAND_QUEUE", DEFAULT_QUEUE_ROOT))
        self.inbox = self.root / "inbox"
        self.processing = self.root / "processing"
        self.outbox = self.root / "outbox"

    def _ensure_paths(self) -> None:
        if self.root.is_symlink():
            raise RuntimeError("Command-Queue-Wurzel darf kein Symlink sein")
        self.inbox.mkdir(parents=True, exist_ok=True, mode=0o770)
        self.processing.mkdir(parents=True, exist_ok=True, mode=0o770)
        self.outbox.mkdir(parents=True, exist_ok=True, mode=0o770)

    @staticmethod
    def _write_atomic(path: Path, payload: bytes) -> None:
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o660)
        temporary.replace(path)

    def _read_result(self, result_path: Path, request_id: str) -> dict[str, Any]:
        if result_path.is_symlink() or not result_path.is_file():
            return {
                "ok": False,
                "status": "BLOCKED",
                "failure_family": "HOST_COMMAND_RESULT_PATH_INVALID",
                "blocker": "Host-Worker-Ergebnispfad ist kein reguläres Ergebnisfile",
            }
        if result_path.stat().st_size > MAX_QUEUE_MESSAGE_BYTES:
            result_path.unlink(missing_ok=True)
            return {
                "ok": False,
                "status": "BLOCKED",
                "failure_family": "HOST_COMMAND_RESULT_TOO_LARGE",
                "blocker": "Host-Worker-Ergebnis überschreitet das Größenlimit",
            }
        try:
            response = json.loads(result_path.read_text("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            result_path.unlink(missing_ok=True)
            return {
                "ok": False,
                "status": "BLOCKED",
                "failure_family": "HOST_COMMAND_RESULT_INVALID",
                "blocker": "Host-Worker-Ergebnis ist kein gültiges JSON-Objekt",
            }
        result_path.unlink(missing_ok=True)
        if response.get("request_id") != request_id:
            return {
                "ok": False,
                "status": "BLOCKED",
                "failure_family": "HOST_COMMAND_RESULT_MISMATCH",
                "blocker": "Host-Worker-Ergebnis gehört nicht zum eingestellten Job",
            }
        result = response.get("result")
        if not isinstance(result, dict):
            return {
                "ok": False,
                "status": "BLOCKED",
                "failure_family": "HOST_COMMAND_RESULT_INVALID",
                "blocker": "Host-Worker-Ergebnis enthält kein Ergebnisobjekt",
            }
        return result

    def status(self, request_id: str) -> dict[str, Any]:
        identifier = str(request_id or "").strip().lower()
        if not _REQUEST_ID.fullmatch(identifier):
            raise ValueError("request_id muss aus 32 hexadezimalen Zeichen bestehen")
        self._ensure_paths()
        result_path = self.outbox / f"{identifier}.json"
        if result_path.exists() or result_path.is_symlink():
            return self._read_result(result_path, identifier)
        if (self.processing / f"{identifier}.json").is_file():
            return {"ok": False, "status": "IN_PROGRESS", "request_id": identifier}
        if (self.inbox / f"{identifier}.json").is_file():
            return {"ok": False, "status": "QUEUED", "request_id": identifier}
        return {"ok": False, "status": "NOT_FOUND", "request_id": identifier}

    def submit(
        self,
        action: str,
        arguments: dict[str, Any] | None = None,
        *,
        timeout: float,
    ) -> dict[str, Any]:
        action_name = str(action or "").strip()
        if not is_mutating_action(action_name):
            raise ValueError(f"Queue akzeptiert nur mutierende allowlistete Aktionen: {action_name}")
        values = arguments or {}
        if not isinstance(values, dict):
            raise ValueError("arguments must be an object")

        self._ensure_paths()
        request_id = uuid.uuid4().hex
        request_path = self.inbox / f"{request_id}.json"
        processing_path = self.processing / f"{request_id}.json"
        result_path = self.outbox / f"{request_id}.json"
        payload = json.dumps(
            {
                "version": 1,
                "request_id": request_id,
                "action": action_name,
                "arguments": values,
                "submitted_at": int(time.time()),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        if len(payload) > MAX_QUEUE_MESSAGE_BYTES:
            raise ValueError("Command-Queue-Anfrage ist größer als 1,2 MB")
        self._write_atomic(request_path, payload)

        deadline = time.monotonic() + max(0.1, float(timeout))
        while time.monotonic() < deadline:
            if result_path.exists() or result_path.is_symlink():
                return self._read_result(result_path, request_id)
            time.sleep(0.1)

        if result_path.exists() or result_path.is_symlink():
            return self._read_result(result_path, request_id)
        if request_path.is_file() and not request_path.is_symlink():
            try:
                request_path.unlink()
            except FileNotFoundError:
                pass
            else:
                return {
                    "ok": False,
                    "status": "CANCELLED",
                    "failure_family": "HOST_COMMAND_QUEUE_TIMEOUT_BEFORE_CLAIM",
                    "blocker": "Job wurde vor der Ausführung abgebrochen, weil ihn kein Host-Worker fristgerecht beansprucht hat",
                    "request_id": request_id,
                }
        if processing_path.is_file() and not processing_path.is_symlink():
            return {
                "ok": False,
                "status": "IN_PROGRESS",
                "failure_family": "HOST_COMMAND_STILL_RUNNING",
                "request_id": request_id,
                "next_action": "read_mcp_host_command_status_without_resubmitting",
            }
        return {
            "ok": False,
            "status": "UNKNOWN",
            "failure_family": "HOST_COMMAND_OUTCOME_UNKNOWN",
            "blocker": "Job ist weder in Queue, Verarbeitung noch Ergebnisablage auffindbar",
            "request_id": request_id,
            "next_action": "inspect_sovereign_command_worker_journal_without_resubmitting",
        }
