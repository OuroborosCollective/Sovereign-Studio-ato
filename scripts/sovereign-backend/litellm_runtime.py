"""Bounded internal LiteLLM client for Sovereign routing evidence.

Provider credentials stay inside the LiteLLM container. The Sovereign backend
reads only the internal LiteLLM master key from an owner-managed file and never
returns it in API responses, logs, database rows or error messages.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests

LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "http://litellm:4000").rstrip("/")
LITELLM_MASTER_KEY_FILE = Path(
    os.getenv(
        "LITELLM_MASTER_KEY_FILE",
        "/opt/sovereign-owner-managed/litellm_master_key.txt",
    )
)
LITELLM_TIMEOUT_SECONDS = max(
    5,
    min(int(os.getenv("LITELLM_TIMEOUT_SECONDS", "90")), 180),
)
MAX_SECRET_BYTES = 8192


def _read_internal_master_key() -> str:
    path = LITELLM_MASTER_KEY_FILE
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("LiteLLM internal key file is unavailable")
    if path.stat().st_size < 16 or path.stat().st_size > MAX_SECRET_BYTES:
        raise RuntimeError("LiteLLM internal key file has an invalid size")
    value = path.read_text("utf-8").strip()
    if len(value) < 16 or "\x00" in value or "\n" in value or "\r" in value:
        raise RuntimeError("LiteLLM internal key file is invalid")
    return value


def _headers(*, authenticated: bool) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if authenticated:
        headers["Authorization"] = f"Bearer {_read_internal_master_key()}"
    return headers


def fetch_litellm(
    path: str,
    *,
    method: str = "GET",
    json_data: dict[str, Any] | None = None,
    authenticated: bool = True,
    timeout: int | None = None,
) -> tuple[requests.Response | None, str]:
    """Call one internal LiteLLM endpoint and return bounded non-secret errors."""
    url = f"{LITELLM_BASE_URL}/{path.lstrip('/')}"
    request_timeout = timeout or LITELLM_TIMEOUT_SECONDS
    try:
        if method == "GET":
            response = requests.get(
                url,
                headers=_headers(authenticated=authenticated),
                timeout=request_timeout,
            )
        elif method == "POST":
            response = requests.post(
                url,
                headers=_headers(authenticated=authenticated),
                json=json_data,
                timeout=request_timeout,
            )
        else:
            return None, "unsupported_litellm_method"
        return response, ""
    except requests.exceptions.Timeout:
        return None, "litellm_timeout"
    except requests.exceptions.ConnectionError:
        return None, "litellm_unreachable"
    except (OSError, RuntimeError, UnicodeError):
        return None, "litellm_internal_key_unavailable"
    except requests.exceptions.RequestException:
        return None, "litellm_request_failed"


def litellm_readiness() -> dict[str, Any]:
    response, error = fetch_litellm(
        "/health/readiness",
        authenticated=False,
        timeout=10,
    )
    if error or response is None:
        return {"ok": False, "errorCode": error or "litellm_readiness_failed"}
    payload: dict[str, Any] = {}
    try:
        parsed = response.json()
        payload = parsed if isinstance(parsed, dict) else {}
    except ValueError:
        payload = {}
    return {
        "ok": response.status_code == 200,
        "httpStatus": response.status_code,
        "status": str(payload.get("status") or "unknown")[:40],
        "db": str(payload.get("db") or "unknown")[:40],
    }


def extract_litellm_usage(payload: Any) -> dict[str, int]:
    root = payload if isinstance(payload, dict) else {}
    usage = root.get("usage") if isinstance(root.get("usage"), dict) else {}

    def bounded_int(name: str) -> int:
        try:
            return max(0, min(int(usage.get(name) or 0), 100_000_000))
        except (TypeError, ValueError):
            return 0

    prompt_tokens = bounded_int("prompt_tokens")
    completion_tokens = bounded_int("completion_tokens")
    total_tokens = bounded_int("total_tokens")
    if total_tokens <= 0 and (prompt_tokens > 0 or completion_tokens > 0):
        total_tokens = prompt_tokens + completion_tokens
    return {
        "promptTokens": prompt_tokens,
        "completionTokens": completion_tokens,
        "totalTokens": total_tokens,
    }


def extract_litellm_evidence(response: requests.Response, payload: Any) -> dict[str, Any]:
    root = payload if isinstance(payload, dict) else {}
    upstream_request_id = ""
    for candidate in (
        response.headers.get("x-litellm-call-id"),
        response.headers.get("x-request-id"),
        root.get("id"),
    ):
        normalized = str(candidate or "").strip()
        if normalized:
            upstream_request_id = normalized[:200]
            break

    provider_cost_usd: float | None = None
    for header_name in (
        "x-litellm-response-cost",
        "x-litellm-spend",
    ):
        raw = str(response.headers.get(header_name) or "").strip()
        if not raw:
            continue
        try:
            parsed = float(raw)
        except ValueError:
            continue
        if 0 <= parsed <= 1_000_000:
            provider_cost_usd = parsed
            break

    return {
        **extract_litellm_usage(root),
        "upstreamRequestId": upstream_request_id,
        "providerCostUsd": provider_cost_usd,
    }
