from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys

import pytest

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from agent_runtime.desktop_activation import DesktopActivationHandleV1
from agent_runtime.desktop_projection import DesktopFrameProxyV1
from agent_runtime.fleet_supervisor import stable_hash


class _Response:
    def __init__(self, content: bytes, content_type: str = "image/png") -> None:
        self._content = content
        self.headers = {"Content-Type": content_type}

    def read(self, _limit: int) -> bytes:
        return self._content

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _setup(tmp_path: Path):
    root = tmp_path / "activations"
    root.mkdir()
    activation_id = "a" * 64
    scope = "view-scope-value-000000000000000000000000000000000"
    scope_file = root / f"{activation_id}.view.scope"
    scope_file.write_text(scope, "utf-8")
    os.chmod(scope_file, 0o400)
    handle_payload = {
        "activationId": activation_id,
        "sessionBindingHash": "b" * 64,
        "attemptId": "attempt-" + "c" * 24,
        "workspaceId": "job-live-workspace",
        "worktreeIdentityHash": "d" * 64,
        "imageReference": "ghcr.io/ouroboroscollective/desktop@sha256:" + "e" * 64,
        "runtimeIdentityHash": "f" * 64,
    }
    handle = DesktopActivationHandleV1(
        activation_id=handle_payload["activationId"],
        session_binding_hash=handle_payload["sessionBindingHash"],
        attempt_id=handle_payload["attemptId"],
        workspace_id=handle_payload["workspaceId"],
        worktree_identity_hash=handle_payload["worktreeIdentityHash"],
        image_reference=handle_payload["imageReference"],
        runtime_identity_hash=handle_payload["runtimeIdentityHash"],
        handle_hash=stable_hash(handle_payload),
    )
    document = {
        "activationId": activation_id,
        "sessionBindingHash": handle.session_binding_hash,
        "viewScopeFile": scope_file.name,
        "viewScopeHash": hashlib.sha256(scope.encode("utf-8")).hexdigest(),
    }
    (root / f"{activation_id}.json").write_text(json.dumps(document), "utf-8")
    os.chmod(root / f"{activation_id}.json", 0o600)
    return root, handle, scope


def test_frame_proxy_uses_private_scope_and_returns_observation_only(tmp_path: Path) -> None:
    root, handle, scope = _setup(tmp_path)
    observed = {}

    def opener(request, timeout):
        observed["url"] = request.full_url
        observed["scope"] = request.headers.get("X-sovereign-desktop-scope")
        observed["timeout"] = timeout
        return _Response(b"\x89PNG\r\n\x1a\nframe")

    frame = DesktopFrameProxyV1(activation_root=root, opener=opener).frame(handle=handle)
    assert frame.content.startswith(b"\x89PNG")
    assert frame.observation()["targetEffectVerified"] is False
    assert frame.observation()["authoritative"] is False
    assert observed["scope"] == scope
    assert scope not in str(frame.observation())
    assert "sovereign-desktop-" in observed["url"]


def test_frame_proxy_rejects_tampered_scope_and_non_png_output(tmp_path: Path) -> None:
    root, handle, _ = _setup(tmp_path)
    document = root / f"{handle.activation_id}.json"
    raw = json.loads(document.read_text("utf-8"))
    raw["viewScopeHash"] = "0" * 64
    document.write_text(json.dumps(raw), "utf-8")
    with pytest.raises(Exception, match="scope"):
        DesktopFrameProxyV1(activation_root=root, opener=lambda *_args, **_kwargs: _Response(b"\x89PNG")).frame(handle=handle)
    second = tmp_path / "second"
    second.mkdir()
    root, handle, _ = _setup(second)
    with pytest.raises(Exception, match="frame response"):
        DesktopFrameProxyV1(activation_root=root, opener=lambda *_args, **_kwargs: _Response(b"not-a-png")).frame(handle=handle)


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "backend").is_dir() and (candidate / "scripts/sovereign-backend").is_dir():
            return candidate
    raise AssertionError("repository root not found")


def test_desktop_projection_is_byte_identical_in_deployment_mirror() -> None:
    root = _repo_root()
    assert (root / "backend/agent_runtime/desktop_projection.py").read_bytes() == (
        root / "scripts/sovereign-backend/agent_runtime/desktop_projection.py"
    ).read_bytes()
