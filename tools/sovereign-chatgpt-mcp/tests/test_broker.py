from __future__ import annotations

from pathlib import Path
import socket as stdlib_socket

from broker import BrokerRuntime
import broker_client
from broker_client import HostBrokerClient


def test_missing_broker_socket_is_a_precise_namespace_blocker(tmp_path: Path) -> None:
    client = HostBrokerClient(str(tmp_path / "missing.sock"))
    result = client.call("container_status", {"container": "sovereign-backend"})
    assert result["status"] == "BLOCKED"
    assert result["failure_family"] == "BROKER_SOCKET_PATH_ABSENT"
    assert result["next_action"] == "compare_host_and_container_socket_visibility_then_recreate_mount_if_needed"


def test_non_socket_broker_path_is_not_reported_as_missing(tmp_path: Path) -> None:
    path = tmp_path / "operator.sock"
    path.write_text("not a socket", "utf-8")
    result = HostBrokerClient(str(path)).status()
    assert result["status"] == "BLOCKED"
    assert result["failure_family"] == "BROKER_SOCKET_PATH_INVALID"


def test_empty_broker_response_is_classified_without_tool_crash(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "operator.sock"
    bound = stdlib_socket.socket(stdlib_socket.AF_UNIX, stdlib_socket.SOCK_STREAM)
    bound.bind(str(path))
    bound.close()

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def settimeout(self, timeout):
            return None

        def connect(self, target):
            return None

        def sendall(self, payload):
            return None

        def recv(self, size):
            return b""

    monkeypatch.setattr(broker_client.socket, "socket", lambda *args, **kwargs: FakeSocket())
    result = HostBrokerClient(str(path)).status()
    assert result["failure_family"] == "BROKER_RPC_EMPTY_RESPONSE"


def test_invalid_broker_json_is_classified_without_tool_crash(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "operator.sock"
    bound = stdlib_socket.socket(stdlib_socket.AF_UNIX, stdlib_socket.SOCK_STREAM)
    bound.bind(str(path))
    bound.close()

    class FakeSocket:
        delivered = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def settimeout(self, timeout):
            return None

        def connect(self, target):
            return None

        def sendall(self, payload):
            return None

        def recv(self, size):
            if self.delivered:
                return b""
            self.delivered = True
            return b"not-json\n"

    monkeypatch.setattr(broker_client.socket, "socket", lambda *args, **kwargs: FakeSocket())
    result = HostBrokerClient(str(path)).status()
    assert result["failure_family"] == "BROKER_RPC_INVALID_RESPONSE"


def test_broker_health_action_reports_real_process_liveness() -> None:
    result = BrokerRuntime().dispatch("broker_health", {})
    assert result["ok"] is True
    assert result["status"] == "BROKER_READY"
    assert isinstance(result["pid"], int)


def test_unknown_broker_action_is_blocked() -> None:
    runtime = BrokerRuntime()
    result = runtime.dispatch("shell", {"command": "rm -rf /"})
    assert result["status"] == "BLOCKED"
    assert "nicht freigegeben" in result["blocker"]


def test_non_allowlisted_container_is_blocked(monkeypatch) -> None:
    monkeypatch.delenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", raising=False)
    runtime = BrokerRuntime()
    result = runtime.dispatch("container_status", {"container": "unrelated-root-container"})
    assert result["status"] == "BLOCKED"
    assert "nicht freigegeben" in result["blocker"]


def test_openai_project_runtime_evidence_dispatch_is_read_only(monkeypatch) -> None:
    runtime = BrokerRuntime()
    monkeypatch.setattr(
        runtime.managed_compose,
        "openai_project_runtime_evidence",
        lambda: {
            "ok": True,
            "status": "OPENAI_PROJECT_RUNTIME_VERIFIED",
            "mutationPerformed": False,
            "secretValuesExposed": False,
        },
    )

    result = runtime.dispatch("openai_project_runtime_evidence", {})

    assert result["ok"] is True
    assert result["status"] == "OPENAI_PROJECT_RUNTIME_VERIFIED"
    assert result["mutationPerformed"] is False
    assert result["secretValuesExposed"] is False


def test_patchmon_read_dispatch_is_allowlisted(monkeypatch) -> None:
    runtime = BrokerRuntime()
    monkeypatch.setattr(
        runtime.patchmon,
        "brain_snapshot",
        lambda **kwargs: {
            "ok": True,
            "status": "PATCHMON_BRAIN_READY",
            "includeFleet": kwargs.get("include_fleet"),
            "mutationPerformed": False,
            "secretValuesExposed": False,
        },
    )

    result = runtime.dispatch("patchmon_brain_snapshot", {"include_fleet": False})

    assert result["status"] == "PATCHMON_BRAIN_READY"
    assert result["includeFleet"] is False
    assert result["mutationPerformed"] is False


def test_patchmon_mutation_is_forbidden_on_inbound_broker_socket(monkeypatch) -> None:
    runtime = BrokerRuntime()
    monkeypatch.setattr(
        runtime.patchmon,
        "patch_action_apply",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not execute")),
    )

    result = runtime.dispatch(
        "patchmon_patch_action_apply",
        {"action": "approve_run", "confirmation_sha256": "a" * 64},
    )

    assert result["status"] == "BLOCKED"
    assert result["failure_family"] == "INBOUND_MUTATION_FORBIDDEN"


def test_patchmon_mutation_is_submitted_to_host_command_queue(monkeypatch, tmp_path: Path) -> None:
    client = HostBrokerClient(
        str(tmp_path / "socket-is-not-used.sock"),
        queue_root=str(tmp_path / "queue"),
    )
    observed = {}

    def submit(action, arguments, timeout):
        observed.update(action=action, arguments=arguments, timeout=timeout)
        return {"ok": True, "status": "IN_PROGRESS", "request_id": "request-1"}

    monkeypatch.setattr(client.command_queue, "submit", submit)
    result = client.call(
        "patchmon_patch_action_apply",
        {"action": "approve_run", "confirmation_sha256": "a" * 64},
        timeout=123,
    )

    assert result["status"] == "IN_PROGRESS"
    assert observed["action"] == "patchmon_patch_action_apply"
    assert observed["timeout"] == 123


def test_deploy_action_remains_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("SOVEREIGN_MCP_ENABLE_DEPLOY", raising=False)
    runtime = BrokerRuntime()
    result = runtime.dispatch(
        "deploy_verified_release",
        {
            "image_digest": "sha256:" + "a" * 64,
            "expected_revision": "b" * 40,
            "confirmation_revision": "b" * 40,
        },
    )
    assert result["status"] == "BLOCKED"
