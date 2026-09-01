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
