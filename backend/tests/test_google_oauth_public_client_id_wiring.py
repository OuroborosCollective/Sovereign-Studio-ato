from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_CONFIG = ROOT / "scripts" / "sovereign-backend" / "google_oauth_public_config.py"
CAPACITOR = ROOT / "capacitor.config.ts"
MAIN = ROOT / "src" / "main.tsx"
GOOGLE_HELPER = ROOT / "src" / "features" / "user" / "googleOAuthLogin.ts"
ANDROID_STRINGS = ROOT / "android" / "app" / "src" / "main" / "res" / "values" / "strings.xml"
BACKEND_APP = ROOT / "scripts" / "sovereign-backend" / "app.py"
GOOGLE_CLIENT_ID_RE = re.compile(r"[A-Za-z0-9_-]+\.apps\.googleusercontent\.com")


def _public_client_ids() -> tuple[str, str]:
    spec = importlib.util.spec_from_file_location("google_oauth_public_config", PUBLIC_CONFIG)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    web = module.PUBLIC_GOOGLE_WEB_CLIENT_ID
    android = module.PUBLIC_GOOGLE_ANDROID_CLIENT_ID
    assert isinstance(web, str)
    assert isinstance(android, str)
    return web, android


def test_web_server_client_id_is_one_public_identifier_across_build_surfaces() -> None:
    expected, _android = _public_client_ids()
    assert GOOGLE_CLIENT_ID_RE.fullmatch(expected)

    capacitor = CAPACITOR.read_text(encoding="utf-8")
    main = MAIN.read_text(encoding="utf-8")
    google_helper = GOOGLE_HELPER.read_text(encoding="utf-8")
    android_strings = ANDROID_STRINGS.read_text(encoding="utf-8")

    assert expected in capacitor
    assert expected in google_helper
    assert "initGoogleAuth" not in main
    assert f'<string name="google_client_id">{expected}</string>' in android_strings
    assert "REPLACE_WITH_YOUR_GOOGLE_CLIENT_ID" not in android_strings


def test_android_oauth_client_is_explicit_and_separate_from_web_server_client() -> None:
    web, android = _public_client_ids()
    capacitor = CAPACITOR.read_text(encoding="utf-8")
    android_strings = ANDROID_STRINGS.read_text(encoding="utf-8")

    assert GOOGLE_CLIENT_ID_RE.fullmatch(android)
    assert android != web
    assert android in capacitor
    assert f'<string name="google_android_client_id">{android}</string>' in android_strings
    assert android_strings.count(android) == 1
    assert "const PUBLIC_GOOGLE_ANDROID_CLIENT_ID" in capacitor
    assert (
        "const googleAndroidClientId = envValue('VITE_GOOGLE_ANDROID_CLIENT_ID') "
        "?? PUBLIC_GOOGLE_ANDROID_CLIENT_ID;"
    ) in capacitor
    assert (
        "const googleAndroidClientId = envValue('VITE_GOOGLE_ANDROID_CLIENT_ID') "
        "?? PUBLIC_GOOGLE_WEB_CLIENT_ID;"
    ) not in capacitor
    assert "androidClientId: googleClientId" not in capacitor
    assert "androidClientId: googleServerClientId" not in capacitor


def test_backend_audience_uses_env_override_or_public_web_client_id() -> None:
    backend = BACKEND_APP.read_text(encoding="utf-8")

    assert "from google_oauth_public_config import PUBLIC_GOOGLE_WEB_CLIENT_ID" in backend
    assert (
        'GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip() '
        "or PUBLIC_GOOGLE_WEB_CLIENT_ID"
    ) in backend
    assert "audience=GOOGLE_CLIENT_ID," in backend
    assert '"verify_aud": True' in backend
    assert '"require": ["exp", "iat", "iss", "sub"]' in backend
    assert "audience=GOOGLE_CLIENT_ID if GOOGLE_CLIENT_ID else None" not in backend
    assert 'options={"verify_aud": bool(GOOGLE_CLIENT_ID)}' not in backend


def test_public_config_contains_no_secret_material() -> None:
    source = PUBLIC_CONFIG.read_text(encoding="utf-8")
    lower = source.lower()

    assert "client_secret" not in lower
    assert "private_key" not in lower
    assert "refresh_token" not in lower
    assert "access_token" not in lower
