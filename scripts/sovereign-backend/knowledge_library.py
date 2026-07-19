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
AuditRecorder = Callable[[str, str | None, dict[str, Any]], None]

MAX_UPLOAD_BYTES = 33 * 1024 * 1024
MAX_NON_PDF_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_SOURCE_TEXT_CHARS = 12_000_000
MAX_GITHUB_FILES = 80
MAX_GITHUB_FILE_BYTES = 512 * 1024
MAX_GITHUB_TOTAL_BYTES = 6 * 1024 * 1024
MAX_PDF_PAGES = 500
CHUNK_TARGET_CHARS = 1_800
CHUNK_OVERLAP_CHARS = 220
MAX_SEARCH_LIMIT = 20
PROCESSING_STALE_SECONDS = 15 * 60

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


class GitHubKnowledgeAccessError(ValueError):
    """Bounded GitHub import failure with an operator-safe blocker family."""

    def __init__(
        self,
        message: str,
        *,
        blocker: str,
        github_status: int | None = None,
        response_status: int = 502,
    ) -> None:
        super().__init__(message)
        self.blocker = blocker
        self.github_status = github_status
        self.response_status = response_status


def _github_get(url: str, *, headers: dict[str, str]) -> Any:
    """Run one bounded GitHub HTTPS request and classify transport failures."""
    try:
        return requests.get(url, headers=headers, timeout=25)
    except requests.Timeout as exc:
        raise GitHubKnowledgeAccessError(
            "GitHub hat über HTTPS/443 nicht rechtzeitig geantwortet. Erneut versuchen; bei Wiederholung DNS, Firewall und Proxy der Backend-Runtime prüfen.",
            blocker="github_api_timeout",
            response_status=504,
        ) from exc
    except requests.exceptions.SSLError as exc:
        raise GitHubKnowledgeAccessError(
            "Die TLS-Verbindung zu GitHub über HTTPS/443 konnte nicht verifiziert werden. Zertifikat-, CA- und Proxy-Konfiguration der Backend-Runtime prüfen.",
            blocker="github_tls_failure",
            response_status=502,
        ) from exc
    except requests.ConnectionError as exc:
        raise GitHubKnowledgeAccessError(
            "GitHub ist aus der Backend-Runtime über HTTPS/443 nicht erreichbar. DNS, Firewall und ausgehenden Proxy prüfen.",
            blocker="github_connection_unavailable",
            response_status=502,
        ) from exc
    except requests.RequestException as exc:
        raise GitHubKnowledgeAccessError(
            "Der GitHub-Aufruf über HTTPS/443 ist auf Transportebene fehlgeschlagen. Den Backend-Netzwerkpfad prüfen.",
            blocker="github_transport_error",
            response_status=502,
        ) from exc


def _record_github_import_failure(
    audit_event: AuditRecorder | None,
    source_url: str,
    error: GitHubKnowledgeAccessError,
) -> tuple[str, bool]:
    """Persist bounded failure evidence and return its non-secret correlation state."""
    correlation_id = str(uuid.uuid4())
    if not callable(audit_event):
        return correlation_id, False
    source_fingerprint = _sha256_text(str(source_url or "").strip())[:24]
    try:
        audit_event(
            "knowledge:github_import_failed",
            f"github:{source_fingerprint}",
            {
                "result": "blocked",
                "blocker": error.blocker,
                "githubHttpStatus": error.github_status,
                "transportFailure": error.github_status is None,
                "correlationId": correlation_id,
            },
        )
        return correlation_id, True
    except Exception:
        # Audit availability must not hide the classified import blocker.
        return correlation_id, False


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


def _github_public_headers() -> dict[str, str]:
    return {
        key: value
        for key, value in _github_headers().items()
        if key.lower() != "authorization"
    }


