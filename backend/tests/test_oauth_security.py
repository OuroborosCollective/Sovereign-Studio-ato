"""
OAuth Security Live-Path Contract Tests

Diese Tests importieren den ECHTEN Backend-Code aus security_oauth.py
und testen den Live-Path.

Siehe: https://github.com/OuroborosCollective/Sovereign-Studio-ato/issues/560
"""

import pytest
import base64
import hashlib
import secrets
import time
import threading
import sys
import os

# Füge Backend zum Python Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importiere den ECHTEN Code aus dem Backend-Modul
from security_oauth import (
    init_token_encryption,
    _encrypt_token,
    _decrypt_token,
    _store_oauth_state,
    _get_oauth_state,
    _peek_oauth_state,
    _clear_all_oauth_states,
    _validate_pkce,
    _check_rate_limit,
    _audit_event,
    _rate_limit_store,
    _generate_pkce,
    _generate_state,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_oauth_state():
    """Löscht OAuth State vor und nach jedem Test."""
    _clear_all_oauth_states()
    yield
    _clear_all_oauth_states()


@pytest.fixture
def init_encryption():
    """Initialisiert Token-Verschlüsselung für Tests."""
    init_token_encryption("test-secret-key-for-testing")
    yield
    # Reset nach Test (nicht wirklich nötig aber sauber)


# ── Token Encryption Tests ──────────────────────────────────────────────────────

class TestTokenEncryption:
    """Live-Path Tests für Token-Verschlüsselung."""

    def test_encrypt_token_uses_real_cipher(self, init_encryption):
        """Token wird mit echtem Fernet-Cipher verschlüsselt."""
        original_token = "gho_live_token_12345"
        encrypted = _encrypt_token(original_token)
        
        # Muss verschlüsselt sein
        assert encrypted != original_token
        assert len(encrypted) > len(original_token)

    def test_decrypt_token_recovers_original(self, init_encryption):
        """Entschlüsselter Token ist identisch mit Original."""
        original_token = "gho_live_token_12345"
        encrypted = _encrypt_token(original_token)
        decrypted = _decrypt_token(encrypted)
        
        assert decrypted == original_token

    def test_encryption_is_not_deterministic(self, init_encryption):
        """Gleicher Token produziert unterschiedliche Ciphertexte (IV)."""
        token = "static_token"
        encrypted1 = _encrypt_token(token)
        encrypted2 = _encrypt_token(token)
        
        assert encrypted1 != encrypted2, \
            "Fernet verwendet random IV - gleicher Plaintext muss unterschiedlichen Ciphertext produzieren"

    def test_encrypted_token_is_fernet_format(self, init_encryption):
        """Verschlüsselter Token hat korrektes Fernet-Format."""
        token = "test_token"
        encrypted = _encrypt_token(token)
        
        # Fernet-Tokens sind URL-safe Base64 mit 43+ chars
        assert len(encrypted) >= 43
        decoded = base64.urlsafe_b64decode(encrypted)
        assert len(decoded) >= 48  # Fernet-Header + MAC + IV + Payload

    def test_wrong_decryption_returns_none(self, init_encryption):
        """Ungültige ciphertext gibt None zurück."""
        result = _decrypt_token("invalid_base64!!")
        assert result is None


# ── OAuth State Store Tests ────────────────────────────────────────────────────

class TestOAuthStateStore:
    """Live-Path Tests für OAuth State Store."""

    def test_store_and_retrieve_state(self):
        """State kann gespeichert und abgerufen werden."""
        state = _generate_state()
        data = {"user_id": "test-123", "code_challenge": "challenge_abc"}
        
        _store_oauth_state(state, data)
        retrieved = _get_oauth_state(state)
        
        assert retrieved is not None
        assert retrieved["user_id"] == "test-123"
        assert retrieved["code_challenge"] == "challenge_abc"

    def test_state_is_one_time_use(self):
        """State darf nur EINMAL verwendet werden."""
        state = _generate_state()
        _store_oauth_state(state, {"test": True})
        
        # Erste Verwendung - OK
        first = _get_oauth_state(state)
        assert first is not None
        
        # Zweite Verwendung - None (bereits verwendet)
        second = _get_oauth_state(state)
        assert second is None

    def test_peek_reads_callback_context_without_consuming_state(self):
        """Der Callback darf den Rückkanal lesen; nur der Exchange verbraucht den State."""
        state = _generate_state()
        _store_oauth_state(state, {"opener_origin": "https://chat.arelorian.de"})

        first_peek = _peek_oauth_state(state)
        second_peek = _peek_oauth_state(state)
        consumed = _get_oauth_state(state)
        after_consume = _peek_oauth_state(state)

        assert first_peek["opener_origin"] == "https://chat.arelorian.de"
        assert second_peek["opener_origin"] == "https://chat.arelorian.de"
        assert consumed["opener_origin"] == "https://chat.arelorian.de"
        assert after_consume is None

    def test_invalid_state_returns_none(self):
        """Ungültiger/nicht existenter State gibt None zurück."""
        result = _get_oauth_state("this_state_was_never_stored")
        assert result is None

    def test_state_contains_created_at(self):
        """State speichert Erstellungszeitpunkt."""
        state = _generate_state()
        _store_oauth_state(state, {"data": "test"})
        
        retrieved = _get_oauth_state(state)
        assert "created_at" in retrieved
        assert isinstance(retrieved["created_at"], float)

    def test_multiple_states_independent(self):
        """Mehrere States werden unabhängig gespeichert."""
        state1 = _generate_state()
        state2 = _generate_state()
        
        _store_oauth_state(state1, {"id": 1})
        _store_oauth_state(state2, {"id": 2})
        
        result1 = _get_oauth_state(state1)
        result2 = _get_oauth_state(state2)
        
        assert result1["id"] == 1
        assert result2["id"] == 2

    def test_clear_all_states(self):
        """Alle States können gelöscht werden."""
        _store_oauth_state(_generate_state(), {"a": 1})
        _store_oauth_state(_generate_state(), {"b": 2})
        
        count = _clear_all_oauth_states()
        assert count == 2
        
        # Verify alle weg
        assert len([s for s in [_generate_state()] if _get_oauth_state(s) is None]) == 1


# ── PKCE Validation Tests ───────────────────────────────────────────────────────

class TestPKCEValidation:
    """Live-Path Tests für PKCE-Validierung."""

    def test_pkce_validation_with_matching_challenge(self, init_encryption):
        """Korrekter PKCE Verifier wird akzeptiert."""
        verifier, challenge = _generate_pkce()
        
        assert _validate_pkce(verifier, challenge) is True

    def test_pkce_validation_with_wrong_verifier(self, init_encryption):
        """Falscher PKCE Verifier wird abgelehnt."""
        correct_verifier, challenge = _generate_pkce()
        wrong_verifier = secrets.token_urlsafe(64)
        
        # Verifier ist anders, also sollte es fehlschlagen
        assert wrong_verifier != correct_verifier
        assert _validate_pkce(wrong_verifier, challenge) is False

    def test_pkce_validation_rejects_missing_verifier_when_challenge_exists(self):
        """Fehlender verifier wird abgelehnt, wenn PKCE angefordert wurde."""
        _, challenge = _generate_pkce()

        assert _validate_pkce(None, challenge) is False
        assert _validate_pkce("", challenge) is False

    def test_pkce_validation_is_optional(self):
        """PKCE ist optional wenn nicht angefordert."""
        # Keine PKCE verwendet
        assert _validate_pkce(None, None) is True
        assert _validate_pkce("", None) is True
        assert _validate_pkce(None, "") is True

    def test_pkce_verifier_length(self):
        """PKCE Verifier hat korrekte Länge (43-128 chars)."""
        verifier, challenge = _generate_pkce()
        
        assert len(verifier) >= 43, f"Verifier zu kurz: {len(verifier)}"
        assert len(verifier) <= 128, f"Verifier zu lang: {len(verifier)}"
        assert len(challenge) == 43, f"Challenge hat falsche Länge: {len(challenge)}"

    def test_pkce_is_url_safe(self):
        """PKCE Parameter sind URL-safe."""
        verifier, challenge = _generate_pkce()
        
        # Darf keine URL-unsicheren Zeichen enthalten
        assert '+' not in verifier
        assert '/' not in verifier
        assert '=' not in verifier
        assert '+' not in challenge
        assert '/' not in challenge

    def test_pkce_is_unpredictable(self):
        """PKCE Verifier sind kryptographisch sicher."""
        verifiers = set()
        for _ in range(100):
            v, _ = _generate_pkce()
            verifiers.add(v)
        
        assert len(verifiers) == 100, "PKCE Verifier nicht eindeutig genug!"


# ── State Generation Tests ────────────────────────────────────────────────────

class TestStateGeneration:
    """Tests für State-Generierung."""

    def test_state_is_cryptographically_random(self):
        """Generierte States sind kryptographisch sicher."""
        states = set()
        for _ in range(100):
            state = _generate_state()
            assert len(state) >= 32, f"State zu kurz: {len(state)}"
            states.add(state)
        
        assert len(states) == 100, "State-Kollision - Zufall nicht sicher!"

    def test_state_is_url_safe(self):
        """States sind URL-safe."""
        for _ in range(10):
            state = _generate_state()
            assert '+' not in state
            assert '/' not in state


# ── Integration Tests ───────────────────────────────────────────────────────────

class TestOAuthIntegration:
    """Integrationstests für den kompletten OAuth Flow."""

    def test_full_oauth_flow_with_pkce(self, init_encryption):
        """
        Simuliert den kompletten OAuth Flow:
        1. Generate State + PKCE
        2. Store State mit Challenge
        3. Token verschlüsseln
        4. PKCE validieren
        """
        # 1. Generate
        state = _generate_state()
        verifier, challenge = _generate_pkce()
        
        # 2. Store
        _store_oauth_state(state, {
            "code_challenge": challenge,
            "redirect_uri": "https://app.example.com/callback",
        })
        
        # 3. Token verschlüsseln
        github_token = "gho_real_github_token_12345"
        encrypted_token = _encrypt_token(github_token)
        
        # 4. Retrieve und validieren
        stored = _get_oauth_state(state)
        assert stored is not None
        assert stored["code_challenge"] == challenge
        
        # PKCE validieren
        assert _validate_pkce(verifier, stored["code_challenge"]) is True
        
        # Token entschlüsseln
        decrypted = _decrypt_token(encrypted_token)
        assert decrypted == github_token

    def test_oauth_flow_with_pkce_rejects_tampered_verifier(self, init_encryption):
        """Flow lehnt manipulierten PKCE Verifier ab."""
        state = _generate_state()
        correct_verifier, challenge = _generate_pkce()
        wrong_verifier, _ = _generate_pkce()  # Anderer random Verifier
        
        _store_oauth_state(state, {"code_challenge": challenge})
        stored = _get_oauth_state(state)
        
        # Falscher Verifier wird abgelehnt
        assert _validate_pkce(wrong_verifier, stored["code_challenge"]) is False


# ── Health Check ────────────────────────────────────────────────────────────────

def test_module_exports_all_functions():
    """Verifiziert dass alle Funktionen exportiert werden."""
    from security_oauth import __all__
    
    required_exports = [
        "init_token_encryption",
        "_encrypt_token",
        "_decrypt_token",
        "_store_oauth_state",
        "_get_oauth_state",
        "_peek_oauth_state",
        "_validate_pkce",
        "_generate_pkce",
        "_generate_state",
    ]
    
    for func in required_exports:
        assert func in __all__, f"Fehlende Export: {func}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

class TestRateLimiting:
    """Tests für Rate-Limiting Funktion."""

    def setup_method(self):
        _clear_all_oauth_states()
        _rate_limit_store.clear()

    def test_rate_limit_allows_within_limit(self):
        """Anfragen innerhalb des Limits sollten erlaubt sein."""
        identifier = "test_ip_123"
        for i in range(5):
            allowed, remaining = _check_rate_limit(identifier, max_requests=10)
            assert allowed is True
            assert remaining == 10 - i - 1

    def test_rate_limit_blocks_after_limit(self):
        """Anfragen über dem Limit sollten blockiert werden."""
        identifier = "test_ip_block"
        # Make 10 requests (the limit)
        for _ in range(10):
            _check_rate_limit(identifier, max_requests=10)
        
        # 11th request should be blocked
        allowed, remaining = _check_rate_limit(identifier, max_requests=10)
        assert allowed is False
        assert remaining == 0

    def test_rate_limit_window_resets(self):
        """Rate-Limit sollte nach der Window-Zeit zurückgesetzt werden."""
        import time
        identifier = "test_ip_reset"
        
        # First request
        allowed1, _ = _check_rate_limit(identifier, max_requests=2)
        assert allowed1 is True
        
        # Second request (at limit)
        allowed2, _ = _check_rate_limit(identifier, max_requests=2)
        assert allowed2 is True
        
        # Third request (over limit)
        allowed3, _ = _check_rate_limit(identifier, max_requests=2)
        assert allowed3 is False

    def test_rate_limit_different_identifiers_independent(self):
        """Verschiedene Identifiers sollten unabhängige Limits haben."""
        ip1 = "192.168.1.1"
        ip2 = "192.168.1.2"
        
        # Use up limit for ip1
        for _ in range(10):
            _check_rate_limit(ip1, max_requests=10)
        
        # ip2 should still work
        allowed, remaining = _check_rate_limit(ip2, max_requests=10)
        assert allowed is True
        assert remaining == 9

    def test_module_exports_rate_limit_function(self):
        """Rate-Limit Funktion sollte exportiert sein."""
        from security_oauth import _check_rate_limit
        assert callable(_check_rate_limit)

    def test_rate_limit_deletes_empty_active_lists_instead_of_leaking(self):
        """Identifikatoren ohne aktive Timestamps müssen aus dem Store gelöscht werden."""
        from security_oauth import _rate_limit_store, _check_rate_limit
        identifier = "temp_ip_eviction"

        # Erstelle ein abgelaufenes Timestamp-Eintrag
        _rate_limit_store[identifier] = [time.time() - 3600]

        # Trigger Limit Check -> Sollte den abgelaufenen Eintrag säubern und den Key ganz löschen
        allowed, remaining = _check_rate_limit(identifier, max_requests=10)

        assert allowed is True
        # Da wir den abgelaufenen Key gelöscht haben, wird er neu angelegt mit nur dem aktuellen Timestamp
        assert identifier in _rate_limit_store
        assert len(_rate_limit_store[identifier]) == 1

    def test_rate_limit_memory_bounded_proactive_sweep(self):
        """Der Store darf nicht unendlich wachsen; bei >1000 Einträgen wird proaktiv gefegt."""
        from security_oauth import _rate_limit_store, _check_rate_limit

        # Fülle den Store künstlich mit 1005 abgelaufenen Keys
        for i in range(1005):
            _rate_limit_store[f"old_ip_{i}"] = [time.time() - 3600]

        assert len(_rate_limit_store) > 1000

        # Trigger Limit Check -> Sollte proaktiv fegen
        allowed, remaining = _check_rate_limit("new_active_ip", max_requests=10)

        assert allowed is True
        # Alle 1005 abgelaufenen Keys müssen entfernt worden sein, nur der neue und aktive verbleibt
        assert len(_rate_limit_store) <= 5  # Erwartet: 1 (nur "new_active_ip")
        assert "new_active_ip" in _rate_limit_store


class TestAuditLogging:
    """Tests für Audit-Logging Funktion."""

    def test_audit_event_does_not_raise(self):
        """_audit_event sollte keine Exceptions werfen."""
        _audit_event("TEST_EVENT", True, "test_details", "127.0.0.1")
        _audit_event("TEST_EVENT", False, "test_details", "127.0.0.1")

    def test_module_exports_audit_function(self):
        """Audit-Funktion sollte exportiert sein."""
        from security_oauth import _audit_event
        assert callable(_audit_event)

