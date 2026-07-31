from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent_runtime.repair_capsule import (
    MAX_REPAIR_CAPSULE_PATCH_BYTES,
    REPAIR_CAPSULE_SCHEMA_VERSION,
    build_repair_capsule,
    build_repair_capsule_manifest,
    build_repair_capsule_verifier,
    parse_repair_patch_paths,
    verify_repair_capsule_manifest,
)


BASE_SHA = "a" * 40
OTHER_SHA = "b" * 40
OUTCOME_SHA = "c" * 64
REPAIR_ID = "00000000-0000-4000-8000-000000000123"


def repair(*, base_sha: str = BASE_SHA) -> dict[str, str]:
    return {
        "repair_id": REPAIR_ID,
        "repository": "https://github.com/Acme/Example",
        "base_sha": base_sha,
        "failure_family": "github_actions_ci",
        "outcome_contract_sha256": OUTCOME_SHA,
    }


def job(paths: list[str], summary: str = "targeted tests passed") -> dict[str, object]:
    return {
        "changed_files": paths,
        "test_summary": summary,
    }


def patch_for(path: str = "backend/app.py", before: str = "old", after: str = "new") -> bytes:
    return (
        f"diff --git a/{path} b/{path}\n"
        "index 3367afd..3e75765 100644\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1 +1 @@\n"
        f"-{before}\n"
        f"+{after}\n"
    ).encode("utf-8")


def test_capsule_manifest_is_deterministic_and_contains_only_bound_identities() -> None:
    patch = patch_for()
    first = build_repair_capsule_manifest(
        repair=repair(),
        job=job(["backend/app.py"]),
        patch_value=patch,
    )
    second = build_repair_capsule_manifest(
        repair=repair(),
        job=job(["backend/app.py"]),
        patch_value=patch,
    )
    assert first == second
    assert first["schemaVersion"] == REPAIR_CAPSULE_SCHEMA_VERSION
    assert first["ready"] is True
    assert first["blockers"] == []
    assert first["baseSha"] == BASE_SHA
    assert first["changedFiles"] == ["backend/app.py"]
    assert first["productionMutationIncluded"] is False
    assert first["secretValuesReturned"] is False
    assert "repository" not in first
    assert len(first["repositoryIdentitySha256"]) == 64
    assert len(first["capsuleSha256"]) == 64
    assert verify_repair_capsule_manifest(first, patch) is True


def test_patch_or_revision_change_changes_capsule_identity() -> None:
    original = build_repair_capsule_manifest(
        repair=repair(),
        job=job(["backend/app.py"]),
        patch_value=patch_for(after="new"),
    )
    changed_patch = build_repair_capsule_manifest(
        repair=repair(),
        job=job(["backend/app.py"]),
        patch_value=patch_for(after="newer"),
    )
    changed_base = build_repair_capsule_manifest(
        repair=repair(base_sha=OTHER_SHA),
        job=job(["backend/app.py"]),
        patch_value=patch_for(after="new"),
    )
    assert original["patchSha256"] != changed_patch["patchSha256"]
    assert original["capsuleSha256"] != changed_patch["capsuleSha256"]
    assert original["capsuleSha256"] != changed_base["capsuleSha256"]
    assert verify_repair_capsule_manifest(original, patch_for(after="newer")) is False


def test_patch_paths_are_derived_sorted_and_must_match_persisted_evidence() -> None:
    combined = patch_for("src/zeta.py") + patch_for("backend/alpha.py")
    assert parse_repair_patch_paths(combined) == ("backend/alpha.py", "src/zeta.py")
    ready = build_repair_capsule_manifest(
        repair=repair(),
        job=job(["src/zeta.py", "backend/alpha.py"]),
        patch_value=combined,
    )
    assert ready["ready"] is True
    assert ready["changedFiles"] == ["backend/alpha.py", "src/zeta.py"]

    mismatch = build_repair_capsule_manifest(
        repair=repair(),
        job=job(["src/zeta.py"]),
        patch_value=combined,
    )
    assert mismatch["ready"] is False
    assert "capsule_changed_file_identity_mismatch" in mismatch["blockers"]


@pytest.mark.parametrize(
    ("patch", "expected_blocker"),
    [
        (
            patch_for("../escape.py"),
            "capsule_patch_path_unsafe",
        ),
        (
            patch_for(".git/config"),
            "capsule_patch_git_metadata_forbidden",
        ),
        (
            (
                "diff --git a/backend/app.py b/backend/app.py\n"
                "old mode 100644\n"
                "new mode 100755\n"
                "index 3367afd..3e75765\n"
                "--- a/backend/app.py\n"
                "+++ b/backend/app.py\n"
                "@@ -1 +1 @@\n-old\n+new\n"
            ).encode(),
            "capsule_patch_unsafe_mode_change",
        ),
        (
            (
                "diff --git a/vendor/lib b/vendor/lib\n"
                "index 1111111..2222222 160000\n"
                "--- a/vendor/lib\n"
                "+++ b/vendor/lib\n"
                "@@ -1 +1 @@\n-Subproject commit 1111111\n+Subproject commit 2222222\n"
            ).encode(),
            "capsule_patch_submodule_forbidden",
        ),
        (
            (
                "diff --git a/assets/blob.bin b/assets/blob.bin\n"
                "new file mode 100644\n"
                "index 0000000..1111111\n"
                "GIT binary patch\nliteral 0\nHcmV?d00001\n"
            ).encode(),
            "capsule_patch_binary_forbidden",
        ),
        (
            patch_for(
                "backend/app.py",
                after="Author" + "ization: Bearer " + "github_" + "pat_" + "abcdefghijklmnop",
            ),
            "capsule_patch_secret_material_detected",
        ),
        (
            patch_for("backend/my file.py"),
            "capsule_patch_unsupported_diff_header",
        ),
    ],
)
def test_capsule_parser_fails_closed_on_unsafe_diff_features(
    patch: bytes,
    expected_blocker: str,
) -> None:
    manifest = build_repair_capsule_manifest(
        repair=repair(),
        job=job(["backend/app.py"]),
        patch_value=patch,
    )
    assert manifest["ready"] is False
    assert expected_blocker in manifest["blockers"]
    assert build_repair_capsule(
        repair=repair(),
        job=job(["backend/app.py"]),
        patch_value=patch,
    )["files"] == {}


