from __future__ import annotations

import json
import subprocess

from patchmon_operator import PATCHMON_CONTAINERS, PatchmonOperatorRuntime


HOST_ID = "11111111-1111-4111-8111-111111111111"
RUN_ID = "22222222-2222-4222-8222-222222222222"


def _completed(argv: list[str], stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr=stderr)


def test_tool_inventory_declares_closed_safety_boundaries() -> None:
    result = PatchmonOperatorRuntime.tool_inventory()

    assert result["status"] == "PATCHMON_OPERATOR_TOOLS_REGISTERED"
    assert result["boundaries"] == {
        "dockerSocketMountedInMcp": False,
        "genericShellAccepted": False,
        "arbitrarySqlAccepted": False,
        "arbitraryHttpEndpointAccepted": False,
        "mutationTransport": "host_command_queue_only",
        "adminCredentialLocation": "root_only_host_file",
        "externalPatchmonPortRequired": False,
    }
    assert result["secretValuesExposed"] is False


def test_arbitrary_query_and_invalid_filters_are_blocked_without_process_execution() -> None:
    def runner(*args, **kwargs):
        raise AssertionError("blocked input must not execute a process")

    runtime = PatchmonOperatorRuntime(runner=runner)

    arbitrary = runtime.query(view="SELECT * FROM users")
    injected_status = runtime.query(view="hosts", status="active' OR TRUE --")
    injected_host = runtime.query(view="hosts", host_id="not-a-uuid")

    assert arbitrary["status"] == "BLOCKED"
    assert arbitrary["arbitrarySqlAccepted"] is False
    assert injected_status["status"] == "BLOCKED"
    assert injected_host["status"] == "BLOCKED"


def test_status_filters_are_scoped_to_the_selected_view(monkeypatch) -> None:
    runtime = PatchmonOperatorRuntime()
    queries: list[str] = []

    def psql(sql: str, **kwargs):
        queries.append(sql)
        return {"ok": True, "status": "PATCHMON_DATABASE_QUERY_OK", "rows": [], "columns": []}

    monkeypatch.setattr(runtime, "_psql", psql)

    patch_runs = runtime.query(view="patch_runs", status="running")
    hosts = runtime.query(view="hosts", status="offline")
    docker_assets = runtime.query(view="docker_assets")
    invalid_alerts = runtime.query(view="alerts", status="running")

    assert patch_runs["ok"] is True
    assert "pr.status = 'running'" in queries[0]
    assert hosts["ok"] is True
    assert "h.status = 'offline'" in queries[1]
    assert docker_assets["ok"] is True
    assert "LEFT JOIN docker_containers" in queries[2]
    assert "LEFT JOIN hosts" in queries[2]
    assert invalid_alerts["status"] == "BLOCKED"
    assert len(queries) == 3


def test_free_text_redaction_removes_secret_shaped_values() -> None:
    payload = PatchmonOperatorRuntime._redact({
        "message": "Bearer abcdefghijklmnop api_key=sk-proj-abcdefghijklmnopqrstuv headerpart12.payloadpart12.signaturepart12",
        "detail": "normal diagnostic text",
    })
    encoded = json.dumps(payload)

    assert "abcdefghijklmnop" not in encoded
    assert "sk-proj-" not in encoded
    assert "headerpart12.payloadpart12.signaturepart12" not in encoded
    assert payload["detail"] == "normal diagnostic text"


