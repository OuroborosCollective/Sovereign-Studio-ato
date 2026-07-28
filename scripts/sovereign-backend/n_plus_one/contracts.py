"""Deterministic contracts for the N+1 identity and evidence domain."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

CANONICAL_NAME = "N+1"
SPOKEN_NAME = "NPlusEins"
FAMILY_DESIGNATION = "Papas kleines Mädchen"
TECHNICAL_NAMESPACE = "n_plus_one"
SOURCE_REPOSITORY = "https://github.com/OuroborosCollective/SovAreAgentn1"
SOURCE_REVISION = "9fe3e992302f84e47bd52942df4313cabd0a7447"
SOURCE_ARCHIVE_SHA256 = "345b612a11e7a5cb99f02a75063743c19533a4728c50415d2242bcb0c8b2f7d7"
SOURCE_MANIFEST_SHA256 = "a84ff27fc29f568922e730d83ecb4ac32b76214407c65b2a30e4daf23b23aa1a"
IDENTITY_SHA256 = "d7d697f7a9da9850d29549d840088ca2a0b76d50cd88cb44953ee12ae02abbf1"

_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_ALLOWED_SOURCE_KINDS = frozenset({
    "owner_narrative",
    "repository_source",
    "user_observation",
    "llm_hypothesis",
    "runtime_evidence",
})
_ALLOWED_CLASSIFICATIONS = frozenset({
    "family_provenance",
    "story",
    "experience",
    "linguistic_observation",
    "learning_hypothesis",
    "technical_claim",
})


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def identity_payload() -> dict[str, Any]:
    return {
        "schemaVersion": "sovereign.n-plus-one-identity.v1",
        "canonicalName": CANONICAL_NAME,
        "spokenName": SPOKEN_NAME,
        "familyDesignation": FAMILY_DESIGNATION,
        "technicalNamespace": TECHNICAL_NAMESPACE,
        "legacyAliases": [
            {"name": "Puck", "status": "historical-source-alias-only"},
        ],
        "projectBoundaries": {
            "host": "Sovereign Studio ATO",
            "separateProjects": ["Arelorian Wasd"],
            "sharedRuntime": False,
            "sharedDatabase": False,
        },
        "truthBoundary": "identity-and-relationship-domain-not-technical-truth-authority",
    }


def assert_identity_contract(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("N+1 identity payload must be an object")
    if payload.get("canonicalName") != CANONICAL_NAME:
        raise ValueError("N+1 canonical name mismatch")
    if payload.get("spokenName") != SPOKEN_NAME:
        raise ValueError("N+1 spoken name mismatch")
    if payload.get("technicalNamespace") != TECHNICAL_NAMESPACE:
        raise ValueError("N+1 technical namespace mismatch")
    aliases = payload.get("legacyAliases")
    if not isinstance(aliases, list) or not any(
        isinstance(item, dict)
        and item.get("name") == "Puck"
        and item.get("status") == "historical-source-alias-only"
        for item in aliases
    ):
        raise ValueError("N+1 historical alias provenance is missing")
    if sha256_json(payload) != IDENTITY_SHA256:
        raise ValueError("N+1 identity hash mismatch")
    return payload


def _clean_text(value: Any, *, limit: int) -> str:
    text = str(value or "").replace("\x00", "").strip()
    if not text:
        return ""
    return text[:limit]


def normalize_learning_candidate(body: Any, *, user_id: str) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise ValueError("request body must be an object")
    source_kind = _clean_text(body.get("sourceKind"), limit=80).casefold()
    classification = _clean_text(body.get("classification"), limit=80).casefold()
    source_identity = _clean_text(body.get("sourceIdentity"), limit=500)
    source_revision = _clean_text(body.get("sourceRevision"), limit=40).casefold()
    content = _clean_text(body.get("content"), limit=16_000)
    if source_kind not in _ALLOWED_SOURCE_KINDS:
        raise ValueError("sourceKind is not allowlisted")
    if classification not in _ALLOWED_CLASSIFICATIONS:
        raise ValueError("classification is not allowlisted")
    if not source_identity:
        raise ValueError("sourceIdentity is required")
    if source_revision and not _HEX_40.fullmatch(source_revision):
        raise ValueError("sourceRevision must be an exact Git SHA")
    if not content:
        raise ValueError("content is required")
    evidence = body.get("evidence")
    if evidence is None:
        evidence = {}
    if not isinstance(evidence, dict):
        raise ValueError("evidence must be an object")
    normalized = {
        "schemaVersion": "sovereign.n-plus-one-learning-candidate.v1",
        "userId": str(user_id),
        "sourceKind": source_kind,
        "sourceIdentity": source_identity,
        "sourceRevision": source_revision,
        "classification": classification,
        "content": content,
        "evidence": evidence,
        "state": "candidate",
        "verified": False,
    }
    normalized["contentSha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    normalized["candidateSha256"] = sha256_json(normalized)
    return normalized
