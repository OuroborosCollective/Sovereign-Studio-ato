"""Direct OpenRouter credential, catalog, pricing, and activation runtime.

The protected API key is written by the existing owner-input surface to an
allowlisted 0600 file.  This module never returns, logs, or persists that value.
PostgreSQL stores only a fingerprint, hint, bounded canary evidence, model
metadata, and immutable price snapshots.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path
from typing import Any, Callable, Iterator

import requests
from flask import jsonify, request

from llm_transport import OPENROUTER_BASE_URL


ConnectionFactory = Callable[[], Any]
OPENROUTER_OWNER_TARGET = "openrouter_api_key"
OPENROUTER_ROOT_ROUTE_ID = "openrouter-paid-gpt-5-4-mini"
OPENROUTER_DEFAULT_MODEL = "openai/gpt-5.4-mini"
_OWNER_ROOT = Path("/opt/sovereign-owner-managed")
_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{1,239}$")
_MAX_CATALOG_BYTES = 16_000_000
_MAX_MODELS = 700
_MAX_AGENT_CANARY_CANDIDATES = 12
_MARKUP_MULTIPLIER = 4
_PROVIDER_POLICY = {
    "require_parameters": True,
    "allow_fallbacks": False,
    "data_collection": "deny",
    "zdr": True,
}
_REQUIRED_AGENT_PARAMETERS = frozenset({"tools", "tool_choice"})
_REQUIRED_CANARY_PARAMETERS = frozenset({"tools", "tool_choice", "max_tokens"})
_STRUCTURED_PARAMETERS = frozenset({"response_format", "structured_outputs"})
_MODEL_POLICY_REJECTION_FAMILIES = frozenset({
    "openrouter_no_provider_meets_policy",
    "openrouter_invalid_request",
    "openrouter_provider_unavailable",
    "openrouter_zdr_agent_canary_rejected",
})


class OpenRouterRuntimeError(RuntimeError):
    def __init__(self, family: str, *, status_code: int = 503) -> None:
        super().__init__(family)
        self.family = str(family)[:120]
        self.status_code = int(status_code)


def _owner_root() -> Path:
    return Path(os.getenv("SOVEREIGN_OWNER_INPUT_ROOT", str(_OWNER_ROOT))).resolve()


def _key_path() -> Path:
    root = _owner_root()
    candidate = Path(
        os.getenv(
            "SOVEREIGN_OPENROUTER_API_KEY_FILE",
            str(root / "openrouter_api_key.txt"),
        )
    ).resolve()
    if candidate.parent != root or candidate.name != "openrouter_api_key.txt":
        raise OpenRouterRuntimeError("openrouter_secret_path_invalid", status_code=500)
    return candidate


@contextmanager
def _protected_key() -> Iterator[str]:
    path = _key_path()
    protected = bytearray()
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
            raise OpenRouterRuntimeError(
                "openrouter_secret_permissions_invalid", status_code=500
            )
        if info.st_size < 16 or info.st_size > 8192:
            raise OpenRouterRuntimeError("openrouter_secret_invalid", status_code=409)
        protected = bytearray(path.read_bytes())
        key = protected.decode("utf-8").strip()
        if len(key) < 16 or any(character.isspace() for character in key):
            raise OpenRouterRuntimeError("openrouter_secret_invalid", status_code=409)
        yield key
    except FileNotFoundError as exc:
        raise OpenRouterRuntimeError("openrouter_secret_missing", status_code=409) from exc
    except UnicodeDecodeError as exc:
        raise OpenRouterRuntimeError(
            "openrouter_secret_invalid_encoding", status_code=409
        ) from exc
    finally:
        for index in range(len(protected)):
            protected[index] = 0


def _close(connection: Any) -> None:
    close = getattr(connection, "close", None)
    if callable(close):
        close()


def _decimal(value: Any) -> Decimal | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    return parsed


def _per_million(value: Any) -> str | None:
    parsed = _decimal(value)
    if parsed is None:
        return None
    result = parsed * Decimal(1_000_000)
    return format(result.normalize(), "f")


def _bounded_nonnegative_int(value: Any) -> int:
    if value in (None, "") or isinstance(value, bool):
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, parsed)


def _credits_per_thousand(
    output_usd_per_million: str,
    multiplier: int = _MARKUP_MULTIPLIER,
) -> int:
    value = Decimal(output_usd_per_million) * Decimal(max(_MARKUP_MULTIPLIER, multiplier))
    return max(1, int(value.to_integral_value(rounding=ROUND_CEILING)))


def _request_headers(key: str) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "sovereign-studio-openrouter/1",
    }
    referer = os.getenv("SOVEREIGN_OPENROUTER_HTTP_REFERER", "").strip()
    title = os.getenv("SOVEREIGN_OPENROUTER_APP_TITLE", "Sovereign Studio").strip()
    if referer:
        headers["HTTP-Referer"] = referer[:500]
    if title:
        headers["X-OpenRouter-Title"] = title[:200]
    return headers


def _bounded_json_response(response: requests.Response, *, limit: int) -> Any:
    content_length = int(response.headers.get("Content-Length") or 0)
    if content_length > limit:
        raise OpenRouterRuntimeError("openrouter_response_too_large")
    raw = response.raw.read(limit + 1, decode_content=True)
    if len(raw) > limit:
        raise OpenRouterRuntimeError("openrouter_response_too_large")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OpenRouterRuntimeError("openrouter_response_invalid_json") from exc


def _safe_openrouter_error_token(value: Any) -> str:
    token = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
    return token[:60]


def _openrouter_error_family(response: requests.Response) -> str:
    """Map bounded typed OpenRouter errors without retaining raw messages."""

    status = int(response.status_code)
    try:
        payload = _bounded_json_response(response, limit=65_536)
    except OpenRouterRuntimeError:
        payload = {}
    error = payload.get("error") if isinstance(payload, dict) else None
    error = error if isinstance(error, dict) else {}
    metadata = error.get("metadata") if isinstance(error.get("metadata"), dict) else {}
    error_type = _safe_openrouter_error_token(metadata.get("error_type"))
    provider_code = _safe_openrouter_error_token(metadata.get("provider_code"))

    if status == 404:
        return "openrouter_no_provider_meets_policy"
    if error_type:
        return f"openrouter_{error_type}"[:120]
    if provider_code:
        return f"openrouter_provider_{provider_code}"[:120]
    return {
        400: "openrouter_invalid_request",
        408: "openrouter_timeout",
        502: "openrouter_provider_unavailable",
        503: "openrouter_provider_unavailable",
    }.get(status, "openrouter_zdr_agent_canary_rejected")


def _fetch_models(key: str) -> tuple[list[dict[str, Any]], str]:
    endpoint = f"{OPENROUTER_BASE_URL}/models"
    try:
        with requests.Session() as session:
            session.trust_env = False
            with session.get(
                endpoint,
                headers=_request_headers(key),
                timeout=30,
                allow_redirects=False,
                stream=True,
            ) as response:
                if response.status_code in {401, 403}:
                    raise OpenRouterRuntimeError(
                        "openrouter_credentials_rejected", status_code=401
                    )
                if response.status_code == 429:
                    raise OpenRouterRuntimeError("openrouter_rate_limited", status_code=429)
                if response.status_code >= 400:
                    raise OpenRouterRuntimeError(
                        "openrouter_catalog_unavailable", status_code=503
                    )
                payload = _bounded_json_response(response, limit=_MAX_CATALOG_BYTES)
                request_id = str(
                    response.headers.get("x-request-id")
                    or response.headers.get("X-Request-Id")
                    or ""
                )[:200]
    except requests.Timeout as exc:
        raise OpenRouterRuntimeError("openrouter_timeout") from exc
    except requests.RequestException as exc:
        raise OpenRouterRuntimeError("openrouter_catalog_unavailable") from exc
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise OpenRouterRuntimeError("openrouter_catalog_invalid")
    return [row for row in rows[:_MAX_MODELS] if isinstance(row, dict)], request_id


def _fetch_agent_models(key: str) -> tuple[dict[str, dict[str, Any]], str]:
    endpoint = f"{OPENROUTER_BASE_URL}/models"
    try:
        with requests.Session() as session:
            session.trust_env = False
            with session.get(
                endpoint,
                headers=_request_headers(key),
                timeout=30,
                allow_redirects=False,
                stream=True,
            ) as response:
                if response.status_code in {401, 403}:
                    raise OpenRouterRuntimeError(
                        "openrouter_credentials_rejected", status_code=401
                    )
                if response.status_code == 429:
                    raise OpenRouterRuntimeError("openrouter_rate_limited", status_code=429)
                if response.status_code >= 400:
                    raise OpenRouterRuntimeError(
                        "openrouter_agent_catalog_unavailable", status_code=503
                    )
                payload = _bounded_json_response(response, limit=_MAX_CATALOG_BYTES)
                request_id = str(
                    response.headers.get("x-request-id")
                    or response.headers.get("X-Request-Id")
                    or ""
                )[:200]
    except requests.Timeout as exc:
        raise OpenRouterRuntimeError("openrouter_timeout") from exc
    except requests.RequestException as exc:
        raise OpenRouterRuntimeError("openrouter_agent_catalog_unavailable") from exc

    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise OpenRouterRuntimeError("openrouter_agent_catalog_invalid")
    eligible: dict[str, dict[str, Any]] = {}
    for item in rows[:_MAX_MODELS * 10]:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or item.get("model_id") or "").strip()
        supported = {
            str(value).strip()
            for value in (item.get("supported_parameters") or [])
            if str(value).strip()
        }
        pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
        input_price = _per_million(pricing.get("prompt"))
        output_price = _per_million(pricing.get("completion"))
        if (
            not _MODEL_ID_RE.fullmatch(model_id)
            or model_id.endswith(":free")
            or not _REQUIRED_CANARY_PARAMETERS.issubset(supported)
            or input_price is None
            or output_price is None
            or Decimal(input_price) <= 0
            or Decimal(output_price) <= 0
        ):
            continue
        candidate = {
            "modelId": model_id,
            "providerName": str(item.get("provider_name") or "OpenRouter")[:120],
            "inputUsdPerMillion": input_price,
            "outputUsdPerMillion": output_price,
            "supportedParameters": sorted(supported),
        }
        current = eligible.get(model_id)
        if current is None or (
            Decimal(candidate["outputUsdPerMillion"]),
            Decimal(candidate["inputUsdPerMillion"]),
            candidate["providerName"].casefold(),
        ) < (
            Decimal(current["outputUsdPerMillion"]),
            Decimal(current["inputUsdPerMillion"]),
            current["providerName"].casefold(),
        ):
            eligible[model_id] = candidate
    if not eligible:
        raise OpenRouterRuntimeError("openrouter_agent_catalog_empty")
    return eligible, request_id


def _ordered_agent_canary_models(endpoints: dict[str, dict[str, Any]]) -> list[str]:
    ordered = [
        item["modelId"]
        for item in sorted(
            endpoints.values(),
            key=lambda item: (
                Decimal(item["outputUsdPerMillion"]),
                Decimal(item["inputUsdPerMillion"]),
                item["modelId"].casefold(),
            ),
        )
    ]
    if OPENROUTER_DEFAULT_MODEL in endpoints:
        ordered = [OPENROUTER_DEFAULT_MODEL] + [
            model_id for model_id in ordered if model_id != OPENROUTER_DEFAULT_MODEL
        ]
    return ordered[:_MAX_AGENT_CANARY_CANDIDATES]


def _select_agent_canary_model(endpoints: dict[str, dict[str, Any]]) -> str:
    ordered = _ordered_agent_canary_models(endpoints)
    if not ordered:
        raise OpenRouterRuntimeError("openrouter_agent_catalog_empty")
    return ordered[0]


def _normalize_model(item: dict[str, Any]) -> dict[str, Any] | None:
    model_id = str(item.get("id") or "").strip()
    if not _MODEL_ID_RE.fullmatch(model_id) or model_id.endswith(":free"):
        return None
    if model_id.startswith("openrouter/"):
        return None
    pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
    input_price = _per_million(pricing.get("prompt"))
    output_price = _per_million(pricing.get("completion"))
    cached_price = _per_million(
        pricing.get("input_cache_read", pricing.get("cached_prompt", pricing.get("cache_read")))
    )
    if input_price is None or output_price is None:
        return None
    if Decimal(input_price) <= 0 or Decimal(output_price) <= 0:
        return None
    if cached_price is None:
        cached_price = input_price
    if Decimal(cached_price) > Decimal(input_price):
        cached_price = input_price

    supported = {
        str(value).strip()
        for value in (item.get("supported_parameters") or [])
        if str(value).strip()
    }
    if not _REQUIRED_AGENT_PARAMETERS.issubset(supported):
        return None
    if not (_STRUCTURED_PARAMETERS & supported):
        return None
    architecture = item.get("architecture") if isinstance(item.get("architecture"), dict) else {}
    inputs = {str(value) for value in (architecture.get("input_modalities") or [])}
    outputs = {str(value) for value in (architecture.get("output_modalities") or [])}
    if inputs and "text" not in inputs:
        return None
    if outputs and "text" not in outputs:
        return None

    canonical = str(item.get("canonical_slug") or model_id).strip()[:260]
    name = str(item.get("name") or model_id).strip()[:180] or model_id
    context_length = _bounded_nonnegative_int(item.get("context_length"))
    top_provider = item.get("top_provider") if isinstance(item.get("top_provider"), dict) else {}
    max_completion = _bounded_nonnegative_int(top_provider.get("max_completion_tokens"))
    payload_hash = hashlib.sha256(
        json.dumps(item, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "modelId": model_id,
        "canonicalModelSlug": canonical,
        "displayName": name,
        "contextLength": context_length,
        "maxCompletionTokens": max_completion,
        "inputUsdPerMillion": input_price,
        "cachedInputUsdPerMillion": cached_price,
        "outputUsdPerMillion": output_price,
        "supportedParameters": sorted(supported),
        "priceOverridesPresent": bool(pricing.get("overrides")),
        "payloadSha256": payload_hash,
    }


def _route_id(model_id: str, *, default_model: str = OPENROUTER_DEFAULT_MODEL) -> str:
    if model_id == default_model:
        return OPENROUTER_ROOT_ROUTE_ID
    digest = hashlib.sha256(model_id.encode()).hexdigest()[:32]
    return f"openrouter-paid-{digest}"


def _catalog_hash(models: list[dict[str, Any]]) -> str:
    payload = [
        {
            "id": model["modelId"],
            "canonical": model["canonicalModelSlug"],
            "input": model["inputUsdPerMillion"],
            "cached": model["cachedInputUsdPerMillion"],
            "output": model["outputUsdPerMillion"],
            "payload": model["payloadSha256"],
        }
        for model in models
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _completion_canary(key: str, *, model_id: str) -> dict[str, Any]:
    endpoint = f"{OPENROUTER_BASE_URL}/chat/completions"
    body = {
        "model": model_id,
        "messages": [
            {
                "role": "user",
                "content": "Call canary_ok once with value OK and do not disclose credentials.",
            }
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "canary_ok",
                    "description": "Return a bounded activation proof.",
                    "parameters": {
                        "type": "object",
                        "properties": {"value": {"type": "string"}},
                        "required": ["value"],
                        "additionalProperties": False,
                    },
                },
            }
        ],
        "tool_choice": {"type": "function", "function": {"name": "canary_ok"}},
        "max_tokens": 64,
        "provider": dict(_PROVIDER_POLICY),
        "stream": False,
    }
    try:
        with requests.Session() as session:
            session.trust_env = False
            with session.post(
                endpoint,
                headers=_request_headers(key),
                json=body,
                timeout=45,
                allow_redirects=False,
                stream=True,
            ) as response:
                status = int(response.status_code)
                request_id = str(
                    response.headers.get("x-request-id")
                    or response.headers.get("X-Request-Id")
                    or ""
                )[:200]
                if status in {401, 403}:
                    raise OpenRouterRuntimeError(
                        "openrouter_credentials_rejected", status_code=401
                    )
                if status == 402:
                    raise OpenRouterRuntimeError(
                        "openrouter_account_credits_required", status_code=402
                    )
                if status == 429:
                    raise OpenRouterRuntimeError("openrouter_rate_limited", status_code=429)
                if status >= 400:
                    raise OpenRouterRuntimeError(
                        _openrouter_error_family(response), status_code=503
                    )
                payload = _bounded_json_response(response, limit=1_000_000)
    except requests.Timeout as exc:
        raise OpenRouterRuntimeError("openrouter_timeout") from exc
    except requests.RequestException as exc:
        raise OpenRouterRuntimeError("openrouter_upstream_unavailable") from exc
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not isinstance(choices, list) or not choices:
        raise OpenRouterRuntimeError("openrouter_canary_response_invalid")
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    return {
        "requestId": str(payload.get("id") or request_id or "")[:200] or None,
        "providerCostUsd": usage.get("cost"),
        "httpStatus": status,
        "modelId": model_id,
        "providerPolicySha256": hashlib.sha256(
            json.dumps(_PROVIDER_POLICY, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "rawResponsePersisted": False,
    }


def _completion_canary_with_rotation(
    key: str,
    *,
    agent_models: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    rejected_families: list[str] = []
    for model_id in _ordered_agent_canary_models(agent_models):
        try:
            canary = _completion_canary(key, model_id=model_id)
            return {
                **canary,
                "attemptedModelCount": len(rejected_families) + 1,
                "rejectedPolicyFamilies": sorted(set(rejected_families)),
            }
        except OpenRouterRuntimeError as exc:
            if exc.family not in _MODEL_POLICY_REJECTION_FAMILIES:
                raise
            rejected_families.append(exc.family)
    if rejected_families:
        raise OpenRouterRuntimeError("openrouter_no_eligible_policy_provider")
    raise OpenRouterRuntimeError("openrouter_agent_catalog_empty")


def _sync_catalog(
    get_connection: ConnectionFactory,
    *,
    key: str,
    key_fingerprint: str,
    key_hint: str,
    canary: dict[str, Any],
    agent_models: dict[str, dict[str, Any]],
    agent_catalog_request_id: str,
) -> dict[str, Any]:
    rows, catalog_request_id = _fetch_models(key)
    models = [
        model
        for row in rows
        if (model := _normalize_model(row))
        and model["modelId"] in agent_models
    ]
    default_model = str(canary.get("modelId") or "")
    if not models or not any(model["modelId"] == default_model for model in models):
        raise OpenRouterRuntimeError("openrouter_agent_catalog_empty")
    models.sort(
        key=lambda model: (
            Decimal(model["outputUsdPerMillion"]),
            Decimal(model["inputUsdPerMillion"]),
            model["modelId"].casefold(),
        )
    )
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    catalog_sha = _catalog_hash(models)
    model_ids: list[str] = []
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            for priority, model in enumerate(models, start=100):
                model_id = str(model["modelId"])
                route_priority = 10 if model_id == default_model else priority
                model_ids.append(f"sovereign-openrouter:{model_id}")
                config = {
                    "transport": "openrouter",
                    "direct": True,
                    "providerModel": model_id,
                    "canonicalModelSlug": model["canonicalModelSlug"],
                    "billingCategory": "standard",
                    "billingClass": "standard",
                    "markupMultiplier": _MARKUP_MULTIPLIER,
                    "minimumMultiplier": _MARKUP_MULTIPLIER,
                    "fundingMode": "provider_priced",
                    "inputUsdPerMillion": model["inputUsdPerMillion"],
                    "cachedInputUsdPerMillion": model["cachedInputUsdPerMillion"],
                    "outputUsdPerMillion": model["outputUsdPerMillion"],
                    "pricingVerified": True,
                    "pricingSource": f"openrouter-models-api:{now}",
                    "pricingAuthority": "openrouter-models-api",
                    "priceOverridesPresent": model["priceOverridesPresent"],
                    "usdMicrosPerCredit": 1000,
                    "executionProfile": "paid_swarm_6",
                    "supportedExecutionRoles": ["main", "swarm_agents"],
                    "resolverMode": "selected-pair",
                    "maxForegroundAgents": 1,
                    "maxBackgroundAgents": 6,
                    "repositoryExecutionAllowed": True,
                    "quotaScope": f"openrouter:model:{hashlib.sha256(model_id.encode()).hexdigest()[:24]}",
                    "providerPolicy": dict(_PROVIDER_POLICY),
                    "agentModelVerified": True,
                    "agentModelProvider": agent_models[model_id]["providerName"],
                    "agentCatalogRequestId": agent_catalog_request_id or None,
                    "catalogVerified": True,
                    "catalogPayloadSha256": model["payloadSha256"],
                    "catalogSnapshotSha256": catalog_sha,
                    "transportCanaryVerified": True,
                    "canaryVerified": True,
                    "canaryRequestId": canary.get("requestId"),
                    "canaryProviderPolicySha256": canary["providerPolicySha256"],
                    "contextLength": model["contextLength"],
                    "maxCompletionTokens": model["maxCompletionTokens"],
                    "supportedParameters": model["supportedParameters"],
                    "selectable": True,
                    "activationState": "ready",
                }
                cursor.execute(
                    """INSERT INTO llm_routes
                           (id, model_id, model_name, provider, base_url,
                            credits_per_unit, disabled, priority, runtime_kind,
                            tier, config, updated_at)
                       VALUES (%s,%s,%s,'openrouter',%s,%s,false,%s,
                               'openrouter','standard',%s::jsonb,NOW())
                       ON CONFLICT (id) DO UPDATE SET
                           model_id=EXCLUDED.model_id,
                           model_name=EXCLUDED.model_name,
                           provider='openrouter', base_url=EXCLUDED.base_url,
                           credits_per_unit=EXCLUDED.credits_per_unit,
                           disabled=false, priority=EXCLUDED.priority,
                           runtime_kind='openrouter', tier='standard',
                           credits_per_unit=GREATEST(
                               1,
                               CEIL(
                                   (EXCLUDED.config->>'outputUsdPerMillion')::numeric
                                   * GREATEST(
                                       4,
                                       CASE
                                           WHEN COALESCE(llm_routes.config->>'markupMultiplier', '')
                                                ~ '^[0-9]+$'
                                           THEN (llm_routes.config->>'markupMultiplier')::integer
                                           ELSE 4
                                       END
                                   )
                               )::integer
                           ),
                           config=EXCLUDED.config || jsonb_build_object(
                               'markupMultiplier',
                               GREATEST(
                                   4,
                                   CASE
                                       WHEN COALESCE(llm_routes.config->>'markupMultiplier', '')
                                            ~ '^[0-9]+$'
                                       THEN (llm_routes.config->>'markupMultiplier')::integer
                                       ELSE 4
                                   END
                               )
                           ),
                           updated_at=NOW()""",
                    (
                        _route_id(model_id, default_model=default_model),
                        f"sovereign-openrouter:{model_id}",
                        model["displayName"],
                        OPENROUTER_BASE_URL,
                        _credits_per_thousand(model["outputUsdPerMillion"]),
                        route_priority,
                        json.dumps(config, ensure_ascii=True),
                    ),
                )
            cursor.execute(
                """UPDATE llm_routes
                   SET disabled=true,
                       config=COALESCE(config, '{}'::jsonb)
                              || '{"selectable":false,"activationState":"missing-from-current-catalog"}'::jsonb,
                       updated_at=NOW()
                   WHERE lower(COALESCE(runtime_kind, provider))='openrouter'
                     AND NOT (model_id = ANY(%s))""",
                (model_ids,),
            )
            cursor.execute(
                """UPDATE llm_provider_deployments
                   SET status='ready', key_fingerprint=%s, key_hint=%s,
                       last_canary_request_id=%s, last_canary_at=NOW(),
                       last_error_code=NULL, litellm_deployment_id=NULL,
                       updated_at=NOW()
                   WHERE route_id=%s""",
                (
                    key_fingerprint,
                    key_hint,
                    canary.get("requestId"),
                    OPENROUTER_ROOT_ROUTE_ID,
                ),
            )
            if cursor.rowcount != 1:
                raise OpenRouterRuntimeError(
                    "openrouter_root_deployment_missing", status_code=409
                )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        _close(connection)
    return {
        "modelCount": len(models),
        "catalogSnapshotSha256": catalog_sha,
        "catalogRequestId": catalog_request_id or None,
        "defaultModel": default_model,
        "agentCatalogRequestId": agent_catalog_request_id or None,
    }


def _mark_blocked(
    query: Callable[..., Any],
    *,
    route_id: str,
    family: str,
) -> None:
    try:
        query(
            """UPDATE llm_provider_deployments
               SET status='blocked', last_error_code=%s, updated_at=NOW()
               WHERE route_id=%s""",
            (str(family)[:120], route_id),
            write=True,
        )
        query(
            "UPDATE llm_routes SET disabled=true, updated_at=NOW() WHERE id=%s",
            (route_id,),
            write=True,
        )
    except Exception:
        return


def activate_openrouter_provider(
    route_id: str,
    *,
    query: Callable[..., Any],
    get_connection: ConnectionFactory,
    audit: Callable[[str, str | None, dict[str, Any]], None],
):
    """Activate the direct OpenRouter transport from a protected owner value."""

    normalized_route = str(route_id or "").strip()
    if normalized_route != OPENROUTER_ROOT_ROUTE_ID:
        return jsonify({"error": "OpenRouter-Aktivierungsroute unbekannt"}), 404
    deployment = query(
        """SELECT deployment.status, deployment.key_fingerprint,
                  deployment.owner_request_id::text AS owner_request_id,
                  route.disabled AS route_disabled
           FROM llm_provider_deployments AS deployment
           JOIN llm_routes AS route ON route.id=deployment.route_id
           WHERE deployment.route_id=%s LIMIT 1""",
        (normalized_route,),
        one=True,
    )
    if not deployment:
        return jsonify({"error": "OpenRouter-Aktivierungsroute fehlt"}), 404
    owner_request = query(
        """SELECT id::text, status, target_id
           FROM owner_input_requests
           WHERE target_id=%s AND status='consumed'
           ORDER BY consumed_at DESC NULLS LAST, resolved_at DESC
           LIMIT 1""",
        (OPENROUTER_OWNER_TARGET,),
        one=True,
    )
    previously_authorized = bool(deployment.get("key_fingerprint"))
    if not previously_authorized and (
        not owner_request
        or owner_request.get("status") != "consumed"
        or owner_request.get("target_id") != OPENROUTER_OWNER_TARGET
    ):
        return jsonify(
            {
                "error": "Geschützter OpenRouter-Zugang wurde noch nicht bestätigt",
                "blocker": "openrouter_owner_input_required",
                "secretValuesReturned": False,
            }
        ), 409

    try:
        with _protected_key() as key:
            key_fingerprint = hashlib.sha256(key.encode()).hexdigest()
            key_hint = f"…{key[-4:]}"
            agent_models, agent_catalog_request_id = _fetch_agent_models(key)
            canary = _completion_canary_with_rotation(
                key,
                agent_models=agent_models,
            )
            catalog = _sync_catalog(
                get_connection,
                key=key,
                key_fingerprint=key_fingerprint,
                key_hint=key_hint,
                canary=canary,
                agent_models=agent_models,
                agent_catalog_request_id=agent_catalog_request_id,
            )
    except OpenRouterRuntimeError as exc:
        _mark_blocked(query, route_id=normalized_route, family=exc.family)
        return jsonify(
            {
                "ok": False,
                "status": "blocked",
                "blocker": exc.family,
                "secretValuesReturned": False,
            }
        ), exc.status_code
    except Exception as exc:
        error_type = _safe_openrouter_error_token(type(exc).__name__) or "unknown"
        family = f"openrouter_activation_{error_type}"[:120]
        _mark_blocked(
            query,
            route_id=normalized_route,
            family=family,
        )
        return jsonify(
            {
                "ok": False,
                "status": "blocked",
                "blocker": family,
                "secretValuesReturned": False,
            }
        ), 503

    audit(
        "openrouter_direct_transport_activated",
        normalized_route,
        {
            "modelCount": catalog["modelCount"],
            "catalogSnapshotSha256": catalog["catalogSnapshotSha256"],
            "canaryRequestId": canary.get("requestId"),
            "providerPolicySha256": canary["providerPolicySha256"],
            "attemptedModelCount": canary.get("attemptedModelCount"),
            "rejectedPolicyFamilies": canary.get("rejectedPolicyFamilies", []),
            "rawSecretPersistedInDatabase": False,
        },
    )
    return jsonify(
        {
            "ok": True,
            "status": "ready",
            "transport": "openrouter",
            "routeId": normalized_route,
            "catalog": catalog,
            "canary": canary,
            "keyHint": key_hint,
            "secretValuesReturned": False,
        }
    )


def _markup_multiplier(config: dict[str, Any]) -> int:
    value = config.get("markupMultiplier")
    if isinstance(value, bool):
        return _MARKUP_MULTIPLIER
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return _MARKUP_MULTIPLIER
    return min(32_767, max(_MARKUP_MULTIPLIER, parsed))


def _price_decimal(config: dict[str, Any], field: str) -> Decimal:
    return _decimal(config.get(field)) or Decimal(0)


def _formatted_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _catalog_identity(row: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return {
        "selectionId": str(config.get("providerModel") or ""),
        "routeId": str(row.get("id") or ""),
        "displayName": str(row.get("model_name") or ""),
        "canonicalModelSlug": str(config.get("canonicalModelSlug") or ""),
        "supportedRoles": list(config.get("supportedExecutionRoles") or []),
        "contextLength": int(config.get("contextLength") or 0),
        "maxCompletionTokens": int(config.get("maxCompletionTokens") or 0),
        "selectable": bool(config.get("selectable")) and not bool(row.get("disabled")),
        "dataCollectionDenied": True,
    }


def _customer_price_payload(config: dict[str, Any]) -> dict[str, Any]:
    multiplier = _markup_multiplier(config)
    input_cost = _price_decimal(config, "inputUsdPerMillion")
    cached_cost = _price_decimal(config, "cachedInputUsdPerMillion")
    output_cost = _price_decimal(config, "outputUsdPerMillion")

    def customer_price(value: Decimal) -> str:
        return _formatted_decimal(value * Decimal(multiplier))

    def credits_per_million(value: Decimal) -> int:
        return int(
            (value * Decimal(multiplier) * Decimal(1000)).to_integral_value(
                rounding=ROUND_CEILING
            )
        )

    return {
        "currency": "USD",
        "unit": "per_million_tokens",
        "input": customer_price(input_cost),
        "cachedInput": customer_price(cached_cost),
        "output": customer_price(output_cost),
        "inputCredits": credits_per_million(input_cost),
        "cachedInputCredits": credits_per_million(cached_cost),
        "outputCredits": credits_per_million(output_cost),
    }


def _user_catalog_row(row: dict[str, Any]) -> dict[str, Any]:
    config = row.get("config") if isinstance(row.get("config"), dict) else {}
    payload = _catalog_identity(row, config)
    payload["prices"] = _customer_price_payload(config)
    return payload


def _admin_catalog_row(row: dict[str, Any]) -> dict[str, Any]:
    config = row.get("config") if isinstance(row.get("config"), dict) else {}
    payload = _user_catalog_row(row)
    payload["pricingAdmin"] = {
        "providerCost": {
            "currency": "USD",
            "unit": "per_million_tokens",
            "input": _formatted_decimal(
                _price_decimal(config, "inputUsdPerMillion")
            ),
            "cachedInput": _formatted_decimal(
                _price_decimal(config, "cachedInputUsdPerMillion")
            ),
            "output": _formatted_decimal(
                _price_decimal(config, "outputUsdPerMillion")
            ),
        },
        "customerPrice": dict(payload["prices"]),
        "markupMultiplier": _markup_multiplier(config),
        "minimumMarkupMultiplier": _MARKUP_MULTIPLIER,
        "priceOverridesPresent": bool(config.get("priceOverridesPresent")),
        "pricingSource": str(config.get("pricingSource") or ""),
    }
    return payload


def register_openrouter_provider_runtime(
    app: Any,
    *,
    require_admin: Callable,
    require_session: Callable,
    query: Callable[..., Any],
    get_connection: ConnectionFactory,
    audit: Callable[[str, str | None, dict[str, Any]], None],
) -> None:
    @app.route("/api/admin/llm/openrouter/owner-input", methods=["POST"])
    @require_admin
    def prepare_openrouter_owner_input():
        connection = get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE owner_input_requests
                       SET status='expired', resolved_at=NOW(), result_code='superseded'
                       WHERE target_id=%s AND status IN ('pending','processing')""",
                    (OPENROUTER_OWNER_TARGET,),
                )
                cursor.execute(
                    """INSERT INTO owner_input_requests
                           (target_id, title, reason, field_label, expires_at)
                       VALUES (%s, 'OpenRouter aktivieren',
                               'Persistenter, geschützter Zugang nur für die direkte bezahlte OpenRouter-Route; der Rohwert wird nie in PostgreSQL gespeichert.',
                               'OpenRouter API-Key', NOW() + INTERVAL '15 minutes')
                       RETURNING id::text""",
                    (OPENROUTER_OWNER_TARGET,),
                )
                request_id = str(cursor.fetchone()["id"])
                cursor.execute(
                    """UPDATE llm_provider_deployments
                       SET owner_request_id=%s::uuid, status='awaiting_owner_input',
                           last_error_code=NULL, updated_at=NOW()
                       WHERE route_id=%s""",
                    (request_id, OPENROUTER_ROOT_ROUTE_ID),
                )
                if cursor.rowcount != 1:
                    raise OpenRouterRuntimeError(
                        "openrouter_root_deployment_missing", status_code=409
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            return jsonify(
                {
                    "error": "Geschützte OpenRouter-Eingabe konnte nicht vorbereitet werden",
                    "blocker": "openrouter_owner_input_prepare_failed",
                }
            ), 500
        finally:
            _close(connection)
        return jsonify(
            {
                "ok": True,
                "status": "awaiting_owner_input",
                "ownerRequestId": request_id,
                "ownerUrl": f"/owner-approvals?request_id={request_id}",
                "targetId": OPENROUTER_OWNER_TARGET,
                "secretValuesReturned": False,
            }
        ), 202

    @app.route("/api/admin/llm/openrouter/activate", methods=["POST"])
    @require_admin
    def admin_activate_openrouter():
        return activate_openrouter_provider(
            OPENROUTER_ROOT_ROUTE_ID,
            query=query,
            get_connection=get_connection,
            audit=audit,
        )

    @app.route("/api/admin/llm/openrouter/catalog/refresh", methods=["POST"])
    @require_admin
    def refresh_openrouter_catalog():
        try:
            deployment = query(
                """SELECT key_fingerprint, key_hint, last_canary_request_id
                   FROM llm_provider_deployments WHERE route_id=%s LIMIT 1""",
                (OPENROUTER_ROOT_ROUTE_ID,),
                one=True,
            ) or {}
            if not deployment.get("key_fingerprint"):
                raise OpenRouterRuntimeError(
                    "openrouter_owner_input_required", status_code=409
                )
            with _protected_key() as key:
                fingerprint = hashlib.sha256(key.encode()).hexdigest()
                if fingerprint != str(deployment.get("key_fingerprint") or ""):
                    raise OpenRouterRuntimeError(
                        "openrouter_secret_fingerprint_mismatch", status_code=409
                    )
                agent_models, agent_catalog_request_id = _fetch_agent_models(key)
                canary = _completion_canary_with_rotation(
                    key,
                    agent_models=agent_models,
                )
                catalog = _sync_catalog(
                    get_connection,
                    key=key,
                    key_fingerprint=fingerprint,
                    key_hint=f"…{key[-4:]}",
                    canary=canary,
                    agent_models=agent_models,
                    agent_catalog_request_id=agent_catalog_request_id,
                )
        except OpenRouterRuntimeError as exc:
            return jsonify(
                {
                    "ok": False,
                    "blocker": exc.family,
                    "secretValuesReturned": False,
                }
            ), exc.status_code
        audit(
            "openrouter_catalog_refreshed",
            OPENROUTER_ROOT_ROUTE_ID,
            {
                "modelCount": catalog["modelCount"],
                "catalogSnapshotSha256": catalog["catalogSnapshotSha256"],
            },
        )
        return jsonify(
            {
                "ok": True,
                "status": "ready",
                "catalog": catalog,
                "secretValuesReturned": False,
            }
        )

    @app.route("/api/admin/llm/openrouter/status", methods=["GET"])
    @require_admin
    def openrouter_status():
        row = query(
            """SELECT deployment.status, deployment.key_hint,
                      deployment.last_canary_request_id,
                      deployment.last_canary_at, deployment.last_error_code,
                      COUNT(route.id) FILTER (
                          WHERE route.disabled=false
                            AND lower(COALESCE(route.runtime_kind, route.provider))='openrouter'
                      ) OVER () AS selectable_models
               FROM llm_provider_deployments AS deployment
               LEFT JOIN llm_routes AS route ON true
               WHERE deployment.route_id=%s
               LIMIT 1""",
            (OPENROUTER_ROOT_ROUTE_ID,),
            one=True,
        ) or {}
        return jsonify(
            {
                "status": str(row.get("status") or "not_configured"),
                "keyStored": _key_path().exists(),
                "keyHint": row.get("key_hint"),
                "selectableModels": int(row.get("selectable_models") or 0),
                "lastCanaryRequestId": row.get("last_canary_request_id"),
                "lastCanaryAt": row.get("last_canary_at"),
                "lastErrorCode": row.get("last_error_code"),
                "secretValuesReturned": False,
            }
        )

    @app.route("/api/admin/llm/openrouter/models", methods=["GET"])
    @require_admin
    def admin_openrouter_models():
        rows = query(
            """SELECT id::text, model_id, model_name, disabled, priority, config
               FROM llm_routes
               WHERE lower(COALESCE(runtime_kind, provider))='openrouter'
               ORDER BY disabled ASC, priority ASC, model_name ASC
               LIMIT 700"""
        ) or []
        return jsonify(
            {
                "ok": True,
                "models": [_admin_catalog_row(dict(row)) for row in rows],
                "minimumMarkupMultiplier": _MARKUP_MULTIPLIER,
                "secretValuesReturned": False,
            }
        )

    @app.route(
        "/api/admin/llm/openrouter/models/<route_id>/markup",
        methods=["PATCH"],
    )
    @require_admin
    def update_openrouter_model_markup(route_id: str):
        body = request.get_json(silent=True)
        raw_multiplier = body.get("markupMultiplier") if isinstance(body, dict) else None
        if isinstance(raw_multiplier, bool) or not isinstance(raw_multiplier, int):
            return jsonify(
                {
                    "error": "markupMultiplier muss eine ganze Zahl sein",
                    "minimumMarkupMultiplier": _MARKUP_MULTIPLIER,
                }
            ), 400
        if not _MARKUP_MULTIPLIER <= raw_multiplier <= 32_767:
            return jsonify(
                {
                    "error": "markupMultiplier liegt außerhalb des erlaubten Bereichs",
                    "minimumMarkupMultiplier": _MARKUP_MULTIPLIER,
                    "maximumMarkupMultiplier": 32_767,
                }
            ), 400

        connection = get_connection()
        updated: dict[str, Any] | None = None
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT id::text, config
                       FROM llm_routes
                       WHERE id::text=%s
                         AND lower(COALESCE(runtime_kind, provider))='openrouter'
                       FOR UPDATE""",
                    (str(route_id),),
                )
                existing = cursor.fetchone()
                if existing:
                    existing_config = (
                        existing.get("config")
                        if isinstance(existing.get("config"), dict)
                        else {}
                    )
                    credits_per_unit = _credits_per_thousand(
                        str(existing_config.get("outputUsdPerMillion") or "0"),
                        raw_multiplier,
                    )
                    cursor.execute(
                        """UPDATE llm_routes
                           SET credits_per_unit=%s,
                               config=jsonb_set(
                                   jsonb_set(
                                       COALESCE(config, '{}'::jsonb),
                                       '{markupMultiplier}',
                                       to_jsonb(%s::integer),
                                       true
                                   ),
                                   '{minimumMultiplier}',
                                   to_jsonb(4),
                                   true
                               ),
                               updated_at=NOW()
                           WHERE id::text=%s
                             AND lower(COALESCE(runtime_kind, provider))='openrouter'
                           RETURNING id::text, model_id, model_name, disabled,
                                     priority, config""",
                        (credits_per_unit, raw_multiplier, str(route_id)),
                    )
                    row = cursor.fetchone()
                    updated = dict(row) if row else None
                    if str(route_id) == OPENROUTER_ROOT_ROUTE_ID:
                        cursor.execute(
                            """UPDATE llm_provider_deployments
                               SET markup_multiplier=%s, updated_at=NOW()
                               WHERE route_id=%s""",
                            (raw_multiplier, OPENROUTER_ROOT_ROUTE_ID),
                        )
            if not updated:
                connection.rollback()
                return jsonify({"error": "OpenRouter-Modellroute nicht gefunden"}), 404
            connection.commit()
        except Exception:
            connection.rollback()
            return jsonify(
                {
                    "error": "OpenRouter-Verkaufspreis konnte nicht gespeichert werden",
                    "blocker": "openrouter_markup_update_failed",
                }
            ), 500
        finally:
            _close(connection)

        audit(
            "openrouter_model_markup_updated",
            str(route_id),
            {
                "modelId": str(updated.get("model_id") or ""),
                "markupMultiplier": raw_multiplier,
                "minimumMarkupMultiplier": _MARKUP_MULTIPLIER,
            },
        )
        return jsonify(
            {
                "ok": True,
                "model": _admin_catalog_row(updated),
                "secretValuesReturned": False,
            }
        )

    @app.route("/api/user/agent/swarm/models", methods=["GET"])
    @require_session
    def user_openrouter_models():
        rows = query(
            """SELECT id::text, model_id, model_name, disabled, priority, config
               FROM llm_routes
               WHERE disabled=false
                 AND lower(COALESCE(runtime_kind, provider))='openrouter'
                 AND COALESCE((config->>'selectable')::boolean, false)=true
               ORDER BY priority ASC, model_name ASC
               LIMIT 700"""
        ) or []
        models = [_user_catalog_row(dict(row)) for row in rows]
        default_model = (
            OPENROUTER_DEFAULT_MODEL
            if any(model["selectionId"] == OPENROUTER_DEFAULT_MODEL for model in models)
            else models[0]["selectionId"]
            if models
            else None
        )
        return jsonify(
            {
                "ok": bool(models),
                "status": "ready" if models else "openrouter_not_activated",
                "models": models,
                "defaults": {
                    "mainModel": default_model,
                    "agentModel": default_model,
                },
                "selectionSchema": {
                    "mainModel": "OpenRouter selectionId for intent, dispatcher, and judge",
                    "agentModel": "OpenRouter selectionId shared by exactly six bounded agents",
                },
                "freeMode": {
                    "modelSelection": "automatic_quota_aware_freellm",
                    "maxForegroundAgents": 1,
                    "maxBackgroundAgents": 0,
                },
                "providerPolicy": dict(_PROVIDER_POLICY),
                "secretValuesReturned": False,
            }
        ), 200 if models else 503

