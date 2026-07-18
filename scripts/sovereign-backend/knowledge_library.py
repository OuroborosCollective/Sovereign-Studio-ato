"""Persistent reference knowledge library for Sovereign Studio.

Reference knowledge is deliberately separate from evidence-derived agent
experience. Sources are fetched or uploaded, content-hashed, chunked, embedded
with a real provider and stored in PostgreSQL/pgvector. Browser-direct vector DB
connections and arbitrary URL fetching are not part of this live path.
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import io
import json
import os
import re
from typing import Any, Callable, Iterable
from urllib.parse import quote, unquote, urlparse
import uuid

from flask import jsonify, request
import psycopg2.extras
import requests

from r2_storage import (
    MAX_KNOWLEDGE_BYTES,
    MAX_PDF_KNOWLEDGE_BYTES,
    R2EvidenceMismatch,
    R2ObjectMissing,
    R2Storage,
    R2StorageError,
    R2StorageUnavailable,
    knowledge_object_key,
    validate_knowledge_upload,
)
from vector_embedding import EMBEDDING_MODEL, EmbeddingUnavailable, embed_texts, vector_literal

ConnectionFactory = Callable[[], Any]

MAX_UPLOAD_BYTES = MAX_KNOWLEDGE_BYTES
MAX_PDF_UPLOAD_BYTES = MAX_PDF_KNOWLEDGE_BYTES
MAX_SOURCE_TEXT_CHARS = 12_000_000
MAX_GITHUB_FILES = 80
MAX_GITHUB_FILE_BYTES = 512 * 1024
MAX_GITHUB_TOTAL_BYTES = 6 * 1024 * 1024
MAX_PDF_PAGES = 500
CHUNK_TARGET_CHARS = 1_800
CHUNK_OVERLAP_CHARS = 220
MAX_SEARCH_LIMIT = 20

_MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdx"}
_TEXT_EXTENSIONS = {
    *_MARKDOWN_EXTENSIONS, ".txt", ".rst", ".json", ".yaml", ".yml", ".toml",
    ".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".kt", ".kts",
    ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx",
    ".rs", ".go", ".cs", ".php", ".rb", ".sh", ".sql", ".html", ".css",
}


@dataclass(frozen=True)
class KnowledgeDocument:
    source_type: str
    title: str
    text: str
    source_url: str | None
    metadata: dict[str, Any]


@dataclass(frozen=True)
class KnowledgeChunk:
    ordinal: int
    section_title: str
    content: str
    content_sha256: str


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_title(value: str, fallback: str = "Knowledge source") -> str:
    clean = re.sub(r"\s+", " ", str(value or "")).strip()
    return (clean or fallback)[:240]


def _close(conn: Any) -> None:
    close = getattr(conn, "close", None)
    if callable(close):
        close()


def _github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "sovereign-knowledge-library/1.0",
    }
    token = (
        os.getenv("TOOLCHAIN_GITHUB_TOKEN", "").strip()
        or os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", "").strip()
    )
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _github_json(path: str) -> Any:
    response = requests.get(
        f"https://api.github.com{path}",
        headers=_github_headers(),
        timeout=25,
    )
    if not response.ok:
        raise ValueError(f"GitHub returned HTTP {response.status_code}")
    return response.json()


def _decode_github_content(payload: dict[str, Any]) -> str:
    encoded = str(payload.get("content") or "").replace("\n", "")
    if not encoded:
        download_url = str(payload.get("download_url") or "")
        if not download_url:
            return ""
        response = requests.get(download_url, headers=_github_headers(), timeout=25)
        if not response.ok:
            raise ValueError(f"GitHub raw content returned HTTP {response.status_code}")
        return response.text
    raw = base64.b64decode(encoded)
    if len(raw) > MAX_GITHUB_FILE_BYTES:
        raise ValueError("GitHub file exceeds the per-file knowledge limit")
    return raw.decode("utf-8", errors="replace")


def _is_supported_repo_path(path: str, size: int) -> bool:
    lower = path.lower()
    if size <= 0 or size > MAX_GITHUB_FILE_BYTES:
        return False
    if any(part in lower for part in ("node_modules/", "dist/", "build/", ".git/", "vendor/")):
        return False
    name = lower.rsplit("/", 1)[-1]
    if name in {"readme", "license", "dockerfile", "makefile"}:
        return True
    suffix = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    return suffix in _TEXT_EXTENSIONS


def _github_document(url: str) -> KnowledgeDocument:
    parsed = urlparse(url)
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if parsed.hostname not in {"github.com", "www.github.com"} or len(parts) < 2:
        raise ValueError("Only canonical github.com repository or file URLs are accepted")

    owner, repo = parts[0], parts[1].removesuffix(".git")
    repo_info = _github_json(f"/repos/{quote(owner)}/{quote(repo)}")
    default_branch = str(repo_info.get("default_branch") or "main")
    branch = default_branch
    prefix = ""
    specific_file = ""

    if len(parts) >= 5 and parts[2] in {"blob", "tree"}:
        branch = parts[3]
        remainder = "/".join(parts[4:])
        if parts[2] == "blob":
            specific_file = remainder
        else:
            prefix = remainder.rstrip("/") + "/"

    if specific_file:
        payload = _github_json(
            f"/repos/{quote(owner)}/{quote(repo)}/contents/{quote(specific_file, safe='/')}?ref={quote(branch)}"
        )
        if not isinstance(payload, dict) or payload.get("type") != "file":
            raise ValueError("GitHub URL does not resolve to a file")
        text = _decode_github_content(payload)
        title = f"{owner}/{repo}: {specific_file}"
        return KnowledgeDocument(
            source_type="github",
            title=title,
            text=f"# {specific_file}\n\n{text}",
            source_url=url,
            metadata={
                "owner": owner,
                "repo": repo,
                "branch": branch,
                "paths": [specific_file],
                "commitSha": payload.get("sha"),
            },
        )

    tree = _github_json(
        f"/repos/{quote(owner)}/{quote(repo)}/git/trees/{quote(branch)}?recursive=1"
    )
    entries = tree.get("tree") if isinstance(tree, dict) else []
    candidates = []
    total_bytes = 0
    for entry in entries or []:
        path = str(entry.get("path") or "")
        size = int(entry.get("size") or 0)
        if prefix and not path.startswith(prefix):
            continue
        if not _is_supported_repo_path(path, size):
            continue
        if total_bytes + size > MAX_GITHUB_TOTAL_BYTES:
            break
        candidates.append((path, size, entry.get("sha")))
        total_bytes += size
        if len(candidates) >= MAX_GITHUB_FILES:
            break

    if not candidates:
        raise ValueError("GitHub source contains no supported text or code files within limits")

    sections: list[str] = []
    imported_paths: list[str] = []
    for path, _size, _sha in candidates:
        payload = _github_json(
            f"/repos/{quote(owner)}/{quote(repo)}/contents/{quote(path, safe='/')}?ref={quote(branch)}"
        )
        if not isinstance(payload, dict) or payload.get("type") != "file":
            continue
        content = _decode_github_content(payload)
        if not content.strip():
            continue
        sections.append(f"# FILE: {path}\n\n{content}")
        imported_paths.append(path)

    if not sections:
        raise ValueError("GitHub source files could not be read")

    return KnowledgeDocument(
        source_type="github",
        title=f"{owner}/{repo}" + (f"/{prefix.rstrip('/')}" if prefix else ""),
        text="\n\n".join(sections)[:MAX_SOURCE_TEXT_CHARS],
        source_url=url,
        metadata={
            "owner": owner,
            "repo": repo,
            "branch": branch,
            "paths": imported_paths,
            "treeSha": tree.get("sha") if isinstance(tree, dict) else None,
            "truncated": len(imported_paths) >= MAX_GITHUB_FILES,
        },
    )


def _wikipedia_document(url: str) -> KnowledgeDocument:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if not hostname.endswith(".wikipedia.org"):
        raise ValueError("Only wikipedia.org article URLs are accepted")
    marker = "/wiki/"
    if marker not in parsed.path:
        raise ValueError("Wikipedia URL must point to an article")
    article = unquote(parsed.path.split(marker, 1)[1]).replace("_", " ").strip()
    if not article:
        raise ValueError("Wikipedia article title is empty")

    response = requests.get(
        f"https://{hostname}/w/api.php",
        params={
            "action": "query",
            "prop": "extracts|info",
            "explaintext": "1",
            "redirects": "1",
            "inprop": "url",
            "titles": article,
            "format": "json",
            "formatversion": "2",
        },
        headers={"User-Agent": "sovereign-knowledge-library/1.0"},
        timeout=25,
    )
    if not response.ok:
        raise ValueError(f"Wikipedia returned HTTP {response.status_code}")
    pages = response.json().get("query", {}).get("pages", [])
    page = pages[0] if pages else {}
    text = str(page.get("extract") or "").strip()
    if not text:
        raise ValueError("Wikipedia article contains no extractable text")
    title = _safe_title(str(page.get("title") or article), article)
    return KnowledgeDocument(
        source_type="wikipedia",
        title=title,
        text=f"# {title}\n\n{text}"[:MAX_SOURCE_TEXT_CHARS],
        source_url=str(page.get("fullurl") or url),
        metadata={"pageId": page.get("pageid"), "languageHost": hostname},
    )


def fetch_url_document(url: str) -> KnowledgeDocument:
    value = str(url or "").strip()
    parsed = urlparse(value)
    if parsed.scheme != "https":
        raise ValueError("Knowledge URLs must use HTTPS")
    hostname = (parsed.hostname or "").lower()
    if hostname in {"github.com", "www.github.com"}:
        return _github_document(value)
    if hostname.endswith(".wikipedia.org"):
        return _wikipedia_document(value)
    raise ValueError("Allowed knowledge URL hosts are github.com and wikipedia.org")


def _pdf_document(filename: str, payload: bytes) -> KnowledgeDocument:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF import requires the pypdf backend dependency") from exc

    reader = PdfReader(io.BytesIO(payload))
    if len(reader.pages) > MAX_PDF_PAGES:
        raise ValueError(f"PDF exceeds the {MAX_PDF_PAGES}-page limit")
    pages: list[str] = []
    for index, page in enumerate(reader.pages):
        text = str(page.extract_text() or "").strip()
        if text:
            pages.append(f"# Page {index + 1}\n\n{text}")
    if not pages:
        raise ValueError("PDF contains no extractable text; scanned PDFs need preprocessing")
    return KnowledgeDocument(
        source_type="pdf",
        title=_safe_title(filename, "Uploaded PDF"),
        text="\n\n".join(pages)[:MAX_SOURCE_TEXT_CHARS],
        source_url=None,
        metadata={"filename": filename, "pages": len(reader.pages)},
    )


def upload_limit_bytes(filename: str) -> int:
    return MAX_PDF_UPLOAD_BYTES if str(filename or "").lower().endswith(".pdf") else MAX_UPLOAD_BYTES


def upload_document(filename: str, payload: bytes) -> KnowledgeDocument:
    if not payload:
        raise ValueError("Uploaded file is empty")
    maximum = upload_limit_bytes(filename)
    if len(payload) > maximum:
        raise ValueError(f"Uploaded file exceeds {maximum // (1024 * 1024)} MB")
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return _pdf_document(filename, payload)

    suffix = "." + lower.rsplit(".", 1)[-1] if "." in lower else ""
    if suffix not in _TEXT_EXTENSIONS:
        raise ValueError("Unsupported upload type; use PDF, text, Markdown or source code")
    text = payload.decode("utf-8", errors="replace").lstrip("\ufeff").strip()
    if not text:
        raise ValueError("Uploaded file contains no readable text")
    if suffix in {
        ".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".kt", ".kts",
        ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx",
        ".rs", ".go", ".cs", ".php", ".rb", ".sh", ".sql",
    }:
        source_type = "code"
    elif suffix in _MARKDOWN_EXTENSIONS:
        source_type = "markdown"
    else:
        source_type = "text"
    return KnowledgeDocument(
        source_type=source_type,
        title=_safe_title(filename, "Uploaded document"),
        text=f"# {filename}\n\n{text}"[:MAX_SOURCE_TEXT_CHARS],
        source_url=None,
        metadata={"filename": filename, "extension": suffix, "format": source_type},
    )


def chunk_document(text: str) -> list[KnowledgeChunk]:
    clean = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not clean:
        return []

    headings: list[tuple[str, str]] = []
    current_title = "Document"
    current_lines: list[str] = []
    for line in clean.split("\n"):
        heading_match = re.match(r"^\s*(?:#{1,6}\s+|FILE:\s*|Page\s+\d+\b)(.+)$", line, re.IGNORECASE)
        if heading_match and current_lines:
            headings.append((current_title, "\n".join(current_lines).strip()))
            current_lines = []
        if heading_match:
            current_title = _safe_title(heading_match.group(1), current_title)
        current_lines.append(line)
    if current_lines:
        headings.append((current_title, "\n".join(current_lines).strip()))

    chunks: list[KnowledgeChunk] = []
    seen_hashes: set[str] = set()
    ordinal = 0
    for section_title, section in headings:
        if not section:
            continue
        start = 0
        while start < len(section):
            end = min(len(section), start + CHUNK_TARGET_CHARS)
            if end < len(section):
                boundary = max(
                    section.rfind("\n\n", start + CHUNK_TARGET_CHARS // 2, end),
                    section.rfind("\n", start + CHUNK_TARGET_CHARS // 2, end),
                    section.rfind(". ", start + CHUNK_TARGET_CHARS // 2, end),
                )
                if boundary > start:
                    end = boundary + 1
            content = section[start:end].strip()
            if content:
                content_sha256 = _sha256_text(content)
                if content_sha256 not in seen_hashes:
                    seen_hashes.add(content_sha256)
                    chunks.append(KnowledgeChunk(
                        ordinal=ordinal,
                        section_title=section_title,
                        content=content,
                        content_sha256=content_sha256,
                    ))
                    ordinal += 1
            if end >= len(section):
                break
            start = max(start + 1, end - CHUNK_OVERLAP_CHARS)
    return chunks


def _insert_document(
    conn: Any,
    user_id: str,
    document: KnowledgeDocument,
    *,
    source_id_override: str | None = None,
) -> dict[str, Any]:
    source_hash = _sha256_text(document.text)
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id::text, source_type AS "sourceType",
                      source_url AS "sourceUrl", title, status,
                      chunk_count AS "chunkCount"
               FROM knowledge_sources
               WHERE user_id = %s::uuid AND content_sha256 = %s
               LIMIT 1""",
            (user_id, source_hash),
        )
        existing = cur.fetchone()
        if existing:
            return {
                "duplicate": True,
                "source": dict(existing),
                "contentSha256": source_hash,
            }

        source_id = str(uuid.UUID(source_id_override)) if source_id_override else str(uuid.uuid4())
        cur.execute(
            """INSERT INTO knowledge_sources
               (id, user_id, source_type, source_url, title, content_sha256,
                status, content_bytes, metadata)
               VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s,
                       'processing', %s, %s::jsonb)""",
            (
                source_id,
                user_id,
                document.source_type,
                document.source_url,
                document.title,
                source_hash,
                len(document.text.encode("utf-8")),
                json.dumps(document.metadata, ensure_ascii=False),
            ),
        )
    conn.commit()

    chunks = chunk_document(document.text)
    if not chunks:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE knowledge_sources
                   SET status='blocked', blocker='No usable chunks', updated_at=NOW()
                   WHERE id=%s::uuid AND user_id=%s::uuid""",
                (source_id, user_id),
            )
        conn.commit()
        return {
            "duplicate": False,
            "source": {"id": source_id, "title": document.title, "status": "blocked", "chunkCount": 0},
            "contentSha256": source_hash,
            "blocker": "No usable chunks",
        }

    vectors: list[tuple[float, ...] | None] = [None] * len(chunks)
    embedding_provider = None
    embedding_blocker = None
    try:
        for offset in range(0, len(chunks), 32):
            batch_chunks = chunks[offset:offset + 32]
            batch = embed_texts(chunk.content for chunk in batch_chunks)
            embedding_provider = batch.provider
            for index, vector in enumerate(batch.vectors):
                vectors[offset + index] = vector
    except (EmbeddingUnavailable, ValueError, requests.RequestException) as exc:
        embedding_blocker = str(exc)[:500]

    with conn.cursor() as cur:
        for chunk, vector in zip(chunks, vectors):
            vector_value = vector_literal(vector) if vector is not None else None
            cur.execute(
                """INSERT INTO knowledge_blocks
                   (user_id, content_sha256, section_title, content, embedding,
                    embedding_model, metadata)
                   VALUES (%s::uuid, %s, %s, %s, %s::vector, %s, %s::jsonb)
                   ON CONFLICT (user_id, content_sha256) DO UPDATE SET
                       updated_at=NOW(),
                       section_title=COALESCE(knowledge_blocks.section_title, EXCLUDED.section_title),
                       embedding=COALESCE(knowledge_blocks.embedding, EXCLUDED.embedding),
                       embedding_model=COALESCE(knowledge_blocks.embedding_model, EXCLUDED.embedding_model)
                   RETURNING id::text""",
                (
                    user_id,
                    chunk.content_sha256,
                    chunk.section_title,
                    chunk.content,
                    vector_value,
                    EMBEDDING_MODEL if vector is not None else None,
                    json.dumps({"sourceType": document.source_type}, ensure_ascii=False),
                ),
            )
            block_id = str(cur.fetchone()["id"])
            cur.execute(
                """INSERT INTO knowledge_source_blocks
                   (source_id, block_id, ordinal, section_title)
                   VALUES (%s::uuid, %s::uuid, %s, %s)
                   ON CONFLICT (source_id, ordinal) DO NOTHING""",
                (source_id, block_id, chunk.ordinal, chunk.section_title),
            )

        embedded_count = sum(vector is not None for vector in vectors)
        status = "ready" if embedded_count == len(chunks) else "partial"
        cur.execute(
            """UPDATE knowledge_sources
               SET status=%s, chunk_count=%s, blocker=%s,
                   metadata=metadata || %s::jsonb, updated_at=NOW()
               WHERE id=%s::uuid AND user_id=%s::uuid""",
            (
                status,
                len(chunks),
                embedding_blocker,
                json.dumps({
                    "embeddingModel": EMBEDDING_MODEL,
                    "embeddingProvider": embedding_provider,
                    "embeddedChunks": embedded_count,
                }, ensure_ascii=False),
                source_id,
                user_id,
            ),
        )
    conn.commit()
    return {
        "duplicate": False,
        "source": {
            "id": source_id,
            "title": document.title,
            "status": status,
            "chunkCount": len(chunks),
            "embeddedChunks": embedded_count,
            "sourceType": document.source_type,
            "sourceUrl": document.source_url,
        },
        "contentSha256": source_hash,
        "blocker": embedding_blocker,
    }


def _source_rows(conn: Any, user_id: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id::text, source_type AS "sourceType", source_url AS "sourceUrl",
                      title, content_sha256 AS "contentSha256", status,
                      content_bytes AS "contentBytes", chunk_count AS "chunkCount",
                      metadata, blocker,
                      to_char(created_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS "createdAt",
                      to_char(updated_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS "updatedAt"
               FROM knowledge_sources
               WHERE user_id=%s::uuid
               ORDER BY created_at DESC LIMIT 200""",
            (user_id,),
        )
        return [dict(row) for row in cur.fetchall()]


