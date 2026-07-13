from __future__ import annotations

import json
import os
import socket
import uuid
from pathlib import Path
from typing import Any

from command_contract import is_mutating_action
from command_queue import HostCommandQueueClient

MAX_BROKER_REQUEST_BYTES = 1_200_000
MAX_BROKER_RESPONSE_BYTES = 1_000_000


class HostBrokerClient:
    def __init__(
        self,
        socket_path: str | None = None,
        timeout: float = 30.0,
        queue_root: str | None = None,
    ) -> None:
        self.socket_path = Path(socket_path or os.getenv("SOVEREIGN_MCP_BROKER_SOCKET", "/run/sovereign-chatgpt-broker/operator.sock"))
        self.timeout = timeout
        self.command_queue = HostCommandQueueClient(queue_root)

    def _socket_contract_failure(self) -> dict[str, Any] | None:
        if not self.socket_path.exists() and not self.socket_path.is_symlink():
            return {
                "ok": False,
                "status": "BLOCKED",
                "failure_family": "BROKER_SOCKET_PATH_ABSENT",
                "blocker": f"Broker-Socket ist in diesem Runtime-Namespace nicht vorhanden: {self.socket_path}",
                "socket_path": str(self.socket_path),
                "next_action": "compare_host_and_container_socket_visibility_then_recreate_mount_if_needed",
            }
        if not self.socket_path.is_socket():
            return {
                "ok": False,
                "status": "BLOCKED",
                "failure_family": "BROKER_SOCKET_PATH_INVALID",
                "blocker": f"Broker-Pfad existiert, ist aber kein Unix-Socket: {self.socket_path}",
                "socket_path": str(self.socket_path),
                "next_action": "remove_only_the_invalid_runtime_path_then_restart_broker",
            }
        return None

    def status(self) -> dict[str, Any]:
        """Probe the broker control plane while preserving precise failure-family evidence."""
        return self.call("broker_health", {}, timeout=min(self.timeout, 5.0))

    def command_status(self, request_id: str) -> dict[str, Any]:
        """Read one queued host-command result without resubmitting the mutation."""
        return self.command_queue.status(request_id)

    def call(self, action: str, arguments: dict[str, Any] | None = None, *, timeout: float | None = None) -> dict[str, Any]:
        if is_mutating_action(action):
            return self.command_queue.submit(
                action,
                arguments,
                timeout=float(timeout or self.timeout),
            )
        request_id = uuid.uuid4().hex
        payload = json.dumps(
            {"request_id": request_id, "action": action, "arguments": arguments or {}},
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        if len(payload) > MAX_BROKER_REQUEST_BYTES:
            raise ValueError("Broker-Anfrage ist größer als 1,2 MB")
        contract_failure = self._socket_contract_failure()
        if contract_failure is not None:
            return contract_failure

        chunks: list[bytes] = []
        size = 0
        try:
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
                    if size > MAX_BROKER_RESPONSE_BYTES:
                        raise RuntimeError("Broker-Antwort ist zu groß")
                    if b"\n" in chunk:
                        break
        except PermissionError:
            return {
                "ok": False,
                "status": "BLOCKED",
                "failure_family": "BROKER_SOCKET_PERMISSION_DENIED",
                "blocker": "Broker-Socket ist sichtbar, aber für den MCP-Prozess nicht zugreifbar",
                "socket_path": str(self.socket_path),
                "next_action": "verify_sovereign_mcp_group_gid_and_container_group_add",
            }
        except ConnectionRefusedError:
            return {
                "ok": False,
                "status": "BLOCKED",
                "failure_family": "BROKER_SOCKET_CONNECTION_REFUSED",
                "blocker": "Broker-Socket ist sichtbar, aber kein Broker nimmt Verbindungen an",
                "socket_path": str(self.socket_path),
                "next_action": "restart_broker_and_verify_broker_health_action",
            }
        except FileNotFoundError:
            return {
                "ok": False,
                "status": "BLOCKED",
                "failure_family": "BROKER_SOCKET_DISAPPEARED",
                "blocker": "Broker-Socket verschwand zwischen Prüfung und Verbindungsaufbau",
                "socket_path": str(self.socket_path),
                "next_action": "stabilize_runtime_directory_then_retry_once",
            }
        except socket.timeout:
            return {
                "ok": False,
                "status": "BLOCKED",
                "failure_family": "BROKER_RPC_TIMEOUT",
                "blocker": "Broker nahm die Verbindung an, lieferte aber keine fristgerechte Antwort",
                "socket_path": str(self.socket_path),
                "next_action": "inspect_broker_journal_for_blocked_handler",
            }
        except OSError as exc:
            return {
                "ok": False,
                "status": "BLOCKED",
                "failure_family": "BROKER_RPC_UNAVAILABLE",
                "blocker": f"Broker-RPC ist nicht verfügbar: {exc}",
                "socket_path": str(self.socket_path),
                "next_action": "collect_broker_service_and_socket_runtime_evidence",
            }

        raw = b"".join(chunks).split(b"\n", 1)[0]
        if not raw:
            return {
                "ok": False,
                "status": "BLOCKED",
                "failure_family": "BROKER_RPC_EMPTY_RESPONSE",
                "blocker": "Broker schloss die Verbindung ohne Antwort",
                "socket_path": str(self.socket_path),
                "next_action": "inspect_broker_handler_exception_and_restart_once",
            }
        try:
            response = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {
                "ok": False,
                "status": "BLOCKED",
                "failure_family": "BROKER_RPC_INVALID_RESPONSE",
                "blocker": "Broker lieferte keine gültige JSON-Antwort",
                "socket_path": str(self.socket_path),
                "next_action": "inspect_broker_protocol_version_and_handler_logs",
            }
        if response.get("request_id") != request_id:
            return {
                "ok": False,
                "status": "BLOCKED",
                "failure_family": "BROKER_RPC_REQUEST_MISMATCH",
                "blocker": "Broker-Antwort gehört nicht zur gesendeten Anfrage",
                "socket_path": str(self.socket_path),
                "next_action": "restart_broker_to_clear_stale_connection_state",
            }
        result = response.get("result")
        if not isinstance(result, dict):
            return {
                "ok": False,
                "status": "BLOCKED",
                "failure_family": "BROKER_RPC_RESULT_MISSING",
                "blocker": "Broker-Antwort enthält kein Ergebnisobjekt",
                "socket_path": str(self.socket_path),
                "next_action": "inspect_broker_dispatch_contract",
            }
        return result
