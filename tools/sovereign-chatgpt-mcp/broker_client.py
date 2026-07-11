from __future__ import annotations

import json
import os
import socket
import uuid
from pathlib import Path
from typing import Any


class HostBrokerClient:
    def __init__(self, socket_path: str | None = None, timeout: float = 30.0) -> None:
        self.socket_path = Path(socket_path or os.getenv("SOVEREIGN_MCP_BROKER_SOCKET", "/run/sovereign-chatgpt-broker/operator.sock"))
        self.timeout = timeout

    def call(self, action: str, arguments: dict[str, Any] | None = None, *, timeout: float | None = None) -> dict[str, Any]:
        request_id = uuid.uuid4().hex
        payload = json.dumps(
            {"request_id": request_id, "action": action, "arguments": arguments or {}},
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        if len(payload) > 64_000:
            raise ValueError("Broker-Anfrage ist zu groß")
        if not self.socket_path.is_socket():
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": f"Host-Broker-Socket fehlt: {self.socket_path}",
            }

        chunks: list[bytes] = []
        size = 0
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout or self.timeout)
            client.connect(str(self.socket_path))
            client.sendall(payload)
            while True:
                chunk = client.recv(8192)
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > 1_000_000:
                    raise RuntimeError("Broker-Antwort ist zu groß")
                if b"\n" in chunk:
                    break

        raw = b"".join(chunks).split(b"\n", 1)[0]
        response = json.loads(raw.decode("utf-8"))
        if response.get("request_id") != request_id:
            raise RuntimeError("Broker-Antwort gehört nicht zur Anfrage")
        result = response.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("Broker-Antwort enthält kein Ergebnis")
        return result
