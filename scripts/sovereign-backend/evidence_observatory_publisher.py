"""Fail-closed Hugging Face publisher contracts for the Evidence Observatory.

The publisher is intentionally split from Flask/DB code.  A public projection
must already carry a current PUBLISHABLE gate/passport binding.  This module
then adds publication-only controls: provenance, privacy, redistribution
rights, target deduplication, deterministic batch identity, exact target
readback and a hash-bound publication receipt.

No raw credential is accepted by any function.  Authentication is delegated to
``huggingface_hub``'s runtime identity.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from functools import partial
from pathlib import Path
from typing import Any

from evidence_observatory_contracts import canonical_json, https_url, sha256_json, sha256_text
from freellm_provider_credentials import provider_secret_paths

PUBLISHER_POLICY: dict[str, Any] = {
    "schemaVersion": "sovereign.evidence-hf-publisher-policy.v2",
    "stagingOnly": True,
    "forbiddenDirectRevisions": ["main", "master"],
    "requirePublishable": True,
    "requireFreshGatePassportHashes": True,
    "requirePositiveRedistributionRights": True,
    "requireSourceProvenance": True,
    "requirePrivacyScan": True,
    "requireTargetDedup": True,
    "readbackBeforeRetry": True,
    "maxWriteAttempts": 2,
    "forbiddenPublicFields": [
        "rawPrompt", "rawPrompts", "chainOfThought", "chain_of_thought",
        "privateSourceFiles", "privateDbRecords", "rawLogs", "rawPayload",
        "raw_payload", "credential", "credentials", "authorization",
        "password", "secret", "token", "apiKey", "api_key",
    ],
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE)
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
_TOKEN_RE = re.compile(
    r"\b(?:hf_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})\b"
)
_FORBIDDEN_KEYS = {
    re.sub(r"[^a-z0-9]", "", item.lower())
    for item in PUBLISHER_POLICY["forbiddenPublicFields"]
}
_OWNER_INPUT_ROOT = Path(os.getenv("SOVEREIGN_OWNER_INPUT_ROOT") or "/opt/sovereign-owner-managed").resolve()
_HF_RIGHTS_PATH = Path(
    os.getenv("SOVEREIGN_HF_PUBLICATION_RIGHTS_FILE")
    or str(_OWNER_INPUT_ROOT / "hf_publication_rights.json")
).resolve()


def _load_huggingface_runtime_token() -> str:
    """Resolve one existing owner-managed HF credential only at transport time.

    The publisher intentionally reuses the canonical FreeLLM provider credential
    pool instead of introducing a second Hugging Face secret store.  Raw token
    values never enter manifests, receipts, logs or return payloads.
    """
    candidates: list[tuple[int, Path]] = []
    for path in provider_secret_paths(_OWNER_INPUT_ROOT, "huggingface"):
        try:
            if path.is_symlink() or not path.is_file():
                continue
            stat = path.stat()
        except OSError:
            continue
        if stat.st_size < 8 or stat.st_size > 8192:
            continue
        if stat.st_mode & 0o077:
            continue
        candidates.append((int(stat.st_mtime_ns), path))

    for _, path in sorted(candidates, key=lambda item: item[0], reverse=True):
        protected = bytearray()
        try:
            protected = bytearray(path.read_bytes())
            if not protected or len(protected) > 8192:
                continue
            token = bytes(protected).strip().decode("utf-8")
            if not token.startswith("hf_") or len(token) < 20:
                continue
            return token
        except (OSError, UnicodeDecodeError):
            continue
        finally:
            for index in range(len(protected)):
                protected[index] = 0
    raise RuntimeError("huggingface_runtime_credential_missing")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _valid_sha256(value: Any) -> bool:
    return bool(_SHA256_RE.fullmatch(str(value or "").strip().lower()))


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _verify_embedded_hash(obj: dict[str, Any], hash_key: str) -> bool:
    claimed = str(obj.get(hash_key) or "").strip().lower()
    if not _valid_sha256(claimed):
        return False
    base = dict(obj)
    base.pop(hash_key, None)
    return sha256_json(base) == claimed


def load_huggingface_publication_rights() -> dict[str, Any]:
    """Load a non-secret owner-managed rights receipt without exposing secrets."""
    path = _HF_RIGHTS_PATH
    if path.parent != _OWNER_INPUT_ROOT and _OWNER_INPUT_ROOT not in path.parents:
        raise RuntimeError("huggingface_rights_path_outside_owner_root")
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError("huggingface_publication_rights_missing") from exc
    if len(raw.encode("utf-8")) > 64_000:
        raise RuntimeError("huggingface_publication_rights_oversized")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("huggingface_publication_rights_invalid_json") from exc
    if not isinstance(value, dict):
        raise RuntimeError("huggingface_publication_rights_object_required")
    return value


def validate_huggingface_publication_rights(
    rights: Any, *, repo_id: str, revision: str, case_ids: list[str]
) -> dict[str, Any]:
    """Validate one exact positive redistribution authorization.

    The authorization text is included so its digest is independently
    recomputable.  A URL alone is not treated as permission.
    """
    body = rights if isinstance(rights, dict) else {}
    blockers: list[str] = []
    if body.get("schemaVersion") != "sovereign.hf-publication-rights.v1":
        blockers.append("rights_schema_version")
    if body.get("status") != "AUTHORIZED":
        blockers.append("rights_status_not_authorized")
    for key in ("rightsHolder", "authorizedEntity", "purpose", "scope", "licenseId", "authorizationText"):
        if not str(body.get(key) or "").strip():
            blockers.append(f"rights_{key}_required")
    if str(body.get("licenseId") or "").strip().upper() in {"", "UNKNOWN", "UNVERIFIED"}:
        blockers.append("rights_license_unknown")
    if str(body.get("authorizedTarget") or "").strip() != repo_id:
        blockers.append("rights_target_mismatch")
    if str(body.get("authorizedRevision") or "").strip() != revision:
        blockers.append("rights_revision_mismatch")
    authorization_ref = str(body.get("authorizationRef") or "").strip()
    if not https_url(authorization_ref):
        blockers.append("rights_authorization_https_ref")
    authorization_text = str(body.get("authorizationText") or "")
    expected_authorization_sha = sha256_text(authorization_text) if authorization_text else ""
    if str(body.get("authorizationSha256") or "").strip().lower() != expected_authorization_sha:
        blockers.append("rights_authorization_hash_mismatch")
    authorized_cases = {str(item) for item in (body.get("authorizedCaseIds") or []) if str(item)}
    requested_cases = set(case_ids)
    if not requested_cases or not requested_cases.issubset(authorized_cases):
        blockers.append("rights_case_scope_mismatch")
    conditions = body.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        blockers.append("rights_conditions_required")
    if blockers:
        raise RuntimeError("huggingface_publication_rights_blocked:" + ",".join(sorted(set(blockers))))
    return body


def scan_public_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministically scan the final public objects for secret/PII shapes."""
    findings: list[dict[str, str]] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                child = f"{path}.{key}" if path else str(key)
                if _normalized_key(key) in _FORBIDDEN_KEYS:
                    findings.append({"path": child, "kind": "forbidden_private_field"})
                    continue
                walk(item, child)
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
            return
        if not isinstance(value, str):
            return
        if _PRIVATE_KEY_RE.search(value):
            findings.append({"path": path, "kind": "private_key_shape"})
        if _BEARER_RE.search(value):
            findings.append({"path": path, "kind": "bearer_credential_shape"})
        if _TOKEN_RE.search(value):
            findings.append({"path": path, "kind": "provider_token_shape"})
        if _EMAIL_RE.search(value):
            findings.append({"path": path, "kind": "email_pii_shape"})

    for index, row in enumerate(rows):
        walk(row, f"rows[{index}]")
    public_hashes = [sha256_json(row) for row in rows]
    report: dict[str, Any] = {
        "schemaVersion": "sovereign.evidence-public-privacy-scan.v1",
        "caseIds": [str(row.get("caseId") or "") for row in rows],
        "publicPayloadHashes": public_hashes,
        "findingCount": len(findings),
        "findings": findings,
        "secretsExcluded": not findings,
        "piiExcluded": not findings,
        "scanScope": "final-canonical-public-json-objects",
    }
    report["privacyScanSha256"] = sha256_json(report)
    return report


