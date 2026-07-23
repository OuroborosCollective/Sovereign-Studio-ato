"""Bounded direct OpenAI-compatible HTTP transport for persisted LLM routes.

Paid traffic goes directly to OpenRouter and free traffic goes directly to the
managed FreeLLM API. Protected service keys are read only from allowlisted 0600
owner files and are never returned, logged, or persisted by this module.
"""
from __future__ import annotations

import json
import os
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import requests

from llm_transport import (
    FREELLM_TRANSPORT,
    OPENROUTER_TRANSPORT,
    route_api_base,
    route_config,
    route_is_direct_freellm,
    route_is_openrouter_paid,
    route_provider_model,
    route_transport,
)

_MAX_SECRET_BYTES = 8192
_MAX_RESPONSE_BYTES = 4_000_000
_MIN_SECRET_BYTES = 16
_OWNER_ROOT = Path("/opt/sovereign-owner-managed")
_RETRYABLE_FREELLM_BLOCKERS = frozenset({
    "freellm_rate_limited",
    "freellm_timeout",
    "freellm_upstream_unavailable",
    "free_provider_canary_failed",
})
_RETRYABLE_FREELLM_FAMILIES = frozenset({
    "upstream_rate_limited",
    "upstream_http_timeout",
    "upstream_http_4xx",
    "upstream_http_5xx",
    "upstream_redirect_rejected",
    "transport_timeout",
    "transport_request_exception",
})


def classify_freellm_canary_state(result: dict[str, Any]) -> tuple[str, str]:
    """Separate retryable pool availability from hard policy failures."""

    blocker = str(
        result.get("blocker")
        or result.get("error")
        or "free_provider_canary_failed"
    )[:120]
    family = str(result.get("failureFamily") or "")[:120]
    retryable = (
        blocker in _RETRYABLE_FREELLM_BLOCKERS
        or family in _RETRYABLE_FREELLM_FAMILIES
    )
    return ("discovered" if retryable else "blocked", blocker)


class DirectLlmRuntimeError(RuntimeError):
    def __init__(self, family: str) -> None:
        super().__init__(family)
        self.family = str(family)[:120]


def _owner_root() -> Path:
    return Path(os.getenv("SOVEREIGN_OWNER_INPUT_ROOT", str(_OWNER_ROOT))).resolve()


def _key_contract(transport: str, api_base: str) -> tuple[str, str]:
    if transport == OPENROUTER_TRANSPORT:
        return "SOVEREIGN_OPENROUTER_API_KEY_FILE", "openrouter_api_key.txt"
    if transport == FREELLM_TRANSPORT:
        normalized = str(api_base or "").strip().rstrip("/")
        if normalized == "http://freellmapi:3001/v1":
            return "SOVEREIGN_FREELLMAPI_UNIFIED_KEY_FILE", "freellmapi_unified_key.txt"
        if normalized == "http://freellmpool:8080/v1":
            return "SOVEREIGN_FREELLMPOOL_PROXY_KEY_FILE", "freellmpool_proxy_key.txt"
    raise DirectLlmRuntimeError("unsupported_llm_transport")


@contextmanager
def _protected_key(transport: str, api_base: str) -> Iterator[str]:
    env_name, filename = _key_contract(transport, api_base)
    root = _owner_root()
    candidate = Path(os.getenv(env_name, str(root / filename))).resolve()
    protected = bytearray()
    try:
        if candidate.parent != root or candidate.name != filename:
            raise DirectLlmRuntimeError(f"{transport}_key_path_invalid")
        info = candidate.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or candidate.is_symlink()
            or stat.S_IMODE(info.st_mode) & 0o077
        ):
            raise DirectLlmRuntimeError(f"{transport}_key_permissions_invalid")
        if not _MIN_SECRET_BYTES <= info.st_size <= _MAX_SECRET_BYTES:
            raise DirectLlmRuntimeError(f"{transport}_key_invalid")
        protected = bytearray(candidate.read_bytes())
        key = protected.decode("utf-8").strip()
        if len(key) < _MIN_SECRET_BYTES or any(marker in key for marker in ("\x00", "\n", "\r")):
            raise DirectLlmRuntimeError(f"{transport}_key_invalid")
        yield key
    except FileNotFoundError as exc:
        raise DirectLlmRuntimeError(f"{transport}_key_missing") from exc
    except UnicodeDecodeError as exc:
        raise DirectLlmRuntimeError(f"{transport}_key_invalid") from exc
    finally:
        for index in range(len(protected)):
            protected[index] = 0


