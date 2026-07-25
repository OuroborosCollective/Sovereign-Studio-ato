from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import patchmon_fleet
from patchmon_fleet import PatchmonFleetRuntime
from patchmon_operator import PatchmonOperatorRuntime


HOST_ID = "11111111-1111-4111-8111-111111111111"


def test_bootstrap_plan_is_state_bound_and_keeps_container_revision_lane_separate(monkeypatch) -> None:
    operator = PatchmonOperatorRuntime()
    runtime = PatchmonFleetRuntime(operator)
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PATCHMON_PATCH_WRITE", "1")
    monkeypatch.setattr(
        runtime,
        "_state",
        lambda friendly_name: {
            "runtimeStatus": "PATCHMON_RUNTIME_VERIFIED",
            "runtimeReady": True,
            "fleetContainerCount": 31,
            "database": {
                "users_total": "0",
                "hosts_total": "0",
                "hosts_active": "0",
                "docker_containers_observed": "0",
            },
            "agent": {"activeState": "inactive"},
            "adminToken": {"ready": False},
            "credentialBundle": {"ready": False},
        },
    )

    plan = runtime.bootstrap_plan(friendly_name="sovereign-vps")

    assert plan["status"] == "PATCHMON_FLEET_BOOTSTRAP_PLAN_READY"
    assert plan["currentState"]["fleetContainerCount"] == 31
    assert plan["immutableContainerLane"] == "unchanged_existing_revision_bound_image_deploy_path"
    assert "create_or_reuse_one_local_host_with_docker_enabled" in plan["effects"]
    assert len(plan["confirmationSha256"]) == 64
    assert plan["readyToApply"] is True
    assert plan["directDatabaseMutationUsed"] is False
    assert plan["mutationPerformed"] is False


def test_bootstrap_apply_replans_and_blocks_stale_confirmation(monkeypatch) -> None:
    operator = PatchmonOperatorRuntime()
    runtime = PatchmonFleetRuntime(operator)
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PATCHMON_PATCH_WRITE", "1")
    states = iter(
        [
            {
                "runtimeStatus": "PATCHMON_RUNTIME_VERIFIED",
                "runtimeReady": True,
                "fleetContainerCount": 31,
                "database": {"users_total": "0", "hosts_total": "0"},
                "agent": {"activeState": "inactive"},
                "adminToken": {"ready": False},
                "credentialBundle": {"ready": False},
            },
            {
                "runtimeStatus": "PATCHMON_RUNTIME_VERIFIED",
                "runtimeReady": True,
                "fleetContainerCount": 32,
                "database": {"users_total": "0", "hosts_total": "0"},
                "agent": {"activeState": "inactive"},
                "adminToken": {"ready": False},
                "credentialBundle": {"ready": False},
            },
        ]
    )
    monkeypatch.setattr(runtime, "_state", lambda friendly_name: next(states))
    first = runtime.bootstrap_plan()
    called = False

    def bootstrap_admin() -> str:
        nonlocal called
        called = True
        return "headerpart12.payloadpart12.signaturepart12"

    monkeypatch.setattr(runtime, "_bootstrap_admin", bootstrap_admin)
    result = runtime.bootstrap_apply(
        confirmation_sha256=first["confirmationSha256"],
        owner_approved=True,
    )

    assert result["status"] == "BLOCKED"
    assert "does not match current state" in result["blocker"]
    assert called is False


def test_agent_state_parses_named_systemd_properties(monkeypatch, tmp_path: Path) -> None:
    operator = PatchmonOperatorRuntime()
    runtime = PatchmonFleetRuntime(operator)
    binary = tmp_path / "patchmon-agent"
    config = tmp_path / "config.yml"
    binary.write_text("binary", encoding="utf-8")
    config.write_text("config", encoding="utf-8")
    monkeypatch.setattr(patchmon_fleet, "PATCHMON_AGENT_BINARY", binary)
    monkeypatch.setattr(patchmon_fleet, "PATCHMON_AGENT_CONFIG", config)
    monkeypatch.setattr(
        operator,
        "_run",
        lambda argv, **kwargs: {
            "ok": True,
            "stdout": "SubState=running\nLoadState=loaded\nActiveState=active\n",
            "stderr": "",
        },
    )

    state = runtime._agent_state()

    assert state == {
        "queryOk": True,
        "loadState": "loaded",
        "activeState": "active",
        "subState": "running",
        "binaryPresent": True,
        "configPresent": True,
    }


