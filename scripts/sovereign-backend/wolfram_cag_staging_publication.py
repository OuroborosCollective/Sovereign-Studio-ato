"""One-shot owner-confirmed Wolfram CAG benchmark publication to HF staging.

This is the only productive trigger for the 12 code-defined CAG benchmark
projections.  Callers cannot supply rows, repository identity, target revision,
rights material or Hub credentials.  The function delegates all publication
truth to the existing fail-closed Evidence Observatory publisher and persists a
publication receipt only after exact target readback.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Callable

import psycopg2.extras

from evidence_observatory_publisher import publish_huggingface_batch
from wolfram_cag_benchmark_publication import PROJECT_ID, build_cag_benchmark_public_rows

HF_REPO_ID = "Thorsu/sovereign-evidence-observatory"
HF_STAGING_REVISION = "staging-atlas"
EXPECTED_CASE_IDS = tuple(f"cag-bench-{index:03d}" for index in range(1, 13))

ConnectionFactory = Callable[[], Any]


def _close(conn: Any) -> None:
    close = getattr(conn, "close", None)
    if callable(close):
        close()


def build_cag_staging_rows() -> list[dict[str, Any]]:
    rows = build_cag_benchmark_public_rows()
    case_ids = tuple(str(row.get("caseId") or "") for row in rows)
    if case_ids != EXPECTED_CASE_IDS:
        raise RuntimeError("cag_staging_case_identity_mismatch")
    for row in rows:
        if row.get("projectId") != PROJECT_ID:
            raise RuntimeError("cag_staging_project_identity_mismatch")
        if row.get("workflowState") != "PUBLISHABLE":
            raise RuntimeError("cag_staging_case_not_publishable")
        truth_boundary = row.get("truthBoundary") if isinstance(row.get("truthBoundary"), dict) else {}
        if truth_boundary.get("liveCagResult") is not False:
            raise RuntimeError("cag_staging_live_result_boundary_missing")
        if truth_boundary.get("fixtureReference") is not True:
            raise RuntimeError("cag_staging_fixture_boundary_missing")
    return rows


def _persist_verified_receipt(
    *,
    get_connection: ConnectionFactory,
    admin_id: str,
    case_ids: list[str],
    receipt: dict[str, Any],
) -> dict[str, Any]:
    try:
        normalized_admin_id = str(uuid.UUID(str(admin_id)))
        normalized_batch_id = str(uuid.UUID(str(receipt.get("batchId") or "")))
    except (ValueError, TypeError, AttributeError) as exc:
        raise RuntimeError("cag_staging_persistence_identity_invalid") from exc

    publication = receipt.get("publicationReceipt") if isinstance(receipt.get("publicationReceipt"), dict) else {}
    required_text = (
        "commitOid", "dataPath", "manifestPath", "dataSha256", "manifestSha256",
        "batchSha256", "licenseRightsHash", "privacyScanHash", "publisherPolicyHash",
        "publicationReceiptSha256",
    )
    if any(not str(receipt.get(key) or "").strip() for key in required_text):
        raise RuntimeError("cag_staging_publication_receipt_incomplete")
    if receipt.get("status") != "PUBLISHED_VERIFIED" or receipt.get("readbackVerified") is not True:
        raise RuntimeError("cag_staging_publication_not_verified")
    if publication.get("status") != "PUBLISHED_VERIFIED":
        raise RuntimeError("cag_staging_publication_receipt_not_verified")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO evidence_observatory_publish_receipts
                       (batch_id, repo_id, revision, commit_oid, data_path, manifest_path,
                        data_sha256, manifest_sha256, case_ids, state, readback_verified,
                        batch_sha256, license_rights_sha256, privacy_scan_sha256,
                        publisher_policy_sha256, expected_target, observed_target,
                        observed_target_revision, observed_artifact_hashes,
                        write_attempt_identity, readback_identity, publication_status,
                        publication_receipt, publication_receipt_sha256, created_by)
                   VALUES (%s::uuid,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'PUBLISHED',true,
                           %s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,'PUBLISHED_VERIFIED',%s::jsonb,%s,%s::uuid)
                   ON CONFLICT (batch_id) DO NOTHING
                   RETURNING id::text""",
                (
                    normalized_batch_id,
                    HF_REPO_ID,
                    HF_STAGING_REVISION,
                    str(receipt["commitOid"]),
                    str(receipt["dataPath"]),
                    str(receipt["manifestPath"]),
                    str(receipt["dataSha256"]),
                    str(receipt["manifestSha256"]),
                    psycopg2.extras.Json(case_ids),
                    str(receipt["batchSha256"]),
                    str(receipt["licenseRightsHash"]),
                    str(receipt["privacyScanHash"]),
                    str(receipt["publisherPolicyHash"]),
                    str(publication.get("expectedTarget") or ""),
                    str(publication.get("observedTarget") or ""),
                    str(publication.get("observedTargetRevision") or ""),
                    psycopg2.extras.Json(publication.get("observedArtifactHashes") or []),
                    str(publication.get("writeAttemptIdentity") or ""),
                    str(publication.get("readbackIdentity") or ""),
                    psycopg2.extras.Json(publication),
                    str(receipt["publicationReceiptSha256"]),
                    normalized_admin_id,
                ),
            )
            inserted = cur.fetchone()
            cur.execute(
                """SELECT id::text, batch_id::text, repo_id, revision, commit_oid,
                          data_sha256, manifest_sha256, case_ids, readback_verified,
                          batch_sha256, license_rights_sha256, privacy_scan_sha256,
                          publisher_policy_sha256, observed_target_revision,
                          publication_status, publication_receipt_sha256
                   FROM evidence_observatory_publish_receipts
                   WHERE batch_id=%s::uuid LIMIT 1""",
                (normalized_batch_id,),
            )
            observed = cur.fetchone()
        conn.commit()
    except Exception:
        rollback = getattr(conn, "rollback", None)
        if callable(rollback):
            rollback()
        raise
    finally:
        _close(conn)

    row = dict(observed) if observed else {}
    expected = {
        "batch_id": normalized_batch_id,
        "repo_id": HF_REPO_ID,
        "revision": HF_STAGING_REVISION,
        "commit_oid": str(receipt["commitOid"]),
        "data_sha256": str(receipt["dataSha256"]),
        "manifest_sha256": str(receipt["manifestSha256"]),
        "case_ids": case_ids,
        "readback_verified": True,
        "batch_sha256": str(receipt["batchSha256"]),
        "license_rights_sha256": str(receipt["licenseRightsHash"]),
        "privacy_scan_sha256": str(receipt["privacyScanHash"]),
        "publisher_policy_sha256": str(receipt["publisherPolicyHash"]),
        "observed_target_revision": str(publication.get("observedTargetRevision") or ""),
        "publication_status": "PUBLISHED_VERIFIED",
        "publication_receipt_sha256": str(receipt["publicationReceiptSha256"]),
    }
    for key, value in expected.items():
        observed_value = row.get(key)
        if key == "case_ids" and isinstance(observed_value, str):
            try:
                observed_value = json.loads(observed_value)
            except json.JSONDecodeError as exc:
                raise RuntimeError("cag_staging_persistence_readback_invalid") from exc
        if observed_value != value:
            raise RuntimeError(f"cag_staging_persistence_readback_mismatch:{key}")
    return {
        "receiptId": str(row.get("id") or ""),
        "inserted": bool(inserted),
        "persistenceVerified": True,
    }