def _openrouter_policy(route: dict[str, Any]) -> dict[str, Any]:
    policy = route_config(route).get("providerPolicy")
    required = {
        "require_parameters": True,
        "allow_fallbacks": False,
        "data_collection": "deny",
    }
    if not isinstance(policy, dict) or any(policy.get(key) != value for key, value in required.items()):
        raise DirectLlmRuntimeError("openrouter_provider_policy_rejected")
    return required


def _response_copy(response: requests.Response, raw: bytes) -> requests.Response:
    copied = requests.Response()
    copied.status_code = int(response.status_code)
    copied.headers = response.headers.copy()
    copied.url = response.url
    copied.reason = response.reason
    copied.encoding = response.encoding or "utf-8"
    copied._content = raw
    return copied


def fetch_direct_llm(
    route: dict[str, Any],
    *,
    json_data: dict[str, Any],
    timeout: int = 120,
) -> tuple[requests.Response | None, str]:
    """Execute one exact persisted direct route and return bounded response bytes."""

    transport = route_transport(route)
    if transport == OPENROUTER_TRANSPORT:
        if not route_is_openrouter_paid(route):
            return None, "openrouter_paid_route_rejected"
    elif transport == FREELLM_TRANSPORT:
        if not route_is_direct_freellm(route):
            return None, "freellm_direct_route_rejected"
    else:
        return None, "unsupported_llm_transport"

    api_base = route_api_base(route)
    model = route_provider_model(route)
    if not model or len(model) > 240:
        return None, f"{transport}_model_invalid"
    body = dict(json_data or {})
    body["model"] = model
    body["stream"] = False
    if transport == OPENROUTER_TRANSPORT:
        try:
            body["provider"] = _openrouter_policy(route)
        except DirectLlmRuntimeError as exc:
            return None, exc.family

    try:
        with _protected_key(transport, api_base) as key:
            headers = {
                "Authorization": f"Bearer {key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "sovereign-studio-direct-llm/1",
            }
            if transport == OPENROUTER_TRANSPORT:
                referer = os.getenv("SOVEREIGN_OPENROUTER_HTTP_REFERER", "").strip()
                title = os.getenv("SOVEREIGN_OPENROUTER_APP_TITLE", "Sovereign Studio").strip()
                if referer:
                    headers["HTTP-Referer"] = referer[:500]
                if title:
                    headers["X-OpenRouter-Title"] = title[:200]
            endpoint = f"{api_base}/chat/completions"
            with requests.Session() as session:
                session.trust_env = False
                with session.post(
                    endpoint,
                    headers=headers,
                    json=body,
                    timeout=max(5, min(int(timeout), 180)),
                    allow_redirects=False,
                    stream=True,
                ) as response:
                    content_length = int(response.headers.get("Content-Length") or 0)
                    if content_length > _MAX_RESPONSE_BYTES:
                        return None, f"{transport}_response_too_large"
                    raw = response.raw.read(_MAX_RESPONSE_BYTES + 1, decode_content=True)
                    if len(raw) > _MAX_RESPONSE_BYTES:
                        return None, f"{transport}_response_too_large"
                    return _response_copy(response, raw), ""
    except DirectLlmRuntimeError as exc:
        return None, exc.family
    except requests.Timeout:
        return None, f"{transport}_timeout"
    except requests.ConnectionError:
        return None, f"{transport}_upstream_unavailable"
    except (OSError, requests.RequestException):
        return None, f"{transport}_request_failed"


def _bounded_int(value: Any) -> int:
    try:
        return max(0, min(int(value or 0), 100_000_000))
    except (TypeError, ValueError):
        return 0


