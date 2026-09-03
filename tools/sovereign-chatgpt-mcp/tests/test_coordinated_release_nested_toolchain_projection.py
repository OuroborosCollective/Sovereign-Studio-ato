from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy/reconcile-main-release.py"


def _load():
    spec = importlib.util.spec_from_file_location(
        "coordinated_release_nested_toolchain_projection", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _failure(reason: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        ["install"],
        1,
        "",
        (
            "install blocked: stage=install_revision_bound_toolchain exit=1 "
            f"reason={reason} rollback_attempted=1 toolchain_rollback=verified\n"
        ),
    )


def test_nested_uv_diagnostic_is_projected_without_raw_installer_detail(monkeypatch) -> None:
    module = _load()
    reason = (
        "revision-bound toolchain installer failed: "
        "SOVEREIGN_TOOLCHAIN_INSTALL_FAILURE stage=uv_sync "
        + "reason_sha256="
        + "a" * 64
        + " rollback=verified "
        "SOVEREIGN_TOOLCHAIN_UV_DIAGNOSTIC family=CLI_COMPATIBILITY "
        "uv_version=0.10.4 output_sha256="
        + "b" * 64
        + " output_sha256="
        + "c" * 64
    )
    monkeypatch.setattr(module, "_run", lambda *_args, **_kwargs: _failure(reason))

    with pytest.raises(module.ReconcileError) as caught:
        module._command_json(["install"], timeout=10, stage="mcp_deploy")

    diagnostic = caught.value.safe_evidence["installerDiagnostic"]
    assert diagnostic["toolchain"] == {
        "stage": "uv_sync",
        "reasonSha256": "a" * 64,
        "rollback": "verified",
        "outputSha256": "c" * 64,
        "uv": {
            "family": "CLI_COMPATIBILITY",
            "version": "0.10.4",
            "outputSha256": "b" * 64,
        },
    }
    assert reason not in str(caught.value.safe_evidence)
    assert reason not in caught.value.detail


def test_nested_rollback_diagnostic_is_projected_without_raw_reason(monkeypatch) -> None:
    module = _load()
    reason = (
        "revision-bound toolchain installer failed: "
        "SOVEREIGN_TOOLCHAIN_INSTALL_FAILURE stage=rollback_toolchain "
        + "reason_sha256="
        + "d" * 64
        + " rollback=failed "
        "SOVEREIGN_TOOLCHAIN_ROLLBACK_FAILURE operation=rollback reason_sha256="
        + "e" * 64
        + " output_sha256="
        + "f" * 64
    )
    monkeypatch.setattr(module, "_run", lambda *_args, **_kwargs: _failure(reason))

    with pytest.raises(module.ReconcileError) as caught:
        module._command_json(["install"], timeout=10, stage="mcp_deploy")

    assert caught.value.safe_evidence["installerDiagnostic"]["toolchain"] == {
        "stage": "rollback_toolchain",
        "reasonSha256": "d" * 64,
        "rollback": "failed",
        "outputSha256": "f" * 64,
        "rollbackFailure": {
            "operation": "rollback",
            "reasonSha256": "e" * 64,
        },
    }


def test_nested_toolchain_projection_rejects_unallowlisted_tail(monkeypatch) -> None:
    module = _load()
    raw_marker = "raw=must-not-project"
    reason = (
        "revision-bound toolchain installer failed: "
        "SOVEREIGN_TOOLCHAIN_INSTALL_FAILURE stage=uv_sync "
        + "reason_sha256="
        + "1" * 64
        + " rollback=verified "
        "SOVEREIGN_TOOLCHAIN_UV_DIAGNOSTIC family=NETWORK "
        "uv_version=0.10.4 output_sha256="
        + "2" * 64
        + f" {raw_marker} output_sha256="
        + "3" * 64
    )
    monkeypatch.setattr(module, "_run", lambda *_args, **_kwargs: _failure(reason))

    with pytest.raises(module.ReconcileError) as caught:
        module._command_json(["install"], timeout=10, stage="mcp_deploy")

    diagnostic = caught.value.safe_evidence["installerDiagnostic"]
    assert "toolchain" not in diagnostic
    assert raw_marker not in str(caught.value.safe_evidence)
    assert raw_marker not in caught.value.detail
