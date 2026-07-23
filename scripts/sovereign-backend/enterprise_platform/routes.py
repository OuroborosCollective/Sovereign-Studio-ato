"""Flask transport adapter for the enterprise platform application service."""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

from flask import Blueprint, Flask, g, jsonify, request

from .contracts import SCHEMA_VERSION, api_error
from .service import (
    EnterprisePlatformService,
    PlatformEvidenceWriteError,
)


def _request_id() -> str:
    value = getattr(g, "sovereign_request_id", None)
    return str(value or uuid.uuid4())


def _actor_id(get_current_admin) -> str:
    admin = get_current_admin() or {}
    try:
        return str(uuid.UUID(str(admin.get("id") or "")))
    except (TypeError, ValueError, AttributeError):
        return ""


def _openapi_contract() -> dict[str, Any]:
    protected = [{"bearerAuth": []}]
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Sovereign Enterprise Platform Admin API",
            "version": "1.0.0",
            "description": "Evidence-first administrative platform API. Every route requires the existing admin bearer key.",
        },
        "servers": [{"url": "/api/admin/platform/v1"}],
        "paths": {
            "/identity": {"get": {"security": protected, "responses": {"200": {"description": "Runtime identity"}}}},
            "/overview": {"get": {"security": protected, "responses": {"200": {"description": "Live platform overview"}}}},
            "/statistics": {"get": {"security": protected, "responses": {"200": {"description": "Database-backed statistics"}}}},
            "/integrations": {"get": {"security": protected, "responses": {"200": {"description": "Dependency evidence"}}}},
            "/evidence": {"get": {"security": protected, "responses": {"200": {"description": "Persisted evidence receipts"}}}},
            "/canaries": {
                "post": {
                    "security": protected,
                    "requestBody": {"required": True},
                    "responses": {
                        "200": {"description": "Verified and persisted canary"},
                        "400": {"description": "Invalid input"},
                        "410": {"description": "Legacy completion canary removed"},
                        "503": {"description": "Evidence persistence failed"},
                    },
                }
            },
            "/openapi.json": {"get": {"security": protected, "responses": {"200": {"description": "This contract"}}}},
        },
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "admin-api-key"}
            }
        },
    }


