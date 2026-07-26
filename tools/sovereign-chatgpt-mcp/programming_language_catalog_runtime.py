from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any


COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
CATALOG_REVISION = "af9c4489e9151c5598622950631def2d4d561e94"
CATALOG_TITLE = "ProgrammiersprachenMD · kuratierter Sprachkatalog"


_BACKEND_PERSISTENT_IMPORT_SCRIPT = r'''
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


expected_revision, expected_digest, expected_catalog_revision = sys.argv[1:4]
admin_key = os.environ.get("ADMIN_API_KEY", "").strip()
conn = None
mutation_started = False


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
        with urllib.request.urlopen(request, timeout=420) as response:
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


def scalar(cursor, sql: str, params=()) -> int:
    cursor.execute(sql, params)
    row = cursor.fetchone()
    if isinstance(row, dict):
        return int(next(iter(row.values())) or 0)
    return int(row[0] or 0)


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

    mutation_started = True
    first_status, first = request_json(
        "POST",
        "/api/admin/knowledge/catalogs/programming-languages/import",
    )
    if first_status not in {200, 201} or first.get("ok") is not True:
        raise RuntimeError("first catalog import did not succeed")
    if first.get("catalogRevision") != expected_catalog_revision:
        raise RuntimeError("first catalog import returned a different pinned revision")
    first_source = first.get("source") if isinstance(first.get("source"), dict) else {}
    source_id = str(first_source.get("id") or "")
    content_sha256 = str(first.get("contentSha256") or "")
    if not source_id or not re.fullmatch(r"[0-9a-f-]{36}", source_id):
        raise RuntimeError("first catalog import returned no valid source identity")
    if not re.fullmatch(r"[0-9a-f]{64}", content_sha256):
        raise RuntimeError("first catalog import returned no valid content identity")

    second_status, second = request_json(
        "POST",
        "/api/admin/knowledge/catalogs/programming-languages/import",
    )
    second_source = second.get("source") if isinstance(second.get("source"), dict) else {}
    if (
        second_status != 200
        or second.get("ok") is not True
        or second.get("duplicate") is not True
        or second.get("catalogRevision") != expected_catalog_revision
        or str(second_source.get("id") or "") != source_id
        or str(second.get("contentSha256") or "") != content_sha256
    ):
        raise RuntimeError("second catalog import did not prove deterministic deduplication")

    list_status, listing = request_json("GET", "/api/admin/knowledge/sources")
    sources = listing.get("sources") if isinstance(listing.get("sources"), list) else []
    api_source = next(
        (
            item
            for item in sources
            if isinstance(item, dict) and str(item.get("id") or "") == source_id
        ),
        None,
    )
    if list_status != 200 or not isinstance(api_source, dict):
        raise RuntimeError("catalog source is not visible in the authenticated Knowledge Library projection")

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
            """SELECT id::text AS "sourceId", user_id::text AS "userId",
                      source_type AS "sourceType", source_url AS "sourceUrl",
                      title, content_sha256 AS "contentSha256", status,
                      content_bytes AS "contentBytes", chunk_count AS "chunkCount",
                      metadata, blocker
               FROM knowledge_sources
               WHERE id=%s::uuid
               LIMIT 1""",
            (source_id,),
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError("persisted catalog source row is missing")
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        user_id = str(row.get("userId") or "")
        chunk_count = int(row.get("chunkCount") or 0)
        linked_blocks = scalar(
            cur,
            "SELECT COUNT(*) FROM knowledge_source_blocks WHERE source_id=%s::uuid",
            (source_id,),
        )
        embedded_blocks = scalar(
            cur,
            """SELECT COUNT(*)
               FROM knowledge_source_blocks link
               JOIN knowledge_blocks block ON block.id=link.block_id
               WHERE link.source_id=%s::uuid AND block.embedding IS NOT NULL""",
            (source_id,),
        )
        missing_embeddings = scalar(
            cur,
            """SELECT COUNT(*)
               FROM knowledge_source_blocks link
               JOIN knowledge_blocks block ON block.id=link.block_id
               WHERE link.source_id=%s::uuid AND block.embedding IS NULL""",
            (source_id,),
        )
        candidate_count = scalar(
            cur,
            "SELECT COUNT(*) FROM knowledge_learning_candidates WHERE source_id=%s::uuid",
            (source_id,),
        )
        outbox_count = scalar(
            cur,
            """SELECT COUNT(*)
               FROM vector_index_outbox outbox
               JOIN knowledge_source_blocks link ON link.block_id::text=outbox.entity_id
               WHERE link.source_id=%s::uuid
                 AND outbox.entity_type='knowledge_block'""",
            (source_id,),
        )
        duplicate_source_rows = scalar(
            cur,
            """SELECT COUNT(*)
               FROM knowledge_sources
               WHERE user_id=%s::uuid AND content_sha256=%s""",
            (user_id, content_sha256),
        )

    required_metadata = {
        "originRevision": expected_catalog_revision,
        "commitSha": expected_catalog_revision,
        "authority": "curated-reference",
        "bugfixObservationAuthority": "unverified-reference-candidate",
        "sourcePinned": True,
    }
    for key, expected in required_metadata.items():
        if metadata.get(key) != expected:
            raise RuntimeError(f"catalog metadata mismatch: {key}")
    tree_sha = str(metadata.get("treeSha") or "")
    language_count = int(metadata.get("languageCount") or 0)
    bugfix_count = int(metadata.get("bugfixObservationCount") or 0)
    embedded_metadata = int(metadata.get("embeddedChunks") or 0)
    if not re.fullmatch(r"[0-9a-f]{40}", tree_sha):
        raise RuntimeError("catalog tree identity is missing")
    if (
        row.get("status") != "ready"
        or chunk_count <= 0
        or linked_blocks != chunk_count
        or embedded_blocks != chunk_count
        or embedded_metadata != chunk_count
        or missing_embeddings != 0
        or candidate_count != chunk_count
        or outbox_count != chunk_count
        or duplicate_source_rows != 1
        or language_count <= 0
    ):
        raise RuntimeError("catalog persistence, vector or deduplication evidence is incomplete")
    if (
        str(api_source.get("title") or "") != str(row.get("title") or "")
        or str(api_source.get("contentSha256") or "") != content_sha256
        or int(api_source.get("chunkCount") or 0) != chunk_count
        or (api_source.get("metadata") or {}).get("originRevision") != expected_catalog_revision
    ):
        raise RuntimeError("Knowledge Library API projection does not match the persisted source")

    payload = {
        "ok": True,
        "status": "PROGRAMMING_LANGUAGE_CATALOG_PERSISTENT_IMPORT_VERIFIED",
        "sourceRevision": expected_revision,
        "imageDigest": expected_digest,
        "catalog": {
            "catalogRevision": expected_catalog_revision,
            "commitSha": str(metadata.get("commitSha") or ""),
            "treeSha": tree_sha,
            "sourceId": source_id,
            "sourceUrl": str(row.get("sourceUrl") or ""),
            "title": str(row.get("title") or ""),
            "status": str(row.get("status") or ""),
            "contentSha256": content_sha256,
            "contentBytes": int(row.get("contentBytes") or 0),
            "chunkCount": chunk_count,
            "linkedBlocks": linked_blocks,
            "embeddedBlocks": embedded_blocks,
            "missingEmbeddings": missing_embeddings,
            "learningCandidateCount": candidate_count,
            "outboxCount": outbox_count,
            "languageCount": language_count,
            "bugfixObservationCount": bugfix_count,
            "authority": str(metadata.get("authority") or ""),
            "bugfixObservationAuthority": str(metadata.get("bugfixObservationAuthority") or ""),
            "sourcePinned": metadata.get("sourcePinned") is True,
            "embeddingModel": str(metadata.get("embeddingModel") or ""),
            "embeddingProviderPresent": bool(metadata.get("embeddingProvider")),
            "userAssignmentFingerprint": digest_text(user_id)[:24],
        },
        "http": {
            "firstImportStatus": first_status,
            "firstImportDuplicate": first.get("duplicate") is True,
            "secondImportStatus": second_status,
            "secondImportDuplicate": True,
            "knowledgeLibraryListStatus": list_status,
            "knowledgeLibraryProjectionVisible": True,
        },
        "deduplication": {
            "sameSourceId": True,
            "sameContentSha256": True,
            "sourceRowsForUserAndContent": duplicate_source_rows,
        },
        "mutationPerformed": True,
        "persistentMutation": True,
        "secretValuesReturned": False,
        "documentContentReturned": False,
    }
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
except Exception as exc:
    print(json.dumps({
        "ok": False,
        "status": "PROGRAMMING_LANGUAGE_CATALOG_PERSISTENT_IMPORT_FAILED",
        "sourceRevision": expected_revision,
        "imageDigest": expected_digest,
        "failureType": type(exc).__name__,
        "failureSha256": digest_text(exc),
        "mutationPerformed": mutation_started,
        "persistentMutation": mutation_started,
        "secretValuesReturned": False,
        "documentContentReturned": False,
    }, sort_keys=True, separators=(",", ":")))
    raise SystemExit(1)
finally:
    if conn is not None:
        conn.close()
'''


