from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import github_knowledge_mcp_client as client


REVISION = "a" * 40
DIGEST = "sha256:" + "b" * 64


def _verified_payload() -> dict[str, object]:
    return {
        "ok": True,
        "status": "GITHUB_KNOWLEDGE_LIVE_CANARY_VERIFIED",
        "sourceRevision": REVISION,
        "imageDigest": DIGEST,
        "evidence": {
            "source": {
                "status": "ready",
                "chunkCount": 2,
                "embeddedCount": 2,
                "candidateCount": 2,
                "outboxCount": 2,
                "contentSha256": "c" * 64,
                "embeddingModel": "text-embedding-canary",
                "embeddingProviderPresent": True,
                "markerSha256": "d" * 64,
                "publicReadWithoutCredential": True,
                "githubRequestCount": 3,
                "sourceUrlFingerprint": "e" * 24,
            },
            "transportFailure": {
                "blocker": "github_api_timeout",
                "httpStatus": 504,
                "auditRecorded": True,
                "targetFingerprintPresent": True,
                "rawUrlPersisted": False,
                "rawExceptionPersisted": False,
                "correlationIdSha256": "f" * 64,
            },
        },
        "cleanup": {
            "sourceRows": 0,
            "linkRows": 0,
            "candidateRows": 0,
            "blockRows": 0,
            "outboxRows": 0,
            "auditRows": 0,
        },
        "cleanupVerified": True,
        "secretValuesReturned": False,
        "documentContentReturned": False,
    }


def test_client_source_compiles() -> None:
    compile((ROOT / "github_knowledge_mcp_client.py").read_text("utf-8"), "github-knowledge-mcp-client", "exec")


def test_extract_payload_prefers_structured_content() -> None:
    payload = {"status": "VERIFIED"}
    result = SimpleNamespace(structuredContent=payload, content=[])
    assert client._extract_payload(result) == payload


def test_extract_payload_accepts_bounded_json_text() -> None:
    payload = {"status": "VERIFIED"}
    result = SimpleNamespace(
        structuredContent=None,
        content=[SimpleNamespace(text=json.dumps(payload))],
    )
    assert client._extract_payload(result) == payload


def test_queue_helpers_require_stable_hex_request_id() -> None:
    request_id = "1" * 32
    assert client._request_id({"request_id": request_id}) == request_id
    assert client._request_id({"requestId": request_id.upper()}) == request_id
    assert client._request_id({"request_id": "not-valid"}) == ""
    assert client._terminal_payload({"status": "QUEUED"}) is False
    assert client._terminal_payload({"status": "IN_PROGRESS"}) is False
    assert client._terminal_payload({"status": "GITHUB_KNOWLEDGE_LIVE_CANARY_VERIFIED"}) is True


def test_verified_payload_returns_only_bounded_summary() -> None:
    summary = client._validated_summary(
        _verified_payload(),
        expected_revision=REVISION,
        expected_image_digest=DIGEST,
    )
    assert summary["status"] == "GITHUB_KNOWLEDGE_LIVE_CANARY_VERIFIED"
    assert summary["chunkCount"] == 2
    assert summary["cleanupVerified"] is True
    assert summary["cleanup"] == {
        "sourceRows": 0,
        "linkRows": 0,
        "candidateRows": 0,
        "blockRows": 0,
        "outboxRows": 0,
        "auditRows": 0,
    }
    assert len(str(summary["evidenceSha256"])) == 64
    assert summary["documentContentReturned"] is False
    assert "https://" not in json.dumps(summary).casefold()
    assert "github.com" not in json.dumps(summary).casefold()


def test_cleanup_or_vector_gap_is_rejected() -> None:
    payload = _verified_payload()
    payload["cleanup"]["outboxRows"] = 1  # type: ignore[index]
    payload["evidence"]["source"]["embeddedCount"] = 1  # type: ignore[index]

    with pytest.raises(RuntimeError, match="cleanupZero"):
        client._validated_summary(
            payload,
            expected_revision=REVISION,
            expected_image_digest=DIGEST,
        )


def test_chunk_count_must_remain_positive_and_bounded() -> None:
    payload = _verified_payload()
    payload["evidence"]["source"]["chunkCount"] = 5  # type: ignore[index]
    payload["evidence"]["source"]["embeddedCount"] = 5  # type: ignore[index]
    payload["evidence"]["source"]["candidateCount"] = 5  # type: ignore[index]
    payload["evidence"]["source"]["outboxCount"] = 5  # type: ignore[index]

    with pytest.raises(RuntimeError, match="boundedChunkCount"):
        client._validated_summary(
            payload,
            expected_revision=REVISION,
            expected_image_digest=DIGEST,
        )
