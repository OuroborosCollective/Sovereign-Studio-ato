#!/usr/bin/env python3
"""Prepare, verify, and execute the exact two-service Toolchain rollback."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from typing import Any

ROOT = Path("/opt/sovereign-legacy-mcp")
BACKUP_ROOT = ROOT / ".installer-backups"
MANIFEST_PATH = BACKUP_ROOT / "last-install.json"
REVISION_MARKER = ".sovereign-source-revision"
SCHEMA = "sovereign.toolchain.rollback.v1"
SERVICES = (
    "sovereign-toolchain.service",
    "sovereign-toolchain-n8n-evidence.service",
)
DIRECTORIES = (
    (ROOT / "sovereign-toolchain", "sovereign-toolchain"),
    (ROOT / "sovereign-legacy-mcp-common", "sovereign-legacy-mcp-common"),
)
FILES = (
    (Path("/etc/systemd/system/sovereign-toolchain.service"), "sovereign-toolchain.service", 0o644),
    (
        Path("/etc/systemd/system/sovereign-toolchain-n8n-evidence.service"),
        "sovereign-toolchain-n8n-evidence.service",
        0o644,
    ),
    (Path("/etc/sovereign-toolchain/runtime.env"), "runtime.env", 0o600),
    (Path("/etc/sovereign-toolchain/evidence-runtime.env"), "evidence-runtime.env", 0o600),
    (Path("/etc/sovereign-toolchain/n8n-evidence.key"), "n8n-evidence.key", 0o600),
)
SHA40 = re.compile(r"^[0-9a-f]{40}$")
STAMP = re.compile(r"^[0-9]{8}T[0-9]{6}Z\.[1-9][0-9]*$")


class RollbackError(RuntimeError):
    pass


def require_root() -> None:
    if os.geteuid() != 0:
        raise RollbackError("root authority is required")
    metadata = BACKUP_ROOT.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or BACKUP_ROOT.is_symlink()
        or metadata.st_uid != 0
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise RollbackError("backup root violates the security contract")


def run_systemctl(*arguments: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["systemctl", *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RollbackError("systemd command failed") from exc


def is_active(service: str) -> bool:
    return run_systemctl("is-active", "--quiet", service).returncode == 0


def is_enabled(service: str) -> bool:
    return run_systemctl("is-enabled", "--quiet", service).returncode == 0


def property_value(service: str, name: str) -> str:
    result = run_systemctl("show", f"--property={name}", "--value", service)
    if result.returncode != 0:
        raise RollbackError("systemd property readback failed")
    return result.stdout.strip()


def sha256_file(path: Path) -> str:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    digest = hashlib.sha256()
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RollbackError("snapshot path is not a regular file")
        while True:
            chunk = os.read(descriptor, 131072)
            if not chunk:
                break
            digest.update(chunk)
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def atomic_json_write(payload: dict[str, Any]) -> None:
    temporary = BACKUP_ROOT / f".last-install.{os.getpid()}.tmp"
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, 0, 0)
    finally:
        os.close(descriptor)
    os.replace(temporary, MANIFEST_PATH)
    directory = os.open(BACKUP_ROOT, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def read_manifest() -> dict[str, Any]:
    metadata = MANIFEST_PATH.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or MANIFEST_PATH.is_symlink()
        or metadata.st_uid != 0
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_size <= 0
        or metadata.st_size > 65536
    ):
        raise RollbackError("rollback manifest violates the security contract")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(MANIFEST_PATH, flags)
    try:
        raw = os.read(descriptor, 65537)
    finally:
        os.close(descriptor)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RollbackError("rollback manifest is invalid") from exc
    if not isinstance(payload, dict):
        raise RollbackError("rollback manifest is invalid")
    return validate_manifest(payload)


def validate_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    revision = payload.get("installedRevision")
    stamp = payload.get("stamp")
    if (
        payload.get("schemaVersion") != SCHEMA
        or payload.get("state") not in {"pending", "committed", "rolled_back"}
        or not isinstance(revision, str)
        or not SHA40.fullmatch(revision)
        or not isinstance(stamp, str)
        or not STAMP.fullmatch(stamp)
    ):
        raise RollbackError("rollback manifest identity is invalid")
    previous = payload.get("previousRevision")
    if previous is not None and (not isinstance(previous, str) or not SHA40.fullmatch(previous)):
        raise RollbackError("previous revision is invalid")

    directories = payload.get("directories")
    if not isinstance(directories, list) or len(directories) != len(DIRECTORIES):
        raise RollbackError("directory rollback set is invalid")
    for entry, (target, basename) in zip(directories, DIRECTORIES, strict=True):
        expected_backup = BACKUP_ROOT / f"{basename}.{stamp}"
        if (
            not isinstance(entry, dict)
            or entry.get("target") != str(target)
            or entry.get("backup") != str(expected_backup)
            or type(entry.get("previousPresent")) is not bool
        ):
            raise RollbackError("directory rollback entry is invalid")
        if entry["previousPresent"]:
            if not isinstance(entry.get("previousDevice"), int) or not isinstance(entry.get("previousInode"), int):
                raise RollbackError("directory identity is invalid")
        elif entry.get("previousDevice") is not None or entry.get("previousInode") is not None:
            raise RollbackError("absent directory identity is invalid")

    files = payload.get("files")
    if not isinstance(files, list) or len(files) != len(FILES):
        raise RollbackError("file rollback set is invalid")
    for entry, (target, basename, _required_mode) in zip(files, FILES, strict=True):
        expected_backup = BACKUP_ROOT / f"{basename}.{stamp}"
        if (
            not isinstance(entry, dict)
            or entry.get("target") != str(target)
            or entry.get("backup") != str(expected_backup)
            or type(entry.get("previousPresent")) is not bool
        ):
            raise RollbackError("file rollback entry is invalid")
        if entry["previousPresent"]:
            if (
                not isinstance(entry.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
                or not all(isinstance(entry.get(field), int) for field in ("mode", "uid", "gid", "size"))
            ):
                raise RollbackError("file snapshot identity is invalid")
        elif any(entry.get(field) is not None for field in ("sha256", "mode", "uid", "gid", "size")):
            raise RollbackError("absent file identity is invalid")

    services = payload.get("services")
    if not isinstance(services, list) or len(services) != len(SERVICES):
        raise RollbackError("service rollback set is invalid")
    for entry, service in zip(services, SERVICES, strict=True):
        if (
            not isinstance(entry, dict)
            or entry.get("name") != service
            or type(entry.get("active")) is not bool
            or type(entry.get("enabled")) is not bool
        ):
            raise RollbackError("service rollback entry is invalid")
    return payload


def listener_addresses(path: Path, port: int) -> set[str]:
    addresses: set[str] = set()
    for line in path.read_text("ascii").splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 4 and fields[3] == "0A":
            address, encoded_port = fields[1].split(":", 1)
            if int(encoded_port, 16) == port:
                addresses.add(address)
    return addresses


def verify_socket_boundary(full_active: bool, evidence_active: bool) -> None:
    full_v4 = listener_addresses(Path("/proc/net/tcp"), 8001)
    full_v6 = listener_addresses(Path("/proc/net/tcp6"), 8001)
    evidence_v4 = listener_addresses(Path("/proc/net/tcp"), 8002)
    evidence_v6 = listener_addresses(Path("/proc/net/tcp6"), 8002)
    if full_active:
        if full_v4 != {"0100007F"} or full_v6:
            raise RollbackError("full listener socket boundary is invalid")
    elif full_v4 or full_v6:
        raise RollbackError("inactive full service retains a listener")
    if evidence_active:
        if evidence_v4 != {"00000000"} or evidence_v6:
            raise RollbackError("evidence listener socket boundary is invalid")
    elif evidence_v4 or evidence_v6:
        raise RollbackError("inactive evidence service retains a listener")


def verify_effective_units(full_active: bool, evidence_active: bool) -> None:
    if full_active and "--host 127.0.0.1 --port 8001" not in property_value(SERVICES[0], "ExecStart"):
        raise RollbackError("full service effective bind is invalid")
    if evidence_active:
        if "--host 0.0.0.0 --port 8002" not in property_value(SERVICES[1], "ExecStart"):
            raise RollbackError("evidence service effective bind is invalid")
        if property_value(SERVICES[1], "DynamicUser") != "yes":
            raise RollbackError("evidence service is not dynamically unprivileged")
        if property_value(SERVICES[1], "ProtectSystem") != "strict":
            raise RollbackError("evidence service filesystem protection is invalid")
        if property_value(SERVICES[1], "ReadWritePaths"):
            raise RollbackError("evidence service has writable filesystem paths")


def verify_service_activation_states(services: list[dict[str, Any]]) -> None:
    for entry in services:
        if is_active(entry["name"]) is not entry["active"]:
            raise RollbackError("service active-state readback failed")
        if is_enabled(entry["name"]) is not entry["enabled"]:
            raise RollbackError("service enable-state readback failed")


def verify_service_states(services: list[dict[str, Any]]) -> None:
    verify_service_activation_states(services)
    full_active = services[0]["active"]
    evidence_active = services[1]["active"]
    verify_effective_units(full_active, evidence_active)
    verify_socket_boundary(full_active, evidence_active)


def is_managed_snapshot(path: Path) -> bool:
    if path.parent != BACKUP_ROOT:
        return False
    basenames = tuple(basename for _target, basename in DIRECTORIES) + tuple(
        basename for _target, basename, _mode in FILES
    )
    for basename in basenames:
        prefix = f"{basename}."
        if path.name.startswith(prefix) and STAMP.fullmatch(path.name[len(prefix) :]):
            return True
    for _target, basename in DIRECTORIES:
        prefix = f"failed-{basename}."
        if path.name.startswith(prefix) and STAMP.fullmatch(path.name[len(prefix) :]):
            return True
    return False


def retire_superseded_snapshots(retained_payload: dict[str, Any]) -> None:
    retained = {
        Path(entry["backup"])
        for group in (retained_payload["directories"], retained_payload["files"])
        for entry in group
    }
    retained.update(
        BACKUP_ROOT / f"failed-{Path(entry['target']).name}.{retained_payload['stamp']}"
        for entry in retained_payload["directories"]
    )
    changed = False
    for candidate in BACKUP_ROOT.iterdir():
        if candidate in retained or not is_managed_snapshot(candidate):
            continue
        metadata = candidate.lstat()
        if stat.S_ISLNK(metadata.st_mode) or stat.S_ISREG(metadata.st_mode):
            candidate.unlink()
        elif stat.S_ISDIR(metadata.st_mode):
            shutil.rmtree(candidate)
        else:
            raise RollbackError("superseded snapshot type is invalid")
        changed = True
    if changed:
        directory = os.open(BACKUP_ROOT, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def copy_snapshot(source: Path, target: Path, metadata: os.stat_result) -> None:
    if target.exists() or target.is_symlink():
        raise RollbackError("rollback backup already exists")
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    output = os.open(temporary, flags, stat.S_IMODE(metadata.st_mode))
    input_descriptor = os.open(
        source,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        current = os.fstat(input_descriptor)
        if not stat.S_ISREG(current.st_mode):
            raise RollbackError("rollback source is not a regular file")
        while True:
            chunk = os.read(input_descriptor, 131072)
            if not chunk:
                break
            view = memoryview(chunk)
            while view:
                written = os.write(output, view)
                view = view[written:]
        os.fchmod(output, stat.S_IMODE(metadata.st_mode))
        os.fchown(output, metadata.st_uid, metadata.st_gid)
        os.fsync(output)
    finally:
        os.close(input_descriptor)
        os.close(output)
    os.replace(temporary, target)


def prepare(expected_revision: str, stamp: str) -> None:
    if not SHA40.fullmatch(expected_revision) or not STAMP.fullmatch(stamp):
        raise RollbackError("prepare identity is invalid")
    if MANIFEST_PATH.exists() or MANIFEST_PATH.is_symlink():
        existing = read_manifest()
        if existing["state"] == "pending":
            restore(existing, existing["installedRevision"])

    directories: list[dict[str, Any]] = []
    previous_revision = None
    for target, basename in DIRECTORIES:
        present = target.exists()
        if target.is_symlink() or (present and not target.is_dir()):
            raise RollbackError("existing deployment directory is invalid")
        metadata = target.stat() if present else None
        directories.append(
            {
                "target": str(target),
                "backup": str(BACKUP_ROOT / f"{basename}.{stamp}"),
                "previousPresent": present,
                "previousDevice": metadata.st_dev if metadata else None,
                "previousInode": metadata.st_ino if metadata else None,
            }
        )
    if directories[0]["previousPresent"]:
        marker = DIRECTORIES[0][0] / REVISION_MARKER
        if marker.is_symlink() or not marker.is_file():
            raise RollbackError("previous revision marker is unavailable")
        previous_revision = marker.read_text("ascii").strip()
        if not SHA40.fullmatch(previous_revision):
            raise RollbackError("previous revision marker is invalid")

    files: list[dict[str, Any]] = []
    for target, basename, required_mode in FILES:
        present = target.exists()
        if target.is_symlink() or (present and not target.is_file()):
            raise RollbackError("existing deployment file is invalid")
        if present:
            metadata = target.stat()
            if metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) != required_mode:
                raise RollbackError("existing deployment file metadata is invalid")
            entry = {
                "target": str(target),
                "backup": str(BACKUP_ROOT / f"{basename}.{stamp}"),
                "previousPresent": True,
                "sha256": sha256_file(target),
                "mode": stat.S_IMODE(metadata.st_mode),
                "uid": metadata.st_uid,
                "gid": metadata.st_gid,
                "size": metadata.st_size,
            }
            copy_snapshot(target, Path(entry["backup"]), metadata)
        else:
            entry = {
                "target": str(target),
                "backup": str(BACKUP_ROOT / f"{basename}.{stamp}"),
                "previousPresent": False,
                "sha256": None,
                "mode": None,
                "uid": None,
                "gid": None,
                "size": None,
            }
        files.append(entry)

    services = [
        {"name": service, "active": is_active(service), "enabled": is_enabled(service)}
        for service in SERVICES
    ]
    verify_service_activation_states(services)
    atomic_json_write(
        {
            "schemaVersion": SCHEMA,
            "state": "pending",
            "installedRevision": expected_revision,
            "previousRevision": previous_revision,
            "stamp": stamp,
            "directories": directories,
            "files": files,
            "services": services,
        }
    )
    # The new pending manifest is fsynced and read back before any snapshot
    # generation becomes unreachable. A bounded scan also repairs leftovers
    # from an interrupted retirement on the next prepare.
    retire_superseded_snapshots(read_manifest())


def restore_file(entry: dict[str, Any]) -> None:
    target = Path(entry["target"])
    if not entry["previousPresent"]:
        if target.exists() or target.is_symlink():
            target.unlink()
        return
    backup = Path(entry["backup"])
    metadata = backup.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or backup.is_symlink()
        or sha256_file(backup) != entry["sha256"]
        or metadata.st_size != entry["size"]
    ):
        raise RollbackError("file rollback backup readback failed")
    if (
        target.is_file()
        and not target.is_symlink()
        and sha256_file(target) == entry["sha256"]
        and stat.S_IMODE(target.stat().st_mode) == entry["mode"]
        and target.stat().st_uid == entry["uid"]
        and target.stat().st_gid == entry["gid"]
    ):
        return
    temporary = target.parent / f".{target.name}.rollback.{os.getpid()}"
    copy_snapshot(backup, temporary, metadata)
    os.chmod(temporary, entry["mode"])
    os.chown(temporary, entry["uid"], entry["gid"])
    os.replace(temporary, target)


def restore_directory(entry: dict[str, Any], stamp: str) -> None:
    target = Path(entry["target"])
    backup = Path(entry["backup"])
    if entry["previousPresent"]:
        if target.is_dir() and not target.is_symlink():
            metadata = target.stat()
            if metadata.st_dev == entry["previousDevice"] and metadata.st_ino == entry["previousInode"]:
                return
        if not backup.is_dir() or backup.is_symlink():
            raise RollbackError("directory rollback backup is unavailable")
        metadata = backup.stat()
        if metadata.st_dev != entry["previousDevice"] or metadata.st_ino != entry["previousInode"]:
            raise RollbackError("directory rollback backup identity changed")
        if target.exists() or target.is_symlink():
            quarantine = BACKUP_ROOT / f"failed-{target.name}.{stamp}"
            if quarantine.exists() or quarantine.is_symlink():
                raise RollbackError("rollback quarantine already exists")
            os.replace(target, quarantine)
        os.replace(backup, target)
    elif target.exists() or target.is_symlink():
        quarantine = BACKUP_ROOT / f"failed-{target.name}.{stamp}"
        if quarantine.exists() or quarantine.is_symlink():
            raise RollbackError("rollback quarantine already exists")
        os.replace(target, quarantine)


def verify_restored_snapshots(payload: dict[str, Any]) -> None:
    for entry in payload["directories"]:
        target = Path(entry["target"])
        if entry["previousPresent"]:
            metadata = target.stat()
            if (
                target.is_symlink()
                or not target.is_dir()
                or metadata.st_dev != entry["previousDevice"]
                or metadata.st_ino != entry["previousInode"]
            ):
                raise RollbackError("restored directory identity readback failed")
        elif target.exists() or target.is_symlink():
            raise RollbackError("absent directory was recreated")
    for entry in payload["files"]:
        target = Path(entry["target"])
        if entry["previousPresent"]:
            metadata = target.lstat()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or target.is_symlink()
                or metadata.st_uid != entry["uid"]
                or metadata.st_gid != entry["gid"]
                or stat.S_IMODE(metadata.st_mode) != entry["mode"]
                or metadata.st_size != entry["size"]
                or sha256_file(target) != entry["sha256"]
            ):
                raise RollbackError("restored file readback failed")
        elif target.exists() or target.is_symlink():
            raise RollbackError("absent file was recreated")
    previous = payload["previousRevision"]
    if payload["directories"][0]["previousPresent"]:
        marker = DIRECTORIES[0][0] / REVISION_MARKER
        if marker.read_text("ascii").strip() != previous:
            raise RollbackError("restored revision readback failed")


def restore(payload: dict[str, Any], expected_revision: str) -> None:
    if payload["installedRevision"] != expected_revision:
        raise RollbackError("rollback expected revision mismatch")
    for service in reversed(SERVICES):
        run_systemctl("stop", service)
    if any(is_active(service) for service in SERVICES):
        raise RollbackError("services did not stop before rollback")
    for entry in payload["directories"]:
        restore_directory(entry, payload["stamp"])
    for entry in payload["files"]:
        restore_file(entry)
    if run_systemctl("daemon-reload").returncode != 0:
        raise RollbackError("systemd daemon reload failed")
    for entry in payload["services"]:
        action = "enable" if entry["enabled"] else "disable"
        result = run_systemctl(action, entry["name"])
        if entry["enabled"] and result.returncode != 0:
            raise RollbackError("service enablement rollback failed")
    for entry in payload["services"]:
        if entry["active"] and run_systemctl("start", entry["name"]).returncode != 0:
            raise RollbackError("service restart rollback failed")
    verify_restored_snapshots(payload)
    # A predecessor can legitimately implement an older listener boundary.
    # Its exact unit files and activation flags were already snapshotted.
    verify_service_activation_states(payload["services"])
    payload["state"] = "rolled_back"
    atomic_json_write(payload)


def commit(payload: dict[str, Any], expected_revision: str) -> None:
    if payload["installedRevision"] != expected_revision or payload["state"] != "pending":
        raise RollbackError("commit manifest state is invalid")
    marker = DIRECTORIES[0][0] / REVISION_MARKER
    if marker.is_symlink() or not marker.is_file() or marker.read_text("ascii").strip() != expected_revision:
        raise RollbackError("installed revision commit readback failed")
    desired = [
        {"name": SERVICES[0], "active": True, "enabled": True},
        {"name": SERVICES[1], "active": True, "enabled": True},
    ]
    verify_service_states(desired)
    payload["state"] = "committed"
    atomic_json_write(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="operation", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--expected-installed-revision", required=True)
    prepare_parser.add_argument("--stamp", required=True)
    for operation in ("rollback", "commit"):
        child = subparsers.add_parser(operation)
        child.add_argument("--expected-installed-revision", required=True)
    arguments = parser.parse_args()
    try:
        require_root()
        if arguments.operation == "prepare":
            prepare(arguments.expected_installed_revision, arguments.stamp)
        else:
            payload = read_manifest()
            if arguments.operation == "rollback":
                restore(payload, arguments.expected_installed_revision)
            else:
                commit(payload, arguments.expected_installed_revision)
    except (OSError, RollbackError, ValueError) as exc:
        digest = hashlib.sha256(str(exc).encode("utf-8")).hexdigest()
        print(
            f"SOVEREIGN_TOOLCHAIN_ROLLBACK_FAILURE operation={arguments.operation} reason_sha256={digest}",
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "operation": arguments.operation,
                "rollbackVerified": arguments.operation == "rollback",
                "servicesReadback": True,
                "revisionReadback": True,
                "socketBoundaryReadback": arguments.operation == "commit",
                "predecessorBoundaryPreserved": arguments.operation == "rollback",
                "secretValuesReturned": False,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