def _github_access_error(
    response: Any,
    *,
    authenticated: bool,
    public_retry_status: int | None = None,
) -> GitHubKnowledgeAccessError:
    status = int(getattr(response, "status_code", 0) or 0)
    remaining = str(getattr(response, "headers", {}).get("x-ratelimit-remaining") or "").strip()
    if status == 403 and remaining == "0":
        return GitHubKnowledgeAccessError(
            "GitHub API-Limit ist erschöpft. Nach Reset erneut versuchen oder einen gültigen Repository-Zugang hinterlegen.",
            blocker="github_rate_limit_exhausted",
            github_status=status,
            response_status=429,
        )
    if authenticated and status in {401, 403}:
        if public_retry_status == 404:
            message = "Der hinterlegte GitHub-Zugang wurde abgelehnt und das Repository ist nicht öffentlich lesbar. Token-/App-Berechtigung für das Repository erneuern."
            blocker = "github_private_repo_access_required"
            response_status = 409
        else:
            message = "Der hinterlegte GitHub-Zugang wurde von GitHub abgelehnt. Token, GitHub-App-Berechtigung oder SSO-Freigabe erneuern."
            blocker = "github_credentials_rejected"
            response_status = 409
        return GitHubKnowledgeAccessError(
            message,
            blocker=blocker,
            github_status=status,
            response_status=response_status,
        )
    if authenticated and status == 404:
        return GitHubKnowledgeAccessError(
            "Repository oder Pfad wurde nicht gefunden, oder der hinterlegte GitHub-Zugang besitzt keine Leseberechtigung.",
            blocker="github_repository_not_accessible",
            github_status=status,
            response_status=404,
        )
    if status in {401, 403, 404}:
        return GitHubKnowledgeAccessError(
            "Repository ist nicht öffentlich lesbar. Für private Repositories ist ein bestätigter serverseitiger GitHub-Zugang erforderlich.",
            blocker="github_private_repo_access_required",
            github_status=status,
            response_status=409 if status != 404 else 404,
        )
    return GitHubKnowledgeAccessError(
        f"GitHub-Import ist mit HTTP {status or 'unknown'} fehlgeschlagen.",
        blocker="github_api_unavailable",
        github_status=status or None,
        response_status=502,
    )


def _github_json(
    path: str,
    *,
    auth_state: dict[str, bool] | None = None,
) -> Any:
    url = f"https://api.github.com{path}"
    private_headers = _github_headers()
    has_private_access = "Authorization" in private_headers
    authenticated = bool(auth_state.get("authenticated")) if auth_state is not None else False
    response = _github_get(
        url,
        headers=private_headers if authenticated else _github_public_headers(),
    )
    if (
        not response.ok
        and not authenticated
        and has_private_access
        and response.status_code in {403, 404}
    ):
        public_status = response.status_code
        private_response = _github_get(
            url,
            headers=private_headers,
        )
        if private_response.ok:
            response = private_response
            authenticated = True
            if auth_state is not None:
                auth_state["authenticated"] = True
        else:
            raise _github_access_error(
                private_response,
                authenticated=True,
                public_retry_status=public_status,
            )
    if not response.ok:
        raise _github_access_error(response, authenticated=authenticated)
    try:
        return response.json()
    except ValueError as exc:
        raise GitHubKnowledgeAccessError(
            "GitHub lieferte keine gültige API-Antwort.",
            blocker="github_invalid_response",
            github_status=response.status_code,
            response_status=502,
        ) from exc


