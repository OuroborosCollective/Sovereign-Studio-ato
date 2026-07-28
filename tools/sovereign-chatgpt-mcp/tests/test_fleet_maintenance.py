from __future__ import annotations

import json

from command_contract import is_mutating_action
from fleet_maintenance import (
    FILEBROWSER_CONTAINER,
    FleetMaintenanceRuntime,
    _compatible_restore_toc,
)


PATCH_RUN_ID = "a238357e-03a9-4212-a39a-1db0a18947f1"
BOOT_ID = "11111111-1111-4111-8111-111111111111"
RECEIPT_SHA = "a" * 64


def test_restore_toc_omits_complete_vault_extension_overlap() -> None:
    vault_function = "372; 1255 16427 FUNCTION vault secrets_encrypt_secret_secret() postgres"
    vault_view = "373; 1259 16428 TABLE vault decrypted_secrets postgres"
    vault_trigger = (
        "374; 2620 16429 TRIGGER vault "
        "secrets_encrypt_secret_trigger_secret postgres"
    )
    table = "215; 1259 16384 TABLE public users postgres"
    listing = (
        "; Archive created at 2026-07-28\n"
        + "\n".join((vault_function, vault_view, vault_trigger, table))
        + "\n"
    )

    filtered, omissions = _compatible_restore_toc(listing)

    assert f";{vault_function}" in filtered
    assert f";{vault_view}" in filtered
    assert f";{vault_trigger}" in filtered
    assert table in filtered
    assert f";{table}" not in filtered
    assert omissions == [
        "FUNCTION vault.secrets_encrypt_secret_secret()",
        "TRIGGER vault.secrets_encrypt_secret_trigger_secret",
        "VIEW vault.decrypted_secrets",
    ]


def test_restore_toc_accepts_trigger_tag_layout_variants() -> None:
    vault_function = "372; 1255 16427 FUNCTION vault secrets_encrypt_secret_secret() postgres"
    vault_view = "373; 1259 16428 TABLE vault decrypted_secrets postgres"
    trigger_name = "secrets_encrypt_secret_trigger_secret"
    variants = (
        f"374; 2620 16429 TRIGGER vault secrets {trigger_name} postgres",
        f"374; 2620 16429 TRIGGER vault vault.secrets {trigger_name} postgres",
        f"374; 2620 16429 TRIGGER vault {trigger_name} ON secrets postgres",
        f"374; 2620 16429 TRIGGER - secrets {trigger_name} postgres",
        f"374; 2620 16429 CONSTRAINT TRIGGER - secrets {trigger_name} postgres",
    )

    for vault_trigger in variants:
        listing = "\n".join((vault_function, vault_view, vault_trigger)) + "\n"
        filtered, omissions = _compatible_restore_toc(listing)

        assert f";{vault_trigger}" in filtered
        assert omissions == [
            "FUNCTION vault.secrets_encrypt_secret_secret()",
            "TRIGGER vault.secrets_encrypt_secret_trigger_secret",
            "VIEW vault.decrypted_secrets",
        ]


def test_restore_toc_reports_secret_safe_trigger_candidate_on_layout_drift() -> None:
    vault_function = "372; 1255 16427 FUNCTION vault secrets_encrypt_secret_secret() postgres"
    vault_view = "373; 1259 16428 TABLE vault decrypted_secrets postgres"
    vault_trigger = (
        "374; 2620 16429 EVENT TRIGGER - secrets "
        "secrets_encrypt_secret_trigger_secret postgres"
    )

    try:
        _compatible_restore_toc("\n".join((vault_function, vault_view, vault_trigger)) + "\n")
    except RuntimeError as exc:
        detail = str(exc)
        assert "triggerCandidates" in detail
        assert "<owner>" in detail
        assert "postgres" not in detail
    else:
        raise AssertionError("unexpected trigger layout was not blocked")


def test_restore_toc_blocks_incomplete_vault_extension_overlap() -> None:
    vault_function = "372; 1255 16427 FUNCTION vault secrets_encrypt_secret_secret() postgres"
    vault_view = "373; 1259 16428 TABLE vault decrypted_secrets postgres"

    try:
        _compatible_restore_toc(vault_function + "\n" + vault_view + "\n")
    except RuntimeError as exc:
        assert "Vault compatibility inventory drifted" in str(exc)
        assert '"TRIGGER vault.secrets_encrypt_secret_trigger_secret":0' in str(exc)
    else:
        raise AssertionError("incomplete Vault compatibility inventory was not blocked")


