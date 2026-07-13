from __future__ import annotations

from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP = BACKEND_ROOT / "app.py"


def test_native_android_origins_are_part_of_the_backend_cors_contract() -> None:
    source = APP.read_text("utf-8")

    assert '"https://localhost"' in source
    assert '"capacitor://localhost"' in source
    assert "_REQUIRED_NATIVE_CORS_ORIGINS" in source
    assert "_DEFAULT_CORS_ORIGINS" in source
    assert "CORS(app, origins=list(_DEFAULT_CORS_ORIGINS), supports_credentials=True)" in source


def test_runtime_cors_updates_cannot_remove_native_android_origins() -> None:
    source = APP.read_text("utf-8")

    assert "def _effective_cors_origins(" in source
    assert "*_REQUIRED_NATIVE_CORS_ORIGINS" in source
    assert 'origins = _effective_cors_origins(_RUNTIME_CONFIG.get("cors_origins", []))' in source
    assert 'updates["cors_origins"] = _effective_cors_origins(origins)' in source
    assert 'origin.strip() == "*"' in source


def test_auth_routes_remain_cookie_based_without_client_token_storage() -> None:
    source = APP.read_text("utf-8")

    assert '@app.route("/api/auth/register", methods=["POST"])' in source
    assert '@app.route("/api/auth/google", methods=["POST"])' in source
    assert "httponly=True, secure=True, samesite=\"None\"" in source
    assert "localStorage" not in source[source.index("def _set_session_cookie"):source.index("def _get_session_user_id")]
