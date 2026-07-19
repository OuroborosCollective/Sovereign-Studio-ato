"""
OAuth Security Module - Sovereign Backend

Dieses Modul enthält alle OAuth-Security-Funktionen:
- Token-Verschlüsselung (Fernet)
- State-Validierung (CSRF-Schutz)
- PKCE-Validierung
- Audit-Logging für Security-Events

Importiert von app.py und getestet in tests/test_oauth_security.py
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import threading
import time
from typing import Optional

# ── Audit Logger ───────────────────────────────────────────────────────────────

_audit_log = logging.getLogger("oauth_audit")
_audit_handler = logging.StreamHandler()
_audit_handler.setFormatter(logging.Formatter(
    "%(asctime)s [OAUTH_AUDIT] %(levelname)s: %(message)s"
))
_audit_log.addHandler(_audit_handler)
_audit_log.setLevel(logging.INFO)

# Rate-Limit Tracker (in-memory)
_rate_limit_store: dict[str, list[float]] = {}
_rate_limit_lock = threading.Lock()

# ── Token Encryption ─────────────────────────────────────────────────────────────

try:
    from cryptography.fernet import Fernet
except ImportError as exc:  # pragma: no cover - exercised only in broken deployments
    Fernet = None  # type: ignore[assignment]
    _CRYPTOGRAPHY_IMPORT_ERROR: Exception | None = exc
else:
    _CRYPTOGRAPHY_IMPORT_ERROR = None

_GITHUB_TOKEN_KEY: str | None = None
_github_cipher: Fernet | None = None if Fernet is not None else None


def init_token_encryption(key: str) -> None:
    """Initialisiert die Token-Verschlüsselung.

    Live-Pfad-Regel: Ohne cryptography/Fernet darf der Backend-Code nicht
    still auf Klartext-Speicherung zurückfallen. Ein fehlendes Crypto-Modul ist
    ein Deployment-Fehler und muss fail-closed sichtbar werden.
    """
    if Fernet is None:
        raise RuntimeError(
            "Token encryption unavailable: cryptography/Fernet is required"
        ) from _CRYPTOGRAPHY_IMPORT_ERROR
    if not key or not key.strip():
        raise RuntimeError("Token encryption key is required")

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


def _peek_oauth_state(state: str) -> dict | None:
    """Liest nur den sicheren Callback-Kontext, ohne den OAuth-State zu verbrauchen."""
    with _oauth_lock:
        data = _oauth_state_store.get(state)
        if not data:
            return None
        if time.time() - data.get("created_at", 0) > 600:
            _oauth_state_store.pop(state, None)
            return None
        return dict(data)


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

    PKCE bleibt nur optional, wenn serverseitig kein code_challenge
    gespeichert wurde. Sobald ein challenge existiert, muss ein verifier
    vorhanden sein und exakt dazu passen.

    Args:
        verifier: Der vom Client gesendete code_verifier
        stored_challenge: Der bei der Authorization gespeicherte code_challenge

    Returns:
        True wenn gültig oder nicht angefordert, sonst False
    """
    if not stored_challenge:
        return True  # PKCE wurde serverseitig nicht angefordert
    if not verifier:
        return False
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip('=')
    return secrets.compare_digest(challenge, stored_challenge)


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




# ── Rate Limiting ─────────────────────────────────────────────────────────────

RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 10  # max requests per window


def _check_rate_limit(identifier: str, max_requests: int = RATE_LIMIT_MAX_REQUESTS) -> tuple[bool, int]:
    """
    Prüft Rate-Limit für einen Identifier (IP, User-ID, etc.).
    
    Returns:
        (is_allowed, remaining_requests)
    """
    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW
    
    global _rate_limit_store
    with _rate_limit_lock:
        # Prevent memory exhaustion (DoS): sweep the entire store if it grows too large
        if len(_rate_limit_store) > 1000:
            expired_keys = []
            for k, ts in _rate_limit_store.items():
                active = [t for t in ts if t > cutoff]
                if not active:
                    expired_keys.append(k)
                else:
                    _rate_limit_store[k] = active
            for k in expired_keys:
                _rate_limit_store.pop(k, None)

        # Clean old entries for this identifier
        if identifier in _rate_limit_store:
            _rate_limit_store[identifier] = [
                t for t in _rate_limit_store[identifier] if t > cutoff
            ]
            if not _rate_limit_store[identifier]:
                del _rate_limit_store[identifier]
        
        # Check limit
        current_count = len(_rate_limit_store.get(identifier, []))
        if current_count >= max_requests:
            return False, 0
        
        # Add current request
        if identifier not in _rate_limit_store:
            _rate_limit_store[identifier] = []
        _rate_limit_store[identifier].append(now)
        return True, max_requests - current_count - 1


# ── Audit Logging Helper ─────────────────────────────────────────────────────

def _audit_event(event_type: str, success: bool, details: str, ip: str = "unknown") -> None:
    """
    Loggt einen OAuth Security Event.
    
    Args:
        event_type: Type of event (LOGIN_SUCCESS, LOGIN_FAILED, TOKEN_ENCRYPT, etc.)
        success: Whether the operation succeeded
        details: Additional details
        ip: Client IP address
    """
    status = "SUCCESS" if success else "FAILURE"
    _audit_log.info(
        "event=%s status=%s ip=%s details=%s",
        event_type, status, ip, details
    )


# ── Exported API ────────────────────────────────────────────────────────────────

__all__ = [
    "init_token_encryption",
    "_encrypt_token",
    "_decrypt_token",
    "_store_oauth_state",
    "_get_oauth_state",
    "_peek_oauth_state",
    "_clear_oauth_state",
    "_clear_all_oauth_states",
    "_validate_pkce",
    "_generate_pkce",
    "_generate_state",
    "_check_rate_limit",
    "_audit_event",
    "_rate_limit_store",
]
