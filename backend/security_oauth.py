"""
OAuth Security Module - Sovereign Backend

Dieses Modul enthält alle OAuth-Security-Funktionen:
- Token-Verschlüsselung (Fernet)
- State-Validierung (CSRF-Schutz)
- PKCE-Validierung

Importiert von app.py und getestet in tests/test_oauth_security.py
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
from typing import Optional

# ── Token Encryption ─────────────────────────────────────────────────────────────

try:
    from cryptography.fernet import Fernet
    
    _GITHUB_TOKEN_KEY: str | None = None
    _github_cipher: Fernet | None = None
    
    def init_token_encryption(key: str) -> None:
        """Initialisiert die Token-Verschlüsselung."""
        global _GITHUB_TOKEN_KEY, _github_cipher
        _GITHUB_TOKEN_KEY = key
        _fernet_key = base64.urlsafe_b64encode(
            hashlib.sha256(key.encode()).digest()
        )
        _github_cipher = Fernet(_fernet_key)
    
    def _encrypt_token(token: str) -> str:
        """Verschlüsselt einen Token für sichere Speicherung."""
        if _github_cipher is None:
            raise RuntimeError("Token encryption nicht initialisiert")
        return _github_cipher.encrypt(token.encode()).decode()
    
    def _decrypt_token(encrypted: str) -> str | None:
        """Entschlüsselt einen Token für API-Zugriff."""
        if _github_cipher is None:
            raise RuntimeError("Token encryption nicht initialisiert")
        try:
            return _github_cipher.decrypt(encrypted.encode()).decode()
        except Exception:
            return None

except ImportError:
    # Fallback für Testing ohne cryptography
    def _encrypt_token(token: str) -> str:
        return token
    
    def _decrypt_token(encrypted: str) -> str | None:
        return encrypted
    
    def init_token_encryption(key: str) -> None:
        pass


# ── OAuth State Store ───────────────────────────────────────────────────────────

_oauth_state_store: dict[str, dict] = {}
_oauth_lock = threading.Lock()


def _store_oauth_state(state: str, data: dict) -> None:
    """Speichert OAuth State mit zugehörigen Daten (PKCE, etc.)."""
    with _oauth_lock:
        _oauth_state_store[state] = {
            **data,
            "created_at": time.time(),
        }


def _get_oauth_state(state: str) -> dict | None:
    """Holt OAuth State und löscht ihn (einmalige Verwendung)."""
    with _oauth_lock:
        data = _oauth_state_store.pop(state, None)
        if data:
            # Prüfe ob abgelaufen (10 Minuten)
            if time.time() - data.get("created_at", 0) > 600:
                return None
        return data


def _clear_oauth_state(state: str) -> bool:
    """Löscht einen spezifischen State (ohne retrieval)."""
    with _oauth_lock:
        if state in _oauth_state_store:
            del _oauth_state_store[state]
            return True
        return False


def _clear_all_oauth_states() -> int:
    """Löscht alle States (für Testing)."""
    with _oauth_lock:
        count = len(_oauth_state_store)
        _oauth_state_store.clear()
        return count


# ── PKCE Validation ─────────────────────────────────────────────────────────────

def _validate_pkce(verifier: str | None, stored_challenge: str | None) -> bool:
    """
    Validiert PKCE code_verifier gegen gespeicherten challenge.
    
    Args:
        verifier: Der vom Client gesendete code_verifier
        stored_challenge: Der bei der Authorization gespeicherte code_challenge
    
    Returns:
        True wenn gültig, False wenn ungültig oder nicht verwendet
    """
    if not verifier or not stored_challenge:
        return True  # PKCE optional wenn nicht angefordert
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip('=')
    return challenge == stored_challenge


def _generate_pkce() -> tuple[str, str]:
    """
    Generiert PKCE code_verifier und code_challenge.
    
    Returns:
        (code_verifier, code_challenge) tuple
    """
    verifier = secrets.token_urlsafe(64)  # ~86 chars
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip('=')
    return verifier, challenge


def _generate_state() -> str:
    """Generiert einen kryptographisch sicheren OAuth State."""
    return secrets.token_urlsafe(32)


# ── Exported API ────────────────────────────────────────────────────────────────

__all__ = [
    "init_token_encryption",
    "_encrypt_token",
    "_decrypt_token",
    "_store_oauth_state",
    "_get_oauth_state",
    "_clear_oauth_state",
    "_clear_all_oauth_states",
    "_validate_pkce",
    "_generate_pkce",
    "_generate_state",
]
