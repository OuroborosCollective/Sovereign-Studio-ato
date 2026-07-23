"""Dependency-free deterministic contracts for Free Revolver provider discovery."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import re
import socket
import stat
import urllib.parse
import uuid
from pathlib import Path
from typing import Any

_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,239}$")
_MAX_DISCOVERED_MODELS = 200
_MAX_AUTO_ACTIVATE = 100
_MANAGED_INTERNAL_SOURCES = {
    "freellmapi-direct": {
        "apiBase": "http://freellmapi:3001/v1",
        "host": "freellmapi",
        "port": 3001,
        "keyFilename": "freellmapi_unified_key.txt",
        "keyEnv": "SOVEREIGN_FREELLMAPI_UNIFIED_KEY_FILE",
        "errorPrefix": "freellm",
    },
    "freellmpool-private": {
        "apiBase": "http://freellmpool:8080/v1",
        "host": "freellmpool",
        "port": 8080,
        "keyFilename": "freellmpool_proxy_key.txt",
        "keyEnv": "SOVEREIGN_FREELLMPOOL_PROXY_KEY_FILE",
        "errorPrefix": "freellmpool",
    },
}
_MANAGED_KEY_FILENAME = "freellmapi_unified_key.txt"


class ManagedKeyContractError(ValueError):
    """Bounded key-file contract failure that never contains protected material."""

    def __init__(self, code: str) -> None:
        self.code = str(code)[:120]
        super().__init__(self.code)


def read_managed_freellm_key_file(
    *,
    owner_root: Path,
    configured_path: str,
    expected_fingerprint: str = "",
    expected_filename: str = _MANAGED_KEY_FILENAME,
    error_prefix: str = "freellm",
) -> tuple[bytearray, str]:
    root = Path(owner_root).resolve()
    filename = str(expected_filename or "").strip()
    prefix = str(error_prefix or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{3,40}", prefix) or not re.fullmatch(
        r"[A-Za-z0-9._-]{3,120}", filename
    ):
        raise ManagedKeyContractError("managed_key_contract_invalid")

    def code(suffix: str) -> str:
        return f"{prefix}_managed_key_{suffix}"

    raw_path = str(configured_path or root / filename).strip()
    candidate_path = Path(raw_path)
    if candidate_path.is_symlink():
        raise ManagedKeyContractError(code("path_invalid"))
    try:
        candidate = candidate_path.resolve(strict=False)
    except OSError as exc:
        raise ManagedKeyContractError(code("path_invalid")) from exc
    if candidate.parent != root or candidate.name != filename:
        raise ManagedKeyContractError(code("path_invalid"))
    try:
        info = candidate.lstat()
    except FileNotFoundError as exc:
        raise ManagedKeyContractError(code("missing")) from exc
    except OSError as exc:
        raise ManagedKeyContractError(code("unreadable")) from exc
    if not stat.S_ISREG(info.st_mode):
        raise ManagedKeyContractError(code("type_invalid"))
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise ManagedKeyContractError(code("permissions_invalid"))
    if info.st_size < 8 or info.st_size > 8192:
        raise ManagedKeyContractError(code("size_invalid"))

    protected = bytearray()
    try:
        try:
            protected = bytearray(candidate.read_bytes())
        except OSError as exc:
            raise ManagedKeyContractError(code("unreadable")) from exc
        try:
            key = protected.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise ManagedKeyContractError(code("encoding_invalid")) from exc
        if len(key) < 8 or any(marker in key for marker in ("\x00", "\n", "\r")):
            raise ManagedKeyContractError(code("value_invalid"))
        actual_fingerprint = hashlib.sha256(key.encode()).hexdigest()
        expected = str(expected_fingerprint or "").strip().lower()
        if expected and (
            not re.fullmatch(r"[0-9a-f]{64}", expected)
            or not hmac.compare_digest(actual_fingerprint, expected)
        ):
            raise ManagedKeyContractError(code("fingerprint_mismatch"))
        return protected, key
    except Exception:
        for index in range(len(protected)):
            protected[index] = 0
        raise


def normalize_provider_source_id(value: Any) -> str:
    try:
        return str(uuid.UUID(str(value or "")))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("free_provider_source_id_invalid") from exc


def normalize_max_auto_activate(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("maxAutoActivate muss eine ganze Zahl sein")
    return max(1, min(value, _MAX_AUTO_ACTIVATE))


def managed_internal_source_id(value: Any) -> str | None:
    parsed = urllib.parse.urlsplit(str(value or "").strip())
    path = parsed.path.rstrip("/") or "/"
    if (
        parsed.scheme != "http"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or path not in {
            "/v1",
            "/v1/models",
            "/models",
            "/v1/chat/completions",
            "/chat/completions",
            "/healthz",
            "/status",
            "/v1/status",
        }
    ):
        return None
    for source_id, spec in _MANAGED_INTERNAL_SOURCES.items():
        if (
            (parsed.hostname or "").lower() == spec["host"]
            and parsed.port == spec["port"]
        ):
            return source_id
    return None


def managed_internal_source_spec(value: Any) -> dict[str, Any] | None:
    source_id = managed_internal_source_id(value)
    if source_id is None:
        return None
    return {"sourceId": source_id, **_MANAGED_INTERNAL_SOURCES[source_id]}


def normalize_api_base(value: Any) -> str:
    candidate = str(value or "").strip().rstrip("/")
    parsed = urllib.parse.urlsplit(candidate)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("API-Basis darf keine Zugangsdaten, Query oder Fragmente enthalten")
    path = parsed.path.rstrip("/")
    if path.endswith("/models"):
        path = path[:-7].rstrip("/")
    normalized_internal = urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, path, "", "")
    )
    source = managed_internal_source_spec(normalized_internal)
    if source is not None and path == "/v1":
        return str(source["apiBase"])
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError(
            "API-Basis muss eine vollständige HTTPS-URL oder ein exakt "
            "freigegebener verwalteter Free-Docker-Endpunkt sein"
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
    return managed_internal_source_id(url) is not None


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


def normalize_models_payload(
    payload: Any,
    *,
    managed_quota_contract: bool = False,
) -> list[dict[str, Any]]:
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
        if (
            managed_quota_contract
            and not free_verified
            and pricing_source == "provider-pricing-unreported-or-incomplete"
        ):
            free_verified = True
            pricing_source = "managed-freellm-zero-cost-quota-contract"
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
