"""Pure Zero-Trust Repair Capsule contracts with no network or write effects."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from typing import Any, Mapping
import uuid

try:
    from .rescue import (
        FAILURE_FAMILIES,
        MAX_REPAIR_CHANGED_FILES,
        canonical_sha256,
        extract_terminal_passing_test_readback,
        github_owner_repo,
        normalize_head_sha,
        normalize_repair_changed_files,
        redact_secret_text,
    )
except ImportError:
    from rescue import (
        FAILURE_FAMILIES,
        MAX_REPAIR_CHANGED_FILES,
        canonical_sha256,
        extract_terminal_passing_test_readback,
        github_owner_repo,
        normalize_head_sha,
        normalize_repair_changed_files,
        redact_secret_text,
    )

try:
    from .repair_capsule_verifier_source import REPAIR_CAPSULE_VERIFIER_SOURCE
except ImportError:
    from repair_capsule_verifier_source import REPAIR_CAPSULE_VERIFIER_SOURCE

REPAIR_CAPSULE_SCHEMA_VERSION = "sovereign.repair-capsule.v1"
MAX_REPAIR_CAPSULE_PATCH_BYTES = 2_000_000
MAX_REPAIR_CAPSULE_ARCHIVE_BYTES = 2_500_000
_SUPPORTED_FAMILIES = frozenset(item.code for item in FAILURE_FAMILIES)
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DIFF = re.compile(r"^diff --git a/(\S+) b/(\S+)$")
_INDEX = re.compile(r"^index [0-9a-f]{7,64}\.\.[0-9a-f]{7,64}(?: (100644|100755|120000|160000))?$")
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@(?: .*)?$")
_SECRET = (
    re.compile(r"github_pat_[A-Za-z0-9_]{8,}", re.I),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{8,}", re.I),
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{10,}", re.I),
    re.compile(r"Authorization:\s*(?:Bearer\s+)?[^\s\n]+", re.I),
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


def normalize_capsule_path(value: Any) -> str:
    path = str(value or "")
    if (
        not path
        or path.startswith(("/", "\\"))
        or re.match(r"^[A-Za-z]:/", path)
        or "\\" in path
        or any(ord(ch) < 32 or ord(ch) == 127 or ch.isspace() for ch in path)
    ):
        raise ValueError("capsule_patch_path_unsafe")
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("capsule_patch_path_unsafe")
    if ".git" in parts:
        raise ValueError("capsule_patch_git_metadata_forbidden")
    return path


def _patch_bytes(value: Any) -> bytes:
    patch = value if isinstance(value, bytes) else str(value).encode("utf-8") if isinstance(value, str) else b""
    if not patch:
        raise ValueError("capsule_patch_empty")
    if len(patch) > MAX_REPAIR_CAPSULE_PATCH_BYTES:
        raise ValueError("capsule_patch_too_large")
    if b"\x00" in patch:
        raise ValueError("capsule_patch_binary_forbidden")
    try:
        patch.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("capsule_patch_utf8_required") from exc
    return patch


def _marker(value: str, prefix: str) -> str:
    if not value.startswith(prefix):
        raise ValueError("capsule_patch_header_path_mismatch")
    return normalize_capsule_path(value[len(prefix):])


def parse_repair_patch_paths(value: Any) -> tuple[str, ...]:
    patch = _patch_bytes(value)
    text = patch.decode("utf-8")
    if any(pattern.search(text) for pattern in _SECRET):
        raise ValueError("capsule_patch_secret_material_detected")
    if "GIT binary patch" in text or "Binary files " in text:
        raise ValueError("capsule_patch_binary_forbidden")
    if "Subproject commit " in text:
        raise ValueError("capsule_patch_submodule_forbidden")
    lines = text.split("\n")
    paths: list[str] = []
    seen: set[str] = set()
    cursor = 0
    while cursor < len(lines):
        if cursor == len(lines) - 1 and not lines[cursor]:
            break
        header = _DIFF.fullmatch(lines[cursor])
        if not header:
            raise ValueError("capsule_patch_unsupported_diff_header")
        old_path, new_path = map(normalize_capsule_path, header.groups())
        if old_path != new_path:
            raise ValueError("capsule_patch_rename_forbidden")
        if new_path in seen:
            raise ValueError("capsule_patch_duplicate_path")
        seen.add(new_path)
        paths.append(new_path)
        cursor += 1
        kind = "modify"
        saw_index = False
        while cursor < len(lines) and not lines[cursor].startswith("--- "):
            line = lines[cursor]
            index_match = _INDEX.fullmatch(line)
            if index_match:
                if index_match.group(1) in {"120000", "160000"}:
                    raise ValueError("capsule_patch_symlink_or_submodule_forbidden")
                saw_index = True
            elif line == "new file mode 100644" and kind == "modify":
                kind = "add"
            elif line == "deleted file mode 100644" and kind == "modify":
                kind = "delete"
            elif line.startswith(("new file mode ", "deleted file mode ", "old mode ", "new mode ")):
                raise ValueError("capsule_patch_unsafe_mode_change")
            elif line.startswith(("similarity index ", "dissimilarity index ", "rename from ", "rename to ", "copy from ", "copy to ")):
                raise ValueError("capsule_patch_rename_or_copy_forbidden")
            else:
                raise ValueError("capsule_patch_unknown_metadata")
            cursor += 1
        if not saw_index or cursor + 1 >= len(lines) or not lines[cursor + 1].startswith("+++ "):
            raise ValueError("capsule_patch_file_headers_missing")
        old_marker, new_marker = lines[cursor][4:], lines[cursor + 1][4:]
        cursor += 2
        valid_headers = (
            kind == "modify" and _marker(old_marker, "a/") == new_path and _marker(new_marker, "b/") == new_path
        ) or (
            kind == "add" and old_marker == "/dev/null" and _marker(new_marker, "b/") == new_path
        ) or (
            kind == "delete" and _marker(old_marker, "a/") == new_path and new_marker == "/dev/null"
        )
        if not valid_headers:
            raise ValueError("capsule_patch_header_path_mismatch")
        saw_hunk = False
        while cursor < len(lines) and not lines[cursor].startswith("diff --git "):
            line = lines[cursor]
            if cursor == len(lines) - 1 and not line:
                cursor += 1
                break
            if _HUNK.fullmatch(line):
                saw_hunk = True
            elif not (saw_hunk and (line.startswith((" ", "+", "-")) or line == r"\ No newline at end of file")):
                raise ValueError("capsule_patch_unknown_hunk_syntax")
            cursor += 1
        if not saw_hunk:
            raise ValueError("capsule_patch_hunk_missing")
    if not paths:
        raise ValueError("capsule_patch_empty")
    return tuple(sorted(paths))


def _changed_files(value: Any) -> tuple[str, ...]:
    paths = tuple(normalize_capsule_path(item) for item in normalize_repair_changed_files(value))
    if len(paths) != len(set(paths)):
        raise ValueError("capsule_changed_file_duplicate")
    return tuple(sorted(paths))


def repair_capsule_repository_identity(repository: Any) -> str:
    owner, repo = github_owner_repo(repository)
    return hashlib.sha256(f"github:{owner.lower()}/{repo.lower()}".encode()).hexdigest()


def _readme(base_sha: str, paths: tuple[str, ...]) -> str:
    changed = "\n".join(f"- `{path}`" for path in paths)
    return (
        "# Sovereign Zero-Trust Repair Capsule\n\n"
        "This package performs no network request and never applies a patch automatically.\n\n"
        f"Required repository HEAD: `{base_sha}`\n\nChanged paths:\n{changed}\n\n"
        "Verify: `python verify.py --repo /path/to/repository`\n\n"
        "Apply only after verification: `git -C /path/to/repository apply repair.patch`\n"
    )


def build_repair_capsule_verifier() -> str:
    return REPAIR_CAPSULE_VERIFIER_SOURCE


def _receipt_head_sha(receipt: Mapping[str, object] | None) -> str:
    if not isinstance(receipt, Mapping):
        return "0" * 64
    header = receipt.get("header")
    candidate = str(header.get("hash") if isinstance(header, Mapping) else "").strip().lower()
    return candidate if _SHA256.fullmatch(candidate) else "0" * 64


def build_repair_capsule_manifest(
    *,
    repair: Mapping[str, Any],
    job: Mapping[str, Any],
    patch_value: Any,
    agent_receipts: tuple[Mapping[str, object], ...] = (),
) -> dict[str, Any]:
    blockers: list[str] = []
    try:
        repair_id = str(uuid.UUID(str(repair.get("repair_id") or repair.get("repairId") or "")))
    except (ValueError, TypeError, AttributeError):
        repair_id = ""; blockers.append("capsule_repair_id_invalid")
    try:
        repository_identity = repair_capsule_repository_identity(repair.get("repository"))
    except ValueError:
        repository_identity = ""; blockers.append("capsule_repository_identity_invalid")
    try:
        base_sha = normalize_head_sha(repair.get("base_sha") or repair.get("baseSha"))
    except ValueError:
        base_sha = ""; blockers.append("capsule_base_sha_invalid")
    family = str(repair.get("failure_family") or repair.get("failureFamily") or "")
    if family not in _SUPPORTED_FAMILIES:
        blockers.append("capsule_failure_family_unsupported")
    outcome_sha = str(repair.get("outcome_contract_sha256") or repair.get("outcomeContractSha256") or "").lower()
    if not _SHA256.fullmatch(outcome_sha):
        blockers.append("capsule_outcome_contract_sha256_invalid")
    try:
        patch = _patch_bytes(patch_value)
    except ValueError as exc:
        patch = b""; blockers.append(str(exc))
    parsed: tuple[str, ...] = ()
    if patch:
        try:
            parsed = parse_repair_patch_paths(patch)
        except ValueError as exc:
            blockers.append(str(exc))
    try:
        persisted = _changed_files(job.get("changed_files") or job.get("changedFiles") or [])
    except ValueError as exc:
        persisted = (); blockers.append(str(exc))
    if not persisted:
        blockers.append("capsule_changed_file_evidence_missing")
    if parsed != persisted:
        blockers.append("capsule_changed_file_identity_mismatch")
    if len(parsed) > MAX_REPAIR_CHANGED_FILES:
        blockers.append(f"changed_file_limit_exceeded:{len(parsed)}>{MAX_REPAIR_CHANGED_FILES}")
    raw_summary = str(job.get("test_summary") or job.get("testSummary") or "")
    if len(raw_summary) > 4000:
        blockers.append("capsule_test_evidence_too_large")
    summary = redact_secret_text(raw_summary, 4000)
    if not summary:
        blockers.append("capsule_test_evidence_missing")
    if "[REDACTED]" in summary or (len(raw_summary) <= 4000 and summary != raw_summary):
        blockers.append("capsule_test_evidence_secret_material")

    # Issue #1122: bind the Capsule to the same causal terminal passing-test
    # readback the ProofPack uses. An unsupported application-bug case (targeted
    # tests did not pass in the repair workspace) must not produce a Capsule.
    repository = str(repair.get("repository") or "")
    readback = extract_terminal_passing_test_readback(
        agent_receipts,
        repository=repository,
        base_sha=base_sha,
    )
    if not readback["ok"]:
        blockers.append("capsule_targeted_tests_not_passed")
    mutation_receipt_sha = _receipt_head_sha(readback["mutation_receipt"])
    final_passing_readback_sha = _receipt_head_sha(readback["final_readback_receipt"])

    verifier = build_repair_capsule_verifier(); readme = _readme(base_sha, parsed)
    blockers = list(dict.fromkeys(blockers))
    payload = {
        "schemaVersion": REPAIR_CAPSULE_SCHEMA_VERSION,
        "product": "sovereign-rescue",
        "repairId": repair_id,
        "repositoryIdentitySha256": repository_identity,
        "baseSha": base_sha,
        "failureFamily": family,
        "outcomeContractSha256": outcome_sha,
        "changedFiles": list(parsed),
        "patchSha256": hashlib.sha256(patch).hexdigest(),
        "patchByteCount": len(patch),
        "testEvidenceSha256": hashlib.sha256(summary.encode()).hexdigest(),
        "mutationReceiptSha256": mutation_receipt_sha,
        "finalPassingReadbackReceiptSha256": final_passing_readback_sha,
        "verifierSha256": hashlib.sha256(verifier.encode()).hexdigest(),
        "readmeSha256": hashlib.sha256(readme.encode()).hexdigest(),
        "maxChangedFiles": MAX_REPAIR_CHANGED_FILES,
        "productionMutationIncluded": False,
        "blockers": blockers,
        "ready": not blockers,
        "secretValuesReturned": False,
    }
    return {**payload, "capsuleSha256": canonical_sha256(payload)}


def verify_repair_capsule_manifest(manifest: Mapping[str, Any], patch_value: Any) -> bool:
    try:
        patch = _patch_bytes(patch_value); paths = parse_repair_patch_paths(patch)
        payload = {key: value for key, value in manifest.items() if key != "capsuleSha256"}
        readme = _readme(str(manifest.get("baseSha") or ""), paths); verifier = build_repair_capsule_verifier()
        return bool(
            manifest.get("schemaVersion") == REPAIR_CAPSULE_SCHEMA_VERSION
            and manifest.get("ready") is True and manifest.get("blockers") == []
            and manifest.get("productionMutationIncluded") is False and manifest.get("secretValuesReturned") is False
            and _SHA40.fullmatch(str(manifest.get("baseSha") or ""))
            and _SHA256.fullmatch(str(manifest.get("repositoryIdentitySha256") or ""))
            and _SHA256.fullmatch(str(manifest.get("outcomeContractSha256") or ""))
            and _SHA256.fullmatch(str(manifest.get("mutationReceiptSha256") or ""))
            and _SHA256.fullmatch(str(manifest.get("finalPassingReadbackReceiptSha256") or ""))
            and tuple(manifest.get("changedFiles") or ()) == paths and len(paths) <= MAX_REPAIR_CHANGED_FILES
            and manifest.get("patchByteCount") == len(patch) and manifest.get("patchSha256") == hashlib.sha256(patch).hexdigest()
            and manifest.get("verifierSha256") == hashlib.sha256(verifier.encode()).hexdigest()
            and manifest.get("readmeSha256") == hashlib.sha256(readme.encode()).hexdigest()
            and manifest.get("capsuleSha256") == canonical_sha256(payload)
        )
    except (TypeError, ValueError, UnicodeDecodeError):
        return False


def build_repair_capsule(
    *,
    repair: Mapping[str, Any],
    job: Mapping[str, Any],
    patch_value: Any,
    agent_receipts: tuple[Mapping[str, object], ...] = (),
) -> dict[str, Any]:
    manifest = build_repair_capsule_manifest(
        repair=repair, job=job, patch_value=patch_value, agent_receipts=agent_receipts
    )
    if manifest.get("ready") is not True:
        return {"manifest": manifest, "files": {}, "ready": False}
    patch = _patch_bytes(patch_value)
    if not verify_repair_capsule_manifest(manifest, patch):
        return {"manifest": manifest, "files": {}, "ready": False}
    verifier = build_repair_capsule_verifier(); readme = _readme(str(manifest["baseSha"]), tuple(manifest["changedFiles"]))
    return {
        "manifest": manifest,
        "files": {
            "repair.patch": patch,
            "manifest.json": (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(),
            "verify.py": verifier.encode(),
            "README.md": readme.encode(),
        },
        "ready": True,
    }


def build_repair_capsule_archive(capsule: Mapping[str, Any]) -> bytes:
    """Package exactly the canonical Capsule files into one deterministic ZIP."""

    if capsule.get("ready") is not True:
        raise ValueError("capsule_not_ready")
    files = capsule.get("files")
    if not isinstance(files, Mapping):
        raise ValueError("capsule_files_missing")
    canonical_names = ("README.md", "manifest.json", "repair.patch", "verify.py")
    if set(files) != set(canonical_names):
        raise ValueError("capsule_file_set_invalid")

    target = io.BytesIO()
    with zipfile.ZipFile(
        target,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=True,
    ) as archive:
        for name in canonical_names:
            value = files[name]
            if not isinstance(value, bytes):
                raise ValueError("capsule_file_bytes_required")
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = ((0o100755 if name == "verify.py" else 0o100644) << 16)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, value, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    payload = target.getvalue()
    if not payload or len(payload) > MAX_REPAIR_CAPSULE_ARCHIVE_BYTES:
        raise ValueError("capsule_archive_size_invalid")
    return payload
