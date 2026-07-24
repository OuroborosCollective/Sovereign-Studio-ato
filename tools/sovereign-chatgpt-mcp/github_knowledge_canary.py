from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any


COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
PUBLIC_SOURCE_URL = "https://github.com/octocat/Hello-World/blob/master/README"


_BACKEND_CANARY_SCRIPT = r'''
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
import uuid

import psycopg2
import psycopg2.extras
import requests


expected_revision, expected_digest, source_url = sys.argv[1:4]
source_id = str(uuid.uuid4())
audit_id = ""
block_ids: list[str] = []
cleanup = {
    "sourceRows": -1,
    "linkRows": -1,
    "candidateRows": -1,
    "blockRows": -1,
    "outboxRows": -1,
    "auditRows": -1,
}
evidence: dict[str, object] = {}
failure: dict[str, object] | None = None
conn = None


def digest_text(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8", errors="replace")).hexdigest()


def scalar(cursor, sql: str, params=()) -> int:
    cursor.execute(sql, params)
    row = cursor.fetchone()
    if isinstance(row, dict):
        return int(next(iter(row.values())) or 0)
    return int(row[0] or 0)


try:
    runtime_revision = os.environ.get("SOVEREIGN_SOURCE_REVISION", "").strip()
    runtime_digest = os.environ.get("SOVEREIGN_IMAGE_DIGEST", "").strip()
    if runtime_revision != expected_revision or runtime_digest != expected_digest:
        raise RuntimeError("backend runtime identity mismatch")

    with urllib.request.urlopen("http://127.0.0.1:8787/health", timeout=8) as response:
        health_body = response.read(1_000_000)
    health = json.loads(health_body.decode("utf-8"))
    if (
        health.get("ok") is not True
        or health.get("sourceRevision") != expected_revision
        or health.get("imageDigest") != expected_digest
    ):
        raise RuntimeError("backend health identity mismatch")

    import knowledge_library

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
            """SELECT id::text AS id, email
               FROM admin_users
               ORDER BY created_at ASC, id ASC
               LIMIT 1"""
        )
        admin = cur.fetchone()
    if not admin or not admin.get("id") or not admin.get("email"):
        raise RuntimeError("no persistent admin identity available for canary")
    admin_id = str(admin["id"])
    admin_email = str(admin["email"])

    original_token = os.environ.pop("TOOLCHAIN_GITHUB_TOKEN", None)
    original_pat = os.environ.pop("GITHUB_PERSONAL_ACCESS_TOKEN", None)
    original_github_get = knowledge_library._github_get
    github_calls: list[dict[str, object]] = []

    def recording_github_get(url: str, *, headers: dict[str, str]):
        github_calls.append({
            "host": str(url).split("/", 3)[2] if "://" in str(url) else "",
            "authorizationPresent": any(key.lower() == "authorization" for key in headers),
        })
        return original_github_get(url, headers=headers)

    knowledge_library._github_get = recording_github_get
    try:
        document = knowledge_library.fetch_url_document(source_url)
    finally:
        knowledge_library._github_get = original_github_get
        if original_token is not None:
            os.environ["TOOLCHAIN_GITHUB_TOKEN"] = original_token
        if original_pat is not None:
            os.environ["GITHUB_PERSONAL_ACCESS_TOKEN"] = original_pat

    if not github_calls or any(bool(call["authorizationPresent"]) for call in github_calls):
        raise RuntimeError("public GitHub fetch was not credential-free")
    if document.source_type != "github" or not document.text.strip():
        raise RuntimeError("public GitHub source did not produce a knowledge document")
    if len(document.text) >= 1_000:
        raise RuntimeError("fixed public GitHub canary source exceeded the single-chunk safety bound")

    marker = f"SOVEREIGN_GITHUB_KNOWLEDGE_CANARY:{expected_revision}:{source_id}"
    marker_sha256 = digest_text(marker)
    canary_text = f"# Sovereign live canary\n\n{marker}\n\n{document.text}"
    if len(knowledge_library.chunk_document(canary_text)) != 1:
        raise RuntimeError("canary source no longer maps to exactly one unique cleanup-bound block")
    canary_document = knowledge_library.KnowledgeDocument(
        source_type=document.source_type,
        title=f"Sovereign GitHub knowledge canary {expected_revision[:12]}",
        text=canary_text,
        source_url=document.source_url,
        metadata={
            **document.metadata,
            "liveCanary": True,
            "markerSha256": marker_sha256,
            "expectedRevision": expected_revision,
        },
    )
    inserted = knowledge_library._insert_document(
        conn,
        admin_id,
        canary_document,
        source_id_override=source_id,
    )
    source = inserted.get("source") if isinstance(inserted, dict) else {}
    if (
        inserted.get("duplicate") is not False
        or source.get("id") != source_id
        or source.get("status") != "ready"
        or int(source.get("chunkCount") or 0) <= 0
        or int(source.get("embeddedChunks") or 0) != int(source.get("chunkCount") or 0)
    ):
        raise RuntimeError("knowledge persistence did not reach fully embedded ready state")

    with conn.cursor() as cur:
        cur.execute(
            """SELECT status, chunk_count AS "chunkCount",
                      content_sha256 AS "contentSha256",
                      metadata->>'embeddedChunks' AS "embeddedChunks",
                      metadata->>'embeddingModel' AS "embeddingModel",
                      metadata->>'embeddingProvider' AS "embeddingProvider"
               FROM knowledge_sources WHERE id=%s::uuid""",
            (source_id,),
        )
        source_row = cur.fetchone()
        cur.execute(
            """SELECT block_id::text AS id
               FROM knowledge_source_blocks
               WHERE source_id=%s::uuid
               ORDER BY ordinal""",
            (source_id,),
        )
        block_ids = [str(row["id"]) for row in cur.fetchall()]
        link_count = len(block_ids)
        embedded_count = scalar(
            cur,
            """SELECT COUNT(*)
               FROM knowledge_source_blocks link
               JOIN knowledge_blocks block ON block.id=link.block_id
               WHERE link.source_id=%s::uuid AND block.embedding IS NOT NULL""",
            (source_id,),
        )
        candidate_count = scalar(
            cur,
            "SELECT COUNT(*) FROM knowledge_learning_candidates WHERE source_id=%s::uuid",
            (source_id,),
        )
        outbox_count = scalar(
            cur,
            """SELECT COUNT(*) FROM vector_index_outbox
               WHERE entity_type='knowledge_block' AND entity_id=ANY(%s)""",
            (block_ids,),
        )

    chunk_count = int(source_row.get("chunkCount") or 0) if source_row else 0
    if (
        not source_row
        or source_row.get("status") != "ready"
        or chunk_count <= 0
        or int(source_row.get("embeddedChunks") or 0) != chunk_count
        or link_count != chunk_count
        or embedded_count != chunk_count
        or candidate_count != chunk_count
        or outbox_count != chunk_count
    ):
        raise RuntimeError("persisted knowledge provenance or vector evidence is incomplete")

    sensitive_detail = f"DO_NOT_PERSIST_{uuid.uuid4().hex}"
    original_requests_get = knowledge_library.requests.get

    def raise_timeout(*_args, **_kwargs):
        raise requests.Timeout(sensitive_detail)

    knowledge_library.requests.get = raise_timeout
    try:
        try:
            knowledge_library._github_json("/repos/sovereign-canary/transport")
            raise RuntimeError("controlled transport failure was not raised")
        except knowledge_library.GitHubKnowledgeAccessError as transport_error:
            if (
                transport_error.blocker != "github_api_timeout"
                or transport_error.github_status is not None
                or transport_error.response_status != 504
                or sensitive_detail in str(transport_error)
            ):
                raise RuntimeError("controlled transport failure classification mismatch")
    finally:
        knowledge_library.requests.get = original_requests_get

    def audit_recorder(action: str, target_id: str | None, changes: dict[str, object]) -> None:
        nonlocal_audit = None
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO audit_log (admin_id, admin_email, action, target_id, changes)
                   VALUES (%s::uuid, %s, %s, %s, %s::jsonb)
                   RETURNING id::text AS id""",
                (
                    admin_id,
                    admin_email,
                    action,
                    target_id,
                    json.dumps(changes, sort_keys=True, separators=(",", ":")),
                ),
            )
            nonlocal_audit = str(cur.fetchone()["id"])
        conn.commit()
        audit_ids.append(nonlocal_audit)

    audit_ids: list[str] = []
    failure_url = f"https://github.com/sovereign-canary/transport?token={sensitive_detail}"
    transport_error = knowledge_library.GitHubKnowledgeAccessError(
        "GitHub hat über HTTPS/443 nicht rechtzeitig geantwortet.",
        blocker="github_api_timeout",
        response_status=504,
    )
    correlation_id, audit_recorded = knowledge_library._record_github_import_failure(
        audit_recorder,
        failure_url,
        transport_error,
    )
    audit_id = audit_ids[0] if audit_ids else ""
    if not audit_recorded or not audit_id:
        raise RuntimeError("bounded GitHub failure audit was not persisted")

    with conn.cursor() as cur:
        cur.execute(
            """SELECT action, target_id AS "targetId", changes
               FROM audit_log WHERE id=%s::uuid""",
            (audit_id,),
        )
        audit_row = cur.fetchone()
    audit_serialized = json.dumps(audit_row, sort_keys=True, separators=(",", ":"), default=str)
    if (
        not audit_row
        or audit_row.get("action") != "knowledge:github_import_failed"
        or not str(audit_row.get("targetId") or "").startswith("github:")
        or str((audit_row.get("changes") or {}).get("blocker") or "") != "github_api_timeout"
        or str((audit_row.get("changes") or {}).get("correlationId") or "") != correlation_id
        or sensitive_detail in audit_serialized
        or "sovereign-canary/transport" in audit_serialized
    ):
        raise RuntimeError("failure audit leaked raw transport identity or lost blocker evidence")

    evidence = {
        "source": {
            "status": "ready",
            "chunkCount": chunk_count,
            "embeddedCount": embedded_count,
            "candidateCount": candidate_count,
            "outboxCount": outbox_count,
            "contentSha256": str(source_row.get("contentSha256") or ""),
            "embeddingModel": str(source_row.get("embeddingModel") or ""),
            "embeddingProviderPresent": bool(source_row.get("embeddingProvider")),
            "markerSha256": marker_sha256,
            "publicReadWithoutCredential": True,
            "githubRequestCount": len(github_calls),
            "sourceUrlFingerprint": digest_text(source_url)[:24],
        },
        "transportFailure": {
            "blocker": "github_api_timeout",
            "httpStatus": 504,
            "auditRecorded": True,
            "targetFingerprintPresent": True,
            "rawUrlPersisted": False,
            "rawExceptionPersisted": False,
            "correlationIdSha256": digest_text(correlation_id),
        },
    }
except Exception as exc:
    failure = {
        "type": type(exc).__name__,
        "messageSha256": digest_text(exc),
    }
finally:
    if conn is not None:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            with conn.cursor() as cur:
                if audit_id:
                    cur.execute("DELETE FROM audit_log WHERE id=%s::uuid", (audit_id,))
                if block_ids:
                    cur.execute(
                        """DELETE FROM vector_index_outbox
                           WHERE entity_type='knowledge_block' AND entity_id=ANY(%s)""",
                        (block_ids,),
                    )
                cur.execute("DELETE FROM knowledge_sources WHERE id=%s::uuid", (source_id,))
                if block_ids:
                    cur.execute(
                        """DELETE FROM knowledge_blocks block
                           WHERE block.id::text=ANY(%s)
                             AND NOT EXISTS (
                                 SELECT 1 FROM knowledge_source_blocks link
                                 WHERE link.block_id=block.id
                             )""",
                        (block_ids,),
                    )
            conn.commit()
            with conn.cursor() as cur:
                cleanup["sourceRows"] = scalar(
                    cur,
                    "SELECT COUNT(*) FROM knowledge_sources WHERE id=%s::uuid",
                    (source_id,),
                )
                cleanup["linkRows"] = scalar(
                    cur,
                    "SELECT COUNT(*) FROM knowledge_source_blocks WHERE source_id=%s::uuid",
                    (source_id,),
                )
                cleanup["candidateRows"] = scalar(
                    cur,
                    "SELECT COUNT(*) FROM knowledge_learning_candidates WHERE source_id=%s::uuid",
                    (source_id,),
                )
                cleanup["blockRows"] = (
                    scalar(cur, "SELECT COUNT(*) FROM knowledge_blocks WHERE id::text=ANY(%s)", (block_ids,))
                    if block_ids else 0
                )
                cleanup["outboxRows"] = (
                    scalar(
                        cur,
                        """SELECT COUNT(*) FROM vector_index_outbox
                           WHERE entity_type='knowledge_block' AND entity_id=ANY(%s)""",
                        (block_ids,),
                    )
                    if block_ids else 0
                )
                cleanup["auditRows"] = (
                    scalar(cur, "SELECT COUNT(*) FROM audit_log WHERE id=%s::uuid", (audit_id,))
                    if audit_id else 0
                )
        except Exception as cleanup_exc:
            try:
                conn.rollback()
            except Exception:
                pass
            cleanup["failureType"] = type(cleanup_exc).__name__
            cleanup["failureSha256"] = digest_text(cleanup_exc)
        finally:
            conn.close()

cleanup_ok = all(cleanup.get(key) == 0 for key in (
    "sourceRows", "linkRows", "candidateRows", "blockRows", "outboxRows", "auditRows"
))
if failure is None and not cleanup_ok:
    failure = {
        "type": "CleanupIncomplete",
        "messageSha256": digest_text(cleanup),
    }

payload = {
    "ok": failure is None and cleanup_ok,
    "status": (
        "GITHUB_KNOWLEDGE_LIVE_CANARY_VERIFIED"
        if failure is None and cleanup_ok
        else "GITHUB_KNOWLEDGE_LIVE_CANARY_FAILED"
    ),
    "sourceRevision": expected_revision,
    "imageDigest": expected_digest,
    "evidence": evidence,
    "cleanup": cleanup,
    "cleanupVerified": cleanup_ok,
    "failure": failure,
    "mutationPerformed": True,
    "secretValuesReturned": False,
    "documentContentReturned": False,
}
print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
raise SystemExit(0 if payload["ok"] else 1)
'''


