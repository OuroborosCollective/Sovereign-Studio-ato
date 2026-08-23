from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

MCP_ROOT = Path(__file__).resolve().parents[1]
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

from command_contract import is_mutating_action
from desktop_worker import DesktopWorkerError, DesktopWorkerRuntime


def _write(path: Path, value: bytes, mode: int = 0o600) -> None:
    path.write_bytes(value)
    os.chmod(path, mode)


def _activation(tmp_path: Path) -> tuple[DesktopWorkerRuntime, str, dict]:
    activation_root = tmp_path / "activations"
    workspace_root = tmp_path / "workspaces"
    activation_root.mkdir()
    workspace = workspace_root / "job-live-workspace" / "attempt-a"
    workspace.mkdir(parents=True)
    view = activation_root / "view.scope"
    input_scope = activation_root / "input.scope"
    _write(view, b"view-scope-value")
    _write(input_scope, b"input-scope-value")
    activation_id = "a" * 64
    payload = {
        "activationId": activation_id,
        "sessionBindingHash": "b" * 64,
        "attemptId": "attempt-" + "c" * 24,
        "workspaceId": "job-live-workspace",
        "worktreeIdentityHash": "d" * 64,
        "workspaceRelativePath": "job-live-workspace/attempt-a",
        "workspacePathHash": hashlib.sha256(str(workspace.resolve()).encode("utf-8")).hexdigest(),
        "imageReference": "ghcr.io/ouroboroscollective/sovereign-desktop-worker@sha256:" + "e" * 64,
        "runtimeIdentityHash": "f" * 64,
        "sourceRevision": "1" * 40,
        "expectedBaseRevision": "2" * 40,
        "observedHeadRevision": "3" * 40,
        "viewScopeFile": view.name,
        "viewScopeHash": hashlib.sha256(view.read_bytes()).hexdigest(),
        "inputScopeFile": input_scope.name,
        "inputScopeHash": hashlib.sha256(input_scope.read_bytes()).hexdigest(),
        "cpuMillis": 1000,
        "memoryBytes": 1_073_741_824,
        "pidsLimit": 128,
        "wallTimeSeconds": 3600,
        "idleTimeoutSeconds": 900,
    }
    document = activation_root / f"{activation_id}.json"
    _write(document, json.dumps(payload).encode("utf-8"))
    return DesktopWorkerRuntime(activation_root=str(activation_root), workspace_root=str(workspace_root)), activation_id, payload


def test_desktop_worker_mutations_require_the_host_command_worker() -> None:
    assert is_mutating_action("desktop_worker_start") is True
    assert is_mutating_action("desktop_worker_input") is True
    assert is_mutating_action("desktop_worker_remove") is True
    assert is_mutating_action("desktop_worker_plan") is False
    assert is_mutating_action("desktop_worker_readback") is False
    assert is_mutating_action("desktop_worker_canary") is False


def test_desktop_worker_plan_redacts_host_paths_and_scope_values(tmp_path: Path) -> None:
    runtime, activation_id, payload = _activation(tmp_path)
    plan = runtime.plan(activation_id=activation_id)
    encoded = json.dumps(plan, sort_keys=True)
    assert plan["status"] == "PLANNED"
    assert plan["publishedPorts"] == []
    assert str(runtime.workspace_root / payload["workspaceRelativePath"]) not in encoded
    assert str(runtime.activation_root / payload["viewScopeFile"]) not in encoded
    assert "view-scope-value" not in encoded


def test_run_arguments_enforce_private_network_hardening_and_single_workspace_mount(tmp_path: Path) -> None:
    runtime, activation_id, _ = _activation(tmp_path)
    activation = runtime._load_activation(activation_id)
    argv = runtime._docker_run_argv(activation)
    rendered = " ".join(argv)
    assert "--network sovereign-desktop" in rendered
    assert "--read-only" in argv
    assert "--cap-drop ALL" in rendered
    assert "no-new-privileges:true" in rendered
    assert "--publish" not in argv
    assert "-p" not in argv
    assert "docker.sock" not in rendered
    assert "dst=/workspace" in rendered
    assert rendered.count("type=bind") == 3


def test_activation_rejects_escaping_workspace_and_unsafe_document_permissions(tmp_path: Path) -> None:
    runtime, activation_id, payload = _activation(tmp_path)
    payload["workspaceRelativePath"] = "../../etc"
    document = runtime.activation_root / f"{activation_id}.json"
    _write(document, json.dumps(payload).encode("utf-8"))
    with pytest.raises(DesktopWorkerError, match="relative path"):
        runtime.plan(activation_id=activation_id)
    payload["workspaceRelativePath"] = "job-live-workspace/attempt-a"
    _write(document, json.dumps(payload).encode("utf-8"), mode=0o644)
    with pytest.raises(DesktopWorkerError, match="mode"):
        runtime.plan(activation_id=activation_id)


def test_activation_rejects_shared_or_tampered_scope_material(tmp_path: Path) -> None:
    runtime, activation_id, payload = _activation(tmp_path)
    payload["inputScopeHash"] = payload["viewScopeHash"]
    document = runtime.activation_root / f"{activation_id}.json"
    _write(document, json.dumps(payload).encode("utf-8"))
    with pytest.raises(DesktopWorkerError, match="differ"):
        runtime.plan(activation_id=activation_id)
    second = tmp_path / "second"
    second.mkdir()
    runtime, activation_id, payload = _activation(second)
    (runtime.activation_root / payload["viewScopeFile"]).write_bytes(b"tampered")
    with pytest.raises(DesktopWorkerError, match="scope content"):
        runtime.plan(activation_id=activation_id)


def test_controller_input_is_bounded_host_only_and_redacts_typed_content(tmp_path: Path) -> None:
    runtime, activation_id, _ = _activation(tmp_path)
    runtime.readback = lambda **_kwargs: {"ok": True, "status": "OBSERVED"}  # type: ignore[method-assign]
    captured: dict[str, object] = {}

    def runner(argv, **kwargs):
        captured["argv"] = argv
        captured["input"] = kwargs.get("input")
        return SimpleNamespace(returncode=0, stdout='{"status":"SENT","inputKind":"TYPE","requestHash":"a"}')

    runtime._runner = runner  # type: ignore[assignment]
    result = runtime.controller_input(
        activation_id=activation_id,
        arguments={"action_id": "controller-1", "action": "type", "text": "private text"},
    )
    assert result == {
        "ok": True,
        "status": "SENT",
        "actionId": "controller-1",
        "inputKind": "TYPE",
        "requestHash": "a",
        "runtimeIdentityHash": "f" * 64,
        "targetEffectVerified": False,
        "authoritative": False,
    }
    assert "private text" not in json.dumps(result)
    assert "docker" in captured["argv"]
    assert "private text" in str(captured["input"])
    blocked = runtime.controller_input(
        activation_id=activation_id,
        arguments={"action_id": "controller-2", "action": "shell", "text": "id"},
    )
    assert blocked["status"] == "BLOCKED"
    assert blocked["failure_family"] == "DESKTOP_INPUT_ARGUMENT_INVALID"
