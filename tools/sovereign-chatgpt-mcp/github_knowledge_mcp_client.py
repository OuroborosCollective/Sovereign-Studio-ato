from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
import time
from typing import Any
from urllib.parse import urlparse

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


DEFAULT_URL = "http://127.0.0.1:8090/mcp"
TOOL_NAME = "github_knowledge_live_canary"
STATUS_TOOL_NAME = "mcp_host_command_status"
COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REQUEST_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _extract_payload(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if structured is None:
        structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured

    for item in list(getattr(result, "content", None) or []):
        text = getattr(item, "text", None)
        if not isinstance(text, str) or not text.strip():
            continue
        try:
            candidate = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            return candidate
    raise RuntimeError("MCP tool result contains no bounded JSON object")


def _request_id(payload: dict[str, Any]) -> str:
    value = str(payload.get("request_id") or payload.get("requestId") or "").strip().lower()
    return value if REQUEST_ID_RE.fullmatch(value) else ""


def _terminal_payload(payload: dict[str, Any]) -> bool:
    return str(payload.get("status") or "").strip().upper() not in {
        "QUEUED",
        "IN_PROGRESS",
    }


def _validated_summary(
    payload: dict[str, Any],
    *,
    expected_revision: str,
    expected_image_digest: str,
) -> dict[str, Any]:
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    source = evidence.get("source") if isinstance(evidence.get("source"), dict) else {}
    transport = (
        evidence.get("transportFailure")
        if isinstance(evidence.get("transportFailure"), dict)
        else {}
    )
    cleanup = payload.get("cleanup") if isinstance(payload.get("cleanup"), dict) else {}
    chunk_count = source.get("chunkCount") if isinstance(source.get("chunkCount"), int) else 0
    cleanup_keys = (
        "sourceRows",
        "linkRows",
        "candidateRows",
        "blockRows",
        "outboxRows",
        "auditRows",
    )

    checks = {
        "ok": payload.get("ok") is True,
        "status": payload.get("status") == "GITHUB_KNOWLEDGE_LIVE_CANARY_VERIFIED",
        "revision": payload.get("sourceRevision") == expected_revision,
        "digest": payload.get("imageDigest") == expected_image_digest,
        "sourceReady": source.get("status") == "ready",
        "publicReadWithoutCredential": source.get("publicReadWithoutCredential") is True,
        "githubRequestCount": isinstance(source.get("githubRequestCount"), int)
        and int(source.get("githubRequestCount") or 0) > 0,
        "boundedChunkCount": 1 <= chunk_count <= 4,
        "embeddedCount": source.get("embeddedCount") == chunk_count,
        "candidateCount": source.get("candidateCount") == chunk_count,
        "outboxCount": source.get("outboxCount") == chunk_count,
        "embeddingProviderPresent": source.get("embeddingProviderPresent") is True,
        "embeddingModelPresent": bool(str(source.get("embeddingModel") or "").strip()),
        "contentSha256": bool(re.fullmatch(r"[0-9a-f]{64}", str(source.get("contentSha256") or ""))),
        "markerSha256": bool(re.fullmatch(r"[0-9a-f]{64}", str(source.get("markerSha256") or ""))),
        "sourceUrlFingerprint": bool(
            re.fullmatch(r"[0-9a-f]{24}", str(source.get("sourceUrlFingerprint") or ""))
        ),
        "transportBlocker": transport.get("blocker") == "github_api_timeout",
        "transportHttpStatus": transport.get("httpStatus") == 504,
        "transportAudit": transport.get("auditRecorded") is True,
        "targetFingerprintPresent": transport.get("targetFingerprintPresent") is True,
        "correlationIdSha256": bool(
            re.fullmatch(r"[0-9a-f]{64}", str(transport.get("correlationIdSha256") or ""))
        ),
        "rawUrlAbsent": transport.get("rawUrlPersisted") is False,
        "rawExceptionAbsent": transport.get("rawExceptionPersisted") is False,
        "cleanupVerified": payload.get("cleanupVerified") is True,
        "cleanupZero": all(cleanup.get(key) == 0 for key in cleanup_keys),
        "secretValuesAbsent": payload.get("secretValuesReturned") is False,
        "documentContentAbsent": payload.get("documentContentReturned") is False,
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise RuntimeError("GitHub Knowledge MCP canary evidence incomplete: " + ",".join(failed))

    summary: dict[str, Any] = {
        "status": "GITHUB_KNOWLEDGE_LIVE_CANARY_VERIFIED",
        "sourceRevision": expected_revision,
        "imageDigest": expected_image_digest,
        "chunkCount": chunk_count,
        "embeddedCount": int(source["embeddedCount"]),
        "candidateCount": int(source["candidateCount"]),
        "outboxCount": int(source["outboxCount"]),
        "githubRequestCount": int(source["githubRequestCount"]),
        "contentSha256": str(source.get("contentSha256") or ""),
        "markerSha256": str(source.get("markerSha256") or ""),
        "embeddingModel": str(source.get("embeddingModel") or ""),
        "sourceUrlFingerprint": str(source.get("sourceUrlFingerprint") or ""),
        "transportFailure": {
            "blocker": "github_api_timeout",
            "httpStatus": 504,
            "auditRecorded": True,
            "rawUrlPersisted": False,
            "rawExceptionPersisted": False,
            "correlationIdSha256": str(transport.get("correlationIdSha256") or ""),
        },
        "cleanup": {key: 0 for key in cleanup_keys},
        "cleanupVerified": True,
        "secretValuesReturned": False,
        "documentContentReturned": False,
    }
    canonical = json.dumps(summary, sort_keys=True, separators=(",", ":")).encode("utf-8")
    summary["evidenceSha256"] = hashlib.sha256(canonical).hexdigest()
    return summary


async def _call_canary(
    *,
    url: str,
    expected_revision: str,
    expected_image_digest: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("MCP canary client permits loopback HTTP only")
    if parsed.path != "/mcp" or parsed.params or parsed.query or parsed.fragment:
        raise ValueError("MCP canary client requires the exact /mcp endpoint")

    deadline = time.monotonic() + max(30.0, min(float(timeout_seconds), 900.0))
    async with streamable_http_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            if TOOL_NAME not in names or STATUS_TOOL_NAME not in names:
                raise RuntimeError("required MCP canary tools are not registered")

            result = await session.call_tool(
                TOOL_NAME,
                arguments={
                    "expected_revision": expected_revision,
                    "expected_image_digest": expected_image_digest,
                },
            )
            payload = _extract_payload(result)
            request_id = _request_id(payload)

            while not _terminal_payload(payload):
                if not request_id:
                    raise RuntimeError("queued MCP canary returned no valid request_id")
                if time.monotonic() >= deadline:
                    raise TimeoutError("queued MCP canary did not reach a terminal state")
                await asyncio.sleep(1.0)
                status_result = await session.call_tool(
                    STATUS_TOOL_NAME,
                    arguments={"request_id": request_id},
                )
                payload = _extract_payload(status_result)
                next_id = _request_id(payload)
                if next_id and next_id != request_id:
                    raise RuntimeError("queued MCP canary request_id changed during polling")

            return _validated_summary(
                payload,
                expected_revision=expected_revision,
                expected_image_digest=expected_image_digest,
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the cleanup-bound GitHub Knowledge production canary through MCP tools/call"
    )
    parser.add_argument("expected_revision")
    parser.add_argument("expected_image_digest")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    arguments = parser.parse_args()

    revision = str(arguments.expected_revision or "").strip().lower()
    digest = str(arguments.expected_image_digest or "").strip().lower()
    if not COMMIT_SHA_RE.fullmatch(revision):
        print(json.dumps({"ok": False, "status": "INVALID_BACKEND_REVISION"}), file=sys.stderr)
        return 2
    if not IMAGE_DIGEST_RE.fullmatch(digest):
        print(json.dumps({"ok": False, "status": "INVALID_BACKEND_IMAGE_DIGEST"}), file=sys.stderr)
        return 2

    try:
        summary = asyncio.run(
            _call_canary(
                url=arguments.url,
                expected_revision=revision,
                expected_image_digest=digest,
                timeout_seconds=arguments.timeout_seconds,
            )
        )
    except Exception as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "status": "GITHUB_KNOWLEDGE_MCP_CANARY_FAILED",
                    "errorType": type(error).__name__,
                    "errorSha256": hashlib.sha256(str(error).encode("utf-8", errors="replace")).hexdigest(),
                    "secretValuesReturned": False,
                    "documentContentReturned": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1

    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
