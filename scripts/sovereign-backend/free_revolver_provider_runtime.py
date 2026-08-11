"""Evidence-first direct-provider onboarding for the FreeLLM Revolver control plane.

Managed FreeLLM stays on its private OpenAI-compatible API and never traverses
Legacy LiteLLM. PostgreSQL stores route metadata, fingerprints and bounded health
evidence only; protected key values remain owner-managed.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import stat
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import requests
from flask import jsonify, make_response, request

from direct_llm_runtime import classify_freellm_canary_state
from freellm_provider_admin_page import FREELLM_PROVIDER_KEYS_PAGE as _FREELLM_PROVIDER_KEYS_PAGE
from freellm_provider_credentials import (
    FREELLM_PROVIDER_SPECS,
    FREELLM_RUNTIME_GID,
    FREELLM_RUNTIME_UID,
    detect_freellm_provider_id_from_key,
    normalize_freellm_provider_id,
    provider_keyless_marker_path,
    provider_secret_path,
    provider_secret_paths,
    provider_secret_pool_path,
    provider_target_id,
)
from free_revolver_provider_contracts import (
    ManagedKeyContractError,
    assert_provider_target_allowed,
    general_chat_response_verified,
    is_managed_internal_provider_url,
    is_specialist_model_identifier,
    managed_internal_source_spec,
    models_url_candidates,
    normalize_api_base,
    normalize_max_auto_activate,
    normalize_models_payload,
    normalize_provider_source_id,
    read_managed_freellm_key_file,
)

_ALIAS_RE = re.compile(r"[^a-z0-9-]+")
_MANAGED_AUTH_MODE = "managed-bearer"
_AUTH_MODES = {"bearer", "x-api-key", "none", _MANAGED_AUTH_MODE}
_MAX_MODELS_RESPONSE_BYTES = 2_000_000
_KNOWN_KEYLESS_POOL_PROVIDERS = {"ovh", "ovhcloud", "kilo", "llm7"}
_SOURCE_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_FREELLM_RECEIPT_SCHEMA = "sovereign.freellm-route-receipt.v3"
_DEFAULT_MIN_READY_ROUTES = 5
_DEFAULT_RECONCILE_PACE_SECONDS = 0.25
_DEFAULT_EVIDENCE_MAINTENANCE_INTERVAL_SECONDS = 21_600
_DEFAULT_EVIDENCE_MAINTENANCE_INITIAL_DELAY_SECONDS = 60
_DEFAULT_EVIDENCE_MAINTENANCE_MAX_MODELS = 12
_DEFAULT_EVIDENCE_MAINTENANCE_MAX_ROUNDS = 10
_DEFAULT_EVIDENCE_MAINTENANCE_KEY_IMPORT_FOLLOWUP_SECONDS = 20
_EVIDENCE_MAINTENANCE_ADVISORY_LOCK = (20_260_811, 1_179_405_637)
_VERIFIED_GENERAL_CHAT_BLOCKERS = frozenset({
    "specialist-model-identifier",
    "explicit-non-chat-capability",
    "capability-evidence-too-large",
    "no-text-chat-capability",
})


def _internal_owner_authorized() -> bool:
    expected = os.getenv("SOVEREIGN_OWNER_REQUEST_KEY", "").strip()
    presented = request.headers.get("X-Sovereign-Owner-Request-Key", "").strip()
    return bool(expected and presented) and hmac.compare_digest(expected, presented)


def _owner_root() -> Path:
    return Path(os.getenv("SOVEREIGN_OWNER_INPUT_ROOT", "/opt/sovereign-owner-managed")).resolve()


def _secret_path(owner_request_id: str) -> Path:
    safe_request_id = str(uuid.UUID(str(owner_request_id or "")))
    return _owner_root() / f"revolver_provider_key.{safe_request_id}.txt"


def _read_managed_key(
    api_base: str,
    expected_fingerprint: str = "",
) -> tuple[bytearray, str]:
    root = _owner_root()
    source = managed_internal_source_spec(api_base)
    if source is None:
        raise ManagedKeyContractError("managed_key_source_invalid")
    filename = str(source["keyFilename"])
    configured_path = os.getenv(
        str(source["keyEnv"]),
        str(root / filename),
    )
    return read_managed_freellm_key_file(
        owner_root=root,
        configured_path=configured_path,
        expected_fingerprint=expected_fingerprint,
        expected_filename=filename,
        error_prefix=str(source["errorPrefix"]),
    )


def _managed_key_state(api_base: str, expected_fingerprint: str = "") -> dict[str, Any]:
    protected = bytearray()
    key = ""
    try:
        protected, key = _read_managed_key(api_base, expected_fingerprint)
        return {
            "available": True,
            "fingerprintMatches": bool(expected_fingerprint),
            "blocker": None,
        }
    except ManagedKeyContractError as exc:
        return {
            "available": False,
            "fingerprintMatches": False if expected_fingerprint else None,
            "blocker": exc.code,
        }
    finally:
        key = ""
        for index in range(len(protected)):
            protected[index] = 0


def _securely_remove(path: Path) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISREG(info.st_mode) and info.st_size <= 65536:
        try:
            with path.open("r+b", buffering=0) as handle:
                handle.write(b"\0" * info.st_size)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            pass
    path.unlink(missing_ok=True)


def _cleanup_orphaned_secret_files(query: Callable[..., Any]) -> int:
    """Delete bounded request-key files that no live provider source references."""
    try:
        rows = query(
            """SELECT owner_request_id::text AS request_id
               FROM llm_revolver_provider_sources
               WHERE owner_request_id IS NOT NULL
                 AND enabled=true
                 AND status IN ('awaiting_owner_input','probing')"""
        ) or []
    except Exception:
        return 0
    referenced = {
        str(row.get("request_id") or "")
        for row in rows
        if str(row.get("request_id") or "")
    }
    removed = 0
    try:
        candidates = sorted(_owner_root().glob("revolver_provider_key.*.txt"))[:100]
    except OSError:
        return 0
    for path in candidates:
        raw_request_id = path.name.removeprefix("revolver_provider_key.").removesuffix(".txt")
        try:
            request_id = str(uuid.UUID(raw_request_id))
        except ValueError:
            _securely_remove(path)
            removed += 1
            continue
        if request_id not in referenced:
            _securely_remove(path)
            removed += 1
    return removed


def _minimum_ready_routes() -> int:
    """Return the fixed success threshold, never a ceiling for ready routes."""
    return _DEFAULT_MIN_READY_ROUTES


def _eligibility_evidence_ttl_hours() -> int:
    try:
        value = int(os.getenv("FREE_REVOLVER_ELIGIBILITY_EVIDENCE_TTL_HOURS", "24"))
    except ValueError:
        value = 24
    return max(1, min(value, 168))


def _bounded_maintenance_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


def _reconcile_pace_seconds() -> float:
    try:
        value = float(os.getenv(
            "SOVEREIGN_FREELLM_RECONCILE_PACE_SECONDS",
            str(_DEFAULT_RECONCILE_PACE_SECONDS),
        ))
    except ValueError:
        value = _DEFAULT_RECONCILE_PACE_SECONDS
    return max(0.0, min(value, 3.0))


def _retry_after_seconds(response: Any) -> float:
    raw = str(response.headers.get("Retry-After") or "").strip()
    try:
        return max(0.0, min(float(raw), 300.0))
    except ValueError:
        return 0.0


def _auth_headers(auth_mode: str, key: str) -> dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": "sovereign-free-revolver/3"}
    if auth_mode in {"bearer", _MANAGED_AUTH_MODE}:
        headers["Authorization"] = f"Bearer {key}"
    elif auth_mode == "x-api-key":
        headers["X-API-Key"] = key
    return headers


def _direct_completion_canary(
    *,
    api_base: str,
    auth_mode: str,
    key: str,
    model_id: str,
) -> dict[str, Any]:
    """Run one bounded direct chat completion without exposing response bodies."""

    endpoint = f"{str(api_base).rstrip('/')}/chat/completions"
    assert_provider_target_allowed(endpoint)
    headers = {
        **_auth_headers(auth_mode, key),
        "Content-Type": "application/json",
    }
    status: int | None = None
    started = time.monotonic()
    try:
        with requests.Session() as provider_session:
            provider_session.trust_env = False
            with provider_session.post(
                endpoint,
                headers=headers,
                json={
                    "model": model_id,
                    "messages": [{"role": "user", "content": "Reply with OK."}],
                    "max_tokens": 8,
                    "temperature": 0,
                },
                timeout=30,
                allow_redirects=False,
                stream=True,
            ) as response:
                status = int(response.status_code)
                request_id = (
                    response.headers.get("x-request-id")
                    or response.headers.get("X-Request-Id")
                )
                if status in {401, 403}:
                    return {
                        "ok": False,
                        "blocker": "freellm_credentials_rejected",
                        "httpStatus": status,
                        "failureFamily": "upstream_auth_rejected",
                    }
                if status == 429:
                    return {
                        "ok": False,
                        "blocker": "freellm_rate_limited",
                        "httpStatus": status,
                        "failureFamily": "upstream_rate_limited",
                        "retryAfterSeconds": _retry_after_seconds(response),
                        "latencyMs": int((time.monotonic() - started) * 1000),
                    }
                if status in {408, 504}:
                    return {
                        "ok": False,
                        "blocker": "freellm_timeout",
                        "httpStatus": status,
                        "failureFamily": "upstream_http_timeout",
                    }
                if 300 <= status < 400:
                    return {
                        "ok": False,
                        "blocker": "freellm_upstream_unavailable",
                        "httpStatus": status,
                        "failureFamily": "upstream_redirect_rejected",
                    }
                if 400 <= status < 500:
                    return {
                        "ok": False,
                        "blocker": "freellm_upstream_unavailable",
                        "httpStatus": status,
                        "failureFamily": "upstream_http_4xx",
                    }
                if status >= 500:
                    return {
                        "ok": False,
                        "blocker": "freellm_upstream_unavailable",
                        "httpStatus": status,
                        "failureFamily": "upstream_http_5xx",
                    }
                response.raise_for_status()
                raw = response.raw.read(
                    _MAX_MODELS_RESPONSE_BYTES + 1,
                    decode_content=True,
                )
                if len(raw) > _MAX_MODELS_RESPONSE_BYTES:
                    return {
                        "ok": False,
                        "blocker": "freellm_canary_response_too_large",
                        "httpStatus": status,
                    }
        payload = json.loads(raw.decode("utf-8"))
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not isinstance(choices, list) or not choices:
            return {
                "ok": False,
                "blocker": "freellm_canary_response_invalid",
                "httpStatus": status,
            }
        if not general_chat_response_verified(payload):
            return {
                "ok": False,
                "blocker": "freellm_general_chat_canary_failed",
                "httpStatus": status,
                "failureFamily": "non_chat_completion_response",
            }
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        provider_cost = usage.get("cost")
        generation_id = str(payload.get("id") or request_id or "")[:200] or None
        pool_meta = payload.get("x_freellmpool") if isinstance(payload, dict) else None
        pool_meta = pool_meta if isinstance(pool_meta, dict) else {}
        provider_id = str(pool_meta.get("provider") or "")[:80]
        provider_model = str(pool_meta.get("model") or "")[:200]
        response_model = str(payload.get("model") or "")[:240] if isinstance(payload, dict) else ""
        source = managed_internal_source_spec(api_base) or {}
        return {
            "ok": True,
            "evidence": {
                "upstreamRequestId": generation_id,
                "providerCostUsd": provider_cost,
                "httpStatus": status,
                "latencyMs": int((time.monotonic() - started) * 1000),
                "transport": "freellm",
                "sourceType": str(source.get("sourceId") or "external-free-provider"),
                "providerId": provider_id or None,
                "providerModel": provider_model or None,
                "responseModel": response_model or None,
                "upstreamKeyless": (
                    provider_id.casefold() in _KNOWN_KEYLESS_POOL_PROVIDERS
                    if provider_id
                    else None
                ),
                "textualChatResponseVerified": True,
                "rawResponsePersisted": False,
            },
        }
    except requests.Timeout as exc:
        return {
            "ok": False,
            "blocker": "freellm_timeout",
            "httpStatus": status,
            "failureFamily": "transport_timeout",
            "requestExceptionType": type(exc).__name__[:80],
        }
    except requests.RequestException as exc:
        return {
            "ok": False,
            "blocker": "freellm_upstream_unavailable",
            "httpStatus": status,
            "failureFamily": "transport_request_exception",
            "requestExceptionType": type(exc).__name__[:80],
        }
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "blocker": "freellm_canary_response_invalid",
            "httpStatus": status,
            "failureFamily": "response_decode_invalid",
            "requestExceptionType": type(exc).__name__[:80],
        }


def _confirmed_completion_canary(
    *,
    api_base: str,
    auth_mode: str,
    key: str,
    model_id: str,
) -> dict[str, Any]:
    """Require two sequential real completions before a route can become ready."""

    confirmations: list[dict[str, Any]] = []
    for confirmation_index in (1, 2):
        result = _direct_completion_canary(
            api_base=api_base,
            auth_mode=auth_mode,
            key=key,
            model_id=model_id,
        )
        if not result.get("ok"):
            return {
                "ok": False,
                "blocker": str(result.get("blocker") or "free_provider_canary_failed"),
                "failedConfirmation": confirmation_index,
                "confirmationCount": len(confirmations),
                "httpStatus": result.get("httpStatus"),
                "failureFamily": result.get("failureFamily"),
                "requestExceptionType": result.get("requestExceptionType"),
                "retryAfterSeconds": result.get("retryAfterSeconds"),
                "latencyMs": result.get("latencyMs"),
            }
        confirmations.append(dict(result.get("evidence") or {}))
    return {
        "ok": True,
        "evidence": {
            "confirmationCount": 2,
            "confirmations": confirmations,
            "upstreamRequestId": confirmations[-1].get("upstreamRequestId"),
            "providerCostUsd": confirmations[-1].get("providerCostUsd"),
            "providerCostsUsd": [item.get("providerCostUsd") for item in confirmations],
            "latencyMs": max(
                int(item.get("latencyMs") or 0) for item in confirmations
            ),
            "latenciesMs": [int(item.get("latencyMs") or 0) for item in confirmations],
            "sourceType": confirmations[-1].get("sourceType"),
            "providerId": confirmations[-1].get("providerId"),
            "providerModel": confirmations[-1].get("providerModel"),
            "responseModel": confirmations[-1].get("responseModel"),
            "upstreamKeyless": confirmations[-1].get("upstreamKeyless"),
            "textualChatResponseVerified": all(
                item.get("textualChatResponseVerified") is True
                for item in confirmations
            ),
            "rawResponsePersisted": False,
        },
    }


def _normalized_provider_cost(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed < 0:
        return None
    return parsed


def _runtime_identity() -> dict[str, Any]:
    source_revision = os.getenv("SOVEREIGN_SOURCE_REVISION", "").strip().lower()
    image_digest = os.getenv("SOVEREIGN_IMAGE_DIGEST", "").strip().lower()
    return {
        "sourceRevision": source_revision if _SOURCE_REVISION_RE.fullmatch(source_revision) else "unverified",
        "sourceRevisionVerified": bool(_SOURCE_REVISION_RE.fullmatch(source_revision)),
        "imageDigest": image_digest if _IMAGE_DIGEST_RE.fullmatch(image_digest) else "unverified",
        "imageDigestVerified": bool(_IMAGE_DIGEST_RE.fullmatch(image_digest)),
    }


def _canonical_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


_canary_failure_state = classify_freellm_canary_state


def _alias(source_id: str, model_id: str, key_fingerprint: str) -> str:
    source_slug = source_id.replace("-", "")[:10]
    model_slug = _ALIAS_RE.sub("-", model_id.lower()).strip("-")[:36] or "model"
    digest = hashlib.sha256(
        f"{source_id}\n{model_id}\n{key_fingerprint}".encode()
    ).hexdigest()[:12]
    return f"revolver-{source_slug}-{model_slug}-{digest}"[:100]


def _request_owner_input(
    get_connection: Callable[[], Any],
    *,
    source_id: str,
    label: str,
) -> str:
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT owner_request_id::text
                   FROM llm_revolver_provider_sources
                   WHERE id=%s::uuid
                   FOR UPDATE""",
                (source_id,),
            )
            source = cursor.fetchone()
            if not source:
                raise RuntimeError("free_revolver_source_missing")
            previous_request_id = str(source.get("owner_request_id") or "")
            if previous_request_id:
                cursor.execute(
                    """UPDATE owner_input_requests
                       SET status='expired', resolved_at=NOW(), result_code='superseded'
                       WHERE id=%s::uuid
                         AND target_id='revolver_provider_key'
                         AND status IN ('pending','processing')""",
                    (previous_request_id,),
                )
            cursor.execute(
                """INSERT INTO owner_input_requests
                       (target_id, title, reason, field_label, expires_at)
                   VALUES ('revolver_provider_key', %s, %s, 'Free-Provider API-Key',
                           NOW() + INTERVAL '15 minutes')
                   RETURNING id::text""",
                (
                    f"Free-Revolver-Zugang für {label}",
                    "Einmalige geschützte Eingabe für Models-Discovery, Quotenprüfung und direkte FreeLLM-Aktivierung.",
                ),
            )
            request_id = str(cursor.fetchone()["id"])
            cursor.execute(
                """UPDATE llm_revolver_provider_sources
                   SET owner_request_id=%s::uuid, status='awaiting_owner_input',
                       last_error_code=NULL, updated_at=NOW()
                   WHERE id=%s::uuid""",
                (request_id, source_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("free_revolver_source_missing")
        connection.commit()
        return request_id
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _source_payload(source: dict[str, Any], models: list[dict[str, Any]]) -> dict[str, Any]:
    managed_source = managed_internal_source_spec(source.get("api_base")) or {}
    return {
        "id": str(source.get("id") or ""),
        "sourceType": str(managed_source.get("sourceId") or "external-free-provider"),
        "label": str(source.get("label") or ""),
        "apiBase": str(source.get("api_base") or ""),
        "modelsUrl": source.get("models_url"),
        "authMode": str(source.get("auth_mode") or "bearer"),
        "keyHint": source.get("key_hint"),
        "status": str(source.get("status") or "blocked"),
        "lastHttpStatus": source.get("last_http_status"),
        "lastErrorCode": source.get("last_error_code"),
        "lastDiscoveredAt": source.get("last_discovered_at").isoformat() if source.get("last_discovered_at") else None,
        "lastCheckedAt": source.get("last_checked_at").isoformat() if source.get("last_checked_at") else None,
        "enabled": bool(source.get("enabled")),
        "ownerRequestId": str(source.get("owner_request_id") or "") or None,
        "models": [{
            "id": str(model.get("id") or ""),
            "modelId": str(model.get("upstream_model_id") or ""),
            "displayName": str(model.get("display_name") or ""),
            "routeAlias": model.get("litellm_alias"),
            "routeId": str(model.get("route_id") or "") or None,
            "runtimeIdentity": model.get("runtime_identity") or {},
            "canaryReceipt": model.get("canary_receipt") or {},
            "quotaEvidence": model.get("quota_evidence") or {},
            "retryEvidence": model.get("retry_evidence") or {},
            "cooldownEvidence": model.get("cooldown_evidence") or {},
            "capabilities": model.get("capabilities") or [],
            "freeEligible": bool(model.get("free_eligible")),
            "eligibilitySource": str(model.get("eligibility_source") or "unverified"),
            "eligibilityVerifiedAt": model.get("eligibility_verified_at").isoformat() if model.get("eligibility_verified_at") else None,
            "generalChatBlocker": (
                _verified_general_chat_block_source(model.get("eligibility_source"))
                if str(model.get("status") or "") == "blocked"
                and model.get("eligibility_verified_at")
                else None
            ),
            "generalChatBlockVerified": bool(
                str(model.get("status") or "") == "blocked"
                and model.get("eligibility_verified_at")
                and _verified_general_chat_block_source(model.get("eligibility_source"))
            ),
            "status": str(model.get("status") or "discovered"),
            "lastCanaryRequestId": model.get("last_canary_request_id"),
            "lastCanaryAt": model.get("last_canary_at").isoformat() if model.get("last_canary_at") else None,
            "providerCostState": str(model.get("canary_cost_state") or "unreported"),
            "lastProviderCostUsdMicros": model.get("last_provider_cost_usd_micros"),
            "lastErrorCode": model.get("last_error_code"),
            "enabled": bool(model.get("enabled")),
        } for model in models],
    }


def _freellm_provider_credential_state(provider_id: str) -> dict[str, Any]:
    spec = FREELLM_PROVIDER_SPECS[provider_id]
    root = _owner_root()
    secret_directory = provider_secret_path(root, provider_id).parent
    try:
        directory_info = secret_directory.lstat()
    except FileNotFoundError:
        directory_info = None
    if directory_info is not None and (
        not stat.S_ISDIR(directory_info.st_mode)
        or secret_directory.is_symlink()
        or stat.S_IMODE(directory_info.st_mode) & 0o077
    ):
        return {
            "configured": False,
            "mode": "keyless" if bool(spec.get("keyless")) else "credential-pool",
            "keyCount": 0,
            "fingerprintSha256": None,
            "permissionsValid": False,
        }
    if bool(spec.get("keyless")):
        marker = provider_keyless_marker_path(root, provider_id)
        enabled = marker.is_file() and not marker.is_symlink()
        return {
            "configured": enabled,
            "mode": "keyless",
            "keyCount": 1 if enabled else 0,
            "fingerprintSha256": None,
            "permissionsValid": enabled and stat.S_IMODE(marker.stat().st_mode) & 0o077 == 0,
        }
    fingerprints: list[str] = []
    permissions_valid = True
    for path in provider_secret_paths(root, provider_id):
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        valid = (
            stat.S_ISREG(info.st_mode)
            and not path.is_symlink()
            and not (stat.S_IMODE(info.st_mode) & 0o077)
            and 1 <= info.st_size <= 8192
        )
        permissions_valid = permissions_valid and valid
        if not valid:
            continue
        protected = bytearray(path.read_bytes())
        try:
            fingerprints.append(hashlib.sha256(bytes(protected).strip()).hexdigest())
        finally:
            for index in range(len(protected)):
                protected[index] = 0
    fingerprints = sorted(set(fingerprints))
    return {
        "configured": bool(fingerprints) and permissions_valid,
        "mode": "credential-pool",
        "keyCount": len(fingerprints),
        "fingerprintSha256": fingerprints[0] if len(fingerprints) == 1 else None,
        "permissionsValid": permissions_valid if fingerprints else None,
    }


def _prepare_freellm_secret_directory(directory: Path, owner_blocker: str) -> None:
    if os.geteuid() != 0:
        raise OSError(owner_blocker)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(str(directory), flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode):
            raise OSError("freellm_secret_directory_invalid")
        os.fchown(descriptor, FREELLM_RUNTIME_UID, FREELLM_RUNTIME_GID)
        os.fchmod(descriptor, 0o700)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_keyless_marker(provider_id: str, enabled: bool) -> None:
    path = provider_keyless_marker_path(_owner_root(), provider_id)
    if not enabled:
        raise ValueError("freellm_keyless_disable_requires_provider_runtime_support")
    _prepare_freellm_secret_directory(
        path.parent,
        "freellm_keyless_marker_owner_change_requires_root",
    )
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(descriptor, b"enabled\n")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
        os.chown(path, FREELLM_RUNTIME_UID, FREELLM_RUNTIME_GID)
        os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _write_freellm_provider_key(provider_id: str, protected: bytearray) -> str:
    """Append one hash-addressed key to the owner-managed FreeLLM provider pool."""
    provider_id = normalize_freellm_provider_id(provider_id)
    if bool(FREELLM_PROVIDER_SPECS[provider_id].get("keyless")):
        raise ValueError("freellm_provider_is_keyless")
    start = 0
    end = len(protected)
    while start < end and protected[start] in b" \t\r\n":
        start += 1
    while end > start and protected[end - 1] in b" \t\r\n":
        end -= 1
    if end - start < 8 or end - start > 8192:
        raise ValueError("freellm_provider_key_invalid")
    view = memoryview(protected)[start:end]
    fingerprint = hashlib.sha256(view).hexdigest()
    path = provider_secret_pool_path(_owner_root(), provider_id, fingerprint)
    _prepare_freellm_secret_directory(
        path.parent,
        "freellm_provider_key_owner_change_requires_root",
    )
    if path.exists():
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or path.is_symlink() or stat.S_IMODE(info.st_mode) & 0o077:
            raise OSError("freellm_provider_key_existing_path_invalid")
        existing = bytearray(path.read_bytes())
        try:
            if hashlib.sha256(bytes(existing).strip()).hexdigest() != fingerprint:
                raise OSError("freellm_provider_key_existing_fingerprint_mismatch")
        finally:
            for index in range(len(existing)):
                existing[index] = 0
        return fingerprint
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            written = 0
            while written < len(view):
                written += os.write(descriptor, view[written:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
        os.chown(path, FREELLM_RUNTIME_UID, FREELLM_RUNTIME_GID)
        os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)
    return fingerprint


def _verified_general_chat_block_source(value: Any) -> str | None:
    source = str(value or "").strip()
    return source if source in _VERIFIED_GENERAL_CHAT_BLOCKERS else None


def _revision_bound_ready_model_ids(
    query: Callable[..., Any],
    *,
    source_id: str,
    runtime_identity: dict[str, Any],
) -> set[str]:
    """Return currently certified routes that discovery must not demote."""
    if not (
        runtime_identity.get("sourceRevisionVerified") is True
        and runtime_identity.get("imageDigestVerified") is True
    ):
        return set()
    rows = query(
        """SELECT model.upstream_model_id
           FROM llm_revolver_provider_models AS model
           JOIN llm_routes AS route
             ON route.model_id=model.litellm_alias
            AND route.config->>'revolverProviderSourceId'=%s
           WHERE model.source_id=%s::uuid
             AND model.status='ready'
             AND model.enabled=true
             AND model.free_eligible=true
             AND model.eligibility_verified_at IS NOT NULL
             AND model.eligibility_verified_at >= NOW() - (%s * INTERVAL '1 hour')
             AND model.last_canary_at IS NOT NULL
             AND model.last_canary_at >= NOW() - (%s * INTERVAL '1 hour')
             AND route.disabled=false
             AND route.config->'runtimeIdentity'->>'sourceRevision'=%s
             AND route.config->'runtimeIdentity'->>'imageDigest'=%s
             AND route.config->'runtimeIdentity'->>'sourceRevisionVerified'='true'
             AND route.config->'runtimeIdentity'->>'imageDigestVerified'='true'
             AND route.config->'canaryReceipt'->>'schemaVersion'=%s
             AND route.config->'canaryReceipt'->>'generalChatEvidenceVerified'='true'
             AND route.config->'canaryReceipt'->>'receiptSha256' ~ '^[0-9a-f]{64}$'""",
        (
            source_id,
            source_id,
            _eligibility_evidence_ttl_hours(),
            _eligibility_evidence_ttl_hours(),
            runtime_identity["sourceRevision"],
            runtime_identity["imageDigest"],
            _FREELLM_RECEIPT_SCHEMA,
        ),
    ) or []
    return {
        str(row.get("upstream_model_id") or "")
        for row in rows
        if str(row.get("upstream_model_id") or "")
    }


def _persist_verified_general_chat_blocks(
    get_connection: Callable[[], Any],
    *,
    source_id: str,
    models: list[dict[str, Any]],
) -> None:
    """Persist definitive chat incompatibility as verified blocker evidence."""
    blocked = [
        model
        for model in models
        if bool(model.get("generalChatBlockVerified"))
    ]
    if not blocked:
        return
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            for model in blocked:
                blocker = _verified_general_chat_block_source(
                    model.get("generalChatEligibilitySource")
                )
                if blocker is None:
                    raise RuntimeError("free_revolver_chat_block_reason_invalid")
                cursor.execute(
                    """UPDATE llm_revolver_provider_models
                       SET free_eligible=false, status='blocked', enabled=false,
                           eligibility_source=%s, eligibility_verified_at=NOW(),
                           last_error_code=%s, updated_at=NOW()
                       WHERE source_id=%s::uuid AND upstream_model_id=%s""",
                    (blocker, blocker, source_id, str(model["modelId"])),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("free_revolver_chat_block_evidence_missing")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _blocked_general_chat_evidence(
    query: Callable[..., Any],
    source_id: str,
) -> list[dict[str, Any]]:
    rows = query(
        """SELECT upstream_model_id, eligibility_source,
                  eligibility_verified_at, last_error_code
           FROM llm_revolver_provider_models
           WHERE source_id=%s::uuid
             AND status='blocked'
             AND free_eligible=false
             AND eligibility_verified_at IS NOT NULL
             AND eligibility_source = ANY(%s)
           ORDER BY display_name ASC
           LIMIT 20""",
        (source_id, sorted(_VERIFIED_GENERAL_CHAT_BLOCKERS)),
    ) or []
    return [{
        "modelId": str(row.get("upstream_model_id") or ""),
        "generalChatEligible": False,
        "generalChatBlockVerified": True,
        "generalChatEligibilitySource": str(
            row.get("eligibility_source") or "general-chat-incompatible"
        ),
        "eligibilityVerifiedAt": (
            row["eligibility_verified_at"].isoformat()
            if row.get("eligibility_verified_at") else None
        ),
        "lastErrorCode": str(row.get("last_error_code") or "") or None,
    } for row in rows]


class _FreeLlmEvidenceMaintainer:
    """Keep managed FreeLLM route evidence fresh without blocking user requests."""

    def __init__(self, get_connection: Callable[[], Any]) -> None:
        self._get_connection = get_connection
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._state_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._force_discovery = False

    @staticmethod
    def _enabled() -> bool:
        return os.getenv(
            "SOVEREIGN_FREELLM_EVIDENCE_MAINTAINER_ENABLED",
            "0",
        ).strip() == "1"

    def request_maintenance(self, *, force_discovery: bool = False) -> None:
        if force_discovery:
            with self._state_lock:
                self._force_discovery = True
        self._wake.set()

    def _consume_force_discovery(self) -> bool:
        with self._state_lock:
            value = self._force_discovery
            self._force_discovery = False
            return value

    @staticmethod
    def _request_json(
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        timeout_seconds: int = 120,
    ) -> tuple[int, dict[str, Any]]:
        owner_key = os.getenv("SOVEREIGN_OWNER_REQUEST_KEY", "").strip()
        if not owner_key:
            raise RuntimeError("freellm_evidence_maintainer_owner_key_missing")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Sovereign-Owner-Request-Key": owner_key,
        }
        with requests.Session() as session:
            session.trust_env = False
            response = session.request(
                method,
                f"http://127.0.0.1:8787{path}",
                headers=headers,
                json=payload,
                timeout=max(5, min(int(timeout_seconds), 120)),
                allow_redirects=False,
            )
            if len(response.content) > _MAX_MODELS_RESPONSE_BYTES:
                raise ValueError("freellm_evidence_maintainer_response_too_large")
            try:
                decoded = response.json()
            except ValueError as exc:
                raise ValueError("freellm_evidence_maintainer_invalid_json") from exc
        if not isinstance(decoded, dict):
            raise ValueError("freellm_evidence_maintainer_invalid_payload")
        return int(response.status_code), decoded

    def _run_provider(self, source_id: str, *, force_discovery: bool) -> None:
        max_models = _bounded_maintenance_env_int(
            "SOVEREIGN_FREELLM_EVIDENCE_MAINTAINER_MAX_MODELS",
            _DEFAULT_EVIDENCE_MAINTENANCE_MAX_MODELS,
            1,
            100,
        )
        max_rounds = _bounded_maintenance_env_int(
            "SOVEREIGN_FREELLM_EVIDENCE_MAINTAINER_MAX_ROUNDS",
            _DEFAULT_EVIDENCE_MAINTENANCE_MAX_ROUNDS,
            1,
            20,
        )
        encoded_source_id = normalize_provider_source_id(source_id)
        if force_discovery:
            self._request_json(
                f"/api/internal/llm/freellm/providers/{encoded_source_id}/discover",
                method="POST",
                payload={"maxModels": max_models},
                timeout_seconds=120,
            )
        previous_attempt_signature: tuple[str, ...] | None = None
        for _round in range(max_rounds):
            status_code, result = self._request_json(
                f"/api/internal/llm/freellm/providers/{encoded_source_id}/reconcile",
                method="POST",
                payload={"maxModels": max_models},
                timeout_seconds=120,
            )
            blocker = str(result.get("blocker") or "")
            if status_code == 409 and blocker == "freellm_fresh_catalog_required":
                self._request_json(
                    f"/api/internal/llm/freellm/providers/{encoded_source_id}/discover",
                    method="POST",
                    payload={"maxModels": max_models},
                    timeout_seconds=120,
                )
                previous_attempt_signature = None
                continue
            if status_code not in {200, 409}:
                return
            attempted = []
            for field in ("ready", "deferred", "blocked"):
                values = result.get(field)
                if not isinstance(values, list):
                    continue
                attempted.extend(
                    str(item.get("modelId") or "")
                    for item in values
                    if isinstance(item, dict) and str(item.get("modelId") or "")
                )
            if not attempted:
                return
            signature = tuple(sorted(set(attempted)))
            if signature == previous_attempt_signature:
                return
            previous_attempt_signature = signature

    def run_once(self, *, force_discovery: bool = False) -> bool:
        if not self._enabled():
            return False
        lease_connection = self._get_connection()
        acquired = False
        try:
            with lease_connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_try_advisory_lock(%s,%s) AS acquired",
                    _EVIDENCE_MAINTENANCE_ADVISORY_LOCK,
                )
                row = cursor.fetchone() or {}
                acquired = bool(row.get("acquired"))
            if not acquired:
                return False
            status_code, payload = self._request_json(
                "/api/internal/llm/freellm/providers",
                timeout_seconds=30,
            )
            if status_code != 200 or payload.get("ok") is not True:
                return False
            providers = payload.get("providers")
            if not isinstance(providers, list):
                return False
            for provider in providers:
                if not isinstance(provider, dict):
                    continue
                source_id = str(provider.get("sourceId") or "")
                if (
                    not source_id
                    or provider.get("enabled") is not True
                    or provider.get("managedKeyAvailable") is not True
                ):
                    continue
                self._run_provider(source_id, force_discovery=force_discovery)
            return True
        except (OSError, RuntimeError, ValueError, requests.RequestException):
            return False
        finally:
            if acquired:
                try:
                    with lease_connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT pg_advisory_unlock(%s,%s)",
                            _EVIDENCE_MAINTENANCE_ADVISORY_LOCK,
                        )
                except Exception:
                    pass
            lease_connection.close()

    def _run_loop(self) -> None:
        initial_delay = _bounded_maintenance_env_int(
            "SOVEREIGN_FREELLM_EVIDENCE_MAINTAINER_INITIAL_DELAY_SECONDS",
            _DEFAULT_EVIDENCE_MAINTENANCE_INITIAL_DELAY_SECONDS,
            0,
            600,
        )
        interval = _bounded_maintenance_env_int(
            "SOVEREIGN_FREELLM_EVIDENCE_MAINTAINER_INTERVAL_SECONDS",
            _DEFAULT_EVIDENCE_MAINTENANCE_INTERVAL_SECONDS,
            300,
            86_400,
        )
        self._wake.wait(initial_delay)
        self._wake.clear()
        while not self._stop.is_set():
            force_discovery = self._consume_force_discovery()
            self.run_once(force_discovery=force_discovery)
            if force_discovery:
                followup_seconds = _bounded_maintenance_env_int(
                    "SOVEREIGN_FREELLM_EVIDENCE_MAINTAINER_KEY_IMPORT_FOLLOWUP_SECONDS",
                    _DEFAULT_EVIDENCE_MAINTENANCE_KEY_IMPORT_FOLLOWUP_SECONDS,
                    15,
                    120,
                )
                if not self._stop.wait(followup_seconds):
                    self.run_once(force_discovery=True)
            self._wake.wait(interval)
            self._wake.clear()

    def start(self) -> bool:
        if not self._enabled():
            return False
        with self._state_lock:
            if self._thread and self._thread.is_alive():
                return False
            self._thread = threading.Thread(
                target=self._run_loop,
                daemon=True,
                name="sovereign-freellm-evidence-maintainer",
            )
            self._thread.start()
            return True


def register_free_revolver_provider_runtime(
    app: Any,
    *,
    require_admin: Callable[..., Any],
    query: Callable[..., Any],
    get_connection: Callable[[], Any],
    get_current_admin: Callable[[], dict[str, Any] | None],
    audit: Callable[..., Any],
) -> None:
    evidence_maintainer = _FreeLlmEvidenceMaintainer(get_connection)

    @app.route("/freellm-provider-keys", methods=["GET"])
    def freellm_provider_credentials_page():
        response = make_response(_FREELLM_PROVIDER_KEYS_PAGE)
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
            "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        )
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.route("/api/admin/llm/freellm/provider-credentials", methods=["GET"])
    @require_admin
    def admin_freellm_provider_credentials():
        providers = []
        for provider_id, spec in FREELLM_PROVIDER_SPECS.items():
            state = _freellm_provider_credential_state(provider_id)
            providers.append({
                "providerId": provider_id,
                "label": str(spec["label"]),
                "keyless": bool(spec.get("keyless")),
                "privacyNotice": spec.get("privacyNotice"),
                **state,
            })
        return jsonify({
            "ok": True,
            "providers": providers,
            "rawCredentialsReturned": False,
            "databaseCredentialStorage": False,
            "nextAction": "Einzelnen Provider sicher eintragen oder Keyless-Tier aktivieren.",
        })

    @app.route(
        "/api/admin/llm/freellm/provider-credentials/auto",
        methods=["POST"],
    )
    @require_admin
    def admin_auto_configure_freellm_provider_credential():
        content_length = int(request.content_length or 0)
        if content_length < 8 or content_length > 8192:
            return jsonify({
                "error": "API-Key fehlt oder überschreitet das zulässige Limit.",
                "blocker": "freellm_provider_key_invalid",
                "rawCredentialReturned": False,
            }), 400
        protected = bytearray(request.get_data(cache=False, as_text=False) or b"")
        provider_id = ""
        try:
            explicit_provider = request.headers.get("X-FreeLLM-Provider-Id", "").strip()
            if explicit_provider:
                provider_id = normalize_freellm_provider_id(explicit_provider)
            else:
                provider_id = detect_freellm_provider_id_from_key(protected)
            spec = FREELLM_PROVIDER_SPECS[provider_id]
            _write_freellm_provider_key(provider_id, protected)
            state = _freellm_provider_credential_state(provider_id)
            if not bool(state.get("configured")) or state.get("permissionsValid") is not True:
                raise OSError("freellm_provider_key_readback_failed")
            evidence_maintainer.request_maintenance(force_discovery=True)
            audit("admin_freellm_provider_key_auto_configured", provider_id, {
                "detectionMode": "explicit-fallback" if explicit_provider else "strong-key-signature",
                "rawCredentialPersistedInDatabase": False,
                "permissionsValid": True,
                "keyCount": int(state.get("keyCount") or 0),
            })
            return jsonify({
                "ok": True,
                "providerId": provider_id,
                "label": str(spec["label"]),
                "detectedAutomatically": not bool(explicit_provider),
                "configured": True,
                "permissionsValid": True,
                "keyCount": int(state.get("keyCount") or 0),
                "runtimeImportPending": True,
                "nextAction": "FreeLLM übernimmt den Key automatisch; anschließend stehen erkannte Modelle im Revolver-Katalog bereit.",
                "rawCredentialReturned": False,
                "databaseCredentialStorage": False,
            }), 201
        except ValueError as exc:
            blocker = str(exc)[:120]
            status = 422 if blocker == "freellm_provider_key_unrecognized" else 400
            return jsonify({
                "error": (
                    "Provider konnte nicht eindeutig aus dem Key erkannt werden."
                    if blocker == "freellm_provider_key_unrecognized"
                    else "Provider-Key konnte nicht sicher verarbeitet werden."
                ),
                "blocker": blocker,
                "providerSelectionRequired": blocker == "freellm_provider_key_unrecognized",
                "providers": [
                    {"providerId": item_id, "label": str(item["label"])}
                    for item_id, item in FREELLM_PROVIDER_SPECS.items()
                    if not bool(item.get("keyless"))
                ] if blocker == "freellm_provider_key_unrecognized" else [],
                "rawCredentialReturned": False,
            }), status
        except OSError:
            return jsonify({
                "error": "Provider-Key konnte nicht sicher owner-managed gespeichert werden.",
                "blocker": "freellm_provider_key_write_failed",
                "providerId": provider_id or None,
                "rawCredentialReturned": False,
            }), 500
        finally:
            for index in range(len(protected)):
                protected[index] = 0

    @app.route(
        "/api/admin/llm/freellm/provider-credentials/<provider_id>/owner-input",
        methods=["POST"],
    )
    @require_admin
    def admin_prepare_freellm_provider_credential(provider_id: str):
        try:
            provider_id = normalize_freellm_provider_id(provider_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        spec = FREELLM_PROVIDER_SPECS[provider_id]
        if bool(spec.get("keyless")):
            return jsonify({
                "error": "Dieser Provider kann ohne Key aktiviert werden.",
                "blocker": "freellm_provider_is_keyless",
            }), 409
        target_id = provider_target_id(provider_id)
        connection = get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE owner_input_requests
                       SET status='expired', resolved_at=NOW(), result_code='superseded'
                       WHERE target_id=%s AND status IN ('pending','processing')""",
                    (target_id,),
                )
                cursor.execute(
                    """INSERT INTO owner_input_requests
                           (target_id, title, reason, field_label, expires_at)
                       VALUES (%s,%s,%s,%s,NOW() + INTERVAL '15 minutes')
                       RETURNING id::text""",
                    (
                        target_id,
                        f"FreeLLMAPI-Zugang für {spec['label']}",
                        "Der Key wird ausschließlich als geschützte 0600-Datei gespeichert und von FreeLLMAPI verschlüsselt importiert.",
                        f"{spec['label']} API-Key",
                    ),
                )
                request_id = str(cursor.fetchone()["id"])
            connection.commit()
        except Exception:
            connection.rollback()
            return jsonify({
                "error": "Geschützte Provider-Key-Eingabe konnte nicht vorbereitet werden.",
                "blocker": "freellm_provider_owner_input_prepare_failed",
            }), 500
        finally:
            connection.close()
        audit("admin_freellm_provider_owner_input_prepared", provider_id, {
            "targetId": target_id,
            "rawCredentialPersistedInDatabase": False,
        })
        return jsonify({
            "ok": True,
            "providerId": provider_id,
            "ownerRequestId": request_id,
            "ownerUrl": f"/owner-approvals?request_id={request_id}",
            "rawCredentialReturned": False,
        }), 201

    @app.route(
        "/api/admin/llm/freellm/provider-credentials/<provider_id>/keyless",
        methods=["POST"],
    )
    @require_admin
    def admin_toggle_freellm_keyless_provider(provider_id: str):
        try:
            provider_id = normalize_freellm_provider_id(provider_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        spec = FREELLM_PROVIDER_SPECS[provider_id]
        if not bool(spec.get("keyless")):
            return jsonify({
                "error": "Dieser Provider benötigt einen eigenen API-Key.",
                "blocker": "freellm_provider_key_required",
            }), 409
        body = request.get_json(silent=True) or {}
        enabled = bool(body.get("enabled", True))
        if not enabled:
            return jsonify({
                "error": "Keyless-Deaktivierung benötigt einen bestätigten FreeLLM-Runtime-Delete-Pfad.",
                "blocker": "freellm_keyless_disable_not_supported",
            }), 409
        try:
            _write_keyless_marker(provider_id, enabled)
        except (OSError, ValueError):
            return jsonify({
                "error": "Keyless-Providerstatus konnte nicht sicher gespeichert werden.",
                "blocker": "freellm_keyless_marker_write_failed",
            }), 500
        evidence_maintainer.request_maintenance(force_discovery=True)
        audit("admin_freellm_keyless_provider_toggled", provider_id, {
            "enabled": enabled,
            "privacyNoticePresent": bool(spec.get("privacyNotice")),
        })
        return jsonify({
            "ok": True,
            "providerId": provider_id,
            "enabled": enabled,
            "privacyNotice": spec.get("privacyNotice"),
            "rawCredentialReturned": False,
        })

    @app.route(
        "/api/internal/llm/freellm/provider-credentials/<provider_id>/keyless",
        methods=["POST"],
    )
    def internal_activate_freellm_keyless_provider(provider_id: str):
        if not _internal_owner_authorized():
            return jsonify({
                "error": "forbidden",
                "protectedValuesReturned": False,
            }), 403
        try:
            provider_id = normalize_freellm_provider_id(provider_id)
        except ValueError as exc:
            return jsonify({
                "error": str(exc),
                "protectedValuesReturned": False,
            }), 409
        spec = FREELLM_PROVIDER_SPECS[provider_id]
        if not bool(spec.get("keyless")):
            return jsonify({
                "error": "Dieser Provider benötigt einen eigenen API-Key.",
                "blocker": "freellm_provider_key_required",
                "providerId": provider_id,
                "protectedValuesReturned": False,
            }), 409
        body = request.get_json(silent=True) or {}
        if body.get("enabled", True) is not True:
            return jsonify({
                "error": "Keyless-Deaktivierung ist über diesen bounded Toolpfad nicht erlaubt.",
                "blocker": "freellm_keyless_disable_not_supported",
                "providerId": provider_id,
                "protectedValuesReturned": False,
            }), 409
        try:
            _write_keyless_marker(provider_id, True)
            state = _freellm_provider_credential_state(provider_id)
        except (OSError, ValueError):
            return jsonify({
                "error": "Keyless-Providerstatus konnte nicht sicher gespeichert werden.",
                "blocker": "freellm_keyless_marker_write_failed",
                "providerId": provider_id,
                "protectedValuesReturned": False,
            }), 500
        evidence_maintainer.request_maintenance(force_discovery=True)
        audit("internal_freellm_keyless_provider_activated", provider_id, {
            "enabled": True,
            "privacyNoticePresent": bool(spec.get("privacyNotice")),
            "rawCredentialPersistedInDatabase": False,
        })
        return jsonify({
            "ok": bool(state.get("configured")) and bool(state.get("permissionsValid")),
            "status": "FREELLM_KEYLESS_MARKER_CONFIGURED",
            "providerId": provider_id,
            "configured": bool(state.get("configured")),
            "permissionsValid": state.get("permissionsValid"),
            "privacyNotice": spec.get("privacyNotice"),
            "runtimeImportPending": True,
            "routeReady": False,
            "nextAction": "FreeLLMAPI-Import abwarten und anschließend Managed-Discovery mit Doppel-Canary ausführen.",
            "rawCredentialReturned": False,
            "protectedValuesReturned": False,
        }), 200

    @app.route("/api/admin/llm/revolver-v3/providers", methods=["GET"])
    @require_admin
    def admin_free_revolver_providers():
        orphaned_secret_files_removed = _cleanup_orphaned_secret_files(query)
        sources = query(
            """SELECT id::text, label, api_base, models_url, auth_mode,
                      owner_request_id::text, key_hint, status, last_http_status,
                      last_error_code, last_discovered_at, last_checked_at, enabled
               FROM llm_revolver_provider_sources
               ORDER BY created_at DESC"""
        ) or []
        result = []
        for source in sources:
            models = query(
                """SELECT id::text, upstream_model_id, display_name, litellm_alias,
                          capabilities, free_eligible, eligibility_source,
                          eligibility_verified_at, status,
                          last_canary_request_id, last_canary_at, canary_cost_state,
                          last_provider_cost_usd_micros, last_error_code, enabled,
                          (SELECT route.id::text FROM llm_routes AS route
                           WHERE route.model_id=llm_revolver_provider_models.litellm_alias
                           LIMIT 1) AS route_id,
                          (SELECT route.config->'runtimeIdentity' FROM llm_routes AS route
                           WHERE route.model_id=llm_revolver_provider_models.litellm_alias
                           LIMIT 1) AS runtime_identity,
                          (SELECT route.config->'canaryReceipt' FROM llm_routes AS route
                           WHERE route.model_id=llm_revolver_provider_models.litellm_alias
                           LIMIT 1) AS canary_receipt,
                          (SELECT route.config->'quotaEvidence' FROM llm_routes AS route
                           WHERE route.model_id=llm_revolver_provider_models.litellm_alias
                           LIMIT 1) AS quota_evidence,
                          (SELECT route.config->'retryEvidence' FROM llm_routes AS route
                           WHERE route.model_id=llm_revolver_provider_models.litellm_alias
                           LIMIT 1) AS retry_evidence,
                          (SELECT route.config->'cooldownEvidence' FROM llm_routes AS route
                           WHERE route.model_id=llm_revolver_provider_models.litellm_alias
                           LIMIT 1) AS cooldown_evidence
                   FROM llm_revolver_provider_models
                   WHERE source_id=%s::uuid
                   ORDER BY free_eligible DESC, display_name ASC""",
                (source["id"],),
            ) or []
            result.append(_source_payload(dict(source), [dict(row) for row in models]))
        return jsonify({
            "ok": True,
            "schemaVersion": "sovereign.free-revolver-provider-admin.v1",
            "truthOwner": "postgresql-owner-input-direct-freellm",
            "providers": result,
            "keyStorage": "owner-managed-direct-freellm",
            "activationRule": "managed-free-quota-plus-revision-bound-double-canary-without-positive-cost-contradiction",
            "orphanedSecretFilesRemoved": orphaned_secret_files_removed,
        })

    @app.route("/api/admin/llm/revolver-v3/providers", methods=["POST"])
    @require_admin
    def admin_create_free_revolver_provider():
        body = request.get_json(force=True) or {}
        label = str(body.get("label") or "").strip()[:120]
        auth_mode = str(body.get("authMode") or "bearer").strip().lower()
        if not label:
            return jsonify({"error": "Provider-Name fehlt"}), 400
        if auth_mode not in _AUTH_MODES:
            return jsonify({"error": "authMode muss bearer, x-api-key, none oder managed-bearer sein"}), 400
        try:
            api_base = normalize_api_base(body.get("apiBase"))
            assert_provider_target_allowed(api_base)
            managed_target = is_managed_internal_provider_url(api_base)
            if (auth_mode == _MANAGED_AUTH_MODE) != managed_target:
                raise ValueError(
                    "managed-bearer ist ausschließlich für den verwalteten FreeLLM-API-Docker-Endpunkt erlaubt"
                )
        except ValueError as exc:
            return jsonify({"error": str(exc), "blocker": "free_provider_url_invalid"}), 400
        existing = query(
            "SELECT id::text FROM llm_revolver_provider_sources WHERE lower(api_base)=lower(%s) LIMIT 1",
            (api_base,), one=True,
        )
        if existing:
            return jsonify({
                "error": "Diese API-Basis ist bereits eingetragen. Nutze die vorhandene Providerkarte für Discovery oder Healthcheck.",
                "blocker": "free_provider_api_base_already_registered",
                "sourceId": existing["id"],
                "nextAction": "use_existing_provider",
            }), 409
        admin = get_current_admin() or {}
        source = query(
            """INSERT INTO llm_revolver_provider_sources
                   (label, api_base, auth_mode, status, created_by)
               VALUES (%s,%s,%s,%s,%s::uuid)
               RETURNING id::text""",
            (
                label,
                api_base,
                auth_mode,
                "degraded" if auth_mode in {"none", _MANAGED_AUTH_MODE} else "awaiting_owner_input",
                str(admin.get("id") or ""),
            ),
            one=True, write=True,
        )
        source_id = str(source["id"])
        request_id = None
        if auth_mode in {"bearer", "x-api-key"}:
            try:
                request_id = _request_owner_input(get_connection, source_id=source_id, label=label)
            except Exception:
                query("DELETE FROM llm_revolver_provider_sources WHERE id=%s::uuid", (source_id,), write=True)
                return jsonify({"error": "Geschützte Key-Eingabe konnte nicht vorbereitet werden"}), 500
        audit("admin_free_revolver_provider_created", source_id, {
            "label": label, "apiBase": api_base, "authMode": auth_mode,
        })
        return jsonify({
            "ok": True,
            "sourceId": source_id,
            "ownerRequestId": request_id,
            "ownerUrl": f"/owner-approvals?request_id={request_id}" if request_id else None,
            "nextAction": (
                "Discovery starten; diese API benötigt keinen Key."
                if auth_mode == "none"
                else "Discovery starten; der interne FreeLLM-Schlüssel bleibt owner-managed."
                if auth_mode == _MANAGED_AUTH_MODE
                else "API-Key sicher eintragen und danach Discovery starten."
            ),
        }), 201

    @app.route("/api/admin/llm/revolver-v3/providers/<source_id>/owner-input", methods=["POST"])
    @require_admin
    def admin_refresh_free_revolver_provider_key(source_id: str):
        try:
            source_id = normalize_provider_source_id(source_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        source = query(
            "SELECT id::text, label FROM llm_revolver_provider_sources WHERE id=%s::uuid LIMIT 1",
            (source_id,), one=True,
        )
        if not source:
            return jsonify({"error": "Free-Provider nicht gefunden"}), 404
        auth = query(
            "SELECT auth_mode FROM llm_revolver_provider_sources WHERE id=%s::uuid LIMIT 1",
            (source_id,), one=True,
        ) or {}
        if str(auth.get("auth_mode") or "") in {"none", _MANAGED_AUTH_MODE}:
            return jsonify({"error": "Dieser Provider verwendet keinen erneuerbaren Owner-Input-Key"}), 409
        try:
            request_id = _request_owner_input(
                get_connection,
                source_id=source_id,
                label=str(source["label"]),
            )
        except Exception:
            return jsonify({"error": "Neue geschützte Key-Eingabe konnte nicht vorbereitet werden"}), 500
        return jsonify({
            "ok": True,
            "sourceId": source_id,
            "ownerRequestId": request_id,
            "ownerUrl": f"/owner-approvals?request_id={request_id}",
        }), 201

    def persist_check(
        source_id: str,
        *,
        check_kind: str,
        models_url: str | None,
        http_status: int | None,
        outcome: str,
        model_count: int,
        free_count: int,
        evidence: dict[str, Any],
    ) -> None:
        query(
            """INSERT INTO llm_revolver_provider_checks
                   (source_id, check_kind, models_url, http_status, outcome,
                    model_count, free_model_count, evidence)
               VALUES (%s::uuid,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
            (
                source_id, check_kind, models_url, http_status, outcome,
                model_count, free_count, json.dumps(evidence, ensure_ascii=False),
            ),
            write=True,
        )

    def activate_model(source: dict[str, Any], model: dict[str, Any], key: str) -> dict[str, Any]:
        source_id = str(source["id"])
        model_id = str(model["modelId"])
        alias = _alias(
            source_id,
            model_id,
            str(source.get("key_fingerprint") or ""),
        )
        if is_specialist_model_identifier(model_id):
            return {
                "ok": False,
                "alias": alias,
                "error": "free_provider_model_not_general_chat_compatible",
                "blocker": "freellm_model_not_general_chat_compatible",
                "failureFamily": "specialist_model_identifier",
            }
        if (
            str(source.get("auth_mode") or "") != _MANAGED_AUTH_MODE
            or not is_managed_internal_provider_url(str(source.get("api_base") or ""))
        ):
            return {
                "ok": False,
                "alias": alias,
                "error": "free_direct_runtime_credentials_unavailable",
            }
        canary = _confirmed_completion_canary(
            api_base=str(source["api_base"]),
            auth_mode=str(source["auth_mode"]),
            key=key,
            model_id=model_id,
        )
        if not canary.get("ok"):
            return {
                "ok": False,
                "alias": alias,
                "error": "free_provider_canary_failed",
                "blocker": str(canary.get("blocker") or "free_provider_canary_failed"),
                "failedConfirmation": canary.get("failedConfirmation"),
                "confirmationCount": canary.get("confirmationCount"),
                "httpStatus": canary.get("httpStatus"),
                "failureFamily": canary.get("failureFamily"),
                "requestExceptionType": canary.get("requestExceptionType"),
                "retryAfterSeconds": canary.get("retryAfterSeconds"),
                "latencyMs": canary.get("latencyMs"),
            }
        evidence = dict(canary.get("evidence") or {})
        if evidence.get("textualChatResponseVerified") is not True:
            return {
                "ok": False,
                "alias": alias,
                "error": "free_provider_general_chat_evidence_missing",
                "blocker": "freellm_general_chat_canary_failed",
            }
        activation_eligibility_source = (
            "managed-freellm-chat-canary-verified"
            if bool(model.get("generalChatCanaryRequired"))
            else str(model.get("eligibilitySource") or "unverified")
        )
        raw_costs = evidence.get("providerCostsUsd")
        if not isinstance(raw_costs, list) or len(raw_costs) != 2:
            return {
                "ok": False,
                "alias": alias,
                "error": "free_provider_confirmation_evidence_invalid",
                "blocker": "freellm_double_canary_evidence_missing",
            }
        provider_costs = [_normalized_provider_cost(value) for value in raw_costs]
        if any(value not in (None, 0, 0.0) for value in provider_costs):
            return {
                "ok": False,
                "alias": alias,
                "error": "free_provider_cost_not_zero",
                "providerCostState": "nonzero",
            }
        provider_cost = provider_costs[-1]
        canary_cost_state = (
            "zero"
            if all(value in (0, 0.0) for value in provider_costs)
            else "unreported"
        )
        provider_cost_micros = (
            int(round(float(provider_cost) * 1_000_000))
            if provider_cost is not None
            else None
        )
        route_id = str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"sovereign-free-revolver:{source_id}:{model_id}",
        ))
        quota_scope = (
            "freellm:model:"
            f"{str(source.get('key_fingerprint') or '')[:12]}:"
            f"{hashlib.sha256(model_id.encode()).hexdigest()[:12]}"
        )
        runtime_identity = _runtime_identity()
        if not (
            runtime_identity["sourceRevisionVerified"]
            and runtime_identity["imageDigestVerified"]
        ):
            return {
                "ok": False,
                "alias": alias,
                "error": "freellm_runtime_identity_unverified",
                "blocker": "freellm_revision_bound_receipt_required",
            }
        confirmation_request_ids = [
            str(item.get("upstreamRequestId") or "")
            for item in evidence.get("confirmations") or []
            if isinstance(item, dict) and str(item.get("upstreamRequestId") or "")
        ]
        quota_contract = {
            "scope": quota_scope,
            "evidence": "managed-provider-quota-and-per-model-runtime-cooldown",
            "stateOwner": "postgresql-revolver-state",
            "contractVerified": True,
            "executionProfile": "free_single_agent",
            "maxForegroundAgents": 1,
            "maxBackgroundAgents": 0,
        }
        retry_contract = {
            "candidateFailuresAreIsolated": True,
            "globalProviderFailureOnCandidateFailure": False,
            "retryableFailureFamilies": [
                "upstream_rate_limited",
                "upstream_http_timeout",
                "transport_timeout",
                "upstream_http_5xx",
                "transport_request_exception",
            ],
        }
        cooldown_contract = {
            "scope": quota_scope,
            "stateOwner": "postgresql-revolver-state",
            "reactivationRequiresFreshDoubleCanary": True,
            "failClosedOnDrift": True,
        }
        receipt_payload = {
            "schemaVersion": _FREELLM_RECEIPT_SCHEMA,
            "routeId": route_id,
            "sourceId": source_id,
            "providerEvidence": {
                "sourceType": evidence.get("sourceType"),
                "providerId": evidence.get("providerId"),
                "upstreamKeyless": evidence.get("upstreamKeyless"),
            },
            "modelEvidence": {
                "requestedModel": model_id,
                "providerModel": evidence.get("providerModel"),
                "responseModel": evidence.get("responseModel"),
            },
            "eligibilityEvidence": {
                "eligibilitySource": activation_eligibility_source,
                "generalChatEvidenceSource": (
                    "revision-bound-double-chat-canary"
                    if bool(model.get("generalChatCanaryRequired"))
                    else "explicit-catalog-capability-plus-double-chat-canary"
                ),
                "discoveryPayloadSha256": model["payloadSha256"],
                "providerCostState": canary_cost_state,
                "freeQuotaContract": (
                    "managed-provider-quota-plus-noncontradictory-double-canary"
                ),
            },
            "canaryEvidence": {
                "confirmationCount": int(evidence.get("confirmationCount") or 0),
                "requestIds": confirmation_request_ids,
                "latencyMs": int(evidence.get("latencyMs") or 0),
                "latenciesMs": [int(value or 0) for value in evidence.get("latenciesMs") or []],
                "textualChatResponsesVerified": True,
                "rawResponsesPersisted": False,
            },
            "quotaEvidence": quota_contract,
            "retryEvidence": retry_contract,
            "cooldownEvidence": cooldown_contract,
            "runtimeIdentity": runtime_identity,
        }
        receipt_sha256 = _canonical_sha256(receipt_payload)
        receipt_id = f"freellm-route:{route_id}:{receipt_sha256[:16]}"
        api_base = str(source["api_base"]).rstrip("/")
        config = {
            "routingOwner": "free-revolver-v3",
            "managedBy": "sovereign-admin",
            "revolverProviderSourceId": source_id,
            "freeSourceType": evidence.get("sourceType"),
            "transport": "freellm",
            "direct": True,
            "authMode": _MANAGED_AUTH_MODE,
            "providerModel": model_id,
            "billingCategory": "free",
            "billingClass": "free",
            "fundingMode": "provider_free_quota",
            "markupMultiplier": 0,
            "minimumMultiplier": 0,
            "providerPricingRequired": False,
            "pricingVerified": False,
            "freeEligible": True,
            "eligibilitySource": activation_eligibility_source,
            "generalChatEvidenceSource": (
                "revision-bound-double-chat-canary"
                if bool(model.get("generalChatCanaryRequired"))
                else "explicit-catalog-capability-plus-double-chat-canary"
            ),
            "quotaContractVerified": True,
            "userChargeCredits": 0,
            "providerCostState": canary_cost_state,
            "eligibilityEvidence": {
                "discoveryPayloadSha256": model["payloadSha256"],
                "providerCostState": canary_cost_state,
                "canaryRequestId": evidence.get("upstreamRequestId") or None,
                "canaryConfirmationCount": int(evidence.get("confirmationCount") or 0),
            },
            "actualUpstream": {
                "providerId": evidence.get("providerId"),
                "providerModel": evidence.get("providerModel"),
                "responseModel": evidence.get("responseModel"),
                "keyless": evidence.get("upstreamKeyless"),
            },
            "canaryVerified": True,
            "canaryConfirmationCount": int(evidence.get("confirmationCount") or 0),
            "canaryLatencyMs": int(evidence.get("latencyMs") or 0),
            "certificationState": "certified",
            "revolverEligible": True,
            "executionProfile": "free_single_agent",
            "resolverMode": "revolver",
            "maxForegroundAgents": 1,
            "maxBackgroundAgents": 0,
            "repositoryExecutionAllowed": True,
            "quotaScope": quota_scope,
            "quotaEvidence": quota_contract,
            "retryEvidence": retry_contract,
            "cooldownEvidence": cooldown_contract,
            "runtimeIdentity": runtime_identity,
            "canaryReceipt": {
                "schemaVersion": _FREELLM_RECEIPT_SCHEMA,
                "receiptId": receipt_id,
                "receiptSha256": receipt_sha256,
                "generalChatEvidenceVerified": True,
            },
            "canaryRequestId": evidence.get("upstreamRequestId") or None,
        }
        connection = get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO llm_routes
                           (id, model_id, model_name, provider, base_url, credits_per_unit,
                            disabled, priority, runtime_kind, tier, config, updated_at)
                       VALUES (%s,%s,%s,'freellm',%s,0,
                               false,50,'freellm','free',%s::jsonb,NOW())
                       ON CONFLICT (id) DO UPDATE SET
                           model_id=EXCLUDED.model_id,
                           model_name=EXCLUDED.model_name, provider='freellm',
                           base_url=EXCLUDED.base_url, credits_per_unit=0,
                           disabled=false, runtime_kind='freellm', tier='free',
                           config=EXCLUDED.config, updated_at=NOW()""",
                    (
                        route_id,
                        alias,
                        model["displayName"],
                        api_base,
                        json.dumps(config, ensure_ascii=False),
                    ),
                )
                cursor.execute(
                    """UPDATE llm_revolver_provider_models
                       SET litellm_alias=%s, status='ready', enabled=true,
                           free_eligible=true, eligibility_source=%s,
                           eligibility_verified_at=NOW(),
                           last_canary_request_id=%s, last_canary_at=NOW(),
                           canary_cost_state=%s, last_provider_cost_usd_micros=%s,
                           last_error_code=NULL, updated_at=NOW()
                       WHERE source_id=%s::uuid AND upstream_model_id=%s""",
                    (
                        alias, activation_eligibility_source,
                        str(evidence.get("upstreamRequestId") or "") or None,
                        canary_cost_state, provider_cost_micros,
                        source_id, model_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("free_revolver_model_evidence_missing")
            connection.commit()
        except Exception:
            connection.rollback()
            return {"ok": False, "alias": alias, "error": "free_route_persistence_failed"}
        finally:
            connection.close()
        return {
            "ok": True,
            "alias": alias,
            "routeId": route_id,
            "transport": "freellm",
            "sourceType": evidence.get("sourceType"),
            "providerId": evidence.get("providerId"),
            "providerModel": evidence.get("providerModel"),
            "responseModel": evidence.get("responseModel"),
            "upstreamKeyless": evidence.get("upstreamKeyless"),
            "canaryConfirmationCount": int(evidence.get("confirmationCount") or 0),
            "canaryLatencyMs": int(evidence.get("latencyMs") or 0),
            "canaryRequestId": evidence.get("upstreamRequestId") or None,
            "providerCostState": canary_cost_state,
            "runtimeIdentity": runtime_identity,
            "receiptId": receipt_id,
            "receiptSha256": receipt_sha256,
        }

    @app.route("/api/admin/llm/revolver-v3/providers/<source_id>/discover", methods=["POST"])
    @require_admin
    def admin_discover_free_revolver_provider(source_id: str):
        body = request.get_json(silent=True) or {}
        try:
            source_id = normalize_provider_source_id(source_id)
            max_auto = normalize_max_auto_activate(body.get("maxAutoActivate", 20))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        source = query(
            """SELECT id::text, label, api_base, models_url, auth_mode,
                      owner_request_id::text, key_fingerprint, key_hint, status, enabled
               FROM llm_revolver_provider_sources WHERE id=%s::uuid LIMIT 1""",
            (source_id,), one=True,
        )
        if not source:
            return jsonify({"error": "Free-Provider nicht gefunden"}), 404
        owner_request_id = str(source.get("owner_request_id") or "")
        owner_request = query(
            """SELECT status, target_id FROM owner_input_requests
               WHERE id=%s::uuid LIMIT 1""",
            (owner_request_id,), one=True,
        ) if owner_request_id else None
        if (
            source.get("auth_mode") in {"bearer", "x-api-key"}
            and (
                not owner_request
                or owner_request.get("status") != "consumed"
                or owner_request.get("target_id") != "revolver_provider_key"
            )
        ):
            return jsonify({
                "error": "Der API-Key wurde noch nicht über die geschützte Owner-Eingabe bestätigt",
                "blocker": "free_provider_owner_input_required",
                "ownerRequestId": owner_request_id or None,
            }), 409
        claimed = query(
            """UPDATE llm_revolver_provider_sources
               SET status='probing', last_error_code=NULL, updated_at=NOW()
               WHERE id=%s::uuid AND enabled=true
                 AND (
                   status IN ('awaiting_owner_input','degraded','blocked','healthy')
                   OR (status='probing' AND updated_at < NOW() - INTERVAL '5 minutes')
                 )
               RETURNING id::text""",
            (source_id,), one=True, write=True,
        )
        if not claimed:
            return jsonify({
                "error": "Provider ist deaktiviert oder eine Discovery läuft bereits. Status neu laden, bevor erneut gestartet wird.",
                "blocker": "free_provider_not_discoverable",
                "nextAction": "reload_provider_status",
            }), 409

        protected = bytearray()
        path = (
            _secret_path(owner_request_id)
            if source["auth_mode"] in {"bearer", "x-api-key"}
            else _owner_root() / ".no-key-provider"
        )
        selected_url = None
        last_status = None
        key = ""
        try:
            if source["auth_mode"] == _MANAGED_AUTH_MODE:
                protected, key = _read_managed_key(str(source["api_base"]))
            elif source["auth_mode"] != "none":
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
                    raise ValueError("free_provider_secret_permissions_invalid")
                if info.st_size < 1 or info.st_size > 8192:
                    raise ValueError("free_provider_secret_invalid")
                protected = bytearray(path.read_bytes())
                key = protected.decode("utf-8").strip()
                if len(key) < 8:
                    raise ValueError("free_provider_secret_invalid")
            key_fingerprint = hashlib.sha256(
                (key if key else f"public:{source['api_base']}").encode()
            ).hexdigest()
            key_hint = (
                "owner-managed"
                if source["auth_mode"] == _MANAGED_AUTH_MODE
                else f"…{key[-4:]}"
                if key
                else "ohne Key"
            )
            source["key_fingerprint"] = key_fingerprint
            source["key_hint"] = key_hint
            headers = _auth_headers(str(source["auth_mode"]), key)
            payload = None
            with requests.Session() as provider_session:
                provider_session.trust_env = False
                for candidate in models_url_candidates(str(source["api_base"])):
                    assert_provider_target_allowed(candidate)
                    with provider_session.get(
                        candidate,
                        headers=headers,
                        timeout=15,
                        allow_redirects=False,
                        stream=True,
                    ) as response:
                        last_status = response.status_code
                        if response.status_code in {401, 403}:
                            raise PermissionError("free_provider_credentials_rejected")
                        if response.status_code in {404, 405}:
                            continue
                        response.raise_for_status()
                        content_length = int(response.headers.get("Content-Length") or 0)
                        if content_length > _MAX_MODELS_RESPONSE_BYTES:
                            raise ValueError("free_provider_models_response_too_large")
                        raw_payload = response.raw.read(
                            _MAX_MODELS_RESPONSE_BYTES + 1,
                            decode_content=True,
                        )
                        if len(raw_payload) > _MAX_MODELS_RESPONSE_BYTES:
                            raise ValueError("free_provider_models_response_too_large")
                        try:
                            payload = json.loads(raw_payload.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                            raise ValueError("free_provider_models_invalid_json") from exc
                        selected_url = candidate
                        break
            if selected_url is None or payload is None:
                raise ValueError("free_provider_models_endpoint_missing")
            models = normalize_models_payload(
                payload,
                managed_quota_contract=(
                    str(source.get("auth_mode") or "") == _MANAGED_AUTH_MODE
                    and is_managed_internal_provider_url(str(source.get("api_base") or ""))
                ),
            )
            model_ids = [model["modelId"] for model in models]
            eligible_models = [model for model in models if model["freeEligible"]]
            runtime_identity = _runtime_identity()
            current_ready_model_ids = _revision_bound_ready_model_ids(
                query,
                source_id=source_id,
                runtime_identity=runtime_identity,
            )
            preserved_ready_model_ids = {
                str(model["modelId"])
                for model in models
                if str(model["modelId"]) in current_ready_model_ids
                and not bool(model.get("generalChatBlockVerified"))
                and (
                    bool(model.get("freeEligible"))
                    or bool(model.get("generalChatCanaryRequired"))
                )
            }
            activation_models = [
                model
                for model in models
                if (
                    model["freeEligible"] or model["generalChatCanaryRequired"]
                )
                and str(model["modelId"]) not in preserved_ready_model_ids
            ]
            connection = get_connection()
            try:
                with connection.cursor() as cursor:
                    for model in models:
                        if str(model["modelId"]) in preserved_ready_model_ids:
                            cursor.execute(
                                """UPDATE llm_revolver_provider_models
                                   SET display_name=%s, capabilities=%s::jsonb,
                                       discovery_payload_sha256=%s,
                                       last_seen_at=NOW(), updated_at=NOW()
                                   WHERE source_id=%s::uuid AND upstream_model_id=%s""",
                                (
                                    model["displayName"],
                                    json.dumps(model["capabilities"]),
                                    model["payloadSha256"],
                                    source_id,
                                    model["modelId"],
                                ),
                            )
                            continue
                        cursor.execute(
                            """INSERT INTO llm_revolver_provider_models
                                   (source_id, upstream_model_id, display_name, capabilities,
                                    free_eligible, eligibility_source, discovery_payload_sha256,
                                    eligibility_verified_at, status, enabled, last_seen_at, updated_at)
                               VALUES (
                                   %s::uuid,%s,%s,%s::jsonb,%s,%s,%s,
                                   CASE WHEN %s THEN NOW() ELSE NULL END,
                                   %s,false,NOW(),NOW()
                               )
                               ON CONFLICT (source_id, upstream_model_id) DO UPDATE SET
                                   display_name=EXCLUDED.display_name,
                                   capabilities=EXCLUDED.capabilities,
                                   free_eligible=EXCLUDED.free_eligible,
                                   eligibility_source=EXCLUDED.eligibility_source,
                                   discovery_payload_sha256=EXCLUDED.discovery_payload_sha256,
                                   eligibility_verified_at=CASE WHEN EXCLUDED.free_eligible THEN NOW() ELSE NULL END,
                                   status=CASE WHEN llm_revolver_provider_models.status='ready'
                                               AND EXCLUDED.free_eligible THEN 'ready'
                                               WHEN EXCLUDED.free_eligible THEN 'discovered'
                                               WHEN EXCLUDED.eligibility_source=
                                                    'managed-freellm-chat-canary-required'
                                               THEN 'discovered'
                                               ELSE 'blocked' END,
                                   enabled=CASE WHEN EXCLUDED.free_eligible
                                                THEN llm_revolver_provider_models.enabled
                                                ELSE false END,
                                   last_error_code=CASE
                                       WHEN EXCLUDED.free_eligible THEN NULL
                                       WHEN EXCLUDED.eligibility_source=
                                            'managed-freellm-chat-canary-required'
                                       THEN 'general_chat_canary_required'
                                       ELSE 'free_quota_ineligible' END,
                                   last_seen_at=NOW(), updated_at=NOW()""",
                            (
                                source_id, model["modelId"], model["displayName"],
                                json.dumps(model["capabilities"]), model["freeEligible"],
                                model["eligibilitySource"], model["payloadSha256"],
                                model["freeEligible"],
                                (
                                    "discovered"
                                    if model["freeEligible"]
                                    or model["generalChatCanaryRequired"]
                                    else "blocked"
                                ),
                            ),
                        )
                    if model_ids:
                        cursor.execute(
                            """UPDATE llm_revolver_provider_models
                               SET status='blocked', enabled=false,
                                   last_error_code='model_missing_from_provider_catalog',
                                   updated_at=NOW()
                               WHERE source_id=%s::uuid
                                 AND NOT (upstream_model_id = ANY(%s))""",
                            (source_id, model_ids),
                        )
                    else:
                        cursor.execute(
                            """UPDATE llm_revolver_provider_models
                               SET status='blocked', enabled=false,
                                   last_error_code='provider_catalog_empty',
                                   updated_at=NOW()
                               WHERE source_id=%s::uuid""",
                            (source_id,),
                        )
                    cursor.execute(
                        """UPDATE llm_routes AS route
                           SET disabled=true, updated_at=NOW()
                           FROM llm_revolver_provider_models AS model
                           WHERE model.source_id=%s::uuid
                             AND route.model_id=model.litellm_alias
                             AND (model.free_eligible=false OR model.status='blocked')""",
                        (source_id,),
                    )
                    cursor.execute(
                        """UPDATE llm_revolver_provider_sources
                           SET models_url=%s, key_fingerprint=%s, key_hint=%s,
                               last_http_status=%s, last_discovered_at=NOW(),
                               last_checked_at=NOW(), updated_at=NOW()
                           WHERE id=%s::uuid""",
                        (selected_url, key_fingerprint, key_hint, last_status, source_id),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

            _persist_verified_general_chat_blocks(
                get_connection,
                source_id=source_id,
                models=models,
            )
            activated = []
            deferred = []
            blocked = []
            for model in activation_models[:max_auto]:
                result = activate_model(dict(source), model, key)
                if result.get("ok"):
                    activated.append({"modelId": model["modelId"], **result})
                    continue
                model_status, blocker = _canary_failure_state(result)
                finding = {
                    "modelId": model["modelId"],
                    **result,
                    "modelStatus": model_status,
                    "blocker": blocker,
                }
                (deferred if model_status == "discovered" else blocked).append(finding)
                query(
                    """UPDATE llm_revolver_provider_models
                       SET status=%s, enabled=false, last_error_code=%s, updated_at=NOW()
                       WHERE source_id=%s::uuid AND upstream_model_id=%s""",
                    (model_status, blocker, source_id, model["modelId"]), write=True,
                )
            preserved_ready = sorted(preserved_ready_model_ids)
            has_ready = bool(activated or preserved_ready)
            status = (
                "healthy"
                if has_ready and not blocked and not deferred
                else "degraded"
                if has_ready or models
                else "blocked"
            )
            error_code = (
                "some_free_quota_routes_blocked"
                if has_ready and blocked
                else "some_free_quota_routes_deferred"
                if has_ready and deferred
                else None
                if has_ready
                else "no_free_quota_route_activated"
            )
            query(
                """UPDATE llm_revolver_provider_sources
                   SET status=%s, last_error_code=%s, owner_request_id=NULL,
                       last_checked_at=NOW(), updated_at=NOW()
                   WHERE id=%s::uuid""",
                (status, error_code, source_id), write=True,
            )
            persist_check(
                source_id,
                check_kind="models_discovery",
                models_url=selected_url,
                http_status=last_status,
                outcome="success" if has_ready else "degraded",
                model_count=len(models),
                free_count=len(eligible_models),
                evidence={
                    "activatedModels": [item["modelId"] for item in activated],
                    "preservedReadyModelIds": preserved_ready,
                    "deferredModels": [item["modelId"] for item in deferred],
                    "blockedModels": [item["modelId"] for item in blocked],
                    "eligibilityRule": "managed-free-quota-or-explicit-zero-catalog-with-double-canary",
                    "availabilityFailuresAreRetryable": True,
                },
            )
            audit("admin_free_revolver_provider_discovered", source_id, {
                "modelsUrl": selected_url,
                "modelCount": len(models),
                "freeEligibleCount": len(eligible_models),
                "activatedCount": len(activated),
                "keyHint": key_hint,
            })
            return jsonify({
                "ok": has_ready,
                "status": status,
                "sourceId": source_id,
                "modelsUrl": selected_url,
                "discovered": len(models),
                "freeEligible": len(eligible_models),
                "activated": activated,
                "preservedReady": preserved_ready,
                "deferred": deferred,
                "blocked": blocked,
                "ineligible": [model["modelId"] for model in models if not model["freeEligible"]],
                "keyStoredBy": (
                    "owner-managed-direct-freellm"
                    if source["auth_mode"] == _MANAGED_AUTH_MODE
                    else "ephemeral-discovery-only"
                ),
            }), 200 if has_ready else 409
        except PermissionError as exc:
            code = str(exc)
            query(
                """UPDATE llm_revolver_provider_sources
                   SET status='blocked', last_http_status=%s, last_error_code=%s,
                       owner_request_id=NULL, last_checked_at=NOW(), updated_at=NOW()
                   WHERE id=%s::uuid""",
                (last_status, code, source_id), write=True,
            )
            persist_check(
                source_id, check_kind="models_discovery", models_url=selected_url,
                http_status=last_status, outcome="blocked", model_count=0,
                free_count=0, evidence={"blocker": code},
            )
            return jsonify({"error": "Provider-Zugang wurde abgelehnt", "blocker": code}), 401
        except (OSError, requests.RequestException, UnicodeDecodeError, ValueError) as exc:
            code = str(exc)[:120] or "free_provider_discovery_failed"
            query(
                """UPDATE llm_revolver_provider_sources
                   SET status='blocked', last_http_status=%s, last_error_code=%s,
                       owner_request_id=NULL, last_checked_at=NOW(), updated_at=NOW()
                   WHERE id=%s::uuid""",
                (last_status, code, source_id), write=True,
            )
            persist_check(
                source_id, check_kind="models_discovery", models_url=selected_url,
                http_status=last_status, outcome="blocked", model_count=0,
                free_count=0, evidence={"blocker": code},
            )
            return jsonify({"error": "Free-Provider konnte nicht sicher erkannt werden", "blocker": code}), 502
        finally:
            key = ""
            for index in range(len(protected)):
                protected[index] = 0
            if source.get("auth_mode") in {"bearer", "x-api-key"}:
                _securely_remove(path)

    @app.route(
        "/api/internal/llm/freellm/providers/<source_id>/discover",
        methods=["POST"],
    )
    def internal_discover_managed_freellm_provider(source_id: str):
        """Bootstrap one managed source from a real authenticated catalog and canaries."""
        if not _internal_owner_authorized():
            return jsonify({"error": "forbidden", "protectedValuesReturned": False}), 403
        body = request.get_json(silent=True) or {}
        try:
            source_id = normalize_provider_source_id(source_id)
            max_models = normalize_max_auto_activate(body.get("maxModels", 20))
        except ValueError as exc:
            return jsonify({
                "error": str(exc),
                "protectedValuesReturned": False,
            }), 409
        source = query(
            """SELECT id::text, label, api_base, auth_mode, key_fingerprint,
                      models_url, status, enabled
               FROM llm_revolver_provider_sources
               WHERE id=%s::uuid
               LIMIT 1""",
            (source_id,),
            one=True,
        )
        if (
            not source
            or not bool(source.get("enabled"))
            or str(source.get("auth_mode") or "") != _MANAGED_AUTH_MODE
            or not is_managed_internal_provider_url(str(source.get("api_base") or ""))
        ):
            return jsonify({
                "error": "Nur eine aktivierte verwaltete direkte FreeLLM-Quelle kann initialisiert werden.",
                "blocker": "free_direct_managed_source_required",
                "protectedValuesReturned": False,
            }), 409
        claimed = query(
            """UPDATE llm_revolver_provider_sources
               SET status='probing', last_error_code=NULL, updated_at=NOW()
               WHERE id=%s::uuid AND enabled=true
                 AND (
                   status IN ('degraded','blocked','healthy')
                   OR (status='probing' AND updated_at < NOW() - INTERVAL '5 minutes')
                 )
               RETURNING id::text""",
            (source_id,),
            one=True,
            write=True,
        )
        if not claimed:
            return jsonify({
                "error": "Provider ist deaktiviert oder eine Discovery läuft bereits.",
                "blocker": "free_provider_not_discoverable",
                "sourceId": source_id,
                "protectedValuesReturned": False,
            }), 409

        protected = bytearray()
        key = ""
        selected_url = None
        last_status = None
        bootstrap_stage = "managed_key_read"
        try:
            api_base = str(source.get("api_base") or "")
            protected, key = _read_managed_key(api_base)
            key_fingerprint = hashlib.sha256(key.encode()).hexdigest()
            source_payload = dict(source)
            source_payload["key_fingerprint"] = key_fingerprint
            source_payload["key_hint"] = "owner-managed"

            bootstrap_stage = "authenticated_catalog_fetch"
            payload = None
            headers = _auth_headers(_MANAGED_AUTH_MODE, key)
            with requests.Session() as provider_session:
                provider_session.trust_env = False
                for candidate in models_url_candidates(api_base):
                    assert_provider_target_allowed(candidate)
                    with provider_session.get(
                        candidate,
                        headers=headers,
                        timeout=15,
                        allow_redirects=False,
                        stream=True,
                    ) as response:
                        last_status = int(response.status_code)
                        if last_status in {401, 403}:
                            raise PermissionError("free_provider_credentials_rejected")
                        if last_status in {404, 405}:
                            continue
                        response.raise_for_status()
                        content_length = int(response.headers.get("Content-Length") or 0)
                        if content_length > _MAX_MODELS_RESPONSE_BYTES:
                            raise ValueError("free_provider_models_response_too_large")
                        raw_payload = response.raw.read(
                            _MAX_MODELS_RESPONSE_BYTES + 1,
                            decode_content=True,
                        )
                        if len(raw_payload) > _MAX_MODELS_RESPONSE_BYTES:
                            raise ValueError("free_provider_models_response_too_large")
                        try:
                            payload = json.loads(raw_payload.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                            raise ValueError("free_provider_models_invalid_json") from exc
                        selected_url = candidate
                        break
            if selected_url is None or payload is None:
                raise ValueError("free_provider_models_endpoint_missing")
            models = normalize_models_payload(payload, managed_quota_contract=True)
            model_ids = [str(model["modelId"]) for model in models]
            eligible_models = [model for model in models if bool(model.get("freeEligible"))]
            runtime_identity = _runtime_identity()
            current_ready_model_ids = _revision_bound_ready_model_ids(
                query,
                source_id=source_id,
                runtime_identity=runtime_identity,
            )
            preserved_ready_model_ids = {
                str(model["modelId"])
                for model in models
                if str(model["modelId"]) in current_ready_model_ids
                and not bool(model.get("generalChatBlockVerified"))
                and (
                    bool(model.get("freeEligible"))
                    or bool(model.get("generalChatCanaryRequired"))
                )
            }
            activation_models = [
                model
                for model in models
                if (
                    bool(model.get("freeEligible"))
                    or bool(model.get("generalChatCanaryRequired"))
                )
                and str(model["modelId"]) not in preserved_ready_model_ids
            ]

            bootstrap_stage = "catalog_persistence"
            connection = get_connection()
            try:
                with connection.cursor() as cursor:
                    for model in models:
                        if str(model["modelId"]) in preserved_ready_model_ids:
                            cursor.execute(
                                """UPDATE llm_revolver_provider_models
                                   SET display_name=%s, capabilities=%s::jsonb,
                                       discovery_payload_sha256=%s,
                                       last_seen_at=NOW(), updated_at=NOW()
                                   WHERE source_id=%s::uuid AND upstream_model_id=%s""",
                                (
                                    model["displayName"],
                                    json.dumps(model["capabilities"]),
                                    model["payloadSha256"],
                                    source_id,
                                    model["modelId"],
                                ),
                            )
                            continue
                        cursor.execute(
                            """INSERT INTO llm_revolver_provider_models
                                   (source_id, upstream_model_id, display_name, capabilities,
                                    free_eligible, eligibility_source, discovery_payload_sha256,
                                    eligibility_verified_at, status, enabled, last_seen_at, updated_at)
                               VALUES (
                                   %s::uuid,%s,%s,%s::jsonb,%s,%s,%s,
                                   CASE WHEN %s THEN NOW() ELSE NULL END,
                                   %s,false,NOW(),NOW()
                               )
                               ON CONFLICT (source_id, upstream_model_id) DO UPDATE SET
                                   display_name=EXCLUDED.display_name,
                                   capabilities=EXCLUDED.capabilities,
                                   free_eligible=EXCLUDED.free_eligible,
                                   eligibility_source=EXCLUDED.eligibility_source,
                                   discovery_payload_sha256=EXCLUDED.discovery_payload_sha256,
                                   eligibility_verified_at=CASE WHEN EXCLUDED.free_eligible THEN NOW() ELSE NULL END,
                                   status=CASE WHEN llm_revolver_provider_models.status='ready'
                                               AND EXCLUDED.free_eligible THEN 'ready'
                                               WHEN EXCLUDED.free_eligible THEN 'discovered'
                                               WHEN EXCLUDED.eligibility_source=
                                                    'managed-freellm-chat-canary-required'
                                               THEN 'discovered'
                                               ELSE 'blocked' END,
                                   enabled=CASE WHEN EXCLUDED.free_eligible
                                                THEN llm_revolver_provider_models.enabled
                                                ELSE false END,
                                   last_error_code=CASE
                                       WHEN EXCLUDED.free_eligible THEN NULL
                                       WHEN EXCLUDED.eligibility_source=
                                            'managed-freellm-chat-canary-required'
                                       THEN 'general_chat_canary_required'
                                       ELSE 'free_quota_ineligible' END,
                                   last_seen_at=NOW(), updated_at=NOW()""",
                            (
                                source_id,
                                model["modelId"],
                                model["displayName"],
                                json.dumps(model["capabilities"]),
                                model["freeEligible"],
                                model["eligibilitySource"],
                                model["payloadSha256"],
                                model["freeEligible"],
                                (
                                    "discovered"
                                    if model["freeEligible"]
                                    or model["generalChatCanaryRequired"]
                                    else "blocked"
                                ),
                            ),
                        )
                    if model_ids:
                        cursor.execute(
                            """UPDATE llm_revolver_provider_models
                               SET status='blocked', enabled=false,
                                   last_error_code='model_missing_from_provider_catalog',
                                   updated_at=NOW()
                               WHERE source_id=%s::uuid
                                 AND NOT (upstream_model_id = ANY(%s))""",
                            (source_id, model_ids),
                        )
                    else:
                        cursor.execute(
                            """UPDATE llm_revolver_provider_models
                               SET status='blocked', enabled=false,
                                   last_error_code='provider_catalog_empty',
                                   updated_at=NOW()
                               WHERE source_id=%s::uuid""",
                            (source_id,),
                        )
                    cursor.execute(
                        """UPDATE llm_routes AS route
                           SET disabled=true, updated_at=NOW()
                           FROM llm_revolver_provider_models AS model
                           WHERE model.source_id=%s::uuid
                             AND route.model_id=model.litellm_alias
                             AND (model.free_eligible=false OR model.status='blocked')""",
                        (source_id,),
                    )
                    cursor.execute(
                        """UPDATE llm_revolver_provider_sources
                           SET models_url=%s, key_fingerprint=%s,
                               key_hint='owner-managed', last_http_status=%s,
                               last_discovered_at=NOW(), last_checked_at=NOW(),
                               updated_at=NOW()
                           WHERE id=%s::uuid""",
                        (selected_url, key_fingerprint, last_status, source_id),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

            _persist_verified_general_chat_blocks(
                get_connection,
                source_id=source_id,
                models=models,
            )
            bootstrap_stage = "double_canary_activation"
            ready = []
            deferred = []
            blocked = []
            for model in activation_models[:max_models]:
                result = activate_model(source_payload, model, key)
                if result.get("ok"):
                    ready.append({
                        "modelId": model["modelId"],
                        "routeId": result.get("routeId"),
                        "sourceType": result.get("sourceType"),
                        "providerId": result.get("providerId"),
                        "providerModel": result.get("providerModel"),
                        "responseModel": result.get("responseModel"),
                        "upstreamKeyless": result.get("upstreamKeyless"),
                        "canaryConfirmationCount": result.get("canaryConfirmationCount"),
                        "providerCostState": result.get("providerCostState"),
                        "runtimeIdentity": result.get("runtimeIdentity"),
                        "receiptId": result.get("receiptId"),
                        "receiptSha256": result.get("receiptSha256"),
                    })
                    continue
                model_status, blocker = _canary_failure_state(result)
                finding = {
                    "modelId": model["modelId"],
                    "blocker": blocker,
                    "modelStatus": model_status,
                    "failedConfirmation": result.get("failedConfirmation"),
                    "confirmationCount": result.get("confirmationCount"),
                    "httpStatus": result.get("httpStatus"),
                    "failureFamily": result.get("failureFamily"),
                    "requestExceptionType": result.get("requestExceptionType"),
                }
                (deferred if model_status == "discovered" else blocked).append(finding)
                query(
                    """UPDATE llm_revolver_provider_models
                       SET status=%s, enabled=false, last_error_code=%s,
                           updated_at=NOW()
                       WHERE source_id=%s::uuid AND upstream_model_id=%s""",
                    (model_status, blocker, source_id, model["modelId"]),
                    write=True,
                )
            preserved_ready = sorted(preserved_ready_model_ids)
            has_ready = bool(ready or preserved_ready)
            status = (
                "healthy"
                if has_ready and not blocked and not deferred
                else "degraded"
                if has_ready or models
                else "blocked"
            )
            error_code = (
                "some_freellm_routes_blocked"
                if has_ready and blocked
                else "some_freellm_routes_deferred"
                if has_ready and deferred
                else None
                if has_ready
                else "no_freellm_route_activated"
            )
            query(
                """UPDATE llm_revolver_provider_sources
                   SET status=%s, last_error_code=%s, last_checked_at=NOW(),
                       updated_at=NOW()
                   WHERE id=%s::uuid""",
                (status, error_code, source_id),
                write=True,
            )
            persist_check(
                source_id,
                check_kind="models_discovery",
                models_url=selected_url,
                http_status=last_status,
                outcome=(
                    "success"
                    if ready and not blocked
                    else "degraded"
                    if ready or models
                    else "blocked"
                ),
                model_count=len(models),
                free_count=len(ready),
                evidence={
                    "readyModelIds": [item["modelId"] for item in ready],
                    "preservedReadyModelIds": preserved_ready,
                    "readyReceipts": [
                        {
                            "modelId": item["modelId"],
                            "routeId": item.get("routeId"),
                            "receiptId": item.get("receiptId"),
                            "receiptSha256": item.get("receiptSha256"),
                            "runtimeIdentity": item.get("runtimeIdentity"),
                        }
                        for item in ready
                    ],
                    "deferredModelIds": [item["modelId"] for item in deferred],
                    "blockedModelIds": [item["modelId"] for item in blocked],
                    "transport": "freellm",
                    "managedCatalogBootstrap": True,
                    "authenticatedCatalogHttpStatus": last_status,
                    "doubleCanaryRequired": True,
                    "rawProviderResponsesPersisted": False,
                },
            )
            return jsonify({
                "ok": has_ready,
                "status": status,
                "sourceId": source_id,
                "modelsUrl": selected_url,
                "authenticatedCatalogHttpStatus": last_status,
                "keyFingerprintPresent": True,
                "discovered": len(models),
                "eligible": len(eligible_models),
                "ready": ready,
                "preservedReady": preserved_ready,
                "deferred": deferred,
                "blocked": blocked,
                "transport": "freellm",
                "executionProfile": "free_single_agent",
                "maxForegroundAgents": 1,
                "maxBackgroundAgents": 0,
                "protectedValuesReturned": False,
                "rawProviderResponsesReturned": False,
            }), 200 if has_ready else 409
        except PermissionError as exc:
            code = str(exc)[:120] or "free_provider_credentials_rejected"
            query(
                """UPDATE llm_revolver_provider_sources
                   SET status='blocked', last_http_status=%s,
                       last_error_code=%s, last_checked_at=NOW(), updated_at=NOW()
                   WHERE id=%s::uuid""",
                (last_status, code, source_id),
                write=True,
            )
            persist_check(
                source_id,
                check_kind="models_discovery",
                models_url=selected_url,
                http_status=last_status,
                outcome="blocked",
                model_count=0,
                free_count=0,
                evidence={"blocker": code, "rawProviderResponsesPersisted": False},
            )
            return jsonify({
                "error": "Provider-Zugang wurde abgelehnt.",
                "blocker": code,
                "sourceId": source_id,
                "protectedValuesReturned": False,
            }), 401
        except ManagedKeyContractError as exc:
            query(
                """UPDATE llm_revolver_provider_sources
                   SET status='degraded', last_error_code=%s,
                       last_checked_at=NOW(), updated_at=NOW()
                   WHERE id=%s::uuid""",
                (exc.code, source_id),
                write=True,
            )
            return jsonify({
                "error": "Der verwaltete FreeLLM-Schlüssel konnte nicht sicher gelesen werden.",
                "blocker": exc.code,
                "sourceId": source_id,
                "protectedValuesReturned": False,
            }), 503
        except (OSError, requests.RequestException, UnicodeDecodeError, ValueError):
            blocker = {
                "managed_key_read": "freellm_managed_key_unavailable",
                "authenticated_catalog_fetch": "freellm_catalog_fetch_failed",
                "catalog_persistence": "freellm_catalog_persistence_failed",
                "double_canary_activation": "freellm_model_reconcile_failed",
            }.get(bootstrap_stage, "freellm_bootstrap_runtime_failed")
            query(
                """UPDATE llm_revolver_provider_sources
                   SET status='degraded', last_http_status=%s,
                       last_error_code=%s, last_checked_at=NOW(), updated_at=NOW()
                   WHERE id=%s::uuid""",
                (last_status, blocker, source_id),
                write=True,
            )
            return jsonify({
                "error": "Die verwaltete FreeLLM-Quelle konnte nicht sicher initialisiert werden.",
                "blocker": blocker,
                "sourceId": source_id,
                "protectedValuesReturned": False,
            }), 502
        finally:
            key = ""
            for index in range(len(protected)):
                protected[index] = 0

    @app.route("/api/internal/llm/freellm/providers", methods=["GET"])
    def internal_freellm_provider_status():
        if not _internal_owner_authorized():
            return jsonify({"error": "forbidden", "protectedValuesReturned": False}), 403
        rows = query(
            """SELECT source.id::text, source.label, source.api_base, source.auth_mode,
                      source.status, source.enabled, source.last_http_status,
                      source.last_error_code, source.last_discovered_at,
                      source.last_checked_at, source.key_fingerprint,
                      (source.key_fingerprint IS NOT NULL) AS key_fingerprint_present,
                      COUNT(model.id)::int AS model_count,
                      COUNT(model.id) FILTER (WHERE model.free_eligible=true)::int AS free_eligible_count,
                      COUNT(model.id) FILTER (
                          WHERE model.status='ready' AND model.enabled=true
                      )::int AS ready_count
               FROM llm_revolver_provider_sources AS source
               LEFT JOIN llm_revolver_provider_models AS model
                 ON model.source_id=source.id
               WHERE source.auth_mode=%s
               GROUP BY source.id
               ORDER BY source.created_at DESC""",
            (_MANAGED_AUTH_MODE,),
        ) or []
        providers = []
        for row in rows:
            source = dict(row)
            if not is_managed_internal_provider_url(str(source.get("api_base") or "")):
                continue
            managed_key = _managed_key_state(
                str(source.get("api_base") or ""),
                str(source.get("key_fingerprint") or ""),
            )
            managed_source = managed_internal_source_spec(source.get("api_base")) or {}
            ready_rows = query(
                """SELECT model.upstream_model_id,
                          route.id::text AS route_id,
                          route.config->'runtimeIdentity' AS runtime_identity,
                          route.config->'canaryReceipt' AS canary_receipt,
                          route.config->'quotaEvidence' AS quota_evidence,
                          route.config->'retryEvidence' AS retry_evidence,
                          route.config->'cooldownEvidence' AS cooldown_evidence,
                          route.config->'eligibilityEvidence' AS eligibility_evidence,
                          route.config->'actualUpstream' AS actual_upstream
                   FROM llm_revolver_provider_models AS model
                   JOIN llm_routes AS route
                     ON route.model_id=model.litellm_alias
                    AND route.config->>'revolverProviderSourceId'=%s
                   WHERE model.source_id=%s::uuid
                     AND model.status='ready'
                     AND model.enabled=true
                     AND route.disabled=false
                   ORDER BY model.display_name ASC
                   LIMIT 20""",
                (str(source.get("id") or ""), str(source.get("id") or "")),
            ) or []
            ready_evidence = [{
                "modelId": str(item.get("upstream_model_id") or ""),
                "routeId": str(item.get("route_id") or ""),
                "runtimeIdentity": item.get("runtime_identity") or {},
                "canaryReceipt": item.get("canary_receipt") or {},
                "quotaEvidence": item.get("quota_evidence") or {},
                "retryEvidence": item.get("retry_evidence") or {},
                "cooldownEvidence": item.get("cooldown_evidence") or {},
                "eligibilityEvidence": item.get("eligibility_evidence") or {},
                "actualUpstream": item.get("actual_upstream") or {},
            } for item in ready_rows]
            providers.append({
                "sourceId": str(source.get("id") or ""),
                "sourceType": str(managed_source.get("sourceId") or "external-free-provider"),
                "label": str(source.get("label") or ""),
                "apiBase": str(source.get("api_base") or ""),
                "authMode": str(source.get("auth_mode") or ""),
                "status": str(source.get("status") or "blocked"),
                "enabled": bool(source.get("enabled")),
                "lastHttpStatus": source.get("last_http_status"),
                "lastErrorCode": source.get("last_error_code"),
                "lastDiscoveredAt": (
                    source["last_discovered_at"].isoformat()
                    if source.get("last_discovered_at") else None
                ),
                "lastCheckedAt": (
                    source["last_checked_at"].isoformat()
                    if source.get("last_checked_at") else None
                ),
                "keyFingerprintPresent": bool(source.get("key_fingerprint_present")),
                "managedKeyAvailable": bool(managed_key["available"]),
                "managedKeyBlocker": managed_key["blocker"],
                "keyFingerprintMatchesFile": managed_key["fingerprintMatches"],
                "modelCount": int(source.get("model_count") or 0),
                "freeEligibleCount": int(source.get("free_eligible_count") or 0),
                "readyCount": int(source.get("ready_count") or 0),
                "readyEvidence": ready_evidence,
                "blockedEvidence": _blocked_general_chat_evidence(
                    query,
                    str(source.get("id") or ""),
                ),
            })
        credential_pools = []
        for credential_provider_id, spec in FREELLM_PROVIDER_SPECS.items():
            state = _freellm_provider_credential_state(credential_provider_id)
            credential_pools.append({
                "providerId": credential_provider_id,
                "label": str(spec["label"]),
                "mode": state.get("mode"),
                "configured": bool(state.get("configured")),
                "keyCount": int(state.get("keyCount") or 0),
                "permissionsValid": state.get("permissionsValid"),
            })
        return jsonify({
            "ok": True,
            "status": "FREELLM_PROVIDER_STATUS",
            "providers": providers,
            "credentialPools": credential_pools,
            "ownerManagedCredentialCount": sum(
                item["keyCount"]
                for item in credential_pools
                if item["mode"] == "credential-pool"
            ),
            "keylessMarkerCount": sum(
                item["keyCount"]
                for item in credential_pools
                if item["mode"] == "keyless"
            ),
            "runtimeIdentity": _runtime_identity(),
            "protectedValuesReturned": False,
        })

    @app.route(
        "/api/internal/llm/freellm/providers/<source_id>/reconcile",
        methods=["POST"],
    )
    def internal_reconcile_freellm_provider(source_id: str):
        if not _internal_owner_authorized():
            return jsonify({"error": "forbidden", "protectedValuesReturned": False}), 403
        body = request.get_json(silent=True) or {}
        try:
            source_id = normalize_provider_source_id(source_id)
            max_models = normalize_max_auto_activate(body.get("maxModels", 20))
        except ValueError as exc:
            return jsonify({
                "error": str(exc),
                "protectedValuesReturned": False,
            }), 409
        source = query(
            """SELECT id::text, label, api_base, auth_mode, key_fingerprint,
                      models_url, last_http_status, last_discovered_at, enabled,
                      (
                          last_discovered_at IS NOT NULL
                          AND last_discovered_at >= NOW() - INTERVAL '24 hours'
                      ) AS catalog_fresh
               FROM llm_revolver_provider_sources
               WHERE id=%s::uuid
               LIMIT 1""",
            (source_id,),
            one=True,
        )
        if (
            not source
            or not bool(source.get("enabled"))
            or str(source.get("auth_mode") or "") != _MANAGED_AUTH_MODE
            or not is_managed_internal_provider_url(str(source.get("api_base") or ""))
        ):
            return jsonify({
                "error": "Nur die aktivierte verwaltete direkte FreeLLM-Quelle kann abgeglichen werden.",
                "blocker": "free_direct_managed_source_required",
                "protectedValuesReturned": False,
            }), 409
        if (
            not source.get("key_fingerprint")
            or int(source.get("last_http_status") or 0) != 200
            or not bool(source.get("catalog_fresh"))
        ):
            return jsonify({
                "error": "Ein frischer, authentifizierter HTTP-200-Modellkatalog ist erforderlich.",
                "blocker": "freellm_fresh_catalog_required",
                "sourceId": source_id,
                "keyFingerprintPresent": bool(source.get("key_fingerprint")),
                "protectedValuesReturned": False,
            }), 409
        runtime_identity = _runtime_identity()
        target_ready_count = _minimum_ready_routes()
        models = query(
            """SELECT *
               FROM (
                   SELECT model.id::text, model.upstream_model_id,
                          model.display_name, model.litellm_alias,
                          model.discovery_payload_sha256, model.free_eligible,
                          model.eligibility_source, model.status, model.enabled,
                          model.last_error_code, model.last_canary_request_id,
                          model.last_canary_at, model.canary_cost_state,
                          COALESCE(
                              route.config->'runtimeIdentity'->>'sourceRevision'=%s
                              AND route.config->'runtimeIdentity'->>'imageDigest'=%s
                              AND route.config->'runtimeIdentity'->>'sourceRevisionVerified'='true'
                              AND route.config->'runtimeIdentity'->>'imageDigestVerified'='true'
                              AND route.config->'canaryReceipt'->>'schemaVersion'=%s
                              AND route.config->'canaryReceipt'->>'generalChatEvidenceVerified'='true'
                              AND route.config->'canaryReceipt'->>'receiptSha256' ~ '^[0-9a-f]{64}$'
                              AND model.eligibility_verified_at IS NOT NULL
                              AND model.eligibility_verified_at >= NOW() - (%s * INTERVAL '1 hour')
                              AND model.last_canary_at IS NOT NULL
                              AND model.last_canary_at >= NOW() - (%s * INTERVAL '1 hour')
                              AND route.disabled=false,
                              false
                          ) AS receipt_current
                   FROM llm_revolver_provider_models AS model
                   LEFT JOIN llm_routes AS route
                     ON route.model_id=model.litellm_alias
                    AND route.config->>'revolverProviderSourceId'=%s
                   WHERE model.source_id=%s::uuid
                     AND model.last_seen_at >= NOW() - INTERVAL '24 hours'
                     AND (
                         model.free_eligible=true
                         OR (
                             model.free_eligible=false
                             AND model.eligibility_source IN (
                                 'provider-pricing-unreported-or-incomplete',
                                 'managed-freellm-quota-contract',
                                 'migration-042-recheck-required',
                                 'managed-freellm-chat-canary-required'
                             )
                         )
                     )
               ) AS candidate
               ORDER BY
                   CASE
                       WHEN status='ready' AND enabled=true AND receipt_current=false THEN 0
                       WHEN last_canary_request_id IS NOT NULL
                            AND canary_cost_state='zero'
                            AND receipt_current=false THEN 1
                       WHEN receipt_current=false
                            AND last_canary_request_id IS NULL
                            AND (
                                last_error_code IS NULL
                                OR last_error_code IN (
                                    'general_chat_canary_required',
                                    'freellm_quota_contract_recheck_required'
                                )
                            ) THEN 2
                       WHEN status<>'ready' AND last_error_code IS NULL THEN 3
                       WHEN status<>'ready' AND last_error_code IN (
                           'freellm_rate_limited','freellm_timeout','freellm_upstream_unavailable'
                       ) THEN 4
                       WHEN receipt_current=true THEN 6
                       ELSE 5
                   END,
                   CASE
                       WHEN last_canary_request_id IS NOT NULL
                            AND canary_cost_state='zero'
                       THEN last_canary_at
                   END DESC NULLS LAST,
                   last_canary_at ASC NULLS FIRST,
                   display_name ASC
               LIMIT %s""",
            (
                runtime_identity["sourceRevision"],
                runtime_identity["imageDigest"],
                _FREELLM_RECEIPT_SCHEMA,
                _eligibility_evidence_ttl_hours(),
                _eligibility_evidence_ttl_hours(),
                source_id,
                source_id,
                max_models,
            ),
        ) or []
        if not models:
            return jsonify({
                "error": "Der frische Katalog enthält keine sicher abgleichbaren Modelle.",
                "blocker": "freellm_no_reconcilable_models",
                "sourceId": source_id,
                "protectedValuesReturned": False,
            }), 409

        protected = bytearray()
        key = ""
        reconcile_stage = "managed_key_read"
        try:
            protected, key = _read_managed_key(
                str(source.get("api_base") or ""),
                str(source.get("key_fingerprint") or ""),
            )

            reconcile_stage = "model_activation"
            source_payload = dict(source)
            ready = []
            current_ready = []
            deferred = []
            blocked = []
            for row in models:
                stored = dict(row)
                model_id = str(stored.get("upstream_model_id") or "")
                alias = str(stored.get("litellm_alias") or "")
                if is_specialist_model_identifier(model_id):
                    blocker = "freellm_model_not_general_chat_compatible"
                    blocked.append({
                        "modelId": model_id,
                        "blocker": blocker,
                        "modelStatus": "blocked",
                        "failureFamily": "specialist_model_identifier",
                    })
                    query(
                        """UPDATE llm_revolver_provider_models
                           SET free_eligible=false, status='blocked', enabled=false,
                               eligibility_source='specialist-model-identifier',
                               eligibility_verified_at=NOW(),
                               last_error_code='specialist-model-identifier',
                               updated_at=NOW()
                           WHERE id=%s::uuid""",
                        (stored["id"],),
                        write=True,
                    )
                    if alias:
                        query(
                            """UPDATE llm_routes
                               SET disabled=true, updated_at=NOW()
                               WHERE model_id=%s""",
                            (alias,),
                            write=True,
                        )
                    continue
                if (
                    bool(stored.get("receipt_current"))
                    and str(stored.get("status") or "") == "ready"
                    and bool(stored.get("enabled"))
                ):
                    current_ready.append({
                        "modelId": model_id,
                        "routeAlias": alias,
                        "receiptCurrent": True,
                    })
                    continue
                eligibility_source = str(
                    stored.get("eligibility_source")
                    or "managed-freellm-quota-contract"
                )
                try:
                    result = activate_model(
                        source_payload,
                        {
                            "modelId": model_id,
                            "displayName": str(stored.get("display_name") or model_id),
                            "eligibilitySource": eligibility_source,
                            "generalChatCanaryRequired": True,
                            "payloadSha256": str(stored.get("discovery_payload_sha256") or ""),
                        },
                        key,
                    )
                except (ArithmeticError, TypeError, ValueError) as exc:
                    error_type = re.sub(
                        r"[^a-z0-9]+", "_", type(exc).__name__.lower()
                    ).strip("_")[:40]
                    result = {
                        "ok": False,
                        "blocker": (
                            f"freellm_model_activation_{error_type}"
                            if error_type
                            else "freellm_model_activation_invalid_evidence"
                        ),
                    }
                if result.get("ok"):
                    ready.append({
                        "modelId": model_id,
                        "routeId": result.get("routeId"),
                        "sourceType": result.get("sourceType"),
                        "providerId": result.get("providerId"),
                        "providerModel": result.get("providerModel"),
                        "responseModel": result.get("responseModel"),
                        "upstreamKeyless": result.get("upstreamKeyless"),
                        "canaryConfirmationCount": result.get("canaryConfirmationCount"),
                        "providerCostState": result.get("providerCostState"),
                        "canaryLatencyMs": result.get("canaryLatencyMs"),
                        "runtimeIdentity": result.get("runtimeIdentity"),
                        "receiptId": result.get("receiptId"),
                        "receiptSha256": result.get("receiptSha256"),
                    })
                    if _reconcile_pace_seconds() > 0:
                        time.sleep(_reconcile_pace_seconds())
                    continue
                model_status, blocker = _canary_failure_state(result)
                finding = {
                    "modelId": model_id,
                    "blocker": blocker,
                    "modelStatus": model_status,
                    "failedConfirmation": result.get("failedConfirmation"),
                    "confirmationCount": result.get("confirmationCount"),
                    "httpStatus": result.get("httpStatus"),
                    "failureFamily": result.get("failureFamily"),
                    "requestExceptionType": result.get("requestExceptionType"),
                    "retryAfterSeconds": result.get("retryAfterSeconds"),
                    "latencyMs": result.get("latencyMs"),
                }
                (deferred if model_status == "discovered" else blocked).append(finding)
                reconcile_stage = "model_state_persistence"
                query(
                    """UPDATE llm_revolver_provider_models
                       SET status=%s, enabled=false, last_error_code=%s,
                           updated_at=NOW()
                       WHERE id=%s::uuid""",
                    (model_status, blocker, stored["id"]),
                    write=True,
                )
                reconcile_stage = "model_activation"
                alias = str(stored.get("litellm_alias") or "")
                if alias:
                    query(
                        """UPDATE llm_routes
                           SET disabled=true, updated_at=NOW()
                           WHERE model_id=%s""",
                        (alias,),
                        write=True,
                    )
                delay_seconds = max(
                    _reconcile_pace_seconds(),
                    min(float(result.get("retryAfterSeconds") or 0), 3.0),
                )
                if delay_seconds > 0:
                    time.sleep(delay_seconds)
            reconcile_stage = "route_activation_parity"
            query(
                """UPDATE llm_routes AS route
                   SET disabled=NOT (
                           model.status='ready'
                           AND model.enabled=true
                           AND model.free_eligible=true
                           AND model.eligibility_verified_at IS NOT NULL
                           AND model.eligibility_verified_at >= NOW() - (%s * INTERVAL '1 hour')
                           AND model.last_canary_at IS NOT NULL
                           AND model.last_canary_at >= NOW() - (%s * INTERVAL '1 hour')
                           AND route.config->'runtimeIdentity'->>'sourceRevision'=%s
                           AND route.config->'runtimeIdentity'->>'imageDigest'=%s
                           AND route.config->'runtimeIdentity'->>'sourceRevisionVerified'='true'
                           AND route.config->'runtimeIdentity'->>'imageDigestVerified'='true'
                           AND route.config->'canaryReceipt'->>'schemaVersion'=%s
                           AND route.config->'canaryReceipt'->>'generalChatEvidenceVerified'='true'
                           AND route.config->'canaryReceipt'->>'receiptSha256' ~ '^[0-9a-f]{64}$'
                       ),
                       provider='freellm', runtime_kind='freellm',
                       updated_at=NOW()
                   FROM llm_revolver_provider_models AS model
                   WHERE model.source_id=%s::uuid
                     AND model.litellm_alias IS NOT NULL
                     AND route.model_id=model.litellm_alias
                     AND route.config->>'revolverProviderSourceId'=%s""",
                (
                    _eligibility_evidence_ttl_hours(),
                    _eligibility_evidence_ttl_hours(),
                    runtime_identity["sourceRevision"],
                    runtime_identity["imageDigest"],
                    _FREELLM_RECEIPT_SCHEMA,
                    source_id,
                    source_id,
                ),
                write=True,
            )
            ready_state = query(
                """SELECT
                       COUNT(*) FILTER (
                           WHERE model.status='ready'
                             AND model.enabled=true
                             AND model.free_eligible=true
                             AND model.eligibility_verified_at IS NOT NULL
                             AND model.eligibility_verified_at >= NOW() - (%s * INTERVAL '1 hour')
                             AND model.last_canary_at IS NOT NULL
                             AND model.last_canary_at >= NOW() - (%s * INTERVAL '1 hour')
                             AND route.disabled=false
                             AND route.config->'runtimeIdentity'->>'sourceRevision'=%s
                             AND route.config->'runtimeIdentity'->>'imageDigest'=%s
                             AND route.config->'canaryReceipt'->>'schemaVersion'=%s
                             AND route.config->'canaryReceipt'->>'generalChatEvidenceVerified'='true'
                             AND route.config->'canaryReceipt'->>'receiptSha256' ~ '^[0-9a-f]{64}$'
                       )::int AS ready_count,
                       COUNT(*) FILTER (
                           WHERE model.status='discovered'
                       )::int AS deferred_count,
                       COUNT(*) FILTER (
                           WHERE model.status='blocked'
                              OR route.id IS NULL
                       )::int AS blocked_count
                   FROM llm_revolver_provider_models AS model
                   LEFT JOIN llm_routes AS route
                     ON route.model_id=model.litellm_alias
                    AND route.config->>'revolverProviderSourceId'=%s
                   WHERE model.source_id=%s::uuid""",
                (
                    _eligibility_evidence_ttl_hours(),
                    _eligibility_evidence_ttl_hours(),
                    runtime_identity["sourceRevision"],
                    runtime_identity["imageDigest"],
                    _FREELLM_RECEIPT_SCHEMA,
                    source_id,
                    source_id,
                ),
                one=True,
            ) or {}
            overall_ready_count = int(ready_state.get("ready_count") or 0)
            overall_deferred_count = int(ready_state.get("deferred_count") or 0)
            overall_blocked_count = int(ready_state.get("blocked_count") or 0)
            minimum_ready_satisfied = overall_ready_count >= target_ready_count
            status = (
                "healthy"
                if minimum_ready_satisfied
                else "degraded"
                if overall_ready_count > 0 or overall_deferred_count > 0
                else "blocked"
            )
            error_code = (
                None
                if minimum_ready_satisfied
                else "some_freellm_routes_blocked"
                if overall_blocked_count > 0
                else "some_freellm_routes_deferred"
                if overall_deferred_count > 0
                else "freellm_minimum_ready_routes_not_met"
                if overall_ready_count > 0
                else "no_freellm_route_activated"
            )
            reconcile_stage = "provider_state_persistence"
            query(
                """UPDATE llm_revolver_provider_sources
                   SET status=%s, last_error_code=%s, last_checked_at=NOW(),
                       updated_at=NOW()
                   WHERE id=%s::uuid""",
                (status, error_code, source_id),
                write=True,
            )
            reconcile_stage = "check_persistence"
            persist_check(
                source_id,
                check_kind="managed_quota_direct_canary",
                models_url=str(source.get("models_url") or "") or None,
                http_status=source.get("last_http_status"),
                outcome=(
                    "success"
                    if status == "healthy"
                    else "degraded"
                    if overall_ready_count > 0 or overall_deferred_count > 0
                    else "blocked"
                ),
                model_count=len(models),
                free_count=overall_ready_count,
                evidence={
                    "checkedReadyModelIds": [item["modelId"] for item in ready],
                    "currentReceiptModelIds": [item["modelId"] for item in current_ready],
                    "minimumReadyRoutes": target_ready_count,
                    "minimumReadySatisfied": minimum_ready_satisfied,
                    "readyRouteCeiling": None,
                    "additionalReadyRoutesAllowed": True,
                    "readyReceipts": [
                        {
                            "modelId": item["modelId"],
                            "routeId": item.get("routeId"),
                            "receiptId": item.get("receiptId"),
                            "receiptSha256": item.get("receiptSha256"),
                            "runtimeIdentity": item.get("runtimeIdentity"),
                        }
                        for item in ready
                    ],
                    "checkedDeferredModelIds": [item["modelId"] for item in deferred],
                    "checkedBlockedModelIds": [item["modelId"] for item in blocked],
                    "overallReadyCount": overall_ready_count,
                    "overallDeferredCount": overall_deferred_count,
                    "overallBlockedCount": overall_blocked_count,
                    "transport": "freellm",
                    "managedQuotaContract": True,
                    "rawProviderResponsesPersisted": False,
                },
            )
            return jsonify({
                "ok": minimum_ready_satisfied,
                "status": status,
                "sourceId": source_id,
                "keyFingerprintPresent": True,
                "readyCount": overall_ready_count,
                "minimumReadyRoutes": target_ready_count,
                "minimumReadySatisfied": minimum_ready_satisfied,
                "readyRouteCeiling": None,
                "additionalReadyRoutesAllowed": True,
                "deferredCount": overall_deferred_count,
                "currentReady": current_ready,
                "ready": ready,
                "deferred": deferred,
                "blocked": blocked,
                "transport": "freellm",
                "executionProfile": "free_single_agent",
                "maxForegroundAgents": 1,
                "maxBackgroundAgents": 0,
                "protectedValuesReturned": False,
            }), 200 if minimum_ready_satisfied else 409
        except ManagedKeyContractError as exc:
            query(
                """UPDATE llm_revolver_provider_sources
                   SET status='degraded', last_error_code=%s,
                       last_checked_at=NOW(), updated_at=NOW()
                   WHERE id=%s::uuid""",
                (exc.code, source_id),
                write=True,
            )
            return jsonify({
                "error": "Der verwaltete FreeLLM-Schlüssel konnte nicht sicher geprüft werden.",
                "blocker": exc.code,
                "sourceId": source_id,
                "protectedValuesReturned": False,
            }), 503
        except (ArithmeticError, OSError, TypeError, UnicodeDecodeError, ValueError):
            blocker = {
                "managed_key_read": "freellm_managed_key_unavailable",
                "model_activation": "freellm_model_reconcile_failed",
                "model_state_persistence": "freellm_model_state_persistence_failed",
                "route_activation_parity": "freellm_route_activation_parity_failed",
                "provider_state_persistence": "freellm_provider_state_persistence_failed",
                "check_persistence": "freellm_check_persistence_failed",
            }.get(reconcile_stage, "freellm_reconcile_runtime_failed")
            query(
                """UPDATE llm_revolver_provider_sources
                   SET status='degraded', last_error_code=%s,
                       last_checked_at=NOW(), updated_at=NOW()
                   WHERE id=%s::uuid""",
                (blocker, source_id),
                write=True,
            )
            return jsonify({
                "error": "Der direkte FreeLLM-Abgleich konnte nicht abgeschlossen werden.",
                "blocker": blocker,
                "sourceId": source_id,
                "protectedValuesReturned": False,
            }), 503
        finally:
            key = ""
            for index in range(len(protected)):
                protected[index] = 0

    @app.route("/api/admin/llm/revolver-v3/providers/<source_id>/recheck", methods=["POST"])
    @require_admin
    def admin_recheck_free_revolver_provider(source_id: str):
        try:
            source_id = normalize_provider_source_id(source_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        source = query(
            """SELECT id::text, api_base, auth_mode, key_fingerprint
               FROM llm_revolver_provider_sources
               WHERE id=%s::uuid AND enabled=true LIMIT 1""",
            (source_id,),
            one=True,
        )
        if (
            not source
            or str(source.get("auth_mode") or "") != _MANAGED_AUTH_MODE
            or not is_managed_internal_provider_url(str(source.get("api_base") or ""))
        ):
            return jsonify({
                "error": "Nur die verwaltete direkte FreeLLM-Route kann erneut geprüft werden.",
                "blocker": "free_direct_managed_source_required",
            }), 409
        models = query(
            """SELECT id::text, upstream_model_id, display_name,
                      litellm_alias, discovery_payload_sha256,
                      eligibility_source
               FROM llm_revolver_provider_models
               WHERE source_id=%s::uuid
                 AND (
                     free_eligible=true
                     OR eligibility_source='managed-freellm-chat-canary-required'
                 )
               ORDER BY display_name ASC LIMIT 100""",
            (source_id,),
        ) or []
        if not models:
            return jsonify({
                "error": "Keine healthcheckfähigen Free-Routen vorhanden. Zuerst Discovery und Quotenprüfung ausführen.",
                "blocker": "free_provider_no_recheckable_routes",
                "nextAction": "discover_provider_models",
            }), 409

        protected = bytearray()
        key = ""
        try:
            protected, key = _read_managed_key(
                str(source.get("api_base") or ""),
                str(source.get("key_fingerprint") or ""),
            )

            ready = []
            deferred = []
            blocked = []
            source_payload = dict(source)
            for model in models:
                alias = str(model.get("litellm_alias") or "")
                model_id = str(model["upstream_model_id"])
                if is_specialist_model_identifier(model_id):
                    blocker = "freellm_model_not_general_chat_compatible"
                    blocked.append({
                        "modelId": model_id,
                        "blocker": blocker,
                        "modelStatus": "blocked",
                        "failureFamily": "specialist_model_identifier",
                    })
                    query(
                        """UPDATE llm_revolver_provider_models
                           SET free_eligible=false, status='blocked', enabled=false,
                               eligibility_source='specialist-model-identifier',
                               eligibility_verified_at=NOW(),
                               last_error_code='specialist-model-identifier',
                               updated_at=NOW()
                           WHERE id=%s::uuid""",
                        (model["id"],),
                        write=True,
                    )
                    if alias:
                        query(
                            "UPDATE llm_routes SET disabled=true, updated_at=NOW() WHERE model_id=%s",
                            (alias,),
                            write=True,
                        )
                    continue
                result = activate_model(
                    source_payload,
                    {
                        "modelId": str(model["upstream_model_id"]),
                        "displayName": str(
                            model.get("display_name")
                            or model["upstream_model_id"]
                        ),
                        "eligibilitySource": str(
                            model.get("eligibility_source")
                            or "managed-freellm-quota-contract"
                        ),
                        "generalChatCanaryRequired": True,
                        "payloadSha256": str(
                            model.get("discovery_payload_sha256") or ""
                        ),
                    },
                    key,
                )
                if result.get("ok"):
                    ready.append({
                        "modelId": str(model["upstream_model_id"]),
                        "routeId": result.get("routeId"),
                        "sourceType": result.get("sourceType"),
                        "providerId": result.get("providerId"),
                        "providerModel": result.get("providerModel"),
                        "responseModel": result.get("responseModel"),
                        "upstreamKeyless": result.get("upstreamKeyless"),
                        "canaryConfirmationCount": result.get(
                            "canaryConfirmationCount"
                        ),
                        "providerCostState": result.get("providerCostState"),
                        "runtimeIdentity": result.get("runtimeIdentity"),
                        "receiptId": result.get("receiptId"),
                        "receiptSha256": result.get("receiptSha256"),
                    })
                    continue
                model_status, blocker = _canary_failure_state(result)
                target = deferred if model_status == "discovered" else blocked
                target.append({
                    "modelId": str(model["upstream_model_id"]),
                    "blocker": blocker,
                    "modelStatus": model_status,
                    "failureFamily": result.get("failureFamily"),
                    "httpStatus": result.get("httpStatus"),
                })
                query(
                    """UPDATE llm_revolver_provider_models
                       SET status=%s, enabled=false, last_error_code=%s,
                           updated_at=NOW() WHERE id=%s::uuid""",
                    (model_status, blocker, model["id"]),
                    write=True,
                )
                if alias:
                    query(
                        "UPDATE llm_routes SET disabled=true, updated_at=NOW() WHERE model_id=%s",
                        (alias,), write=True,
                    )
            status = (
                "healthy"
                if ready and not blocked and not deferred
                else "degraded"
                if ready or deferred
                else "blocked"
            )
            error_code = (
                "freellm_routes_hard_blocked"
                if blocked
                else "freellm_routes_awaiting_upstream_availability"
                if deferred
                else None
            )
            query(
                """UPDATE llm_revolver_provider_sources
                   SET status=%s, last_error_code=%s, last_checked_at=NOW(), updated_at=NOW()
                   WHERE id=%s::uuid""",
                (status, error_code, source_id), write=True,
            )
            persist_check(
                source_id, check_kind="direct_route_canary", models_url=None, http_status=None,
                outcome=(
                    "success"
                    if status == "healthy"
                    else "degraded"
                    if ready or deferred
                    else "blocked"
                ),
                model_count=len(models), free_count=len(ready),
                evidence={
                    "ready": ready,
                    "deferred": deferred,
                    "blocked": blocked,
                    "transport": "freellm",
                    "availabilityFailuresAreRetryable": True,
                },
            )
            return jsonify({
                "ok": bool(ready),
                "status": status,
                "transport": "freellm",
                "ready": ready,
                "deferred": deferred,
                "blocked": blocked,
            })
        except ManagedKeyContractError as exc:
            return jsonify({
                "error": "Der verwaltete FreeLLM-Schlüssel konnte nicht sicher gelesen werden.",
                "blocker": exc.code,
            }), 503
        except (OSError, UnicodeDecodeError, ValueError):
            return jsonify({
                "error": "Der verwaltete FreeLLM-Schlüssel konnte nicht sicher gelesen werden.",
                "blocker": "freellm_managed_key_unavailable",
            }), 503
        finally:
            key = ""
            for index in range(len(protected)):
                protected[index] = 0

    @app.route("/api/admin/llm/revolver-v3/providers/<source_id>", methods=["PATCH"])
    @require_admin
    def admin_update_free_revolver_provider(source_id: str):
        try:
            source_id = normalize_provider_source_id(source_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        body = request.get_json(force=True) or {}
        if "enabled" not in body:
            return jsonify({"error": "Nur enabled kann hier geändert werden"}), 400
        enabled = bool(body["enabled"])
        connection = get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE llm_revolver_provider_sources
                       SET enabled=%s, status=CASE WHEN %s THEN 'degraded' ELSE 'disabled' END,
                           updated_at=NOW() WHERE id=%s::uuid RETURNING id::text""",
                    (enabled, enabled, source_id),
                )
                if not cursor.fetchone():
                    connection.rollback()
                    return jsonify({"error": "Free-Provider nicht gefunden"}), 404
                cursor.execute(
                    """UPDATE llm_routes SET disabled=true, updated_at=NOW()
                       WHERE config->>'revolverProviderSourceId'=%s""",
                    (source_id,),
                )
                cursor.execute(
                    """UPDATE llm_revolver_provider_models
                       SET enabled=false,
                           last_error_code=CASE WHEN %s
                               THEN 'provider_recheck_required'
                               ELSE last_error_code END,
                           updated_at=NOW()
                       WHERE source_id=%s::uuid""",
                    (enabled, source_id),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            return jsonify({"error": "Provider-Status konnte nicht atomar geändert werden"}), 500
        finally:
            connection.close()
        audit("admin_free_revolver_provider_toggled", source_id, {"enabled": enabled})
        if enabled:
            evidence_maintainer.request_maintenance(force_discovery=True)
        return jsonify({"ok": True, "sourceId": source_id, "enabled": enabled})

    evidence_maintainer.start()
