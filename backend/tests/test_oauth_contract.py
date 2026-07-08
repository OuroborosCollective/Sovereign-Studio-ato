"""
OAuth Contract Tests - App Integration

Diese Tests importieren das echte app.py Modul mit einem isolierten psycopg2-Testdouble
und prüfen die OAuth Live-Path-Verträge ohne echte Datenbank.
"""

from __future__ import annotations

import os
import sys
import types

import pytest

# Füge Backend zum Python Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Mock psycopg2 vor app.py Import ───────────────────────────────────────────

class MockCursor:
    """Minimaler Cursor für Import-/Contract-Tests."""

    def __init__(self):
        self.sql = None
        self.params = None
        self._results = []

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = params
        self._results = []

    def fetchone(self):
        return self._results[0] if self._results else None

    def fetchall(self):
        return self._results

    def __iter__(self):
        return iter(self._results)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class MockConnection:
    """Minimaler DB-Connection-Dummy für Import-/Contract-Tests."""

    def cursor(self, *args, **kwargs):
        return MockCursor()

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class MockPool:
    """Minimaler Connection-Pool-Dummy."""

    def getconn(self):
        return MockConnection()

    def putconn(self, conn):
        pass

    def closeall(self):
        pass


class MockRealDictCursor:
    pass


class MockJson:
    def __init__(self, value):
        self.value = value


psycopg2_module = types.ModuleType("psycopg2")
psycopg2_extras_module = types.ModuleType("psycopg2.extras")
psycopg2_pool_module = types.ModuleType("psycopg2.pool")

psycopg2_pool_module.ThreadedConnectionPool = lambda *args, **kwargs: MockPool()
psycopg2_extras_module.RealDictCursor = MockRealDictCursor
psycopg2_extras_module.Json = MockJson
psycopg2_module.connect = lambda *args, **kwargs: MockConnection()
psycopg2_module.extras = psycopg2_extras_module
psycopg2_module.pool = psycopg2_pool_module

sys.modules["psycopg2"] = psycopg2_module
sys.modules["psycopg2.extras"] = psycopg2_extras_module
sys.modules["psycopg2.pool"] = psycopg2_pool_module


# ── Environment für app.py Import ─────────────────────────────────────────────

os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-testing")
os.environ.setdefault("GITHUB_CLIENT_ID", "test_client_id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test_client_secret")
os.environ.setdefault("GITHUB_TOKEN_ENCRYPTION_KEY", "test-token-encryption-key")


try:
    import app
    import security_oauth

    HAS_APP_IMPORT = True
except ImportError as exc:  # pragma: no cover - only for missing test deps
    app = None  # type: ignore[assignment]
    security_oauth = None  # type: ignore[assignment]
    HAS_APP_IMPORT = False
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


def require_app_import():
    assert HAS_APP_IMPORT, f"app.py import failed: {IMPORT_ERROR}"
    assert app is not None
    return app


