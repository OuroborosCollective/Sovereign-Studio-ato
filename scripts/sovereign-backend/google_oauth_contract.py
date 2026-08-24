"""Pure Google OAuth identity/configuration contract.

This module contains no network, database, filesystem or secret access. It is
mirrored byte-for-byte into scripts/sovereign-backend for the deployed backend.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping

GOOGLE_CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]+\.apps\.googleusercontent\.com$")
GOOGLE_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})


def google_oauth_configuration(client_id: str) -> dict[str, Any]:
    normalized = str(client_id or "").strip()
    configured = bool(GOOGLE_CLIENT_ID_RE.fullmatch(normalized))
    return {
        "configured": configured,
        "clientIdFingerprint": hashlib.sha256(normalized.encode("utf-8")).hexdigest() if configured else None,
        "audienceVerificationRequired": True,
        "issuerVerificationRequired": True,
        "emailVerificationRequired": True,
        "rawCredentialReturned": False,
    }


def validate_google_identity_claims(payload: Mapping[str, Any]) -> dict[str, str | None]:
    issuer = str(payload.get("iss") or "").strip()
    if issuer not in GOOGLE_ISSUERS:
        raise ValueError("google_issuer_invalid")

    google_id = str(payload.get("sub") or "").strip()
    if not google_id or len(google_id) > 255:
        raise ValueError("google_subject_invalid")

    email = str(payload.get("email") or "").strip().lower()
    if not email or len(email) > 320 or "@" not in email:
        raise ValueError("google_email_invalid")
    if payload.get("email_verified") is not True:
        raise ValueError("google_email_unverified")

    display_name = str(payload.get("name") or "").strip()[:255] or email.split("@", 1)[0]
    picture = str(payload.get("picture") or "").strip()
    avatar_url = picture if picture.startswith("https://") and len(picture) <= 2048 else None

    return {
        "googleId": google_id,
        "email": email,
        "displayName": display_name,
        "avatarUrl": avatar_url,
    }
