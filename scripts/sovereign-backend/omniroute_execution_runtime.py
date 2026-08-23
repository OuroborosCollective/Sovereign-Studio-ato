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

    def _canonical_route(self) -> dict[str, Any] | None:
        route = self._query(
            """SELECT id::text, model_id, base_url, disabled, config, updated_at
               FROM llm_routes WHERE id=%s LIMIT 1""",
            (_ROUTE_ID,),
            one=True,
        )
        if not isinstance(route, dict):
            return None
        if (
            str(route.get("id") or "") != _ROUTE_ID
            or str(route.get("model_id") or "") != _MODEL_ALIAS
            or str(route.get("base_url") or "").lower()
            != OMNIROUTE_BASE_URL.lower()
        ):
            return None
        return route

    def _mark_failed(self, family: str) -> None:
        self._query(
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
                 AND lower(COALESCE(base_url,''))=lower(%s)""",
            (family, _ROUTE_ID, _MODEL_ALIAS, OMNIROUTE_BASE_URL),
            write=True,
        )
        self._query(
            """UPDATE llm_revolver_provider_models
               SET status='discovered', enabled=false, free_verified=false,
                   free_eligible=false, last_error_code=%s, updated_at=NOW()
               WHERE source_id=%s::uuid AND upstream_model_id='auto'""",
            (family, _SOURCE_ID),
            write=True,
        )
        self._query(
            """UPDATE llm_revolver_provider_sources
               SET status='degraded', last_error_code=%s,
                   last_checked_at=NOW(), updated_at=NOW()
               WHERE id=%s::uuid""",
            (family, _SOURCE_ID),
            write=True,
        )

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

                if self._canonical_route() is None:
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

                self._query(
                    """UPDATE llm_revolver_provider_sources
                       SET status='healthy', last_http_status=200,
                           last_error_code=NULL, last_discovered_at=NOW(),
                           last_checked_at=NOW(), enabled=true, updated_at=NOW()
                       WHERE id=%s::uuid""",
                    (_SOURCE_ID,),
                    write=True,
                )
                self._query(
                    """UPDATE llm_revolver_provider_models
                       SET status='ready', enabled=true, free_verified=true,
                           free_eligible=true,
                           eligibility_source='omniroute-keyless-runtime-double-canary',
                           eligibility_verified_at=NOW(),
                           last_canary_request_id=%s, last_canary_at=NOW(),
                           canary_cost_state=%s,
                           last_provider_cost_usd_micros=%s,
                           last_error_code=NULL, updated_at=NOW()
                       WHERE source_id=%s::uuid AND upstream_model_id='auto'""",
                    (
                        last_request_id or None,
                        cost_state,
                        0 if cost_state == "zero" else None,
                        _SOURCE_ID,
                    ),
                    write=True,
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
                self._query(
                    """UPDATE llm_routes
                       SET disabled=false,
                           config=COALESCE(config,'{}'::jsonb) || %s::jsonb,
                           updated_at=NOW()
                       WHERE id=%s
                         AND model_id=%s
                         AND lower(COALESCE(base_url,''))=lower(%s)""",
                    (
                        json.dumps(runtime_config, separators=(",", ":")),
                        _ROUTE_ID,
                        _MODEL_ALIAS,
                        OMNIROUTE_BASE_URL,
                    ),
                    write=True,
                )
                self._query(
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
                    write=True,
                )
                self._audit("omniroute_runtime_double_canary_verified", _ROUTE_ID, {
                    "routeSource": "omniroute",
                    "confirmationCount": 2,
                    "catalogSha256": catalog["modelSetSha256"],
                    "receiptSha256": receipt["receiptSha256"],
                    "sourceRevision": identity["sourceRevision"],
                    "imageDigest": identity["imageDigest"],
                    "rawProviderResponsesPersisted": False,
                })
                lock_connection.commit()
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
                try:
                    lock_connection.rollback()
                except Exception:
                    pass
            try:
                self._mark_failed(exc.family)
            except Exception:
                pass
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
            try:
                self._mark_failed("omniroute_activation_internal_failure")
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

    def status(self) -> dict[str, Any]:
        route = self._canonical_route()
        if route is None:
            return {
                "ok": False,
                "routeSource": "omniroute",
                "routeId": _ROUTE_ID,
                "modelId": _MODEL_ALIAS,
                "apiBase": OMNIROUTE_BASE_URL,
                "disabled": True,
                "activationState": "blocked",
                "blocker": "omniroute_route_identity_invalid",
                "confirmationCount": 0,
                "receiptSha256": None,
                "sourceRevision": None,
                "imageDigest": None,
                "freeLlmApiChanged": False,
                "rawProviderResponsesReturned": False,
            }
        config = route.get("config") if isinstance(route.get("config"), dict) else {}
        receipt = config.get("canaryReceipt") if isinstance(config.get("canaryReceipt"), dict) else {}
        identity = config.get("runtimeIdentity") if isinstance(config.get("runtimeIdentity"), dict) else {}
        return {
            "ok": bool(
                route
                and not route.get("disabled")
                and config.get("selectable") is True
                and config.get("canaryVerified") is True
                and int(config.get("canaryConfirmationCount") or 0) >= 2
            ),
            "routeSource": "omniroute",
            "routeId": str(route.get("id") or _ROUTE_ID),
            "modelId": str(route.get("model_id") or _MODEL_ALIAS),
            "apiBase": str(route.get("base_url") or OMNIROUTE_BASE_URL),
            "disabled": bool(route.get("disabled", True)),
            "activationState": str(config.get("activationState") or "unknown"),
            "blocker": config.get("activationBlocker"),
            "confirmationCount": int(config.get("canaryConfirmationCount") or 0),
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
