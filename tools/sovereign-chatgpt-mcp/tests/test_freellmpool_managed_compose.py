from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from managed_compose import (
    FREELLMPOOL_CONTAINER,
    FREELLMPOOL_IMAGE,
    ManagedComposeRuntime,
    STACKS,
)


def _missing_runner(argv, **kwargs):
    return subprocess.CompletedProcess(argv, 1, "", "not found")


def test_legacy_free_aggregators_are_not_managed_stacks() -> None:
    assert "sovereign-freellmpool" not in STACKS
    assert "sovereign-omniroute" not in STACKS
    assert "sovereign-freellmapi" in STACKS


def test_omniroute_cannot_be_planned_or_deployed(tmp_path: Path) -> None:
    runtime = ManagedComposeRuntime(runner=_missing_runner, template_root=str(tmp_path))
    with pytest.raises(ValueError, match="nicht freigegeben"):
        runtime.plan("sovereign-omniroute")
    with pytest.raises(ValueError, match="nicht freigegeben"):
        runtime.deploy("sovereign-omniroute", "0" * 64)


def test_omniroute_template_is_an_inert_historical_tombstone() -> None:
    root = Path(__file__).resolve().parents[1] / "templates" / "sovereign-omniroute"
    template = (root / "docker-compose.yml").read_text("utf-8")

    assert "services: {}" in template
    assert "image:" not in template
    assert "container_name:" not in template
    assert "sovereign-omniroute-data" not in template


def test_legacy_freellmpool_retirement_is_identity_bound_and_preserves_image_volume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = ManagedComposeRuntime(runner=_missing_runner, template_root=str(tmp_path))
    states = iter([
        {
            "present": True,
            "project": "sovereign-freellmpool",
            "service": "freellmpool",
            "imageReference": FREELLMPOOL_IMAGE,
        },
        {"present": False, "container": FREELLMPOOL_CONTAINER},
    ])
    monkeypatch.setattr(runtime, "_inspect", lambda _container: next(states))
    calls: list[list[str]] = []

    def runner(argv, **kwargs):
        calls.append(argv)
        return {"ok": True, "exit_code": 0, "stdout": FREELLMPOOL_CONTAINER + "\n", "stderr": ""}

    monkeypatch.setattr(runtime, "_run", runner)
    result = runtime._retire_legacy_freellmpool()

    assert result["ok"] is True
    assert result["status"] == "FREELLMPOOL_RETIRED"
    assert result["containerRemoved"] is True
    assert result["imageRemoved"] is False
    assert result["volumeRemoved"] is False
    assert calls == [["docker", "rm", "--force", FREELLMPOOL_CONTAINER]]


def test_legacy_freellmpool_retirement_refuses_identity_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = ManagedComposeRuntime(runner=_missing_runner, template_root=str(tmp_path))
    monkeypatch.setattr(runtime, "_inspect", lambda _container: {
        "present": True,
        "project": "unexpected-project",
        "service": "freellmpool",
        "imageReference": FREELLMPOOL_IMAGE,
    })

    result = runtime._retire_legacy_freellmpool()

    assert result["ok"] is False
    assert result["status"] == "FREELLMPOOL_RETIREMENT_IDENTITY_MISMATCH"
    assert result["containerRemoved"] is False
