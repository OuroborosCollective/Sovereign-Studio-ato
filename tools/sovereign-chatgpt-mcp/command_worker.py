from __future__ import annotations

import fcntl
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from broker import BrokerRuntime
from command_contract import is_mutating_action
from command_queue import DEFAULT_QUEUE_ROOT, MAX_QUEUE_MESSAGE_BYTES

_REQUEST_NAME = re.compile(r"^(?P<request_id>[0-9a-f]{32})\.json$")


class HostCommandWorker:
    def __init__(self, root: str | None = None, runtime: BrokerRuntime | None = None) -> None:
        self.root = Path(root or os.getenv("SOVEREIGN_MCP_COMMAND_QUEUE", DEFAULT_QUEUE_ROOT))
        self.inbox = self.root / "inbox"
        self.processing = self.root / "processing"
        self.outbox = self.root / "outbox"
        self.runtime = runtime or BrokerRuntime()

    def ensure_paths(self) -> None:
        if self.root.is_symlink():
            raise RuntimeError("command queue root must not be a symlink")
        self.inbox.mkdir(parents=True, exist_ok=True, mode=0o770)
        self.processing.mkdir(parents=True, exist_ok=True, mode=0o770)
        self.outbox.mkdir(parents=True, exist_ok=True, mode=0o770)
        os.chmod(self.root, 0o770)
        os.chmod(self.inbox, 0o770)
        os.chmod(self.processing, 0o770)
        os.chmod(self.outbox, 0o770)

    @staticmethod
    def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(encoded) > MAX_QUEUE_MESSAGE_BYTES:
            encoded = json.dumps(
                {
                    "request_id": str(payload.get("request_id") or "unknown"),
                    "result": {
                        "ok": False,
                        "status": "FAILED",
                        "failure_family": "HOST_COMMAND_RESULT_TOO_LARGE",
                        "error": "Host-Worker-Ergebnis überschreitet das Größenlimit",
                    },
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8") + b"\n"
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        with temporary.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o660)
        temporary.replace(path)

    def process_once(self) -> bool:
        self.ensure_paths()
        for processing_path in sorted(self.processing.glob("*.json")):
            match = _REQUEST_NAME.fullmatch(processing_path.name)
            if not match or processing_path.is_symlink() or not processing_path.is_file():
                continue
            request_id = match.group("request_id")
            self._write_atomic(
                self.outbox / f"{request_id}.json",
                {
                    "request_id": request_id,
                    "result": {
                        "ok": False,
                        "status": "UNKNOWN",
                        "failure_family": "HOST_COMMAND_OUTCOME_UNCERTAIN_AFTER_WORKER_RESTART",
                        "blocker": "Host-Worker wurde während der Ausführung neu gestartet; der Job wird nicht automatisch erneut ausgeführt",
                        "request_id": request_id,
                        "next_action": "inspect_target_state_before_any_manual_retry",
                    },
                },
            )
            processing_path.unlink(missing_ok=True)
            return True

        for request_path in sorted(self.inbox.glob("*.json")):
            match = _REQUEST_NAME.fullmatch(request_path.name)
            if not match or request_path.is_symlink() or not request_path.is_file():
                continue
            request_id = match.group("request_id")
            processing_path = self.processing / request_path.name
            result_path = self.outbox / f"{request_id}.json"
            try:
                request_path.replace(processing_path)
            except FileNotFoundError:
                continue
            try:
                if processing_path.stat().st_size > MAX_QUEUE_MESSAGE_BYTES:
                    raise ValueError("Queue request exceeded size limit")
                request = json.loads(processing_path.read_text("utf-8"))
                if request.get("version") != 1:
                    raise ValueError("unsupported command queue version")
                if request.get("request_id") != request_id:
                    raise ValueError("request id does not match filename")
                action = str(request.get("action") or "").strip()
                arguments = request.get("arguments") or {}
                if not is_mutating_action(action):
                    raise ValueError(f"action is not an allowlisted mutation: {action}")
                if not isinstance(arguments, dict):
                    raise ValueError("arguments must be an object")
                result = self.runtime.dispatch(action, arguments, execution_origin="host_worker")
            except Exception as exc:
                result = {
                    "ok": False,
                    "status": "BLOCKED",
                    "failure_family": "HOST_COMMAND_REQUEST_INVALID",
                    "blocker": str(exc)[:2000],
                }
            self._write_atomic(result_path, {"request_id": request_id, "result": result})
            processing_path.unlink(missing_ok=True)
            return True
        return False

    def serve_forever(self) -> None:
        self.ensure_paths()
        lock_path = Path(
            os.getenv(
                "SOVEREIGN_MCP_COMMAND_WORKER_LOCK",
                "/run/sovereign-chatgpt-command-worker/worker.lock",
            )
        )
        lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o660)
        with os.fdopen(descriptor, "a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            while True:
                if not self.process_once():
                    time.sleep(0.2)


def main() -> None:
    HostCommandWorker().serve_forever()


if __name__ == "__main__":
    main()