def publish_wolfram_cag_benchmark_staging(
    *,
    get_connection: ConnectionFactory,
    admin_id: str,
) -> dict[str, Any]:
    """Publish exactly the 12 CAG fixtures to the fixed HF staging target."""
    rows = build_cag_staging_rows()
    case_ids = [str(row["caseId"]) for row in rows]
    receipt = publish_huggingface_batch(
        rows=rows,
        repo_id=HF_REPO_ID,
        revision=HF_STAGING_REVISION,
    )
    status = str(receipt.get("status") or "")
    if status == "DUPLICATE_NOOP":
        return {
            **receipt,
            "publishedCaseIds": [],
            "skippedCaseIds": case_ids,
            "persistenceVerified": False,
            "persistencePerformed": False,
            "mutationPerformed": False,
            "truthNotice": (
                "The exact semantic batch already exists in the target corpus; "
                "no staging write or publication receipt was created."
            ),
        }
    if status != "PUBLISHED_VERIFIED" or receipt.get("readbackVerified") is not True:
        raise RuntimeError("cag_staging_publish_not_verified")
    persistence = _persist_verified_receipt(
        get_connection=get_connection,
        admin_id=admin_id,
        case_ids=case_ids,
        receipt=receipt,
    )
    external_mutation = not bool(receipt.get("idempotent"))
    persistence_mutation = bool(persistence.get("inserted"))
    return {
        **receipt,
        **persistence,
        "publishedCaseIds": case_ids,
        "skippedCaseIds": [],
        "externalMutationPerformed": external_mutation,
        "persistencePerformed": persistence_mutation,
        "mutationPerformed": external_mutation or persistence_mutation,
        "truthNotice": (
            "Published objects are reproducible benchmark fixtures with independent Wolfram reference evidence; "
            "they are not live CAG component results."
        ),
    }


__all__ = [
    "EXPECTED_CASE_IDS",
    "HF_REPO_ID",
    "HF_STAGING_REVISION",
    "build_cag_staging_rows",
    "publish_wolfram_cag_benchmark_staging",
]
