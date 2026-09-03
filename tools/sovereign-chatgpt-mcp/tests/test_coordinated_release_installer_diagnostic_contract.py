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
    assert "TOOLCHAIN_UV_DIAGNOSTIC=" in installer
    assert (
        "^SOVEREIGN_TOOLCHAIN_INSTALL_FAILURE stage=[a-z][a-z0-9_-]{0,79} "
        "reason_sha256=[0-9a-f]{64} rollback=(not-required|verified|failed)$"
    ) in installer
    assert (
        "^SOVEREIGN_TOOLCHAIN_UV_DIAGNOSTIC family=(CLI_COMPATIBILITY|LOCK_DRIFT|STORAGE|PERMISSION|BUILD_SYSTEM|CACHE_IO|RESOLUTION|PYTHON|NETWORK|OTHER) "
        "uv_version=([0-9]+\\.[0-9]+\\.[0-9]+|unknown) output_sha256=[0-9a-f]{64}$"
    ) in installer
    assert (
        'fail "revision-bound toolchain installer failed: '
        '$TOOLCHAIN_FAILURE_DIAGNOSTIC $TOOLCHAIN_UV_DIAGNOSTIC '
        'output_sha256=$TOOLCHAIN_FAILURE_SHA256"'
    ) in installer
    assert (
        'fail "revision-bound toolchain installer failed: '
        '$TOOLCHAIN_FAILURE_DIAGNOSTIC output_sha256=$TOOLCHAIN_FAILURE_SHA256"'
    ) in installer
    assert "head -n 1" in installer
    assert '"$TOOLCHAIN_INSTALL_LOG" | tail -n 1' not in installer
    assert "cut -c1-512" in installer


def test_outer_installer_preserves_first_nested_failure_when_err_propagates(tmp_path: Path) -> None:
    log = tmp_path / "toolchain.log"
    deepest = (
        "SOVEREIGN_TOOLCHAIN_INSTALL_FAILURE stage=stage "
        + "reason_sha256="
        + "a" * 64
        + " rollback=not-required"
    )
    parent = (
        "SOVEREIGN_TOOLCHAIN_INSTALL_FAILURE stage=stage "
        + "reason_sha256="
        + "b" * 64
        + " rollback=not-required"
    )
    log.write_text(deepest + "\n" + parent + "\n", encoding="utf-8")

    completed = subprocess.run(
        [
            "bash",
            "-c",
            "grep -E '^SOVEREIGN_TOOLCHAIN_INSTALL_FAILURE stage=[a-z][a-z0-9_-]{0,79} reason_sha256=[0-9a-f]{64} rollback=(not-required|verified|failed)$' \"$1\" | head -n 1 | tr -d '\\r\\n' | cut -c1-512",
            "bash",
            str(log),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == deepest
    assert parent not in completed.stdout


def test_nested_toolchain_uv_diagnostic_projects_only_bounded_fields(tmp_path: Path) -> None:
    log = tmp_path / "toolchain.log"
    valid = (
        "SOVEREIGN_TOOLCHAIN_UV_DIAGNOSTIC family=BUILD_SYSTEM "
        "uv_version=0.10.4 output_sha256=" + "c" * 64
    )
    raw = valid + " raw=do-not-project-this"
    log.write_text(raw + "\n" + valid + "\n", encoding="utf-8")

    completed = subprocess.run(
        [
            "grep",
            "-E",
            r"^SOVEREIGN_TOOLCHAIN_UV_DIAGNOSTIC family=(CLI_COMPATIBILITY|LOCK_DRIFT|STORAGE|PERMISSION|BUILD_SYSTEM|CACHE_IO|RESOLUTION|PYTHON|NETWORK|OTHER) uv_version=([0-9]+\.[0-9]+\.[0-9]+|unknown) output_sha256=[0-9a-f]{64}$",
            str(log),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.splitlines() == [valid]
    assert "do-not-project-this" not in completed.stdout


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