def test_vault_compatibility_digest_requires_complete_definitions(monkeypatch) -> None:
    runtime = FleetMaintenanceRuntime()
    payload = {
        "function": "CREATE FUNCTION vault.secrets_encrypt_secret_secret() RETURNS trigger",
        "trigger": "CREATE TRIGGER secrets_encrypt_secret_trigger_secret",
        "view": "SELECT * FROM vault.secrets",
    }
    monkeypatch.setattr(
        runtime,
        "_psql",
        lambda _database, _sql, timeout=300: {
            "ok": True,
            "stdout": json.dumps(payload) + "\n",
            "stderr": "",
        },
    )

    digest = runtime._vault_compatibility_digest("postgres")

    assert len(digest) == 64


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


def test_backup_plan_binds_disk_safety_floor_not_volatile_free_space(monkeypatch, tmp_path) -> None:
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
    available_values = iter((2_147_483_648, 3_221_225_472))
    monkeypatch.setattr(
        runtime,
        "_run_text",
        lambda argv, timeout=120: {
            "ok": True,
            "exit_code": 0,
            "stdout": f"Avail\n{next(available_values)}\n",
            "stderr": "",
        },
    )

    first = runtime.postgres_backup_restore_plan(patch_run_id=PATCH_RUN_ID)
    second = runtime.postgres_backup_restore_plan(patch_run_id=PATCH_RUN_ID)

    assert first["status"] == "POSTGRES_BACKUP_RESTORE_PLAN_READY"
    assert first["patchRun"]["status"] == "pending_approval"
    assert first["bootId"] == BOOT_ID
    assert first["isolatedRestoreRequired"] is True
    assert first["minimumAvailableBytes"] == 1_073_741_824
    assert first["availableBytes"] != second["availableBytes"]
    assert first["confirmationSha256"] == second["confirmationSha256"]
    assert len(first["confirmationSha256"]) == 64


def test_backup_apply_uses_filtered_toc_and_verifies_restore(monkeypatch, tmp_path) -> None:
    runtime = FleetMaintenanceRuntime(maintenance_root=str(tmp_path / "maintenance"))
    confirmation = "b" * 64
    calls: list[list[str]] = []
    manifest = {
        "schemaDigest": "c" * 64,
        "rowCountDigest": "d" * 64,
        "tableCount": 3,
        "totalRows": 7,
    }
    vault_function = "372; 1255 16427 FUNCTION vault secrets_encrypt_secret_secret() postgres"
    vault_view = "373; 1259 16428 TABLE vault decrypted_secrets postgres"
    vault_trigger = (
        "374; 2620 16429 TRIGGER vault "
        "secrets_encrypt_secret_trigger_secret postgres"
    )
    vault_digest = "e" * 64

    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_PATCHMON_PATCH_WRITE", "1")
    monkeypatch.setattr(
        runtime,
        "postgres_backup_restore_plan",
        lambda **_kwargs: {
            "ok": True,
            "status": "POSTGRES_BACKUP_RESTORE_PLAN_READY",
            "confirmationSha256": confirmation,
            "bootId": BOOT_ID,
        },
    )
    monkeypatch.setattr(runtime, "_database_manifest", lambda _database: manifest)
    monkeypatch.setattr(runtime, "_vault_compatibility_digest", lambda _database: vault_digest)
    monkeypatch.setattr(runtime, "_drop_restore_database", lambda _database: True)
    monkeypatch.setattr(
        runtime,
        "_run_file_input",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("restore must use the in-container archive and filtered TOC")
        ),
    )

    def run(argv, timeout=120):
        calls.append(argv)
        if argv[:2] == ["docker", "cp"] and ":/tmp/sovereign-prepatch-" in argv[2]:
            target = argv[3]
            with open(target, "wb") as handle:
                handle.write(b"custom-format-backup")
        if "pg_restore" in argv and "--list" in argv:
            return {
                "ok": True,
                "exit_code": 0,
                "stdout": (
                    "; archive\n"
                    + "\n".join((vault_function, vault_view, vault_trigger))
                    + "\n215; 1259 16384 TABLE public users postgres\n"
                ),
                "stderr": "",
            }
        return {"ok": True, "exit_code": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(runtime, "_run_text", run)

    result = runtime.postgres_backup_restore_apply(
        patch_run_id=PATCH_RUN_ID,
        confirmation_sha256=confirmation,
        owner_approved=True,
    )

    assert result["status"] == "POSTGRES_BACKUP_RESTORE_VERIFIED"
    assert result["restoreCompatibilityOmissions"] == [
        "FUNCTION vault.secrets_encrypt_secret_secret()",
        "TRIGGER vault.secrets_encrypt_secret_trigger_secret",
        "VIEW vault.decrypted_secrets",
    ]
    assert result["vaultCompatibilityDigest"] == f"sha256:{vault_digest}"
    assert result["isolatedTargetRemoved"] is True
    restore_calls = [call for call in calls if "pg_restore" in call and "--use-list" in call]
    assert len(restore_calls) == 1
    assert restore_calls[0][-1].endswith(".dump")
    assert any(call[:4] == ["docker", "exec", "--user", "0"] for call in calls)


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
