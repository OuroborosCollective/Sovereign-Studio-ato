"""Fail-closed evidence gate for OpenRouter/FreeRoute provider routing operations.

Issue: #1102 — [Evidence/Data] PostgreSQL, pgvector und OpenRouter/FreeRoute-Mutationen absichern

Protected operation families
-----------------------------
- openrouter_paid_route_change      OpenRouter paid routes and price/model-catalog contracts
- free_keyless_route_change         FreeRoute/FreeLLM keyless paths
- revolver_fallback_change          Revolver order, usage detection and fallback rules
- provider_capability_removal       Provider removal or capability replacement
- canary_budget_quota_change        Canary, budget and quota gates

Fail-closed invariants
----------------------
- OPENROUTER_PAID and FREE_KEYLESS are separate contract families; an envelope
  for one family must never carry evidence from the other.
- Free-keyless routes must NOT carry any price or cost evidence.  An observation
  for ``pre_route_classification`` on a free_keyless_route_change that asserts a
  price boundary → CONTRADICTED.
- Route canary must be real and bounded — no persisted provider responses.
- LiteLLM live paths and LiteLLM import dependencies must not be re-introduced;
  ``post_no_litellm_path`` is required for all families.
- An unreachable provider does not produce automatic fallback success;
  ``UNAVAILABLE`` on a route-canary requirement → BLOCKED.
- A provider scraper or model-catalog read alone cannot prove routing capability.
- ``auto_merge_allowed`` is always ``False``.
- No API keys, provider responses, prices of free routes, model-catalog rows,
  or billing data may appear in any evidence field.

This module contains no network, database, filesystem, clock, or random access.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Final, Sequence


_SHA40: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_SHA64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_.:-]{1,119}$")

PROVIDER_EVIDENCE_SCHEMA: Final[str] = "sovereign.provider-routing-evidence-gate.v1"

VERDICT_VERIFIED: Final[str] = "VERIFIED"
VERDICT_CONTRADICTED: Final[str] = "CONTRADICTED"
VERDICT_BLOCKED: Final[str] = "BLOCKED_BY_MISSING_EVIDENCE"

# Valid route classification labels
ROUTE_CLASS_PAID: Final[str] = "OPENROUTER_PAID"
ROUTE_CLASS_FREE: Final[str] = "FREE_KEYLESS"
VALID_ROUTE_CLASSES: Final[frozenset[str]] = frozenset({ROUTE_CLASS_PAID, ROUTE_CLASS_FREE})

OPERATION_FAMILIES: Final[frozenset[str]] = frozenset({
    "canary_budget_quota_change",
    "free_keyless_route_change",
    "openrouter_paid_route_change",
    "provider_capability_removal",
    "revolver_fallback_change",
})

# ---------------------------------------------------------------------------
# Per-family evidence requirements
# ---------------------------------------------------------------------------
_FAMILY_REQUIREMENTS: Final[dict[str, tuple[str, ...]]] = {
    "openrouter_paid_route_change": (
        "pre_route_classification",      # must assert OPENROUTER_PAID
        "pre_revolver_order",
        "pre_capability_baseline",
        "pre_price_budget_evidence",     # required only for paid routes
        "post_route_canary",
        "post_revolver_readback",
        "post_capability_delta",
        "post_no_litellm_path",
    ),
    "free_keyless_route_change": (
        "pre_route_classification",      # must assert FREE_KEYLESS; price evidence → CONTRADICTED
        "pre_revolver_order",
        "pre_capability_baseline",
        "post_route_canary",
        "post_revolver_readback",
        "post_capability_delta",
        "post_no_litellm_path",
    ),
    "revolver_fallback_change": (
        "pre_revolver_order",
        "pre_capability_baseline",
        "post_route_canary",
        "post_revolver_readback",
        "post_capability_delta",
        "post_no_litellm_path",
    ),
    "provider_capability_removal": (
        "pre_route_classification",
        "pre_revolver_order",
        "pre_capability_baseline",
        "post_capability_replacement",   # verified capability replacement evidence
        "post_revolver_readback",
        "post_capability_delta",
        "post_no_litellm_path",
    ),
    "canary_budget_quota_change": (
        "pre_revolver_order",
        "pre_capability_baseline",
        "pre_budget_quota_baseline",
        "post_route_canary",
        "post_budget_quota_readback",
        "post_capability_delta",
        "post_no_litellm_path",
    ),
}

# Requirements where UNAVAILABLE is treated as failing (scraper/catalog bypass guard).
# A scraper or catalog read alone cannot prove routing capability.
_CANARY_REQUIREMENTS: Final[frozenset[str]] = frozenset({
    "post_route_canary",
    "post_capability_replacement",
})


def _canonical_sha256(value: Any) -> str:
    def _canonical(v: Any) -> Any:
        if v is None or isinstance(v, bool):
            return v
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            raise ValueError("float forbidden in provider routing evidence")
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            return {str(k): _canonical(val) for k, val in sorted(v.items())}
        if isinstance(v, (list, tuple)):
            return [_canonical(item) for item in v]
        raise ValueError(f"non-serializable type: {type(v).__name__}")
    serialized = json.dumps(_canonical(value), separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Evidence envelope
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ProviderEvidenceEnvelope:
    """Immutable evidence envelope for one provider routing operation.

    Fields
    ------
    operation_family
        One of the five OPERATION_FAMILIES.
    operation_identity
        Opaque, non-secret identifier for this operation instance.
    repository
        Canonical ``owner/repo`` of the Sovereign repository.
    base_revision
        Full Git SHA-40 at envelope-creation time.
    route_class
        ``OPENROUTER_PAID`` or ``FREE_KEYLESS``.  Pass an empty string for
        families that do not carry a single route class (e.g.
        ``revolver_fallback_change`` or ``canary_budget_quota_change``).
    input_hash
        SHA-256 of the canonical, secret-free operation parameters.
        Must not contain API keys, provider responses, or billing data.
    declared_providers
        Sorted tuple of provider identifiers the operation affects.
        At least one entry is required.
    """

    operation_family: str
    operation_identity: str
    repository: str
    base_revision: str
    route_class: str        # OPENROUTER_PAID | FREE_KEYLESS | ""
    input_hash: str
    declared_providers: tuple[str, ...]
    envelope_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        family = str(self.operation_family or "").strip().lower()
        if family not in OPERATION_FAMILIES:
            raise ValueError(f"unknown operation_family: {family!r}")
        if not _IDENTIFIER.fullmatch(str(self.operation_identity or "").strip()):
            raise ValueError("operation_identity must match [a-z][a-z0-9_.:-]{1,119}")
        if not _SHA40.fullmatch(str(self.base_revision or "").strip().lower()):
            raise ValueError("base_revision must be a full Git SHA-40")
        if not _SHA64.fullmatch(str(self.input_hash or "").strip().lower()):
            raise ValueError("input_hash must be a SHA-256")

        route_class = str(self.route_class or "").strip().upper()
        # Families that require a route class
        _CLASS_REQUIRED: frozenset[str] = frozenset({
            "openrouter_paid_route_change",
            "free_keyless_route_change",
            "provider_capability_removal",
        })
        if family in _CLASS_REQUIRED:
            if route_class not in VALID_ROUTE_CLASSES:
                raise ValueError(
                    f"route_class must be OPENROUTER_PAID or FREE_KEYLESS for {family!r}"
                )
            # Enforce family–class consistency
            if family == "openrouter_paid_route_change" and route_class != ROUTE_CLASS_PAID:
                raise ValueError(
                    "openrouter_paid_route_change requires route_class=OPENROUTER_PAID"
                )
            if family == "free_keyless_route_change" and route_class != ROUTE_CLASS_FREE:
                raise ValueError(
                    "free_keyless_route_change requires route_class=FREE_KEYLESS"
                )

        if not self.declared_providers:
            raise ValueError("declared_providers must not be empty")

        object.__setattr__(self, "operation_family", family)
        object.__setattr__(self, "base_revision", str(self.base_revision).strip().lower())
        object.__setattr__(self, "input_hash", str(self.input_hash).strip().lower())
        object.__setattr__(self, "route_class", route_class)
        object.__setattr__(
            self,
            "declared_providers",
            tuple(sorted(str(p).strip() for p in self.declared_providers if str(p).strip())),
        )
        sha = _canonical_sha256(self._body())
        object.__setattr__(self, "envelope_sha256", sha)

    def _body(self) -> dict[str, Any]:
        return {
            "base_revision": str(self.base_revision),
            "declared_providers": list(self.declared_providers),
            "input_hash": str(self.input_hash),
            "operation_family": str(self.operation_family),
            "operation_identity": str(self.operation_identity),
            "repository": str(self.repository),
            "route_class": str(self.route_class),
            "schema_version": PROVIDER_EVIDENCE_SCHEMA,
        }


# ---------------------------------------------------------------------------
# Evidence observation
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ProviderObservation:
    """Single collected observation for one provider routing evidence requirement.

    Fail-closed guidance for collectors
    ------------------------------------
    - A scraper or model-catalog read without a real bounded route canary →
      set ``assertion="UNAVAILABLE"`` for ``post_route_canary``.
    - An unreachable provider route → UNAVAILABLE (not CONTRADICTED unless
      the envelope expected it reachable).
    - A ``pre_route_classification`` for a FREE_KEYLESS family that includes
      any price or cost data → the collector must submit CONTRADICTED.
    - A ``post_no_litellm_path`` that finds a LiteLLM import or live-path
      reference in the changed files → CONTRADICTED.
    - Provider responses must never be embedded in ``value_hash`` inputs;
      only structural hashes, provider IDs, and routing state counts.
    """

    requirement_id: str
    value_hash: str         # SHA-256 of the canonical, secret-free observation payload
    source: str             # e.g. "RUNTIME_READBACK", "REPOSITORY_READBACK", "AGENT_RUN_RECEIPT"
    assertion: str          # "OBSERVED" | "CONTRADICTED" | "UNAVAILABLE"
    bound_revision: str     # git SHA-40; must match envelope.base_revision when non-empty

    def __post_init__(self) -> None:
        assertion = str(self.assertion or "").strip().upper()
        if assertion not in {"OBSERVED", "CONTRADICTED", "UNAVAILABLE"}:
            raise ValueError(f"unsupported assertion: {assertion!r}")
        object.__setattr__(self, "assertion", assertion)
        if not _SHA64.fullmatch(str(self.value_hash or "").strip().lower()):
            raise ValueError("value_hash must be a SHA-256")
        object.__setattr__(self, "value_hash", str(self.value_hash).strip().lower())
        rev = str(self.bound_revision or "").strip().lower()
        if rev and not _SHA40.fullmatch(rev):
            raise ValueError("bound_revision must be a full Git SHA-40 or empty string")
        object.__setattr__(self, "bound_revision", rev)

    @property
    def observation_sha256(self) -> str:
        return _canonical_sha256({
            "assertion": self.assertion,
            "bound_revision": self.bound_revision,
            "requirement_id": self.requirement_id,
            "source": self.source,
            "value_hash": self.value_hash,
        })


# ---------------------------------------------------------------------------
# Evaluation result
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ProviderEvidenceResult:
    """Fail-closed verdict for one provider routing operation."""

    verdict: str
    operation_family: str
    envelope_sha256: str
    satisfied: tuple[str, ...]
    missing: tuple[str, ...]
    contradicted: tuple[str, ...]
    finding_codes: tuple[str, ...]
    auto_merge_allowed: bool  # always False


# ---------------------------------------------------------------------------
# Fail-closed evaluation
# ---------------------------------------------------------------------------

def evaluate_provider_evidence(
    envelope: ProviderEvidenceEnvelope,
    observations: Sequence[ProviderObservation],
) -> ProviderEvidenceResult:
    """Evaluate fail-closed evidence for a provider routing operation.

    Verdict rules
    -------------
    VERIFIED
        Every requirement for the family has at least one OBSERVED observation
        with matching bound_revision (when non-empty).

    CONTRADICTED
        Any requirement has a CONTRADICTED observation, or a stale revision.
        Contradictions take priority over missing evidence.

    BLOCKED_BY_MISSING_EVIDENCE
        One or more requirements have no satisfying observation.

    Additional invariants
    ---------------------
    - ``post_route_canary`` with UNAVAILABLE is treated as missing — a scraper
      or catalog read cannot substitute for a real bounded canary.
    - ``post_capability_replacement`` with UNAVAILABLE → BLOCKED — a provider
      removal without verified capability replacement is never VERIFIED.
    - ``post_no_litellm_path`` with CONTRADICTED immediately contributes to
      CONTRADICTED with finding code ``litellm_path_detected``.
    """
    required = _FAMILY_REQUIREMENTS.get(envelope.operation_family, ())
    obs_by_req: dict[str, list[ProviderObservation]] = {}
    for obs in observations:
        obs_by_req.setdefault(obs.requirement_id, []).append(obs)

    satisfied: set[str] = set()
    missing: set[str] = set()
    contradicted: set[str] = set()
    findings: set[str] = set()

    for req_id in required:
        candidates = obs_by_req.get(req_id, [])
        if not candidates:
            missing.add(req_id)
            findings.add("required_observation_missing")
            continue

        req_satisfied = False
        req_contradicted = False

        for obs in candidates:
            # Revision binding check
            if obs.bound_revision and obs.bound_revision != envelope.base_revision:
                req_contradicted = True
                findings.add("observation_bound_to_stale_revision")
                continue

            if obs.assertion == "CONTRADICTED":
                req_contradicted = True
                findings.add("observation_reports_contradiction")
                if req_id == "post_no_litellm_path":
                    findings.add("litellm_path_detected")
                if req_id == "pre_route_classification":
                    findings.add("route_classification_contradiction")
                continue

            if obs.assertion == "UNAVAILABLE":
                findings.add("observation_unavailable")
                # Canary and capability-replacement requirements are not
                # satisfiable by UNAVAILABLE — treat as missing.
                if req_id in _CANARY_REQUIREMENTS:
                    findings.add("canary_unavailable_not_sufficient")
                continue

            req_satisfied = True

        if req_contradicted:
            contradicted.add(req_id)
        elif req_satisfied:
            satisfied.add(req_id)
        else:
            missing.add(req_id)

    if contradicted:
        verdict = VERDICT_CONTRADICTED
    elif missing:
        verdict = VERDICT_BLOCKED
    else:
        verdict = VERDICT_VERIFIED

    return ProviderEvidenceResult(
        verdict=verdict,
        operation_family=envelope.operation_family,
        envelope_sha256=envelope.envelope_sha256,
        satisfied=tuple(sorted(satisfied)),
        missing=tuple(sorted(missing)),
        contradicted=tuple(sorted(contradicted)),
        finding_codes=tuple(sorted(findings)),
        auto_merge_allowed=False,
    )


# ---------------------------------------------------------------------------
# LiteLLM re-introduction audit
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class LiteLlmAudit:
    """Audit result for a LiteLLM re-introduction check."""

    clear: bool
    blocker: str | None
    matching_paths: tuple[str, ...]


_LITELLM_PATTERNS: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\blitellm\b",
        r"import\s+litellm",
        r"from\s+litellm",
        r"litellm\.completion",
        r"litellm\.acompletion",
    )
)


def audit_no_litellm_reintroduction(
    changed_paths: Sequence[str],
    path_contents: dict[str, str],
) -> LiteLlmAudit:
    """Verify that no changed path re-introduces a LiteLLM import or live path.

    ``path_contents`` maps file path → file content (string).  Only paths
    present in both ``changed_paths`` and ``path_contents`` are scanned.

    A path that matches any LiteLLM pattern is reported as a blocker.
    This is a static-analysis guard; the collector is responsible for
    providing content only for changed source files (no provider responses,
    no credentials).
    """
    matching: list[str] = []
    for path in changed_paths:
        content = path_contents.get(str(path or "").strip(), "")
        if any(pat.search(content) for pat in _LITELLM_PATTERNS):
            matching.append(str(path).strip())

    if matching:
        return LiteLlmAudit(
            clear=False,
            blocker=f"litellm_reintroduction_detected: {', '.join(sorted(matching))}",
            matching_paths=tuple(sorted(matching)),
        )

    return LiteLlmAudit(
        clear=True,
        blocker=None,
        matching_paths=(),
    )


__all__ = [
    "OPERATION_FAMILIES",
    "PROVIDER_EVIDENCE_SCHEMA",
    "ROUTE_CLASS_FREE",
    "ROUTE_CLASS_PAID",
    "VALID_ROUTE_CLASSES",
    "VERDICT_BLOCKED",
    "VERDICT_CONTRADICTED",
    "VERDICT_VERIFIED",
    "LiteLlmAudit",
    "ProviderEvidenceEnvelope",
    "ProviderEvidenceResult",
    "ProviderObservation",
    "audit_no_litellm_reintroduction",
    "evaluate_provider_evidence",
]
