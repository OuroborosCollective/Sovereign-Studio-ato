"""Tests for provider_routing_evidence_gate.py — Issue #1102 (provider half).

Covers:
- Envelope validation (all five families, route_class consistency, required fields)
- Observation validation (assertion values, revision binding)
- evaluate_provider_evidence — VERIFIED, CONTRADICTED, BLOCKED for each family
- Fail-closed invariants:
  - Stale revision → CONTRADICTED
  - post_route_canary UNAVAILABLE → BLOCKED (scraper bypass guard)
  - post_capability_replacement UNAVAILABLE → BLOCKED
  - post_no_litellm_path CONTRADICTED → CONTRADICTED + litellm_path_detected
  - pre_route_classification CONTRADICTED → route_classification_contradiction
  - contradicted takes priority over missing
  - auto_merge_allowed is always False
- Route-class consistency (paid/free mismatch raises)
- audit_no_litellm_reintroduction (clear + each pattern variant)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent_runtime.provider_routing_evidence_gate import (
    OPERATION_FAMILIES,
    ROUTE_CLASS_FREE,
    ROUTE_CLASS_PAID,
    VERDICT_BLOCKED,
    VERDICT_CONTRADICTED,
    VERDICT_VERIFIED,
    LiteLlmAudit,
    ProviderEvidenceEnvelope,
    ProviderEvidenceResult,
    ProviderObservation,
    audit_no_litellm_reintroduction,
    evaluate_provider_evidence,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SHA40_A = "a" * 40
_SHA40_B = "b" * 40
_SHA64_A = "a" * 64
_SHA64_B = "b" * 64
_SHA64_C = "c" * 64

_FAMILY_ROUTE_CLASS: dict[str, str] = {
    "openrouter_paid_route_change": ROUTE_CLASS_PAID,
    "free_keyless_route_change": ROUTE_CLASS_FREE,
    "revolver_fallback_change": "",
    "provider_capability_removal": ROUTE_CLASS_PAID,
    "canary_budget_quota_change": "",
}


def _envelope(
    family: str = "openrouter_paid_route_change",
    *,
    identity: str = "prov.abc-001",
    repository: str = "owner/repo",
    base_revision: str = _SHA40_A,
    route_class: str | None = None,
    input_hash: str = _SHA64_A,
    declared_providers: tuple[str, ...] = ("openrouter",),
) -> ProviderEvidenceEnvelope:
    if route_class is None:
        route_class = _FAMILY_ROUTE_CLASS.get(family, "")
    return ProviderEvidenceEnvelope(
        operation_family=family,
        operation_identity=identity,
        repository=repository,
        base_revision=base_revision,
        route_class=route_class,
        input_hash=input_hash,
        declared_providers=declared_providers,
    )


def _obs(
    requirement_id: str,
    *,
    value_hash: str = _SHA64_C,
    source: str = "RUNTIME_READBACK",
    assertion: str = "OBSERVED",
    bound_revision: str = _SHA40_A,
) -> ProviderObservation:
    return ProviderObservation(
        requirement_id=requirement_id,
        value_hash=value_hash,
        source=source,
        assertion=assertion,
        bound_revision=bound_revision,
    )


def _full_observations(family: str) -> list[ProviderObservation]:
    from agent_runtime.provider_routing_evidence_gate import _FAMILY_REQUIREMENTS
    return [
        ProviderObservation(
            requirement_id=req_id,
            value_hash=_SHA64_C,
            source="RUNTIME_READBACK",
            assertion="OBSERVED",
            bound_revision=_SHA40_A,
        )
        for req_id in _FAMILY_REQUIREMENTS[family]
    ]


# ---------------------------------------------------------------------------
# Envelope validation
# ---------------------------------------------------------------------------

class TestEnvelopeValidation:
    def test_all_five_families_create_envelope(self) -> None:
        for family in OPERATION_FAMILIES:
            env = _envelope(family=family)
            assert env.operation_family == family

    def test_unknown_family_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown operation_family"):
            _envelope(family="not_a_family")

    def test_invalid_base_revision_raises(self) -> None:
        with pytest.raises(ValueError, match="SHA-40"):
            _envelope(base_revision="short")

    def test_invalid_input_hash_raises(self) -> None:
        with pytest.raises(ValueError, match="SHA-256"):
            _envelope(input_hash="bad")

    def test_invalid_operation_identity_raises(self) -> None:
        with pytest.raises(ValueError, match="operation_identity"):
            _envelope(identity="BAD IDENTITY!")

    def test_empty_declared_providers_raises(self) -> None:
        with pytest.raises(ValueError, match="declared_providers"):
            _envelope(declared_providers=())

    def test_paid_family_requires_paid_class(self) -> None:
        with pytest.raises(ValueError, match="OPENROUTER_PAID"):
            _envelope(family="openrouter_paid_route_change", route_class=ROUTE_CLASS_FREE)

    def test_free_family_requires_free_class(self) -> None:
        with pytest.raises(ValueError, match="FREE_KEYLESS"):
            _envelope(family="free_keyless_route_change", route_class=ROUTE_CLASS_PAID)

    def test_paid_family_rejects_empty_class(self) -> None:
        with pytest.raises(ValueError):
            _envelope(family="openrouter_paid_route_change", route_class="")

    def test_revolver_family_allows_empty_class(self) -> None:
        env = _envelope(family="revolver_fallback_change", route_class="")
        assert env.route_class == ""

    def test_canary_family_allows_empty_class(self) -> None:
        env = _envelope(family="canary_budget_quota_change", route_class="")
        assert env.route_class == ""

    def test_provider_removal_accepts_free_class(self) -> None:
        env = _envelope(family="provider_capability_removal", route_class=ROUTE_CLASS_FREE)
        assert env.route_class == ROUTE_CLASS_FREE

    def test_envelope_sha256_deterministic(self) -> None:
        env1 = _envelope()
        env2 = _envelope()
        assert env1.envelope_sha256 == env2.envelope_sha256

    def test_envelope_sha256_changes_with_family(self) -> None:
        env1 = _envelope(family="openrouter_paid_route_change")
        env2 = _envelope(family="revolver_fallback_change")
        assert env1.envelope_sha256 != env2.envelope_sha256

    def test_envelope_is_immutable(self) -> None:
        env = _envelope()
        with pytest.raises((AttributeError, TypeError)):
            env.operation_family = "other"  # type: ignore[misc]

    def test_declared_providers_sorted(self) -> None:
        env = _envelope(declared_providers=("z_provider", "a_provider"))
        assert env.declared_providers == ("a_provider", "z_provider")


# ---------------------------------------------------------------------------
# Observation validation
# ---------------------------------------------------------------------------

class TestObservationValidation:
    def test_valid_observation(self) -> None:
        obs = _obs("pre_route_classification")
        assert obs.assertion == "OBSERVED"

    def test_invalid_assertion_raises(self) -> None:
        with pytest.raises(ValueError, match="unsupported assertion"):
            ProviderObservation(
                requirement_id="x",
                value_hash=_SHA64_A,
                source="RUNTIME_READBACK",
                assertion="SCRAPER_CATALOG",
                bound_revision="",
            )

    def test_invalid_value_hash_raises(self) -> None:
        with pytest.raises(ValueError, match="SHA-256"):
            _obs("x", value_hash="bad")

    def test_invalid_bound_revision_raises(self) -> None:
        with pytest.raises(ValueError, match="SHA-40"):
            _obs("x", bound_revision="not-sha40")

    def test_empty_bound_revision_allowed(self) -> None:
        obs = _obs("x", bound_revision="")
        assert obs.bound_revision == ""

    def test_observation_sha256_deterministic(self) -> None:
        obs1 = _obs("req")
        obs2 = _obs("req")
        assert obs1.observation_sha256 == obs2.observation_sha256

    def test_observation_is_immutable(self) -> None:
        obs = _obs("req")
        with pytest.raises((AttributeError, TypeError)):
            obs.assertion = "UNAVAILABLE"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# evaluate_provider_evidence — happy path
# ---------------------------------------------------------------------------

class TestEvaluateVerified:
    @pytest.mark.parametrize("family", sorted(OPERATION_FAMILIES))
    def test_all_families_verified_with_full_observations(self, family: str) -> None:
        env = _envelope(family=family)
        result = evaluate_provider_evidence(env, _full_observations(family))
        assert result.verdict == VERDICT_VERIFIED, (
            f"{family}: missing={result.missing}, contradicted={result.contradicted}"
        )

    @pytest.mark.parametrize("family", sorted(OPERATION_FAMILIES))
    def test_auto_merge_always_false(self, family: str) -> None:
        env = _envelope(family=family)
        result = evaluate_provider_evidence(env, _full_observations(family))
        assert result.auto_merge_allowed is False

    def test_envelope_sha256_propagated(self) -> None:
        env = _envelope()
        result = evaluate_provider_evidence(env, _full_observations("openrouter_paid_route_change"))
        assert result.envelope_sha256 == env.envelope_sha256

    def test_result_is_immutable(self) -> None:
        env = _envelope()
        result = evaluate_provider_evidence(env, _full_observations("openrouter_paid_route_change"))
        with pytest.raises((AttributeError, TypeError)):
            result.verdict = "VERIFIED"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# evaluate_provider_evidence — BLOCKED paths
# ---------------------------------------------------------------------------

class TestEvaluateBlocked:
    def test_empty_observations_blocked(self) -> None:
        env = _envelope()
        result = evaluate_provider_evidence(env, [])
        assert result.verdict == VERDICT_BLOCKED

    def test_single_missing_requirement_blocked(self) -> None:
        env = _envelope(family="openrouter_paid_route_change")
        obs = [o for o in _full_observations("openrouter_paid_route_change") if o.requirement_id != "post_no_litellm_path"]
        result = evaluate_provider_evidence(env, obs)
        assert result.verdict == VERDICT_BLOCKED
        assert "post_no_litellm_path" in result.missing

    def test_canary_unavailable_blocked(self) -> None:
        """A scraper/catalog read must not substitute for a real bounded canary."""
        env = _envelope(family="openrouter_paid_route_change")
        obs = [
            ProviderObservation(
                requirement_id="post_route_canary",
                value_hash=_SHA64_C,
                source="RUNTIME_READBACK",
                assertion="UNAVAILABLE",
                bound_revision=_SHA40_A,
            )
            if o.requirement_id == "post_route_canary"
            else o
            for o in _full_observations("openrouter_paid_route_change")
        ]
        result = evaluate_provider_evidence(env, obs)
        assert result.verdict == VERDICT_BLOCKED
        assert "post_route_canary" in result.missing
        assert "canary_unavailable_not_sufficient" in result.finding_codes

    def test_capability_replacement_unavailable_blocked(self) -> None:
        env = _envelope(family="provider_capability_removal")
        obs = [
            ProviderObservation(
                requirement_id="post_capability_replacement",
                value_hash=_SHA64_C,
                source="RUNTIME_READBACK",
                assertion="UNAVAILABLE",
                bound_revision=_SHA40_A,
            )
            if o.requirement_id == "post_capability_replacement"
            else o
            for o in _full_observations("provider_capability_removal")
        ]
        result = evaluate_provider_evidence(env, obs)
        assert result.verdict == VERDICT_BLOCKED
        assert "post_capability_replacement" in result.missing
        assert "canary_unavailable_not_sufficient" in result.finding_codes

    def test_free_keyless_requires_post_no_litellm_path(self) -> None:
        env = _envelope(family="free_keyless_route_change")
        obs = [o for o in _full_observations("free_keyless_route_change") if o.requirement_id != "post_no_litellm_path"]
        result = evaluate_provider_evidence(env, obs)
        assert result.verdict == VERDICT_BLOCKED
        assert "post_no_litellm_path" in result.missing

    def test_revolver_change_requires_post_revolver_readback(self) -> None:
        env = _envelope(family="revolver_fallback_change")
        obs = [o for o in _full_observations("revolver_fallback_change") if o.requirement_id != "post_revolver_readback"]
        result = evaluate_provider_evidence(env, obs)
        assert result.verdict == VERDICT_BLOCKED

    def test_canary_family_requires_budget_quota_readback(self) -> None:
        env = _envelope(family="canary_budget_quota_change")
        obs = [o for o in _full_observations("canary_budget_quota_change") if o.requirement_id != "post_budget_quota_readback"]
        result = evaluate_provider_evidence(env, obs)
        assert result.verdict == VERDICT_BLOCKED
        assert "post_budget_quota_readback" in result.missing

    def test_paid_route_requires_price_budget_evidence(self) -> None:
        env = _envelope(family="openrouter_paid_route_change")
        obs = [o for o in _full_observations("openrouter_paid_route_change") if o.requirement_id != "pre_price_budget_evidence"]
        result = evaluate_provider_evidence(env, obs)
        assert result.verdict == VERDICT_BLOCKED
        assert "pre_price_budget_evidence" in result.missing


# ---------------------------------------------------------------------------
# evaluate_provider_evidence — CONTRADICTED paths
# ---------------------------------------------------------------------------

class TestEvaluateContradicted:
    def test_stale_revision_contradicted(self) -> None:
        env = _envelope()
        obs = [
            ProviderObservation(
                requirement_id="pre_revolver_order",
                value_hash=_SHA64_C,
                source="RUNTIME_READBACK",
                assertion="OBSERVED",
                bound_revision=_SHA40_B,  # stale
            )
            if o.requirement_id == "pre_revolver_order"
            else o
            for o in _full_observations("openrouter_paid_route_change")
        ]
        result = evaluate_provider_evidence(env, obs)
        assert result.verdict == VERDICT_CONTRADICTED
        assert "pre_revolver_order" in result.contradicted
        assert "observation_bound_to_stale_revision" in result.finding_codes

    def test_litellm_path_detected_contradicted(self) -> None:
        env = _envelope()
        obs = [
            ProviderObservation(
                requirement_id="post_no_litellm_path",
                value_hash=_SHA64_C,
                source="REPOSITORY_READBACK",
                assertion="CONTRADICTED",
                bound_revision=_SHA40_A,
            )
            if o.requirement_id == "post_no_litellm_path"
            else o
            for o in _full_observations("openrouter_paid_route_change")
        ]
        result = evaluate_provider_evidence(env, obs)
        assert result.verdict == VERDICT_CONTRADICTED
        assert "post_no_litellm_path" in result.contradicted
        assert "litellm_path_detected" in result.finding_codes

    def test_route_classification_contradiction(self) -> None:
        env = _envelope(family="free_keyless_route_change")
        obs = [
            ProviderObservation(
                requirement_id="pre_route_classification",
                value_hash=_SHA64_C,
                source="REPOSITORY_READBACK",
                assertion="CONTRADICTED",
                bound_revision=_SHA40_A,
            )
            if o.requirement_id == "pre_route_classification"
            else o
            for o in _full_observations("free_keyless_route_change")
        ]
        result = evaluate_provider_evidence(env, obs)
        assert result.verdict == VERDICT_CONTRADICTED
        assert "route_classification_contradiction" in result.finding_codes

    def test_contradicted_takes_priority_over_missing(self) -> None:
        env = _envelope()
        contradicted_obs = ProviderObservation(
            requirement_id="pre_revolver_order",
            value_hash=_SHA64_C,
            source="RUNTIME_READBACK",
            assertion="CONTRADICTED",
            bound_revision=_SHA40_A,
        )
        result = evaluate_provider_evidence(env, [contradicted_obs])
        assert result.verdict == VERDICT_CONTRADICTED


# ---------------------------------------------------------------------------
# Family-specific structural checks
# ---------------------------------------------------------------------------

class TestFamilyRequirements:
    def test_free_keyless_no_price_evidence_required(self) -> None:
        """Free-keyless family must NOT require pre_price_budget_evidence."""
        from agent_runtime.provider_routing_evidence_gate import _FAMILY_REQUIREMENTS
        reqs = _FAMILY_REQUIREMENTS["free_keyless_route_change"]
        assert "pre_price_budget_evidence" not in reqs

    def test_paid_route_requires_price_evidence(self) -> None:
        from agent_runtime.provider_routing_evidence_gate import _FAMILY_REQUIREMENTS
        reqs = _FAMILY_REQUIREMENTS["openrouter_paid_route_change"]
        assert "pre_price_budget_evidence" in reqs

    def test_all_families_require_post_no_litellm_path(self) -> None:
        from agent_runtime.provider_routing_evidence_gate import _FAMILY_REQUIREMENTS
        for family, reqs in _FAMILY_REQUIREMENTS.items():
            assert "post_no_litellm_path" in reqs, f"{family} missing post_no_litellm_path"

    def test_all_families_require_post_capability_delta(self) -> None:
        from agent_runtime.provider_routing_evidence_gate import _FAMILY_REQUIREMENTS
        for family, reqs in _FAMILY_REQUIREMENTS.items():
            assert "post_capability_delta" in reqs, f"{family} missing post_capability_delta"

    def test_provider_removal_requires_capability_replacement(self) -> None:
        from agent_runtime.provider_routing_evidence_gate import _FAMILY_REQUIREMENTS
        reqs = _FAMILY_REQUIREMENTS["provider_capability_removal"]
        assert "post_capability_replacement" in reqs


# ---------------------------------------------------------------------------
# audit_no_litellm_reintroduction
# ---------------------------------------------------------------------------

class TestAuditNoLitellmReintroduction:
    def test_clear_for_clean_files(self) -> None:
        audit = audit_no_litellm_reintroduction(
            changed_paths=["src/router.py"],
            path_contents={"src/router.py": "from openrouter import client\nclient.chat()"},
        )
        assert audit.clear is True
        assert audit.blocker is None

    def test_litellm_import_detected(self) -> None:
        audit = audit_no_litellm_reintroduction(
            changed_paths=["src/router.py"],
            path_contents={"src/router.py": "import litellm\nlitellm.completion(model='gpt-4')"},
        )
        assert audit.clear is False
        assert "src/router.py" in audit.matching_paths

    def test_from_litellm_import_detected(self) -> None:
        audit = audit_no_litellm_reintroduction(
            changed_paths=["backend/llm.py"],
            path_contents={"backend/llm.py": "from litellm import completion"},
        )
        assert audit.clear is False

    def test_litellm_completion_call_detected(self) -> None:
        audit = audit_no_litellm_reintroduction(
            changed_paths=["agent.py"],
            path_contents={"agent.py": "result = litellm.completion(model='claude-3')"},
        )
        assert audit.clear is False

    def test_litellm_acompletion_call_detected(self) -> None:
        audit = audit_no_litellm_reintroduction(
            changed_paths=["agent.py"],
            path_contents={"agent.py": "await litellm.acompletion(messages=[])"},
        )
        assert audit.clear is False

    def test_bare_litellm_word_detected(self) -> None:
        audit = audit_no_litellm_reintroduction(
            changed_paths=["config.py"],
            path_contents={"config.py": "# uses litellm for routing"},
        )
        assert audit.clear is False

    def test_path_not_in_contents_skipped(self) -> None:
        """A changed path with no entry in path_contents is skipped (not failed)."""
        audit = audit_no_litellm_reintroduction(
            changed_paths=["missing.py"],
            path_contents={},
        )
        assert audit.clear is True

    def test_multiple_matching_paths(self) -> None:
        audit = audit_no_litellm_reintroduction(
            changed_paths=["a.py", "b.py", "c.py"],
            path_contents={
                "a.py": "import litellm",
                "b.py": "clean code here",
                "c.py": "from litellm import acompletion",
            },
        )
        assert audit.clear is False
        assert len(audit.matching_paths) == 2
        assert "a.py" in audit.matching_paths
        assert "c.py" in audit.matching_paths

    def test_result_is_immutable(self) -> None:
        audit = audit_no_litellm_reintroduction([], {})
        with pytest.raises((AttributeError, TypeError)):
            audit.clear = False  # type: ignore[misc]