class ProgrammingLanguageCatalogRuntime:
    def __init__(self) -> None:
        self.container = os.getenv("SOVEREIGN_BACKEND_CONTAINER", "sovereign-backend").strip()

    def persistent_import(
        self,
        *,
        expected_revision: str,
        expected_image_digest: str,
        owner_approved: bool,
    ) -> dict[str, Any]:
        revision = str(expected_revision or "").strip().lower()
        digest = str(expected_image_digest or "").strip().lower()
        if not owner_approved:
            raise ValueError("Explizite Owner-Freigabe für den persistenten Katalogimport fehlt")
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
                CATALOG_REVISION,
            ],
            input=_BACKEND_PERSISTENT_IMPORT_SCRIPT,
            capture_output=True,
            text=True,
            timeout=960,
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

        catalog = payload.get("catalog") if isinstance(payload.get("catalog"), dict) else {}
        http = payload.get("http") if isinstance(payload.get("http"), dict) else {}
        dedupe = payload.get("deduplication") if isinstance(payload.get("deduplication"), dict) else {}
        chunk_count = int(catalog.get("chunkCount") or 0)
        verified = bool(
            completed.returncode == 0
            and payload.get("ok") is True
            and payload.get("status") == "PROGRAMMING_LANGUAGE_CATALOG_PERSISTENT_IMPORT_VERIFIED"
            and payload.get("sourceRevision") == revision
            and payload.get("imageDigest") == digest
            and catalog.get("catalogRevision") == CATALOG_REVISION
            and catalog.get("commitSha") == CATALOG_REVISION
            and re.fullmatch(r"[0-9a-f]{40}", str(catalog.get("treeSha") or ""))
            and catalog.get("status") == "ready"
            and chunk_count > 0
            and catalog.get("linkedBlocks") == chunk_count
            and catalog.get("embeddedBlocks") == chunk_count
            and catalog.get("missingEmbeddings") == 0
            and catalog.get("learningCandidateCount") == chunk_count
            and catalog.get("outboxCount") == chunk_count
            and int(catalog.get("languageCount") or 0) > 0
            and catalog.get("authority") == "curated-reference"
            and catalog.get("bugfixObservationAuthority") == "unverified-reference-candidate"
            and catalog.get("sourcePinned") is True
            and http.get("secondImportStatus") == 200
            and http.get("secondImportDuplicate") is True
            and http.get("knowledgeLibraryProjectionVisible") is True
            and dedupe.get("sameSourceId") is True
            and dedupe.get("sameContentSha256") is True
            and dedupe.get("sourceRowsForUserAndContent") == 1
            and payload.get("persistentMutation") is True
            and payload.get("secretValuesReturned") is False
            and payload.get("documentContentReturned") is False
        )
        if verified:
            return payload
        return {
            "ok": False,
            "status": "PROGRAMMING_LANGUAGE_CATALOG_PERSISTENT_IMPORT_FAILED",
            "failureFamily": "PROGRAMMING_LANGUAGE_CATALOG_EVIDENCE_INCOMPLETE",
            "blocker": "Persistenter Import, Deduplizierung, Vector- oder Knowledge-Library-Readback ist unvollständig",
            "sourceRevision": revision,
            "imageDigest": digest,
            "readback": payload,
            "exitCode": completed.returncode,
            "stderrType": "present" if completed.stderr.strip() else "empty",
            "mutationPerformed": bool(payload.get("mutationPerformed")),
            "persistentMutation": bool(payload.get("persistentMutation")),
            "secretValuesReturned": False,
            "documentContentReturned": False,
        }
