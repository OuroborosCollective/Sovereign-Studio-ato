"""Causal Hugging Face recovery for the Sovereign shadow-inference dataset.

The recovery lane never rewrites canonical historical receipts. It verifies
embedded receipt hashes, separates source-revision truth from Hugging Face
publication history, projects only provenance-verified receipts into the live
Dataset Viewer, and records unresolved/misbound legacy receipts in a separate
supersession ledger.

A live Hub mutation is allowed only with explicit owner approval and an exact
pre-write Hub revision. Every written byte is read back and hash-verified.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from evidence_observatory_contracts import canonical_json, sha256_json
from evidence_observatory_publisher import _load_huggingface_runtime_token

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
SECRET_PATTERNS = (
    re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
)

VIEWER_STRING_FIELDS = (
    "schemaVersion",
    "recordType",
    "observedAt",
    "provider",
    "model",
    "providerSurface",
    "finishReason",
    "truthVerdict",
    "sourceRevision",
    "outputSha256",
    "promptSha256",
    "planSha256",
    "primaryAuthority",
    "credentialSource",
    "promptClassification",
    "costClaim",
)
VIEWER_INT_FIELDS = (
    "maxOutputTokens",
    "seed",
    "latencyMs",
    "requestCount",
    "automaticRetries",
)
VIEWER_BOOL_FIELDS = (
    "automaticFallback",
    "literalMatch",
    "secretValuesReturned",
)


@dataclass(frozen=True)
class ShadowRecoveryArtifact:
    path: str
    content: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


def _valid_sha256(value: Any) -> bool:
    return bool(SHA256_RE.fullmatch(str(value or "").strip().lower()))


def _valid_revision(value: Any) -> bool:
    return bool(GIT_REVISION_RE.fullmatch(str(value or "").strip().lower()))


def _verify_embedded_receipt_hash(receipt: dict[str, Any]) -> str:
    claimed = str(receipt.get("receiptSha256") or "").strip().lower()
    if not _valid_sha256(claimed):
        raise RuntimeError("shadow_receipt_hash_invalid")
    base = dict(receipt)
    base.pop("receiptSha256", None)
    if sha256_json(base) != claimed:
        raise RuntimeError("shadow_receipt_hash_mismatch")
    return claimed


def _assert_public_safe(value: Any, *, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if normalized in {"token", "apikey", "password", "authorization", "credential", "secret"}:
                raise RuntimeError(f"shadow_public_secret_field:{path}.{key}")
            _assert_public_safe(item, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_public_safe(item, path=f"{path}[{index}]")
        return
    if isinstance(value, str):
        for pattern in SECRET_PATTERNS:
            if pattern.search(value):
                raise RuntimeError(f"shadow_public_secret_shape:{path}")


def _optional_string(receipt: dict[str, Any], field: str) -> str | None:
    value = receipt.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeError(f"shadow_viewer_type_invalid:{field}")
    return value


def _optional_int(receipt: dict[str, Any], field: str) -> int | None:
    value = receipt.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(f"shadow_viewer_type_invalid:{field}")
    return value


def _optional_bool(receipt: dict[str, Any], field: str) -> bool | None:
    value = receipt.get(field)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise RuntimeError(f"shadow_viewer_type_invalid:{field}")
    return value


def classify_source_revision(
    source_revision: str,
    *,
    sovereign_revisions: set[str],
    hf_publication_revisions: set[str],
) -> str:
    revision = str(source_revision or "").strip().lower()
    if not _valid_revision(revision):
        return "INVALID_REVISION"
    if revision in sovereign_revisions:
        return "SOVEREIGN_SOURCE_VERIFIED"
    if revision in hf_publication_revisions:
        return "MISBOUND_HF_PUBLICATION_REVISION"
    return "SOURCE_REVISION_UNRESOLVED"


def _viewer_row(receipt: dict[str, Any], *, receipt_path: str, source_repository: str) -> dict[str, Any]:
    receipt_sha = _verify_embedded_receipt_hash(receipt)
    source_revision = str(receipt.get("sourceRevision") or "").strip().lower()
    if not _valid_revision(source_revision):
        raise RuntimeError("shadow_source_revision_invalid")

    row: dict[str, Any] = {
        "receiptSha256": receipt_sha,
        "receiptPath": receipt_path,
        "sourceRepository": source_repository,
        "sourceRevisionVerified": True,
    }
    for field in VIEWER_STRING_FIELDS:
        row[field] = _optional_string(receipt, field)
    for field in VIEWER_INT_FIELDS:
        row[field] = _optional_int(receipt, field)
    for field in VIEWER_BOOL_FIELDS:
        row[field] = _optional_bool(receipt, field)

    usage = receipt.get("usage")
    if usage is not None and not isinstance(usage, dict):
        raise RuntimeError("shadow_usage_not_object")
    row["usageJson"] = canonical_json(usage) if usage is not None else None
    row["usageSha256"] = sha256_json(usage) if usage is not None else None
    row["viewerRowSha256"] = sha256_json(row)
    _assert_public_safe(row)
    return row


def _jsonl(rows: Iterable[dict[str, Any]]) -> bytes:
    values = list(rows)
    return ("\n".join(canonical_json(row) for row in values) + ("\n" if values else "")).encode("utf-8")


def _dataset_card(existing_readme: str, *, candidate_revision: str, verified_count: int, legacy_count: int) -> bytes:
    body = existing_readme
    if body.startswith("---\n"):
        end = body.find("\n---\n", 4)
        if end >= 0:
            body = body[end + 5 :]

    frontmatter = """---
