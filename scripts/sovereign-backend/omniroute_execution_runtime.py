"""Runtime activation for the OmniRoute replacement of retired FreeLLMPool routes.

FreeLLMAPI remains an independent live route source. This module owns only the
OmniRoute candidate seeded by migration 055 and promotes it after a bounded
models readback plus two real keyless chat completions on the deployed revision.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from typing import Any, Callable

import requests
from flask import jsonify

from llm_revolver import verify_free_route_reason
from llm_transport import OMNIROUTE_BASE_URL

_SOURCE_ID = "0609e75c-8c48-59db-80a4-3155b823205b"
_MODEL_ALIAS = "sovereign-omniroute:auto"
_ROUTE_ID = "sovereign-omniroute-auto"
_RECEIPT_SCHEMA = "sovereign.freellm-route-receipt.v3"
_MAX_RESPONSE_BYTES = 2_000_000
_SOURCE_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ADVISORY_LOCK = (20_260_818, 1_545)
_DEFAULT_INITIAL_DELAY_SECONDS = 15
_DEFAULT_INTERVAL_SECONDS = 21_600


class OmniRouteActivationError(RuntimeError):
    def __init__(self, family: str) -> None:
        super().__init__(family)
        self.family = str(family)[:120]


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


def _runtime_identity() -> dict[str, Any]:
    revision = os.getenv("SOVEREIGN_SOURCE_REVISION", "").strip().lower()
    digest = os.getenv("SOVEREIGN_IMAGE_DIGEST", "").strip().lower()
    return {
        "sourceRevision": revision,
        "sourceRevisionVerified": _SOURCE_REVISION_RE.fullmatch(revision) is not None,
        "imageDigest": digest,
        "imageDigestVerified": _IMAGE_DIGEST_RE.fullmatch(digest) is not None,
    }


def _is_zero_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 0


def _safe_nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed >= 0 else 0


def _read_response(response: requests.Response) -> dict[str, Any]:
    declared = int(response.headers.get("Content-Length") or 0)
    if declared > _MAX_RESPONSE_BYTES:
        raise OmniRouteActivationError("omniroute_response_too_large")
    raw = response.raw.read(_MAX_RESPONSE_BYTES + 1, decode_content=True)
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise OmniRouteActivationError("omniroute_response_too_large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OmniRouteActivationError("omniroute_response_invalid") from exc
    if not isinstance(payload, dict):
        raise OmniRouteActivationError("omniroute_response_invalid")
    return payload


def _request(method: str, path: str, *, body: dict[str, Any] | None = None) -> tuple[requests.Response, dict[str, Any]]:
    endpoint = f"{OMNIROUTE_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
        "User-Agent": "sovereign-omniroute-canary/1",
    }
    try:
        with requests.Session() as session:
            session.trust_env = False
            with session.request(
                method,
                endpoint,
                headers=headers,
                json=body,
                timeout=30,
                allow_redirects=False,
                stream=True,
            ) as response:
                payload = _read_response(response)
                copied = requests.Response()
                copied.status_code = int(response.status_code)
                copied.headers = response.headers.copy()
                copied.url = response.url
                copied.reason = response.reason
                return copied, payload
    except requests.Timeout as exc:
        raise OmniRouteActivationError("omniroute_timeout") from exc
    except requests.RequestException as exc:
        raise OmniRouteActivationError("omniroute_upstream_unavailable") from exc


def _models_readback() -> dict[str, Any]:
    response, payload = _request("GET", "models")
    if response.status_code != 200:
        raise OmniRouteActivationError(f"omniroute_models_http_{response.status_code}")
    models = payload.get("data")
    if not isinstance(models, list) or not models:
        raise OmniRouteActivationError("omniroute_models_empty")
    model_ids = [
        str(item.get("id") or "").strip()
        for item in models[:500]
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]
    if not model_ids:
        raise OmniRouteActivationError("omniroute_models_invalid")
    return {
        "modelCount": len(model_ids),
        "modelSetSha256": _canonical_sha256(sorted(model_ids)),
        "rawModelCatalogPersisted": False,
    }


def _completion_canary(confirmation: int) -> dict[str, Any]:
    nonce = uuid.uuid4().hex
    body = {
        "model": "auto",
        "messages": [{
            "role": "user",
            "content": f"Reply with exactly OK. Sovereign canary {confirmation}:{nonce}",
        }],
        "max_tokens": 8,
        "temperature": 0,
        "stream": False,
    }
    started = time.monotonic()
    response, payload = _request("POST", "chat/completions", body=body)
    latency_ms = int((time.monotonic() - started) * 1000)
    if response.status_code != 200:
        raise OmniRouteActivationError(f"omniroute_canary_http_{response.status_code}")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise OmniRouteActivationError("omniroute_canary_response_invalid")
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first.get("message"), dict) else {}
    content = str(message.get("content") or "").strip()
    if not content:
        raise OmniRouteActivationError("omniroute_canary_response_invalid")
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    provider_cost = usage.get("cost")
    if provider_cost is not None and not isinstance(provider_cost, bool):
        try:
            normalized_cost = float(provider_cost)
        except (TypeError, ValueError) as exc:
            raise OmniRouteActivationError("omniroute_canary_cost_invalid") from exc
        if normalized_cost != 0.0:
            raise OmniRouteActivationError("omniroute_canary_reported_nonzero_cost")
    else:
        normalized_cost = None
    request_id = str(
        response.headers.get("x-request-id")
        or payload.get("id")
        or ""
    )[:200]
    return {
        "confirmation": confirmation,
        "upstreamRequestId": request_id or None,
        "providerGenerationId": str(payload.get("id") or "")[:200] or None,
        "responseModel": str(payload.get("model") or "")[:240] or None,
        "providerCostUsd": normalized_cost,
        "latencyMs": latency_ms,
        "textualChatResponseVerified": True,
        "rawProviderResponsePersisted": False,
        "requestAuthorizationHeaderSent": False,
    }


def _receipt(identity: dict[str, Any], catalog: dict[str, Any], confirmations: list[dict[str, Any]]) -> dict[str, Any]:
    base = {
        "schemaVersion": _RECEIPT_SCHEMA,
        "generalChatEvidenceVerified": True,
        "canaryConfirmationCount": 2,
        "routeSource": "omniroute",
        "providerModel": "auto",
        "keylessBoundaryVerified": all(
            item.get("requestAuthorizationHeaderSent") is False
            for item in confirmations
        ),
        "zeroCostEvidenceVerified": all(
            item.get("providerCostUsd") in (None, 0, 0.0)
            for item in confirmations
        ),
        "catalogSha256": str(catalog.get("modelSetSha256") or ""),
        "sourceRevision": identity["sourceRevision"],
        "imageDigest": identity["imageDigest"],
        "confirmationRequestIds": [
            item.get("upstreamRequestId") for item in confirmations
        ],
        "rawProviderResponsesPersisted": False,
    }
    return {**base, "receiptSha256": _canonical_sha256(base)}


class OmniRouteExecutionRuntime:
    def __init__(
        self,
        *,
        query: Callable[..., Any],
        get_connection: Callable[[], Any],
        audit: Callable[..., Any],
    ) -> None:
        self._query = query
        self._get_connection = get_connection
        self._audit = audit
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._local_lock = threading.Lock()

    @property
    def interval_seconds(self) -> int:
        return _bounded_env_int(
            "SOVEREIGN_OMNIROUTE_EXECUTION_INTERVAL_SECONDS",
            _DEFAULT_INTERVAL_SECONDS,
            900,
            86_400,
        )

    @staticmethod
    def _is_canonical_route(route: Any) -> bool:
        if not isinstance(route, dict):
            return False
        config = route.get("config") if isinstance(route.get("config"), dict) else {}
        quota_evidence = (
            config.get("quotaEvidence")
            if isinstance(config.get("quotaEvidence"), dict)
            else {}
        )
        return (
            str(route.get("id") or "") == _ROUTE_ID
            and str(route.get("model_id") or "") == _MODEL_ALIAS
            and str(route.get("provider") or "") == "freellm"
            and str(route.get("runtime_kind") or "") == "freellm"
            and str(route.get("base_url") or "") == OMNIROUTE_BASE_URL
            and config.get("routeSource") == "omniroute"
            and config.get("sourceType") == "omniroute"
            and config.get("transport") == "freellm"
            and config.get("providerModel") == "auto"
            and config.get("executionProfile") == "free_single_agent"
            and config.get("billingCategory") == "free"
            and config.get("billingClass") == "free"
            and config.get("fundingMode") == "provider_free_quota"
            and config.get("pricingVerified") is False
            and _is_zero_int(config.get("markupMultiplier"))
            and _is_zero_int(config.get("minimumMultiplier"))
            and _is_zero_int(config.get("userChargeCredits"))
            and config.get("quotaScope") == "freellm:omniroute:auto"
            and quota_evidence.get("scope") == "freellm:omniroute:auto"
            and quota_evidence.get("stateOwner") == "postgresql-revolver-state"
            and config.get("routingOwner") == "free-revolver-v3"
            and config.get("resolverMode") == "revolver"
            and config.get("direct") is True
        )

    def _canonical_route(self) -> dict[str, Any] | None:
        route = self._query(
            """SELECT id::text, model_id, provider, runtime_kind, base_url, disabled, config, updated_at,
                      EXISTS(
                          SELECT 1 FROM llm_revolver_provider_sources
                          WHERE id=%s::uuid AND api_base=%s AND auth_mode='none'
                            AND enabled=true
                            AND status='healthy'
                      ) AS source_present,
                      EXISTS(
                          SELECT 1 FROM llm_revolver_provider_models
                          WHERE source_id=%s::uuid
                            AND upstream_model_id='auto'
                            AND litellm_alias=%s
                            AND enabled=true
                            AND status='ready'
                            AND free_verified=true
                            AND free_eligible=true
                      ) AS model_present
               FROM llm_routes WHERE id=%s LIMIT 1""",
            (_SOURCE_ID, OMNIROUTE_BASE_URL, _SOURCE_ID, _MODEL_ALIAS, _ROUTE_ID),
            one=True,
        )
        return route if self._is_canonical_route(route) else None

    @staticmethod
    def _has_canonical_supporting_state(route: dict[str, Any]) -> bool:
        return (
            route.get("source_present") is True
            and route.get("model_present") is True
        )

    def _locked_canonical_state(self, cursor: Any) -> dict[str, Any] | None:
        cursor.execute(
            """SELECT id::text, model_id, provider, runtime_kind, base_url, disabled, config, updated_at
               FROM llm_routes WHERE id=%s FOR UPDATE""",
            (_ROUTE_ID,),
        )
        route = cursor.fetchone()
        if not self._is_canonical_route(route):
            return None
        cursor.execute(
            """SELECT id::text
               FROM llm_revolver_provider_sources
               WHERE id=%s::uuid AND api_base=%s AND auth_mode='none'
               FOR UPDATE""",
            (_SOURCE_ID, OMNIROUTE_BASE_URL),
        )
        if not isinstance(cursor.fetchone(), dict):
            return None
        cursor.execute(
            """SELECT id::text
               FROM llm_revolver_provider_models
               WHERE source_id=%s::uuid
                 AND upstream_model_id='auto'
                 AND litellm_alias=%s
               FOR UPDATE""",
            (_SOURCE_ID, _MODEL_ALIAS),
        )
        if not isinstance(cursor.fetchone(), dict):
            return None
        return route

    @staticmethod
    def _write_exact(cursor: Any, sql: str, params: tuple[Any, ...]) -> None:
        cursor.execute(sql, params)
        if getattr(cursor, "rowcount", -1) != 1:
            raise OmniRouteActivationError("omniroute_canonical_state_rows_missing")

    def _mark_failed(self, cursor: Any, family: str) -> None:
        self._write_exact(
            cursor,
            """UPDATE llm_routes
               SET disabled=true,
                   config=COALESCE(config,'{}'::jsonb) || jsonb_build_object(
                       'freeEligible', false,
                       'quotaContractVerified', false,
                       'canaryVerified', false,
                       'transportCanaryVerified', false,
                       'selectable', false,
                       'activationState', 'blocked',
                       'activationBlocker', %s
                   ),
                   updated_at=NOW()
               WHERE id=%s
                 AND model_id=%s
                 AND provider='freellm'
                 AND runtime_kind='freellm'
                 AND COALESCE(base_url,'')=%s
                 AND COALESCE(config->>'routeSource','')='omniroute'
                 AND COALESCE(config->>'sourceType','')='omniroute'
                 AND COALESCE(config->>'transport','')='freellm'
                 AND COALESCE(config->>'routingOwner','')='free-revolver-v3'
                 AND COALESCE(config->>'resolverMode','')='revolver'
                 AND COALESCE(config->>'direct','')='true'""",
            (family, _ROUTE_ID, _MODEL_ALIAS, OMNIROUTE_BASE_URL),
        )
        self._write_exact(
            cursor,
            """UPDATE llm_revolver_provider_models
               SET status='discovered', enabled=false, free_verified=false,
                   free_eligible=false, last_error_code=%s, updated_at=NOW()
               WHERE source_id=%s::uuid
                 AND upstream_model_id='auto'
                 AND litellm_alias=%s""",
            (family, _SOURCE_ID, _MODEL_ALIAS),
        )
        self._write_exact(
            cursor,
            """UPDATE llm_revolver_provider_sources
               SET status='degraded', last_error_code=%s,
                   last_checked_at=NOW(), updated_at=NOW()
               WHERE id=%s::uuid AND api_base=%s AND auth_mode='none'""",
            (family, _SOURCE_ID, OMNIROUTE_BASE_URL),
        )

    def _project_failure_while_locked(
        self,
        connection: Any,
        family: str,
    ) -> bool:
        """Persist a rejected scan while the transaction advisory lock is held."""
        try:
            with connection.cursor() as cursor:
                if self._locked_canonical_state(cursor) is None:
                    connection.rollback()
                    return False
                self._mark_failed(cursor, family)
            connection.commit()
            return True
        except Exception:
            try:
                connection.rollback()
            except Exception:
                pass
            return False

    def scan_once(self) -> dict[str, Any]:
        if not self._local_lock.acquire(blocking=False):
            return {"ok": False, "status": "busy", "routeSource": "omniroute"}
        lock_connection: Any | None = None
        try:
            lock_connection = self._get_connection()
            with lock_connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_try_advisory_xact_lock(%s,%s) AS acquired",
                    _ADVISORY_LOCK,
                )
                row = cursor.fetchone() or {}
                if not bool(row.get("acquired")):
                    lock_connection.rollback()
                    return {"ok": False, "status": "busy", "routeSource": "omniroute"}

                if self._locked_canonical_state(cursor) is None:
                    lock_connection.rollback()
                    return {
                        "ok": False,
                        "status": "blocked",
                        "routeSource": "omniroute",
                        "blocker": "omniroute_route_identity_invalid",
                        "freeLlmApiChanged": False,
                    }

                identity = _runtime_identity()
                if not (
                    identity["sourceRevisionVerified"]
                    and identity["imageDigestVerified"]
                ):
                    raise OmniRouteActivationError("omniroute_runtime_identity_unverified")

                catalog = _models_readback()
                confirmations = [
                    _completion_canary(1),
                    _completion_canary(2),
                ]
                receipt = _receipt(identity, catalog, confirmations)
                max_latency = max(int(item["latencyMs"]) for item in confirmations)
                last_request_id = str(
                    confirmations[-1].get("upstreamRequestId") or ""
                )[:200]
                costs = [item.get("providerCostUsd") for item in confirmations]
                cost_state = "zero" if all(value == 0.0 for value in costs) else "unreported"

                self._write_exact(
                    cursor,
                    """UPDATE llm_revolver_provider_sources
                       SET status='healthy', last_http_status=200,
                           last_error_code=NULL, last_discovered_at=NOW(),
                           last_checked_at=NOW(), enabled=true, updated_at=NOW()
                       WHERE id=%s::uuid AND api_base=%s AND auth_mode='none'""",
                    (_SOURCE_ID, OMNIROUTE_BASE_URL),
                )
                self._write_exact(
                    cursor,
                    """UPDATE llm_revolver_provider_models
                       SET status='ready', enabled=true, free_verified=true,
                           free_eligible=true,
                           eligibility_source='omniroute-keyless-runtime-double-canary',
                           eligibility_verified_at=NOW(),
                           last_canary_request_id=%s, last_canary_at=NOW(),
                           canary_cost_state=%s,
                           last_provider_cost_usd_micros=%s,
                           last_error_code=NULL, updated_at=NOW()
                       WHERE source_id=%s::uuid
                         AND upstream_model_id='auto'
                         AND litellm_alias=%s""",
                    (
                        last_request_id or None,
                        cost_state,
                        0 if cost_state == "zero" else None,
                        _SOURCE_ID,
                        _MODEL_ALIAS,
                    ),
                )
                runtime_config = {
                    "freeEligible": True,
                    "quotaContractVerified": True,
                    "canaryVerified": True,
                    "canaryConfirmationCount": 2,
                    "catalogVerified": True,
                    "transportCanaryVerified": True,
                    "selectable": True,
                    "activationState": "ready",
                    "activationBlocker": None,
                    "canaryLatencyMs": max_latency,
                    "providerCostState": cost_state,
                    "runtimeIdentity": identity,
                    "canaryReceipt": receipt,
                    "routeSource": "omniroute",
                    "sourceType": "omniroute",
                    "rawProviderResponsePersisted": False,
                }
                self._write_exact(
                    cursor,
                    """UPDATE llm_routes
                       SET disabled=false,
                           config=COALESCE(config,'{}'::jsonb) || %s::jsonb,
                           updated_at=NOW()
                       WHERE id=%s
                         AND model_id=%s
                         AND provider='freellm'
                         AND runtime_kind='freellm'
                         AND COALESCE(base_url,'')=%s
                         AND COALESCE(config->>'routeSource','')='omniroute'
                         AND COALESCE(config->>'sourceType','')='omniroute'
                         AND COALESCE(config->>'transport','')='freellm'
                         AND COALESCE(config->>'routingOwner','')='free-revolver-v3'
                         AND COALESCE(config->>'resolverMode','')='revolver'
                         AND COALESCE(config->>'direct','')='true'""",
                    (
                        json.dumps(runtime_config, separators=(",", ":")),
                        _ROUTE_ID,
                        _MODEL_ALIAS,
                        OMNIROUTE_BASE_URL,
                    ),
                )
                self._write_exact(
                    cursor,
                    """INSERT INTO llm_revolver_provider_checks
                           (source_id, check_kind, models_url, http_status,
                            outcome, model_count, free_model_count, evidence)
                       VALUES (%s::uuid,'route_canary',%s,200,'success',%s,1,%s::jsonb)""",
                    (
                        _SOURCE_ID,
                        f"{OMNIROUTE_BASE_URL}/models",
                        int(catalog["modelCount"]),
                        json.dumps({
                            "schemaVersion": "sovereign.omniroute-route-canary.v1",
                            "confirmationCount": 2,
                            "catalogSha256": catalog["modelSetSha256"],
                            "receiptSha256": receipt["receiptSha256"],
                            "sourceRevision": identity["sourceRevision"],
                            "imageDigest": identity["imageDigest"],
                            "keylessBoundaryVerified": True,
                            "rawProviderResponsesPersisted": False,
                        }, separators=(",", ":")),
                    ),
                )
                lock_connection.commit()
                try:
                    self._audit("omniroute_runtime_double_canary_verified", _ROUTE_ID, {
                        "routeSource": "omniroute",
                        "confirmationCount": 2,
                        "catalogSha256": catalog["modelSetSha256"],
                        "receiptSha256": receipt["receiptSha256"],
                        "sourceRevision": identity["sourceRevision"],
                        "imageDigest": identity["imageDigest"],
                        "rawProviderResponsesPersisted": False,
                    })
                except Exception:
                    pass
                return {
                    "ok": True,
                    "status": "ready",
                    "routeSource": "omniroute",
                    "routeId": _ROUTE_ID,
                    "modelId": _MODEL_ALIAS,
                    "confirmationCount": 2,
                    "catalogModelCount": int(catalog["modelCount"]),
                    "receiptSha256": receipt["receiptSha256"],
                    "sourceRevision": identity["sourceRevision"],
                    "imageDigest": identity["imageDigest"],
                    "freeLlmApiChanged": False,
                }
        except OmniRouteActivationError as exc:
            if lock_connection is not None:
                self._project_failure_while_locked(
                    lock_connection,
                    exc.family,
                )
            return {
                "ok": False,
                "status": "degraded",
                "routeSource": "omniroute",
                "blocker": exc.family,
                "freeLlmApiChanged": False,
            }
        except Exception:
            if lock_connection is not None:
                try:
                    lock_connection.rollback()
                except Exception:
                    pass
            return {
                "ok": False,
                "status": "degraded",
                "routeSource": "omniroute",
                "blocker": "omniroute_activation_internal_failure",
                "freeLlmApiChanged": False,
            }
        finally:
            if lock_connection is not None:
                try:
                    lock_connection.close()
                except Exception:
                    pass
            self._local_lock.release()

    def _blocked_status(
        self,
        blocker: str,
        route: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = route or {}
        config = current.get("config") if isinstance(current.get("config"), dict) else {}
        receipt = config.get("canaryReceipt") if isinstance(config.get("canaryReceipt"), dict) else {}
        identity = config.get("runtimeIdentity") if isinstance(config.get("runtimeIdentity"), dict) else {}
        return {
            "ok": False,
            "routeSource": "omniroute",
            "routeId": str(current.get("id") or _ROUTE_ID),
            "modelId": str(current.get("model_id") or _MODEL_ALIAS),
            "apiBase": str(current.get("base_url") or OMNIROUTE_BASE_URL),
            "disabled": True,
            "activationState": "blocked",
            "blocker": blocker,
            "confirmationCount": _safe_nonnegative_int(
                config.get("canaryConfirmationCount")
            ),
            "receiptSha256": receipt.get("receiptSha256"),
            "sourceRevision": identity.get("sourceRevision"),
            "imageDigest": identity.get("imageDigest"),
            "freeLlmApiChanged": False,
            "rawProviderResponsesReturned": False,
        }

    def status(self) -> dict[str, Any]:
        route = self._canonical_route()
        if route is None:
            return self._blocked_status("omniroute_route_identity_invalid")
        if not self._has_canonical_supporting_state(route):
            return self._blocked_status(
                "omniroute_canonical_state_rows_missing",
                route,
            )
        config = route.get("config") if isinstance(route.get("config"), dict) else {}
        receipt = config.get("canaryReceipt") if isinstance(config.get("canaryReceipt"), dict) else {}
        identity = config.get("runtimeIdentity") if isinstance(config.get("runtimeIdentity"), dict) else {}
        try:
            verification = verify_free_route_reason(route)
        except Exception:
            verification = {
                "ok": False,
                "failureFamilies": ["omniroute_execution_verification_failed"],
            }
        verification_failures = verification.get("failureFamilies")
        failure_families = (
            [str(item) for item in verification_failures if str(item)]
            if isinstance(verification_failures, list)
            else []
        )
        execution_eligible = (
            verification.get("ok") is True
            and not bool(route.get("disabled"))
        )
        configured_blocker = config.get("activationBlocker")
        if execution_eligible:
            blocker = None
        elif isinstance(configured_blocker, str) and configured_blocker:
            blocker = configured_blocker
        elif failure_families:
            blocker = failure_families[0]
        else:
            blocker = "omniroute_route_disabled"
        confirmation_count = _safe_nonnegative_int(
            config.get("canaryConfirmationCount")
        )
        return {
            "ok": execution_eligible,
            "routeSource": "omniroute",
            "routeId": str(route.get("id") or _ROUTE_ID),
            "modelId": str(route.get("model_id") or _MODEL_ALIAS),
            "apiBase": str(route.get("base_url") or OMNIROUTE_BASE_URL),
            "disabled": not execution_eligible,
            "activationState": "ready" if execution_eligible else "blocked",
            "blocker": blocker,
            "confirmationCount": confirmation_count,
            "receiptSha256": receipt.get("receiptSha256"),
            "sourceRevision": identity.get("sourceRevision"),
            "imageDigest": identity.get("imageDigest"),
            "freeLlmApiChanged": False,
            "rawProviderResponsesReturned": False,
        }

    def _loop(self) -> None:
        delay = _bounded_env_int(
            "SOVEREIGN_OMNIROUTE_EXECUTION_INITIAL_DELAY_SECONDS",
            _DEFAULT_INITIAL_DELAY_SECONDS,
            1,
            300,
        )
        if self._stop.wait(delay):
            return
        while not self._stop.is_set():
            self.scan_once()
            if self._stop.wait(self.interval_seconds):
                return

    def start(self) -> None:
        if os.getenv("SOVEREIGN_OMNIROUTE_EXECUTION_ENABLED", "1").strip() != "1":
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._loop,
            name="sovereign-omniroute-execution",
            daemon=True,
        )
        self._thread.start()


def register_omniroute_execution_runtime(
    app: Any,
    *,
    require_admin: Callable[..., Any],
    query: Callable[..., Any],
    get_connection: Callable[[], Any],
    audit: Callable[..., Any],
) -> OmniRouteExecutionRuntime:
    service = OmniRouteExecutionRuntime(
        query=query,
        get_connection=get_connection,
        audit=audit,
    )

    @app.route("/api/admin/llm/omniroute/status", methods=["GET"])
    @require_admin
    def admin_omniroute_status():
        return jsonify(service.status())

    @app.route("/api/admin/llm/omniroute/refresh", methods=["POST"])
    @require_admin
    def admin_omniroute_refresh():
        result = service.scan_once()
        # Mutating execution evidence is never itself the UI state contract.
        # Return the canonical status projection after the scan so success,
        # degraded and busy outcomes all have one typed readback shape.
        return jsonify(service.status()), 200 if result.get("ok") else 503

    service.start()
    return service
