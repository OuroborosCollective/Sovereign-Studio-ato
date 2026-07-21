from __future__ import annotations

import subprocess
from pathlib import Path

from managed_compose import (
    FREELLMAPI_DATA_VOLUME,
    FREELLMAPI_IMAGE,
    FREELLMAPI_REPO_DIGEST,
    ManagedComposeRuntime,
    STACKS,
)


def _missing_runner(argv, **kwargs):
    return subprocess.CompletedProcess(argv, 1, "", "not found")


def test_freellmapi_template_is_private_immutable_and_source_bound() -> None:
    template = (
        Path(__file__).resolve().parents[1]
        / "templates"
        / "sovereign-freellmapi"
        / "docker-compose.yml"
    ).read_text("utf-8")

    assert FREELLMAPI_IMAGE in template
    assert "v0.5.0@sha256:e3ffcd7f78527cf16113fa196174bebdd6fa5dd0c84adfa9e577f43f4a48a784" in template
    assert "dd134590f336a8a36488e903e6129c2ee04929508b9a811e0de6b72b1f89a9ef" in template
    assert "ports:" not in template
    assert "sovereign-private:" in template
    assert "external: true" in template
    assert "freellmapi-data:/app/server/data" in template
    assert "/var/run/docker.sock" not in template


def test_freellmapi_secret_env_is_generated_without_returning_values(tmp_path: Path) -> None:
    runtime = ManagedComposeRuntime(runner=_missing_runner, template_root=str(tmp_path))
    original = STACKS["sovereign-freellmapi"]
    stack = type(original)(**{**original.__dict__, "deploy_root": str(tmp_path / "deploy")})

    result = runtime._ensure_stack_secret_env(stack)
    env_path = Path(result["path"])
    values = dict(
        line.split("=", 1)
        for line in env_path.read_text("utf-8").splitlines()
        if line and "=" in line
    )

    assert result["created"] is True
    assert result["keysPresent"] == ["ENCRYPTION_KEY"]
    assert result["secretValuesReturned"] is False
    assert env_path.stat().st_mode & 0o777 == 0o600
    assert len(values["ENCRYPTION_KEY"]) == 64
    assert values["ENCRYPTION_KEY"] not in str(result)


def test_freellmapi_transport_requires_private_network_digest_volume_and_no_ports(tmp_path: Path) -> None:
    runtime = ManagedComposeRuntime(runner=_missing_runner, template_root=str(tmp_path))
    state = {
        "present": True,
        "running": True,
        "publishedPorts": {},
        "networks": ["sovereign-private"],
        "imageReference": FREELLMAPI_IMAGE,
        "repoDigests": [FREELLMAPI_REPO_DIGEST],
        "mounts": [{
            "type": "volume",
            "name": FREELLMAPI_DATA_VOLUME,
            "destination": "/app/server/data",
            "rw": True,
        }],
    }

    assert runtime._freellmapi_transport_ready(state) is True
    state["publishedPorts"] = {"3001/tcp": [{"HostIp": "127.0.0.1", "HostPort": "3001"}]}
    assert runtime._freellmapi_transport_ready(state) is False
    state["publishedPorts"] = {}
    state["networks"] = ["other"]
    assert runtime._freellmapi_transport_ready(state) is False


def test_freellmapi_owner_key_sync_writes_private_file_without_returning_key(
    tmp_path: Path,
    monkeypatch,
) -> None:
    key = "freellmapi-" + ("a" * 48)

    def runner(argv, **kwargs):
        if argv[:4] == ["docker", "exec", "sovereign-freellmapi", "node"]:
            return subprocess.CompletedProcess(argv, 0, key, "")
        return subprocess.CompletedProcess(argv, 1, "", "not found")

    destination = tmp_path / "owner" / "freellmapi_unified_key.txt"
    monkeypatch.setattr("managed_compose.FREELLMAPI_OWNER_KEY_PATH", str(destination))
    runtime = ManagedComposeRuntime(runner=runner, template_root=str(tmp_path))

    result = runtime._freellmapi_owner_key_sync()

    assert result["status"] == "FREELLMAPI_OWNER_KEY_SYNCED"
    assert result["secretValuesReturned"] is False
    assert result["mode"] == "0600"
    assert destination.read_text("utf-8") == key + "\n"
    assert destination.stat().st_mode & 0o777 == 0o600
    assert key not in str(result)


def test_freellmapi_runtime_canary_requires_authenticated_models_without_content(tmp_path: Path) -> None:
    receipt = (
        '{"ok":true,"pingStatus":200,"modelsStatus":200,"modelCount":7,'
        '"unifiedKeySha256":"' + ("b" * 64) + '"}'
    )

    def runner(argv, **kwargs):
        if argv[:4] == ["docker", "exec", "sovereign-freellmapi", "node"]:
            return subprocess.CompletedProcess(argv, 0, receipt, "")
        return subprocess.CompletedProcess(argv, 1, "", "not found")

    runtime = ManagedComposeRuntime(runner=runner, template_root=str(tmp_path))
    result = runtime._freellmapi_runtime_canary()

    assert result["status"] == "FREELLMAPI_AUTHENTICATED_MODELS_VERIFIED"
    assert result["modelCount"] == 7
    assert result["keyFingerprintSha256"] == "b" * 64
    assert result["responseContentReturned"] is False
    assert result["secretValuesReturned"] is False
