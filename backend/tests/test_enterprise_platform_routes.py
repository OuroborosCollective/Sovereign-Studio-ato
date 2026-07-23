from __future__ import annotations

import sys
from functools import wraps
from pathlib import Path
from typing import Any

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

try:
    from flask import Flask, jsonify, request
    from enterprise_platform.routes import register_enterprise_platform_routes
except ModuleNotFoundError:
    FLASK_AVAILABLE = False
else:
    FLASK_AVAILABLE = True


ADMIN_ID = "11111111-1111-4111-8111-111111111111"
REQUEST_ID = "22222222-2222-4222-8222-222222222222"


class RouteQueryDouble:
    def __call__(
        self,
        statement: str,
        params: tuple[Any, ...] | None = None,
        *,
        one: bool = False,
        write: bool = False,
    ) -> Any:
        if "platform:models:active" in statement:
            return [{"model_id": "sovereign-fast"}]
        if "platform:evidence:list" in statement:
            return []
        raise AssertionError("Unexpected route SQL contract: " + statement[:100])


def test_route_contract_is_statically_present_without_runtime_dependencies() -> None:
    source = (BACKEND_ROOT / "enterprise_platform" / "routes.py").read_text(encoding="utf-8")
    assert 'url_prefix="/api/admin/platform/v1"' in source
    assert "@require_admin" in source
    assert 'response.headers["X-Content-Type-Options"] = "nosniff"' in source
    assert "PlatformCanaryRateLimited" not in source
    assert "PlatformModelRejected" not in source
    assert '"platform_legacy_completion_canary_removed"' in source
    assert 'blocker="legacy_litellm_replaced_by_direct_routes"' in source


def build_app(monkeypatch: pytest.MonkeyPatch) -> Flask:
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", "a" * 40)
    monkeypatch.setenv("SOVEREIGN_IMAGE_DIGEST", "sha256:" + "b" * 64)
    monkeypatch.setenv("SOVEREIGN_MAX_REQUEST_BYTES", "invalid")
    app = Flask(__name__)

    def require_admin(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if request.headers.get("Authorization") != "Bearer existing-admin-key":
                return jsonify({"ok": False, "error": "unauthorized"}), 401
            return view(*args, **kwargs)

        return wrapped

    register_enterprise_platform_routes(
        app,
        require_admin=require_admin,
        query=RouteQueryDouble(),
        get_current_admin=lambda: {"id": ADMIN_ID},
        audit=lambda *_args, **_kwargs: None,
    )
    return app


@pytest.mark.skipif(not FLASK_AVAILABLE, reason="Flask is installed by backend CI")
def test_routes_reuse_existing_admin_auth_and_add_security_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = build_app(monkeypatch)
    client = app.test_client()

    denied = client.get("/api/admin/platform/v1/identity")
    assert denied.status_code == 401

    response = client.get(
        "/api/admin/platform/v1/identity",
        headers={
            "Authorization": "Bearer existing-admin-key",
            "X-Request-ID": REQUEST_ID,
        },
    )

    assert response.status_code == 200
    assert response.json["requestId"] == REQUEST_ID
    assert response.headers["X-Request-ID"] == REQUEST_ID
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert app.config["MAX_CONTENT_LENGTH"] == 64 * 1024 * 1024


@pytest.mark.skipif(not FLASK_AVAILABLE, reason="Flask is installed by backend CI")
def test_canary_route_requires_json_and_openapi_declares_bearer_security(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = build_app(monkeypatch)
    client = app.test_client()
    headers = {"Authorization": "Bearer existing-admin-key"}

    response = client.post(
        "/api/admin/platform/v1/canaries",
        headers=headers,
        data="scope=readiness",
    )
    assert response.status_code == 415
    assert response.json["error"]["code"] == "platform_json_required"

    contract = client.get("/api/admin/platform/v1/openapi.json", headers=headers)
    assert contract.status_code == 200
    assert contract.json["openapi"] == "3.1.0"
    assert contract.json["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"

    removed = client.post(
        "/api/admin/platform/v1/canaries",
        headers={**headers, "Content-Type": "application/json"},
        json={"scope": "completion", "modelId": "sovereign-fast", "confirmed": True},
    )
    assert removed.status_code == 410
    assert removed.json["error"]["code"] == "platform_legacy_completion_canary_removed"
    assert removed.json["error"]["blocker"] == "legacy_litellm_replaced_by_direct_routes"

    assert set(contract.json["paths"]) == {
        "/identity",
        "/overview",
        "/statistics",
        "/integrations",
        "/evidence",
        "/canaries",
        "/openapi.json",
    }
