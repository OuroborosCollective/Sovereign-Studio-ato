from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile
from typing import Mapping

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent_runtime.repair_capsule import (
    MAX_REPAIR_CAPSULE_PATCH_BYTES,
    REPAIR_CAPSULE_SCHEMA_VERSION,
    build_repair_capsule,
    build_repair_capsule_archive,
    build_repair_capsule_manifest,
    build_repair_capsule_verifier,
    parse_repair_patch_paths,
    verify_repair_capsule_manifest,
)
from agent_runtime.agent_run_receipts import build_agent_run_receipt
from agent_runtime.rescue import extract_terminal_passing_test_readback


BASE_SHA = "a" * 40
OTHER_SHA = "b" * 40
OUTCOME_SHA = "c" * 64
REPAIR_ID = "00000000-0000-4000-8000-000000000123"
REPOSITORY = "https://github.com/Acme/Example"


def repair(*, base_sha: str = BASE_SHA) -> dict[str, str]:
    return {
        "repair_id": REPAIR_ID,
        "repository": REPOSITORY,
        "base_sha": base_sha,
        "failure_family": "github_actions_ci",
        "outcome_contract_sha256": OUTCOME_SHA,
    }


def job(paths: list[str], summary: str = "targeted tests passed") -> dict[str, object]:
    return {
        "changed_files": paths,
        "test_summary": summary,
    }


def _mutation_receipt(*, base_sha: str = BASE_SHA, diff_sha: str = "3" * 64) -> dict[str, object]:
    return build_agent_run_receipt(
        sequence=0,
        repository=REPOSITORY,
        base_commit_sha=base_sha,
        mcp_revision=base_sha,
        mcp_image_digest="sha256:" + "e" * 64,
        mcp_revision_verified=True,
        agent_run_id="run-capsule",
        tool_name="write_file",
        call_id="call-capsule-write",
        operation_identity="agent-repository-tool:free_single_agent:write_file",
        input_sha256="1" * 64,
        output_sha256="2" * 64,
        diff_sha256=diff_sha,
        test_evidence_sha256="4" * 64,
        evidence_gate_result="BLOCKED",
        mutation_performed=True,
        observed_effect="workspace-write",
        authoritative_readback_sha256="5" * 64,
        previous_receipt_sha256="0" * 64,
    )


def _passing_test_receipt(
    mutation: Mapping[str, object],
    *,
    diff_sha: str = "3" * 64,
    changed_paths: tuple[str, ...] = ("backend/app.py",),
) -> dict[str, object]:
    return build_agent_run_receipt(
        sequence=1,
        repository=REPOSITORY,
        base_commit_sha=str(mutation["body"]["base_commit_sha"]),
        mcp_revision=str(mutation["body"]["base_commit_sha"]),
        mcp_image_digest="sha256:" + "e" * 64,
        mcp_revision_verified=True,
        agent_run_id="run-capsule",
        tool_name="test",
        call_id="call-capsule-test",
        operation_identity="agent-repository-tool:free_single_agent:test",
        input_sha256="6" * 64,
        output_sha256="7" * 64,
        diff_sha256=diff_sha,
        test_evidence_sha256="8" * 64,
        evidence_gate_result="PASS",
        mutation_performed=False,
        observed_effect="read",
        authoritative_readback_sha256="5" * 64,
        previous_receipt_sha256=str(mutation["header"]["hash"]),
        test_execution_kind="qualifying-test",
        changed_paths=changed_paths,
    )


