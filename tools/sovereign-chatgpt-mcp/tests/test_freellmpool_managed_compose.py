from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from managed_compose import (
    FREELLMPOOL_CONTAINER,
    FREELLMPOOL_IMAGE,
    OMNIROUTE_CONTAINER,
    OMNIROUTE_DATA_VOLUME,
    OMNIROUTE_IMAGE,
    ManagedComposeRuntime,
    STACKS,
)


def _missing_runner(argv, **kwargs):
    return subprocess.CompletedProcess(argv, 1, "", "not found")


def test_omniroute_replaces_freellmpool_in_managed_stack_allowlist() -> None:
    assert "sovereign-omniroute" in STACKS
    assert "sovereign-freellmpool" not in STACKS
    stack = STACKS["sovereign-omniroute"]
    assert stack.anchor_container == OMNIROUTE_CONTAINER
    assert stack.expected_containers == (OMNIROUTE_CONTAINER,)
    assert stack.allowed_services == ("omniroute",)
    assert stack.allowed_networks == ("sovereign-private",)


def test_omniroute_template_is_private_immutable_and_non_root() -> None:
    root = Path(__file__).resolve().parents[1] / "templates" / "sovereign-omniroute"
    template = (root / "docker-compose.yml").read_text("utf-8")

    assert OMNIROUTE_IMAGE in template
    assert 'container_name: sovereign-omniroute' in template
    assert 'user: "1000:1000"' in template
    assert "read_only: true" in template
    assert "privileged: false" in template
    assert "no-new-privileges:true" in template
    assert "cap_drop:" in template and "- ALL" in template
    assert "ports:" not in template
    assert "sovereign-private:" in template and "external: true" in template
    assert "sovereign-omniroute-data:/app/data" in template
    assert "healthcheck.mjs" in template
    assert "JWT_SECRET: ${JWT_SECRET}" in template
    assert "API_KEY_SECRET: ${API_KEY_SECRET}" in template
    assert "INITIAL_PASSWORD: ${INITIAL_PASSWORD}" in template
    assert "STORAGE_ENCRYPTION_KEY: ${STORAGE_ENCRYPTION_KEY}" in template
    assert "REQUIRE_API_KEY: ${REQUIRE_API_KEY:-false}" in template
    assert "TMPDIR: ${TMPDIR:-/app/data}" in template
    assert "/tmp:rw" not in template
    assert "tmpfs:" not in template
    assert "/var/run/docker.sock" not in template


def test_omniroute_secret_env_is_generated_for_keyless_internal_runtime(
    tmp_path: Path,
) -> None:
    runtime = ManagedComposeRuntime(runner=_missing_runner, template_root=str(tmp_path))
    original = STACKS["sovereign-omniroute"]
    stack = type(original)(
        **{
            **original.__dict__,
            "deploy_root": str(tmp_path / "omniroute"),
        }
    )

    result = runtime._ensure_stack_secret_env(stack)
    env_path = Path(result["path"])
    values = dict(
        line.split("=", 1)
        for line in env_path.read_text("utf-8").splitlines()
        if line and "=" in line
    )

    assert result["required"] is True
    assert result["created"] is True
    assert result["secretValuesReturned"] is False
    assert env_path.stat().st_mode & 0o777 == 0o600
    assert len(values["JWT_SECRET"]) == 96
    assert len(values["API_KEY_SECRET"]) == 64
    assert len(values["INITIAL_PASSWORD"]) == 48
    assert len(values["STORAGE_ENCRYPTION_KEY"]) == 64
    assert values["REQUIRE_API_KEY"] == "false"
    assert values["BASE_URL"] == "http://127.0.0.1:20128"
    assert values["NEXT_PUBLIC_BASE_URL"] == "http://127.0.0.1:20128"
    assert values["AUTH_COOKIE_SECURE"] == "false"
    assert values["APP_LOG_TO_FILE"] == "false"
    assert values["TMPDIR"] == "/app/data"
    for secret_key in result["keysPresent"]:
        assert values[secret_key] not in str(result)


def test_omniroute_transport_requires_health_security_volume_and_private_network() -> None:
    state = {
        "present": True,
        "running": True,
        "health": "healthy",
        "publishedPorts": {},
        "networks": ["sovereign-private"],
        "imageReference": OMNIROUTE_IMAGE,
        "runtimeUser": "1000:1000",
        "readOnlyRootfs": True,
        "privileged": False,
        "capDrop": ["ALL"],
        "securityOpt": ["no-new-privileges:true"],
        "pidsLimit": 256,
        "mounts": [{
            "type": "volume",
            "name": OMNIROUTE_DATA_VOLUME,
            "destination": "/app/data",
            "rw": True,
        }],
    }

    assert ManagedComposeRuntime._omniroute_transport_ready(state) is True
    state["health"] = "unhealthy"
    assert ManagedComposeRuntime._omniroute_transport_ready(state) is False
    state["health"] = "healthy"
    state["runtimeUser"] = "0:0"
    assert ManagedComposeRuntime._omniroute_transport_ready(state) is False


def test_omniroute_runtime_canary_requires_real_models_readback(tmp_path: Path) -> None:
    def runner(argv, **kwargs):
        if argv[:3] == ["docker", "exec", OMNIROUTE_CONTAINER]:
            assert "http://127.0.0.1:20128/v1/models" in argv[-1]
            return subprocess.CompletedProcess(argv, 0, '{"ok":true,"httpStatus":200,"modelCount":17}', "")
        return subprocess.CompletedProcess(argv, 1, "", "not found")

    runtime = ManagedComposeRuntime(runner=runner, template_root=str(tmp_path))
    result = runtime._omniroute_runtime_canary()

    assert result["ok"] is True
    assert result["status"] == "OMNIROUTE_MODELS_VERIFIED"
    assert result["modelsStatus"] == 200
    assert result["modelCount"] == 17
    assert result["responseContentReturned"] is False


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