class GitHubKnowledgeCanaryRuntime:
    def __init__(self) -> None:
        self.container = os.getenv("SOVEREIGN_BACKEND_CONTAINER", "sovereign-backend").strip()

    def live_canary(self, *, expected_revision: str, expected_image_digest: str) -> dict[str, Any]:
        revision = str(expected_revision or "").strip().lower()
        digest = str(expected_image_digest or "").strip().lower()
        if not COMMIT_SHA_RE.fullmatch(revision):
            raise ValueError("expected_revision muss ein vollständiger Commit-SHA sein")
        if not IMAGE_DIGEST_RE.fullmatch(digest):
            raise ValueError("expected_image_digest muss ein vollständiger sha256-Digest sein")
        if not CONTAINER_RE.fullmatch(self.container):
            raise ValueError("Backend-Containername ist ungültig")

        completed = subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                self.container,
                "python3",
                "-",
                revision,
                digest,
                PUBLIC_SOURCE_URL,
            ],
            input=_BACKEND_CANARY_SCRIPT,
            capture_output=True,
            text=True,
            timeout=420,
            check=False,
            env={
                **os.environ,
                "PATH": os.environ.get(
                    "PATH",
                    "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                ),
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

        evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
        source = evidence.get("source") if isinstance(evidence.get("source"), dict) else {}
        transport = (
            evidence.get("transportFailure")
            if isinstance(evidence.get("transportFailure"), dict)
            else {}
        )
        cleanup = payload.get("cleanup") if isinstance(payload.get("cleanup"), dict) else {}
        chunk_count = source.get("chunkCount") if isinstance(source.get("chunkCount"), int) else 0
        verified = bool(
            completed.returncode == 0
            and payload.get("ok") is True
            and payload.get("status") == "GITHUB_KNOWLEDGE_LIVE_CANARY_VERIFIED"
            and payload.get("sourceRevision") == revision
            and payload.get("imageDigest") == digest
            and source.get("status") == "ready"
            and source.get("publicReadWithoutCredential") is True
            and chunk_count > 0
            and source.get("embeddedCount") == chunk_count
            and source.get("candidateCount") == chunk_count
            and source.get("outboxCount") == chunk_count
            and transport.get("blocker") == "github_api_timeout"
            and transport.get("httpStatus") == 504
            and transport.get("auditRecorded") is True
            and transport.get("rawUrlPersisted") is False
            and transport.get("rawExceptionPersisted") is False
            and payload.get("cleanupVerified") is True
            and all(cleanup.get(key) == 0 for key in (
                "sourceRows",
                "linkRows",
                "candidateRows",
                "blockRows",
                "outboxRows",
                "auditRows",
            ))
            and payload.get("secretValuesReturned") is False
            and payload.get("documentContentReturned") is False
        )
        if verified:
            return payload
        return {
            "ok": False,
            "status": "GITHUB_KNOWLEDGE_LIVE_CANARY_FAILED",
            "failureFamily": "GITHUB_KNOWLEDGE_LIVE_CANARY_FAILED",
            "blocker": "GitHub-Knowledge-Import, Transportfehler-Evidence oder Cleanup ist unvollständig",
            "sourceRevision": revision,
            "imageDigest": digest,
            "readback": payload,
            "exitCode": completed.returncode,
            "stderrType": "present" if completed.stderr.strip() else "empty",
            "secretValuesReturned": False,
            "documentContentReturned": False,
        }
