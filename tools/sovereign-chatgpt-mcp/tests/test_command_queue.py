from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from broker import BrokerRuntime
from broker_client import HostBrokerClient
from command_queue import HostCommandQueueClient
from command_worker import HostCommandWorker


class _FakeRuntime:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], str]] = []

    def dispatch(self, action, arguments, *, execution_origin="socket"):
        self.calls.append((action, arguments, execution_origin))
        return {
            "ok": True,
            "status": "HOST_WORKER_READY",
            "execution_origin": execution_origin,
        }


def _process_until_claimed(worker: HostCommandWorker, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if worker.process_once():
            return
        time.sleep(0.01)


def test_direct_inbound_mutation_is_blocked_but_host_worker_origin_is_allowed() -> None:
    runtime = BrokerRuntime()

    blocked = runtime.dispatch("host_worker_canary", {})
    assert blocked["status"] == "BLOCKED"
    assert blocked["failure_family"] == "INBOUND_MUTATION_FORBIDDEN"

    allowed = runtime.dispatch("host_worker_canary", {}, execution_origin="host_worker")
    assert allowed["ok"] is True
    assert allowed["status"] == "HOST_WORKER_READY"
    assert allowed["execution_origin"] == "host_worker"


def test_mutation_roundtrip_is_claimed_and_executed_by_host_worker(tmp_path: Path) -> None:
    runtime = _FakeRuntime()
    worker = HostCommandWorker(str(tmp_path), runtime=runtime)
    client = HostCommandQueueClient(str(tmp_path))

    thread = threading.Thread(target=_process_until_claimed, args=(worker,))
    thread.start()
    result = client.submit("host_worker_canary", {}, timeout=2)
    thread.join(timeout=2)

    assert result["status"] == "HOST_WORKER_READY"
    assert runtime.calls == [("host_worker_canary", {}, "host_worker")]
    assert not list((tmp_path / "inbox").glob("*.json"))
    assert not list((tmp_path / "outbox").glob("*.json"))


def test_broker_client_routes_mutation_to_queue_without_using_socket(tmp_path: Path) -> None:
    runtime = _FakeRuntime()
    worker = HostCommandWorker(str(tmp_path / "queue"), runtime=runtime)
    client = HostBrokerClient(
        socket_path=str(tmp_path / "missing.sock"),
        queue_root=str(tmp_path / "queue"),
        timeout=2,
    )

    thread = threading.Thread(target=_process_until_claimed, args=(worker,))
    thread.start()
    mutation = client.call("host_worker_canary", {}, timeout=2)
    thread.join(timeout=2)
    read = client.call("container_status", {"container": "sovereign-backend"})

    assert mutation["status"] == "HOST_WORKER_READY"
    assert read["failure_family"] == "BROKER_SOCKET_PATH_ABSENT"


def test_timeout_before_worker_claim_cancels_without_late_execution(tmp_path: Path) -> None:
    client = HostCommandQueueClient(str(tmp_path))

    result = client.submit("host_worker_canary", {}, timeout=0.1)

    assert result["status"] == "CANCELLED"
    assert result["failure_family"] == "HOST_COMMAND_QUEUE_TIMEOUT_BEFORE_CLAIM"
    assert not list((tmp_path / "inbox").glob("*.json"))


def test_orphaned_processing_job_is_not_reexecuted_after_worker_restart(tmp_path: Path) -> None:
    client = HostCommandQueueClient(str(tmp_path))
    client._ensure_paths()
    request_id = "a" * 32
    processing = tmp_path / "processing" / f"{request_id}.json"
    processing.write_text(
        '{"version":1,"request_id":"' + request_id + '","action":"host_worker_canary","arguments":{}}\n',
        "utf-8",
    )

    assert client.status(request_id)["status"] == "IN_PROGRESS"
    assert HostCommandWorker(str(tmp_path), runtime=_FakeRuntime()).process_once() is True
    result = client.status(request_id)

    assert result["status"] == "UNKNOWN"
    assert result["failure_family"] == "HOST_COMMAND_OUTCOME_UNCERTAIN_AFTER_WORKER_RESTART"


def test_queue_root_symlink_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "queue-link"
    link.symlink_to(target, target_is_directory=True)

    with pytest.raises(RuntimeError, match="darf kein Symlink sein"):
        HostCommandQueueClient(str(link)).submit("host_worker_canary", {}, timeout=1)


def test_server_exposes_queue_status_without_resubmission() -> None:
    import server

    assert callable(server.mcp_host_command_status)
    assert callable(server.broker.command_status)


def test_queue_rejects_non_mutating_or_unknown_actions(tmp_path: Path) -> None:
    client = HostCommandQueueClient(str(tmp_path))

    with pytest.raises(ValueError, match="nur mutierende allowlistete Aktionen"):
        client.submit("container_status", {}, timeout=1)
    with pytest.raises(ValueError, match="nur mutierende allowlistete Aktionen"):
        client.submit("shell", {"command": "false"}, timeout=1)
