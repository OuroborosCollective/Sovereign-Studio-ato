from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent_runtime.repair_capsule import (
    build_repair_capsule,
    build_repair_capsule_archive,
)
from agent_runtime.repair_capsule_benchmark import (
    NOT_MEASURED,
    STATUS_BLOCKED,
    STATUS_NOT_RUN,
    STATUS_VERIFIED,
    audit_capsule_archive,
    benchmark_capsule_delivery,
)

BASE_SHA_PLACEHOLDER = "a" * 40
OUTCOME_SHA = "c" * 64
REPAIR_ID = "00000000-0000-4000-8000-000000000456"


def _repair(base_sha: str) -> dict[str, str]:
    return {
        "repair_id": REPAIR_ID,
        "repository": "https://github.com/Acme/SandboxExample",
        "base_sha": base_sha,
        "failure_family": "github_actions_ci",
        "outcome_contract_sha256": OUTCOME_SHA,
    }


def _job(paths: list[str]) -> dict[str, object]:
    return {"changed_files": paths, "test_summary": "targeted tests passed"}


def _patch(path: str = "src/app.py", before: str = "old", after: str = "new") -> bytes:
    return (
        f"diff --git a/{path} b/{path}\n"
        "index 3367afd..3e75765 100644\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1 +1 @@\n"
        f"-{before}\n"
        f"+{after}\n"
    ).encode("utf-8")


def _ready_archive() -> bytes:
    capsule = build_repair_capsule(
        repair=_repair(BASE_SHA_PLACEHOLDER),
        job=_job(["src/app.py"]),
        patch_value=_patch(),
    )
    assert capsule["ready"] is True
    return build_repair_capsule_archive(capsule)


def _init_clone(tmp_path: Path, head_sha: str) -> Path:
    repo = tmp_path / "clone"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("old\n")
    subprocess.run(
        ["git", "-C", str(repo), "add", "."], check=True, env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"}
    )
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True, env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"})
    actual = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    # Rebuild the capsule bound to the real clone head so the base matches.
    return repo, actual


def test_static_audit_proves_zero_write_by_construction() -> None:
    audit = audit_capsule_archive(_ready_archive())
    assert audit["status"] == STATUS_VERIFIED
    assert audit["blockers"] == []
    assert audit["githubWriteCount"] == 0
    assert audit["productionMutationIncluded"] is False
    assert audit["secretValuesReturned"] is False
    assert audit["schemaVersion"] == "sovereign.repair-capsule.v1"
    assert audit["changedFiles"] == ["src/app.py"]


def test_static_audit_blocks_tampered_member_set() -> None:
    capsule = build_repair_capsule(
        repair=_repair(BASE_SHA_PLACEHOLDER),
        job=_job(["src/app.py"]),
        patch_value=_patch(),
    )
    capsule["files"]["extra.txt"] = b"tamper"
    import zipfile
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in capsule["files"].items():
            archive.writestr(name, data)
    audit = audit_capsule_archive(buffer.getvalue())
    assert audit["status"] == STATUS_BLOCKED
    assert "capsule_member_set_invalid" in audit["blockers"]


def test_static_audit_blocks_production_mutation_or_secret_flags() -> None:
    capsule = build_repair_capsule(
        repair=_repair(BASE_SHA_PLACEHOLDER),
        job=_job(["src/app.py"]),
        patch_value=_patch(),
    )
    manifest = dict(capsule["manifest"])
    manifest["productionMutationIncluded"] = True
    capsule["manifest"] = manifest
    capsule["files"]["manifest.json"] = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    import zipfile
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("README.md", "manifest.json", "repair.patch", "verify.py"):
            archive.writestr(name, capsule["files"][name])
    audit = audit_capsule_archive(buffer.getvalue())
    assert audit["status"] == STATUS_BLOCKED
    assert "capsule_production_mutation_included" in audit["blockers"]


def test_benchmark_without_clone_records_not_measured_and_does_not_invent() -> None:
    report = benchmark_capsule_delivery(archive_bytes=_ready_archive())
    assert report["status"] == STATUS_NOT_RUN
    assert report["blockers"] == ["clone_dir_not_provided"]
    assert report["freshClone"]["headSha"] == NOT_MEASURED
    assert report["verifier"] == NOT_MEASURED
    assert report["gitApplyCheck"] == NOT_MEASURED
    assert report["userExperience"]["modeSelection"] == NOT_MEASURED
    assert report["comparison"]["draftPrGithubWriteCount"] == NOT_MEASURED
    assert report["comparison"]["capsuleGithubWriteCount"] == 0


def test_benchmark_fails_closed_on_base_sha_mismatch(tmp_path: Path) -> None:
    repo, real_head = _init_clone(tmp_path, BASE_SHA_PLACEHOLDER)
    archive = build_repair_capsule_archive(
        build_repair_capsule(
            repair=_repair("0" * 40),
            job=_job(["src/app.py"]),
            patch_value=_patch(),
        )
    )
    report = benchmark_capsule_delivery(archive_bytes=archive, clone_dir=repo)
    assert report["status"] == STATUS_BLOCKED
    assert "fresh_clone_base_sha_mismatch" in report["blockers"]
    assert report["freshClone"]["headSha"] == real_head
    assert report["freshClone"]["baseShaMatches"] is False


def test_benchmark_verifies_and_applies_against_real_fresh_clone(tmp_path: Path) -> None:
    repo, real_head = _init_clone(tmp_path, BASE_SHA_PLACEHOLDER)
    archive = build_repair_capsule_archive(
        build_repair_capsule(
            repair=_repair(real_head),
            job=_job(["src/app.py"]),
            patch_value=_patch(),
        )
    )
    before_hash = hashlib.sha256((repo / "src" / "app.py").read_bytes()).hexdigest()
    report = benchmark_capsule_delivery(
        archive_bytes=archive,
        clone_dir=repo,
        workspace_changed_file_hashes={"src/app.py": hashlib.sha256(b"new\n").hexdigest()},
        targeted_test_command=["python3", "-c", "import sys; sys.exit(0)"],
        draft_pr_github_write_count=1,
    )
    assert report["status"] == STATUS_VERIFIED, report
    assert report["blockers"] == []
    assert report["freshClone"]["baseShaMatches"] is True
    assert report["verifier"]["ok"] is True
    assert report["gitApplyCheck"]["ok"] is True
    assert report["localApply"]["ok"] is True
    assert report["changedFileHashParity"] is True
    assert report["targetedTests"]["parity"] is True
    assert report["comparison"]["draftPrGithubWriteCount"] == 1
    # The harness must roll back the local apply, leaving the clone pristine.
    after_hash = hashlib.sha256((repo / "src" / "app.py").read_bytes()).hexdigest()
    assert after_hash == before_hash


def test_benchmark_blocks_when_targeted_tests_diverge_after_apply(tmp_path: Path) -> None:
    repo, real_head = _init_clone(tmp_path, BASE_SHA_PLACEHOLDER)
    archive = build_repair_capsule_archive(
        build_repair_capsule(
            repair=_repair(real_head),
            job=_job(["src/app.py"]),
            patch_value=_patch(),
        )
    )
    report = benchmark_capsule_delivery(
        archive_bytes=archive,
        clone_dir=repo,
        workspace_changed_file_hashes={"src/app.py": hashlib.sha256(b"new\n").hexdigest()},
        targeted_test_command=["python3", "-c", "import sys; sys.exit(2)"],
    )
    assert report["status"] == STATUS_BLOCKED
    assert "targeted_test_parity_failed" in report["blockers"]
