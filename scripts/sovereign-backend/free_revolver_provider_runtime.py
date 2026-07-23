"""Evidence-first direct-provider onboarding for the FreeLLM Revolver control plane.

Managed FreeLLM stays on its private OpenAI-compatible API and never traverses
LiteLLM. PostgreSQL stores route metadata, fingerprints and bounded health
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
    normalize_freellm_provider_id,
    provider_keyless_marker_path,
    provider_secret_path,
    provider_target_id,
)
from free_revolver_provider_contracts import (
    ManagedKeyContractError,
    assert_provider_target_allowed,
    is_managed_internal_provider_url,
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
            "sourceType": confirmations[-1].get("sourceType"),
            "providerId": confirmations[-1].get("providerId"),
            "providerModel": confirmations[-1].get("providerModel"),
            "responseModel": confirmations[-1].get("responseModel"),
            "upstreamKeyless": confirmations[-1].get("upstreamKeyless"),
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
                    "Einmalige geschützte Eingabe für Models-Discovery, Nullkostenprüfung und direkte FreeLLM-Aktivierung.",
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
            "litellmAlias": model.get("litellm_alias"),
            "capabilities": model.get("capabilities") or [],
            "freeVerified": bool(model.get("free_verified")),
            "pricingSource": str(model.get("pricing_source") or "unverified"),
            "pricingVerifiedAt": model.get("pricing_verified_at").isoformat() if model.get("pricing_verified_at") else None,
            "status": str(model.get("status") or "discovered"),
            "lastCanaryRequestId": model.get("last_canary_request_id"),
            "lastCanaryAt": model.get("last_canary_at").isoformat() if model.get("last_canary_at") else None,
            "canaryCostState": str(model.get("canary_cost_state") or "unreported"),
            "lastProviderCostUsdMicros": model.get("last_provider_cost_usd_micros"),
            "lastErrorCode": model.get("last_error_code"),
            "enabled": bool(model.get("enabled")),
        } for model in models],
    }


def _freellm_provider_credential_state(provider_id: str) -> dict[str, Any]:
    spec = FREELLM_PROVIDER_SPECS[provider_id]
    root = _owner_root()
    if bool(spec.get("keyless")):
        marker = provider_keyless_marker_path(root, provider_id)
        enabled = marker.is_file() and not marker.is_symlink()
        return {
            "configured": enabled,
            "mode": "keyless",
            "fingerprintSha256": None,
            "permissionsValid": enabled and stat.S_IMODE(marker.stat().st_mode) & 0o077 == 0,
        }
    path = provider_secret_path(root, provider_id)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {
            "configured": False,
            "mode": "credential",
            "fingerprintSha256": None,
            "permissionsValid": None,
        }
    valid = stat.S_ISREG(info.st_mode) and not path.is_symlink() and not (stat.S_IMODE(info.st_mode) & 0o077)
    fingerprint = None
    if valid and 1 <= info.st_size <= 8192:
        protected = bytearray(path.read_bytes())
        try:
            fingerprint = hashlib.sha256(bytes(protected).strip()).hexdigest()
        finally:
            for index in range(len(protected)):
                protected[index] = 0
    return {
        "configured": bool(valid and fingerprint),
        "mode": "credential",
        "fingerprintSha256": fingerprint,
        "permissionsValid": valid,
    }


def _write_keyless_marker(provider_id: str, enabled: bool) -> None:
    path = provider_keyless_marker_path(_owner_root(), provider_id)
    if not enabled:
        raise ValueError("freellm_keyless_disable_requires_provider_runtime_support")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.geteuid() != 0:
        raise OSError("freellm_keyless_marker_owner_change_requires_root")
    os.chown(path.parent, FREELLM_RUNTIME_UID, FREELLM_RUNTIME_GID)
    os.chmod(path.parent, 0o700)
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


def register_free_revolver_provider_runtime(
    app: Any,
    *,
    require_admin: Callable[..., Any],
    query: Callable[..., Any],
    get_connection: Callable[[], Any],
    get_current_admin: Callable[[], dict[str, Any] | None],
    audit: Callable[..., Any],
) -> None:
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
                          capabilities, free_verified, pricing_source, pricing_verified_at, status,
                          last_canary_request_id, last_canary_at, canary_cost_state,
                          last_provider_cost_usd_micros, last_error_code, enabled
                   FROM llm_revolver_provider_models
                   WHERE source_id=%s::uuid
                   ORDER BY free_verified DESC, display_name ASC""",
                (source["id"],),
            ) or []
            result.append(_source_payload(dict(source), [dict(row) for row in models]))
        return jsonify({
            "ok": True,
            "schemaVersion": "sovereign.free-revolver-provider-admin.v1",
            "truthOwner": "postgresql-owner-input-direct-freellm",
            "providers": result,
            "keyStorage": "owner-managed-direct-freellm",
            "activationRule": "explicit-provider-zero-pricing-and-noncontradictory-canary",
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
            }
        evidence = dict(canary.get("evidence") or {})
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
                "canaryCostState": "nonzero",
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
            "fundingMode": "verified_zero_cost",
            "markupMultiplier": 0,
            "minimumMultiplier": 0,
            "inputUsdPerMillion": 0,
            "cachedInputUsdPerMillion": 0,
            "outputUsdPerMillion": 0,
            "pricingVerified": True,
            "pricingSource": model["pricingSource"],
            "pricingEvidence": {
                "discoveryPayloadSha256": model["payloadSha256"],
                "canaryCostState": canary_cost_state,
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
            "revolverEligible": True,
            "executionProfile": "free_single_agent",
            "resolverMode": "revolver",
            "maxForegroundAgents": 1,
            "maxBackgroundAgents": 0,
            "repositoryExecutionAllowed": True,
            "quotaScope": quota_scope,
            "quotaEvidence": "per-model-runtime-cooldown-and-provider-catalog",
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
                           free_verified=true, pricing_source=%s,
                           pricing_verified_at=NOW(),
                           last_canary_request_id=%s, last_canary_at=NOW(),
                           canary_cost_state=%s, last_provider_cost_usd_micros=%s,
                           last_error_code=NULL, updated_at=NOW()
                       WHERE source_id=%s::uuid AND upstream_model_id=%s""",
                    (
                        alias, model["pricingSource"],
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
            "canaryRequestId": evidence.get("upstreamRequestId") or None,
            "canaryCostState": canary_cost_state,
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
            free_models = [model for model in models if model["freeVerified"]]
            connection = get_connection()
            try:
                with connection.cursor() as cursor:
                    for model in models:
                        cursor.execute(
                            """INSERT INTO llm_revolver_provider_models
                                   (source_id, upstream_model_id, display_name, capabilities,
                                    free_verified, pricing_source, discovery_payload_sha256,
                                    pricing_verified_at, status, enabled, last_seen_at, updated_at)
                               VALUES (
                                   %s::uuid,%s,%s,%s::jsonb,%s,%s,%s,
                                   CASE WHEN %s THEN NOW() ELSE NULL END,
                                   %s,false,NOW(),NOW()
                               )
                               ON CONFLICT (source_id, upstream_model_id) DO UPDATE SET
                                   display_name=EXCLUDED.display_name,
                                   capabilities=EXCLUDED.capabilities,
                                   free_verified=EXCLUDED.free_verified,
                                   pricing_source=EXCLUDED.pricing_source,
                                   discovery_payload_sha256=EXCLUDED.discovery_payload_sha256,
                                   pricing_verified_at=CASE WHEN EXCLUDED.free_verified THEN NOW() ELSE NULL END,
                                   status=CASE WHEN llm_revolver_provider_models.status='ready'
                                               AND EXCLUDED.free_verified THEN 'ready'
                                               WHEN EXCLUDED.free_verified THEN 'discovered'
                                               ELSE 'blocked' END,
                                   enabled=CASE WHEN EXCLUDED.free_verified
                                                THEN llm_revolver_provider_models.enabled
                                                ELSE false END,
                                   last_error_code=CASE WHEN EXCLUDED.free_verified THEN NULL
                                                        ELSE 'provider_pricing_unverified' END,
                                   last_seen_at=NOW(), updated_at=NOW()""",
                            (
                                source_id, model["modelId"], model["displayName"],
                                json.dumps(model["capabilities"]), model["freeVerified"],
                                model["pricingSource"], model["payloadSha256"],
                                model["freeVerified"],
                                "discovered" if model["freeVerified"] else "blocked",
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
                             AND (model.free_verified=false OR model.status='blocked')""",
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

            activated = []
            deferred = []
            blocked = []
            for model in free_models[:max_auto]:
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
            status = (
                "healthy"
                if activated and not blocked and not deferred
                else "degraded"
                if activated or models
                else "blocked"
            )
            error_code = (
                "some_zero_cost_routes_blocked"
                if activated and blocked
                else "some_zero_cost_routes_deferred"
                if activated and deferred
                else None
                if activated
                else "no_zero_cost_route_activated"
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
                outcome="success" if activated else "degraded",
                model_count=len(models),
                free_count=len(free_models),
                evidence={
                    "activatedModels": [item["modelId"] for item in activated],
                    "deferredModels": [item["modelId"] for item in deferred],
                    "blockedModels": [item["modelId"] for item in blocked],
                    "pricingRule": "explicit-zero-fields-only",
                    "availabilityFailuresAreRetryable": True,
                },
            )
            audit("admin_free_revolver_provider_discovered", source_id, {
                "modelsUrl": selected_url,
                "modelCount": len(models),
                "freeVerifiedCount": len(free_models),
                "activatedCount": len(activated),
                "keyHint": key_hint,
            })
            return jsonify({
                "ok": bool(activated),
                "status": status,
                "sourceId": source_id,
                "modelsUrl": selected_url,
                "discovered": len(models),
                "freeVerified": len(free_models),
                "activated": activated,
                "deferred": deferred,
                "blocked": blocked,
                "unverified": [model["modelId"] for model in models if not model["freeVerified"]],
                "keyStoredBy": (
                    "owner-managed-direct-freellm"
                    if source["auth_mode"] == _MANAGED_AUTH_MODE
                    else "ephemeral-discovery-only"
                ),
            }), 200 if activated else 409
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
            eligible_models = [model for model in models if bool(model.get("freeVerified"))]

            bootstrap_stage = "catalog_persistence"
            connection = get_connection()
            try:
                with connection.cursor() as cursor:
                    for model in models:
                        cursor.execute(
                            """INSERT INTO llm_revolver_provider_models
                                   (source_id, upstream_model_id, display_name, capabilities,
                                    free_verified, pricing_source, discovery_payload_sha256,
                                    pricing_verified_at, status, enabled, last_seen_at, updated_at)
                               VALUES (
                                   %s::uuid,%s,%s,%s::jsonb,%s,%s,%s,
                                   CASE WHEN %s THEN NOW() ELSE NULL END,
                                   %s,false,NOW(),NOW()
                               )
                               ON CONFLICT (source_id, upstream_model_id) DO UPDATE SET
                                   display_name=EXCLUDED.display_name,
                                   capabilities=EXCLUDED.capabilities,
                                   free_verified=EXCLUDED.free_verified,
                                   pricing_source=EXCLUDED.pricing_source,
                                   discovery_payload_sha256=EXCLUDED.discovery_payload_sha256,
                                   pricing_verified_at=CASE WHEN EXCLUDED.free_verified THEN NOW() ELSE NULL END,
                                   status=CASE WHEN llm_revolver_provider_models.status='ready'
                                               AND EXCLUDED.free_verified THEN 'ready'
                                               WHEN EXCLUDED.free_verified THEN 'discovered'
                                               ELSE 'blocked' END,
                                   enabled=CASE WHEN EXCLUDED.free_verified
                                                THEN llm_revolver_provider_models.enabled
                                                ELSE false END,
                                   last_error_code=CASE WHEN EXCLUDED.free_verified THEN NULL
                                                        ELSE 'provider_pricing_unverified' END,
                                   last_seen_at=NOW(), updated_at=NOW()""",
                            (
                                source_id,
                                model["modelId"],
                                model["displayName"],
                                json.dumps(model["capabilities"]),
                                model["freeVerified"],
                                model["pricingSource"],
                                model["payloadSha256"],
                                model["freeVerified"],
                                "discovered" if model["freeVerified"] else "blocked",
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
                             AND (model.free_verified=false OR model.status='blocked')""",
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

            bootstrap_stage = "double_canary_activation"
            ready = []
            deferred = []
            blocked = []
            for model in eligible_models[:max_models]:
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
                        "canaryCostState": result.get("canaryCostState"),
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
            status = (
                "healthy"
                if ready and not blocked and not deferred
                else "degraded"
                if ready or models
                else "blocked"
            )
            error_code = (
                "some_freellm_routes_blocked"
                if ready and blocked
                else "some_freellm_routes_deferred"
                if ready and deferred
                else None
                if ready
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
                "ok": bool(ready),
                "status": status,
                "sourceId": source_id,
                "modelsUrl": selected_url,
                "authenticatedCatalogHttpStatus": last_status,
                "keyFingerprintPresent": True,
                "discovered": len(models),
                "eligible": len(eligible_models),
                "ready": ready,
                "deferred": deferred,
                "blocked": blocked,
                "transport": "freellm",
                "executionProfile": "free_single_agent",
                "maxForegroundAgents": 1,
                "maxBackgroundAgents": 0,
                "protectedValuesReturned": False,
                "rawProviderResponsesReturned": False,
            }), 200 if ready else 409
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
                      COUNT(model.id) FILTER (WHERE model.free_verified=true)::int AS free_verified_count,
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
                "freeVerifiedCount": int(source.get("free_verified_count") or 0),
                "readyCount": int(source.get("ready_count") or 0),
            })
        return jsonify({
            "ok": True,
            "status": "FREELLM_PROVIDER_STATUS",
            "providers": providers,
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
        models = query(
            """SELECT id::text, upstream_model_id, display_name, litellm_alias,
                      discovery_payload_sha256, free_verified, pricing_source,
                      status, enabled
               FROM llm_revolver_provider_models
               WHERE source_id=%s::uuid
                 AND last_seen_at >= NOW() - INTERVAL '24 hours'
                 AND (
                     free_verified=true
                     OR (
                         free_verified=false
                         AND pricing_source='provider-pricing-unreported-or-incomplete'
                     )
                 )
               ORDER BY (status='ready' AND enabled=true) DESC,
                        free_verified DESC, display_name ASC
               LIMIT %s""",
            (source_id, max_models),
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
            deferred = []
            blocked = []
            for row in models:
                stored = dict(row)
                model_id = str(stored.get("upstream_model_id") or "")
                pricing_source = str(
                    stored.get("pricing_source")
                    or "provider-pricing-unreported-or-incomplete"
                )
                if not bool(stored.get("free_verified")):
                    pricing_source = "managed-freellm-zero-cost-quota-contract"
                try:
                    result = activate_model(
                        source_payload,
                        {
                            "modelId": model_id,
                            "displayName": str(stored.get("display_name") or model_id),
                            "pricingSource": pricing_source,
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
                        "canaryCostState": result.get("canaryCostState"),
                    })
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
            reconcile_stage = "route_activation_parity"
            query(
                """UPDATE llm_routes AS route
                   SET disabled=NOT (
                           model.status='ready'
                           AND model.enabled=true
                           AND model.free_verified=true
                       ),
                       provider='freellm', runtime_kind='freellm',
                       updated_at=NOW()
                   FROM llm_revolver_provider_models AS model
                   WHERE model.source_id=%s::uuid
                     AND model.litellm_alias IS NOT NULL
                     AND route.model_id=model.litellm_alias
                     AND route.config->>'revolverProviderSourceId'=%s""",
                (source_id, source_id),
                write=True,
            )
            ready_state = query(
                """SELECT
                       COUNT(*) FILTER (
                           WHERE model.status='ready'
                             AND model.enabled=true
                             AND model.free_verified=true
                             AND route.disabled=false
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
                (source_id, source_id),
                one=True,
            ) or {}
            overall_ready_count = int(ready_state.get("ready_count") or 0)
            overall_deferred_count = int(ready_state.get("deferred_count") or 0)
            overall_blocked_count = int(ready_state.get("blocked_count") or 0)
            status = (
                "healthy"
                if overall_ready_count > 0 and overall_blocked_count == 0 and overall_deferred_count == 0
                else "degraded"
                if overall_ready_count > 0 or overall_deferred_count > 0
                else "blocked"
            )
            error_code = (
                "some_freellm_routes_blocked"
                if overall_blocked_count > 0
                else "some_freellm_routes_deferred"
                if overall_deferred_count > 0
                else None
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
                "ok": overall_ready_count > 0,
                "status": status,
                "sourceId": source_id,
                "keyFingerprintPresent": True,
                "readyCount": overall_ready_count,
                "deferredCount": overall_deferred_count,
                "ready": ready,
                "deferred": deferred,
                "blocked": blocked,
                "transport": "freellm",
                "executionProfile": "free_single_agent",
                "maxForegroundAgents": 1,
                "maxBackgroundAgents": 0,
                "protectedValuesReturned": False,
            }), 200 if overall_ready_count > 0 else 409
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
            """SELECT id::text, upstream_model_id, litellm_alias
               FROM llm_revolver_provider_models
               WHERE source_id=%s::uuid AND free_verified=true
                 AND litellm_alias IS NOT NULL
               ORDER BY display_name ASC LIMIT 100""",
            (source_id,),
        ) or []
        if not models:
            return jsonify({
                "error": "Keine healthcheckfähigen Free-Routen vorhanden. Zuerst Discovery und Preisprüfung ausführen.",
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
            for model in models:
                alias = str(model["litellm_alias"])
                canary = _confirmed_completion_canary(
                    api_base=str(source["api_base"]),
                    auth_mode=_MANAGED_AUTH_MODE,
                    key=key,
                    model_id=str(model["upstream_model_id"]),
                )
                evidence = dict(canary.get("evidence") or {})
                raw_costs = evidence.get("providerCostsUsd")
                provider_costs = (
                    [_normalized_provider_cost(value) for value in raw_costs]
                    if isinstance(raw_costs, list) and len(raw_costs) == 2
                    else []
                )
                cost_state = (
                    "nonzero"
                    if provider_costs
                    and any(value not in (None, 0, 0.0) for value in provider_costs)
                    else "zero"
                    if provider_costs
                    and all(value in (0, 0.0) for value in provider_costs)
                    else "unreported"
                )
                provider_cost = provider_costs[-1] if provider_costs else None
                provider_cost_micros = (
                    int(round(float(provider_cost) * 1_000_000))
                    if provider_cost is not None
                    else None
                )
                if not canary.get("ok"):
                    model_status, blocker = _canary_failure_state(canary)
                elif len(provider_costs) != 2:
                    model_status, blocker = (
                        "blocked",
                        "freellm_double_canary_evidence_missing",
                    )
                elif cost_state == "nonzero":
                    model_status, blocker = (
                        "blocked",
                        "free_provider_cost_not_zero",
                    )
                else:
                    model_status, blocker = "ready", None
                canary_request_id = str(evidence.get("upstreamRequestId") or "") or None
                if blocker:
                    target = deferred if model_status == "discovered" else blocked
                    target.append({
                        "modelId": str(model["upstream_model_id"]),
                        "blocker": blocker,
                        "modelStatus": model_status,
                        "failureFamily": canary.get("failureFamily"),
                        "httpStatus": canary.get("httpStatus"),
                    })
                    query(
                        """UPDATE llm_revolver_provider_models
                           SET status=%s, enabled=false, last_error_code=%s,
                               last_canary_request_id=%s, last_canary_at=NOW(),
                               canary_cost_state=%s, last_provider_cost_usd_micros=%s,
                               updated_at=NOW() WHERE id=%s::uuid""",
                        (
                            model_status, blocker, canary_request_id, cost_state,
                            provider_cost_micros, model["id"],
                        ),
                        write=True,
                    )
                    query(
                        "UPDATE llm_routes SET disabled=true, updated_at=NOW() WHERE model_id=%s",
                        (alias,), write=True,
                    )
                else:
                    ready.append({
                        "modelId": str(model["upstream_model_id"]),
                        "sourceType": evidence.get("sourceType"),
                        "providerId": evidence.get("providerId"),
                        "providerModel": evidence.get("providerModel"),
                        "responseModel": evidence.get("responseModel"),
                        "upstreamKeyless": evidence.get("upstreamKeyless"),
                        "canaryConfirmationCount": int(evidence.get("confirmationCount") or 0),
                    })
                    query(
                        """UPDATE llm_revolver_provider_models
                           SET status='ready', enabled=true, last_error_code=NULL,
                               last_canary_request_id=%s, last_canary_at=NOW(),
                               canary_cost_state=%s, last_provider_cost_usd_micros=%s,
                               updated_at=NOW()
                           WHERE id=%s::uuid""",
                        (
                            canary_request_id, cost_state,
                            provider_cost_micros, model["id"],
                        ),
                        write=True,
                    )
                    query(
                        """UPDATE llm_routes
                           SET disabled=false,
                               provider='freellm',
                               runtime_kind='freellm',
                               base_url=%s,
                               config=(
                                   jsonb_set(
                                       jsonb_set(
                                           config,
                                           '{pricingEvidence,canaryCostState}',
                                           COALESCE(to_jsonb(%s::text), 'null'::jsonb),
                                           true
                                       ),
                                       '{pricingEvidence,canaryRequestId}',
                                       COALESCE(to_jsonb(%s::text), 'null'::jsonb),
                                       true
                                   )
                                   || jsonb_build_object(
                                       'transport', 'freellm',
                                       'direct', true,
                                       'canaryVerified', true
                                   )
                               ),
                               updated_at=NOW()
                           WHERE model_id=%s""",
                        (
                            str(source["api_base"]).rstrip("/"),
                            cost_state,
                            canary_request_id,
                            alias,
                        ),
                        write=True,
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
        return jsonify({"ok": True, "sourceId": source_id, "enabled": enabled})
