"""
Toolchain Security Tests

Verifies SSRF protection in `/api/toolchain/apply-patch-worker`.
"""

from __future__ import annotations

import os
import sys
import types
import urllib.parse

import pytest

# Add backend to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Mock psycopg2 before app.py import ───────────────────────────────────────

class MockCursor:
    def __init__(self):
        self.sql = None
        self.params = None
        self._results = []

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = params

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

class MockConnection:
    def cursor(self, *args, **kwargs):
        return MockCursor()

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass

class MockPool:
    def getconn(self):
        return MockConnection()

    def putconn(self, conn):
        pass

    def closeall(self):
        pass

psycopg2_module = types.ModuleType("psycopg2")
psycopg2_extras_module = types.ModuleType("psycopg2.extras")
psycopg2_pool_module = types.ModuleType("psycopg2.pool")

psycopg2_pool_module.ThreadedConnectionPool = lambda *args, **kwargs: MockPool()
psycopg2_module.connect = lambda *args, **kwargs: MockConnection()
psycopg2_module.extras = psycopg2_extras_module
psycopg2_module.pool = psycopg2_pool_module

sys.modules["psycopg2"] = psycopg2_module
sys.modules["psycopg2.extras"] = psycopg2_extras_module
sys.modules["psycopg2.pool"] = psycopg2_pool_module

# ── Environment for app.py import ─────────────────────────────────────────────

os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-testing-at-least-32-bytes")
os.environ.setdefault("GITHUB_CLIENT_ID", "test_client_id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test_client_secret")
os.environ.setdefault("GITHUB_TOKEN_ENCRYPTION_KEY", "test-token-encryption-key")

import app


class FakeResponse:
    def __init__(self, ok, status_code=200, content=b"{}"):
        self.ok = ok
        self.status_code = status_code
        self.content = content

    def json(self):
        return {}

    def raise_for_status(self):
        if not self.ok:
            raise Exception("HTTP Error")


@pytest.fixture
def mock_app_deps(monkeypatch):
    """Mocks user session, query, allowlist checks, and external requests."""
    monkeypatch.setattr(app, "_get_session_user_id", lambda: "00000000-0000-0000-0000-000000000001")

    # Mock admin user query to bypass credit and role checks
    def fake_query(sql, params=None, one=False, write=False):
        normalized_sql = " ".join(sql.upper().split())
        if "SELECT CREDITS, ROLE FROM ADMIN_USERS" in normalized_sql:
            return {"credits": 500, "role": "admin"}
        if "SELECT ROLE FROM ADMIN_USERS" in normalized_sql:
            return {"role": "admin"}
        return None

    monkeypatch.setattr(app, "query", fake_query)

    # Mock allowlist check
    monkeypatch.setattr(app, "_tc_allowed", lambda owner, repo: None)


class TestToolchainSsrfProtection:
    """Verifies that SSRF is prevented in apply-patch-worker."""

    def test_apply_patch_worker_valid_url(self, mock_app_deps, monkeypatch):
        """Should allow valid worker url matching _TC_WORKER_URL."""
        calls = []

        def fake_post(url, json=None, timeout=None):
            calls.append(url)
            return FakeResponse(True, 200)

        monkeypatch.setattr(app.requests, "post", fake_post)

        client = app.app.test_client()
        response = client.post(
            "/api/toolchain/apply-patch-worker",
            json={
                "owner": "OuroborosCollective",
                "repo": "Sovereign-Studio-ato",
                "path": "README.md",
                "message": "Update doc",
                "blocks": [{"search": "a", "replace": "b"}],
                "confirm": True,
                "worker_url": app._TC_WORKER_URL,
            },
        )

        assert response.status_code == 200
        assert len(calls) == 1
        assert calls[0] == app._TC_WORKER_URL

    def test_apply_patch_worker_default_url(self, mock_app_deps, monkeypatch):
        """Should use and allow default _TC_WORKER_URL when not specified."""
        calls = []

        def fake_post(url, json=None, timeout=None):
            calls.append(url)
            return FakeResponse(True, 200)

        monkeypatch.setattr(app.requests, "post", fake_post)

        client = app.app.test_client()
        response = client.post(
            "/api/toolchain/apply-patch-worker",
            json={
                "owner": "OuroborosCollective",
                "repo": "Sovereign-Studio-ato",
                "path": "README.md",
                "message": "Update doc",
                "blocks": [{"search": "a", "replace": "b"}],
                "confirm": True,
            },
        )

        assert response.status_code == 200
        assert len(calls) == 1
        assert calls[0] == app._TC_WORKER_URL

    def test_apply_patch_worker_invalid_scheme(self, mock_app_deps):
        """Should reject non-HTTPS worker URLs."""
        client = app.app.test_client()

        # Determine a non-HTTPS variant of our worker URL
        default_parsed = urllib.parse.urlparse(app._TC_WORKER_URL)
        bad_worker = f"http://{default_parsed.netloc}/git/patch"

        response = client.post(
            "/api/toolchain/apply-patch-worker",
            json={
                "owner": "OuroborosCollective",
                "repo": "Sovereign-Studio-ato",
                "path": "README.md",
                "message": "Update doc",
                "blocks": [{"search": "a", "replace": "b"}],
                "confirm": True,
                "worker_url": bad_worker,
            },
        )

        assert response.status_code == 400
        assert "must use HTTPS" in response.get_json()["error"]

    def test_apply_patch_worker_invalid_host(self, mock_app_deps):
        """Should reject worker URLs targeting other domains (SSRF protection)."""
        client = app.app.test_client()

        bad_worker = "https://malicious-domain.com/git/patch"

        response = client.post(
            "/api/toolchain/apply-patch-worker",
            json={
                "owner": "OuroborosCollective",
                "repo": "Sovereign-Studio-ato",
                "path": "README.md",
                "message": "Update doc",
                "blocks": [{"search": "a", "replace": "b"}],
                "confirm": True,
                "worker_url": bad_worker,
            },
        )

        assert response.status_code == 400
        assert "Unauthorized worker host" in response.get_json()["error"]
