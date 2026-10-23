"""Real broker readback contracts; Docker is the only substituted adapter."""
import base64
import json

import pytest

from broker import BrokerRuntime

TARGET = "echoes-of-aurion-aurion-1"
REVISION = "a" * 40
CONTAINER_ID = "b" * 64
IMAGE = "sha256:" + "c" * 64
KEY = base64.urlsafe_b64encode(bytes(range(32))).decode().rstrip("=")


def snapshot(environment=None):
    return {
        "state": {"Running": True, "Status": "running"},
        "id": CONTAINER_ID,
        "image": IMAGE,
        "labels": {
            "com.docker.compose.project": "echoes-of-aurion",
            "com.docker.compose.service": "aurion",
            "org.opencontainers.image.revision": REVISION,
        },
        "environment": environment if environment is not None else [
            "NATIVE_AUTH_RELEASE_ENABLED=true",
            "NATIVE_AUTH_STATE_SEAL_KEY=" + KEY,
            "DATABASE_URL=SYNTHETIC_PRIVATE_DATABASE_VALUE",
            "UNRELATED=SYNTHETIC_PRIVATE_OTHER_VALUE",
        ],
    }


def inspect(monkeypatch, value, private=True, target=TARGET):
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1" if private else "0")
    monkeypatch.setenv("SOVEREIGN_MCP_ALLOWED_CONTAINERS", target)
    runtime = BrokerRuntime()
    calls = []

    def docker(argv, timeout):
        calls.append(argv)
        assert argv[:3] == ["docker", "inspect", "--format"]
        assert argv[-1] == target and timeout == 30
        return {"ok": True, "stdout": json.dumps(value), "stderr": ""}

    monkeypatch.setattr(runtime, "_run", docker)
    return runtime.dispatch("container_status", {"container": target}), calls


def test_private_aurion_readback_binds_identity_and_never_returns_environment(monkeypatch):
    result, calls = inspect(monkeypatch, snapshot())
    assert result["ok"] is True
    assert result["state"]["Running"] is True
    auth = result["nativeAuthConfiguration"]
    assert auth == {
        "status": "CONFIGURATION_PREREQUISITES_PRESENT",
        "sourceRevision": REVISION,
        "containerId": CONTAINER_ID,
        "imageDigest": IMAGE,
        "releaseFlagPresent": True,
        "releaseEnabled": True,
        "stateSealKeyPresent": True,
        "stateSealKeyValid": True,
        "databaseConnection": "UNVERIFIED",
        "login": "UNVERIFIED",
    }
    assert len(calls) == 1
    encoded = json.dumps(result)
    for private_value in [KEY, "SYNTHETIC_PRIVATE_DATABASE_VALUE", "SYNTHETIC_PRIVATE_OTHER_VALUE"]:
        assert private_value not in encoded
    assert "environment" not in result and "labels" not in result


@pytest.mark.parametrize("value", ["false", "1", "True", "true ", ""])
def test_non_exact_release_flag_blocks_configuration(monkeypatch, value):
    result, _ = inspect(monkeypatch, snapshot([
        "NATIVE_AUTH_RELEASE_ENABLED=" + value,
        "NATIVE_AUTH_STATE_SEAL_KEY=" + KEY,
    ]))
    auth = result["nativeAuthConfiguration"]
    assert auth["releaseEnabled"] is False
    assert auth["stateSealKeyValid"] is True
    assert auth["status"] == "CONFIGURATION_BLOCKED"


@pytest.mark.parametrize("value", ["", "invalid", KEY + "=", KEY[:-1] + "B", "é" * 43])
def test_invalid_or_noncanonical_seal_key_is_not_reported_as_valid(monkeypatch, value):
    result, _ = inspect(monkeypatch, snapshot([
        "NATIVE_AUTH_RELEASE_ENABLED=true",
        "NATIVE_AUTH_STATE_SEAL_KEY=" + value,
    ]))
    auth = result["nativeAuthConfiguration"]
    assert auth["stateSealKeyValid"] is False
    assert auth["status"] == "CONFIGURATION_BLOCKED"
    assert value == "" or value not in json.dumps(auth)


def test_absent_configuration_is_distinguished_from_present_but_invalid(monkeypatch):
    result, _ = inspect(monkeypatch, snapshot([]))
    auth = result["nativeAuthConfiguration"]
    assert auth["releaseFlagPresent"] is False
    assert auth["releaseEnabled"] is False
    assert auth["stateSealKeyPresent"] is False
    assert auth["stateSealKeyValid"] is False
    assert auth["status"] == "CONFIGURATION_BLOCKED"


@pytest.mark.parametrize("field,value", [
    ("id", "invalid"),
    ("image", "mutable:latest"),
    ("labels", {}),
    ("environment", {}),
    ("environment", ["NATIVE_AUTH_RELEASE_ENABLED=true", "NATIVE_AUTH_RELEASE_ENABLED=false"]),
    ("environment", [None]),
])
def test_invalid_or_ambiguous_readback_fails_closed_without_reflecting_raw_data(monkeypatch, field, value):
    raw = snapshot()
    raw[field] = value
    result, _ = inspect(monkeypatch, raw)
    assert result["ok"] is False
    assert "nativeAuthConfiguration" not in result
    assert KEY not in json.dumps(result)


@pytest.mark.parametrize("label,value", [
    ("com.docker.compose.project", "other"),
    ("com.docker.compose.service", "other"),
    ("org.opencontainers.image.revision", "stale-tag"),
])
def test_cross_scope_and_unbound_revision_are_rejected(monkeypatch, label, value):
    raw = snapshot()
    raw["labels"][label] = value
    result, _ = inspect(monkeypatch, raw)
    assert result["ok"] is False
    assert KEY not in json.dumps(result)


@pytest.mark.parametrize("private,target", [(False, TARGET), (True, "sovereign-backend")])
def test_other_owner_or_container_keeps_original_state_only_contract(monkeypatch, private, target):
    state = {"Running": True}
    result, calls = inspect(monkeypatch, state, private=private, target=target)
    assert result == {"ok": True, "status": "VERIFIED", "container": target, "state": state}
    assert calls == [["docker", "inspect", "--format", "{{json .State}}", target]]


def test_failed_private_inspection_does_not_expose_docker_output(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    runtime = BrokerRuntime()
    monkeypatch.setattr(runtime, "_run", lambda *a, **k: {
        "ok": False, "stdout": KEY, "stderr": "SYNTHETIC_PRIVATE_OTHER_VALUE",
    })
    result = runtime.dispatch("container_status", {"container": TARGET})
    assert result["ok"] is False
    assert KEY not in json.dumps(result)
    assert "SYNTHETIC_PRIVATE_OTHER_VALUE" not in json.dumps(result)
