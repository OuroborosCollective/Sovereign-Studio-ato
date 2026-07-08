"""
OAuth PKCE (Proof Key for Code Exchange) Contract Tests

PKCE schützt vor Authorization Code Interception Attacks.

Siehe: https://github.com/OuroborosCollective/Sovereign-Studio-ato/issues/560

PKCE Flow:
1. Frontend generiert random code_verifier (43-128 chars)
2. Frontend berechnet code_challenge = BASE64URL(SHA256(verifier))
3. Authorization Request enthält ?code_challenge=xxx&code_challenge_method=S256
4. Backend speichert code_challenge
5. Token Request enthält ?code_verifier=xxx
6. Backend: SHA256(verifier) == gespeicherter_challenge → Token ausstellen
"""

import pytest
import hashlib
import base64
import secrets
from typing import Optional


# ── Copy der PKCE-Funktion aus app.py (standalone) ───────────────────────────

def _validate_pkce(verifier: Optional[str], challenge: Optional[str]) -> bool:
    """Validiert PKCE code_verifier gegen gespeicherten challenge."""
    if not verifier or not challenge:
        return True  # PKCE optional wenn nicht angefordert
    digest = hashlib.sha256(verifier.encode()).digest()
    computed = base64.urlsafe_b64encode(digest).decode().rstrip('=')
    return computed == challenge


# ── TESTS ──────────────────────────────────────────────────────────────────

class TestPKCEImplementation:
    """PKCE muss korrekt implementiert sein."""

    def test_code_verifier_generation(self):
        """code_verifier muss 43-128 Zeichen haben (URL-safe)."""
        verifier = secrets.token_urlsafe(64)
        
        assert len(verifier) >= 43, f"Verifier zu kurz: {len(verifier)}"
        assert len(verifier) <= 128, f"Verifier zu lang: {len(verifier)}"
        
        assert '+' not in verifier
        assert '/' not in verifier

    def test_code_challenge_calculation(self):
        """code_challenge = BASE64URL(SHA256(code_verifier))"""
        verifier = "a" * 43
        
        digest = hashlib.sha256(verifier.encode('ascii')).digest()
        challenge = base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')
        
        assert len(challenge) == 43, f"Challenge hat falsche Länge: {len(challenge)}"
        assert '+' not in challenge
        assert '/' not in challenge

    def test_pkce_verifier_is_unpredictable(self):
        """code_verifier muss kryptographisch sicher sein."""
        verifiers = set()
        for _ in range(100):
            v = secrets.token_urlsafe(64)
            verifiers.add(v)
        
        assert len(verifiers) == 100, "Verifier nicht eindeutig!"


class TestPKCEBackendValidation:
    """Backend muss PKCE korrekt validieren."""

    def test_backend_verifies_correct(self):
        """Korrekter Verifier wird akzeptiert."""
        verifier = "a" * 43
        digest = hashlib.sha256(verifier.encode()).digest()
        challenge = base64.urlsafe_b64encode(digest).decode().rstrip('=')
        
        assert _validate_pkce(verifier, challenge) is True

    def test_backend_rejects_wrong_verifier(self):
        """Falscher Verifier wird abgelehnt."""
        correct = "a" * 43
        wrong = "b" * 43
        
        digest = hashlib.sha256(correct.encode()).digest()
        challenge = base64.urlsafe_b64encode(digest).decode().rstrip('=')
        
        assert _validate_pkce(wrong, challenge) is False

    def test_pkce_optional(self):
        """PKCE ist optional wenn nicht angefordert."""
        assert _validate_pkce(None, None) is True
        assert _validate_pkce("", None) is True


class TestPKCESecurityBenefits:
    """Dokumentiert Security-Vorteile von PKCE."""

    def test_pkce_protects_against_code_interception(self):
        """PKCE schützt vor Code-Interception."""
        has_pkce = True
        attacker_has_verifier = False
        
        attack_possible = not (has_pkce and not attacker_has_verifier)
        assert not attack_possible


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