def _validate_public_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        raise RuntimeError("huggingface_publish_empty_batch")
    if len(rows) > 500:
        raise RuntimeError("huggingface_publish_batch_bound_exceeded")
    source_refs: list[dict[str, Any]] = []
    case_ids: set[str] = set()
    for row_index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise RuntimeError(f"huggingface_public_row_invalid:{row_index}")
        case_id = str(row.get("caseId") or "").strip()
        if not case_id:
            raise RuntimeError(f"huggingface_public_case_id_missing:{row_index}")
        if case_id in case_ids:
            raise RuntimeError(f"huggingface_duplicate_batch_case_id:{case_id}")
        case_ids.add(case_id)
        if row.get("workflowState") != "PUBLISHABLE":
            raise RuntimeError(f"huggingface_case_not_publishable:{case_id}")
        if not _valid_sha256(row.get("caseSha256")):
            raise RuntimeError(f"huggingface_case_hash_missing:{case_id}")
        if not _valid_sha256(row.get("passportSha256")):
            raise RuntimeError(f"huggingface_passport_hash_missing:{case_id}")
        gate = row.get("gateReport") if isinstance(row.get("gateReport"), dict) else {}
        if gate.get("passed") is not True or not _verify_embedded_hash(gate, "gateSha256"):
            raise RuntimeError(f"huggingface_gate_receipt_invalid:{case_id}")
        passport = row.get("evidencePassport") if isinstance(row.get("evidencePassport"), dict) else {}
        if str(passport.get("passportSha256") or "").lower() != str(row.get("passportSha256") or "").lower():
            raise RuntimeError(f"huggingface_passport_binding_mismatch:{case_id}")
        if not _verify_embedded_hash(passport, "passportSha256"):
            raise RuntimeError(f"huggingface_passport_invalid:{case_id}")
        sources = row.get("sources") if isinstance(row.get("sources"), list) else []
        if not sources:
            raise RuntimeError(f"huggingface_source_provenance_missing:{case_id}")
        for source_index, source in enumerate(sources):
            if not isinstance(source, dict):
                raise RuntimeError(f"huggingface_source_invalid:{case_id}:{source_index}")
            source_id = str(source.get("id") or "").strip()
            locator = str(source.get("locator") or "").strip()
            content_sha = str(source.get("contentSha256") or "").strip().lower()
            provenance = source.get("provenance") if isinstance(source.get("provenance"), dict) else {}
            origin = str(provenance.get("originFamily") or "").strip()
            if not source_id or not https_url(locator) or not _valid_sha256(content_sha) or not origin:
                raise RuntimeError(f"huggingface_source_provenance_invalid:{case_id}:{source_index}")
            source_refs.append({
                "caseId": case_id,
                "sourceId": source_id,
                "locator": locator,
                "contentSha256": content_sha,
                "originFamily": origin,
            })
    return source_refs


