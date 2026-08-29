from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "src" / "main.tsx"
GOOGLE = ROOT / "src" / "features" / "user" / "googleOAuthLogin.ts"
LOGIN_MODAL = ROOT / "src" / "features" / "user" / "components" / "LoginModal.tsx"
STORE = ROOT / "src" / "features" / "user" / "useUserStore.ts"
GITHUB = ROOT / "src" / "features" / "github" / "githubOAuthLogin.ts"
CAPACITOR = ROOT / "capacitor.config.ts"
BACKEND = ROOT / "scripts" / "sovereign-backend" / "app.py"


def test_android_google_does_not_receive_web_client_id_from_startup_or_native_initialize() -> None:
    main = MAIN.read_text(encoding="utf-8")
    google = GOOGLE.read_text(encoding="utf-8")
    capacitor = CAPACITOR.read_text(encoding="utf-8")

    assert "initGoogleAuth" not in main
    assert "GoogleAuth.initialize" not in main
    assert "if (Capacitor.isNativePlatform())" in google
    native_block = google.split("if (Capacitor.isNativePlatform())", 1)[1].split("} else {", 1)[0]
    assert "clientId:" not in native_block
    assert "grantOfflineAccess: false" in native_block
    assert "androidClientId" in capacitor
    assert "serverClientId" in capacitor
    assert "forceCodeForRefreshToken: false" in capacitor


def test_google_login_uses_backend_audience_preflight_and_bounded_error_mapping() -> None:
    google = GOOGLE.read_text(encoding="utf-8")
    modal = LOGIN_MODAL.read_text(encoding="utf-8")
    backend = BACKEND.read_text(encoding="utf-8")

    assert "/api/auth/google/configured" in google
    assert "clientIdFingerprint" in google
    assert "rawCredentialReturned !== false" in google
    assert "globalThis.fetch.bind(globalThis)" in google
    assert "googleOAuthErrorMessage(reason)" in modal
    assert 'audience=GOOGLE_CLIENT_ID,' in backend
    assert '"verify_aud": True' in backend
    assert '"require": ["exp", "iat", "iss", "sub"]' in backend
    assert "validate_google_identity_claims(payload)" in backend
    assert "Google-Token ungültig: {verify_err}" not in backend


def test_github_authorize_url_and_redirect_are_fail_closed() -> None:
    github = GITHUB.read_text(encoding="utf-8")
    backend = BACKEND.read_text(encoding="utf-8")

    assert "validateGitHubAuthorizeUrl(initialized)" in github
    assert "parsed.pathname !== '/login/oauth/authorize'" in github
    assert "parsed.searchParams.get('client_id')" in github
    assert "validateOAuthState(parsed.searchParams.get('state'), initialized.state)" in github
    assert "globalThis.fetch.bind(globalThis)" in github
    assert "authorizeRedirectUri: string" in github
    assert "redirectUri !== initialized.authorizeRedirectUri" in github
    assert 'redirect_uri = _github_oauth_authorize_redirect_uri(oauth_contract["source"])' in backend
    assert 'auth_params["redirect_uri"] = redirect_uri' in backend
    assert '"authorizeRedirectUri": redirect_uri' in backend
    assert '"https://sovereign-backend.arelorian.de/api/auth/github-app/callback"' in backend


def test_capacitor_session_cookie_and_origin_contract_support_verified_readback() -> None:
    backend = BACKEND.read_text(encoding="utf-8")

    assert '"https://localhost"' in backend
    assert 'httponly=True, secure=True, samesite="None"' in backend
    assert 'delete_cookie(_COOKIE, path="/", samesite="None", secure=True)' in backend


def test_oauth_post_success_is_not_session_truth_and_registration_labels_are_correct() -> None:
    store = STORE.read_text(encoding="utf-8")
    modal = LOGIN_MODAL.read_text(encoding="utf-8")

    assert "async function readVerifiedSessionUser" in store
    assert "await readVerifiedSessionUser()" in store
    assert "globalThis.fetch.bind(globalThis)" in store
    assert "Mit Google registrieren" in modal
    assert "Mit GitHub registrieren" in modal
    assert "setGithubStatus('');" in modal