def search_knowledge_blocks(conn: Any, user_id: str, query_text: str, limit: int) -> list[dict[str, Any]]:
    batch = embed_texts([query_text])
    query_vector = vector_literal(batch.vectors[0])
    with conn.cursor() as cur:
        cur.execute(
            """SELECT b.id::text AS "blockId", b.section_title AS "sectionTitle",
                      b.content, b.content_sha256 AS "contentSha256",
                      s.id::text AS "sourceId", s.title AS "sourceTitle",
                      s.source_type AS "sourceType", s.source_url AS "sourceUrl",
                      1 - (b.embedding <=> %s::vector) AS similarity
               FROM knowledge_blocks b
               JOIN knowledge_source_blocks sb ON sb.block_id=b.id
               JOIN knowledge_sources s ON s.id=sb.source_id
               WHERE b.user_id=%s::uuid
                 AND s.user_id=%s::uuid
                 AND b.embedding IS NOT NULL
                 AND s.status IN ('ready','partial')
               ORDER BY b.embedding <=> %s::vector,
                        b.content_sha256 ASC,
                        b.id ASC
               LIMIT %s""",
            (query_vector, user_id, user_id, query_vector, limit),
        )
        return [dict(row) for row in cur.fetchall()]


def _create_r2_upload_ticket(conn: Any, user_id: str, body: dict[str, Any]) -> dict[str, Any]:
    storage = R2Storage.from_env()
    spec = validate_knowledge_upload(
        str(body.get("filename") or ""),
        str(body.get("contentType") or ""),
        body.get("sizeBytes"),
        str(body.get("sha256") or ""),
    )
    object_id = str(uuid.uuid4())
    object_key = knowledge_object_key(user_id, object_id, spec.sha256, spec.filename)
    ticket = storage.presign_put(
        bucket=storage.knowledge_bucket,
        object_key=object_key,
        content_type=spec.content_type,
        size_bytes=spec.size_bytes,
        sha256=spec.sha256,
    )
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO sovereign_objects
               (id, user_id, bucket_name, object_key, sha256, content_type,
                size_bytes, status)
               VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, 'pending')""",
            (
                object_id,
                user_id,
                storage.knowledge_bucket,
                object_key,
                spec.sha256,
                spec.content_type,
                spec.size_bytes,
            ),
        )
    conn.commit()
    return {
        "objectId": object_id,
        "uploadUrl": ticket.url,
        "headers": ticket.headers,
        "expiresInSeconds": ticket.expires_in_seconds,
        "status": "preparing",
    }


def _confirmed_source(conn: Any, user_id: str, object_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT s.id::text, s.source_type AS "sourceType",
                      s.source_url AS "sourceUrl", s.title,
                      s.content_sha256 AS "contentSha256", s.status,
                      s.content_bytes AS "contentBytes",
                      s.chunk_count AS "chunkCount", s.metadata, s.blocker,
                      to_char(s.created_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS "createdAt",
                      to_char(s.updated_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS "updatedAt"
               FROM sovereign_objects o
               JOIN knowledge_sources s ON s.id=o.source_id
               WHERE o.id=%s::uuid AND o.user_id=%s::uuid
                 AND o.status IN ('completed','deleted')
               LIMIT 1""",
            (object_id, user_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _confirm_r2_upload(conn: Any, user_id: str, object_id: str) -> dict[str, Any]:
    normalized_id = str(uuid.UUID(str(object_id or "").strip()))
    existing_source = _confirmed_source(conn, user_id, normalized_id)
    if existing_source:
        return {"duplicate": False, "source": existing_source, "idempotent": True}

    with conn.cursor() as cur:
        cur.execute(
            """SELECT id::text, bucket_name, object_key, sha256,
                      content_type, size_bytes, status
               FROM sovereign_objects
               WHERE id=%s::uuid AND user_id=%s::uuid AND deleted_at IS NULL
               LIMIT 1 FOR UPDATE""",
            (normalized_id, user_id),
        )
        row = cur.fetchone()
        if not row:
            raise LookupError("Upload ticket not found for active user")
        if row["status"] not in {"pending", "uploaded", "verifying", "blocked"}:
            raise ValueError(f"Upload cannot be confirmed from status {row['status']}")
        cur.execute(
            """UPDATE sovereign_objects
               SET status='verifying', blocker=NULL
               WHERE id=%s::uuid AND user_id=%s::uuid""",
            (normalized_id, user_id),
        )
    conn.commit()

    storage = R2Storage.from_env()
    try:
        filename = str(row["object_key"]).rsplit("/", 1)[-1]
        maximum = upload_limit_bytes(filename)
        evidence = storage.verify_object(
            bucket=str(row["bucket_name"]),
            object_key=str(row["object_key"]),
            expected_sha256=str(row["sha256"]),
            expected_content_type=str(row["content_type"]),
            expected_size_bytes=int(row["size_bytes"]),
            max_bytes=maximum,
        )
        payload = storage.get_object_bytes(
            bucket=evidence.bucket,
            object_key=evidence.object_key,
            max_bytes=maximum,
        )
        document = upload_document(filename, payload)
        result = _insert_document(
            conn,
            user_id,
            document,
            source_id_override=normalized_id,
        )
        source_id = str(result["source"]["id"])
        if result["duplicate"]:
            storage.delete_object(bucket=evidence.bucket, object_key=evidence.object_key)
            final_status = "deleted"
        else:
            final_status = "completed"
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE sovereign_objects
                   SET source_id=%s::uuid, status=%s, etag=%s,
                       verified_at=NOW(), blocker=NULL,
                       deleted_at=CASE WHEN %s='deleted' THEN NOW() ELSE NULL END
                   WHERE id=%s::uuid AND user_id=%s::uuid""",
                (
                    source_id,
                    final_status,
                    evidence.etag,
                    final_status,
                    normalized_id,
                    user_id,
                ),
            )
        conn.commit()
        return {**result, "objectId": normalized_id, "objectVerified": True}
    except Exception as exc:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE sovereign_objects
                   SET status='blocked', blocker=%s
                   WHERE id=%s::uuid AND user_id=%s::uuid""",
                (str(exc)[:500], normalized_id, user_id),
            )
        conn.commit()
        raise