def build_huggingface_publish_plan(
    *, rows: list[dict[str, Any]], repo_id: str, revision: str, license_rights: dict[str, Any]
) -> dict[str, Any]:
    """Build the deterministic #1507 manifest before any Hub mutation."""
    if not repo_id:
        raise RuntimeError("huggingface_repo_configuration_missing")
    target_revision = str(revision or "").strip() or "staging-atlas"
    if target_revision in set(PUBLISHER_POLICY["forbiddenDirectRevisions"]):
        raise RuntimeError("huggingface_direct_main_publish_forbidden")
    source_refs = _validate_public_rows(rows)
    case_ids = [str(row.get("caseId")) for row in rows]
    rights = validate_huggingface_publication_rights(
        license_rights, repo_id=repo_id, revision=target_revision, case_ids=case_ids
    )
    privacy = scan_public_payload(rows)
    if privacy["findingCount"]:
        kinds = ",".join(sorted({item["kind"] for item in privacy["findings"]}))
        raise RuntimeError("huggingface_public_privacy_scan_blocked:" + kinds)

    public_payload_hashes = list(privacy["publicPayloadHashes"])
    passport_hashes = [str(row.get("passportSha256")) for row in rows]
    gate_receipt_hashes = [str((row.get("gateReport") or {}).get("gateSha256")) for row in rows]
    policy_hash = sha256_json(PUBLISHER_POLICY)
    rights_hash = sha256_json(rights)
    privacy_hash = str(privacy["privacyScanSha256"])
    batch_seed = {
        "caseIds": case_ids,
        "passportHashes": passport_hashes,
        "gateReceiptHashes": gate_receipt_hashes,
        "publicPayloadHashes": public_payload_hashes,
        "licenseRightsHash": rights_hash,
        "privacyScanHash": privacy_hash,
        "publisherPolicyHash": policy_hash,
        "targetRepoIdentity": f"dataset:{repo_id}@{target_revision}",
    }
    seed_sha = sha256_json(batch_seed)
    batch_id = str(uuid.UUID(seed_sha[:32]))
    data_path = f"staging/atlas-batches/{batch_id}.jsonl"
    manifest_path = f"staging/atlas-batches/{batch_id}.manifest.json"
    data_bytes = ("\n".join(canonical_json(row) for row in rows) + "\n").encode("utf-8")
    data_sha = _sha256_bytes(data_bytes)
    manifest: dict[str, Any] = {
        "schema_version": "sovereign.evidence-hf-batch.v2",
        "batch_id": batch_id,
        "case_ids": case_ids,
        "passport_hashes": passport_hashes,
        "gate_receipt_hashes": gate_receipt_hashes,
        "public_payload_hashes": public_payload_hashes,
        "source_publication_refs": source_refs,
        "license_rights_hash": rights_hash,
        "license_rights_ref": rights.get("authorizationRef"),
        "license_id": rights.get("licenseId"),
        "privacy_scan_hash": privacy_hash,
        "publisher_policy_hash": policy_hash,
        "target_repo_identity": f"dataset:{repo_id}@{target_revision}",
        "data_path": data_path,
        "data_sha256": data_sha,
        "truth_notice": (
            "HF publication proves only that this public-safe evidence state passed publication gates; "
            "it does not turn fixture references into live Wolfram CAG results."
        ),
    }
    manifest["batch_sha256"] = sha256_json(manifest)
    manifest_bytes = canonical_json(manifest).encode("utf-8")
    return {
        "batchId": batch_id,
        "repoId": repo_id,
        "revision": target_revision,
        "dataPath": data_path,
        "manifestPath": manifest_path,
        "dataBytes": data_bytes,
        "manifestBytes": manifest_bytes,
        "dataSha256": data_sha,
        "manifestSha256": _sha256_bytes(manifest_bytes),
        "batchSha256": manifest["batch_sha256"],
        "publicPayloadHashes": public_payload_hashes,
        "privacyScan": privacy,
        "licenseRightsHash": rights_hash,
        "publisherPolicyHash": policy_hash,
        "manifest": manifest,
    }


