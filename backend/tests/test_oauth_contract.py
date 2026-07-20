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

# Importiere die echte produktive Backend-App aus scripts/sovereign-backend.
# backend/ enthält Verträge und Tests, aber bewusst keine zweite app.py-Wahrheit.
TEST_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPOSITORY_ROOT = os.path.dirname(TEST_BACKEND_ROOT)
PRODUCTION_BACKEND_ROOT = os.path.join(REPOSITORY_ROOT, "scripts", "sovereign-backend")
sys.path.insert(0, TEST_BACKEND_ROOT)
sys.path.insert(0, PRODUCTION_BACKEND_ROOT)


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

os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-testing-at-least-32-bytes")
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

    def test_user_row_to_dict_excludes_token(self, monkeypatch):
        """CRITICAL CONTRACT: _user_row_to_dict darf KEIN Token zurückgeben."""
        app_module = require_app_import()
        monkeypatch.setattr(app_module, "_read_verified_credit_balance", lambda user_id: 500)
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

    def test_user_row_to_dict_includes_safe_github_fields(self, monkeypatch):
        """GitHub Username und ID dürfen im Response sein, keine Secrets."""
        app_module = require_app_import()
        monkeypatch.setattr(app_module, "_read_verified_credit_balance", lambda user_id: 500)
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

    def test_oauth_state_store_hashes_raw_state_and_persists_payload(self, monkeypatch):
        """Mehrprozess-State wird nur gehasht und mit Ablaufzeit in PostgreSQL gespeichert."""
        app_module = require_app_import()
        calls = []

        def fake_query(sql, params=None, one=False, write=False):
            calls.append((sql, params, one, write))
            return None

        monkeypatch.setattr(app_module, "query", fake_query)
        app_module._store_oauth_state("raw-secret-state", {
            "code_challenge": "challenge",
            "opener_origin": "https://chat.arelorian.de",
        })

        assert len(calls) == 2
        insert_sql, insert_params, one, write = calls[1]
        assert "INSERT INTO github_oauth_states" in insert_sql
        assert insert_params[0] == app_module.hashlib.sha256(b"raw-secret-state").hexdigest()
        assert "raw-secret-state" not in repr(insert_params)
        assert insert_params[1].value["opener_origin"] == "https://chat.arelorian.de"
        assert one is False
        assert write is True

    def test_oauth_state_exchange_consumes_state_atomically(self, monkeypatch):
        """Ein State kann workerübergreifend nur einmal per DELETE RETURNING verbraucht werden."""
        app_module = require_app_import()
        calls = []

        def fake_query(sql, params=None, one=False, write=False):
            calls.append((sql, params, one, write))
            return {"payload": {"code_challenge": "challenge"}}

        monkeypatch.setattr(app_module, "query", fake_query)
        payload = app_module._get_oauth_state("one-time-state")

        sql, params, one, write = calls[0]
        assert "DELETE FROM github_oauth_states" in sql
        assert "RETURNING payload" in sql
        assert params[0] == app_module.hashlib.sha256(b"one-time-state").hexdigest()
        assert payload == {"code_challenge": "challenge"}
        assert one is True
        assert write is True

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

        # Monkeypatch the server-side redirect URI
        monkeypatch.setattr(
            app_module,
            "GITHUB_OAUTH_REDIRECT_URI",
            "https://sovereign-backend.arelorian.de/api/auth/github",
        )
        
        client = app_module.app.test_client()
        response = client.post(
            "/api/auth/github/init",
            json={
                "redirect_uri": "https://example.test/callback",  # Client tries to override
                "opener_origin": "https://chat.arelorian.de",
                "scopes": "repo delete_repo admin:org read:user user:email",
            },
        )

        assert response.status_code == 200
        payload = response.get_json()
        assert "scope=read%3Auser+user%3Aemail" in payload["authUrl"]
        assert "repo" not in payload["authUrl"]
        # Server-side redirect_uri must be used, not client redirect
        assert "redirect_uri=https%3A%2F%2Fsovereign-backend.arelorian.de" in payload["authUrl"]
        assert captured_state["state"] == "state_test"
        assert captured_state["data"] == {
            "code_challenge": "challenge_test",
            "redirect_uri": "https://sovereign-backend.arelorian.de/api/auth/github",
            "opener_origin": "https://chat.arelorian.de",
        }
        assert "code_verifier" not in captured_state["data"]
        assert payload["codeVerifier"] == "verifier_test"
        assert payload["openerOrigin"] == "https://chat.arelorian.de"
        assert payload["callbackOrigin"] == "https://sovereign-backend.arelorian.de"

    def test_auth_github_init_rejects_unapproved_opener_origin(self):
        """OAuth darf keinen Rückkanal an beliebige Origins vorbereiten."""
        app_module = require_app_import()
        client = app_module.app.test_client()

        response = client.post(
            "/api/auth/github/init",
            json={
                "redirect_uri": "https://evil.example/callback",
                "opener_origin": "https://evil.example",
            },
        )

        assert response.status_code == 400
        assert response.get_json()["blocker"] == "github_oauth_opener_origin_not_allowed"

    def test_auth_github_callback_context_returns_origin_without_consuming_state(self, monkeypatch):
        """Callback liest nur den Rückkanal; der Token-Exchange verbraucht den State später."""
        app_module = require_app_import()
        calls = []

        def fake_peek(state):
            calls.append(state)
            return {"opener_origin": "https://chat.arelorian.de"}

        monkeypatch.setattr(app_module, "_peek_oauth_state", fake_peek)
        monkeypatch.setattr(
            app_module,
            "GITHUB_OAUTH_REDIRECT_URI",
            "https://chat.arelorian.de/auth/github/callback.html",
        )

        client = app_module.app.test_client()
        response = client.get("/api/auth/github/callback-context?state=state_test")

        assert response.status_code == 200
        assert calls == ["state_test"]
        assert response.get_json() == {
            "openerOrigin": "https://chat.arelorian.de",
            "callbackOrigin": "https://chat.arelorian.de",
        }
        assert response.headers["Cache-Control"] == "no-store"

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

        created_users = []

        def fake_create_user(**kwargs):
            created_users.append(dict(kwargs))

        def fake_query(sql, params=(), one=False, write=False):
            normalized_sql = " ".join(sql.upper().split())

            if normalized_sql.startswith("SELECT * FROM ADMIN_USERS WHERE GITHUB_ID"):
                return None

            if write:
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

        # Server-side redirect URI (same as in _get_oauth_state)
        server_redirect_uri = "https://sovereign-backend.arelorian.de/api/auth/github"
        app_module.GITHUB_OAUTH_REDIRECT_URI = server_redirect_uri
        monkeypatch.setattr(app_module, "_get_oauth_state", lambda state: {
            "code_challenge": "challenge_test",
            "redirect_uri": server_redirect_uri,
        })
        monkeypatch.setattr(app_module, "_validate_pkce", lambda verifier, challenge: True)
        monkeypatch.setattr(app_module, "_encrypt_token", lambda token: f"encrypted-{token}")
        monkeypatch.setattr(app_module, "_read_verified_credit_balance", lambda user_id: 500)
        monkeypatch.setattr(app_module, "_create_user_with_initial_credits", fake_create_user)
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
        assert token_payload["redirect_uri"] == server_redirect_uri
        assert created_users, "OAuth flow must use the atomic user-and-ledger creation path"
        created_user = created_users[0]
        assert created_user["github_access_token"] == "encrypted-gho_live_token"
        assert "gho_live_token" not in created_user.values()
        assert created_user["github_id"] == "12345"
        assert created_user["github_username"] == "octo-user"
        assert created_user["initial_credits"] == 500
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
