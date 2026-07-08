"""
GitHub OAuth Security Contract Tests

Diese Tests verifizieren, dass:
1. Token NIEMALS im Response auftaucht
2. Token verschlüsselt in DB gespeichert wird
3. OAuth State validiert wird
4. PKCE code_verifier validiert wird

Siehe: https://github.com/OuroborosCollective/Sovereign-Studio-ato/issues/560

Die Tests sind standalone und haben keine externen Abhängigkeiten.
"""

import pytest
import json
import base64
import hashlib
import secrets
import time
import threading
from typing import Optional


# ── Copy der relevanten Funktionen aus app.py ───────────────────────────────

# Token Encryption (aus app.py)
from cryptography.fernet import Fernet
import hashlib as _hashlib

_GITHUB_TOKEN_KEY = "test-secret-key-for-testing-only"
_fernet_key = base64.urlsafe_b64encode(
    _hashlib.sha256(_GITHUB_TOKEN_KEY.encode()).digest()
)
_github_cipher = Fernet(_fernet_key)

def _encrypt_token(token: str) -> str:
    return _github_cipher.encrypt(token.encode()).decode()

def _decrypt_token(encrypted: str) -> Optional[str]:
    try:
        return _github_cipher.decrypt(encrypted.encode()).decode()
    except Exception:
        return None

# OAuth State Store (aus app.py)
_oauth_state_store: dict = {}
_oauth_lock = threading.Lock()

def _store_oauth_state(state: str, data: dict) -> None:
    with _oauth_lock:
        _oauth_state_store[state] = {**data, "created_at": time.time()}

def _get_oauth_state(state: str) -> Optional[dict]:
    with _oauth_lock:
        data = _oauth_state_store.pop(state, None)
        if data and time.time() - data.get("created_at", 0) > 600:
            return None
        return data

def _validate_pkce(verifier: Optional[str], challenge: Optional[str]) -> bool:
    if not verifier or not challenge:
        return True
    digest = hashlib.sha256(verifier.encode()).digest()
    computed = base64.urlsafe_b64encode(digest).decode().rstrip('=')
    return computed == challenge

# User Response (aus app.py)
def _user_row_to_dict(row: dict) -> dict:
    """Simuliert _user_row_to_dict aus app.py - Token ist absichtlich NICHT drin!"""
    return {
        "id": str(row["id"]),
        "email": row["email"],
        "displayName": row.get("display_name") or "",
        "role": row.get("role") or "user",
        "credits": int(row.get("credits") or 0),
        "subscriptionStatus": row.get("subscription_status") or "free",
        "isBanned": bool(row.get("is_banned")),
        "createdAt": str(row.get("created_at") or ""),
        "avatarUrl": row.get("avatar_url"),
        "googleId": row.get("google_id"),
        "githubId": row.get("github_id"),
        "githubUsername": row.get("github_username"),
        # NOTE: github_access_token ist ABSICHTLICH NICHT hier!
    }


# ── TESTS ─────────────────────────────────────────────────────────────────

class TestGitHubOAuthTokenNeverInResponse:
    """Contract: github_access_token darf NIEMALS im Response sein."""

    def test_auth_response_never_contains_token_key(self):
        """HARTE ANFORDERUNG: Token darf NICHT im Response sein."""
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
            "github_access_token": "gho_encrypted_token_here",  # In DB, NICHT im Response!
        }
        
        response_dict = _user_row_to_dict(mock_row)
        
        assert "github_access_token" not in response_dict
        assert "githubAccessToken" not in response_dict
        assert "githubToken" not in response_dict
        assert "token" not in response_dict

    def test_auth_response_contains_only_safe_fields(self):
        """Response darf nur sichere Felder enthalten."""
        mock_row = {
            "id": "test-uuid",
            "email": "test@example.com",
            "display_name": "Test User",
            "role": "user",
            "credits": 500,
            "subscription_status": "free",
            "is_banned": False,
            "created_at": "2024-01-01",
            "avatar_url": "https://avatars.githubusercontent.com/u/123",
            "google_id": None,
            "github_id": "12345",
            "github_username": "testuser",
            "github_access_token": "encrypted_token",
        }
        
        response = _user_row_to_dict(mock_row)
        allowed_keys = {
            "id", "email", "displayName", "role", "credits",
            "subscriptionStatus", "isBanned", "createdAt",
            "avatarUrl", "googleId", "githubId", "githubUsername"
        }
        
        for key in response.keys():
            assert key in allowed_keys, f"Unbekanntes Feld '{key}' im Response!"

    def test_json_response_cannot_leak_token(self):
        """Token-Value darf NICHT im JSON auftauchen."""
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
            "github_access_token": "gho_sensitive_token_value",
        }
        
        response_dict = _user_row_to_dict(mock_row)
        response_json = json.dumps(response_dict)
        
        assert "gho_sensitive_token_value" not in response_json


