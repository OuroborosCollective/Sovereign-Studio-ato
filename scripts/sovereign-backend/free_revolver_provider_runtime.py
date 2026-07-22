"""Evidence-first provider onboarding for the Free Revolver control plane.

The raw provider key is accepted only through owner_input_runtime, used once for
OpenAI-compatible model discovery and private LiteLLM registration, then wiped.
PostgreSQL stores metadata, fingerprints, route state and health evidence only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import uuid
from pathlib import Path
from typing import Any, Callable

import requests
from flask import jsonify, request

from litellm_runtime import fetch_litellm, litellm_completion_canary
from free_revolver_provider_contracts import (
    assert_provider_target_allowed,
    is_managed_internal_provider_url,
    models_url_candidates,
    normalize_api_base,
    normalize_max_auto_activate,
    normalize_models_payload,
    normalize_provider_source_id,
)

_ALIAS_RE = re.compile(r"[^a-z0-9-]+")
_MANAGED_AUTH_MODE = "managed-bearer"
_AUTH_MODES = {"bearer", "x-api-key", "none", _MANAGED_AUTH_MODE}
_MAX_MODELS_RESPONSE_BYTES = 2_000_000


def _owner_root() -> Path:
    return Path(os.getenv("SOVEREIGN_OWNER_INPUT_ROOT", "/opt/sovereign-owner-managed")).resolve()


def _secret_path(owner_request_id: str) -> Path:
    safe_request_id = str(uuid.UUID(str(owner_request_id or "")))
    return _owner_root() / f"revolver_provider_key.{safe_request_id}.txt"


def _managed_secret_path() -> Path:
    root = _owner_root()
    candidate = Path(os.getenv(
        "SOVEREIGN_FREELLMAPI_UNIFIED_KEY_FILE",
        str(root / "freellmapi_unified_key.txt"),
    )).resolve()
    if candidate.parent != root or candidate.name != "freellmapi_unified_key.txt":
        raise RuntimeError("free_provider_managed_secret_path_invalid")
    return candidate


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
                    "Einmalige geschützte Eingabe für Models-Discovery, Nullkostenprüfung und private LiteLLM-Registrierung.",
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
    return {
        "id": str(source.get("id") or ""),
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


def register_free_revolver_provider_runtime(
    app: Any,
    *,
    require_admin: Callable[..., Any],
    query: Callable[..., Any],
    get_connection: Callable[[], Any],
    get_current_admin: Callable[[], dict[str, Any] | None],
    audit: Callable[..., Any],
) -> None:
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
            "truthOwner": "postgresql-owner-input-private-litellm",
            "providers": result,
            "keyStorage": "one-time-owner-input-then-private-litellm",
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
            return jsonify({"error": "Diese API-Basis ist bereits eingetragen", "sourceId": existing["id"]}), 409
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
        litellm_params: dict[str, Any] = {
            "model": f"openai/{model_id}",
            "api_base": str(source["api_base"]),
            "api_key": key if source.get("auth_mode") in {"bearer", _MANAGED_AUTH_MODE} else "",
        }
        if source.get("auth_mode") == "x-api-key":
            litellm_params["extra_headers"] = {"X-API-Key": key}
        registration, registration_error = fetch_litellm(
            "/model/new",
            method="POST",
            json_data={
                "model_name": alias,
                "litellm_params": litellm_params,
                "model_info": {
                    "description": "Sovereign Free Revolver provider-priced route candidate",
                    "metadata": {
                        "sovereign_free_revolver_source_id": source_id,
                        "pricing_source": model["pricingSource"],
                        "discovery_payload_sha256": model["payloadSha256"],
                    },
                },
            },
        )
        litellm_params["api_key"] = ""
        if isinstance(litellm_params.get("extra_headers"), dict):
            litellm_params["extra_headers"]["X-API-Key"] = ""
        if registration_error or registration is None or (not registration.ok and registration.status_code != 409):
            return {"ok": False, "alias": alias, "error": "litellm_model_registration_failed"}
        canary = litellm_completion_canary(alias)
        if not canary.get("ok"):
            return {
                "ok": False,
                "alias": alias,
                "error": "free_provider_canary_failed",
                "blocker": str(canary.get("blocker") or "free_provider_canary_failed"),
            }
        evidence = dict(canary.get("evidence") or {})
        provider_cost = evidence.get("providerCostUsd")
        if provider_cost not in (None, 0, 0.0):
            return {
                "ok": False,
                "alias": alias,
                "error": "free_provider_cost_not_zero",
                "providerCostUsd": provider_cost,
                "canaryCostState": "nonzero",
            }
        canary_cost_state = "zero" if provider_cost in (0, 0.0) else "unreported"
        provider_cost_micros = (
            int(round(float(provider_cost) * 1_000_000))
            if provider_cost is not None
            else None
        )
        route_id = str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"sovereign-free-revolver:{source_id}:{model_id}",
        ))
        quota_scope = f"revolver:key:{str(source.get('key_fingerprint') or '')[:24]}"
        config = {
            "routingOwner": "free-revolver-v3",
            "managedBy": "sovereign-admin",
            "revolverProviderSourceId": source_id,
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
            },
            "revolverEligible": True,
            "executionProfile": "free_single_agent",
            "resolverMode": "revolver",
            "maxForegroundAgents": 1,
            "maxBackgroundAgents": 0,
            "repositoryExecutionAllowed": True,
            "quotaScope": quota_scope,
            "canaryRequestId": evidence.get("upstreamRequestId") or None,
        }
        connection = get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO llm_routes
                           (id, model_id, model_name, provider, base_url, credits_per_unit,
                            disabled, priority, runtime_kind, tier, config, updated_at)
                       VALUES (%s,%s,%s,'litellm','http://litellm:4000',0,
                               false,50,'litellm','free',%s::jsonb,NOW())
                       ON CONFLICT (id) DO UPDATE SET
                           model_id=EXCLUDED.model_id,
                           model_name=EXCLUDED.model_name, provider='litellm',
                           base_url='http://litellm:4000', credits_per_unit=0,
                           disabled=false, runtime_kind='litellm', tier='free',
                           config=EXCLUDED.config, updated_at=NOW()""",
                    (route_id, alias, model["displayName"], json.dumps(config, ensure_ascii=False)),
                )
                cursor.execute(
                    """UPDATE llm_revolver_provider_models
                       SET litellm_alias=%s, status='ready', enabled=true,
                           last_canary_request_id=%s, last_canary_at=NOW(),
                           canary_cost_state=%s, last_provider_cost_usd_micros=%s,
                           last_error_code=NULL, updated_at=NOW()
                       WHERE source_id=%s::uuid AND upstream_model_id=%s""",
                    (
                        alias, str(evidence.get("upstreamRequestId") or "") or None,
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
            return jsonify({"error": "Provider ist deaktiviert oder wird bereits geprüft"}), 409

        protected = bytearray()
        path = (
            _managed_secret_path()
            if source["auth_mode"] == _MANAGED_AUTH_MODE
            else _secret_path(owner_request_id)
            if source["auth_mode"] in {"bearer", "x-api-key"}
            else _owner_root() / ".no-key-provider"
        )
        selected_url = None
        last_status = None
        key = ""
        try:
            if source["auth_mode"] != "none":
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
            models = normalize_models_payload(payload)
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
            blocked = []
            for model in free_models[:max_auto]:
                result = activate_model(dict(source), model, key)
                (activated if result.get("ok") else blocked).append({"modelId": model["modelId"], **result})
                if not result.get("ok"):
                    query(
                        """UPDATE llm_revolver_provider_models
                           SET status='blocked', enabled=false, last_error_code=%s, updated_at=NOW()
                           WHERE source_id=%s::uuid AND upstream_model_id=%s""",
                        (result.get("error"), source_id, model["modelId"]), write=True,
                    )
            status = (
                "healthy"
                if activated and not blocked
                else "degraded"
                if activated or models
                else "blocked"
            )
            error_code = (
                "some_zero_cost_routes_blocked"
                if activated and blocked
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
                    "blockedModels": [item["modelId"] for item in blocked],
                    "pricingRule": "explicit-zero-fields-only",
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
                "blocked": blocked,
                "unverified": [model["modelId"] for model in models if not model["freeVerified"]],
                "keyStoredBy": (
                    "owner-managed-file-and-private-litellm"
                    if source["auth_mode"] == _MANAGED_AUTH_MODE
                    else "private-litellm-only"
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

    @app.route("/api/admin/llm/revolver-v3/providers/<source_id>/recheck", methods=["POST"])
    @require_admin
    def admin_recheck_free_revolver_provider(source_id: str):
        try:
            source_id = normalize_provider_source_id(source_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        models = query(
            """SELECT id::text, upstream_model_id, litellm_alias
               FROM llm_revolver_provider_models
               WHERE source_id=%s::uuid AND free_verified=true
                 AND litellm_alias IS NOT NULL
               ORDER BY display_name ASC LIMIT 100""",
            (source_id,),
        ) or []
        if not models:
            return jsonify({"error": "Keine verifizierten Free-Routen zum Prüfen"}), 409
        ready = []
        blocked = []
        for model in models:
            alias = str(model["litellm_alias"])
            canary = litellm_completion_canary(alias)
            evidence = dict(canary.get("evidence") or {})
            provider_cost = evidence.get("providerCostUsd")
            cost_state = (
                "nonzero"
                if provider_cost not in (None, 0, 0.0)
                else "zero"
                if provider_cost in (0, 0.0)
                else "unreported"
            )
            provider_cost_micros = (
                int(round(float(provider_cost) * 1_000_000))
                if provider_cost is not None
                else None
            )
            blocker = (
                str(canary.get("blocker") or "free_provider_canary_failed")
                if not canary.get("ok")
                else "free_provider_cost_not_zero"
                if cost_state == "nonzero"
                else None
            )
            canary_request_id = str(evidence.get("upstreamRequestId") or "") or None
            if blocker:
                blocked.append(str(model["upstream_model_id"]))
                query(
                    """UPDATE llm_revolver_provider_models
                       SET status='blocked', enabled=false, last_error_code=%s,
                           last_canary_request_id=%s, last_canary_at=NOW(),
                           canary_cost_state=%s, last_provider_cost_usd_micros=%s,
                           updated_at=NOW() WHERE id=%s::uuid""",
                    (
                        blocker, canary_request_id, cost_state,
                        provider_cost_micros, model["id"],
                    ),
                    write=True,
                )
                query(
                    "UPDATE llm_routes SET disabled=true, updated_at=NOW() WHERE model_id=%s",
                    (alias,), write=True,
                )
            else:
                ready.append(str(model["upstream_model_id"]))
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
                           config=jsonb_set(
                               jsonb_set(
                                   config,
                                   '{pricingEvidence,canaryCostState}',
                                   COALESCE(to_jsonb(%s::text), 'null'::jsonb),
                                   true
                               ),
                               '{pricingEvidence,canaryRequestId}',
                               COALESCE(to_jsonb(%s::text), 'null'::jsonb),
                               true
                           ),
                           updated_at=NOW()
                       WHERE model_id=%s""",
                    (cost_state, canary_request_id, alias),
                    write=True,
                )
        status = "healthy" if ready and not blocked else "degraded" if ready else "blocked"
        query(
            """UPDATE llm_revolver_provider_sources
               SET status=%s, last_error_code=%s, last_checked_at=NOW(), updated_at=NOW()
               WHERE id=%s::uuid""",
            (status, "route_canary_failed" if blocked else None, source_id), write=True,
        )
        persist_check(
            source_id, check_kind="route_canary", models_url=None, http_status=None,
            outcome="success" if not blocked else "degraded" if ready else "blocked",
            model_count=len(models), free_count=len(ready),
            evidence={"ready": ready, "blocked": blocked},
        )
        return jsonify({"ok": bool(ready), "status": status, "ready": ready, "blocked": blocked})

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
