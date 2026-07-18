"""Fail-closed Cloudflare R2 storage adapter for Sovereign Studio.

The frontend receives only short-lived presigned URLs. Long-lived R2 credentials
remain server-side. PostgreSQL owns object metadata and ownership; R2 owns bytes.
No successful state is returned without object evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import re
from typing import Any, Mapping
from urllib.parse import urlparse
import uuid


MAX_KNOWLEDGE_BYTES = 33 * 1024 * 1024
MAX_PDF_KNOWLEDGE_BYTES = MAX_KNOWLEDGE_BYTES
MAX_NON_PDF_KNOWLEDGE_BYTES = 12 * 1024 * 1024
MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
DEFAULT_PRESIGN_SECONDS = 900
MAX_PRESIGN_SECONDS = 3600

_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_SAFE_JOB_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")

_KNOWLEDGE_TYPES: dict[str, tuple[str, ...]] = {
    ".pdf": ("application/pdf",),
    ".txt": ("text/plain",),
    ".md": ("text/markdown", "text/plain"),
    ".markdown": ("text/markdown", "text/plain"),
    ".mdx": ("text/markdown", "text/mdx", "text/plain"),
    ".rst": ("text/plain", "text/x-rst"),
    ".json": ("application/json", "text/json", "text/plain"),
    ".yaml": ("application/yaml", "text/yaml", "text/plain"),
    ".yml": ("application/yaml", "text/yaml", "text/plain"),
    ".toml": ("application/toml", "text/plain"),
    ".py": ("text/x-python", "text/plain"),
    ".ts": ("text/typescript", "application/typescript", "video/mp2t", "text/plain"),
    ".tsx": ("text/typescript", "application/typescript", "text/plain"),
    ".js": ("text/javascript", "application/javascript", "text/plain"),
    ".jsx": ("text/javascript", "application/javascript", "text/plain"),
    ".java": ("text/x-java-source", "text/plain"),
    ".kt": ("text/x-kotlin", "text/plain"),
    ".kts": ("text/x-kotlin", "text/plain"),
    ".c": ("text/x-c", "text/plain"),
    ".cc": ("text/x-c++", "text/plain"),
    ".cpp": ("text/x-c++", "text/plain"),
    ".cxx": ("text/x-c++", "text/plain"),
    ".h": ("text/x-c", "text/plain"),
    ".hh": ("text/x-c++", "text/plain"),
    ".hpp": ("text/x-c++", "text/plain"),
    ".hxx": ("text/x-c++", "text/plain"),
    ".rs": ("text/x-rust", "text/plain"),
    ".go": ("text/x-go", "text/plain"),
    ".cs": ("text/x-csharp", "text/plain"),
    ".php": ("application/x-httpd-php", "text/plain"),
    ".rb": ("text/x-ruby", "text/plain"),
    ".sh": ("application/x-sh", "text/x-shellscript", "text/plain"),
    ".sql": ("application/sql", "text/x-sql", "text/plain"),
    ".html": ("text/html",),
    ".css": ("text/css",),
}

_ARTIFACT_TYPES: dict[str, tuple[str, ...]] = {
    ".zip": ("application/zip", "application/x-zip-compressed"),
    ".json": ("application/json", "text/json"),
    ".txt": ("text/plain",),
    ".log": ("text/plain",),
    ".xml": ("application/xml", "text/xml"),
    ".html": ("text/html",),
    ".png": ("image/png",),
    ".jpg": ("image/jpeg",),
    ".jpeg": ("image/jpeg",),
    ".webp": ("image/webp",),
    ".webm": ("video/webm",),
    ".patch": ("text/x-diff", "text/plain"),
    ".diff": ("text/x-diff", "text/plain"),
    ".apk": ("application/vnd.android.package-archive", "application/octet-stream"),
    ".aab": ("application/octet-stream",),
    ".enc": ("application/octet-stream",),
}


class R2StorageError(RuntimeError):
    """Base error for storage operations without credential disclosure."""


class R2StorageUnavailable(R2StorageError):
    """Raised when the real R2 runtime is not fully configured."""


class R2ObjectMissing(R2StorageError):
    """Raised when R2 does not contain the expected object."""


class R2EvidenceMismatch(R2StorageError):
    """Raised when HEAD/body evidence differs from PostgreSQL expectations."""


@dataclass(frozen=True)
class UploadSpec:
    filename: str
    extension: str
    content_type: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class ObjectEvidence:
    bucket: str
    object_key: str
    sha256: str
    content_type: str
    size_bytes: int
    etag: str | None


@dataclass(frozen=True)
class PresignedUpload:
    url: str
    headers: dict[str, str]
    expires_in_seconds: int


def _canonical_uuid(value: str, label: str) -> str:
    try:
        return str(uuid.UUID(str(value or "").strip()))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{label} must be a UUID") from exc


def _safe_job_id(value: str) -> str:
    candidate = str(value or "").strip()
    if not _SAFE_JOB_RE.fullmatch(candidate):
        raise ValueError("job_id contains unsafe characters")
    return candidate


def _safe_filename(value: str) -> str:
    raw = str(value or "").strip().replace("\\", "/").rsplit("/", 1)[-1]
    if not raw or raw in {".", ".."}:
        raise ValueError("filename is required")
    safe = _SAFE_NAME_RE.sub("-", raw).strip(".-")
    if not safe:
        raise ValueError("filename contains no safe characters")
    if safe.startswith(".") or ".." in safe:
        raise ValueError("filename contains path traversal")
    return safe[:180]


def _extension(filename: str) -> str:
    lower = filename.lower()
    return "." + lower.rsplit(".", 1)[-1] if "." in lower else ""


def _sha256(value: str) -> str:
    candidate = str(value or "").strip().lower()
    if not _SHA256_RE.fullmatch(candidate):
        raise ValueError("sha256 must contain exactly 64 lowercase hex characters")
    return candidate


def _size(value: Any, maximum: int) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("sizeBytes must be an integer") from exc
    if size <= 0:
        raise ValueError("sizeBytes must be greater than zero")
    if size > maximum:
        raise ValueError(f"sizeBytes exceeds the {maximum}-byte limit")
    return size


def _upload_spec(
    filename: str,
    content_type: str | None,
    size_bytes: Any,
    sha256: str,
    *,
    allowed: Mapping[str, tuple[str, ...]],
    maximum: int,
) -> UploadSpec:
    safe_name = _safe_filename(filename)
    extension = _extension(safe_name)
    permitted = allowed.get(extension)
    if not permitted:
        raise ValueError(f"unsupported file extension: {extension or 'none'}")
    claimed = str(content_type or "").split(";", 1)[0].strip().lower()
    if claimed and claimed not in permitted:
        raise ValueError(f"content type {claimed} is not allowed for {extension}")
    return UploadSpec(
        filename=safe_name,
        extension=extension,
        content_type=permitted[0],
        size_bytes=_size(size_bytes, maximum),
        sha256=_sha256(sha256),
    )


def validate_knowledge_upload(
    filename: str,
    content_type: str | None,
    size_bytes: Any,
    sha256: str,
) -> UploadSpec:
    maximum = (
        MAX_KNOWLEDGE_BYTES
        if str(filename or "").lower().endswith(".pdf")
        else MAX_NON_PDF_KNOWLEDGE_BYTES
    )
    return _upload_spec(
        filename,
        content_type,
        size_bytes,
        sha256,
        allowed=_KNOWLEDGE_TYPES,
        maximum=maximum,
    )


def validate_artifact_upload(
    filename: str,
    content_type: str | None,
    size_bytes: Any,
    sha256: str,
) -> UploadSpec:
    return _upload_spec(
        filename,
        content_type,
        size_bytes,
        sha256,
        allowed=_ARTIFACT_TYPES,
        maximum=MAX_ARTIFACT_BYTES,
    )


def knowledge_object_key(user_id: str, source_id: str, sha256: str, filename: str) -> str:
    user = _canonical_uuid(user_id, "user_id")
    source = _canonical_uuid(source_id, "source_id")
    digest = _sha256(sha256)
    name = _safe_filename(filename)
    return _assert_safe_key(f"users/{user}/knowledge/{source}/{digest}/{name}")


def artifact_object_key(user_id: str, job_id: str, sha256: str, filename: str) -> str:
    user = _canonical_uuid(user_id, "user_id")
    job = _safe_job_id(job_id)
    digest = _sha256(sha256)
    name = _safe_filename(filename)
    return _assert_safe_key(f"users/{user}/jobs/{job}/artifacts/{digest}/{name}")


def _assert_safe_key(value: str) -> str:
    if not value or value.startswith("/") or "\\" in value or "//" in value:
        raise ValueError("object key is unsafe")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("object key contains path traversal")
    return value


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class R2Storage:
    def __init__(
        self,
        *,
        endpoint: str,
        access_key_id: str,
        secret_access_key: str,
        knowledge_bucket: str,
        artifacts_bucket: str,
        region: str = "auto",
        client: Any | None = None,
    ):
        self.endpoint = self._validate_endpoint(endpoint)
        self.access_key_id = str(access_key_id or "").strip()
        self.secret_access_key = str(secret_access_key or "").strip()
        self.knowledge_bucket = self._validate_bucket(knowledge_bucket, "R2_KNOWLEDGE_BUCKET")
        self.artifacts_bucket = self._validate_bucket(artifacts_bucket, "R2_ARTIFACTS_BUCKET")
        self.region = str(region or "auto").strip() or "auto"
        if not self.access_key_id or not self.secret_access_key:
            raise R2StorageUnavailable("R2 credentials are not configured")
        self._client = client

    @classmethod
    def from_env(cls) -> "R2Storage":
        required = {
            "R2_ENDPOINT": os.getenv("R2_ENDPOINT", "").strip(),
            "R2_ACCESS_KEY_ID": os.getenv("R2_ACCESS_KEY_ID", "").strip(),
            "R2_SECRET_ACCESS_KEY": os.getenv("R2_SECRET_ACCESS_KEY", "").strip(),
            "R2_KNOWLEDGE_BUCKET": os.getenv("R2_KNOWLEDGE_BUCKET", "").strip(),
            "R2_ARTIFACTS_BUCKET": os.getenv("R2_ARTIFACTS_BUCKET", "").strip(),
        }
        missing = sorted(name for name, value in required.items() if not value)
        if missing:
            raise R2StorageUnavailable("R2 runtime is not configured: " + ", ".join(missing))
        return cls(
            endpoint=required["R2_ENDPOINT"],
            access_key_id=required["R2_ACCESS_KEY_ID"],
            secret_access_key=required["R2_SECRET_ACCESS_KEY"],
            knowledge_bucket=required["R2_KNOWLEDGE_BUCKET"],
            artifacts_bucket=required["R2_ARTIFACTS_BUCKET"],
            region=os.getenv("R2_REGION", "auto"),
        )

    @staticmethod
    def _validate_endpoint(value: str) -> str:
        candidate = str(value or "").strip().rstrip("/")
        parsed = urlparse(candidate)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or not parsed.hostname.endswith(".r2.cloudflarestorage.com")
        ):
            raise R2StorageUnavailable("R2_ENDPOINT must be a canonical Cloudflare R2 HTTPS endpoint")
        return candidate

    @staticmethod
    def _validate_bucket(value: str, label: str) -> str:
        candidate = str(value or "").strip()
        if not _BUCKET_RE.fullmatch(candidate):
            raise R2StorageUnavailable(f"{label} is not a valid private bucket name")
        return candidate

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import boto3
                from botocore.config import Config
            except ImportError as exc:
                raise R2StorageUnavailable("boto3 is required for the R2 runtime") from exc
            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                region_name=self.region,
                config=Config(
                    signature_version="s3v4",
                    retries={"max_attempts": 3, "mode": "standard"},
                    connect_timeout=8,
                    read_timeout=30,
                ),
            )
        return self._client

    def presign_put(
        self,
        *,
        bucket: str,
        object_key: str,
        content_type: str,
        size_bytes: int,
        sha256: str,
        expires_in_seconds: int = DEFAULT_PRESIGN_SECONDS,
    ) -> PresignedUpload:
        key = _assert_safe_key(object_key)
        digest = _sha256(sha256)
        seconds = max(60, min(int(expires_in_seconds), MAX_PRESIGN_SECONDS))
        metadata = {"sha256": digest, "size-bytes": str(int(size_bytes))}
        try:
            url = self.client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self._validate_bucket(bucket, "bucket"),
                    "Key": key,
                    "ContentType": content_type,
                    "Metadata": metadata,
                },
                ExpiresIn=seconds,
                HttpMethod="PUT",
            )
        except Exception as exc:
            raise R2StorageError("R2 upload URL could not be created") from exc
        return PresignedUpload(
            url=url,
            headers={
                "Content-Type": content_type,
                "x-amz-meta-sha256": digest,
                "x-amz-meta-size-bytes": str(int(size_bytes)),
            },
            expires_in_seconds=seconds,
        )

    def presign_get(
        self,
        *,
        bucket: str,
        object_key: str,
        download_name: str,
        expires_in_seconds: int = DEFAULT_PRESIGN_SECONDS,
    ) -> tuple[str, int]:
        key = _assert_safe_key(object_key)
        name = _safe_filename(download_name)
        seconds = max(60, min(int(expires_in_seconds), MAX_PRESIGN_SECONDS))
        try:
            url = self.client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self._validate_bucket(bucket, "bucket"),
                    "Key": key,
                    "ResponseContentDisposition": f'attachment; filename="{name}"',
                },
                ExpiresIn=seconds,
                HttpMethod="GET",
            )
        except Exception as exc:
            raise R2StorageError("R2 download URL could not be created") from exc
        return url, seconds

    def head_object(self, *, bucket: str, object_key: str) -> dict[str, Any]:
        try:
            return dict(self.client.head_object(
                Bucket=self._validate_bucket(bucket, "bucket"),
                Key=_assert_safe_key(object_key),
            ))
        except Exception as exc:
            raise R2ObjectMissing("R2 object evidence is missing") from exc

    def get_object_bytes(self, *, bucket: str, object_key: str, max_bytes: int) -> bytes:
        try:
            response = self.client.get_object(
                Bucket=self._validate_bucket(bucket, "bucket"),
                Key=_assert_safe_key(object_key),
            )
            body = response.get("Body")
            if body is None or not callable(getattr(body, "read", None)):
                raise R2ObjectMissing("R2 object body is missing")
            payload = body.read(max_bytes + 1)
        except R2StorageError:
            raise
        except Exception as exc:
            raise R2ObjectMissing("R2 object body could not be read") from exc
        if len(payload) > max_bytes:
            raise R2EvidenceMismatch("R2 object exceeds the verified size limit")
        return bytes(payload)

    def verify_object(
        self,
        *,
        bucket: str,
        object_key: str,
        expected_sha256: str,
        expected_content_type: str,
        expected_size_bytes: int,
        max_bytes: int,
    ) -> ObjectEvidence:
        digest = _sha256(expected_sha256)
        head = self.head_object(bucket=bucket, object_key=object_key)
        actual_size = int(head.get("ContentLength") or -1)
        actual_type = str(head.get("ContentType") or "").split(";", 1)[0].strip().lower()
        metadata = {str(k).lower(): str(v) for k, v in dict(head.get("Metadata") or {}).items()}
        if actual_size != int(expected_size_bytes):
            raise R2EvidenceMismatch("R2 object size does not match PostgreSQL evidence")
        if actual_type != expected_content_type.lower():
            raise R2EvidenceMismatch("R2 object content type does not match PostgreSQL evidence")
        if metadata.get("sha256", "").lower() != digest:
            raise R2EvidenceMismatch("R2 object SHA metadata does not match PostgreSQL evidence")
        if metadata.get("size-bytes") != str(int(expected_size_bytes)):
            raise R2EvidenceMismatch("R2 object size metadata does not match PostgreSQL evidence")
        payload = self.get_object_bytes(bucket=bucket, object_key=object_key, max_bytes=max_bytes)
        actual_digest = sha256_bytes(payload)
        if actual_digest != digest:
            raise R2EvidenceMismatch("R2 object bytes do not match the expected SHA-256")
        return ObjectEvidence(
            bucket=bucket,
            object_key=object_key,
            sha256=actual_digest,
            content_type=actual_type,
            size_bytes=actual_size,
            etag=str(head.get("ETag") or "").strip('"') or None,
        )

    def put_object(
        self,
        *,
        bucket: str,
        object_key: str,
        payload: bytes,
        content_type: str,
    ) -> ObjectEvidence:
        digest = sha256_bytes(payload)
        key = _assert_safe_key(object_key)
        target_bucket = self._validate_bucket(bucket, "bucket")
        try:
            self.client.put_object(
                Bucket=target_bucket,
                Key=key,
                Body=payload,
                ContentType=content_type,
                Metadata={"sha256": digest, "size-bytes": str(len(payload))},
            )
        except Exception as exc:
            raise R2StorageError("R2 object upload failed") from exc
        head = self.head_object(bucket=target_bucket, object_key=key)
        if int(head.get("ContentLength") or -1) != len(payload):
            raise R2EvidenceMismatch("R2 upload HEAD size does not match local bytes")
        metadata = {str(k).lower(): str(v) for k, v in dict(head.get("Metadata") or {}).items()}
        if metadata.get("sha256", "").lower() != digest:
            raise R2EvidenceMismatch("R2 upload HEAD SHA does not match local bytes")
        return ObjectEvidence(
            bucket=target_bucket,
            object_key=key,
            sha256=digest,
            content_type=str(head.get("ContentType") or content_type).split(";", 1)[0].strip().lower(),
            size_bytes=len(payload),
            etag=str(head.get("ETag") or "").strip('"') or None,
        )

    def delete_object(self, *, bucket: str, object_key: str) -> None:
        try:
            self.client.delete_object(
                Bucket=self._validate_bucket(bucket, "bucket"),
                Key=_assert_safe_key(object_key),
            )
        except Exception as exc:
            raise R2StorageError("R2 object deletion failed") from exc

    def configured_summary(self) -> dict[str, Any]:
        return {
            "configured": True,
            "endpointHost": urlparse(self.endpoint).hostname,
            "knowledgeBucket": self.knowledge_bucket,
            "artifactsBucket": self.artifacts_bucket,
            "region": self.region,
        }
