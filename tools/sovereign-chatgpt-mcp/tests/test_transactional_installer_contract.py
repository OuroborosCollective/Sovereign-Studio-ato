from __future__ import annotations

import errno
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "deploy" / "install-on-vps.sh"
UPDATER = ROOT / "deploy" / "self-update-chatgpt-mcp.sh"


def test_installer_and_updater_have_valid_bash_syntax() -> None:
    completed = subprocess.run(
        ["bash", "-n", str(INSTALLER), str(UPDATER)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_private_mode_preflight_accepts_protected_secure_file(tmp_path, monkeypatch) -> None:
    script = INSTALLER.read_text("utf-8")
    marker = 'ensure_private_file_mode() {\n  local file="$1"\n  python3 - "$file" <<\'PY\'\n'
    embedded = script.split(marker, 1)[1].split("\nPY\n}", 1)[0]
    target = tmp_path / ".env"
    target.write_text("ALPHA=old\n", "utf-8")
    target.chmod(0o600)
    original_chmod = os.chmod

    def deny_target_chmod(path: str | bytes | os.PathLike[str] | os.PathLike[bytes], mode: int) -> None:
        if Path(path) == target:
            raise OSError(errno.EPERM, "operation not permitted")
        original_chmod(path, mode)

    monkeypatch.setattr(os, "chmod", deny_target_chmod)
    monkeypatch.setattr(sys, "argv", ["ensure-private-mode", str(target)])
    exec(compile(embedded, "embedded-private-mode", "exec"), {})

    assert os.stat(target).st_mode & 0o777 == 0o600


def test_private_mode_preflight_rejects_protected_public_file(tmp_path, monkeypatch) -> None:
    script = INSTALLER.read_text("utf-8")
    marker = 'ensure_private_file_mode() {\n  local file="$1"\n  python3 - "$file" <<\'PY\'\n'
    embedded = script.split(marker, 1)[1].split("\nPY\n}", 1)[0]
    target = tmp_path / ".env"
    target.write_text("ALPHA=old\n", "utf-8")
    target.chmod(0o644)
    original_chmod = os.chmod

    def deny_target_chmod(path: str | bytes | os.PathLike[str] | os.PathLike[bytes], mode: int) -> None:
        if Path(path) == target:
            raise OSError(errno.EPERM, "operation not permitted")
        original_chmod(path, mode)

    monkeypatch.setattr(os, "chmod", deny_target_chmod)
    monkeypatch.setattr(sys, "argv", ["ensure-private-mode", str(target)])

    try:
        exec(compile(embedded, "embedded-private-mode", "exec"), {})
    except SystemExit as exc:
        assert "unsafe mode" in str(exc)
    else:
        raise AssertionError("protected public file must be rejected")


def test_env_update_falls_back_when_replace_and_chmod_are_not_permitted(tmp_path, monkeypatch) -> None:
    script = INSTALLER.read_text("utf-8")
    marker = 'python3 - "$file" "$key" "$value" <<\'PY\'\n'
    embedded = script.split(marker, 1)[1].split("\nPY\n}", 1)[0]
    target = tmp_path / ".env"
    target.write_text("ALPHA=old\nOTHER=kept\n", "utf-8")
    target.chmod(0o600)
    original_replace = Path.replace
    original_chmod = os.chmod

    def deny_atomic_replace(self: Path, destination: Path) -> Path:
        if self.name == ".env.tmp":
            raise OSError(errno.EPERM, "operation not permitted")
        return original_replace(self, destination)

    def deny_target_chmod(path: str | bytes | os.PathLike[str] | os.PathLike[bytes], mode: int) -> None:
        if Path(path) == target:
            raise OSError(errno.EPERM, "operation not permitted")
        original_chmod(path, mode)

    monkeypatch.setattr(Path, "replace", deny_atomic_replace)
    monkeypatch.setattr(os, "chmod", deny_target_chmod)
    monkeypatch.setattr(sys, "argv", ["set-value", str(target), "ALPHA", "new"])
    exec(compile(embedded, "embedded-set-value", "exec"), {})

    assert target.read_text("utf-8") == "ALPHA=new\nOTHER=kept\n"
    assert os.stat(target).st_mode & 0o777 == 0o600
    assert not target.with_suffix(".env.tmp").exists()


def test_env_update_rejects_unfixable_public_mode(tmp_path, monkeypatch) -> None:
    script = INSTALLER.read_text("utf-8")
    marker = 'python3 - "$file" "$key" "$value" <<\'PY\'\n'
    embedded = script.split(marker, 1)[1].split("\nPY\n}", 1)[0]
    target = tmp_path / ".env"
    target.write_text("ALPHA=old\n", "utf-8")
    target.chmod(0o644)
    original_replace = Path.replace
    original_chmod = os.chmod

    def deny_atomic_replace(self: Path, destination: Path) -> Path:
        if self.name == ".env.tmp":
            raise OSError(errno.EPERM, "operation not permitted")
        return original_replace(self, destination)

    def deny_target_chmod(path: str | bytes | os.PathLike[str] | os.PathLike[bytes], mode: int) -> None:
        if Path(path) == target:
            raise OSError(errno.EPERM, "operation not permitted")
        original_chmod(path, mode)

    monkeypatch.setattr(Path, "replace", deny_atomic_replace)
    monkeypatch.setattr(os, "chmod", deny_target_chmod)
    monkeypatch.setattr(sys, "argv", ["set-value", str(target), "ALPHA", "new"])

    try:
        exec(compile(embedded, "embedded-set-value", "exec"), {})
    except PermissionError as exc:
        assert "unsafe mode" in str(exc)
    else:
        raise AssertionError("unfixable public mode must be rejected")

    assert not target.with_suffix(".env.tmp").exists()


def test_compose_preflight_runs_before_host_control_plane_restart() -> None:
    script = INSTALLER.read_text("utf-8")

    compose_index = script.index('INSTALL_STAGE="compose_preflight"')
    start_index = script.index('INSTALL_STAGE="start_host_control_plane"')
    worker_restart_index = script.index("systemctl restart sovereign-chatgpt-command-worker.service", start_index)
    broker_restart_index = script.index("systemctl restart sovereign-chatgpt-broker.service", start_index)
    container_replace_index = script.index('INSTALL_STAGE="replace_mcp_container"')

    assert compose_index < start_index < worker_restart_index < container_replace_index
    assert compose_index < start_index < broker_restart_index < container_replace_index


def test_failed_install_restores_previous_files_services_container_and_tunnel() -> None:
    script = INSTALLER.read_text("utf-8")

    assert "backup_control_plane_file()" in script
    assert "restore_control_plane_files()" in script
    assert "recover_previous_control_plane()" in script
    assert 'ROLLBACK_ARMED=1' in script
    assert 'rollback_attempted=%s' in script
    assert '[[ "$exit_code" -ne 0 ]] || exit_code=1' in script
    assert 'docker compose \\\n        --project-directory "$INSTALL_ROOT"' in script
    assert 'up -d --no-build --force-recreate sovereign-chatgpt-mcp' in script
    assert 'systemctl restart sovereign-openai-tunnel.service' in script
    assert 'INSTALL_COMPLETED=1' in script
    assert 'ROLLBACK_ARMED=0' in script


def test_backend_and_control_plane_environment_files_are_backed_up_before_mutation() -> None:
    script = INSTALLER.read_text("utf-8")

    assert 'backup_control_plane_file "$ENV_FILE"' in script
    assert 'backup_control_plane_file "$BROKER_ENV"' in script
    assert 'backup_control_plane_file "$BACKEND_ENV_PATH"' in script
    assert script.index('backup_control_plane_file "$BACKEND_ENV_PATH"') < script.index(
        'set_value "$BACKEND_ENV_PATH" SOVEREIGN_OWNER_REQUEST_KEY'
    )


def test_self_update_persists_only_bounded_installer_stage_evidence() -> None:
    updater = UPDATER.read_text("utf-8")

    assert 'INSTALL_LOG="$(mktemp)"' in updater
    assert "grep -E '^install blocked: stage='" in updater
    assert "cut -c1-1200" in updater
    assert "installer failed without bounded stage evidence" in updater
    assert 'write_status FAILED "$EXPECTED_REVISION"' in updater
    assert "cat \"$INSTALL_LOG\"" not in updater
    assert "tail -n 200 \"$INSTALL_LOG\"" not in updater


def test_validated_self_update_wrapper_survives_wider_installer_rollback() -> None:
    installer = INSTALLER.read_text("utf-8")

    assert 'SELF_UPDATE_BIN="$BIN_DIR/self-update-chatgpt-mcp"' in installer
    assert 'bash -n "$SOURCE_DIR/deploy/self-update-chatgpt-mcp.sh"' in installer
    assert 'SELF_UPDATE_NEXT="$(mktemp "$BIN_DIR/.self-update-chatgpt-mcp.XXXXXX")"' in installer
    assert 'mv -f "$SELF_UPDATE_NEXT" "$SELF_UPDATE_BIN"' in installer
    assert 'backup_control_plane_file "$BIN_DIR/self-update-chatgpt-mcp"' not in installer
    assert 'install -m 0750 "$SOURCE_DIR/deploy/self-update-chatgpt-mcp.sh" "$BIN_DIR/self-update-chatgpt-mcp"' not in installer
