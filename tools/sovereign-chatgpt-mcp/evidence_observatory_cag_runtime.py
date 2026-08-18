from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any


COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
HF_REPO_ID = "Thorsu/sovereign-evidence-observatory"
HF_REVISION = "staging-atlas"
CAG_CASE_IDS = tuple(f"cag-bench-{index:03d}" for index in range(1, 13))


_BACKEND_CAG_STAGING_PUBLISH_SCRIPT = r'''
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request

import psycopg2
import psycopg2.extras


expected_revision, expected_digest = sys.argv[1:3]
expected_repo = "Thorsu/sovereign-evidence-observatory"
expected_target_revision = "staging-atlas"
expected_case_ids = [f"cag-bench-{index:03d}" for index in range(1, 13)]
admin_key = os.environ.get("ADMIN_API_KEY", "").strip()
conn = None
publish_request_started = False


def digest_text(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8", errors="replace")).hexdigest()


def request_json(method: str, path: str) -> tuple[int, dict[str, object]]:
    request = urllib.request.Request(
        f"http://127.0.0.1:8787{path}",
        data=b"{}" if method == "POST" else None,
        method=method,
        headers={
            "Authorization": f"Bearer {admin_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=480) as response:
            body = response.read(1_000_000)
            status = int(response.status)
    except urllib.error.HTTPError as error:
        body = error.read(1_000_000)
        status = int(error.code)
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"backend returned invalid JSON for {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"backend returned non-object JSON for {path}")
    return status, payload


try:
    if not admin_key:
        raise RuntimeError("backend admin authentication is not configured")
    runtime_revision = os.environ.get("SOVEREIGN_SOURCE_REVISION", "").strip()
    runtime_digest = os.environ.get("SOVEREIGN_IMAGE_DIGEST", "").strip()
    if runtime_revision != expected_revision or runtime_digest != expected_digest:
        raise RuntimeError("backend runtime identity mismatch")

    health_status, health = request_json("GET", "/health")
    if (
        health_status != 200
        or health.get("ok") is not True
        or health.get("sourceRevision") != expected_revision
        or health.get("imageDigest") != expected_digest
    ):
        raise RuntimeError("backend health identity mismatch")

    publish_request_started = True
    publish_status, publish = request_json(
        "POST",
        "/api/admin/evidence-observatory/v1/publish/huggingface/cag-benchmark",
    )
    if publish_status != 200 or publish.get("ok") is not True:
        raise RuntimeError("CAG staging publisher did not succeed")
    if publish.get("repoId") != expected_repo or publish.get("revision") != expected_target_revision:
        raise RuntimeError("CAG staging publisher target mismatch")
    if str(publish.get("status") or "") not in {"PUBLISHED_VERIFIED", "DUPLICATE_NOOP"}:
        raise RuntimeError("CAG staging publisher returned an unsupported status")

    status = str(publish.get("status") or "")
    published_ids = publish.get("publishedCaseIds") if isinstance(publish.get("publishedCaseIds"), list) else []
    skipped_ids = publish.get("skippedCaseIds") if isinstance(publish.get("skippedCaseIds"), list) else []
    observed_ids = published_ids if status == "PUBLISHED_VERIFIED" else skipped_ids
    if observed_ids != expected_case_ids:
        raise RuntimeError("CAG staging publisher case scope mismatch")

    for key in ("batchSha256", "dataSha256", "manifestSha256", "privacyScanHash", "licenseRightsHash", "publisherPolicyHash"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(publish.get(key) or "")):
            raise RuntimeError(f"CAG staging publisher missing hash: {key}")

    persistence_verified = False
    receipt_id = str(publish.get("receiptId") or "")
    if status == "PUBLISHED_VERIFIED":
        if publish.get("readbackVerified") is not True or publish.get("publicationReceiptPersisted") is not True:
            raise RuntimeError("CAG staging publisher readback/persistence not verified")
        if not re.fullmatch(r"[0-9a-f-]{36}", receipt_id):
            raise RuntimeError("CAG staging publisher receipt identity missing")
        if not re.fullmatch(r"[0-9a-f]{40}", str(publish.get("commitOid") or "")):
            raise RuntimeError("CAG staging publisher commit identity missing")
        publication_receipt_sha = str(publish.get("publicationReceiptSha256") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", publication_receipt_sha):
            raise RuntimeError("CAG staging publisher publication receipt hash missing")

        conn = psycopg2.connect(
            host=os.environ.get("POSTGRES_HOST", "db"),
            port=int(os.environ.get("POSTGRES_PORT", "5432")),
            dbname=os.environ.get("POSTGRES_DB", "postgres"),
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            connect_timeout=10,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id::text AS receipt_id, repo_id, revision, commit_oid,
                          data_sha256, manifest_sha256, case_ids, readback_verified,
                          batch_sha256, license_rights_sha256, privacy_scan_sha256,
                          publisher_policy_sha256, publication_status,
                          publication_receipt_sha256
                   FROM evidence_observatory_publish_receipts
                   WHERE id=%s::uuid LIMIT 1""",
                (receipt_id,),
            )
            row = cur.fetchone()
        if not row:
            raise RuntimeError("persisted CAG publication receipt is missing")
        if (
            row.get("repo_id") != expected_repo
            or row.get("revision") != expected_target_revision
            or row.get("commit_oid") != publish.get("commitOid")
            or row.get("data_sha256") != publish.get("dataSha256")
            or row.get("manifest_sha256") != publish.get("manifestSha256")
            or row.get("batch_sha256") != publish.get("batchSha256")
            or row.get("license_rights_sha256") != publish.get("licenseRightsHash")
            or row.get("privacy_scan_sha256") != publish.get("privacyScanHash")
            or row.get("publisher_policy_sha256") != publish.get("publisherPolicyHash")
            or row.get("publication_status") != "PUBLISHED_VERIFIED"
            or row.get("publication_receipt_sha256") != publication_receipt_sha
            or row.get("readback_verified") is not True
            or list(row.get("case_ids") or []) != expected_case_ids
        ):
            raise RuntimeError("persisted CAG publication receipt does not match publisher readback")
        persistence_verified = True
    else:
        if publish.get("duplicateSemanticPublishSkipped") is not True:
            raise RuntimeError("duplicate no-op is missing semantic duplicate evidence")
        if publish.get("readbackVerified") is not False:
            raise RuntimeError("duplicate no-op incorrectly claims publication readback")
        if publish.get("publicationReceiptPersisted") is not False:
            raise RuntimeError("duplicate no-op incorrectly claims a publication receipt")

    result = {
        "ok": True,
        "status": "CAG_STAGING_PUBLICATION_VERIFIED" if status == "PUBLISHED_VERIFIED" else "CAG_STAGING_DUPLICATE_NOOP_VERIFIED",
        "sourceRevision": expected_revision,
        "imageDigest": expected_digest,
        "repoId": expected_repo,
        "revision": expected_target_revision,
        "caseIds": expected_case_ids,
        "publisherStatus": status,
        "batchId": publish.get("batchId"),
        "batchSha256": publish.get("batchSha256"),
        "dataPath": publish.get("dataPath"),
        "manifestPath": publish.get("manifestPath"),
        "dataSha256": publish.get("dataSha256"),
        "manifestSha256": publish.get("manifestSha256"),
        "privacyScanHash": publish.get("privacyScanHash"),
        "licenseRightsHash": publish.get("licenseRightsHash"),
        "publisherPolicyHash": publish.get("publisherPolicyHash"),
        "commitOid": publish.get("commitOid") if status == "PUBLISHED_VERIFIED" else None,
        "publicationReceiptSha256": publish.get("publicationReceiptSha256") if status == "PUBLISHED_VERIFIED" else None,
        "publicationReceiptPersisted": publish.get("publicationReceiptPersisted") is True,
        "persistenceVerified": persistence_verified,
        "targetReadbackVerified": publish.get("readbackVerified") is True,
        "rightsReceiptValidatedByPublisher": True,
        "duplicateSemanticPublishSkipped": publish.get("duplicateSemanticPublishSkipped") is True,
        "truthNotice": "The published rows are reproducible benchmark fixtures with independent Wolfram references, not live CAG provider results.",
        "mutationPerformed": status == "PUBLISHED_VERIFIED",
        "secretValuesReturned": False,
        "protectedRightsValueReturned": False,
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
except Exception as exc:
    failure = {
        "ok": False,
        "status": "CAG_STAGING_PUBLICATION_FAILED",
        "sourceRevision": expected_revision,
        "imageDigest": expected_digest,
        "failureType": type(exc).__name__,
        "failureSha256": digest_text(exc),
        "mutationState": "UNKNOWN_AFTER_PUBLISH_REQUEST" if publish_request_started else "NOT_STARTED",
        "secretValuesReturned": False,
        "protectedRightsValueReturned": False,
    }
    if not publish_request_started:
        failure["mutationPerformed"] = False
    print(json.dumps(failure, sort_keys=True, separators=(",", ":")))
    raise SystemExit(1)
finally:
    if conn is not None:
        conn.close()
'''