def _branch_sha(api: Any, *, repo_id: str, revision: str) -> str:
    try:
        info = api.repo_info(repo_id=repo_id, repo_type="dataset", revision=revision)
    except Exception:
        return ""
    return str(getattr(info, "sha", "") or "")


def _load_target_rows(*, api: Any, hf_hub_download: Any, repo_id: str, revision: str) -> list[dict[str, Any]]:
    try:
        files = list(api.list_repo_files(repo_id=repo_id, repo_type="dataset", revision=revision))
    except Exception:
        return []
    jsonl_files = [
        path for path in files
        if path.endswith(".jsonl") and (path.startswith("staging/atlas-batches/") or path == "data/casebook.jsonl")
    ]
    if len(jsonl_files) > 500:
        raise RuntimeError("huggingface_target_dedup_file_bound_exceeded")
    rows: list[dict[str, Any]] = []
    for path in jsonl_files:
        local = hf_hub_download(repo_id=repo_id, filename=path, repo_type="dataset", revision=revision)
        try:
            if os.path.getsize(local) > 10_000_000:
                raise RuntimeError("huggingface_target_dedup_file_size_bound_exceeded")
            with open(local, "r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if line_number > 10_000:
                        raise RuntimeError("huggingface_target_dedup_row_bound_exceeded")
                    text = line.strip()
                    if not text:
                        continue
                    value = json.loads(text)
                    if isinstance(value, dict):
                        rows.append(value)
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("huggingface_target_dedup_read_invalid") from exc
    return rows


def _claim_sha(row: dict[str, Any]) -> str:
    declared = str(row.get("claimSha256") or "").strip().lower()
    if _valid_sha256(declared):
        return declared
    claim = str(row.get("claim") or "").strip()
    return sha256_text(" ".join(claim.split())) if claim else ""


def _dedup_gate(incoming: list[dict[str, Any]], existing: list[dict[str, Any]]) -> dict[str, Any]:
    existing_by_id: dict[str, dict[str, Any]] = {}
    existing_claims: dict[str, list[str]] = {}
    for row in existing:
        case_id = str(row.get("caseId") or "").strip()
        if case_id:
            existing_by_id[case_id] = row
        claim_sha = _claim_sha(row)
        if claim_sha:
            existing_claims.setdefault(claim_sha, []).append(case_id)
    identical: list[str] = []
    for row in incoming:
        case_id = str(row.get("caseId") or "").strip()
        claim_sha = _claim_sha(row)
        prior = existing_by_id.get(case_id)
        if prior is not None:
            if canonical_json(prior) == canonical_json(row):
                identical.append(case_id)
                continue
            raise RuntimeError(f"huggingface_target_case_id_conflict:{case_id}")
        if claim_sha and claim_sha in existing_claims:
            raise RuntimeError(f"huggingface_target_duplicate_claim:{case_id}")
    return {
        "existingRowCount": len(existing),
        "identicalCaseIds": sorted(identical),
        "allIdentical": len(identical) == len(incoming),
    }


def _readback_paths(
    *, hf_hub_download: Any, repo_id: str, revision: str, plan: dict[str, Any]
) -> dict[str, Any] | None:
    try:
        data_local = hf_hub_download(
            repo_id=repo_id, filename=plan["dataPath"], repo_type="dataset", revision=revision
        )
        manifest_local = hf_hub_download(
            repo_id=repo_id, filename=plan["manifestPath"], repo_type="dataset", revision=revision
        )
        with open(data_local, "rb") as handle:
            observed_data_sha = _sha256_bytes(handle.read())
        with open(manifest_local, "rb") as handle:
            observed_manifest_sha = _sha256_bytes(handle.read())
    except Exception:
        return None
    return {
        "dataSha256": observed_data_sha,
        "manifestSha256": observed_manifest_sha,
        "matches": observed_data_sha == plan["dataSha256"] and observed_manifest_sha == plan["manifestSha256"],
    }


def _publication_receipt(
    *, plan: dict[str, Any], observed_revision: str, write_attempt: int,
    readback: dict[str, Any], prewrite_revision: str, idempotent: bool
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schemaVersion": "sovereign.evidence-hf-publication-receipt.v2",
        "batchSha256": plan["batchSha256"],
        "expectedTarget": f"dataset:{plan['repoId']}@{plan['revision']}",
        "observedTarget": f"dataset:{plan['repoId']}@{plan['revision']}",
        "prewriteTargetRevision": prewrite_revision or None,
        "observedTargetRevision": observed_revision,
        "observedArtifactHashes": [readback["dataSha256"], readback["manifestSha256"]],
        "writeAttemptIdentity": sha256_json({"batchId": plan["batchId"], "attempt": write_attempt}),
        "readbackIdentity": sha256_json({
            "revision": observed_revision,
            "dataSha256": readback["dataSha256"],
            "manifestSha256": readback["manifestSha256"],
        }),
        "status": "PUBLISHED_VERIFIED" if readback.get("matches") else "PUBLISHED_CONTRADICTED",
        "idempotent": idempotent,
    }
    body["publicationReceiptSha256"] = sha256_json(body)
    return body


def publish_huggingface_batch(
    *, rows: list[dict[str, Any]], repo_id: str, revision: str,
    license_rights: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Publish one deterministic, rights-cleared batch and verify exact Hub bytes."""
    target_revision = str(revision or "").strip() or "staging-atlas"
    if target_revision in set(PUBLISHER_POLICY["forbiddenDirectRevisions"]):
        raise RuntimeError("huggingface_direct_main_publish_forbidden")
    rights = license_rights if license_rights is not None else load_huggingface_publication_rights()
    plan = build_huggingface_publish_plan(
        rows=rows, repo_id=repo_id, revision=target_revision, license_rights=rights
    )
    try:
        from huggingface_hub import CommitOperationAdd, HfApi, hf_hub_download as raw_hf_hub_download
    except ImportError as exc:
        raise RuntimeError("huggingface_hub_dependency_missing") from exc

    runtime_token = _load_huggingface_runtime_token()
    api = HfApi(token=runtime_token)
    hf_hub_download = partial(raw_hf_hub_download, token=runtime_token)
    prewrite_revision = _branch_sha(api, repo_id=repo_id, revision=target_revision)
    revisions_to_scan = ["main"]
    if prewrite_revision:
        revisions_to_scan.append(target_revision)
    existing: list[dict[str, Any]] = []
    for target in revisions_to_scan:
        existing.extend(_load_target_rows(
            api=api, hf_hub_download=hf_hub_download, repo_id=repo_id, revision=target
        ))
    dedup = _dedup_gate(rows, existing)

    existing_readback = _readback_paths(
        hf_hub_download=hf_hub_download, repo_id=repo_id,
        revision=target_revision, plan=plan
    ) if prewrite_revision else None
    if existing_readback and existing_readback.get("matches"):
        observed_revision = _branch_sha(api, repo_id=repo_id, revision=target_revision)
        receipt = _publication_receipt(
            plan=plan, observed_revision=observed_revision, write_attempt=0,
            readback=existing_readback, prewrite_revision=prewrite_revision, idempotent=True
        )
        return {
            "ok": True, "status": "PUBLISHED_VERIFIED", "batchId": plan["batchId"], "repoId": repo_id,
            "revision": target_revision, "commitOid": observed_revision,
            "dataPath": plan["dataPath"], "manifestPath": plan["manifestPath"],
            "dataSha256": plan["dataSha256"], "manifestSha256": plan["manifestSha256"],
            "batchSha256": plan["batchSha256"], "readbackVerified": True,
            "runtimeIdentityUsed": True, "idempotent": True,
            "privacyScanHash": plan["privacyScan"]["privacyScanSha256"],
            "licenseRightsHash": plan["licenseRightsHash"],
            "publisherPolicyHash": plan["publisherPolicyHash"],
            "publicationReceipt": receipt, "publicationReceiptSha256": receipt["publicationReceiptSha256"],
            "dedup": dedup,
        }

    if dedup.get("allIdentical"):
        # Semantic duplicates already present in the target corpus are a true
        # no-op.  Do not create a staging branch or publication receipt, since
        # no new target mutation/readback occurred.
        return {
            "ok": True,
            "status": "DUPLICATE_NOOP",
            "batchId": plan["batchId"],
            "repoId": repo_id,
            "revision": target_revision,
            "dataPath": plan["dataPath"],
            "manifestPath": plan["manifestPath"],
            "dataSha256": plan["dataSha256"],
            "manifestSha256": plan["manifestSha256"],
            "batchSha256": plan["batchSha256"],
            "readbackVerified": False,
            "runtimeIdentityUsed": True,
            "idempotent": True,
            "duplicateSemanticPublishSkipped": True,
            "privacyScanHash": plan["privacyScan"]["privacyScanSha256"],
            "licenseRightsHash": plan["licenseRightsHash"],
            "publisherPolicyHash": plan["publisherPolicyHash"],
            "dedup": dedup,
        }

    if not prewrite_revision:
        try:
            api.create_branch(
                repo_id=repo_id, repo_type="dataset", branch=target_revision, exist_ok=True
            )
        except Exception as exc:
            # A concurrent creator is acceptable only if the branch now resolves.
            if not _branch_sha(api, repo_id=repo_id, revision=target_revision):
                raise RuntimeError("huggingface_staging_branch_create_failed") from exc
        prewrite_revision = _branch_sha(api, repo_id=repo_id, revision=target_revision)

    commit_oid = ""
    write_attempt = 0
    last_error: Exception | None = None
    for attempt in (1, 2):
        write_attempt = attempt
        try:
            commit = api.create_commit(
                repo_id=repo_id,
                repo_type="dataset",
                revision=target_revision,
                operations=[
                    CommitOperationAdd(path_in_repo=plan["dataPath"], path_or_fileobj=plan["dataBytes"]),
                    CommitOperationAdd(path_in_repo=plan["manifestPath"], path_or_fileobj=plan["manifestBytes"]),
                ],
                commit_message=f"Sovereign Evidence Atlas deterministic batch {plan['batchId']}",
            )
            commit_oid = str(getattr(commit, "oid", "") or getattr(commit, "commit_id", "") or "")
            if not commit_oid:
                raise RuntimeError("huggingface_commit_oid_missing")
            break
        except Exception as exc:
            last_error = exc
            # Required recovery order: target readback before any retry.
            branch_readback = _readback_paths(
                hf_hub_download=hf_hub_download, repo_id=repo_id,
                revision=target_revision, plan=plan
            )
            if branch_readback and branch_readback.get("matches"):
                commit_oid = _branch_sha(api, repo_id=repo_id, revision=target_revision)
                break
            if attempt == 2:
                raise RuntimeError("huggingface_publish_write_failed_after_readback") from exc
    if not commit_oid:
        raise RuntimeError("huggingface_publish_commit_unresolved") from last_error

    readback = _readback_paths(
        hf_hub_download=hf_hub_download, repo_id=repo_id, revision=commit_oid, plan=plan
    )
    if not readback:
        raise RuntimeError("huggingface_publish_readback_missing")
    if not readback.get("matches"):
        raise RuntimeError("huggingface_publish_readback_mismatch")
    receipt = _publication_receipt(
        plan=plan, observed_revision=commit_oid, write_attempt=write_attempt,
        readback=readback, prewrite_revision=prewrite_revision, idempotent=False
    )
    if receipt["status"] != "PUBLISHED_VERIFIED":
        raise RuntimeError("huggingface_publication_receipt_contradicted")
    return {
        "ok": True,
        "status": "PUBLISHED_VERIFIED",
        "batchId": plan["batchId"],
        "repoId": repo_id,
        "revision": target_revision,
        "commitOid": commit_oid,
        "dataPath": plan["dataPath"],
        "manifestPath": plan["manifestPath"],
        "dataSha256": plan["dataSha256"],
        "manifestSha256": plan["manifestSha256"],
        "batchSha256": plan["batchSha256"],
        "readbackVerified": True,
        "runtimeIdentityUsed": True,
        "idempotent": False,
        "privacyScanHash": plan["privacyScan"]["privacyScanSha256"],
        "licenseRightsHash": plan["licenseRightsHash"],
        "publisherPolicyHash": plan["publisherPolicyHash"],
        "publicationReceipt": receipt,
        "publicationReceiptSha256": receipt["publicationReceiptSha256"],
        "dedup": dedup,
    }


__all__ = [
    "PUBLISHER_POLICY",
    "build_huggingface_publish_plan",
    "load_huggingface_publication_rights",
    "publish_huggingface_batch",
    "scan_public_payload",
    "validate_huggingface_publication_rights",
]