def _decode_github_content(payload: dict[str, Any]) -> str:
    encoded = str(payload.get("content") or "").replace("\n", "")
    if not encoded:
        download_url = str(payload.get("download_url") or "")
        if not download_url:
            return ""
        parsed_download = urlparse(download_url)
        if parsed_download.scheme != "https" or (parsed_download.hostname or "").lower() not in {
            "raw.githubusercontent.com",
            "github.com",
            "www.github.com",
        }:
            raise GitHubKnowledgeAccessError(
                "GitHub lieferte eine nicht erlaubte Download-Adresse.",
                blocker="github_raw_url_rejected",
                response_status=502,
            )
        response = _github_get(
            download_url,
            headers={"User-Agent": "sovereign-knowledge-library/1.0"},
        )
        if not response.ok:
            raise _github_access_error(response, authenticated=False)
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
    auth_state = {"authenticated": False}
    repo_info = _github_json(
        f"/repos/{quote(owner)}/{quote(repo)}",
        auth_state=auth_state,
    )
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
            f"/repos/{quote(owner)}/{quote(repo)}/contents/{quote(specific_file, safe='/')}?ref={quote(branch)}",
            auth_state=auth_state,
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
        f"/repos/{quote(owner)}/{quote(repo)}/git/trees/{quote(branch)}?recursive=1",
        auth_state=auth_state,
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
            f"/repos/{quote(owner)}/{quote(repo)}/contents/{quote(path, safe='/')}?ref={quote(branch)}",
            auth_state=auth_state,
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


def _upload_limit_bytes(filename: str) -> int:
    return MAX_UPLOAD_BYTES if str(filename or "").lower().endswith(".pdf") else MAX_NON_PDF_UPLOAD_BYTES


def upload_document(filename: str, payload: bytes) -> KnowledgeDocument:
    if not payload:
        raise ValueError("Uploaded file is empty")
    upload_limit = _upload_limit_bytes(filename)
    if len(payload) > upload_limit:
        raise ValueError(f"Uploaded file exceeds {upload_limit // (1024 * 1024)} MB")
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


def _insert_document_unchecked(
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


def _insert_document(
    conn: Any,
    user_id: str,
    document: KnowledgeDocument,
    *,
    source_id_override: str | None = None,
) -> dict[str, Any]:
    """Persist one import and fail closed if work stops after the processing commit."""
    source_hash = _sha256_text(document.text)
    try:
        return _insert_document_unchecked(
            conn,
            user_id,
            document,
            source_id_override=source_id_override,
        )
    except Exception as exc:
        conn.rollback()
        failure_type = re.sub(r"[^A-Za-z0-9_]", "", type(exc).__name__)[:80] or "Error"
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE knowledge_sources
                   SET status='blocked', blocker=%s, updated_at=NOW()
                   WHERE user_id=%s::uuid AND content_sha256=%s
                     AND status='processing'""",
                (f"knowledge_import_failed:{failure_type}", user_id, source_hash),
            )
        conn.commit()
        raise


def _reconcile_stale_processing_sources(conn: Any, user_id: str) -> int:
    """Block abandoned zero-block imports without changing recent active work."""
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE knowledge_sources AS source
               SET status='blocked', blocker='knowledge_import_interrupted', updated_at=NOW()
               WHERE source.user_id=%s::uuid
                 AND source.status='processing'
                 AND source.updated_at < NOW() - (%s * INTERVAL '1 second')
                 AND NOT EXISTS (
                     SELECT 1 FROM knowledge_source_blocks AS link
                     WHERE link.source_id=source.id
                 )
               RETURNING source.id""",
            (user_id, PROCESSING_STALE_SECONDS),
        )
        reconciled = len(cur.fetchall())
    conn.commit()
    return reconciled


