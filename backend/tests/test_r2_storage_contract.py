from __future__ import annotations

import io
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
DEPLOY = ROOT / "scripts" / "sovereign-backend"
sys.path.insert(0, str(BACKEND))

import r2_storage


class FakeR2Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], dict[str, object]] = {}
        self.presign_calls: list[dict[str, object]] = []

    def generate_presigned_url(self, operation, *, Params, ExpiresIn, HttpMethod):
        self.presign_calls.append({
            "operation": operation,
            "params": Params,
            "expires": ExpiresIn,
            "method": HttpMethod,
        })
        return f"https://signed.invalid/{operation}/{Params['Bucket']}/{Params['Key']}"

    def put_object(self, *, Bucket, Key, Body, ContentType, Metadata):
        payload = bytes(Body)
        self.objects[(Bucket, Key)] = {
            "payload": payload,
            "content_type": ContentType,
            "metadata": dict(Metadata),
            "etag": "real-etag",
        }
        return {"ETag": '"real-etag"'}

    def head_object(self, *, Bucket, Key):
        item = self.objects[(Bucket, Key)]
        payload = item["payload"]
        return {
            "ContentLength": len(payload),
            "ContentType": item["content_type"],
            "Metadata": item["metadata"],
            "ETag": f'"{item["etag"]}"',
        }

    def get_object(self, *, Bucket, Key):
        item = self.objects[(Bucket, Key)]
        return {"Body": io.BytesIO(item["payload"])}

    def delete_object(self, *, Bucket, Key):
        self.objects.pop((Bucket, Key), None)
        return {}


def storage(client: FakeR2Client | None = None) -> r2_storage.R2Storage:
    return r2_storage.R2Storage(
        endpoint="https://4a82319180f1f1cee60d85a971c3041d.r2.cloudflarestorage.com",
        access_key_id="test-access-key",
        secret_access_key="test-secret-key",
        knowledge_bucket="sovereign-knowledge-files",
        artifacts_bucket="sovereign-runtime-artifacts",
        client=client or FakeR2Client(),
    )


def test_r2_runtime_fails_closed_when_secrets_are_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "R2_ENDPOINT",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_KNOWLEDGE_BUCKET",
        "R2_ARTIFACTS_BUCKET",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(r2_storage.R2StorageUnavailable, match="not configured"):
        r2_storage.R2Storage.from_env()


def test_r2_endpoint_and_bucket_are_restricted() -> None:
    with pytest.raises(r2_storage.R2StorageUnavailable, match="canonical"):
        r2_storage.R2Storage(
            endpoint="https://example.com",
            access_key_id="x",
            secret_access_key="y",
            knowledge_bucket="sovereign-knowledge-files",
            artifacts_bucket="sovereign-runtime-artifacts",
        )
    with pytest.raises(r2_storage.R2StorageUnavailable, match="bucket"):
        r2_storage.R2Storage(
            endpoint="https://account.r2.cloudflarestorage.com",
            access_key_id="x",
            secret_access_key="y",
            knowledge_bucket="../escape",
            artifacts_bucket="sovereign-runtime-artifacts",
        )


def test_knowledge_upload_blocks_path_escape_wrong_mime_and_oversize() -> None:
    digest = "a" * 64
    with pytest.raises(ValueError, match="filename"):
        r2_storage.validate_knowledge_upload("../", "text/plain", 10, digest)
    with pytest.raises(ValueError, match="content type"):
        r2_storage.validate_knowledge_upload("manual.pdf", "text/html", 10, digest)
    with pytest.raises(ValueError, match="exceeds"):
        r2_storage.validate_knowledge_upload(
            "manual.pdf",
            "application/pdf",
            r2_storage.MAX_KNOWLEDGE_BYTES + 1,
            digest,
        )


