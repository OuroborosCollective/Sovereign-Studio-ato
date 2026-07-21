"""Dependency-free deterministic contracts for Free Revolver provider discovery."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
import urllib.parse
from typing import Any

_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,239}$")
_MAX_DISCOVERED_MODELS = 200
_MANAGED_INTERNAL_API_BASE = "http://freellmapi:3001/v1"
_MANAGED_INTERNAL_HOST = "freellmapi"
_MANAGED_INTERNAL_PORT = 3001


def normalize_api_base(value: Any) -> str:
    candidate = str(value or "").strip().rstrip("/")
    parsed = urllib.parse.urlsplit(candidate)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("API-Basis darf keine Zugangsdaten, Query oder Fragmente enthalten")
    path = parsed.path.rstrip("/")
    if path.endswith("/models"):
        path = path[:-7].rstrip("/")
    if (
        parsed.scheme == "http"
        and (parsed.hostname or "").lower() == _MANAGED_INTERNAL_HOST
        and parsed.port == _MANAGED_INTERNAL_PORT
        and path == "/v1"
    ):
        return _MANAGED_INTERNAL_API_BASE
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError(
            "API-Basis muss eine vollständige HTTPS-URL oder der verwaltete "
            "FreeLLM-API-Docker-Endpunkt sein"
        )
    normalized = urllib.parse.urlunsplit(("https", parsed.netloc.lower(), path, "", ""))
    return normalized.rstrip("/")


def models_url_candidates(api_base: str) -> tuple[str, ...]:
    base = normalize_api_base(api_base)
    if base.endswith("/v1"):
        candidates = (f"{base}/models", f"{base[:-3]}/models")
    else:
        candidates = (f"{base}/v1/models", f"{base}/models")
    return tuple(dict.fromkeys(candidate.rstrip("/") for candidate in candidates))


def is_managed_internal_provider_url(url: str) -> bool:
    parsed = urllib.parse.urlsplit(str(url or "").strip())
    return (
        parsed.scheme == "http"
        and (parsed.hostname or "").lower() == _MANAGED_INTERNAL_HOST
        and parsed.port == _MANAGED_INTERNAL_PORT
        and parsed.username is None
        and parsed.password is None
        and parsed.query == ""
        and parsed.fragment == ""
        and parsed.path.rstrip("/") in {"/v1", "/v1/models", "/models"}
    )


def assert_public_https_host(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    hostname = parsed.hostname or ""
    try:
        addresses = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Provider-Hostname konnte nicht aufgelöst werden") from exc
    resolved = {entry[4][0] for entry in addresses}
    if not resolved:
        raise ValueError("Provider-Hostname lieferte keine Adresse")
    for raw in resolved:
        address = ipaddress.ip_address(raw)
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise ValueError("Private oder reservierte Provider-Adressen sind nicht erlaubt")


def assert_provider_target_allowed(url: str) -> None:
    if is_managed_internal_provider_url(url):
        return
    assert_public_https_host(url)


def _numeric_zero(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    try:
        return float(value) == 0.0
    except (TypeError, ValueError):
        return None


def zero_price_evidence(item: dict[str, Any]) -> tuple[bool, str]:
    """Require complete explicit zero-cost evidence; names and free flags never count."""
    sources = [
        item.get("pricing"),
        item.get("price"),
        item.get("cost"),
        item.get("billing"),
    ]
    input_fields = {
        "prompt", "input", "input_cost", "input_cost_per_token", "prompt_cost",
    }
    output_fields = {
        "completion", "output", "output_cost", "output_cost_per_token", "completion_cost",
    }
    request_fields = {"request", "request_cost", "cost_per_request"}
    seen_input = False
    seen_output = False
    seen_request = False
    for source in sources:
        if not isinstance(source, dict):
            continue
        for field in input_fields | output_fields | request_fields:
            if field not in source:
                continue
            verdict = _numeric_zero(source.get(field))
            if verdict is None:
                return False, "provider-pricing-invalid"
            if not verdict:
                return False, "provider-pricing-nonzero"
            seen_input = seen_input or field in input_fields
            seen_output = seen_output or field in output_fields
            seen_request = seen_request or field in request_fields
    if seen_request or (seen_input and seen_output):
        return True, "provider-models-explicit-zero-pricing"
    return False, "provider-pricing-unreported-or-incomplete"


def normalize_models_payload(payload: Any) -> list[dict[str, Any]]:
    rows: Any = payload
    if isinstance(payload, dict):
        rows = payload.get("data", payload.get("models", payload.get("items", [])))
    if not isinstance(rows, list):
        raise ValueError("Models-Endpunkt lieferte keine Modellliste")
    normalized: list[dict[str, Any]] = []
    for raw in rows[:_MAX_DISCOVERED_MODELS]:
        if isinstance(raw, str):
            item = {"id": raw}
        elif isinstance(raw, dict):
            item = raw
        else:
            continue
        model_id = str(item.get("id") or item.get("model") or item.get("name") or "").strip()
        if not _MODEL_ID_RE.fullmatch(model_id):
            continue
        display_name = str(
            item.get("display_name")
            or item.get("displayName")
            or item.get("name")
            or model_id
        ).strip()[:160]
        free_verified, pricing_source = zero_price_evidence(item)
        capabilities = item.get("capabilities") if isinstance(item.get("capabilities"), list) else ["chat"]
        normalized.append({
            "modelId": model_id,
            "displayName": display_name or model_id,
            "capabilities": [str(value)[:60] for value in capabilities[:20]],
            "freeVerified": free_verified,
            "pricingSource": pricing_source,
            "payloadSha256": hashlib.sha256(
                json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
            ).hexdigest(),
        })
    normalized.sort(key=lambda entry: entry["modelId"].casefold())
    return normalized