def test_official_agent_installer_is_loopback_bound_and_secret_free(monkeypatch, tmp_path: Path) -> None:
    operator = PatchmonOperatorRuntime()
    runtime = PatchmonFleetRuntime(operator)
    install_script = tmp_path / ".install.sh"
    monkeypatch.setattr(patchmon_fleet, "PATCHMON_INSTALL_SCRIPT", install_script)
    monkeypatch.setattr(os, "chown", lambda path, uid, gid: None)
    monkeypatch.setattr(runtime, "_host_credentials", lambda host_id: ("api-id-private", "api-key-private"))
    script = (
        "#!/bin/sh\n"
        "PATCHMON_URL=\"http://127.0.0.1:32830\"\n"
        "printf install\n"
    ).encode("utf-8")
    observed: dict[str, object] = {}

    def request(method, endpoint, **kwargs):
        observed["request"] = {
            "method": method,
            "endpoint": endpoint,
            "headers": kwargs.get("headers"),
            "expect_json": kwargs.get("expect_json"),
        }
        return 200, script

    states = iter(
        [
            {"activeState": "inactive", "configPresent": False, "binaryPresent": False},
            {"activeState": "active", "configPresent": True, "binaryPresent": True},
        ]
    )
    monkeypatch.setattr(runtime, "_request", request)
    monkeypatch.setattr(runtime, "_agent_state", lambda: next(states))

    def run(argv, **kwargs):
        observed["argv"] = argv
        assert Path(argv[1]).read_bytes() == script
        return {"ok": True, "stdout": "", "stderr": ""}

    monkeypatch.setattr(operator, "_run", run)

    result = runtime._install_agent(HOST_ID)
    encoded = json.dumps(result)

    assert result["installed"] is True
    assert result["scriptSha256"] == hashlib.sha256(script).hexdigest()
    assert observed["argv"] == ["/bin/sh", str(install_script)]
    assert observed["request"] == {
        "method": "GET",
        "endpoint": "/api/v1/hosts/install?force=true&os=linux",
        "headers": {"X-API-ID": "api-id-private", "X-API-KEY": "api-key-private"},
        "expect_json": False,
    }
    assert "api-id-private" not in encoded
    assert "api-key-private" not in encoded
    assert not install_script.exists()


def test_bootstrap_apply_proves_active_host_and_real_docker_inventory(monkeypatch) -> None:
    operator = PatchmonOperatorRuntime()
    runtime = PatchmonFleetRuntime(operator)
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PATCHMON_PATCH_WRITE", "1")
    state = {
        "runtimeStatus": "PATCHMON_RUNTIME_VERIFIED",
        "runtimeReady": True,
        "fleetContainerCount": 31,
        "database": {"users_total": "0", "hosts_total": "0"},
        "agent": {"activeState": "inactive"},
        "adminToken": {"ready": False},
        "credentialBundle": {"ready": False},
    }
    monkeypatch.setattr(runtime, "_state", lambda friendly_name: state)
    plan = runtime.bootstrap_plan()
    monkeypatch.setattr(runtime, "_bootstrap_admin", lambda: "headerpart12.payloadpart12.signaturepart12")
    monkeypatch.setattr(runtime, "_request", lambda *args, **kwargs: (200, {}))
    host = {"id": HOST_ID, "friendly_name": "sovereign-vps", "status": "active", "docker_enabled": "true"}
    monkeypatch.setattr(runtime, "_create_or_reuse_host", lambda token, friendly_name: host)
    monkeypatch.setattr(
        runtime,
        "_install_agent",
        lambda host_id: {"installed": True, "state": {"activeState": "active"}},
    )
    monkeypatch.setattr(runtime, "_host_row", lambda friendly_name: host)
    monkeypatch.setattr(runtime, "_ensure_docker_enabled", lambda token, current_host: None)
    monkeypatch.setattr(
        runtime,
        "_refresh_and_wait",
        lambda token, host_id, friendly_name, expected_minimum: {
            "hosts_active": "1",
            "docker_containers_observed": "31",
            "docker_images_observed": "24",
            "docker_networks_observed": "12",
            "docker_volumes_observed": "8",
        },
    )

    result = runtime.bootstrap_apply(
        confirmation_sha256=plan["confirmationSha256"],
        owner_approved=True,
    )

    assert result["status"] == "PATCHMON_FLEET_BOOTSTRAPPED"
    assert result["hostActive"] is True
    assert result["expectedFleetContainers"] == 31
    assert result["observedDockerContainers"] == 31
    assert result["immutableContainerLane"] == "unchanged_existing_revision_bound_image_deploy_path"
    assert result["secretValuesExposed"] is False


def test_patch_action_token_provider_is_used_without_returning_token(monkeypatch) -> None:
    operator = PatchmonOperatorRuntime()
    operator.set_admin_token_provider(lambda: "headerpart12.payloadpart12.signaturepart12")

    assert operator._read_admin_token() == "headerpart12.payloadpart12.signaturepart12"