def _knowledge_runtime_summary(conn: Any, user_id: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT COUNT(*)::integer AS sources,
                      COUNT(*) FILTER (WHERE status='ready')::integer AS ready_sources,
                      COUNT(*) FILTER (WHERE status='partial')::integer AS partial_sources,
                      COUNT(*) FILTER (WHERE status='processing')::integer AS processing_sources,
                      COUNT(*) FILTER (WHERE status='blocked')::integer AS blocked_sources,
                      COALESCE(SUM(chunk_count),0)::integer AS source_chunks
               FROM knowledge_sources WHERE user_id=%s::uuid""",
            (user_id,),
        )
        source_state = dict(cur.fetchone())
        cur.execute(
            """SELECT COUNT(*)::integer AS unique_blocks,
                      COUNT(embedding)::integer AS embedded_blocks,
                      COUNT(*) FILTER (WHERE embedding IS NULL)::integer AS missing_embeddings
               FROM knowledge_blocks WHERE user_id=%s::uuid""",
            (user_id,),
        )
        block_state = dict(cur.fetchone())
        cur.execute(
            """SELECT COUNT(*)::integer AS orphan_links
               FROM knowledge_source_blocks AS link
               JOIN knowledge_sources AS source ON source.id=link.source_id
               LEFT JOIN knowledge_blocks AS block ON block.id=link.block_id
               WHERE source.user_id=%s::uuid AND block.id IS NULL""",
            (user_id,),
        )
        orphan_state = dict(cur.fetchone())
    summary = {**source_state, **block_state, **orphan_state}
    summary["importsUsable"] = bool(
        int(summary.get("ready_sources") or 0) + int(summary.get("partial_sources") or 0) > 0
        and int(summary.get("missing_embeddings") or 0) == 0
        and int(summary.get("orphan_links") or 0) == 0
    )
    summary["embeddingModel"] = EMBEDDING_MODEL
    summary["storage"] = "postgres-pgvector"
    return summary


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
        upload_limit = _upload_limit_bytes(filename)
        evidence = storage.verify_object(
            bucket=str(row["bucket_name"]),
            object_key=str(row["object_key"]),
            expected_sha256=str(row["sha256"]),
            expected_content_type=str(row["content_type"]),
            expected_size_bytes=int(row["size_bytes"]),
            max_bytes=upload_limit,
        )
        payload = storage.get_object_bytes(
            bucket=evidence.bucket,
            object_key=evidence.object_key,
            max_bytes=upload_limit,
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


def register_knowledge_routes(
    app: Any,
    *,
    require_session: Callable,
    get_connection: ConnectionFactory,
    audit_event: AuditRecorder | None = None,
) -> None:
    @app.route("/api/knowledge/sources", methods=["GET"])
    @require_session
    def knowledge_sources_list():
        conn = get_connection()
        try:
            reconciled = _reconcile_stale_processing_sources(conn, request.session_user_id)
            return jsonify({
                "sources": _source_rows(conn, request.session_user_id),
                "runtime": _knowledge_runtime_summary(conn, request.session_user_id),
                "reconciledStaleImports": reconciled,
            })
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
        except GitHubKnowledgeAccessError as exc:
            correlation_id, audit_recorded = _record_github_import_failure(
                audit_event,
                str(body.get("url") or ""),
                exc,
            )
            return jsonify({
                "ok": False,
                "error": str(exc),
                "blocker": exc.blocker,
                "githubHttpStatus": exc.github_status,
                "correlationId": correlation_id,
                "auditRecorded": audit_recorded,
            }), exc.response_status
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
            payload = uploaded.stream.read(_upload_limit_bytes(filename) + 1)
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
    audit_event: AuditRecorder | None = None,
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
            user_id = admin_user_id()
            reconciled = _reconcile_stale_processing_sources(conn, user_id)
            return jsonify({
                "sources": _source_rows(conn, user_id),
                "runtime": _knowledge_runtime_summary(conn, user_id),
                "reconciledStaleImports": reconciled,
            })
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
        except GitHubKnowledgeAccessError as exc:
            correlation_id, audit_recorded = _record_github_import_failure(
                audit_event,
                str(body.get("url") or ""),
                exc,
            )
            return jsonify({
                "ok": False,
                "error": str(exc),
                "blocker": exc.blocker,
                "githubHttpStatus": exc.github_status,
                "correlationId": correlation_id,
                "auditRecorded": audit_recorded,
            }), exc.response_status
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
            payload = uploaded.stream.read(_upload_limit_bytes(filename) + 1)
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