configs:
- config_name: receipts_current
  data_files:
  - split: train
    path: data/current/receipts-viewer.jsonl
- config_name: provenance_legacy
  data_files:
  - split: train
    path: data/provenance/supersessions.jsonl
- config_name: seed
  data_files:
  - split: train
    path: data/shadow_receipts.jsonl
---
"""
    notice = (
        "\n> **Current publication truth.** The default live receipt view is now `receipts_current`, "
        "which contains only receipt hashes whose Sovereign source revision was independently resolved. "
        "Historical raw receipts are preserved byte-for-byte but unresolved or misbound source revisions are "
        "listed in `provenance_legacy` and are not current source truth. "
        f"Current Sovereign candidate: `{candidate_revision}`. Verified live receipts: {verified_count}. "
        f"Legacy provenance records: {legacy_count}.\n\n"
    )
    return (frontmatter + notice + body.lstrip()).encode("utf-8")


def build_shadow_recovery_bundle(
    *,
    receipts: list[dict[str, Any]],
    receipt_paths: list[str],
    sovereign_revisions: set[str],
    hf_publication_revisions: set[str],
    source_repository: str,
    candidate_revision: str,
    hf_repo_id: str,
    expected_hf_revision: str,
    existing_readme: str,
) -> dict[str, Any]:
    if not receipts or len(receipts) != len(receipt_paths):
        raise RuntimeError("shadow_recovery_receipt_path_count_mismatch")
    candidate = str(candidate_revision or "").strip().lower()
    if not _valid_revision(candidate) or candidate not in sovereign_revisions:
        raise RuntimeError("shadow_candidate_revision_not_verified")
    if not source_repository or not hf_repo_id or not expected_hf_revision:
        raise RuntimeError("shadow_recovery_target_identity_missing")

    verified_rows: list[dict[str, Any]] = []
    supersessions: list[dict[str, Any]] = []
    seen: set[str] = set()
    original_hashes: list[str] = []

    for receipt, receipt_path in zip(receipts, receipt_paths, strict=True):
        if not isinstance(receipt, dict):
            raise RuntimeError("shadow_receipt_not_object")
        _assert_public_safe(receipt)
        receipt_sha = _verify_embedded_receipt_hash(receipt)
        if receipt_sha in seen:
            raise RuntimeError("shadow_duplicate_receipt")
        seen.add(receipt_sha)
        original_hashes.append(receipt_sha)

        claimed_revision = str(receipt.get("sourceRevision") or "").strip().lower()
        classification = classify_source_revision(
            claimed_revision,
            sovereign_revisions=sovereign_revisions,
            hf_publication_revisions=hf_publication_revisions,
        )
        if classification == "SOVEREIGN_SOURCE_VERIFIED":
            verified_rows.append(_viewer_row(receipt, receipt_path=receipt_path, source_repository=source_repository))
            continue

        supersession = {
            "schemaVersion": "sovereign.hf-shadow-provenance-supersession.v1",
            "receiptSha256": receipt_sha,
            "receiptPath": receipt_path,
            "claimedSourceRevision": claimed_revision or None,
            "classification": classification,
            "currentTruthEligible": False,
            "canonicalReceiptMutated": False,
            "resolution": "PRESERVE_RAW_RECEIPT_AND_EXCLUDE_FROM_CURRENT_VIEWER",
        }
        supersession["supersessionSha256"] = sha256_json(supersession)
        supersessions.append(supersession)

    if not verified_rows:
        raise RuntimeError("shadow_recovery_no_verified_receipts")

    viewer = ShadowRecoveryArtifact("data/current/receipts-viewer.jsonl", _jsonl(verified_rows))
    legacy = ShadowRecoveryArtifact("data/provenance/supersessions.jsonl", _jsonl(supersessions))
    readme = ShadowRecoveryArtifact(
        "README.md",
        _dataset_card(
            existing_readme,
            candidate_revision=candidate,
            verified_count=len(verified_rows),
            legacy_count=len(supersessions),
        ),
    )

    manifest: dict[str, Any] = {
        "schemaVersion": "sovereign.hf-shadow-publication-manifest.v2",
        "sourceRepository": source_repository,
        "candidateRevision": candidate,
        "hfRepoId": hf_repo_id,
        "prewriteHfRevision": expected_hf_revision,
        "canonicalReceiptCount": len(receipts),
        "verifiedViewerReceiptCount": len(verified_rows),
        "legacyProvenanceCount": len(supersessions),
        "canonicalReceiptHashes": original_hashes,
        "canonicalReceiptsMutated": False,
        "viewerPath": viewer.path,
        "viewerSha256": viewer.sha256,
        "supersessionPath": legacy.path,
        "supersessionSha256": legacy.sha256,
        "readmeSha256": readme.sha256,
        "truthBoundary": (
            "receipts_current is current provenance-verified viewer truth; provenance_legacy preserves "
            "historical provenance defects without rewriting canonical receipt hashes"
        ),
    }
    manifest["manifestSha256"] = sha256_json(manifest)
    manifest_artifact = ShadowRecoveryArtifact("PUBLICATION_MANIFEST.v2.json", canonical_json(manifest).encode("utf-8"))

    return {
        "verifiedRows": verified_rows,
        "supersessions": supersessions,
        "manifest": manifest,
        "artifacts": [viewer, legacy, readme, manifest_artifact],
    }


def publish_shadow_recovery_bundle(
    *,
    bundle: dict[str, Any],
    repo_id: str,
    expected_hf_revision: str,
    owner_approved: bool,
    target_revision: str = "main",
) -> dict[str, Any]:
    """Publish exact recovery bytes and verify them at the returned Hub commit."""
    if owner_approved is not True:
        raise RuntimeError("shadow_hf_owner_approval_required")
    if target_revision != "main":
        raise RuntimeError("shadow_hf_recovery_target_must_be_main")

    try:
        from huggingface_hub import CommitOperationAdd, HfApi, hf_hub_download
    except ImportError as exc:
        raise RuntimeError("huggingface_hub_dependency_missing") from exc

    token = _load_huggingface_runtime_token()
    api = HfApi(token=token)
    observed = api.repo_info(repo_id=repo_id, repo_type="dataset", revision=target_revision)
    observed_sha = str(getattr(observed, "sha", "") or "")
    if observed_sha != expected_hf_revision:
        raise RuntimeError("shadow_hf_prewrite_revision_mismatch")

    artifacts = bundle.get("artifacts") if isinstance(bundle, dict) else None
    if not isinstance(artifacts, list) or not artifacts:
        raise RuntimeError("shadow_hf_recovery_artifacts_missing")
    operations = [
        CommitOperationAdd(path_in_repo=item.path, path_or_fileobj=item.content)
        for item in artifacts
        if isinstance(item, ShadowRecoveryArtifact)
    ]
    if len(operations) != len(artifacts):
        raise RuntimeError("shadow_hf_recovery_artifact_invalid")

    commit = api.create_commit(
        repo_id=repo_id,
        repo_type="dataset",
        revision=target_revision,
        operations=operations,
        commit_message="Repair shadow dataset provenance and viewer truth boundary",
    )
    commit_oid = str(getattr(commit, "oid", "") or getattr(commit, "commit_id", "") or "")
    if not _valid_revision(commit_oid):
        raise RuntimeError("shadow_hf_commit_identity_missing")

    readback: dict[str, str] = {}
    for artifact in artifacts:
        local = hf_hub_download(
            repo_id=repo_id,
            repo_type="dataset",
            revision=commit_oid,
            filename=artifact.path,
            token=token,
        )
        observed_bytes = Path(local).read_bytes()
        observed_hash = hashlib.sha256(observed_bytes).hexdigest()
        if observed_hash != artifact.sha256:
            raise RuntimeError(f"shadow_hf_readback_mismatch:{artifact.path}")
        readback[artifact.path] = observed_hash

    return {
        "ok": True,
        "status": "PUBLISHED_VERIFIED",
        "repoId": repo_id,
        "prewriteRevision": expected_hf_revision,
        "commitOid": commit_oid,
        "artifactHashes": readback,
        "readbackVerified": True,
        "canonicalReceiptsMutated": False,
        "secretValuesReturned": False,
    }


__all__ = [
    "ShadowRecoveryArtifact",
    "build_shadow_recovery_bundle",
    "classify_source_revision",
    "publish_shadow_recovery_bundle",
]