class TestOAuthContractWithApp:
    """Verifiziert dass OAuth Contract in app.py korrekt implementiert ist."""

    def test_user_row_to_dict_excludes_token(self):
        """CRITICAL CONTRACT: _user_row_to_dict darf KEIN Token zurückgeben."""
        app_module = require_app_import()
        mock_row = {
            "id": "test-uuid",
            "email": "test@example.com",
            "display_name": "Test User",
            "role": "user",
            "credits": 500,
            "subscription_status": "free",
            "is_banned": False,
            "created_at": "2024-01-01",
            "avatar_url": None,
            "google_id": None,
            "github_id": "12345",
            "github_username": "testuser",
            "github_access_token": "gho_SENSITIVE_TOKEN_VALUE",
        }

        result = app_module._user_row_to_dict(mock_row)

        assert "github_access_token" not in result
        assert "githubAccessToken" not in result
        assert "token" not in result

    def test_user_row_to_dict_includes_safe_github_fields(self):
        """GitHub Username und ID dürfen im Response sein, keine Secrets."""
        app_module = require_app_import()
        mock_row = {
            "id": "test-uuid",
            "email": "test@example.com",
            "display_name": "Test User",
            "role": "user",
            "credits": 500,
            "subscription_status": "free",
            "is_banned": False,
            "created_at": "2024-01-01",
            "avatar_url": None,
            "google_id": None,
            "github_id": "12345",
            "github_username": "testuser",
            "github_access_token": "encrypted_token_value",
        }

        result = app_module._user_row_to_dict(mock_row)

        assert result.get("githubId") == "12345"
        assert result.get("githubUsername") == "testuser"

    def test_auth_github_init_limits_scopes_and_uses_central_pkce(self, monkeypatch):
        """Client-Input darf OAuth nicht auf repo/write-Scope erweitern."""
        app_module = require_app_import()
        captured_state = {}

        def fake_store(state, data):
            captured_state["state"] = state
            captured_state["data"] = data

        monkeypatch.setattr(app_module, "_store_oauth_state", fake_store)
        monkeypatch.setattr(app_module, "_generate_state", lambda: "state_test")
        monkeypatch.setattr(app_module, "_generate_pkce", lambda: ("verifier_test", "challenge_test"))

        client = app_module.app.test_client()
        response = client.post(
            "/api/auth/github/init",
            json={
                "redirect_uri": "https://example.test/callback",
                "scopes": "repo delete_repo admin:org read:user user:email",
            },
        )

        assert response.status_code == 200
        payload = response.get_json()
        assert "scope=read%3Auser+user%3Aemail" in payload["authUrl"]
        assert "repo" not in payload["authUrl"]
        assert captured_state["state"] == "state_test"
        assert captured_state["data"] == {
            "code_challenge": "challenge_test",
            "redirect_uri": "https://example.test/callback",
        }
        assert "code_verifier" not in captured_state["data"]
        assert payload["codeVerifier"] == "verifier_test"

    def test_auth_github_rejects_missing_pkce_verifier_when_challenge_exists(self, monkeypatch):
        """Wenn PKCE angefordert wurde, darf fehlender verifier nicht akzeptiert werden."""
        app_module = require_app_import()
        monkeypatch.setattr(app_module, "_get_oauth_state", lambda state: {"code_challenge": "challenge"})

        client = app_module.app.test_client()
        response = client.post(
            "/api/auth/github",
            json={"code": "oauth_code", "state": "stored_state"},
        )

        assert response.status_code == 400
        assert "PKCE" in response.get_json()["error"]

    def test_auth_github_token_exchange_uses_verifier_and_redirect_uri(self, monkeypatch):
        """Callback muss echte App-Logik nutzen und Token verschlüsselt speichern."""
        app_module = require_app_import()
        calls = []

        class FakeResponse:
            def __init__(self, ok, payload):
                self.ok = ok
                self._payload = payload

            def json(self):
                return self._payload

        def fake_post(url, json, headers, timeout):
            calls.append(("post", url, json, headers, timeout))
            return FakeResponse(True, {"access_token": "gho_live_token"})

        def fake_get(url, headers, timeout):
            calls.append(("get", url, headers, timeout))
            return FakeResponse(True, {
                "id": 12345,
                "login": "octo-user",
                "email": "octo@example.test",
                "name": "Octo User",
                "avatar_url": "https://example.test/avatar.png",
            })

        stored_rows = []

        def fake_query(sql, params=(), one=False, write=False):
            normalized_sql = " ".join(sql.upper().split())

            if normalized_sql.startswith("SELECT * FROM ADMIN_USERS WHERE GITHUB_ID"):
                return None

            if write:
                stored_rows.append((sql, params))
                return None

            if normalized_sql.startswith("SELECT * FROM ADMIN_USERS WHERE ID"):
                return {
                    "id": params[0],
                    "email": "octo@example.test",
                    "display_name": "Octo User",
                    "role": "user",
                    "credits": 500,
                    "subscription_status": "free",
                    "is_banned": False,
                    "created_at": "now",
                    "avatar_url": "https://example.test/avatar.png",
                    "google_id": None,
                    "github_id": "12345",
                    "github_username": "octo-user",
                    "github_access_token": "encrypted-gho_live_token",
                }
            return None

        monkeypatch.setattr(app_module, "_get_oauth_state", lambda state: {
            "code_challenge": "challenge_test",
            "redirect_uri": "https://example.test/callback",
        })
        monkeypatch.setattr(app_module, "_validate_pkce", lambda verifier, challenge: True)
        monkeypatch.setattr(app_module, "_encrypt_token", lambda token: f"encrypted-{token}")
        monkeypatch.setattr(app_module.requests, "post", fake_post)
        monkeypatch.setattr(app_module.requests, "get", fake_get)
        monkeypatch.setattr(app_module, "query", fake_query)

        client = app_module.app.test_client()
        response = client.post(
            "/api/auth/github",
            json={
                "code": "oauth_code",
                "state": "stored_state",
                "code_verifier": "verifier_test",
            },
        )

        assert response.status_code == 200
        token_payload = calls[0][2]
        assert token_payload["code_verifier"] == "verifier_test"
        assert token_payload["redirect_uri"] == "https://example.test/callback"
        assert stored_rows, "OAuth flow must write encrypted token to DB"
        inserted_params = stored_rows[0][1]
        assert any(value == "encrypted-gho_live_token" for value in inserted_params)
        assert all(value != "gho_live_token" for value in inserted_params)
        assert "github_access_token" not in response.get_json()
        assert "githubAccessToken" not in response.get_json()


class TestOAuthContractCodeAnalysis:
    """Analysiert den app.py Code auf Contract-Einhaltung."""

    def test_app_import_is_hard_requirement(self):
        assert HAS_APP_IMPORT, f"app.py import failed: {IMPORT_ERROR}"

    def test_user_row_to_dict_function_exists(self):
        app_module = require_app_import()
        assert callable(app_module._user_row_to_dict)

    def test_auth_github_endpoint_exists(self):
        app_module = require_app_import()
        assert callable(app_module.auth_github)

    def test_auth_github_init_endpoint_exists(self):
        app_module = require_app_import()
        assert callable(app_module.auth_github_init)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
