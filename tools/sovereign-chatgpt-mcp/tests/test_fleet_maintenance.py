from __future__ import annotations

import json

from command_contract import is_mutating_action
from fleet_maintenance import FILEBROWSER_CONTAINER, FleetMaintenanceRuntime


PATCH_RUN_ID = "a238357e-03a9-4212-a39a-1db0a18947f1"
BOOT_ID = "11111111-1111-4111-8111-111111111111"
RECEIPT_SHA = "a" * 64


def _filebrowser_inspect(image: str = "filebrowser/filebrowser:latest") -> dict:
    return {
        "Id": "c" * 64,
        "Image": "sha256:" + "d" * 64,
        "Name": "/" + FILEBROWSER_CONTAINER,
        "Config": {
            "Image": image,
            "Labels": {
                "com.docker.compose.project": "file-browser-cunr",
                "com.docker.compose.service": "filebrowser",
            },
        },
        "State": {
            "Status": "running",
            "Running": True,
            "Health": {"Status": "unhealthy"},
        },
        "Mounts": [
            {
                "Type": "volume",
                "Name": "filebrowser_database",
                "Source": "/var/lib/docker/volumes/filebrowser_database/_data",
                "Destination": "/database",
                "RW": True,
            },
            {
                "Type": "bind",
                "Source": "/private/owner/files",
                "Destination": "/srv",
                "RW": True,
            },
        ],
        "NetworkSettings": {
            "Networks": {"file-browser-cunr_default": {}},
            "Ports": {"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "32832"}]},
        },
    }


def test_filebrowser_plan_is_fixed_and_preserves_volumes(monkeypatch) -> None:
    runtime = FleetMaintenanceRuntime()
    payload = _filebrowser_inspect()
    monkeypatch.setattr(
        runtime,
        "_run_text",
        lambda argv, timeout=120: {
            "ok": True,
            "exit_code": 0,
            "stdout": json.dumps([payload]),
            "stderr": "",
        },
    )

    result = runtime.filebrowser_retirement_plan()

    assert result["ok"] is True
    assert result["status"] == "FILEBROWSER_RETIREMENT_PLAN_READY"
    assert result["target"] == FILEBROWSER_CONTAINER
    assert result["preserveImages"] is True
    assert result["preserveVolumes"] is True
    assert result["preservedNamedVolumes"] == ["filebrowser_database"]
    assert result["container"]["mounts"][0].get("source") is None
    assert len(result["confirmationSha256"]) == 64


def test_filebrowser_plan_blocks_reused_name_with_wrong_image(monkeypatch) -> None:
    runtime = FleetMaintenanceRuntime()
    monkeypatch.setattr(
        runtime,
        "_docker_inspect",
        lambda _name: _filebrowser_inspect("busybox:latest"),
    )

    result = runtime.filebrowser_retirement_plan()

    assert result["ok"] is False
    assert result["failureFamily"] == "TARGET_IDENTITY_MISMATCH"
    assert result["mutationPerformed"] is False


def test_filebrowser_apply_removes_only_exact_container_and_preserves_volume(monkeypatch) -> None:
    runtime = FleetMaintenanceRuntime()
    state = {"present": True}
    calls: list[list[str]] = []

    def inspect(_name):
        return _filebrowser_inspect() if state["present"] else None

    def run(argv, timeout=120):
        calls.append(argv)
        if argv[:3] == ["docker", "rm", "--force"]:
            state["present"] = False
            return {"ok": True, "exit_code": 0, "stdout": FILEBROWSER_CONTAINER, "stderr": ""}
        if argv[:3] == ["docker", "volume", "inspect"]:
            return {"ok": True, "exit_code": 0, "stdout": "[]", "stderr": ""}
        if argv[:3] == ["docker", "ps", "--format"]:
            return {"ok": True, "exit_code": 0, "stdout": "", "stderr": ""}
        raise AssertionError(argv)

    monkeypatch.setattr(runtime, "_docker_inspect", inspect)
    monkeypatch.setattr(runtime, "_run_text", run)
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PATCHMON_PATCH_WRITE", "1")
    confirmation = runtime.filebrowser_retirement_plan()["confirmationSha256"]

    result = runtime.filebrowser_retirement_apply(
        confirmation_sha256=confirmation,
        owner_approved=True,
    )

    assert result["status"] == "FILEBROWSER_RETIRED_VERIFIED"
    assert result["containerAbsent"] is True
    assert result["publishedPort32832Absent"] is True
    assert result["preservedVolumes"] == [{"name": "filebrowser_database", "preserved": True}]
    assert ["docker", "rm", "--force", FILEBROWSER_CONTAINER] in calls
    assert all("--volumes" not in call and "-v" not in call for call in calls)


def test_filebrowser_mutation_requires_owner_and_write_capability(monkeypatch) -> None:
    runtime = FleetMaintenanceRuntime()
    monkeypatch.delenv("SOVEREIGN_MCP_ENABLE_PATCHMON_PATCH_WRITE", raising=False)

    no_owner = runtime.filebrowser_retirement_apply(
        confirmation_sha256="a" * 64,
        owner_approved=False,
    )
    disabled = runtime.filebrowser_retirement_apply(
        confirmation_sha256="a" * 64,
        owner_approved=True,
    )

    assert no_owner["failureFamily"] == "OWNER_APPROVAL_REQUIRED"
    assert disabled["failureFamily"] == "FLEET_MAINTENANCE_WRITE_DISABLED"


def test_backup_plan_binds_pending_patch_run_postgres_boot_and_disk(monkeypatch, tmp_path) -> None:
    runtime = FleetMaintenanceRuntime(
        patch_run_reader=lambda _run_id: {
            "rows": [
                {
                    "id": PATCH_RUN_ID,
                    "status": "pending_approval",
                    "host_id": "da3d0e4a-d7a7-4610-bd8b-89e72b7435d9",
                    "patch_type": "patch_all",
                }
            ]
        },
        maintenance_root=str(tmp_path / "maintenance"),
    )
    monkeypatch.setattr(
        runtime,
        "_postgres_container_state",
        lambda: {
            "containerId": "e" * 64,
            "image": "supabase/postgres:15",
            "imageId": "sha256:" + "f" * 64,
            "running": True,
            "health": "healthy",
        },
    )
    monkeypatch.setattr(runtime, "_boot_id", lambda: BOOT_ID)
    monkeypatch.setattr(
        runtime,
        "_run_text",
        lambda argv, timeout=120: {
            "ok": True,
            "exit_code": 0,
            "stdout": "Avail\n2147483648\n",
            "stderr": "",
        },
    )

    result = runtime.postgres_backup_restore_plan(patch_run_id=PATCH_RUN_ID)

    assert result["status"] == "POSTGRES_BACKUP_RESTORE_PLAN_READY"
    assert result["patchRun"]["status"] == "pending_approval"
    assert result["bootId"] == BOOT_ID
    assert result["isolatedRestoreRequired"] is True
    assert len(result["confirmationSha256"]) == 64


def test_backup_plan_blocks_non_pending_patch_run(monkeypatch, tmp_path) -> None:
    runtime = FleetMaintenanceRuntime(
        patch_run_reader=lambda _run_id: {"rows": [{"id": PATCH_RUN_ID, "status": "completed"}]},
        maintenance_root=str(tmp_path / "maintenance"),
    )

    result = runtime.postgres_backup_restore_plan(patch_run_id=PATCH_RUN_ID)

    assert result["ok"] is False
    assert result["failureFamily"] == "PATCH_RUN_NOT_WAITING_FOR_APPROVAL"


def test_host_reboot_apply_uses_one_bounded_delayed_systemd_unit(monkeypatch) -> None:
    runtime = FleetMaintenanceRuntime()
    confirmation = "b" * 64
    observed: list[list[str]] = []
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PATCHMON_PATCH_WRITE", "1")
    monkeypatch.setattr(
        runtime,
        "host_reboot_plan",
        lambda **_kwargs: {
            "ok": True,
            "status": "HOST_REBOOT_PLAN_READY",
            "previousBootId": BOOT_ID,
            "confirmationSha256": confirmation,
        },
    )

    def run(argv, timeout=120):
        observed.append(argv)
        return {"ok": True, "exit_code": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(runtime, "_run_text", run)

    result = runtime.host_reboot_apply(
        patch_run_id=PATCH_RUN_ID,
        backup_receipt_sha256=RECEIPT_SHA,
        confirmation_sha256=confirmation,
        owner_approved=True,
    )

    assert result["status"] == "HOST_REBOOT_SCHEDULED"
    assert observed == [
        [
            "systemd-run",
            "--unit=sovereign-maintenance-reboot-111111111111",
            "--on-active=15s",
            "--property=Type=oneshot",
            "/usr/bin/systemctl",
            "reboot",
        ]
    ]


def test_all_fleet_mutations_are_host_queue_actions() -> None:
    assert is_mutating_action("fleet_filebrowser_retirement_apply")
    assert is_mutating_action("host_postgres_backup_restore_apply")
    assert is_mutating_action("host_reboot_apply")
    assert not is_mutating_action("fleet_filebrowser_retirement_plan")
    assert not is_mutating_action("host_post_reboot_verify")