def test_object_keys_are_server_generated_and_user_scoped() -> None:
    user_id = "11111111-1111-4111-8111-111111111111"
    source_id = "22222222-2222-4222-8222-222222222222"
    digest = "b" * 64
    key = r2_storage.knowledge_object_key(user_id, source_id, digest, "manual.md")
    assert key == f"users/{user_id}/knowledge/{source_id}/{digest}/manual.md"
    with pytest.raises(ValueError):
        r2_storage.knowledge_object_key(user_id, source_id, digest, "..")
    with pytest.raises(ValueError):
        r2_storage.artifact_object_key(user_id, "../foreign-job", digest, "trace.zip")


def test_presigned_put_binds_content_type_sha_and_size() -> None:
    client = FakeR2Client()
    adapter = storage(client)
    digest = "c" * 64
    ticket = adapter.presign_put(
        bucket=adapter.knowledge_bucket,
        object_key="users/11111111-1111-4111-8111-111111111111/knowledge/22222222-2222-4222-8222-222222222222/" + digest + "/manual.md",
        content_type="text/markdown",
        size_bytes=42,
        sha256=digest,
    )
    assert ticket.expires_in_seconds == 900
    assert ticket.headers == {
        "Content-Type": "text/markdown",
        "x-amz-meta-sha256": digest,
        "x-amz-meta-size-bytes": "42",
    }
    params = client.presign_calls[0]["params"]
    assert params["Metadata"] == {"sha256": digest, "size-bytes": "42"}


def test_verify_object_requires_head_and_real_byte_sha_evidence() -> None:
    client = FakeR2Client()
    adapter = storage(client)
    payload = b"# Runtime truth\n\nNo fake success."
    digest = r2_storage.sha256_bytes(payload)
    key = "users/11111111-1111-4111-8111-111111111111/knowledge/22222222-2222-4222-8222-222222222222/" + digest + "/manual.md"
    evidence = adapter.put_object(
        bucket=adapter.knowledge_bucket,
        object_key=key,
        payload=payload,
        content_type="text/markdown",
    )
    verified = adapter.verify_object(
        bucket=evidence.bucket,
        object_key=evidence.object_key,
        expected_sha256=digest,
        expected_content_type="text/markdown",
        expected_size_bytes=len(payload),
        max_bytes=r2_storage.MAX_KNOWLEDGE_BYTES,
    )
    assert verified.sha256 == digest
    client.objects[(adapter.knowledge_bucket, key)]["payload"] = b"drift"
    with pytest.raises(r2_storage.R2EvidenceMismatch):
        adapter.verify_object(
            bucket=adapter.knowledge_bucket,
            object_key=key,
            expected_sha256=digest,
            expected_content_type="text/markdown",
            expected_size_bytes=len(payload),
            max_bytes=r2_storage.MAX_KNOWLEDGE_BYTES,
        )


def test_migration_and_deploy_image_contain_r2_truth_contract() -> None:
    migration = (DEPLOY / "migrations" / "016_r2_object_metadata.sql").read_text(encoding="utf-8")
    requirements = (DEPLOY / "requirements.txt").read_text(encoding="utf-8")
    dockerfile = (DEPLOY / "Dockerfile").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS sovereign_objects" in migration
    assert "object_key LIKE ('users/' || user_id::text || '/%')" in migration
    assert "source_id UUID REFERENCES knowledge_sources" in migration
    assert "job_id TEXT REFERENCES sovereign_agent_jobs" in migration
    assert "boto3" in requirements
    assert "COPY r2_storage.py ." in dockerfile


def test_backend_and_production_r2_adapters_expose_same_contract() -> None:
    backend = (BACKEND / "r2_storage.py").read_text(encoding="utf-8")
    deploy = (DEPLOY / "r2_storage.py").read_text(encoding="utf-8")
    required_symbols = (
        "class R2Storage",
        "def validate_knowledge_upload",
        "def validate_artifact_upload",
        "def knowledge_object_key",
        "def artifact_object_key",
        "def verify_object",
        "def presign_put",
        "def presign_get",
    )
    for symbol in required_symbols:
        assert symbol in backend
        assert symbol in deploy
