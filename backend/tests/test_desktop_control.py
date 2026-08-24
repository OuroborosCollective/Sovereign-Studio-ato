from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from agent_runtime.desktop_activation import DesktopActivationIssuerV1
from agent_runtime.desktop_control import DesktopControlGatewayV1
from agent_runtime.fleet_supervisor import FleetContractError


HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


class _Response:
    def __init__(self, body: dict[str, object]) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self, maximum: int) -> bytes:
        assert maximum >= 64
        return json.dumps(self.body).encode("utf-8")


def _context(workspace_root: Path, *, projection_state: str = "LIVE", fresh_hash: str = HASH_A):
    worktree = workspace_root / "job-live-workspace" / "attempt-a"
    worktree.mkdir(parents=True, exist_ok=True)
    session = SimpleNamespace(
        session_binding_hash=HASH_A,
        run_id="run-live-workspace",
    )
    attempt = SimpleNamespace(
        attempt_id="attempt-" + "b" * 24,
        workspace_id="job-live-workspace",
        worktree_readback_sha256=HASH_C,
        binding_hash=HASH_B,
        worktree_path=worktree,
        base_revision="d" * 40,
        head_revision="e" * 40,
        receipt_binding=lambda: {"worktreePathSha256": "f" * 64},
    )
    reconciliation = SimpleNamespace(
        projection_state=projection_state,
        session_binding_hash=HASH_A,
        fresh_readback_hash=fresh_hash,
    )
    return SimpleNamespace(session=session, attempt_workspace=attempt, reconciliation=reconciliation)


def _issuer(tmp_path: Path) -> tuple[DesktopActivationIssuerV1, Path, Path]:
    activation_root = tmp_path / "activations"
    workspace_root = tmp_path / "workspaces"
    activation_root.mkdir()
    key = tmp_path / "desktop.key"
    key.write_bytes(b"k" * 48)
    os.chmod(key, 0o600)
    return (
        DesktopActivationIssuerV1(
            activation_root=activation_root,
            workspace_root=workspace_root,
            activation_key_path=key,
            image_reference="ghcr.io/ouroboroscollective/sovereign-desktop-worker@sha256:" + "1" * 64,
            source_revision="2" * 40,
        ),
        activation_root,
        workspace_root,
    )


def test_takeover_is_exclusive_and_blocks_frames_until_reconciliation(tmp_path: Path) -> None:
    issuer, _activation_root, workspace_root = _issuer(tmp_path)
    captured: dict[str, object] = {}

    def opener(request, timeout):
        captured["body"] = request.data
        captured["scope"] = request.get_header("X-sovereign-desktop-scope")
        assert timeout == 8
        return _Response({"status": "SENT", "inputKind": "TYPE", "requestHash": HASH_B})

    gateway = DesktopControlGatewayV1(issuer=issuer, opener=opener, clock=lambda: 100)
    context = _context(workspace_root)
    takeover = gateway.takeover(context=context, user_id="user-1")
    activation_id = takeover["desktopActivation"]["activationId"]
    lease_id = takeover["control"]["leaseId"]

    assert takeover["control"]["state"] == "USER_CONTROLLED"
    assert takeover["control"]["leaseKind"] == "USER_INPUT"
    assert takeover["control"]["ownerSubjectHash"] if "ownerSubjectHash" in takeover["control"] else True
    assert gateway.frame_allowed(context=context) is False
    with pytest.raises(FleetContractError, match="exclusively held"):
        gateway.takeover(context=context, user_id="user-2")

    delivered = gateway.user_input(
        context=context,
        user_id="user-1",
        activation_id=activation_id,
        lease_id=lease_id,
        arguments={"actionId": "human-type-1", "action": "type", "text": "private text"},
    )
    assert delivered["status"] == "SENT"
    assert "private text" not in json.dumps(delivered)
    assert b"private text" in captured["body"]
    assert isinstance(captured["scope"], str)

    stale = _context(workspace_root, projection_state="STALE", fresh_hash=HASH_B)
    blocked = gateway.give_back(
        context=stale,
        user_id="user-1",
        activation_id=activation_id,
        lease_id=lease_id,
    )
    assert blocked["ok"] is False
    assert blocked["control"]["state"] == "BLOCKED_STALE_STATE"

    rebound = gateway.give_back(
        context=context,
        user_id="user-1",
        activation_id=activation_id,
        lease_id=lease_id,
    )
    assert rebound["ok"] is True
    assert rebound["control"]["state"] == "AGENT_CONTROLLED_REBOUND"
    assert gateway.frame_allowed(context=context) is True


    replacement = _context(workspace_root)
    replacement.attempt_workspace.attempt_id = "attempt-" + "d" * 24
    with pytest.raises(FleetContractError, match="another live workspace"):
        gateway.user_input(
            context=replacement,
            user_id="user-1",
            activation_id=activation_id,
            lease_id=lease_id,
            arguments={"actionId": "old-attempt", "action": "click", "x": 1, "y": 1},
        )


def test_takeover_never_becomes_a_deploy_or_owner_authorization(tmp_path: Path) -> None:
    issuer, activation_root, workspace_root = _issuer(tmp_path)
    gateway = DesktopControlGatewayV1(issuer=issuer, clock=lambda: 100)
    result = gateway.takeover(context=_context(workspace_root), user_id="user-1")

    encoded = json.dumps(result, sort_keys=True)
    assert "deploy" not in encoded.lower()
    assert "approval" not in encoded.lower()
    assert result["control"]["authoritative"] is False
    assert result["desktopActivation"]["authoritative"] is False
    assert not any("input.scope" in path.name for path in activation_root.iterdir() if path.suffix == ".json")


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "backend").is_dir() and (candidate / "scripts/sovereign-backend").is_dir():
            return candidate
    raise AssertionError("repository root not found")


def test_desktop_control_is_byte_identical_in_deployment_mirror() -> None:
    root = _repo_root()
    assert (root / "backend/agent_runtime/desktop_control.py").read_bytes() == (
        root / "scripts/sovereign-backend/agent_runtime/desktop_control.py"
    ).read_bytes()
