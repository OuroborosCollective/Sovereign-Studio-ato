from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parents[1]
ENTRYPOINT = ROOT / "deploy/run-coordinated-release-readback.py"
BOOTSTRAP_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/sovereign-release-readback-bootstrap.yml"


def _load_entrypoint():
    spec = importlib.util.spec_from_file_location("runtime_readback_bootstrap_protocol", ENTRYPOINT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _scope() -> dict[str, object]:
    return {
        "revision": "a" * 40,
        "releaseGateRunId": 123456,
        "backendDigest": "sha256:" + "b" * 64,
        "mcpDigest": "sha256:" + "c" * 64,
        "manifestEvidenceSha256": "d" * 64,
    }


def _stdin(payload: bytes) -> io.TextIOWrapper:
    return io.TextIOWrapper(io.BytesIO(payload), encoding="utf-8")


def test_forced_readback_accepts_legacy_two_line_framing(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_entrypoint()
    token = "ghs_ephemeral_runtime_token_abcdefghijklmnopqrstuvwxyz"
    payload = json.dumps(_scope(), separators=(",", ":")).encode() + b"\n" + token.encode() + b"\n"
    monkeypatch.setattr(sys, "stdin", _stdin(payload))
    scope, observed_token, username = module._read_input()
    assert scope["revision"] == "a" * 40
    assert observed_token == token
    assert username == "OuroborosCollective"


def test_forced_readback_accepts_current_three_line_framing(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_entrypoint()
    token = "ghs_ephemeral_runtime_token_abcdefghijklmnopqrstuvwxyz"
    payload = (
        json.dumps(_scope(), separators=(",", ":")).encode()
        + b"\n"
        + token.encode()
        + b"\nOuroborosCollective\n"
    )
    monkeypatch.setattr(sys, "stdin", _stdin(payload))
    _scope_value, observed_token, username = module._read_input()
    assert observed_token == token
    assert username == "OuroborosCollective"


def test_forced_readback_rejects_unbounded_extra_framing(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_entrypoint()
    token = "ghs_ephemeral_runtime_token_abcdefghijklmnopqrstuvwxyz"
    payload = (
        json.dumps(_scope(), separators=(",", ":")).encode()
        + b"\n"
        + token.encode()
        + b"\nOuroborosCollective\nunexpected\n"
    )
    monkeypatch.setattr(sys, "stdin", _stdin(payload))
    with pytest.raises(module.ReadbackError, match="input framing is invalid"):
        module._read_input()


def test_control_plane_bootstrap_is_manual_hash_bound_and_container_free() -> None:
    workflow = BOOTSTRAP_WORKFLOW.read_text("utf-8")
    assert "workflow_dispatch:" in workflow
    assert "push:" not in workflow
    assert "EXPECTED_REVISION: ${{ inputs.expected_revision }}" in workflow
    assert "SOURCE_REVISION_IS_NOT_CURRENT_MAIN" in workflow
    assert "KNOWN_PREVIOUS_REVISION: 738c0ac6616b2b2fadfd554706ac678c90e80e7a" in workflow
    assert "UNEXPECTED_READBACK_ENTRYPOINT_HASH" in workflow
    assert "/opt/sovereign-chatgpt-tools/bin/run-coordinated-release-readback" in workflow
    assert "containersChanged': False" in workflow
    assert "servicesRestarted': False" in workflow
    assert "authorizedKeysChanged': False" in workflow
    assert "deploy/install-on-vps.sh" not in workflow
    assert "docker restart" not in workflow
    assert "docker run" not in workflow
    assert "systemctl restart" not in workflow
    assert "packages: write" not in workflow
    assert "deployments: write" not in workflow