def register_knowledge_routes(app: Any, *, require_session: Callable, get_connection: ConnectionFactory) -> None:
    @app.route("/api/knowledge/sources", methods=["GET"])
    @require_session
    def knowledge_sources_list():
        conn = get_connection()
        try:
            return jsonify({"sources": _source_rows(conn, request.session_user_id)})
        finally:
            _close(conn)

    @app.route("/api/knowledge/sources/url", methods=["POST"])
    @require_session
    def knowledge_source_url():
        body = request.get_json(force=True) or {}
        try:
            document = fetch_url_document(str(body.get("url") or ""))
            if body.get("title"):
                document = KnowledgeDocument(
                    source_type=document.source_type,
                    title=_safe_title(str(body["title"]), document.title),
                    text=document.text,
                    source_url=document.source_url,
                    metadata=document.metadata,
                )
            conn = get_connection()
            try:
                result = _insert_document(conn, request.session_user_id, document)
            finally:
                _close(conn)
            return jsonify({"ok": True, **result}), 200 if result["duplicate"] else 201
        except (ValueError, RuntimeError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)[:500]}), 500

    @app.route("/api/knowledge/sources/upload-ticket", methods=["POST"])
    @require_session
    def knowledge_source_upload_ticket():
        body = request.get_json(force=True) or {}
        conn = get_connection()
        try:
            ticket = _create_r2_upload_ticket(conn, request.session_user_id, body)
            return jsonify({"ok": True, **ticket}), 201
        except (ValueError, R2StorageUnavailable) as exc:
            conn.rollback()
            return jsonify({"ok": False, "error": str(exc), "blocker": "r2_upload_not_ready"}), 400
        except R2StorageError as exc:
            conn.rollback()
            return jsonify({"ok": False, "error": str(exc), "blocker": "r2_upload_unavailable"}), 503
        except Exception as exc:
            conn.rollback()
            return jsonify({"ok": False, "error": str(exc)[:500]}), 500
        finally:
            _close(conn)

    @app.route("/api/knowledge/sources/upload-confirm", methods=["POST"])
    @require_session
    def knowledge_source_upload_confirm():
        body = request.get_json(force=True) or {}
        object_id = str(body.get("objectId") or "").strip()
        if not object_id:
            return jsonify({"ok": False, "error": "objectId is required"}), 400
        conn = get_connection()
        try:
            result = _confirm_r2_upload(conn, request.session_user_id, object_id)
            return jsonify({"ok": True, **result}), 200 if result.get("duplicate") or result.get("idempotent") else 201
        except LookupError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 404
        except (ValueError, R2EvidenceMismatch, R2ObjectMissing) as exc:
            return jsonify({"ok": False, "error": str(exc), "blocker": "r2_object_verification_failed"}), 409
        except R2StorageUnavailable as exc:
            return jsonify({"ok": False, "error": str(exc), "blocker": "r2_upload_not_ready"}), 503
        except R2StorageError as exc:
            return jsonify({"ok": False, "error": str(exc), "blocker": "r2_upload_unavailable"}), 503
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)[:500]}), 500
        finally:
            _close(conn)

    @app.route("/api/knowledge/objects/<object_id>/download", methods=["GET"])
    @require_session
    def knowledge_object_download(object_id: str):
        conn = get_connection()
        try:
            normalized_id = str(uuid.UUID(object_id))
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT bucket_name, object_key
                       FROM sovereign_objects
                       WHERE id=%s::uuid AND user_id=%s::uuid
                         AND status='completed' AND deleted_at IS NULL
                       LIMIT 1""",
                    (normalized_id, request.session_user_id),
                )
                row = cur.fetchone()
            if not row:
                return jsonify({"ok": False, "error": "Verified object not found"}), 404
            storage = R2Storage.from_env()
            url, expires = storage.presign_get(
                bucket=str(row["bucket_name"]),
                object_key=str(row["object_key"]),
                download_name=str(row["object_key"]).rsplit("/", 1)[-1],
            )
            return jsonify({"ok": True, "downloadUrl": url, "expiresInSeconds": expires})
        except (ValueError, R2StorageError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        finally:
            _close(conn)

    @app.route("/api/knowledge/sources/upload", methods=["POST"])
    @require_session
    def knowledge_source_upload():
        uploaded = request.files.get("file")
        if uploaded is None:
            return jsonify({"ok": False, "error": "file is required"}), 400
        try:
            filename = uploaded.filename or "upload.txt"
            payload = uploaded.stream.read(upload_limit_bytes(filename) + 1)
            document = upload_document(filename, payload)
            conn = get_connection()
            try:
                result = _insert_document(conn, request.session_user_id, document)
            finally:
                _close(conn)
            return jsonify({"ok": True, **result}), 200 if result["duplicate"] else 201
        except (ValueError, RuntimeError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)[:500]}), 500

    @app.route("/api/knowledge/sources/<source_id>", methods=["DELETE"])
    @require_session
    def knowledge_source_delete(source_id: str):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM knowledge_sources WHERE id=%s::uuid AND user_id=%s::uuid RETURNING id",
                    (source_id, request.session_user_id),
                )
                deleted = cur.fetchone()
                if deleted:
                    cur.execute(
                        """DELETE FROM knowledge_blocks b
                           WHERE b.user_id=%s::uuid
                             AND NOT EXISTS (
                                 SELECT 1 FROM knowledge_source_blocks sb
                                 WHERE sb.block_id=b.id
                             )""",
                        (request.session_user_id,),
                    )
            conn.commit()
            if not deleted:
                return jsonify({"error": "Knowledge source not found"}), 404
            return jsonify({"ok": True, "deleted": source_id})
        except Exception:
            conn.rollback()
            return jsonify({"error": "Knowledge source could not be deleted"}), 500
        finally:
            _close(conn)

    @app.route("/api/knowledge/search", methods=["POST"])
    @require_session
    def knowledge_search():
        body = request.get_json(force=True) or {}
        query_text = str(body.get("query") or "").strip()[:4_000]
        if not query_text:
            return jsonify({"error": "query is required"}), 400
        try:
            limit = max(1, min(int(body.get("limit", 8)), MAX_SEARCH_LIMIT))
        except (TypeError, ValueError):
            limit = 8
        conn = get_connection()
        try:
            results = search_knowledge_blocks(conn, request.session_user_id, query_text, limit)
            return jsonify({
                "ok": True,
                "query": query_text,
                "results": results,
                "count": len(results),
                "embeddingModel": EMBEDDING_MODEL,
                "storage": "postgres-pgvector",
            })
        except EmbeddingUnavailable as exc:
            return jsonify({
                "ok": False,
                "results": [],
                "blocker": "embedding_unavailable",
                "error": str(exc),
                "storage": "postgres-pgvector",
            }), 503
        except Exception as exc:
            return jsonify({"ok": False, "results": [], "error": str(exc)[:500]}), 500
        finally:
            _close(conn)

    @app.route("/api/knowledge/stats", methods=["GET"])
    @require_session
    def knowledge_stats():
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT COUNT(*) AS sources,
                              COALESCE(SUM(chunk_count),0) AS source_chunks,
                              COALESCE(SUM(content_bytes),0) AS source_bytes
                       FROM knowledge_sources WHERE user_id=%s::uuid""",
                    (request.session_user_id,),
                )
                source_stats = dict(cur.fetchone())
                cur.execute(
                    """SELECT COUNT(*) AS unique_blocks,
                              COUNT(embedding) AS embedded_blocks,
                              COALESCE(SUM(octet_length(content)),0) AS text_bytes
                       FROM knowledge_blocks WHERE user_id=%s::uuid""",
                    (request.session_user_id,),
                )
                block_stats = dict(cur.fetchone())
            return jsonify({
                **source_stats,
                **block_stats,
                "embeddingModel": EMBEDDING_MODEL,
                "storage": "postgres-pgvector",
            })
        finally:
            _close(conn)