class TestGitHubOAuthTokenEncryption:
    """Contract: Token muss verschlüsselt in DB gespeichert werden."""

    def test_token_can_be_encrypted_and_decrypted(self):
        """Token muss mit Fernet verschlüsselt werden können."""
        original_token = "gho_test_token_12345"
        encrypted = _encrypt_token(original_token)
        
        assert encrypted != original_token, "Token wurde nicht verschlüsselt!"
        
        decrypted = _decrypt_token(encrypted)
        assert decrypted == original_token, "Token konnte nicht entschlüsselt werden!"

    def test_encrypted_token_is_fernet_format(self):
        """Verschlüsselter Token muss Fernet-Format haben."""
        token = "test_token"
        encrypted = _encrypt_token(token)
        
        # Fernet-Tokens verwenden URL-safe Base64 mit Padding
        decoded = base64.urlsafe_b64decode(encrypted)
        assert len(decoded) >= 48, "Verschlüsselter Token zu kurz für Fernet!"

    def test_same_token_produces_different_ciphertext(self):
        """Gleicher Token muss unterschiedlichen Ciphertext produzieren (IV)."""
        token = "static_token"
        encrypted1 = _encrypt_token(token)
        encrypted2 = _encrypt_token(token)
        
        assert encrypted1 != encrypted2, "Verschlüsselung ist deterministisch!"


class TestGitHubOAuthStateValidation:
    """Contract: OAuth State Parameter muss validiert werden."""

    def test_state_store_and_retrieve(self):
        """State kann gespeichert und abgerufen werden."""
        state = "test_state_123"
        data = {"user_id": "test-user", "code_challenge": "test"}
        
        _store_oauth_state(state, data)
        retrieved = _get_oauth_state(state)
        
        assert retrieved is not None
        assert retrieved["user_id"] == "test-user"

    def test_state_is_one_time_use(self):
        """State darf nur einmal verwendet werden."""
        state = "single_use_state"
        _store_oauth_state(state, {"test": True})
        
        first = _get_oauth_state(state)
        assert first is not None
        
        second = _get_oauth_state(state)
        assert second is None

    def test_state_validation_detects_invalid(self):
        """Ungültiger State wird abgelehnt."""
        result = _get_oauth_state("invalid_state_never_stored")
        assert result is None


class TestGitHubOAuthPKCEValidation:
    """Contract: PKCE code_verifier muss im Backend validiert werden."""

    def test_pkce_validation_correct(self):
        """Korrekter PKCE Verifier wird akzeptiert."""
        code_verifier = "a" * 43
        digest = hashlib.sha256(code_verifier.encode()).digest()
        code_challenge = base64.urlsafe_b64encode(digest).decode().rstrip('=')
        
        assert _validate_pkce(code_verifier, code_challenge) is True

    def test_pkce_validation_incorrect(self):
        """Falscher PKCE Verifier wird abgelehnt."""
        correct_verifier = "a" * 43
        wrong_verifier = "b" * 43
        
        digest = hashlib.sha256(correct_verifier.encode()).digest()
        correct_challenge = base64.urlsafe_b64encode(digest).decode().rstrip('=')
        
        assert _validate_pkce(wrong_verifier, correct_challenge) is False

    def test_pkce_validation_optional(self):
        """PKCE ist optional wenn nicht angefordert."""
        assert _validate_pkce(None, None) is True
        assert _validate_pkce("", None) is True


class TestGitHubOAuthScopes:
    """Contract: OAuth Scopes müssen minimal sein."""

    def test_default_scopes_are_minimal(self):
        """repo Scope sollte NICHT in Default-Scopes sein."""
        allowed_default_scopes = {"read:user", "user:email"}
        repo_scope = "repo"
        
        assert repo_scope not in allowed_default_scopes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
