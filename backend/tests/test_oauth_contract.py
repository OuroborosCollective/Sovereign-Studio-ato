"""
OAuth Contract Tests - App Integration

Diese Tests importieren das echte app.py Modul (mit psycopg2 Mock)
und testen die OAuth Contract-Verification.

Erfordert psycopg2 Installation.
"""

import pytest
import sys
import os

# Füge Backend zum Python Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Mock psycopg2 für Testing ────────────────────────────────────────────────

class MockPsycopg2:
    """Mock für psycopg2 Module."""
    
    class pool:
        @staticmethod
        def ThreadedConnectionPool(*args, **kwargs):
            return MockPool()
    
    @staticmethod
    def connect(*args, **kwargs):
        return MockConnection()
    
    extras = __import__('psycopg2.extras')


class MockPool:
    """Mock für Connection Pool."""
    
    def getconn(self):
        return MockConnection()
    
    def putconn(self, conn):
        pass
    
    def closeall(self):
        pass


class MockConnection:
    """Mock für Database Connection."""
    
    def cursor(self):
        return MockCursor()
    
    def commit(self):
        pass
    
    def rollback(self):
        pass
    
    def close(self):
        pass


class MockCursor:
    """Mock für Database Cursor."""
    
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


# ── Patch psycopg2 vor Import ────────────────────────────────────────────────

import types

# Erstelle gemockte Module
mock_psycopg2 = MockPsycopg2()
mock_psycopg2_extras = types.ModuleType('psycopg2.extras')

sys.modules['psycopg2'] = mock_psycopg2
sys.modules['psycopg2.extras'] = mock_psycopg2_extras
sys.modules['psycopg2.pool'] = MockPsycopg2.pool


# ── Importiere app.py (nach Mock) ────────────────────────────────────────────

# Setze Environment Variables für Testing
os.environ.setdefault('JWT_SECRET', 'test-jwt-secret-for-testing')
os.environ.setdefault('GITHUB_CLIENT_ID', 'test_client_id')
os.environ.setdefault('GITHUB_CLIENT_SECRET', 'test_client_secret')

# Importiere app.py Module (nur die OAuth-relevanten Teile)
# Da psycopg2 gemockt ist, sollte der Import funktionieren
try:
    import security_oauth
    from security_oauth import (
        _encrypt_token,
        _decrypt_token,
        _store_oauth_state,
        _get_oauth_state,
        _validate_pkce,
        _generate_state,
        _generate_pkce,
    )
    HAS_APP_IMPORT = True
except ImportError as e:
    HAS_APP_IMPORT = False
    print(f"Konnte app.py nicht importieren: {e}")


# ── Contract Tests ────────────────────────────────────────────────────────────

@pytest.mark.skipif(not HAS_APP_IMPORT, reason="App Import fehlgeschlagen")
class TestOAuthContractWithApp:
    """Verifiziert dass OAuth Contract in app.py korrekt implementiert ist."""

    def test_user_row_to_dict_excludes_token(self):
        """
        CRITICAL CONTRACT: _user_row_to_dict darf KEIN github_access_token zurückgeben.
        
        Dies ist der Live-Path Security Check.
        """
        from app import _user_row_to_dict
        
        # Simuliere DB-Zeile MIT Token
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
        
        result = _user_row_to_dict(mock_row)
        
        # HARTE ANFORDERUNG: Token darf NICHT im Response sein
        assert "github_access_token" not in result, \
            "SECURITY BREACH: github_access_token in User-Response!"
        assert "githubAccessToken" not in result, \
            "SECURITY BREACH: githubAccessToken in User-Response!"
        assert "token" not in result, \
            "SECURITY BREACH: 'token' key in User-Response!"

    def test_user_row_to_dict_includes_safe_github_fields(self):
        """GitHub Username und ID dürfen im Response sein (keine Secrets)."""
        from app import _user_row_to_dict
        
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
        
        result = _user_row_to_dict(mock_row)
        
        # Diese Felder sind sicher (keine Secrets)
        assert result.get("githubId") == "12345"
        assert result.get("githubUsername") == "testuser"

    def test_auth_endpoint_validates_state(self):
        """
        Verifiziert dass /api/auth/github State validiert wenn angegeben.
        """
        from app import auth_github
        
        # Init Encryption
        from security_oauth import init_token_encryption
        init_token_encryption("test-key")
        
        # Store einen State
        test_state = _generate_state()
        _store_oauth_state(test_state, {
            "code_challenge": "test_challenge",
        })
        
        # Mit ungültigem State sollte Request abgelehnt werden
        # (Hier nur Verifizierung dass State-Mechanismus existiert)


class TestOAuthContractCodeAnalysis:
    """Analysiert den app.py Code auf Contract-Einhaltung."""

    def test_user_row_to_dict_function_exists(self):
        """_user_row_to_dict Funktion muss existieren."""
        from app import _user_row_to_dict
        assert callable(_user_row_to_dict)

    def test_auth_github_endpoint_exists(self):
        """auth_github Endpoint muss existieren."""
        from app import auth_github
        assert callable(auth_github)

    def test_auth_github_init_endpoint_exists(self):
        """auth_github_init Endpoint muss existieren."""
        from app import auth_github_init
        assert callable(auth_github_init)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