def test_runtime_inventory_does_not_return_container_environment_or_mount_sources(monkeypatch) -> None:
    network_name = "patchmon-sovereign_patchmon-edge"

    def runner(argv, **kwargs):
        if argv[:2] == ["docker", "inspect"]:
            name = argv[2]
            service = name.removeprefix("patchmon-sovereign-").removesuffix("-1")
            published = (
                {"3000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "32830"}]}
                if service == "server"
                else {}
            )
            payload = [{
                "Id": "a" * 64,
                "Name": "/" + name,
                "Image": "sha256:" + "b" * 64,
                "Config": {
                    "Image": "ghcr.io/patchmon/example:2.0.2",
                    "Env": ["JWT_SECRET=must-not-leak", "POSTGRES_PASSWORD=must-not-leak"],
                    "Labels": {
                        "com.docker.compose.project": "patchmon-sovereign",
                        "com.docker.compose.service": service,
                    },
                },
                "State": {
                    "Status": "running",
                    "Running": True,
                    "Paused": False,
                    "Restarting": False,
                    "OOMKilled": False,
                    "Dead": False,
                    "ExitCode": 0,
                    "StartedAt": "2026-07-19T00:00:00Z",
                    "FinishedAt": "",
                    "Health": {"Status": "healthy"},
                },
                "NetworkSettings": {
                    "Networks": {network_name: {"IPAddress": "172.31.0.2", "GlobalIPv6Address": ""}},
                    "Ports": published,
                },
                "Mounts": [{
                    "Type": "bind",
                    "Source": "/root/private/credential-file",
                    "Destination": "/run/secrets/example",
                    "RW": False,
                }],
                "HostConfig": {
                    "Privileged": False,
                    "ReadonlyRootfs": False,
                    "NetworkMode": network_name,
                },
                "RestartCount": 0,
            }]
            return _completed(argv, json.dumps(payload))
        if argv[:3] == ["docker", "network", "ls"]:
            return _completed(argv, json.dumps({"Name": network_name}) + "\n")
        if argv[:3] == ["docker", "network", "inspect"]:
            members = {
                str(index): {"Name": name, "IPv4Address": f"172.31.0.{index + 2}/16", "IPv6Address": ""}
                for index, name in enumerate(PATCHMON_CONTAINERS)
            }
            payload = [{
                "Id": "c" * 64,
                "Name": network_name,
                "Driver": "bridge",
                "Scope": "local",
                "Internal": False,
                "Attachable": False,
                "Ingress": False,
                "Labels": {"com.docker.compose.project": "patchmon-sovereign"},
                "Containers": members,
            }]
            return _completed(argv, json.dumps(payload))
        if argv[:3] == ["docker", "ps", "-a"]:
            return _completed(
                argv,
                json.dumps({
                    "ID": "d" * 64,
                    "Names": "patchmon-sovereign-server-1",
                    "Image": "ghcr.io/patchmon/patchmon-server:2.0.2",
                    "State": "running",
                    "Status": "Up 10 minutes (healthy)",
                    "Networks": network_name,
                    "Ports": "127.0.0.1:32830->3000/tcp",
                }) + "\n",
            )
        raise AssertionError(f"unexpected command: {argv}")

    runtime = PatchmonOperatorRuntime(runner=runner)
    monkeypatch.setattr(
        runtime,
        "_http_health",
        lambda: {
            "ok": True,
            "status": "PATCHMON_HTTP_HEALTH_READY",
            "httpStatus": 200,
            "endpoint": "http://127.0.0.1:32830/api/v1/health?format=json",
        },
    )

    result = runtime.runtime_inventory()
    encoded = json.dumps(result)

    assert result["status"] == "PATCHMON_RUNTIME_VERIFIED"
    assert result["boundaryViolations"] == []
    assert "must-not-leak" not in encoded
    assert "/root/private/credential-file" not in encoded
    assert result["containers"]["patchmon-sovereign-server-1"]["publishedPorts"] == [{
        "containerPort": "3000/tcp",
        "hostIp": "127.0.0.1",
        "hostPort": "32830",
    }]


def test_pending_approval_plan_is_state_bound_and_never_claims_host_execution(monkeypatch) -> None:
    runtime = PatchmonOperatorRuntime()
    monkeypatch.setattr(
        runtime,
        "_target_state",
        lambda action, host_id, run_id: {
            "id": host_id,
            "friendly_name": "critical-host",
            "status": "active",
            "last_update": "2026-07-19T00:00:00Z",
        },
    )
    monkeypatch.setattr(
        runtime,
        "_token_metadata",
        lambda: {"ready": False, "status": "TOKEN_FILE_MISSING"},
    )

    plan = runtime.patch_action_plan(
        action="submit_for_approval",
        host_id=HOST_ID,
        patch_type="patch_all",
    )

    assert plan["status"] == "PATCHMON_ACTION_PLAN_READY"
    assert plan["endpoint"] == "/api/v1/patching/trigger"
    assert plan["requestBody"] == {
        "host_id": HOST_ID,
        "patch_type": "patch_all",
        "dry_run": False,
        "pending_approval": True,
    }
    assert plan["impact"] == "creates_pending_approval_without_host_execution"
    assert len(plan["confirmationSha256"]) == 64
    assert plan["mutationPerformed"] is False


def test_package_contract_matches_patchmon_and_rejects_path_or_shell_tokens(monkeypatch) -> None:
    runtime = PatchmonOperatorRuntime()
    monkeypatch.setattr(runtime, "_target_state", lambda *args: {"id": HOST_ID, "status": "active"})
    monkeypatch.setattr(runtime, "_token_metadata", lambda: {"ready": False})

    valid = runtime.patch_action_plan(
        action="validate_packages",
        host_id=HOST_ID,
        patch_type="patch_package",
        package_names=["libssl3:amd64".split(":")[0], "python3.12-minimal"],
    )
    slash = runtime.patch_action_plan(
        action="validate_packages",
        host_id=HOST_ID,
        patch_type="patch_package",
        package_names=["../../etc/passwd"],
    )
    shell = runtime.patch_action_plan(
        action="validate_packages",
        host_id=HOST_ID,
        patch_type="patch_package",
        package_names=["openssl;reboot"],
    )

    assert valid["ok"] is True
    assert slash["status"] == "BLOCKED"
    assert shell["status"] == "BLOCKED"


def test_action_apply_replans_and_blocks_stale_confirmation(monkeypatch) -> None:
    runtime = PatchmonOperatorRuntime()
    states = iter([
        {"id": HOST_ID, "friendly_name": "host", "status": "active", "last_update": "first"},
        {"id": HOST_ID, "friendly_name": "host", "status": "active", "last_update": "changed"},
    ])
    monkeypatch.setattr(runtime, "_target_state", lambda *args: next(states))
    monkeypatch.setattr(runtime, "_token_metadata", lambda: {"ready": True, "status": "TOKEN_FILE_READY"})
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PATCHMON_PATCH_WRITE", "1")

    first = runtime.patch_action_plan(
        action="submit_for_approval",
        host_id=HOST_ID,
        patch_type="patch_all",
    )
    called = False

    def api_request(*args, **kwargs):
        nonlocal called
        called = True
        return {"ok": True, "httpStatus": 200, "response": {}}

    monkeypatch.setattr(runtime, "_api_request", api_request)
    monkeypatch.setattr(runtime, "_read_admin_token", lambda: "not-returned")

    result = runtime.patch_action_apply(
        action="submit_for_approval",
        confirmation_sha256=first["confirmationSha256"],
        host_id=HOST_ID,
        patch_type="patch_all",
    )

    assert result["status"] == "BLOCKED"
    assert "does not match current state" in result["blocker"]
    assert called is False


def test_action_apply_uses_only_fixed_loopback_contract_and_never_returns_token(monkeypatch) -> None:
    runtime = PatchmonOperatorRuntime()
    state = {"id": RUN_ID, "host_id": HOST_ID, "patch_type": "patch_all", "status": "pending_approval"}
    monkeypatch.setattr(runtime, "_target_state", lambda *args: state)
    monkeypatch.setattr(runtime, "_token_metadata", lambda: {"ready": True, "status": "TOKEN_FILE_READY"})
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PATCHMON_PATCH_WRITE", "1")

    plan = runtime.patch_action_plan(action="approve_run", run_id=RUN_ID)
    observed = {}

    def api_request(method, endpoint, body, token):
        observed.update(method=method, endpoint=endpoint, body=body, token=token)
        return {
            "ok": True,
            "httpStatus": 200,
            "response": {"patch_run_id": "33333333-3333-4333-8333-333333333333"},
        }

    monkeypatch.setattr(runtime, "_read_admin_token", lambda: "header.payload.signature")
    monkeypatch.setattr(runtime, "_api_request", api_request)

    result = runtime.patch_action_apply(
        action="approve_run",
        run_id=RUN_ID,
        confirmation_sha256=plan["confirmationSha256"],
    )
    encoded = json.dumps(result)

    assert observed == {
        "method": "POST",
        "endpoint": f"/api/v1/patching/runs/{RUN_ID}/approve",
        "body": {},
        "token": "header.payload.signature",
    }
    assert result["status"] == "PATCHMON_ACTION_ACCEPTED"
    assert result["patchCompletionClaimed"] is False
    assert result["secretValuesExposed"] is False
    assert "header.payload.signature" not in encoded


def test_stop_plan_requires_current_running_evidence(monkeypatch) -> None:
    runtime = PatchmonOperatorRuntime()
    monkeypatch.setattr(
        runtime,
        "_psql",
        lambda *args, **kwargs: {
            "ok": True,
            "rows": [{
                "id": RUN_ID,
                "host_id": HOST_ID,
                "patch_type": "patch_all",
                "status": "completed",
            }],
        },
    )

    result = runtime.patch_action_plan(action="stop_run", run_id=RUN_ID)

    assert result["status"] == "BLOCKED"
    assert result["blocker"] == "PATCHMON_RUN_NOT_RUNNING"