def register_enterprise_platform_routes(
    app: Flask,
    *,
    require_admin,
    query,
    get_current_admin,
    audit,
) -> EnterprisePlatformService:
    service = EnterprisePlatformService(query=query)
    app.extensions["sovereign_enterprise_platform"] = service

    try:
        configured_max_bytes = int(
            os.getenv("SOVEREIGN_MAX_REQUEST_BYTES", str(64 * 1024 * 1024))
        )
    except (TypeError, ValueError):
        configured_max_bytes = 64 * 1024 * 1024
    app.config["MAX_CONTENT_LENGTH"] = max(
        1_048_576,
        min(configured_max_bytes, 128 * 1024 * 1024),
    )

    @app.before_request
    def sovereign_request_context():
        incoming = request.headers.get("X-Request-ID", "").strip()
        try:
            correlation_id = str(uuid.UUID(incoming)) if incoming else str(uuid.uuid4())
        except ValueError:
            correlation_id = str(uuid.uuid4())
        g.sovereign_request_id = correlation_id
        g.sovereign_request_started = time.monotonic()

    @app.after_request
    def sovereign_security_headers(response):
        response.headers["X-Request-ID"] = _request_id()
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        started = getattr(g, "sovereign_request_started", None)
        if isinstance(started, float):
            response.headers["Server-Timing"] = f"app;dur={max(0, (time.monotonic() - started) * 1000):.1f}"
        return response

    blueprint = Blueprint(
        "sovereign_enterprise_platform_v1",
        __name__,
        url_prefix="/api/admin/platform/v1",
    )

    @blueprint.get("/identity")
    @require_admin
    def platform_identity():
        return jsonify({
            "ok": True,
            "schemaVersion": SCHEMA_VERSION,
            "requestId": _request_id(),
            "runtime": service.runtime_identity(),
        })

    @blueprint.get("/overview")
    @require_admin
    def platform_overview():
        payload = service.overview()
        payload["requestId"] = _request_id()
        return jsonify(payload)

    @blueprint.get("/statistics")
    @require_admin
    def platform_statistics():
        statistics = service.statistics()
        return jsonify({
            "ok": statistics.get("status") == "verified",
            "schemaVersion": SCHEMA_VERSION,
            "requestId": _request_id(),
            "statistics": statistics,
        })

    @blueprint.get("/integrations")
    @require_admin
    def platform_integrations():
        integrations = service.integrations()
        return jsonify({
            "ok": all(
                item.get("status") == "verified"
                for item in integrations
                if item.get("required")
            ),
            "schemaVersion": SCHEMA_VERSION,
            "requestId": _request_id(),
            "integrations": integrations,
        })

    @blueprint.get("/evidence")
    @require_admin
    def platform_evidence():
        try:
            limit = max(1, min(int(request.args.get("limit", "30")), 100))
        except ValueError:
            return jsonify(api_error(
                "platform_evidence_limit_invalid",
                "Das Evidence-Limit muss eine Zahl zwischen 1 und 100 sein.",
                _request_id(),
            )), 400
        try:
            rows = service.list_evidence(limit)
        except Exception:
            return jsonify(api_error(
                "platform_evidence_read_failed",
                "Runtime-Evidence konnte nicht gelesen werden.",
                _request_id(),
                blocker="platform_evidence_read_failed",
            )), 503
        return jsonify({
            "ok": True,
            "schemaVersion": SCHEMA_VERSION,
            "requestId": _request_id(),
            "evidence": rows,
            "count": len(rows),
        })

    @blueprint.post("/canaries")
    @require_admin
    def platform_canaries():
        if not request.is_json:
            return jsonify(api_error(
                "platform_json_required",
                "Für diesen Endpunkt ist application/json erforderlich.",
                _request_id(),
            )), 415
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify(api_error(
                "platform_body_invalid",
                "Der Request-Body muss ein JSON-Objekt sein.",
                _request_id(),
            )), 400
        actor_id = _actor_id(get_current_admin)
        if not actor_id:
            return jsonify(api_error(
                "platform_admin_identity_missing",
                "Der authentifizierte Admin besitzt keine persistente Identität.",
                _request_id(),
                blocker="admin_identity_missing",
            )), 403

        scope = str(body.get("scope") or "").strip().lower()
        if scope != "readiness":
            return jsonify(api_error(
                "platform_legacy_completion_canary_removed",
                "Completion-Canaries über Legacy-LiteLLM wurden entfernt. OpenRouter- und FreeLLM-Prüfungen laufen ausschließlich in ihren direkten Providerbereichen.",
                _request_id(),
                blocker="legacy_litellm_replaced_by_direct_routes",
            )), 410

        try:
            result = service.run_canary(
                request_id=_request_id(),
                actor_id=actor_id,
                scope="readiness",
                model_id=None,
                confirmed=False,
            )
        except ValueError as exc:
            code = str(exc)
            return jsonify(api_error(
                code,
                "Der Readiness-Canary-Request ist ungültig.",
                _request_id(),
            )), 400
        except PlatformEvidenceWriteError:
            return jsonify(api_error(
                "platform_evidence_write_failed",
                "Der Canary lief, aber sein persistenter Evidence-Readback ist fehlgeschlagen.",
                _request_id(),
                blocker="evidence_not_persisted",
            )), 503

        audit(
            "enterprise_platform_canary",
            result.get("receipt", {}).get("id"),
            {
                "scope": result.get("scope"),
                "status": result.get("status"),
                "evidenceSha256": result.get("receipt", {}).get("evidenceSha256"),
                "requestId": result.get("requestId"),
            },
        )
        return jsonify(result), 200 if result.get("ok") else 503

    @blueprint.get("/openapi.json")
    @require_admin
    def platform_openapi():
        return jsonify(_openapi_contract())

    app.register_blueprint(blueprint)
    return service