def extract_direct_llm_evidence(
    response: requests.Response,
    payload: Any,
    *,
    transport: str,
) -> dict[str, Any]:
    root = payload if isinstance(payload, dict) else {}
    usage = root.get("usage") if isinstance(root.get("usage"), dict) else {}
    prompt_tokens = _bounded_int(usage.get("prompt_tokens"))
    completion_tokens = _bounded_int(usage.get("completion_tokens"))
    total_tokens = _bounded_int(usage.get("total_tokens"))
    if total_tokens <= 0 and (prompt_tokens or completion_tokens):
        total_tokens = prompt_tokens + completion_tokens
    prompt_details = (
        usage.get("prompt_tokens_details")
        if isinstance(usage.get("prompt_tokens_details"), dict)
        else {}
    )
    provider_cost: float | None = None
    raw_cost = usage.get("cost")
    if raw_cost is not None and not isinstance(raw_cost, bool):
        try:
            parsed = float(raw_cost)
            if 0 <= parsed <= 1_000_000:
                provider_cost = parsed
        except (TypeError, ValueError):
            provider_cost = None
    request_id = ""
    for candidate in (
        response.headers.get("x-request-id"),
        response.headers.get("X-Request-Id"),
        root.get("id"),
    ):
        normalized = str(candidate or "").strip()
        if normalized:
            request_id = normalized[:200]
            break
    pool_meta = root.get("x_freellmpool") if isinstance(root.get("x_freellmpool"), dict) else {}
    return {
        "promptTokens": prompt_tokens,
        "cachedPromptTokens": _bounded_int(prompt_details.get("cached_tokens")),
        "completionTokens": completion_tokens,
        "totalTokens": total_tokens,
        "upstreamRequestId": request_id,
        "providerGenerationId": str(root.get("id") or "")[:200] or None,
        "providerCostUsd": provider_cost,
        "resolvedTransport": transport,
        "actualProvider": str(pool_meta.get("provider") or "")[:80] or None,
        "actualProviderModel": str(pool_meta.get("model") or "")[:240] or None,
        "rawProviderResponsePersisted": False,
    }


def _safe_error_material(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    root = payload if isinstance(payload, dict) else {}
    error = root.get("error") if isinstance(root.get("error"), dict) else {}
    values = (
        error.get("code"),
        error.get("type"),
        error.get("message"),
        root.get("code"),
        root.get("message"),
    )
    return " ".join(str(value or "").strip().lower()[:240] for value in values)


def classify_direct_llm_failure(
    route: dict[str, Any],
    response: requests.Response | None,
    transport_error: str = "",
) -> dict[str, Any]:
    transport = route_transport(route) or "llm"
    if transport_error:
        raw_blocker = str(transport_error)[:120]
        blocker = (
            f"{transport}_upstream_unavailable"
            if raw_blocker == f"{transport}_request_failed"
            else raw_blocker
        )
        retryable = blocker in {
            f"{transport}_timeout",
            f"{transport}_upstream_unavailable",
        }
        return {
            "ok": False,
            "health": "degraded" if retryable else "blocked",
            "blocker": blocker,
            "error": "Der direkte LLM-Transport ist vorübergehend nicht verfügbar." if retryable else "Der direkte LLM-Transport wurde sicher abgelehnt.",
            "httpStatus": None,
        }
    if response is None:
        return {
            "ok": False,
            "health": "degraded",
            "blocker": f"{transport}_request_failed",
            "error": "Der direkte LLM-Request ist fehlgeschlagen.",
            "httpStatus": None,
        }
    status = int(response.status_code)
    combined = _safe_error_material(response)
    if status == 429 and "quota" in combined:
        blocker = "provider_quota_exhausted"
        health = "blocked"
    elif status == 429:
        blocker = f"{transport}_rate_limited"
        health = "degraded"
    elif status in {408, 504}:
        blocker = f"{transport}_timeout"
        health = "degraded"
    elif status in {401, 403}:
        blocker = f"{transport}_credentials_rejected"
        health = "blocked"
    elif status == 402 and transport == OPENROUTER_TRANSPORT:
        blocker = "openrouter_account_credits_required"
        health = "blocked"
    elif status == 404 or status >= 500 or 300 <= status < 400:
        blocker = f"{transport}_upstream_unavailable"
        health = "degraded"
    else:
        blocker = "provider_rejected"
        health = "blocked"
    return {
        "ok": False,
        "health": health,
        "blocker": blocker,
        "error": "Der direkte Provider hat den Modellaufruf abgelehnt.",
        "httpStatus": status,
    }
