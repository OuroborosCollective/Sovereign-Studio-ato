from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from agent_runtime.desktop_activation import DesktopActivationIssuerV1
from agent_runtime.fleet_supervisor import FleetContractError


def _context(workspace_root: Path, *, projection_state: str = "LIVE"):
    worktree = workspace_root / "job-live-workspace" / "attempt-a"
    worktree.mkdir(parents=True)
    session = SimpleNamespace(
        session_binding_hash="a" * 64,
    )
    attempt = SimpleNamespace(
        attempt_id="attempt-" + "b" * 24,
        workspace_id="job-live-workspace",
        worktree_readback_sha256="c" * 64,
        binding_hash="d" * 64,
        worktree_path=worktree,
        base_revision="e" * 40,
        head_revision="f" * 40,
        receipt_binding=lambda: {"worktreePathSha256": "1" * 64},
    )
    return SimpleNamespace(session=session, attempt_workspace=attempt, reconciliation=SimpleNamespace(projection_state=projection_state))


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
            image_reference="ghcr.io/ouroboroscollective/sovereign-desktop-worker@sha256:" + "2" * 64,
            source_revision="3" * 40,
        ),
        activation_root,
        workspace_root,
    )


def test_issuer_creates_reusable_path_free_handle_for_exact_live_attempt(tmp_path: Path) -> None:
    issuer, activation_root, workspace_root = _issuer(tmp_path)
    context = _context(workspace_root)
    first = issuer.issue(context=context)
    second = issuer.issue(context=context)
    assert first == second
    public = first.to_dict()
    assert public["authoritative"] is False
    assert str(context.attempt_workspace.worktree_path) not in str(public)
    document = activation_root / f"{first.activation_id}.json"
    assert document.is_file()
    assert document.stat().st_mode & 0o077 == 0
    assert (activation_root / f"{first.activation_id}.view.scope").stat().st_mode & 0o077 == 0
    assert (activation_root / f"{first.activation_id}.input.scope").stat().st_mode & 0o077 == 0


def test_issuer_rejects_non_live_context_and_mutable_image(tmp_path: Path) -> None:
    issuer, _, workspace_root = _issuer(tmp_path)
    with pytest.raises(FleetContractError, match="live reconciled"):
        issuer.issue(context=_context(workspace_root, projection_state="STALE"))
    mutable = DesktopActivationIssuerV1(
        activation_root=issuer.activation_root,
        workspace_root=issuer.workspace_root,
        activation_key_path=issuer.activation_key_path,
        image_reference="ghcr.io/ouroboroscollective/sovereign-desktop-worker:latest",
        source_revision=issuer.source_revision,
    )
    with pytest.raises(FleetContractError, match="immutable"):
        mutable.issue(context=_context(workspace_root / "second"))


def test_issuer_rejects_worktree_outside_bound_workspace_root(tmp_path: Path) -> None:
    issuer, _, workspace_root = _issuer(tmp_path)
    workspace_root.mkdir()
    context = _context(tmp_path / "outside")
    with pytest.raises(FleetContractError, match="outside"):
        issuer.issue(context=context)


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "backend").is_dir() and (candidate / "scripts/sovereign-backend").is_dir():
            return candidate
    raise AssertionError("repository root not found")


def test_desktop_activation_is_byte_identical_in_deployment_mirror() -> None:
    root = _repo_root()
    assert (root / "backend/agent_runtime/desktop_activation.py").read_bytes() == (
        root / "scripts/sovereign-backend/agent_runtime/desktop_activation.py"
    ).read_bytes()
