from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy/reconcile-main-release.py"
INSTALLER = ROOT / "deploy/install-on-vps.sh"


def _load():
    spec = importlib.util.spec_from_file_location(
        "coordinated_release_reconciler_diagnostic_contract", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_outer_installer_projects_only_bounded_nested_toolchain_failure() -> None:
    syntax = subprocess.run(
        ["bash", "-n", str(INSTALLER)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert syntax.returncode == 0, syntax.stderr
    installer = INSTALLER.read_text("utf-8")

    assert "TOOLCHAIN_FAILURE_DIAGNOSTIC=" in installer
    assert (
        "^SOVEREIGN_TOOLCHAIN_INSTALL_FAILURE stage=[a-z][a-z0-9_-]{0,79} "
        "reason_sha256=[0-9a-f]{64} rollback=(not-required|verified|failed)$"
    ) in installer
    assert (
        'fail "revision-bound toolchain installer failed: '
        '$TOOLCHAIN_FAILURE_DIAGNOSTIC output_sha256=$TOOLCHAIN_FAILURE_SHA256"'
    ) in installer
    assert "cut -c1-512" in installer


def test_nested_toolchain_diagnostic_pattern_rejects_raw_reason(tmp_path: Path) -> None:
    log = tmp_path / "toolchain.log"
    valid = (
        "SOVEREIGN_TOOLCHAIN_INSTALL_FAILURE stage=metadata "
        + "reason_sha256="
        + "a" * 64
        + " rollback=not-required"
    )
    raw = valid + " reason=do-not-project-this"
    log.write_text(raw + "\n" + valid + "\n", encoding="utf-8")

    completed = subprocess.run(
        [
            "grep",
            "-E",
            r"^SOVEREIGN_TOOLCHAIN_INSTALL_FAILURE stage=[a-z][a-z0-9_-]{0,79} reason_sha256=[0-9a-f]{64} rollback=(not-required|verified|failed)$",
            str(log),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.splitlines() == [valid]
    assert "do-not-project-this" not in completed.stdout


def test_current_installer_failure_projects_toolchain_rollback_without_raw_reason(
    monkeypatch,
) -> None:
    module = _load()
    raw_reason = "private-installer-runtime-detail"
    completed = subprocess.CompletedProcess(
        ["install"],
        1,
        "",
        (
            "install blocked: stage=verify_mcp_tool_surface_preservation exit=1 "
            f"reason={raw_reason} rollback_attempted=1 toolchain_rollback=verified\n"
        ),
    )
    monkeypatch.setattr(module, "_run", lambda *_args, **_kwargs: completed)

    with pytest.raises(module.ReconcileError) as caught:
        module._command_json(["install"], timeout=10, stage="mcp_deploy")

    evidence = caught.value.safe_evidence
    assert evidence["installerDiagnostic"] == {
        "stage": "verify_mcp_tool_surface_preservation",
        "failureReasonSha256": hashlib.sha256(raw_reason.encode("utf-8")).hexdigest(),
        "rollbackAttempted": True,
        "toolchainRollback": "verified",
    }
    serialized = json.dumps(evidence, sort_keys=True)
    assert raw_reason not in serialized
    assert raw_reason not in caught.value.detail


def test_current_nested_toolchain_format_projects_only_bounded_inner_evidence(monkeypatch) -> None:
    module = _load()
    output_sha256 = "a" * 64
    reason_sha256 = "b" * 64
    bounded_reason = (
        "revision-bound toolchain installer failed: "
        "SOVEREIGN_TOOLCHAIN_INSTALL_FAILURE stage=metadata "
        f"reason_sha256={reason_sha256} rollback=verified output_sha256={output_sha256}"
    )
    completed = subprocess.CompletedProcess(
        ["install"],
        1,
        "",
        (
            "install blocked: stage=install_revision_bound_toolchain exit=1 "
            f"reason={bounded_reason} rollback_attempted=1 toolchain_rollback=not-required\n"
        ),
    )
    monkeypatch.setattr(module, "_run", lambda *_args, **_kwargs: completed)

    with pytest.raises(module.ReconcileError) as caught:
        module._command_json(["install"], timeout=10, stage="mcp_deploy")

    diagnostic = caught.value.safe_evidence["installerDiagnostic"]
    assert diagnostic["toolchainFailure"] == {
        "stage": "metadata",
        "failureReasonSha256": reason_sha256,
        "rollback": "verified",
        "outputSha256": output_sha256,
    }
    assert diagnostic["toolchainRollback"] == "not-required"
    assert diagnostic["failureReasonSha256"] == hashlib.sha256(
        bounded_reason.encode("utf-8")
    ).hexdigest()


def test_current_nested_toolchain_format_rejects_unknown_inner_rollback(monkeypatch) -> None:
    module = _load()
    bounded_reason = (
        "revision-bound toolchain installer failed: "
        "SOVEREIGN_TOOLCHAIN_INSTALL_FAILURE stage=metadata "
        f"reason_sha256={'b' * 64} rollback=unknown output_sha256={'a' * 64}"
    )
    completed = subprocess.CompletedProcess(
        ["install"],
        1,
        "",
        (
            "install blocked: stage=install_revision_bound_toolchain exit=1 "
            f"reason={bounded_reason} rollback_attempted=1 toolchain_rollback=not-required\n"
        ),
    )
    monkeypatch.setattr(module, "_run", lambda *_args, **_kwargs: completed)

    with pytest.raises(module.ReconcileError) as caught:
        module._command_json(["install"], timeout=10, stage="mcp_deploy")

    diagnostic = caught.value.safe_evidence["installerDiagnostic"]
    assert "toolchainFailure" not in diagnostic


@pytest.mark.parametrize("rollback_state", ["not-required", "verified", "failed"])
def test_installer_diagnostic_accepts_only_bounded_toolchain_rollback_states(
    monkeypatch,
    rollback_state: str,
) -> None:
    module = _load()
    completed = subprocess.CompletedProcess(
        ["install"],
        1,
        "",
        (
            "install blocked: stage=replace_mcp_container exit=1 "
            "reason=bounded-detail rollback_attempted=1 "
            f"toolchain_rollback={rollback_state}\n"
        ),
    )
    monkeypatch.setattr(module, "_run", lambda *_args, **_kwargs: completed)

    with pytest.raises(module.ReconcileError) as caught:
        module._command_json(["install"], timeout=10, stage="mcp_deploy")

    assert caught.value.safe_evidence["installerDiagnostic"]["toolchainRollback"] == rollback_state


def test_installer_diagnostic_rejects_unknown_toolchain_rollback_state(
    monkeypatch,
) -> None:
    module = _load()
    completed = subprocess.CompletedProcess(
        ["install"],
        1,
        "",
        (
            "install blocked: stage=replace_mcp_container exit=1 "
            "reason=bounded-detail rollback_attempted=1 toolchain_rollback=unknown\n"
        ),
    )
    monkeypatch.setattr(module, "_run", lambda *_args, **_kwargs: completed)

    with pytest.raises(module.ReconcileError) as caught:
        module._command_json(["install"], timeout=10, stage="mcp_deploy")

    assert "installerDiagnostic" not in caught.value.safe_evidence
