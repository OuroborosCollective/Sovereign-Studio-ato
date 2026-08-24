from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "backend" / "google_oauth_contract.py"
MIRROR = ROOT / "scripts" / "sovereign-backend" / "google_oauth_contract.py"


def _load_contract():
    spec = importlib.util.spec_from_file_location("google_oauth_contract_under_test", CANONICAL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_google_contract_mirror_is_byte_identical() -> None:
    assert CANONICAL.read_bytes() == MIRROR.read_bytes()


def test_google_configuration_fails_closed_and_returns_only_fingerprint() -> None:
    contract = _load_contract()
    assert contract.google_oauth_configuration("")["configured"] is False
    assert contract.google_oauth_configuration("not-a-google-client")["configured"] is False

    client_id = "client-test.apps.googleusercontent.com"
    configured = contract.google_oauth_configuration(client_id)
    assert configured == {
        "configured": True,
        "clientIdFingerprint": hashlib.sha256(client_id.encode("utf-8")).hexdigest(),
        "audienceVerificationRequired": True,
        "issuerVerificationRequired": True,
        "emailVerificationRequired": True,
        "rawCredentialReturned": False,
    }
    assert client_id not in repr(configured)


def test_google_identity_requires_issuer_subject_and_verified_email() -> None:
    contract = _load_contract()
    identity = contract.validate_google_identity_claims({
        "iss": "https://accounts.google.com",
        "sub": "google-user-1",
        "email": "Person@Example.Test",
        "email_verified": True,
        "name": "Person",
        "picture": "https://example.test/avatar.png",
    })
    assert identity == {
        "googleId": "google-user-1",
        "email": "person@example.test",
        "displayName": "Person",
        "avatarUrl": "https://example.test/avatar.png",
    }

    with pytest.raises(ValueError, match="google_issuer_invalid"):
        contract.validate_google_identity_claims({
            "iss": "https://evil.example",
            "sub": "google-user-1",
            "email": "person@example.test",
            "email_verified": True,
        })
    with pytest.raises(ValueError, match="google_email_unverified"):
        contract.validate_google_identity_claims({
            "iss": "accounts.google.com",
            "sub": "google-user-1",
            "email": "person@example.test",
            "email_verified": False,
        })


def test_google_identity_drops_non_https_avatar() -> None:
    contract = _load_contract()
    identity = contract.validate_google_identity_claims({
        "iss": "accounts.google.com",
        "sub": "google-user-2",
        "email": "person@example.test",
        "email_verified": True,
        "picture": "http://example.test/avatar.png",
    })
    assert identity["avatarUrl"] is None
