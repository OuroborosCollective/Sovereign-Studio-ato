from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy/reconcile-main-release.py"


def _load():
    spec = importlib.util.spec_from_file_location(
        "coordinated_release_reconciler_diagnostic_contract", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_nested_toolchain_failure_projects_only_bounded_inner_evidence(monkeypatch) -> None:
    module = _load()
    output_sha256 = "a" * 64
    reason_sha256 = "b" * 64
    bounded_reason = (
        "revision-bound toolchain installer failed: "
        f"output_sha256={output_sha256};"
        "toolchain_stage=readback;"
        f"toolchain_reason_sha256={reason_sha256};"
        "toolchain_rollback=verified"
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
        "stage": "readback",
        "failureReasonSha256": reason_sha256,
        "rollback": "verified",
        "outputSha256": output_sha256,
    }
    assert diagnostic["toolchainRollback"] == "not-required"
    assert diagnostic["failureReasonSha256"] == hashlib.sha256(
        bounded_reason.encode("utf-8")
    ).hexdigest()
    serialized = json.dumps(caught.value.safe_evidence, sort_keys=True)
    assert "SOVEREIGN_TOOLCHAIN_INSTALL_FAILURE" not in serialized
    assert "private-toolchain-runtime-detail" not in serialized


@pytest.mark.parametrize(
    "inner_suffix",
    [
        "toolchain_reason_sha256=not-a-hash;toolchain_rollback=verified",
        f"toolchain_reason_sha256={'b' * 64};toolchain_rollback=unknown",
    ],
)
def test_nested_toolchain_failure_rejects_unbounded_inner_fields(
    monkeypatch,
    inner_suffix: str,
) -> None:
    module = _load()
    reason = (
        "revision-bound toolchain installer failed: "
        f"output_sha256={'a' * 64};toolchain_stage=readback;{inner_suffix}"
    )
    completed = subprocess.CompletedProcess(
        ["install"],
        1,
        "",
        (
            "install blocked: stage=install_revision_bound_toolchain exit=1 "
            f"reason={reason} rollback_attempted=1 toolchain_rollback=not-required\n"
        ),
    )
    monkeypatch.setattr(module, "_run", lambda *_args, **_kwargs: completed)

    with pytest.raises(module.ReconcileError) as caught:
        module._command_json(["install"], timeout=10, stage="mcp_deploy")

    diagnostic = caught.value.safe_evidence["installerDiagnostic"]
    assert "toolchainFailure" not in diagnostic


def test_mcp_adapter_extracts_only_bounded_nested_toolchain_failure_fields() -> None:
    installer = (ROOT / "deploy/install-on-vps.sh").read_text("utf-8")
    nested_start = installer.index(
        'bash "$TOOLCHAIN_INSTALLER" "$TOOLCHAIN_SOURCE" >"$TOOLCHAIN_INSTALL_LOG" 2>&1'
    )
    nested_end = installer.index("TOOLCHAIN_ROLLBACK_ARMED=1", nested_start)
    nested_failure = installer[nested_start:nested_end]

    assert "SOVEREIGN_TOOLCHAIN_INSTALL_FAILURE" in nested_failure
    assert 'r"stage=([A-Za-z0-9_-]{1,80}) "' in nested_failure
    assert 'r"reason_sha256=([0-9a-f]{64}) "' in nested_failure
    assert 'r"rollback=(not-required|verified|failed)$"' in nested_failure
    assert "toolchain_reason_sha256=$TOOLCHAIN_FAILURE_REASON_SHA256" in nested_failure
    assert "toolchain_stage=$TOOLCHAIN_FAILURE_STAGE" in nested_failure
    assert "toolchain_rollback=$TOOLCHAIN_FAILURE_ROLLBACK" in nested_failure
    assert 'cat "$TOOLCHAIN_INSTALL_LOG"' not in nested_failure
    assert 'printf "%s" "$TOOLCHAIN_INSTALL_LOG"' not in nested_failure


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
