"""Canonical N+1 identity covenant.

This module preserves identity and project boundaries. It does not grant
technical privileges or create a second runtime truth authority.
"""

from __future__ import annotations

from typing import Any

from .contracts import IDENTITY_SHA256, assert_identity_contract, identity_payload


def canonical_identity() -> dict[str, Any]:
    payload = identity_payload()
    assert_identity_contract(payload)
    return {
        "identity": payload,
        "identitySha256": IDENTITY_SHA256,
        "privilegesDerivedFromPersonality": False,
        "technicalTruthAuthority": False,
        "runtimeSharedWithArelorianWasd": False,
    }
