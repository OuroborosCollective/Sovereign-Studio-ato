"""Stable contracts for the Sovereign enterprise platform API."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

API_VERSION = "v1"
SCHEMA_VERSION = "sovereign.enterprise-platform.v1"
SOURCE_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
EVIDENCE_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")

STATUS_VERIFIED = "verified"
STATUS_DEGRADED = "degraded"
STATUS_BLOCKED = "blocked"
STATUS_DEFINED_NOT_RUN = "defined_not_run"
STATUS_ISOLATED = "isolated"

ALLOWED_STATUSES = frozenset({
    STATUS_VERIFIED,
    STATUS_DEGRADED,
    STATUS_BLOCKED,
    STATUS_DEFINED_NOT_RUN,
    STATUS_ISOLATED,
})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def evidence_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalize_source_revision(value: str | None) -> tuple[str, bool]:
    candidate = str(value or "").strip().lower()
    return (candidate, True) if SOURCE_REVISION_RE.fullmatch(candidate) else ("unverified", False)


def normalize_image_digest(value: str | None) -> tuple[str, bool]:
    candidate = str(value or "").strip().lower()
    return (candidate, True) if IMAGE_DIGEST_RE.fullmatch(candidate) else ("unverified", False)


def bounded_text(value: Any, *, maximum: int = 160) -> str:
    return str(value or "").strip().replace("\x00", "")[:maximum]


def bounded_int(value: Any, *, minimum: int = 0, maximum: int = 2_147_483_647) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = minimum
    return max(minimum, min(parsed, maximum))


def api_error(code: str, message: str, request_id: str, *, blocker: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "error": {
            "code": bounded_text(code, maximum=100),
            "message": bounded_text(message, maximum=300),
        },
        "requestId": request_id,
        "schemaVersion": SCHEMA_VERSION,
    }
    if blocker:
        payload["error"]["blocker"] = bounded_text(blocker, maximum=120)
    return payload