class EvidenceObservatoryCagPublicationRuntime:
    def __init__(self) -> None:
        self.container = os.getenv("SOVEREIGN_BACKEND_CONTAINER", "sovereign-backend").strip()

    def publish_staging(
        self,
        *,
        expected_revision: str,
        expected_image_digest: str,
        owner_approved: bool,
    ) -> dict[str, Any]:
        revision = str(expected_revision or "").strip().lower()
        digest = str(expected_image_digest or "").strip().lower()
        if not owner_approved:
            raise ValueError("Explizite Owner-Freigabe für die CAG-Staging-Publikation fehlt")
        if not COMMIT_SHA_RE.fullmatch(revision):
            raise ValueError("expected_revision muss ein vollständiger Commit-SHA sein")
        if not IMAGE_DIGEST_RE.fullmatch(digest):
            raise ValueError("expected_image_digest muss ein vollständiger sha256-Digest sein")
        if not CONTAINER_RE.fullmatch(self.container):
            raise ValueError("Backend-Containername ist ungültig")

        completed = subprocess.run(
            ["docker", "exec", "-i", self.container, "python3", "-", revision, digest],
            input=_BACKEND_CAG_STAGING_PUBLISH_SCRIPT,
            capture_output=True,
            text=True,
            timeout=720,
            check=False,
            env={
                **os.environ,
                "PATH": os.environ.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"),
            },
        )
        lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        payload: dict[str, Any] = {}
        if lines:
            try:
                candidate = json.loads(lines[-1])
                if isinstance(candidate, dict):
                    payload = candidate
            except json.JSONDecodeError:
                payload = {}

        publisher_status = str(payload.get("publisherStatus") or "")
        case_ids = payload.get("caseIds") if isinstance(payload.get("caseIds"), list) else []
        hashes_valid = all(
            re.fullmatch(r"[0-9a-f]{64}", str(payload.get(key) or ""))
            for key in ("batchSha256", "dataSha256", "manifestSha256", "privacyScanHash", "licenseRightsHash", "publisherPolicyHash")
        )
        published_verified = bool(
            publisher_status == "PUBLISHED_VERIFIED"
            and payload.get("status") == "CAG_STAGING_PUBLICATION_VERIFIED"
            and payload.get("targetReadbackVerified") is True
            and payload.get("publicationReceiptPersisted") is True
            and payload.get("persistenceVerified") is True
            and re.fullmatch(r"[0-9a-f]{40}", str(payload.get("commitOid") or ""))
            and re.fullmatch(r"[0-9a-f]{64}", str(payload.get("publicationReceiptSha256") or ""))
            and payload.get("mutationPerformed") is True
        )
        duplicate_verified = bool(
            publisher_status == "DUPLICATE_NOOP"
            and payload.get("status") == "CAG_STAGING_DUPLICATE_NOOP_VERIFIED"
            and payload.get("duplicateSemanticPublishSkipped") is True
            and payload.get("targetReadbackVerified") is False
            and payload.get("publicationReceiptPersisted") is False
            and payload.get("mutationPerformed") is False
        )
        verified = bool(
            completed.returncode == 0
            and payload.get("ok") is True
            and payload.get("sourceRevision") == revision
            and payload.get("imageDigest") == digest
            and payload.get("repoId") == HF_REPO_ID
            and payload.get("revision") == HF_REVISION
            and case_ids == list(CAG_CASE_IDS)
            and hashes_valid
            and payload.get("rightsReceiptValidatedByPublisher") is True
            and payload.get("secretValuesReturned") is False
            and payload.get("protectedRightsValueReturned") is False
            and (published_verified or duplicate_verified)
        )
        if verified:
            return payload
        failure: dict[str, Any] = {
            "ok": False,
            "status": "CAG_STAGING_PUBLICATION_FAILED",
            "failureFamily": "CAG_STAGING_PUBLICATION_EVIDENCE_INCOMPLETE",
            "blocker": "CAG-Staging-Publisher, Rights-Gate, Target-Readback oder Receipt-Persistenz ist unvollständig",
            "sourceRevision": revision,
            "imageDigest": digest,
            "readback": payload,
            "exitCode": completed.returncode,
            "stderrType": "present" if completed.stderr.strip() else "empty",
            "mutationState": str(payload.get("mutationState") or "UNKNOWN"),
            "secretValuesReturned": False,
            "protectedRightsValueReturned": False,
        }
        if isinstance(payload.get("mutationPerformed"), bool):
            failure["mutationPerformed"] = payload["mutationPerformed"]
        return failure
