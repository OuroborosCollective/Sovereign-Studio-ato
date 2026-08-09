from __future__ import annotations

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
APP_SOURCE = BACKEND / "app.py"
GITHUB_APP_SOURCE = BACKEND / "github_app.py"


def test_github_oauth_sources_are_syntax_valid() -> None:
    ast.parse(APP_SOURCE.read_text(encoding="utf-8"))
    ast.parse(GITHUB_APP_SOURCE.read_text(encoding="utf-8"))


def test_github_app_identity_is_verified_against_authenticated_app_endpoint() -> None:
    source = GITHUB_APP_SOURCE.read_text(encoding="utf-8")
    start = source.index("def github_app_identity_evidence()")
    end = source.index("def list_installations()", start)
    helper = source[start:end]

    assert '"https://api.github.com/app"' in helper
    assert '"Authorization": f"Bearer {jwt_token}"' in helper
    assert 'actual_client_id = str(payload.get("client_id")' in helper
    assert 'hmac.compare_digest(GITHUB_APP_CLIENT_ID, actual_client_id)' in helper
    assert '"actualClientIdFingerprint"' in helper
    assert '"rawCredentialReturned": False' in helper
    assert '"client_secret"' not in helper


def test_login_oauth_prefers_complete_github_app_pair_without_cross_mixing() -> None:
    source = APP_SOURCE.read_text(encoding="utf-8")
    start = source.index("def _github_oauth_credential_contract()")
    end = source.index("_DEFAULT_GITHUB_OAUTH_OPENER_ORIGINS", start)
    helper = source[start:end]

    app_branch = helper.index('if app_pair_complete:')
    legacy_branch = helper.index('elif legacy_pair_complete:')
    assert app_branch < legacy_branch
    assert 'client_id = GITHUB_APP_CLIENT_ID' in helper
    assert 'secret = GITHUB_APP_CLIENT_SECRET' in helper
    assert 'client_id = GITHUB_CLIENT_ID' in helper
    assert 'secret = GITHUB_CLIENT_SECRET' in helper
    assert 'github_oauth_credential_pair_incomplete' in helper
    assert 'github_app_identity_evidence()' in helper


def test_init_and_exchange_share_the_same_resolved_oauth_identity() -> None:
    source = APP_SOURCE.read_text(encoding="utf-8")
    assert source.count('oauth_contract = _github_oauth_credential_contract()') >= 2
    assert '"client_id":     oauth_contract["client_id"]' in source
    assert '"client_secret": oauth_contract["client_secret"]' in source
    assert '"client_id": oauth_contract["client_id"]' in source
    assert '@app.route("/api/auth/github/configured", methods=["GET"])' in source
    assert '"rawCredentialReturned": False' in source


def test_github_app_authorize_uses_registered_callback_instead_of_foreign_redirect_uri() -> None:
    source = APP_SOURCE.read_text(encoding="utf-8")
    start = source.index("def auth_github_init():")
    end = source.index("# ═════════════════════════════════════════════════════════════════════════════\n# SOVEREIGN APP TOOLCHAIN", start)
    route = source[start:end]

    assert 'if oauth_contract["source"] == "github-app"' in route
    assert 'else GITHUB_OAUTH_REDIRECT_URI' in route
    assert 'if redirect_uri:' in route
    assert 'auth_params["redirect_uri"] = redirect_uri' in route
    assert '"redirect_uri": redirect_uri' not in route.split("auth_params = {", 1)[1].split("}", 1)[0]


def test_github_app_backend_callback_forwards_code_and_state_to_fixed_login_callback() -> None:
    source = GITHUB_APP_SOURCE.read_text(encoding="utf-8")
    start = source.index("def github_app_oauth_callback():")
    end = source.index('@app.route("/api/github-app/configured"', start)
    route = source[start:end]

    assert 'state = str(request.args.get("state")' in route
    assert 'github_app_oauth_state_missing' in route
    assert 'GITHUB_APP_LOGIN_FORWARD_URI' in route
    assert 'urllib.parse.urlencode({"code": code, "state": state})' in route
    assert 'response = redirect(target, code=302)' in route
    assert 'response.headers["Cache-Control"] = "no-store"' in route
    assert 'github_app_oauth_exchange_unavailable' not in route
