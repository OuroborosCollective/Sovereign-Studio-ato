"""Bounded internal LiteLLM client for Sovereign routing evidence.

Provider credentials stay inside the LiteLLM container. The Sovereign backend
reads only the internal LiteLLM master key from an owner-managed file and never
returns it in API responses, logs, database rows or error messages.
"""

from __future__ import annotations

import os
from pathlib import Path
import time
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


def _safe_error_material(payload: Any) -> tuple[str, str, str]:
    root = payload if isinstance(payload, dict) else {}
    error = root.get("error") if isinstance(root.get("error"), dict) else {}
    code = str(error.get("code") or root.get("code") or "").strip().lower()[:120]
    error_type = str(error.get("type") or root.get("type") or "").strip().lower()[:120]
    message = str(error.get("message") or root.get("message") or "").strip().lower()[:500]
    return code, error_type, message


def classify_litellm_failure(
    response: requests.Response | None,
    transport_error: str = "",
) -> dict[str, Any]:
    """Map one failed internal request to a bounded non-secret operator state."""
    normalized_transport = str(transport_error or "").strip()
    if normalized_transport:
        transport_map = {
            "litellm_timeout": (
                "degraded",
                "litellm_timeout",
                "LiteLLM hat nicht rechtzeitig geantwortet.",
            ),
            "litellm_unreachable": (
                "degraded",
                "litellm_unreachable",
                "LiteLLM ist vom Backend derzeit nicht erreichbar.",
            ),
            "litellm_internal_key_unavailable": (
                "blocked",
                "litellm_internal_key_unavailable",
                "Der interne LiteLLM-Servicezugang ist nicht verfügbar.",
            ),
            "litellm_request_failed": (
                "degraded",
                "litellm_request_failed",
                "Der interne LiteLLM-Request ist fehlgeschlagen.",
            ),
        }
        health, blocker, error = transport_map.get(
            normalized_transport,
            ("degraded", "litellm_request_failed", "Der interne LiteLLM-Request ist fehlgeschlagen."),
        )
        return {
            "ok": False,
            "health": health,
            "blocker": blocker,
            "error": error,
            "httpStatus": None,
        }

    if response is None:
        return {
            "ok": False,
            "health": "degraded",
            "blocker": "litellm_request_failed",
            "error": "Der interne LiteLLM-Request ist fehlgeschlagen.",
            "httpStatus": None,
        }

    try:
        payload = response.json()
    except ValueError:
        payload = {}
    code, error_type, message = _safe_error_material(payload)
    status = int(response.status_code)
    combined = " ".join((code, error_type, message))

    if status == 429 and ("insufficient_quota" in combined or "quota" in combined):
        health, blocker, error = (
            "blocked",
            "provider_quota_exhausted",
            "Das Provider-Kontingent ist erschöpft. Billing oder Guthaben beim Provider prüfen.",
        )
    elif status == 429:
        health, blocker, error = (
            "degraded",
            "provider_rate_limited",
            "Der Provider begrenzt Anfragen vorübergehend.",
        )
    elif status in {401, 403}:
        health, blocker, error = (
            "blocked",
            "provider_credentials_rejected",
            "Der Provider hat den hinterlegten Servicezugang abgelehnt.",
        )
    elif status == 404:
        health, blocker, error = (
            "blocked",
            "litellm_model_alias_missing",
            "Der konfigurierte Modellalias ist in LiteLLM nicht verfügbar.",
        )
    elif status >= 500:
        health, blocker, error = (
            "degraded",
            "litellm_upstream_unavailable",
            "LiteLLM oder der Upstream-Provider ist vorübergehend nicht bereit.",
        )
    else:
        health, blocker, error = (
            "blocked",
            "provider_rejected",
            "Der Provider hat den Modell-Canary abgelehnt.",
        )
    return {
        "ok": False,
        "health": health,
        "blocker": blocker,
        "error": error,
        "httpStatus": status,
    }


def litellm_completion_canary(model_id: str) -> dict[str, Any]:
    """Verify readiness plus one bounded completion without returning model content."""
    normalized_model = str(model_id or "").strip()
    if not normalized_model or len(normalized_model) > 200 or any(
        character in normalized_model for character in ("\x00", "\n", "\r")
    ):
        return {
            "ok": False,
            "health": "blocked",
            "blocker": "litellm_model_alias_invalid",
            "error": "Der konfigurierte Modellalias ist ungültig.",
            "httpStatus": None,
            "responseTimeMs": None,
            "readinessVerified": False,
            "completionVerified": False,
            "evidence": {},
        }

    readiness = litellm_readiness()
    if not readiness.get("ok"):
        return {
            "ok": False,
            "health": "degraded",
            "blocker": str(readiness.get("errorCode") or "litellm_not_ready")[:120],
            "error": "LiteLLM ist nicht bereit.",
            "httpStatus": readiness.get("httpStatus"),
            "responseTimeMs": None,
            "readinessVerified": False,
            "completionVerified": False,
            "evidence": {},
        }

    started = time.monotonic()
    response, transport_error = fetch_litellm(
        "/v1/chat/completions",
        method="POST",
        json_data={
            "model": normalized_model,
            "messages": [{"role": "user", "content": "Reply with OK."}],
            "temperature": 0,
            "max_tokens": 8,
            "stream": False,
        },
    )
    response_time_ms = max(0, int((time.monotonic() - started) * 1000))
    if transport_error or response is None or not response.ok:
        classified = classify_litellm_failure(response, transport_error)
        return {
            **classified,
            "responseTimeMs": response_time_ms,
            "readinessVerified": True,
            "completionVerified": False,
            "evidence": {},
        }

    try:
        payload = response.json()
    except ValueError:
        payload = {}
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not isinstance(choices, list) or not choices:
        return {
            "ok": False,
            "health": "degraded",
            "blocker": "litellm_invalid_completion_response",
            "error": "LiteLLM lieferte keine verifizierbare Modellantwort.",
            "httpStatus": response.status_code,
            "responseTimeMs": response_time_ms,
            "readinessVerified": True,
            "completionVerified": False,
            "evidence": extract_litellm_evidence(response, payload),
        }

    return {
        "ok": True,
        "health": "healthy",
        "blocker": None,
        "error": None,
        "httpStatus": response.status_code,
        "responseTimeMs": response_time_ms,
        "readinessVerified": True,
        "completionVerified": True,
        "evidence": extract_litellm_evidence(response, payload),
    }