def passing_receipts(
    *,
    base_sha: str = BASE_SHA,
    diff_sha: str = "3" * 64,
    changed_paths: tuple[str, ...] = ("backend/app.py",),
) -> tuple[dict[str, object], ...]:
    mutation = _mutation_receipt(base_sha=base_sha, diff_sha=diff_sha)
    test = _passing_test_receipt(mutation, diff_sha=diff_sha, changed_paths=changed_paths)
    return (mutation, test)


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
    receipts = passing_receipts()
    first = build_repair_capsule_manifest(
        repair=repair(),
        job=job(["backend/app.py"]),
        patch_value=patch,
        agent_receipts=receipts,
    )
    second = build_repair_capsule_manifest(
        repair=repair(),
        job=job(["backend/app.py"]),
        patch_value=patch,
        agent_receipts=receipts,
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
    assert first["mutationReceiptSha256"] == receipts[0]["header"]["hash"]
    assert first["finalPassingReadbackReceiptSha256"] == receipts[1]["header"]["hash"]
    assert verify_repair_capsule_manifest(first, patch) is True


def test_patch_or_revision_change_changes_capsule_identity() -> None:
    original = build_repair_capsule_manifest(
        repair=repair(),
        job=job(["backend/app.py"]),
        patch_value=patch_for(after="new"),
        agent_receipts=passing_receipts(),
    )
    changed_patch = build_repair_capsule_manifest(
        repair=repair(),
        job=job(["backend/app.py"]),
        patch_value=patch_for(after="newer"),
        agent_receipts=passing_receipts(),
    )
    changed_base = build_repair_capsule_manifest(
        repair=repair(base_sha=OTHER_SHA),
        job=job(["backend/app.py"]),
        patch_value=patch_for(after="new"),
        agent_receipts=passing_receipts(base_sha=OTHER_SHA),
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
        agent_receipts=passing_receipts(changed_paths=("backend/alpha.py", "src/zeta.py")),
    )
    assert ready["ready"] is True
    assert ready["changedFiles"] == ["backend/alpha.py", "src/zeta.py"]

    mismatch = build_repair_capsule_manifest(
        repair=repair(),
        job=job(["src/zeta.py"]),
        patch_value=combined,
        agent_receipts=passing_receipts(),
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
        agent_receipts=passing_receipts(changed_paths=("backend/über.py",)),
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


def test_capsule_archive_is_deterministic_and_contains_only_canonical_files() -> None:
    capsule = build_repair_capsule(
        repair=repair(),
        job=job(["backend/app.py"]),
        patch_value=patch_for(),
        agent_receipts=passing_receipts(),
    )
    first = build_repair_capsule_archive(capsule)
    second = build_repair_capsule_archive(capsule)
    assert first == second

    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        assert archive.namelist() == ["README.md", "manifest.json", "repair.patch", "verify.py"]
        assert archive.read("repair.patch") == capsule["files"]["repair.patch"]
        assert archive.read("manifest.json") == capsule["files"]["manifest.json"]
        assert all(item.date_time == (1980, 1, 1, 0, 0, 0) for item in archive.infolist())


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
        agent_receipts=passing_receipts(base_sha=base_sha),
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
        agent_receipts=passing_receipts(base_sha=base_sha),
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



def _failing_test_receipt(mutation: Mapping[str, object]) -> dict[str, object]:
    """A qualifying-test receipt whose evidence gate is FAIL, not PASS."""
    return build_agent_run_receipt(
        sequence=1,
        repository=REPOSITORY,
        base_commit_sha=str(mutation["body"]["base_commit_sha"]),
        mcp_revision=str(mutation["body"]["base_commit_sha"]),
        mcp_image_digest="sha256:" + "e" * 64,
        mcp_revision_verified=True,
        agent_run_id="run-capsule",
        tool_name="test",
        call_id="call-capsule-test-fail",
        operation_identity="agent-repository-tool:free_single_agent:test",
        input_sha256="6" * 64,
        output_sha256="7" * 64,
        diff_sha256="3" * 64,
        test_evidence_sha256="8" * 64,
        evidence_gate_result="FAIL",
        mutation_performed=False,
        observed_effect="read",
        authoritative_readback_sha256="5" * 64,
        previous_receipt_sha256=str(mutation["header"]["hash"]),
        test_execution_kind="qualifying-test",
        changed_paths=("backend/app.py",),
    )


def test_capsule_blocks_unsupported_application_bug_case() -> None:
    """Issue #1122: an unsupported application-bug case (targeted tests did not
    pass in the repair workspace) must not produce a successful Capsule."""
    patch = patch_for()
    mutation = _mutation_receipt()
    failing_chain = (mutation, _failing_test_receipt(mutation))

    manifest = build_repair_capsule_manifest(
        repair=repair(),
        job=job(["backend/app.py"]),
        patch_value=patch,
        agent_receipts=failing_chain,
    )
    assert manifest["ready"] is False
    assert "capsule_targeted_tests_not_passed" in manifest["blockers"]
    assert manifest["mutationReceiptSha256"] == "0" * 64
    assert manifest["finalPassingReadbackReceiptSha256"] == "0" * 64

    capsule = build_repair_capsule(
        repair=repair(),
        job=job(["backend/app.py"]),
        patch_value=patch,
        agent_receipts=failing_chain,
    )
    assert capsule["ready"] is False
    assert capsule["files"] == {}


def test_capsule_blocks_when_no_agent_run_receipts_exist() -> None:
    """Issue #1122: without persisted Agent-Run receipts there is no causal
    proof the targeted tests passed, so the Capsule must fail closed."""
    patch = patch_for()
    manifest = build_repair_capsule_manifest(
        repair=repair(),
        job=job(["backend/app.py"]),
        patch_value=patch,
        agent_receipts=(),
    )
    assert manifest["ready"] is False
    assert "capsule_targeted_tests_not_passed" in manifest["blockers"]
    assert manifest["mutationReceiptSha256"] == "0" * 64
    assert manifest["finalPassingReadbackReceiptSha256"] == "0" * 64


def test_capsule_blocks_when_readback_diff_does_not_match_terminal_mutation() -> None:
    """Issue #1122: a passing test readback that is not causally bound to the
    terminal mutation diff cannot satisfy the Capsule contract."""
    patch = patch_for()
    mutation = _mutation_receipt(diff_sha="3" * 64)
    # Passing test but bound to a different diff than the terminal mutation.
    mismatched_pass = _passing_test_receipt(mutation, diff_sha="9" * 64)
    mismatched_chain = (mutation, mismatched_pass)

    manifest = build_repair_capsule_manifest(
        repair=repair(),
        job=job(["backend/app.py"]),
        patch_value=patch,
        agent_receipts=mismatched_chain,
    )
    assert manifest["ready"] is False
    assert "capsule_targeted_tests_not_passed" in manifest["blockers"]

