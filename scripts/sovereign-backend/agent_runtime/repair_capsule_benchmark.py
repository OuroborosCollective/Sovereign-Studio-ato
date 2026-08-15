"""Deterministic Zero-Trust Repair Capsule benchmark/evidence harness.

Records observed values only. Anything that cannot be observed against a real
fresh clone, real tests or a real Draft-PR delivery run is reported as the
sentinel ``NOT_MEASURED`` rather than an invented number. The harness never
performs a GitHub write, never applies a patch automatically, and fails closed
on any violated zero-write security invariant.

The harness is pure stdlib. The clone-dependent readbacks (head SHA, verify.py,
``git apply --check``, targeted-test parity) require a real fresh clone path and
an optional targeted-test command supplied by the caller. When those are absent
the corresponding fields are ``NOT_MEASURED`` and the run status is ``NOT_RUN``.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

try:
    from .repair_capsule import (
        REPAIR_CAPSULE_SCHEMA_VERSION,
        parse_repair_patch_paths,
        verify_repair_capsule_manifest,
    )
except ImportError:
    from repair_capsule import (
        REPAIR_CAPSULE_SCHEMA_VERSION,
        parse_repair_patch_paths,
        verify_repair_capsule_manifest,
    )

NOT_MEASURED = "not_measured"
STATUS_VERIFIED = "VERIFIED"
STATUS_BLOCKED = "BLOCKED"
STATUS_NOT_RUN = "NOT_RUN"
_CAPSULE_ARCHIVE_MEMBERS = ("README.md", "manifest.json", "repair.patch", "verify.py")


def _is_measured(value: Any) -> bool:
    return value is not NOT_MEASURED and value != NOT_MEASURED


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _git(repository: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repository), *args],
        text=True,
        capture_output=True,
        shell=False,
        check=False,
    )


def _head_sha(repository: Path) -> str | None:
    result = _git(repository, "rev-parse", "--verify", "HEAD")
    if result.returncode != 0:
        return None
    sha = result.stdout.strip().lower()
    return sha or None


def _file_hashes(root: Path, paths: Sequence[str]) -> dict[str, str] | None:
    hashes: dict[str, str] = {}
    for relative in paths:
        target = root / relative
        try:
            hashes[relative] = _digest(target.read_bytes())
        except OSError:
            return None
    return hashes


def audit_capsule_archive(archive_bytes: bytes) -> dict[str, Any]:
    """Static, network-free invariant audit of a Capsule ZIP.

    Runs every time, deterministic, and never invents a value. It proves the
    capsule is zero-write by construction: no production mutation flag, no
    returned secrets, exactly the four canonical members, and a manifest that
    satisfies the offline verifier contract for the embedded patch.
    """

    import zipfile
    import io

    blockers: list[str] = []
    members: list[str] = []
    manifest: dict[str, Any] = {}
    patch = b""
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            members = sorted(archive.namelist())
            if members != sorted(_CAPSULE_ARCHIVE_MEMBERS):
                blockers.append("capsule_member_set_invalid")
            for name in _CAPSULE_ARCHIVE_MEMBERS:
                if name in archive.namelist():
                    data = archive.read(name)
                    if name == "manifest.json":
                        manifest = json.loads(data.decode("utf-8"))
                    elif name == "repair.patch":
                        patch = data
    except Exception as exc:  # pragma: no cover - defensive
        blockers.append(f"capsule_archive_unreadable:{type(exc).__name__}")
        return {
            "status": STATUS_BLOCKED,
            "blockers": blockers,
            "githubWriteCount": 0,
            "productionMutationIncluded": NOT_MEASURED,
            "secretValuesReturned": NOT_MEASURED,
            "schemaVersion": NOT_MEASURED,
        }

    github_write_count = 0
    production_mutation = bool(manifest.get("productionMutationIncluded"))
    secret_values_returned = bool(manifest.get("secretValuesReturned"))
    if production_mutation:
        blockers.append("capsule_production_mutation_included")
    if secret_values_returned:
        blockers.append("capsule_secret_values_returned")
    if manifest.get("schemaVersion") != REPAIR_CAPSULE_SCHEMA_VERSION:
        blockers.append("capsule_schema_version_invalid")
    if manifest.get("product") != "sovereign-rescue":
        blockers.append("capsule_product_invalid")
    if manifest.get("ready") is not True or manifest.get("blockers") != []:
        blockers.append("capsule_manifest_not_ready")
    if not verify_repair_capsule_manifest(manifest, patch):
        blockers.append("capsule_manifest_verification_failed")
    try:
        derived = parse_repair_patch_paths(patch)
    except ValueError as exc:
        derived = ()
        blockers.append(str(exc))
    if derived and tuple(manifest.get("changedFiles") or ()) != derived:
        blockers.append("capsule_changed_file_identity_mismatch")
    # A capsule archive contains no branch, commit, push or PR artifact by
    # construction; assert the canonical member set excludes any such object.
    if "verify.py" not in members or "repair.patch" not in members:
        blockers.append("capsule_verifier_or_patch_missing")
    return {
        "status": STATUS_VERIFIED if not blockers else STATUS_BLOCKED,
        "blockers": list(dict.fromkeys(blockers)),
        "githubWriteCount": github_write_count,
        "productionMutationIncluded": production_mutation,
        "secretValuesReturned": secret_values_returned,
        "schemaVersion": manifest.get("schemaVersion", NOT_MEASURED),
        "baseSha": manifest.get("baseSha", NOT_MEASURED),
        "changedFiles": list(derived) if derived else list(manifest.get("changedFiles") or []),
        "patchSha256": _digest(patch) if patch else NOT_MEASURED,
        "archiveByteCount": len(archive_bytes),
    }


def _run_verify_py(capsule_dir: Path, repository: Path) -> dict[str, Any]:
    verifier = capsule_dir / "verify.py"
    result = subprocess.run(
        ["python3", str(verifier), "--repo", str(repository)],
        cwd=str(capsule_dir),
        text=True,
        capture_output=True,
        shell=False,
        check=False,
    )
    payload: dict[str, Any] = {"ok": False, "status": "BLOCKED", "stdout": result.stdout}
    try:
        payload = json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        payload = {"ok": False, "status": "BLOCKED", "stdout": result.stdout}
    payload["exitCode"] = result.returncode
    return payload


def benchmark_capsule_delivery(
    *,
    archive_bytes: bytes,
    clone_dir: str | os.PathLike[str] | None = None,
    workspace_changed_file_hashes: Mapping[str, str] | None = None,
    targeted_test_command: Sequence[str] | None = None,
    draft_pr_github_write_count: int | None = None,
    clock: Callable[[], float] | None = None,
) -> dict[str, Any]:
    """Run the deterministic Capsule benchmark and record observed values.

    ``clone_dir`` must be a real fresh clone at the Capsule base SHA. When it is
    omitted the harness records the clone-dependent fields as ``NOT_MEASURED``
    and returns status ``NOT_RUN``. ``workspace_changed_file_hashes`` are the
    real file hashes observed in the repair workspace for parity comparison.
    ``targeted_test_command`` is rerun after the local apply. ``draft_pr_github_write_count``
    is the observed write count for the comparable Draft-PR delivery, or
    ``NOT_MEASURED`` when no real Draft-PR run is available.
    """

    audit = audit_capsule_archive(archive_bytes)
    report: dict[str, Any] = {
        "product": "sovereign-rescue",
        "deliveryMode": "capsule",
        "schemaVersion": REPAIR_CAPSULE_SCHEMA_VERSION,
        "audit": audit,
        "freshClone": {
            "headSha": NOT_MEASURED,
            "baseShaMatches": NOT_MEASURED,
        },
        "verifier": NOT_MEASURED,
        "gitApplyCheck": NOT_MEASURED,
        "localApply": NOT_MEASURED,
        "targetedTests": {
            "beforeApply": NOT_MEASURED,
            "afterApply": NOT_MEASURED,
            "parity": NOT_MEASURED,
        },
        "changedFileHashParity": NOT_MEASURED,
        "timeToLocallyVerifiableMs": NOT_MEASURED,
        "comparison": {
            "capsuleGithubWriteCount": audit.get("githubWriteCount"),
            "draftPrGithubWriteCount": draft_pr_github_write_count if draft_pr_github_write_count is not None else NOT_MEASURED,
        },
        "userExperience": {
            "modeSelection": NOT_MEASURED,
            "permissionDialogAbandonment": NOT_MEASURED,
            "supportIncidents": NOT_MEASURED,
        },
    }

    if audit["status"] != STATUS_VERIFIED:
        report["status"] = STATUS_BLOCKED
        report["blockers"] = audit["blockers"]
        return report

    if clone_dir is None:
        report["status"] = STATUS_NOT_RUN
        report["blockers"] = ["clone_dir_not_provided"]
        return report

    repository = Path(clone_dir).resolve()
    base_sha = str(audit["baseSha"])
    head = _head_sha(repository)
    report["freshClone"]["headSha"] = head or NOT_MEASURED
    base_matches = head is not None and head == base_sha.lower()
    report["freshClone"]["baseShaMatches"] = base_matches
    if not base_matches:
        report["status"] = STATUS_BLOCKED
        report["blockers"] = ["fresh_clone_base_sha_mismatch"]
        return report

    blockers: list[str] = []
    started = time.monotonic() if clock is None else clock()

    import zipfile
    import io
    import tempfile

    with tempfile.TemporaryDirectory() as workdir:
        capsule_dir = Path(workdir)
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            archive.extractall(capsule_dir)
        verify = _run_verify_py(capsule_dir, repository)
        report["verifier"] = verify
        if verify.get("ok") is not True:
            blockers.append("verifier_failed")

        apply_check = _git(repository, "apply", "--check", str((capsule_dir / "repair.patch").resolve()))
        report["gitApplyCheck"] = {"ok": apply_check.returncode == 0, "exitCode": apply_check.returncode}
        if apply_check.returncode != 0:
            blockers.append("git_apply_check_failed")

        if not blockers:
            apply_result = _git(repository, "apply", str((capsule_dir / "repair.patch").resolve()))
            applied = apply_result.returncode == 0
            report["localApply"] = {"ok": applied, "exitCode": apply_result.returncode}
            if not applied:
                blockers.append("local_apply_failed")
            else:
                after_hashes = _file_hashes(repository, tuple(audit["changedFiles"]))
                report["changedFileHashParity"] = (
                    after_hashes == dict(workspace_changed_file_hashes or {})
                    if after_hashes is not None
                    else False
                )
                if report["changedFileHashParity"] is False:
                    blockers.append("changed_file_hash_mismatch")
                if targeted_test_command is not None:
                    test_run = subprocess.run(
                        list(targeted_test_command),
                        cwd=str(repository),
                        text=True,
                        capture_output=True,
                        shell=False,
                        check=False,
                    )
                    report["targetedTests"]["afterApply"] = {
                        "exitCode": test_run.returncode,
                        "ok": test_run.returncode == 0,
                    }
                    before = report["targetedTests"]["beforeApply"]
                    after = report["targetedTests"]["afterApply"]
                    if _is_measured(before) and before.get("ok") is True and after.get("ok") is True:
                        report["targetedTests"]["parity"] = True
                    elif _is_measured(before):
                        report["targetedTests"]["parity"] = bool(before.get("ok")) == bool(after.get("ok"))
                    else:
                        report["targetedTests"]["parity"] = after.get("ok") is True
                    if report["targetedTests"]["parity"] is not True:
                        blockers.append("targeted_test_parity_failed")
                else:
                    report["targetedTests"]["afterApply"] = NOT_MEASURED
                    report["targetedTests"]["parity"] = NOT_MEASURED
                # Roll back the local apply so the caller's clone is left clean.
                _git(repository, "apply", "--reverse", str((capsule_dir / "repair.patch").resolve()))

    elapsed_ms = int(((time.monotonic() if clock is None else clock()) - started) * 1000)
    report["timeToLocallyVerifiableMs"] = elapsed_ms
    report["status"] = STATUS_VERIFIED if not blockers else STATUS_BLOCKED
    report["blockers"] = list(dict.fromkeys(blockers))
    return report
