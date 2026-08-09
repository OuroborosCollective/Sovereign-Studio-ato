"""Canonical managed-key contracts required by the FreeLLM embedding adapter.

The deployed provider-discovery implementation lives under
scripts/sovereign-backend. This canonical module intentionally exposes only the
small secret-file and managed-internal-URL contract needed by backend consumers.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import stat
import urllib.parse
from pathlib import Path
from typing import Any

_MANAGED_INTERNAL_SOURCES = {
    "freellmapi-direct": {
        "apiBase": "http://freellmapi:3001/v1",
        "host": "freellmapi",
        "port": 3001,
    },
    "freellmpool-private": {
        "apiBase": "http://freellmpool:8080/v1",
        "host": "freellmpool",
        "port": 8080,
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

    candidate_path = Path(str(configured_path or root / filename).strip())
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
            "/v1/embeddings",
            "/embeddings",
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
