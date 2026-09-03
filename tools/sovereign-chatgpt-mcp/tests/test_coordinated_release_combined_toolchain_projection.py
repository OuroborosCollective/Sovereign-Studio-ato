from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy/reconcile-main-release.py"


def _load():
    spec = importlib.util.spec_from_file_location(
        "coordinated_release_combined_toolchain_projection", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _combined_reason(*, extra: str = "") -> str:
    return (
        "revision-bound toolchain installer failed: "
        "SOVEREIGN_TOOLCHAIN_INSTALL_FAILURE stage=stage "
        + "reason_sha256="
        + "a" * 64
        + " rollback=failed "
        "SOVEREIGN_TOOLCHAIN_UV_DIAGNOSTIC family=OTHER "
        "uv_version=0.11.26 output_sha256="
        + "b" * 64
        + extra
        + " SOVEREIGN_TOOLCHAIN_ROLLBACK_FAILURE operation=rollback reason_sha256="
        + "c" * 64
        + " output_sha256="
        + "d" * 64
    )


def test_combined_uv_and_rollback_diagnostics_are_projected_without_raw_reason() -> None:
    module = _load()

    diagnostic = module._safe_nested_toolchain_diagnostic(_combined_reason())

    assert diagnostic == {
        "stage": "stage",
        "reasonSha256": "a" * 64,
        "rollback": "failed",
        "outputSha256": "d" * 64,
        "uv": {
            "family": "OTHER",
            "version": "0.11.26",
            "outputSha256": "b" * 64,
        },
        "rollbackFailure": {
            "operation": "rollback",
            "reasonSha256": "c" * 64,
        },
    }


def test_combined_projection_still_rejects_unallowlisted_tail() -> None:
    module = _load()

    diagnostic = module._safe_nested_toolchain_diagnostic(
        _combined_reason(extra=" raw=must-not-project")
    )

    assert diagnostic is None
