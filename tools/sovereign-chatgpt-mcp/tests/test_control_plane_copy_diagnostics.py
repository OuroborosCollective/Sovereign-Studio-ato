from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "deploy" / "install-on-vps.sh"


def test_managed_control_plane_copy_is_file_bound_and_fail_closed() -> None:
    script = INSTALLER.read_text("utf-8")

    assert "install_managed_control_plane_file()" in script
    assert 'INSTALL_STAGE="copy_control_plane_file:${label}"' in script
    assert "managed control-plane source is not a regular file" in script
    assert "managed control-plane target is not a regular file" in script
    assert "managed control-plane copy failed: label=$label target=$target" in script
    assert "errno.EPERM, errno.EBUSY, errno.EXDEV" in script
    assert 'with target.open("wb") as handle:' in script
    assert "os.fsync(handle.fileno())" in script
    assert 'install_managed_control_plane_file 0644 "$SOURCE_DIR/$file" "$INSTALL_ROOT/$file" "runtime/$file"' in script
    assert 'install_managed_control_plane_file 0644 "$SOURCE_DIR/continuity-data/CONTEXT.md"' in script
    assert 'install_managed_control_plane_file 0644 "$SOURCE_DIR/continuity-data/LEDGER.jsonl"' in script
    assert 'install_managed_control_plane_file 0640 "$SOURCE_DIR/$file" "$BROKER_DIR/$file" "broker/$file"' in script
    assert 'rollback regular-file backup failed: target=$target' in script
    assert 'rollback special-file backup failed: target=$target' in script
    assert 'rollback manifest write failed: target=$target' in script
    assert 'metadata = source.stat(follow_symlinks=False)' in script
    assert 'os.chmod(target, stat.S_IMODE(metadata.st_mode))' in script
    assert 'os.chown(target, metadata.st_uid, metadata.st_gid)' in script
    assert 'os.utime(' in script
    assert 'install -m 0644 "$SOURCE_DIR/$file" "$INSTALL_ROOT/$file"' not in script
    assert 'install -m 0640 "$SOURCE_DIR/broker.py" "$BROKER_DIR/broker.py"' not in script


def test_installer_rejects_reduced_launcher_surface_and_missing_widget_domain() -> None:
    script = INSTALLER.read_text("utf-8")

    assert 'INSTALL_STAGE="verify_live_tool_surface_and_widget_domain"' in script
    for required_tool in (
        "backend_architecture_assess",
        "deterministic_architecture_inventory",
        "mcp_tool_contract_registry",
        "operational_assurance_skill_inventory",
        "patchmon_tool_inventory",
        "repository_architecture_drift_report",
        "repository_architecture_snapshot",
    ):
        assert f'"{required_tool}"' in script
    assert 'server._live_mcp_registry_evidence()' in script
    assert 'registry.get("registry_tool_count") == len(tool_names)' in script
    assert 'ui://sovereign/dev_dashboard.v2.html' in script
    assert 'expected_domain = "https://sovereign-backend.arelorian.de"' in script
    assert 'resource_meta.get("openai/widgetDomain") == expected_domain' in script
    assert '(resource_meta.get("ui") or {}).get("domain") == expected_domain' in script