def test_unicode_paths_are_supported_but_whitespace_paths_are_not() -> None:
    patch = patch_for("backend/über.py")
    manifest = build_repair_capsule_manifest(
        repair=repair(),
        job=job(["backend/über.py"]),
        patch_value=patch,
    )
    assert manifest["ready"] is True
    assert manifest["changedFiles"] == ["backend/über.py"]


def test_capsule_blocks_missing_oversized_or_secret_test_evidence() -> None:
    missing = build_repair_capsule_manifest(
        repair=repair(),
        job=job(["backend/app.py"], summary=""),
        patch_value=patch_for(),
    )
    assert "capsule_test_evidence_missing" in missing["blockers"]

    oversized = build_repair_capsule_manifest(
        repair=repair(),
        job=job(["backend/app.py"], summary="x" * 4001),
        patch_value=patch_for(),
    )
    assert "capsule_test_evidence_too_large" in oversized["blockers"]

    secret = build_repair_capsule_manifest(
        repair=repair(),
        job=job(
            ["backend/app.py"],
            summary="Author" + "ization: Bearer " + "gh" + "p_" + "abcdefghijklmnop",
        ),
        patch_value=patch_for(),
    )
    assert "capsule_test_evidence_secret_material" in secret["blockers"]


def test_capsule_enforces_patch_size_boundary() -> None:
    manifest = build_repair_capsule_manifest(
        repair=repair(),
        job=job(["backend/app.py"]),
        patch_value=b"x" * (MAX_REPAIR_CAPSULE_PATCH_BYTES + 1),
    )
    assert manifest["ready"] is False
    assert "capsule_patch_too_large" in manifest["blockers"]


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    )


def test_generated_verifier_is_offline_checks_head_and_never_applies(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Capsule Test")
    _git(repo, "config", "user.email", "capsule@example.test")
    source = repo / "backend" / "app.py"
    source.parent.mkdir()
    source.write_text("old\n", encoding="utf-8")
    _git(repo, "add", "backend/app.py")
    _git(repo, "commit", "-m", "baseline")
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    source.write_text("new\n", encoding="utf-8")
    patch = _git(repo, "diff", "--no-ext-diff", "--no-renames").stdout.encode("utf-8")
    _git(repo, "checkout", "--", "backend/app.py")

    capsule = build_repair_capsule(
        repair=repair(base_sha=base_sha),
        job=job(["backend/app.py"]),
        patch_value=patch,
    )
    assert capsule["ready"] is True
    package = tmp_path / "capsule"
    package.mkdir()
    for name, content in capsule["files"].items():
        (package / name).write_bytes(content)

    verifier = build_repair_capsule_verifier()
    assert "urllib" not in verifier
    assert "requests" not in verifier
    assert "socket" not in verifier
    assert '["git", "-C"' in verifier
    result = subprocess.run(
        [sys.executable, str(package / "verify.py"), "--repo", str(repo)],
        cwd=package,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "VERIFIED"
    assert source.read_text(encoding="utf-8") == "old\n"

    (repo / "unrelated.txt").write_text("advance\n", encoding="utf-8")
    _git(repo, "add", "unrelated.txt")
    _git(repo, "commit", "-m", "advance head")
    stale = subprocess.run(
        [sys.executable, str(package / "verify.py"), "--repo", str(repo)],
        cwd=package,
        text=True,
        capture_output=True,
        check=False,
    )
    assert stale.returncode == 1
    assert json.loads(stale.stdout)["status"] == "BLOCKED"


def test_generated_verifier_rejects_rehashed_unsafe_mode_patch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Capsule Test")
    _git(repo, "config", "user.email", "capsule@example.test")
    source = repo / "backend" / "app.py"
    source.parent.mkdir()
    source.write_text("old\n", encoding="utf-8")
    _git(repo, "add", "backend/app.py")
    _git(repo, "commit", "-m", "baseline")
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    capsule = build_repair_capsule(
        repair=repair(base_sha=base_sha),
        job=job(["backend/app.py"]),
        patch_value=patch_for(),
    )
    package = tmp_path / "capsule"
    package.mkdir()
    for name, content in capsule["files"].items():
        (package / name).write_bytes(content)

    unsafe_patch = (
        "diff --git a/backend/app.py b/backend/app.py\n"
        "old mode 100644\n"
        "new mode 100755\n"
        "index 3367afd..3e75765\n"
        "--- a/backend/app.py\n"
        "+++ b/backend/app.py\n"
        "@@ -1 +1 @@\n-old\n+new\n"
    ).encode()
    manifest = json.loads((package / "manifest.json").read_text())
    manifest["patchSha256"] = hashlib.sha256(unsafe_patch).hexdigest()
    manifest["patchByteCount"] = len(unsafe_patch)
    payload = {key: value for key, value in manifest.items() if key != "capsuleSha256"}
    manifest["capsuleSha256"] = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    (package / "repair.patch").write_bytes(unsafe_patch)
    (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(package / "verify.py"), "--repo", str(repo)],
        cwd=package,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "BLOCKED"
