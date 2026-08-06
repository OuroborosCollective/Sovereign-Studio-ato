"""Revision-bound OpenRouter Free-Revolver and management-key runtime.

Management keys and execution keys are deliberately separate. The management
key can only call OpenRouter key-administration endpoints. The dedicated free
execution key can only enter a persisted route whose provider model is exactly
``openrouter/free`` and whose two canaries have zero-cost generation receipts.
Raw credentials remain 0600 owner-managed files and are never returned or
stored in PostgreSQL.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import os
import re
import stat
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import requests
from flask import jsonify, request

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_FREE_MODEL = "openrouter/free"
OPENROUTER_FREE_ROUTE_ALIAS = "sovereign-openrouter-free"
OPENROUTER_FREE_ROUTE_ID = str(
    uuid.uuid5(uuid.NAMESPACE_URL, "sovereign:openrouter:free-revolver:v1")
)
OPENROUTER_FREE_RECEIPT_SCHEMA = "sovereign.openrouter-free-route-receipt.v1"
OPENROUTER_FREE_QUOTA_SCOPE = "openrouter:account:free-models"
_MAX_RESPONSE_BYTES = 2_000_000
_MIN_SECRET_BYTES = 16
_MAX_SECRET_BYTES = 8192
_SOURCE_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_KEY_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_FREE_PROVIDER_POLICY = {
    "require_parameters": False,
    "allow_fallbacks": True,
    "data_collection": "deny",
}


class OpenRouterFreeRuntimeError(RuntimeError):
    def __init__(self, family: str, *, status_code: int = 503) -> None:
        super().__init__(family)
        self.family = str(family)[:120]
        self.status_code = int(status_code)


def _owner_root() -> Path:
    return Path(
        os.getenv("SOVEREIGN_OWNER_INPUT_ROOT", "/opt/sovereign-owner-managed")
    ).resolve()


def _key_contract(kind: str) -> tuple[str, str]:
    if kind == "free":
        return "SOVEREIGN_OPENROUTER_FREE_API_KEY_FILE", "openrouter_free_api_key.txt"
    if kind == "management":
        return (
            "SOVEREIGN_OPENROUTER_MANAGEMENT_API_KEY_FILE",
            "openrouter_management_api_key.txt",
        )
    raise OpenRouterFreeRuntimeError("openrouter_key_kind_invalid", status_code=400)


def _key_path(kind: str) -> Path:
    env_name, filename = _key_contract(kind)
    root = _owner_root()
    path = Path(os.getenv(env_name, str(root / filename))).resolve()
    if path.parent != root or path.name != filename:
        raise OpenRouterFreeRuntimeError(
            f"openrouter_{kind}_key_path_invalid", status_code=409
        )
    return path


def _read_key(kind: str) -> tuple[bytearray, str, str]:
    path = _key_path(kind)
    protected = bytearray()
    try:
        info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or path.is_symlink()
            or stat.S_IMODE(info.st_mode) & 0o077
        ):
            raise OpenRouterFreeRuntimeError(
                f"openrouter_{kind}_key_permissions_invalid", status_code=409
            )
        if not _MIN_SECRET_BYTES <= info.st_size <= _MAX_SECRET_BYTES:
            raise OpenRouterFreeRuntimeError(
                f"openrouter_{kind}_key_invalid", status_code=409
            )
        protected = bytearray(path.read_bytes())
        key = protected.decode("utf-8").strip()
        if (
            len(key) < _MIN_SECRET_BYTES
            or any(marker in key for marker in ("\x00", "\n", "\r"))
        ):
            raise OpenRouterFreeRuntimeError(
                f"openrouter_{kind}_key_invalid", status_code=409
            )
        fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return protected, key, fingerprint
    except FileNotFoundError as exc:
        raise OpenRouterFreeRuntimeError(
            f"openrouter_{kind}_key_missing", status_code=409
        ) from exc
    except UnicodeDecodeError as exc:
        raise OpenRouterFreeRuntimeError(
            f"openrouter_{kind}_key_invalid", status_code=409
        ) from exc


def _key_state(kind: str) -> dict[str, Any]:
    protected = bytearray()
    key = ""
    try:
        protected, key, fingerprint = _read_key(kind)
        return {
            "configured": True,
            "fingerprintSha256": fingerprint,
            "permissionsValid": True,
            "blocker": None,
        }
    except OpenRouterFreeRuntimeError as exc:
        return {
            "configured": False,
            "fingerprintSha256": None,
            "permissionsValid": False,
            "blocker": exc.family,
        }
    finally:
        key = ""
        for index in range(len(protected)):
            protected[index] = 0


def _atomic_write_free_key(value: bytes | bytearray | str) -> None:
    encoded = value if isinstance(value, bytearray) else bytearray(
        value.encode("utf-8") if isinstance(value, str) else value
    )
    path = _key_path("free")
    root = _owner_root()
    if not _MIN_SECRET_BYTES <= len(encoded) <= _MAX_SECRET_BYTES:
        raise OpenRouterFreeRuntimeError("openrouter_free_key_invalid", status_code=409)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            view = memoryview(encoded)
            offset = 0
            while offset < len(view):
                offset += os.write(descriptor, view[offset:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)
        for index in range(len(encoded)):
            encoded[index] = 0


def _remove_free_key() -> None:
    path = _key_path("free")
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISREG(info.st_mode) and info.st_size <= _MAX_SECRET_BYTES:
        try:
            with path.open("r+b", buffering=0) as handle:
                handle.write(b"\0" * info.st_size)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            pass
    path.unlink(missing_ok=True)


def _internal_owner_authorized() -> bool:
    expected = os.getenv("SOVEREIGN_OWNER_REQUEST_KEY", "").strip()
    presented = request.headers.get("X-Sovereign-Owner-Request-Key", "").strip()
    return bool(expected and presented) and hmac.compare_digest(expected, presented)


def _runtime_identity() -> dict[str, Any]:
    revision = os.getenv("SOVEREIGN_SOURCE_REVISION", "").strip().lower()
    digest = os.getenv("SOVEREIGN_IMAGE_DIGEST", "").strip().lower()
    return {
        "sourceRevision": revision if _SOURCE_REVISION_RE.fullmatch(revision) else "unverified",
        "sourceRevisionVerified": bool(_SOURCE_REVISION_RE.fullmatch(revision)),
        "imageDigest": digest if _IMAGE_DIGEST_RE.fullmatch(digest) else "unverified",
        "imageDigestVerified": bool(_IMAGE_DIGEST_RE.fullmatch(digest)),
    }


def _canonical_sha256(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _headers(key: str) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "sovereign-openrouter-free-revolver/1",
    }
    referer = os.getenv("SOVEREIGN_OPENROUTER_HTTP_REFERER", "").strip()
    title = os.getenv("SOVEREIGN_OPENROUTER_APP_TITLE", "Sovereign Studio").strip()
    if referer:
        headers["HTTP-Referer"] = referer[:500]
    if title:
        headers["X-OpenRouter-Title"] = title[:200]
    return headers


def _bounded_json(response: requests.Response) -> dict[str, Any]:
    content_length = int(response.headers.get("Content-Length") or 0)
    if content_length > _MAX_RESPONSE_BYTES:
        raise OpenRouterFreeRuntimeError("openrouter_response_too_large")
    raw = response.raw.read(_MAX_RESPONSE_BYTES + 1, decode_content=True)
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise OpenRouterFreeRuntimeError("openrouter_response_too_large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OpenRouterFreeRuntimeError("openrouter_response_invalid") from exc
    if not isinstance(payload, dict):
        raise OpenRouterFreeRuntimeError("openrouter_response_invalid")
    return payload


def _safe_error_family(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    root = payload if isinstance(payload, dict) else {}
    error = root.get("error") if isinstance(root.get("error"), dict) else {}
    material = " ".join(
        str(value or "").lower()[:160]
        for value in (
            error.get("code"),
            error.get("type"),
            error.get("message"),
            root.get("code"),
            root.get("message"),
        )
    )
    if response.status_code == 429 and "quota" in material:
        return "provider_quota_exhausted"
    if response.status_code == 429:
        return "openrouter_rate_limited"
    if response.status_code in {408, 504}:
        return "openrouter_timeout"
    if response.status_code in {401, 403}:
        return "openrouter_credentials_rejected"
    if response.status_code == 402:
        return "openrouter_account_credits_required"
    if response.status_code >= 500 or response.status_code in {301, 302, 307, 308, 404}:
        return "openrouter_upstream_unavailable"
    return "openrouter_provider_rejected"


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() and parsed >= 0 else None


def _current_key_metadata(key: str) -> dict[str, Any]:
    with requests.Session() as session:
        session.trust_env = False
        with session.get(
            f"{OPENROUTER_BASE_URL}/key",
            headers=_headers(key),
            timeout=15,
            allow_redirects=False,
            stream=True,
        ) as response:
            if response.status_code != 200:
                raise OpenRouterFreeRuntimeError(
                    _safe_error_family(response), status_code=int(response.status_code)
                )
            payload = _bounded_json(response)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if data.get("is_management_key") is True:
        raise OpenRouterFreeRuntimeError(
            "openrouter_management_key_cannot_execute_models", status_code=409
        )
    return {
        "isManagementKey": False,
        "isFreeTier": bool(data.get("is_free_tier")),
        "limit": data.get("limit"),
        "limitRemaining": data.get("limit_remaining"),
        "usageDaily": data.get("usage_daily"),
        "label": str(data.get("label") or "")[:120] or None,
    }


def _generation_zero_cost(key: str, generation_id: str) -> dict[str, Any]:
    last_status = 0
    for attempt in range(4):
        if attempt:
            time.sleep(0.4 * attempt)
        with requests.Session() as session:
            session.trust_env = False
            with session.get(
                f"{OPENROUTER_BASE_URL}/generation",
                headers=_headers(key),
                params={"id": generation_id},
                timeout=15,
                allow_redirects=False,
                stream=True,
            ) as response:
                last_status = int(response.status_code)
                if last_status == 404 and attempt < 3:
                    continue
                if last_status != 200:
                    raise OpenRouterFreeRuntimeError(
                        _safe_error_family(response), status_code=last_status
                    )
                payload = _bounded_json(response)
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        total_cost = _decimal(data.get("total_cost"))
        if total_cost is None:
            total_cost = _decimal(data.get("usage"))
        if total_cost != Decimal(0):
            raise OpenRouterFreeRuntimeError(
                "openrouter_free_generation_cost_not_zero", status_code=409
            )
        resolved_model = str(data.get("model") or "")[:240]
        router = str(data.get("router") or "")[:240]
        if router != OPENROUTER_FREE_MODEL and not resolved_model.endswith(":free"):
            raise OpenRouterFreeRuntimeError(
                "openrouter_free_generation_identity_unverified", status_code=409
            )
        return {
            "generationId": generation_id,
            "totalCostUsd": "0",
            "resolvedModel": resolved_model or None,
            "router": router or None,
            "providerName": str(data.get("provider_name") or "")[:120] or None,
            "requestId": str(data.get("request_id") or "")[:200] or None,
        }
    raise OpenRouterFreeRuntimeError(
        "openrouter_generation_receipt_unavailable", status_code=last_status or 503
    )


def _completion_canary(key: str) -> dict[str, Any]:
    started = time.monotonic()
    with requests.Session() as session:
        session.trust_env = False
        with session.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=_headers(key),
            json={
                "model": OPENROUTER_FREE_MODEL,
                "messages": [{"role": "user", "content": "Reply with OK."}],
                "max_tokens": 8,
                "stream": False,
                "provider": dict(_FREE_PROVIDER_POLICY),
            },
            timeout=45,
            allow_redirects=False,
            stream=True,
        ) as response:
            status = int(response.status_code)
            if status != 200:
                raise OpenRouterFreeRuntimeError(
                    _safe_error_family(response), status_code=status
                )
            payload = _bounded_json(response)
    choices = payload.get("choices") if isinstance(payload.get("choices"), list) else []
    first = choices[0] if choices and isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first.get("message"), dict) else {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise OpenRouterFreeRuntimeError("openrouter_free_canary_text_missing")
    generation_id = str(payload.get("id") or "").strip()[:200]
    if not generation_id:
        raise OpenRouterFreeRuntimeError("openrouter_generation_id_missing")
    generation = _generation_zero_cost(key, generation_id)
    response_model = str(payload.get("model") or "")[:240]
    return {
        **generation,
        "responseModel": response_model or None,
        "latencyMs": int((time.monotonic() - started) * 1000),
        "textualChatResponseVerified": True,
        "rawResponsePersisted": False,
    }


def _double_canary(key: str) -> dict[str, Any]:
    confirmations = [_completion_canary(key), _completion_canary(key)]
    if any(item.get("totalCostUsd") != "0" for item in confirmations):
        raise OpenRouterFreeRuntimeError("openrouter_free_double_canary_cost_invalid")
    return {
        "confirmationCount": 2,
        "confirmations": confirmations,
        "generationIds": [item["generationId"] for item in confirmations],
        "resolvedModels": [item.get("resolvedModel") for item in confirmations],
        "latenciesMs": [int(item.get("latencyMs") or 0) for item in confirmations],
        "providerCostState": "zero",
        "textualChatResponsesVerified": True,
        "rawResponsesPersisted": False,
    }


def _route_record(
    *,
    key_fingerprint: str,
    key_source: str,
    canary: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    identity = _runtime_identity()
    if not (
        identity["sourceRevisionVerified"] and identity["imageDigestVerified"]
    ):
        raise OpenRouterFreeRuntimeError(
            "openrouter_free_runtime_identity_unverified", status_code=409
        )
    receipt_payload = {
        "schemaVersion": OPENROUTER_FREE_RECEIPT_SCHEMA,
        "routeId": OPENROUTER_FREE_ROUTE_ID,
        "providerModel": OPENROUTER_FREE_MODEL,
        "keyFingerprintSha256": key_fingerprint,
        "keySource": key_source,
        "canaryEvidence": canary,
        "runtimeIdentity": identity,
    }
    receipt_sha256 = _canonical_sha256(receipt_payload)
    quota_evidence = {
        "scope": OPENROUTER_FREE_QUOTA_SCOPE,
        "stateOwner": "postgresql-revolver-state",
        "accountWide": True,
        "dailyLimitSharedAcrossKeys": True,
        "reactivationRequiresFreshDoubleCanary": True,
        "failClosedOnDrift": True,
    }
    retry_evidence = {
        "retryableFailureFamilies": [
            "provider_quota_exhausted",
            "openrouter_rate_limited",
            "openrouter_timeout",
            "openrouter_upstream_unavailable",
        ],
        "nextTransportAfterCooldown": "freellm",
        "paidFallbackAllowed": False,
    }
    config = {
        "routingOwner": "openrouter-free-revolver",
        "managedBy": "sovereign-admin",
        "transport": "openrouter",
        "direct": True,
        "providerModel": OPENROUTER_FREE_MODEL,
        "billingCategory": "free",
        "billingClass": "free",
        "fundingMode": "provider_free_quota",
        "markupMultiplier": 0,
        "minimumMultiplier": 0,
        "userChargeCredits": 0,
        "inputUsdPerMillion": "0",
        "cachedInputUsdPerMillion": "0",
        "outputUsdPerMillion": "0",
        "pricingSource": "openrouter-free-generation-receipt",
        "pricingVerified": False,
        "freeEligible": True,
        "quotaContractVerified": True,
        "providerCostState": "zero",
        "catalogVerified": True,
        "transportCanaryVerified": True,
        "canaryVerified": True,
        "canaryConfirmationCount": 2,
        "canaryLatencyMs": max(canary.get("latenciesMs") or [0]),
        "selectable": True,
        "executionProfile": "free_single_agent",
        "resolverMode": "revolver",
        "maxForegroundAgents": 1,
        "maxBackgroundAgents": 0,
        "repositoryExecutionAllowed": True,
        "supportedExecutionRoles": ["main"],
        "capabilities": ["chat"],
        "quotaScope": OPENROUTER_FREE_QUOTA_SCOPE,
        "quotaEvidence": quota_evidence,
        "retryEvidence": retry_evidence,
        "cooldownEvidence": quota_evidence,
        "providerPolicy": dict(_FREE_PROVIDER_POLICY),
        "runtimeIdentity": identity,
        "keyFingerprintSha256": key_fingerprint,
        "keySource": key_source,
        "canaryReceipt": {
            "schemaVersion": OPENROUTER_FREE_RECEIPT_SCHEMA,
            "receiptId": f"openrouter-free:{receipt_sha256[:20]}",
            "receiptSha256": receipt_sha256,
            "generalChatEvidenceVerified": True,
            "zeroCostEvidenceVerified": True,
        },
    }
    return config, receipt_sha256


def _persist_route(
    get_connection: Callable[[], Any],
    *,
    key_fingerprint: str,
    key_source: str,
    canary: dict[str, Any],
    managed_key: dict[str, Any] | None = None,
) -> str:
    config, receipt_sha256 = _route_record(
        key_fingerprint=key_fingerprint,
        key_source=key_source,
        canary=canary,
    )
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO llm_routes
                       (id, model_id, model_name, provider, base_url,
                        credits_per_unit, disabled, priority, runtime_kind,
                        tier, config, updated_at)
                   VALUES (%s::uuid,%s,'OpenRouter Free Router','openrouter',%s,
                           0,false,5,'openrouter','free',%s::jsonb,NOW())
                   ON CONFLICT (id) DO UPDATE SET
                       model_id=EXCLUDED.model_id,
                       model_name=EXCLUDED.model_name,
                       provider='openrouter', base_url=EXCLUDED.base_url,
                       credits_per_unit=0, disabled=false, priority=5,
                       runtime_kind='openrouter', tier='free',
                       config=EXCLUDED.config, updated_at=NOW()""",
                (
                    OPENROUTER_FREE_ROUTE_ID,
                    OPENROUTER_FREE_ROUTE_ALIAS,
                    OPENROUTER_BASE_URL,
                    json.dumps(config, ensure_ascii=True),
                ),
            )
            if managed_key is not None:
                cursor.execute(
                    """UPDATE openrouter_managed_execution_keys
                       SET status='retirement_pending', updated_at=NOW()
                       WHERE purpose='free-revolver' AND status='active'"""
                )
                cursor.execute(
                    """INSERT INTO openrouter_managed_execution_keys
                           (purpose, upstream_key_hash, key_fingerprint_sha256,
                            key_name, status, route_id, metadata,
                            activated_at, last_verified_at, updated_at)
                       VALUES ('free-revolver',%s,%s,%s,'active',%s::uuid,
                               %s::jsonb,NOW(),NOW(),NOW())""",
                    (
                        managed_key["hash"],
                        key_fingerprint,
                        managed_key["name"],
                        OPENROUTER_FREE_ROUTE_ID,
                        json.dumps(
                            {
                                "limitUsd": managed_key.get("limit"),
                                "limitReset": managed_key.get("limitReset"),
                                "includeByokInLimit": managed_key.get(
                                    "includeByokInLimit"
                                ),
                                "rawKeyStoredInDatabase": False,
                                "receiptSha256": receipt_sha256,
                            },
                            ensure_ascii=True,
                        ),
                    ),
                )
        connection.commit()
        return receipt_sha256
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _management_request(
    key: str,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with requests.Session() as session:
        session.trust_env = False
        with session.request(
            method,
            f"{OPENROUTER_BASE_URL}{path}",
            headers=_headers(key),
            json=body,
            timeout=20,
            allow_redirects=False,
            stream=True,
        ) as response:
            status = int(response.status_code)
            expected = {"GET": {200}, "POST": {200, 201}, "PATCH": {200}, "DELETE": {200}}
            if status not in expected.get(method, {200}):
                raise OpenRouterFreeRuntimeError(
                    _safe_error_family(response), status_code=status
                )
            return _bounded_json(response)


def _verify_management_key(key: str) -> dict[str, Any]:
    payload = _management_request(key, "GET", "/keys")
    rows = payload.get("data") if isinstance(payload.get("data"), list) else None
    if rows is None:
        raise OpenRouterFreeRuntimeError("openrouter_management_key_response_invalid")
    return {"visibleKeyCount": len(rows[:100])}


def _managed_key_limit() -> Decimal:
    raw = os.getenv("SOVEREIGN_OPENROUTER_FREE_KEY_LIMIT_USD", "0").strip()
    value = _decimal(raw)
    if value is None or value != Decimal(0):
        raise OpenRouterFreeRuntimeError(
            "openrouter_free_key_limit_must_be_zero", status_code=409
        )
    return value


def _create_managed_free_key(management_key: str) -> tuple[bytearray, dict[str, Any]]:
    limit = _managed_key_limit()
    name = f"Sovereign Free Revolver {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}"
    payload = _management_request(
        management_key,
        "POST",
        "/keys",
        body={
            "name": name,
            "limit": float(limit),
            "limit_reset": "daily",
            "include_byok_in_limit": True,
        },
    )
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    raw_key = payload.get("key")
    if raw_key is None and isinstance(data, dict):
        raw_key = data.get("key")
    key_hash = str(data.get("hash") or "").strip().lower()
    if not isinstance(raw_key, str) or len(raw_key) < _MIN_SECRET_BYTES:
        raise OpenRouterFreeRuntimeError("openrouter_created_key_missing")
    if not _KEY_HASH_RE.fullmatch(key_hash):
        raise OpenRouterFreeRuntimeError("openrouter_created_key_hash_invalid")
    returned_limit = _decimal(data.get("limit"))
    if returned_limit != Decimal(0):
        raise OpenRouterFreeRuntimeError(
            "openrouter_created_key_limit_not_zero", status_code=409
        )
    protected = bytearray(raw_key.encode("utf-8"))
    raw_key = ""
    return protected, {
        "hash": key_hash,
        "name": str(data.get("name") or name)[:160],
        "limit": "0",
        "limitReset": str(data.get("limit_reset") or "daily"),
        "includeByokInLimit": bool(data.get("include_byok_in_limit", True)),
    }


def _retire_upstream_key(management_key: str, key_hash: str) -> bool:
    if not _KEY_HASH_RE.fullmatch(str(key_hash or "")):
        return False
    try:
        payload = _management_request(
            management_key, "DELETE", f"/keys/{key_hash}"
        )
        return payload.get("deleted") is True
    except OpenRouterFreeRuntimeError:
        try:
            payload = _management_request(
                management_key,
                "PATCH",
                f"/keys/{key_hash}",
                body={"disabled": True},
            )
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            return data.get("disabled") is True
        except OpenRouterFreeRuntimeError:
            return False


def _route_status(query: Callable[..., Any]) -> dict[str, Any]:
    route = query(
        """SELECT id::text, model_id, disabled, priority, runtime_kind, config,
                  updated_at
           FROM llm_routes WHERE id=%s::uuid LIMIT 1""",
        (OPENROUTER_FREE_ROUTE_ID,),
        one=True,
    ) or {}
    managed = query(
        """SELECT upstream_key_hash, key_name, status, activated_at,
                  last_verified_at, retired_at, updated_at
           FROM openrouter_managed_execution_keys
           WHERE purpose='free-revolver'
           ORDER BY created_at DESC LIMIT 20"""
    ) or []
    config = route.get("config") if isinstance(route.get("config"), dict) else {}
    return {
        "routeId": str(route.get("id") or "") or None,
        "modelId": str(route.get("model_id") or "") or None,
        "providerModel": config.get("providerModel"),
        "enabled": bool(route) and not bool(route.get("disabled")),
        "priority": route.get("priority"),
        "receipt": config.get("canaryReceipt") or {},
        "runtimeIdentity": config.get("runtimeIdentity") or {},
        "quotaEvidence": config.get("quotaEvidence") or {},
        "managedKeys": [
            {
                "hash": str(row.get("upstream_key_hash") or ""),
                "name": str(row.get("key_name") or ""),
                "status": str(row.get("status") or ""),
                "activatedAt": row["activated_at"].isoformat()
                if row.get("activated_at")
                else None,
                "lastVerifiedAt": row["last_verified_at"].isoformat()
                if row.get("last_verified_at")
                else None,
                "retiredAt": row["retired_at"].isoformat()
                if row.get("retired_at")
                else None,
            }
            for row in managed
        ],
    }


def _prepare_owner_request(
    get_connection: Callable[[], Any],
    *,
    target_id: str,
    title: str,
    reason: str,
    field_label: str,
) -> str:
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
                (target_id, title, reason, field_label),
            )
            request_id = str(cursor.fetchone()["id"])
        connection.commit()
        return request_id
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def register_openrouter_free_runtime(
    app: Any,
    *,
    require_admin: Callable[..., Any],
    query: Callable[..., Any],
    get_connection: Callable[[], Any],
    audit: Callable[..., Any],
) -> None:
    def status_payload() -> dict[str, Any]:
        try:
            route = _route_status(query)
            table_available = True
            table_blocker = None
        except Exception:
            route = {
                "routeId": None,
                "enabled": False,
                "managedKeys": [],
            }
            table_available = False
            table_blocker = "openrouter_management_migration_required"
        return {
            "ok": True,
            "status": "OPENROUTER_FREE_RUNTIME_STATUS",
            "freeExecutionKey": _key_state("free"),
            "managementKey": _key_state("management"),
            "route": route,
            "managementTableAvailable": table_available,
            "managementTableBlocker": table_blocker,
            "routingPolicy": {
                "priority": 5,
                "providerModel": OPENROUTER_FREE_MODEL,
                "fallbackAfterQuota": "freellm",
                "paidFallbackAllowed": False,
                "accountWideQuotaScope": OPENROUTER_FREE_QUOTA_SCOPE,
            },
            "runtimeIdentity": _runtime_identity(),
            "secretValuesReturned": False,
        }

    @app.route("/api/admin/llm/openrouter/free/status", methods=["GET"])
    @require_admin
    def admin_openrouter_free_status():
        return jsonify(status_payload())

    @app.route("/api/internal/llm/openrouter/free/status", methods=["GET"])
    def internal_openrouter_free_status():
        if not _internal_owner_authorized():
            return jsonify({"error": "forbidden", "secretValuesReturned": False}), 403
        return jsonify(status_payload())

    @app.route(
        "/api/admin/llm/openrouter/free-key/owner-input", methods=["POST"]
    )
    @require_admin
    def admin_prepare_openrouter_free_key():
        request_id = _prepare_owner_request(
            get_connection,
            target_id="openrouter_free_api_key",
            title="OpenRouter-Ausführungsschlüssel für den Free-Revolver",
            reason=(
                "Dieser Schlüssel wird ausschließlich für openrouter/free verwendet. "
                "Bezahlte Modelle und der Paid-Pfad bleiben getrennt."
            ),
            field_label="OpenRouter API-Key für kostenlose Modelle",
        )
        return jsonify({
            "ok": True,
            "ownerRequestId": request_id,
            "ownerUrl": f"/owner-approvals?request_id={request_id}",
            "secretValuesReturned": False,
        }), 201

    @app.route(
        "/api/admin/llm/openrouter/management-key/owner-input", methods=["POST"]
    )
    @require_admin
    def admin_prepare_openrouter_management_key():
        request_id = _prepare_owner_request(
            get_connection,
            target_id="openrouter_management_api_key",
            title="OpenRouter Management API Key",
            reason=(
                "Der Management-Key darf nur OpenRouter-Ausführungsschlüssel "
                "erstellen, prüfen, deaktivieren und löschen. Er wird niemals "
                "für Modellanfragen verwendet."
            ),
            field_label="OpenRouter Management API Key",
        )
        return jsonify({
            "ok": True,
            "ownerRequestId": request_id,
            "ownerUrl": f"/owner-approvals?request_id={request_id}",
            "secretValuesReturned": False,
        }), 201

    @app.route("/api/internal/llm/openrouter/free/activate", methods=["POST"])
    def internal_activate_openrouter_free():
        if not _internal_owner_authorized():
            return jsonify({"error": "forbidden", "secretValuesReturned": False}), 403
        protected = bytearray()
        key = ""
        try:
            protected, key, fingerprint = _read_key("free")
            metadata = _current_key_metadata(key)
            canary = _double_canary(key)
            receipt_sha256 = _persist_route(
                get_connection,
                key_fingerprint=fingerprint,
                key_source="owner-managed-free-execution-key",
                canary=canary,
            )
            audit("internal_openrouter_free_activated", OPENROUTER_FREE_ROUTE_ID, {
                "providerModel": OPENROUTER_FREE_MODEL,
                "confirmationCount": 2,
                "providerCostState": "zero",
                "keyFingerprintSha256": fingerprint,
                "rawSecretPersistedInDatabase": False,
            })
            return jsonify({
                "ok": True,
                "status": "OPENROUTER_FREE_ROUTE_ACTIVATED",
                "routeId": OPENROUTER_FREE_ROUTE_ID,
                "providerModel": OPENROUTER_FREE_MODEL,
                "priority": 5,
                "fallbackAfterQuota": "freellm",
                "paidFallbackAllowed": False,
                "keyMetadata": metadata,
                "canaryConfirmationCount": 2,
                "providerCostState": "zero",
                "receiptSha256": receipt_sha256,
                "runtimeIdentity": _runtime_identity(),
                "secretValuesReturned": False,
            })
        except OpenRouterFreeRuntimeError as exc:
            return jsonify({
                "error": exc.family,
                "status": "OPENROUTER_FREE_ACTIVATION_BLOCKED",
                "secretValuesReturned": False,
            }), exc.status_code
        except Exception:
            return jsonify({
                "error": "openrouter_free_activation_failed",
                "status": "OPENROUTER_FREE_ACTIVATION_BLOCKED",
                "secretValuesReturned": False,
            }), 503
        finally:
            key = ""
            for index in range(len(protected)):
                protected[index] = 0

    @app.route(
        "/api/internal/llm/openrouter/management/rotate-free-key",
        methods=["POST"],
    )
    def internal_rotate_openrouter_free_key():
        if not _internal_owner_authorized():
            return jsonify({"error": "forbidden", "secretValuesReturned": False}), 403
        management_protected = bytearray()
        new_protected = bytearray()
        old_protected = bytearray()
        management_key = ""
        new_key = ""
        old_key = ""
        created: dict[str, Any] | None = None
        prior_hashes: list[str] = []
        old_existed = False
        try:
            management_protected, management_key, management_fingerprint = _read_key(
                "management"
            )
            management_evidence = _verify_management_key(management_key)
            try:
                old_protected, old_key, _ = _read_key("free")
                old_existed = True
            except OpenRouterFreeRuntimeError as exc:
                if exc.family != "openrouter_free_key_missing":
                    raise
            rows = query(
                """SELECT upstream_key_hash FROM openrouter_managed_execution_keys
                   WHERE purpose='free-revolver'
                     AND status IN ('active','retirement_pending')
                   ORDER BY created_at ASC"""
            ) or []
            prior_hashes = [
                str(row.get("upstream_key_hash") or "")
                for row in rows
                if _KEY_HASH_RE.fullmatch(
                    str(row.get("upstream_key_hash") or "")
                )
            ]
            new_protected, created = _create_managed_free_key(management_key)
            new_key = new_protected.decode("utf-8").strip()
            new_fingerprint = hashlib.sha256(new_key.encode("utf-8")).hexdigest()
            _atomic_write_free_key(new_protected)
            _current_key_metadata(new_key)
            canary = _double_canary(new_key)
            receipt_sha256 = _persist_route(
                get_connection,
                key_fingerprint=new_fingerprint,
                key_source="openrouter-management-api-rotation",
                canary=canary,
                managed_key=created,
            )
            retired: list[str] = []
            pending: list[str] = []
            for key_hash in prior_hashes:
                if key_hash == created["hash"]:
                    continue
                if _retire_upstream_key(management_key, key_hash):
                    retired.append(key_hash)
                    query(
                        """UPDATE openrouter_managed_execution_keys
                           SET status='retired', retired_at=NOW(), updated_at=NOW()
                           WHERE upstream_key_hash=%s""",
                        (key_hash,),
                        write=True,
                    )
                else:
                    pending.append(key_hash)
                    query(
                        """UPDATE openrouter_managed_execution_keys
                           SET status='retirement_pending', updated_at=NOW()
                           WHERE upstream_key_hash=%s""",
                        (key_hash,),
                        write=True,
                    )
            audit("internal_openrouter_free_key_rotated", OPENROUTER_FREE_ROUTE_ID, {
                "newUpstreamKeyHash": created["hash"],
                "newKeyFingerprintSha256": new_fingerprint,
                "retiredKeyCount": len(retired),
                "retirementPendingCount": len(pending),
                "managementKeyFingerprintSha256": management_fingerprint,
                "rawSecretPersistedInDatabase": False,
            })
            return jsonify({
                "ok": True,
                "status": (
                    "OPENROUTER_FREE_KEY_ROTATED"
                    if not pending
                    else "OPENROUTER_FREE_KEY_ROTATED_RETIREMENT_PENDING"
                ),
                "routeId": OPENROUTER_FREE_ROUTE_ID,
                "providerModel": OPENROUTER_FREE_MODEL,
                "newUpstreamKeyHash": created["hash"],
                "retiredKeyHashes": retired,
                "retirementPendingKeyHashes": pending,
                "managementEvidence": management_evidence,
                "canaryConfirmationCount": 2,
                "providerCostState": "zero",
                "receiptSha256": receipt_sha256,
                "paidFallbackAllowed": False,
                "secretValuesReturned": False,
            }), 200 if not pending else 207
        except OpenRouterFreeRuntimeError as exc:
            if created and _KEY_HASH_RE.fullmatch(str(created.get("hash") or "")):
                _retire_upstream_key(management_key, str(created["hash"]))
            if old_existed and old_protected:
                try:
                    _atomic_write_free_key(old_protected)
                except OpenRouterFreeRuntimeError:
                    _remove_free_key()
            elif created:
                _remove_free_key()
            return jsonify({
                "error": exc.family,
                "status": "OPENROUTER_FREE_KEY_ROTATION_BLOCKED",
                "previousExecutionKeyRestored": old_existed,
                "secretValuesReturned": False,
            }), exc.status_code
        except Exception:
            if created and management_key:
                _retire_upstream_key(management_key, str(created.get("hash") or ""))
            if old_existed and old_protected:
                try:
                    _atomic_write_free_key(old_protected)
                except OpenRouterFreeRuntimeError:
                    _remove_free_key()
            elif created:
                _remove_free_key()
            return jsonify({
                "error": "openrouter_free_key_rotation_failed",
                "status": "OPENROUTER_FREE_KEY_ROTATION_BLOCKED",
                "previousExecutionKeyRestored": old_existed,
                "secretValuesReturned": False,
            }), 503
        finally:
            management_key = ""
            new_key = ""
            old_key = ""
            for buffer in (management_protected, new_protected, old_protected):
                for index in range(len(buffer)):
                    buffer[index] = 0
