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
    assert 'install -m 0644 "$SOURCE_DIR/$file" "$INSTALL_ROOT/$file"' not in script
    assert 'install -m 0640 "$SOURCE_DIR/broker.py" "$BROKER_DIR/broker.py"' not in script