def register_admin_knowledge_routes(
    app: Any,
    *,
    require_admin: Callable,
    get_connection: ConnectionFactory,
    get_admin_user_id: Callable[[], str],
) -> None:
    """Expose the persistent knowledge runtime to an authenticated admin."""

    def admin_user_id() -> str:
        value = str(get_admin_user_id() or "").strip()
        if not value:
            raise RuntimeError("Authenticated admin has no persistent user id")
        return value

    @app.route("/api/admin/knowledge/sources", methods=["GET"])
    @require_admin
    def admin_knowledge_sources_list():
        conn = get_connection()
        try:
            return jsonify({"sources": _source_rows(conn, admin_user_id())})
        finally:
            _close(conn)

    @app.route("/api/admin/knowledge/sources/url", methods=["POST"])
    @require_admin
    def admin_knowledge_source_url():
        body = request.get_json(force=True) or {}
        try:
            document = fetch_url_document(str(body.get("url") or ""))
            conn = get_connection()
            try:
                result = _insert_document(conn, admin_user_id(), document)
            finally:
                _close(conn)
            return jsonify({"ok": True, **result}), 200 if result["duplicate"] else 201
        except (ValueError, RuntimeError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)[:500]}), 500

    @app.route("/api/admin/knowledge/sources/upload", methods=["POST"])
    @require_admin
    def admin_knowledge_source_upload():
        uploaded = request.files.get("file")
        if uploaded is None:
            return jsonify({"ok": False, "error": "file is required"}), 400
        try:
            filename = uploaded.filename or "upload.txt"
            payload = uploaded.stream.read(upload_limit_bytes(filename) + 1)
            document = upload_document(filename, payload)
            conn = get_connection()
            try:
                result = _insert_document(conn, admin_user_id(), document)
            finally:
                _close(conn)
            return jsonify({"ok": True, **result}), 200 if result["duplicate"] else 201
        except (ValueError, RuntimeError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)[:500]}), 500

    @app.route("/api/admin/knowledge/repair", methods=["POST"])
    @require_admin
    def admin_knowledge_repair():
        body = request.get_json(silent=True) or {}
        try:
            max_batches = max(1, min(int(body.get("maxBatches", 8)), 20))
        except (TypeError, ValueError):
            max_batches = 8
        user_id = admin_user_id()
        conn = get_connection()
        try:
            # Imported lazily to avoid the module cycle: are_inference consumes
            # knowledge_library search helpers, while this admin route reuses its
            # bounded and tested embedding-repair transaction.
            from are_inference import repair_missing_knowledge_embeddings

            selected = 0
            repaired = 0
            remaining = 0
            completed_batches = 0
            provider = None
            for _ in range(max_batches):
                result = repair_missing_knowledge_embeddings(
                    conn,
                    user_id=user_id,
                    limit=25,
                )
                completed_batches += 1
                selected += int(result.get("selected") or 0)
                repaired += int(result.get("repaired") or 0)
                remaining = int(result.get("remaining") or 0)
                provider = result.get("provider") or provider
                if remaining == 0 or int(result.get("selected") or 0) == 0:
                    break
                if int(result.get("repaired") or 0) == 0:
                    break
            return jsonify({
                "ok": True,
                "action": "recompute_missing_knowledge_embeddings",
                "selected": selected,
                "repaired": repaired,
                "remaining": remaining,
                "remainingForUser": remaining,
                "batches": completed_batches,
                "provider": provider,
                "storage": "postgres-pgvector",
            })
        except EmbeddingUnavailable as exc:
            conn.rollback()
            return jsonify({
                "ok": False,
                "error": str(exc),
                "blocker": "embedding_unavailable",
            }), 503
        except Exception as exc:
            conn.rollback()
            return jsonify({"ok": False, "error": str(exc)[:500]}), 500
        finally:
            _close(conn)

    @app.route("/api/admin/knowledge/sources/<source_id>", methods=["DELETE"])
    @require_admin
    def admin_knowledge_source_delete(source_id: str):
        user_id = admin_user_id()
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM knowledge_sources WHERE id=%s::uuid AND user_id=%s::uuid RETURNING id",
                    (source_id, user_id),
                )
                deleted = cur.fetchone()
                if deleted:
                    cur.execute(
                        """DELETE FROM knowledge_blocks b
                           WHERE b.user_id=%s::uuid
                             AND NOT EXISTS (
                                 SELECT 1 FROM knowledge_source_blocks sb WHERE sb.block_id=b.id
                             )""",
                        (user_id,),
                    )
            conn.commit()
            if not deleted:
                return jsonify({"error": "Knowledge source not found"}), 404
            return jsonify({"ok": True, "deleted": source_id})
        except Exception:
            conn.rollback()
            return jsonify({"error": "Knowledge source could not be deleted"}), 500
        finally:
            _close(conn)

    @app.route("/api/admin/knowledge/search", methods=["POST"])
    @require_admin
    def admin_knowledge_search():
        body = request.get_json(force=True) or {}
        query_text = str(body.get("query") or "").strip()[:4_000]
        if not query_text:
            return jsonify({"error": "query is required"}), 400
        try:
            limit = max(1, min(int(body.get("limit", 8)), MAX_SEARCH_LIMIT))
        except (TypeError, ValueError):
            limit = 8
        conn = get_connection()
        try:
            results = search_knowledge_blocks(conn, admin_user_id(), query_text, limit)
            return jsonify({"ok": True, "results": results, "count": len(results), "storage": "postgres-pgvector"})
        except EmbeddingUnavailable as exc:
            return jsonify({"ok": False, "results": [], "error": str(exc), "blocker": "embedding_unavailable"}), 503
        except Exception as exc:
            return jsonify({"ok": False, "results": [], "error": str(exc)[:500]}), 500
        finally:
            _close(conn)
