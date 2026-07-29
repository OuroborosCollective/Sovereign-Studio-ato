"""Evidence-only LinguaHabar observations.

Exact configured marker matches are observations, not dialect classifications.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from ..contracts import canonical_json


# Global module-level cache to store compiled regular expressions and case-folded markers.
# This prevents redundant re-compilation, string escaping, and casing operations across function calls.
_MARKER_CACHE: dict[str, tuple[str, re.Pattern[str]]] = {}


def _get_marker_cached_info(marker: str) -> tuple[str, re.Pattern[str]]:
    """Gets the precomputed case-folded representation and compiled Pattern for a marker from the cache."""
    info = _MARKER_CACHE.get(marker)
    if info is None:
        info = (marker.casefold(), re.compile(re.escape(marker), flags=re.IGNORECASE))
        _MARKER_CACHE[marker] = info
    return info


def observe_configured_markers(text: str, rules: list[dict[str, Any]]) -> dict[str, Any]:
    source_text = str(text or "")
    if not source_text.strip():
        raise ValueError("text is required")
    if len(source_text) > 8_000:
        raise ValueError("text exceeds the bounded observation limit")

    # Case-fold the source text once to perform fast O(1) string contains filtering per rule
    source_text_folded = source_text.casefold()

    observations: list[dict[str, Any]] = []
    for rule in sorted(
        (item for item in rules if isinstance(item, dict)),
        key=lambda item: (
            str(item.get("profileKey") or ""),
            str(item.get("ruleKey") or ""),
            str(item.get("markerText") or ""),
        ),
    ):
        marker = str(rule.get("markerText") or "")
        if not marker:
            continue

        # Fast path check: retrieve cached case-folded marker and precompiled regex pattern
        marker_folded, pattern = _get_marker_cached_info(marker)

        # Skip scanning with the heavy regex engine if the case-insensitive marker is not present in the text
        if marker_folded not in source_text_folded:
            continue

        for match in re.finditer(pattern, source_text):
            payload = {
                "schemaVersion": "sovereign.n-plus-one-linguistic-observation.v1",
                "profileKey": str(rule.get("profileKey") or ""),
                "ruleKey": str(rule.get("ruleKey") or ""),
                "category": str(rule.get("category") or "unclassified"),
                "spanStart": match.start(),
                "spanEnd": match.end(),
                "matchedText": source_text[match.start():match.end()],
                "matchConfidencePpm": max(
                    0,
                    min(1_000_000, int(rule.get("confidencePpm") or 0)),
                ),
                "sourceReference": (
                    rule.get("sourceReference")
                    if isinstance(rule.get("sourceReference"), dict)
                    else {}
                ),
                "classificationState": "candidate_observation",
                "dialectVerified": False,
            }
            payload["observationSha256"] = hashlib.sha256(
                canonical_json(payload).encode("utf-8")
            ).hexdigest()
            observations.append(payload)

    text_sha256 = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    batch_identity = {
        "textSha256": text_sha256,
        "observationSha256": [item["observationSha256"] for item in observations],
    }
    return {
        "schemaVersion": "sovereign.n-plus-one-linguistic-observation-batch.v1",
        "textSha256": text_sha256,
        "batchSha256": hashlib.sha256(
            canonical_json(batch_identity).encode("utf-8")
        ).hexdigest(),
        "observations": observations,
        "observationCount": len(observations),
        "dialectVerified": False,
        "detectorClaimed": False,
        "truthNotice": (
            "Exact configured marker matches only; no dialect model or dialect "
            "classification was executed."
        ),
    }
