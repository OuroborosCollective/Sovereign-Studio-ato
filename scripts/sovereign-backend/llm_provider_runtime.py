"""Owner-gated provider onboarding for the private LiteLLM gateway.

Provider metadata is stored in Sovereign PostgreSQL. The protected provider
value is accepted only by owner_input_runtime and is never stored in this DB.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import urllib.parse
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path
from typing import Any, Callable

from flask import jsonify, request

from litellm_runtime import extract_litellm_evidence, fetch_litellm
from llm_cost_policy import (
    BillingPolicyError,
    FREE_CATEGORY,
    category_minimum_multiplier,
    normalize_billing_category,
    normalized_multiplier,
)


_PROVIDER_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,47}$")
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,199}$")
_ALIAS_RE = re.compile(r"[^a-z0-9-]+")
_DEFAULT_SECRET_ROOT = Path("/opt/sovereign-owner-managed")


def _secret_path() -> Path:
    root = Path(os.getenv("SOVEREIGN_OWNER_INPUT_ROOT", str(_DEFAULT_SECRET_ROOT))).resolve()
    return root / "litellm_provider_key.txt"

# UI metadata only. No preset creates or activates a route.
PROVIDER_PRESETS = (
    {"id": "openai", "label": "OpenAI", "apiBase": "https://api.openai.com/v1"},
    {"id": "anthropic", "label": "Anthropic", "apiBase": ""},
    {"id": "gemini", "label": "Google Gemini", "apiBase": ""},
    {"id": "groq", "label": "Groq", "apiBase": "https://api.groq.com/openai/v1"},
    {"id": "openrouter", "label": "OpenRouter", "apiBase": "https://openrouter.ai/api/v1"},
    {"id": "together_ai", "label": "Together AI", "apiBase": "https://api.together.xyz/v1"},
    {"id": "deepseek", "label": "DeepSeek", "apiBase": "https://api.deepseek.com/v1"},
    {"id": "mistral", "label": "Mistral", "apiBase": "https://api.mistral.ai/v1"},
    {"id": "cerebras", "label": "Cerebras", "apiBase": "https://api.cerebras.ai/v1"},
    {"id": "xai", "label": "xAI", "apiBase": "https://api.x.ai/v1"},
    {"id": "openai_compatible", "label": "Andere OpenAI-kompatible API", "apiBase": ""},
)

BILLING_CATEGORY_OPTIONS = (
    {
        "id": "free",
        "label": "Free · Revolver",
        "minimumMultiplier": 0,
        "description": "Nur bei von LiteLLM bestätigten Providerkosten von exakt 0.",
    },
    {
        "id": "standard",
        "label": "Standard · mindestens ×4",
        "minimumMultiplier": 4,
        "description": "Standardroute mit Vorreservierung und Abrechnung aus echten Providerkosten.",
    },
    {
        "id": "premium",
        "label": "Premium · mindestens ×8",
        "minimumMultiplier": 8,
        "description": "Stärkere/teurere Modelle; Multiplikator kann nur erhöht werden.",
    },
)


def _non_negative_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    return parsed


def _per_token_to_per_million(value: Any) -> Decimal | None:
    parsed = _non_negative_decimal(value)
    return parsed * Decimal(1_000_000) if parsed is not None else None


def _first_cost(source: dict[str, Any], names: tuple[str, ...]) -> Decimal | None:
    for name in names:
        if name in source:
            parsed = _per_token_to_per_million(source.get(name))
            if parsed is not None:
                return parsed
    return None


def _litellm_catalog_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    model_name = str(item.get("model_name") or item.get("model") or "").strip()
    params = item.get("litellm_params") if isinstance(item.get("litellm_params"), dict) else {}
    info = item.get("model_info") if isinstance(item.get("model_info"), dict) else {}
    if not model_name:
        return None
    upstream_model = str(params.get("model") or info.get("key") or model_name).strip()
    sources = (info, params, item)

    def price(names: tuple[str, ...]) -> Decimal | None:
        for source in sources:
            found = _first_cost(source, names)
            if found is not None:
                return found
        return None

    input_price = price(("input_cost_per_token", "input_cost_per_token_batches"))
    output_price = price(("output_cost_per_token", "output_cost_per_token_batches"))
    cached_price = price((
        "cache_read_input_token_cost",
        "cached_input_cost_per_token",
        "cache_input_cost_per_token",
    ))
    pricing_verified = input_price is not None and output_price is not None
    if pricing_verified and cached_price is None:
        cached_price = input_price
    zero_cost = bool(
        pricing_verified
        and input_price == 0
        and output_price == 0
        and cached_price == 0
    )
    provider = str(info.get("litellm_provider") or params.get("custom_llm_provider") or "").strip()
    return {
        "modelId": model_name,
        "providerModel": upstream_model,
        "provider": provider or None,
        "inputUsdPerMillion": float(input_price) if input_price is not None else None,
        "cachedInputUsdPerMillion": float(cached_price) if cached_price is not None else None,
        "outputUsdPerMillion": float(output_price) if output_price is not None else None,
        "pricingVerified": pricing_verified,
        "pricingSource": "litellm-model-info" if pricing_verified else "unavailable",
        "freeEligible": zero_cost,
    }


def _load_litellm_catalog() -> tuple[list[dict[str, Any]], str]:
    response, error = fetch_litellm("/v1/model/info", method="GET")
    if error or response is None:
        return [], error or "litellm_model_catalog_unavailable"
    if not response.ok:
        return [], f"litellm_model_catalog_http_{response.status_code}"
    try:
        payload = response.json()
    except ValueError:
        return [], "litellm_model_catalog_invalid_json"
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    models = [normalized for item in rows if (normalized := _litellm_catalog_item(item))]
    models.sort(key=lambda entry: str(entry["modelId"]).casefold())
    return models, ""


def _catalog_model(model_id: str) -> dict[str, Any] | None:
    models, error = _load_litellm_catalog()
    if error:
        return None
    normalized = str(model_id or "").strip()
    return next((item for item in models if item["modelId"] == normalized), None)


def _validate_category_pricing(
    *,
    category: str,
    model: dict[str, Any],
) -> None:
    if not model.get("pricingVerified"):
        raise BillingPolicyError("LiteLLM hat für dieses Modell keine verifizierten Kosten geliefert")
    if category == FREE_CATEGORY and not model.get("freeEligible"):
        raise BillingPolicyError("Free ist nur bei exakt 0 bestätigten Providerkosten erlaubt")
    if category != FREE_CATEGORY:
        input_price = _non_negative_decimal(model.get("inputUsdPerMillion"))
        output_price = _non_negative_decimal(model.get("outputUsdPerMillion"))
        if input_price is None or output_price is None or input_price <= 0 or output_price <= 0:
            raise BillingPolicyError("Bezahlte Routen benötigen positive verifizierte Providerpreise")


def _slug(value: str, limit: int) -> str:
    normalized = _ALIAS_RE.sub("-", value.strip().lower()).strip("-")
    return (normalized or "provider")[:limit]


def _normalize_api_base(value: Any, prefix: str) -> str | None:
    candidate = str(value or "").strip().rstrip("/")
    if not candidate:
        if prefix == "openai_compatible":
            raise ValueError("Für eine OpenAI-kompatible Fremd-API ist apiBase erforderlich")
        return None
    parsed = urllib.parse.urlsplit(candidate)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("apiBase muss eine vollständige HTTPS-URL sein")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("apiBase darf keine Zugangsdaten oder Fragmente enthalten")
    return candidate


def _normalize_metadata(body: dict[str, Any]) -> dict[str, Any]:
    prefix = str(body.get("providerPrefix") or "").strip().lower()
    upstream_model = str(body.get("modelId") or "").strip()
    display_name = str(body.get("displayName") or upstream_model).strip()[:120]
    if not _PROVIDER_RE.fullmatch(prefix):
        raise ValueError("providerPrefix ist ungültig")
    if not _MODEL_RE.fullmatch(upstream_model):
        raise ValueError("modelId ist ungültig")
    api_base = _normalize_api_base(body.get("apiBase"), prefix)
    try:
        category = normalize_billing_category(body.get("billingCategory") or "premium")
        multiplier = normalized_multiplier(category, body.get("markupMultiplier"))
        priority = int(body.get("priority", 50))
    except BillingPolicyError as exc:
        raise ValueError(str(exc)) from exc
    except (TypeError, ValueError):
        raise ValueError("Multiplikator und Priorität müssen Zahlen sein") from None
    if not -10_000 <= priority <= 10_000:
        raise ValueError("priority liegt außerhalb des erlaubten Bereichs")

    material = f"{prefix}\n{upstream_model}\n{api_base or ''}".encode()
    digest = hashlib.sha256(material).hexdigest()
    alias = f"sovereign-{_slug(prefix, 36)}-{_slug(upstream_model, 24)}-{digest[:8]}"
    return {
        "providerPrefix": prefix,
        "upstreamModel": upstream_model,
        "displayName": display_name or upstream_model,
        "apiBase": api_base,
        "billingCategory": category,
        "markupMultiplier": multiplier,
        "minimumMultiplier": category_minimum_multiplier(category),
        "priority": priority,
        "routeId": f"litellm-admin-{digest[:24]}",
        "alias": alias,
        "litellmModel": f"openai/{upstream_model}" if prefix == "openai_compatible" else f"{prefix}/{upstream_model}",
    }


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


def register_llm_provider_routes(
    app: Any,
    *,
    require_admin: Callable,
    query: Callable[..., Any],
    get_connection: Callable[[], Any],
    get_current_admin: Callable[[], dict[str, Any] | None],
    audit: Callable[[str, str | None, dict[str, Any]], None],
) -> None:
    @app.route("/api/admin/llm/provider-presets", methods=["GET"])
    @require_admin
    def admin_llm_provider_presets():
        return jsonify({
            "providers": list(PROVIDER_PRESETS),
            "billingCategories": list(BILLING_CATEGORY_OPTIONS),
            "createsRoutes": False,
        })

    @app.route("/api/admin/llm/model-catalog", methods=["GET"])
    @require_admin
    def admin_llm_model_catalog():
        models, error = _load_litellm_catalog()
        if error:
            return jsonify({
                "models": [],
                "billingCategories": list(BILLING_CATEGORY_OPTIONS),
                "blocker": error,
                "error": "LiteLLM-Modellkatalog ist nicht verfügbar.",
            }), 503
        return jsonify({
            "models": models,
            "billingCategories": list(BILLING_CATEGORY_OPTIONS),
            "pricingAuthority": "litellm-model-info",
        })

    @app.route("/api/admin/llm/model-catalog/attach", methods=["POST"])
    @require_admin
    def admin_attach_litellm_model():
        body = request.get_json(force=True) or {}
        model_id = str(body.get("modelId") or "").strip()
        if not model_id:
            return jsonify({"error": "modelId fehlt", "blocker": "model_id_required"}), 400
        try:
            category = normalize_billing_category(body.get("billingCategory"))
            multiplier = normalized_multiplier(category, body.get("markupMultiplier"))
            priority = int(body.get("priority", 50))
        except (BillingPolicyError, TypeError, ValueError) as exc:
            return jsonify({"error": str(exc), "blocker": "billing_category_invalid"}), 400
        if not -10_000 <= priority <= 10_000:
            return jsonify({"error": "priority liegt außerhalb des erlaubten Bereichs"}), 400

        model = _catalog_model(model_id)
        if not model:
            return jsonify({
                "error": "Modell ist im aktuellen LiteLLM-Katalog nicht vorhanden.",
                "blocker": "litellm_model_not_found",
            }), 404
        try:
            _validate_category_pricing(category=category, model=model)
        except BillingPolicyError as exc:
            return jsonify({"error": str(exc), "blocker": "litellm_pricing_not_eligible"}), 409

        canary_response, canary_error = fetch_litellm(
            "/v1/chat/completions",
            method="POST",
            json_data={
                "model": model_id,
                "messages": [{"role": "user", "content": "Reply with OK."}],
                "temperature": 0,
                "max_tokens": 8,
                "stream": False,
            },
        )
        if canary_error or canary_response is None or not canary_response.ok:
            return jsonify({
                "error": "Das ausgewählte LiteLLM-Modell hat die echte Completion-Canary nicht bestanden.",
                "blocker": "provider_canary_failed",
            }), 502
        try:
            canary_payload = canary_response.json()
        except ValueError:
            return jsonify({"error": "Provider-Canary lieferte kein gültiges JSON"}), 502
        evidence = extract_litellm_evidence(canary_response, canary_payload)
        if category == FREE_CATEGORY and evidence.get("providerCostUsd") not in (0, 0.0):
            return jsonify({
                "error": "Free-Route wurde abgelehnt: Die Canary bestätigt keine Providerkosten von exakt 0.",
                "blocker": "free_route_nonzero_or_unreported_cost",
                "providerCostUsd": evidence.get("providerCostUsd"),
            }), 409

        display_name = str(body.get("displayName") or model_id).strip()[:120] or model_id
        output_price = Decimal(str(model["outputUsdPerMillion"] or 0))
        credits_per_unit = int(
            (output_price * Decimal(multiplier)).to_integral_value(rounding=ROUND_CEILING)
        ) if multiplier else 0
        config = {
            "routingOwner": "litellm",
            "managedBy": "sovereign-admin",
            "providerModel": model["providerModel"],
            "billingCategory": category,
            "billingClass": category,
            "markupMultiplier": multiplier,
            "minimumMultiplier": category_minimum_multiplier(category),
            "inputUsdPerMillion": model["inputUsdPerMillion"],
            "cachedInputUsdPerMillion": model["cachedInputUsdPerMillion"],
            "outputUsdPerMillion": model["outputUsdPerMillion"],
            "pricingVerified": True,
            "pricingSource": model["pricingSource"],
            "usdMicrosPerCredit": 1000,
            "revolverEligible": category == FREE_CATEGORY,
            "canaryRequestId": evidence.get("upstreamRequestId") or None,
        }
        route_id = f"litellm-catalog-{hashlib.sha256(model_id.encode()).hexdigest()[:24]}"
        connection = get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO llm_routes
                           (id, model_id, model_name, provider, base_url, credits_per_unit,
                            disabled, priority, runtime_kind, tier, config, updated_at)
                       VALUES (%s,%s,%s,'litellm','http://litellm:4000',%s,
                               false,%s,'litellm',%s,%s::jsonb,NOW())
                       ON CONFLICT (model_id) DO UPDATE SET
                           model_name=EXCLUDED.model_name,
                           provider='litellm', base_url='http://litellm:4000',
                           credits_per_unit=EXCLUDED.credits_per_unit,
                           disabled=false, priority=EXCLUDED.priority,
                           runtime_kind='litellm', tier=EXCLUDED.tier,
                           config=EXCLUDED.config, updated_at=NOW()""",
                    (
                        route_id,
                        model_id,
                        display_name,
                        credits_per_unit,
                        priority,
                        category,
                        json.dumps(config, ensure_ascii=False),
                    ),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            return jsonify({
                "error": "LiteLLM-Modell konnte nicht atomar als Sovereign-Route gespeichert werden.",
                "blocker": "route_attach_failed",
            }), 500
        finally:
            connection.close()

        audit("admin_llm_catalog_route_attached", route_id, {
            "modelId": model_id,
            "billingCategory": category,
            "markupMultiplier": multiplier,
            "providerCostUsd": evidence.get("providerCostUsd"),
            "canaryRequestId": evidence.get("upstreamRequestId") or None,
        })
        return jsonify({
            "ok": True,
            "routeId": route_id,
            "modelId": model_id,
            "billingCategory": category,
            "markupMultiplier": multiplier,
            "prices": {
                "inputUsdPerMillion": model["inputUsdPerMillion"],
                "cachedInputUsdPerMillion": model["cachedInputUsdPerMillion"],
                "outputUsdPerMillion": model["outputUsdPerMillion"],
            },
            "providerCostUsd": evidence.get("providerCostUsd"),
            "canaryRequestId": evidence.get("upstreamRequestId") or None,
        }), 201

    @app.route("/api/admin/llm/provider-deployments", methods=["GET"])
    @require_admin
    def admin_llm_provider_deployments():
        rows = query(
            """SELECT route_id AS "routeId", provider_name AS "providerName",
                      provider_prefix AS "providerPrefix", upstream_model_id AS "upstreamModelId",
                      litellm_model_name AS "litellmModelName", api_base AS "apiBase",
                      billing_category AS "billingCategory",
                      markup_multiplier AS "markupMultiplier",
                      input_usd_per_million AS "inputUsdPerMillion",
                      cached_input_usd_per_million AS "cachedInputUsdPerMillion",
                      output_usd_per_million AS "outputUsdPerMillion",
                      pricing_source AS "pricingSource",
                      pricing_verified_at AS "pricingVerifiedAt",
                      key_hint AS "keyHint", status, last_error_code AS "lastErrorCode",
                      last_canary_request_id AS "lastCanaryRequestId",
                      to_char(last_canary_at, 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') AS "lastCanaryAt",
                      owner_request_id::text AS "ownerRequestId"
               FROM llm_provider_deployments ORDER BY updated_at DESC"""
        )
        return jsonify({"deployments": [dict(row) for row in (rows or [])]})

    @app.route("/api/admin/llm/provider-deployments/prepare", methods=["POST"])
    @require_admin
    def admin_prepare_llm_provider():
        try:
            config = _normalize_metadata(request.get_json(force=True) or {})
        except ValueError as exc:
            return jsonify({"error": str(exc), "blocker": "provider_config_invalid"}), 400
        admin = get_current_admin() or {}
        admin_id = str(admin.get("id") or "")
        if not admin_id:
            return jsonify({"error": "Persistenter Admin fehlt"}), 401

        existing = query(
            "SELECT status FROM llm_provider_deployments WHERE route_id=%s LIMIT 1",
            (config["routeId"],), one=True,
        )
        if existing and str(existing.get("status") or "") == "ready":
            return jsonify({"error": "Route ist bereits aktiv", "blocker": "provider_route_exists"}), 409

        connection = get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE owner_input_requests SET status='expired', resolved_at=NOW(), result_code='superseded'
                       WHERE target_id='litellm_provider_key' AND status IN ('pending','processing')"""
                )
                cursor.execute(
                    """INSERT INTO owner_input_requests
                           (target_id, title, reason, field_label, expires_at)
                       VALUES ('litellm_provider_key', %s, %s, 'Provider API-Key', NOW() + INTERVAL '15 minutes')
                       RETURNING id::text""",
                    (
                        f"Providerzugang für {config['displayName']}",
                        f"Einmalig für private LiteLLM-Route {config['alias']}; wird nach Aktivierung gelöscht.",
                    ),
                )
                owner_request_id = str(cursor.fetchone()["id"])
                route_config = {
                    "routingOwner": "litellm",
                    "managedBy": "sovereign-admin",
                    "providerModel": config["litellmModel"],
                    "billingCategory": config["billingCategory"],
                    "billingClass": config["billingCategory"],
                    "markupMultiplier": config["markupMultiplier"],
                    "minimumMultiplier": config["minimumMultiplier"],
                    "pricingVerified": False,
                    "pricingSource": "pending-litellm-registration",
                    "usdMicrosPerCredit": 1000,
                    "revolverEligible": config["billingCategory"] == FREE_CATEGORY,
                }
                cursor.execute(
                    """INSERT INTO llm_routes
                           (id, model_id, model_name, provider, base_url, credits_per_unit,
                            disabled, priority, runtime_kind, tier, config, updated_at)
                       VALUES (%s, %s, %s, 'litellm', 'http://litellm:4000', 0,
                               true, %s, 'litellm', %s, %s::jsonb, NOW())
                       ON CONFLICT (model_id) DO UPDATE SET
                           model_name=EXCLUDED.model_name, provider='litellm',
                           base_url='http://litellm:4000', credits_per_unit=0,
                           disabled=true, priority=EXCLUDED.priority, runtime_kind='litellm',
                           tier=EXCLUDED.tier, config=EXCLUDED.config, updated_at=NOW()""",
                    (
                        config["routeId"], config["alias"], config["displayName"],
                        config["priority"], config["billingCategory"],
                        json.dumps(route_config, ensure_ascii=False),
                    ),
                )
                cursor.execute(
                    """INSERT INTO llm_provider_deployments
                           (route_id, provider_name, provider_prefix, upstream_model_id,
                            litellm_model_name, api_base, owner_request_id, status, created_by,
                            billing_category, markup_multiplier)
                       VALUES (%s,%s,%s,%s,%s,%s,%s::uuid,'awaiting_owner_input',%s::uuid,%s,%s)
                       ON CONFLICT (route_id) DO UPDATE SET
                           provider_name=EXCLUDED.provider_name,
                           provider_prefix=EXCLUDED.provider_prefix,
                           upstream_model_id=EXCLUDED.upstream_model_id,
                           litellm_model_name=EXCLUDED.litellm_model_name,
                           api_base=EXCLUDED.api_base,
                           owner_request_id=EXCLUDED.owner_request_id,
                           billing_category=EXCLUDED.billing_category,
                           markup_multiplier=EXCLUDED.markup_multiplier,
                           input_usd_per_million=NULL,
                           cached_input_usd_per_million=NULL,
                           output_usd_per_million=NULL,
                           pricing_source=NULL,
                           pricing_verified_at=NULL,
                           status='awaiting_owner_input', last_error_code=NULL, updated_at=NOW()""",
                    (
                        config["routeId"], config["displayName"], config["providerPrefix"],
                        config["upstreamModel"], config["alias"], config["apiBase"],
                        owner_request_id, admin_id, config["billingCategory"],
                        config["markupMultiplier"],
                    ),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            return jsonify({"error": "Vorbereitung konnte nicht persistent bestätigt werden"}), 500
        finally:
            connection.close()

        return jsonify({
            "ok": True,
            "status": "awaiting_owner_input",
            "routeId": config["routeId"],
            "billingCategory": config["billingCategory"],
            "markupMultiplier": config["markupMultiplier"],
            "minimumMultiplier": config["minimumMultiplier"],
            "ownerRequestId": owner_request_id,
            "ownerUrl": f"/owner-approvals?request_id={owner_request_id}",
            "nextAction": "Provider-Zugang auf der Owner-Seite sicher eintragen und danach aktivieren.",
        }), 202

    @app.route("/api/admin/llm/provider-deployments/<route_id>/activate", methods=["POST"])
    @require_admin
    def admin_activate_llm_provider(route_id: str):
        deployment = query(
            """SELECT route_id, provider_name, provider_prefix, upstream_model_id,
                      litellm_model_name, api_base, owner_request_id::text AS owner_request_id,
                      billing_category, markup_multiplier, status
               FROM llm_provider_deployments WHERE route_id=%s LIMIT 1""",
            (route_id,), one=True,
        )
        if not deployment:
            return jsonify({"error": "Providerroute nicht gefunden"}), 404
        if str(deployment.get("status") or "") == "ready":
            return jsonify({"ok": True, "status": "ready", "routeId": route_id})
        owner_request_id = str(deployment.get("owner_request_id") or "")
        owner_request = query(
            """SELECT status, target_id FROM owner_input_requests
               WHERE id=%s::uuid LIMIT 1""",
            (owner_request_id,), one=True,
        ) if owner_request_id else None
        if not owner_request or owner_request.get("status") != "consumed" or owner_request.get("target_id") != "litellm_provider_key":
            return jsonify({
                "error": "Geschützter Providerzugang wurde noch nicht bestätigt",
                "blocker": "owner_input_required",
                "ownerRequestId": owner_request_id or None,
            }), 409

        claimed = query(
            """UPDATE llm_provider_deployments
               SET status='provisioning', last_error_code=NULL, updated_at=NOW()
               WHERE route_id=%s AND status IN ('awaiting_owner_input','blocked')
               RETURNING route_id""",
            (route_id,), one=True, write=True,
        )
        if not claimed:
            return jsonify({"error": "Providerroute wird bereits verarbeitet", "blocker": "provider_activation_busy"}), 409

        protected = bytearray()
        path = _secret_path()

        def fail(code: str, message: str, status_code: int = 502):
            query(
                """UPDATE llm_provider_deployments
                   SET status='blocked', last_error_code=%s, updated_at=NOW()
                   WHERE route_id=%s""",
                (code, route_id), write=True,
            )
            query(
                "UPDATE llm_routes SET disabled=true, updated_at=NOW() WHERE id::text=%s",
                (route_id,), write=True,
            )
            return jsonify({"error": message, "blocker": code, "routeId": route_id}), status_code

        try:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
                return fail("provider_secret_permissions_invalid", "Geschützter Providerzugang hat keine sichere Dateiberechtigung", 500)
            if info.st_size < 8 or info.st_size > 8192:
                return fail("provider_secret_invalid", "Geschützter Providerzugang fehlt oder ist ungültig", 400)
            protected = bytearray(path.read_bytes())
            secret_text = protected.decode("utf-8").strip()
            if len(secret_text) < 8:
                return fail("provider_secret_invalid", "Geschützter Providerzugang ist leer", 400)

            alias = str(deployment["litellm_model_name"])
            model_info_response, model_info_error = fetch_litellm("/v1/model/info", method="GET")
            model_present = False
            if not model_info_error and model_info_response is not None and model_info_response.ok:
                try:
                    model_info_payload = model_info_response.json()
                except ValueError:
                    model_info_payload = {}
                model_present = any(
                    isinstance(item, dict)
                    and str(item.get("model_name") or item.get("model") or "").strip() == alias
                    for item in (model_info_payload.get("data", []) if isinstance(model_info_payload, dict) else [])
                )

            registration: dict[str, Any] = {}
            if not model_present:
                params: dict[str, Any] = {
                    "model": (
                        f"openai/{deployment['upstream_model_id']}"
                        if deployment["provider_prefix"] == "openai_compatible"
                        else f"{deployment['provider_prefix']}/{deployment['upstream_model_id']}"
                    ),
                    "api_key": secret_text,
                }
                if deployment.get("api_base"):
                    params["api_base"] = deployment["api_base"]
                register_response, register_error = fetch_litellm(
                    "/model/new",
                    method="POST",
                    json_data={
                        "model_name": alias,
                        "litellm_params": params,
                        "model_info": {
                            "description": "Sovereign owner-managed provider route",
                            "metadata": {"sovereign_route_id": route_id},
                        },
                    },
                )
                params["api_key"] = ""
                if register_error or register_response is None or not register_response.ok:
                    return fail("litellm_model_registration_failed", "LiteLLM konnte die Providerroute nicht persistent registrieren")
                try:
                    parsed_registration = register_response.json()
                except ValueError:
                    parsed_registration = {}
                registration = parsed_registration if isinstance(parsed_registration, dict) else {}

            canary_response, canary_error = fetch_litellm(
                "/v1/chat/completions",
                method="POST",
                json_data={
                    "model": alias,
                    "messages": [{"role": "user", "content": "Reply with OK."}],
                    "temperature": 0,
                    "max_tokens": 8,
                    "stream": False,
                },
            )
            if canary_error or canary_response is None or not canary_response.ok:
                return fail("provider_canary_failed", "Providerroute wurde nicht freigegeben, weil die echte Completion-Canary fehlgeschlagen ist")
            try:
                canary_payload = canary_response.json()
            except ValueError:
                return fail("provider_canary_invalid_json", "Provider-Canary lieferte kein gültiges JSON")
            choices = canary_payload.get("choices", []) if isinstance(canary_payload, dict) else []
            output = ""
            if choices and isinstance(choices[0], dict) and isinstance(choices[0].get("message"), dict):
                output = str(choices[0]["message"].get("content") or "").strip()
            if not output:
                return fail("provider_canary_empty_output", "Provider-Canary lieferte keine Modellantwort")
            evidence = extract_litellm_evidence(canary_response, canary_payload)
            category = normalize_billing_category(deployment.get("billing_category"))
            multiplier = normalized_multiplier(category, deployment.get("markup_multiplier"))
            catalog_model = _catalog_model(alias)
            if not catalog_model:
                return fail(
                    "litellm_pricing_unavailable",
                    "Providerroute wurde nicht freigegeben, weil LiteLLM keine Modellkosten bestätigt hat",
                    409,
                )
            try:
                _validate_category_pricing(category=category, model=catalog_model)
            except BillingPolicyError as exc:
                return fail("litellm_pricing_not_eligible", str(exc), 409)
            if category == FREE_CATEGORY and evidence.get("providerCostUsd") not in (0, 0.0):
                return fail(
                    "free_route_nonzero_or_unreported_cost",
                    "Free-Route wurde abgelehnt: Die echte Canary bestätigt keine Providerkosten von exakt 0",
                    409,
                )

            output_price = Decimal(str(catalog_model["outputUsdPerMillion"] or 0))
            credits_per_unit = int(
                (output_price * Decimal(multiplier)).to_integral_value(rounding=ROUND_CEILING)
            ) if multiplier else 0
            route_config = {
                "providerModel": catalog_model["providerModel"],
                "billingCategory": category,
                "billingClass": category,
                "markupMultiplier": multiplier,
                "minimumMultiplier": category_minimum_multiplier(category),
                "inputUsdPerMillion": catalog_model["inputUsdPerMillion"],
                "cachedInputUsdPerMillion": catalog_model["cachedInputUsdPerMillion"],
                "outputUsdPerMillion": catalog_model["outputUsdPerMillion"],
                "pricingVerified": True,
                "pricingSource": catalog_model["pricingSource"],
                "usdMicrosPerCredit": 1000,
                "revolverEligible": category == FREE_CATEGORY,
                "canaryRequestId": evidence.get("upstreamRequestId") or None,
            }
            key_fingerprint = hashlib.sha256(secret_text.encode()).hexdigest()
            key_hint = f"…{secret_text[-4:]}"
            secret_text = ""

            connection = get_connection()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """UPDATE llm_routes
                           SET provider='litellm', base_url='http://litellm:4000',
                               credits_per_unit=%s, disabled=false, tier=%s,
                               config=COALESCE(config, '{}'::jsonb) || %s::jsonb,
                               updated_at=NOW()
                           WHERE id::text=%s AND model_id=%s""",
                        (
                            credits_per_unit,
                            category,
                            json.dumps(route_config, ensure_ascii=False),
                            route_id,
                            alias,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise RuntimeError("route_activation_missing")
                    cursor.execute(
                        """UPDATE llm_provider_deployments
                           SET status='ready', key_fingerprint=%s, key_hint=%s,
                               litellm_deployment_id=%s, last_canary_request_id=%s,
                               last_canary_at=NOW(), last_error_code=NULL,
                               billing_category=%s, markup_multiplier=%s,
                               input_usd_per_million=%s,
                               cached_input_usd_per_million=%s,
                               output_usd_per_million=%s,
                               pricing_source=%s, pricing_verified_at=NOW(),
                               updated_at=NOW()
                           WHERE route_id=%s""",
                        (
                            key_fingerprint,
                            key_hint,
                            str(registration.get("model_id") or registration.get("id") or "") or None,
                            str(evidence.get("upstreamRequestId") or "") or None,
                            category,
                            multiplier,
                            catalog_model["inputUsdPerMillion"],
                            catalog_model["cachedInputUsdPerMillion"],
                            catalog_model["outputUsdPerMillion"],
                            catalog_model["pricingSource"],
                            route_id,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise RuntimeError("provider_evidence_missing")
                connection.commit()
            except Exception:
                connection.rollback()
                return fail("route_activation_failed", "Canary war erfolgreich, aber die atomare Datenbankfreigabe ist fehlgeschlagen", 500)
            finally:
                connection.close()

            audit("admin_llm_provider_route_created", route_id, {
                "providerPrefix": deployment["provider_prefix"],
                "upstreamModelId": deployment["upstream_model_id"],
                "litellmModelName": alias,
                "billingCategory": category,
                "markupMultiplier": multiplier,
                "keyHint": key_hint,
                "canaryRequestId": evidence.get("upstreamRequestId") or None,
                "canaryTokens": int(evidence.get("totalTokens") or 0),
                "providerCostUsd": evidence.get("providerCostUsd"),
            })
            return jsonify({
                "ok": True,
                "status": "ready",
                "routeId": route_id,
                "modelId": alias,
                "provider": "litellm",
                "billingCategory": category,
                "markupMultiplier": multiplier,
                "prices": {
                    "inputUsdPerMillion": catalog_model["inputUsdPerMillion"],
                    "cachedInputUsdPerMillion": catalog_model["cachedInputUsdPerMillion"],
                    "outputUsdPerMillion": catalog_model["outputUsdPerMillion"],
                },
                "providerCostUsd": evidence.get("providerCostUsd"),
                "keyStoredBy": "litellm-private-database",
                "canaryRequestId": evidence.get("upstreamRequestId") or None,
            })
        except FileNotFoundError:
            return fail("provider_secret_missing", "Geschützter Providerzugang wurde nicht gefunden", 409)
        except UnicodeDecodeError:
            return fail("provider_secret_invalid_encoding", "Geschützter Providerzugang ist nicht als Text lesbar", 400)
        finally:
            for index in range(len(protected)):
                protected[index] = 0
            _securely_remove(path)
