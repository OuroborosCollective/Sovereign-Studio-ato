"""Tests for mcp_fleet_deployment_evidence_gate.py — Issue #1101.

Covers:
- Envelope validation (all seven families, required/optional fields)
- Observation validation (assertion values, digest normalization)
- evaluate_mcp_fleet_evidence — VERIFIED, CONTRADICTED, BLOCKED paths for each family
- Fail-closed invariants:
  - Stale revision → CONTRADICTED
  - Wrong digest on post_actual_running_digest / post_published_immutable_digest → CONTRADICTED
  - UNAVAILABLE / liveness-only observations → BLOCKED (not VERIFIED)
  - PatchMon readback without revision/digest binding → does not satisfy requirement
  - Partial fleet → BLOCKED via audit_patchmon_health_count
  - auto_merge_allowed is always False
- audit_patchmon_health_count (all four rejection reasons + accepted)
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent_runtime.mcp_fleet_deployment_evidence_gate import (
    OPERATION_FAMILIES,
    VERDICT_BLOCKED,
    VERDICT_CONTRADICTED,
    VERDICT_VERIFIED,
    McpFleetEvidenceEnvelope,
    McpFleetEvidenceResult,
    McpFleetObservation,
    PatchmonHealthAudit,
    audit_patchmon_health_count,
    evaluate_mcp_fleet_evidence,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SHA40_A = "a" * 40
_SHA40_B = "b" * 40
_SHA64_A = "a" * 64
_SHA64_B = "b" * 64
_SHA64_C = "c" * 64


def _sha256(value: Any) -> str:
    def _canonical(v: Any) -> Any:
        if v is None or isinstance(v, bool):
            return v
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            return {str(k): _canonical(val) for k, val in sorted(v.items())}
        if isinstance(v, (list, tuple)):
            return [_canonical(item) for item in v]
        raise TypeError(f"unsupported: {type(v)}")
    return hashlib.sha256(
        json.dumps(_canonical(value), separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def _envelope(
    family: str = "mcp_self_update",
    *,
    identity: str = "op.abc-001",
    repository: str = "owner/repo",
    base_revision: str = _SHA40_A,
    expected_image_digest: str = _SHA64_A,
    input_hash: str = _SHA64_B,
    declared_capability_families: tuple[str, ...] = ("mcp.tool.run",),
) -> McpFleetEvidenceEnvelope:
    return McpFleetEvidenceEnvelope(
        operation_family=family,
        operation_identity=identity,
        repository=repository,
        base_revision=base_revision,
        expected_image_digest=expected_image_digest,
        input_hash=input_hash,
        declared_capability_families=declared_capability_families,
    )


def _obs(
    requirement_id: str,
    *,
    value_hash: str = _SHA64_C,
    source: str = "MCP_READBACK",
    assertion: str = "OBSERVED",
    bound_revision: str = _SHA40_A,
    bound_digest: str = "",
) -> McpFleetObservation:
    return McpFleetObservation(
        requirement_id=requirement_id,
        value_hash=value_hash,
        source=source,
        assertion=assertion,
        bound_revision=bound_revision,
        bound_digest=bound_digest,
    )


def _full_observations(family: str) -> list[McpFleetObservation]:
    """Build a minimal set of OBSERVED observations that satisfies every requirement."""
    from agent_runtime.mcp_fleet_deployment_evidence_gate import _FAMILY_REQUIREMENTS

    observations = []
    for req_id in _FAMILY_REQUIREMENTS[family]:
        # post_patchmon_fleet_readback needs BOTH a revision and a digest
        # binding to match the audit_patchmon_health_count contract enforced
        # by evaluate_mcp_fleet_evidence. A one-sided binding is no longer
        # sufficient (Issue #1101 / PR #1184).
        bound_rev = _SHA40_A
        bound_digest = ""
        if req_id in (
            "post_published_immutable_digest",
            "post_actual_running_digest",
            "post_patchmon_fleet_readback",
        ):
            bound_digest = _SHA64_A  # matches envelope expected_image_digest
        observations.append(
            McpFleetObservation(
                requirement_id=req_id,
                value_hash=_SHA64_C,
                source="MCP_READBACK",
                assertion="OBSERVED",
                bound_revision=bound_rev,
                bound_digest=bound_digest,
                healthy_count=4 if req_id == "post_patchmon_fleet_readback" else 0,
                total_count=4 if req_id == "post_patchmon_fleet_readback" else 0,
                has_capability_canary=req_id == "post_patchmon_fleet_readback",
            )
        )
    return observations


# ---------------------------------------------------------------------------
# Envelope validation
# ---------------------------------------------------------------------------

class TestEnvelopeValidation:
    def test_all_seven_families_create_envelope(self) -> None:
        for family in OPERATION_FAMILIES:
            digest = "" if family == "mcp_registry_tool_install" else _SHA64_A
            env = _envelope(family=family, expected_image_digest=digest)
            assert env.operation_family == family

    def test_unknown_family_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown operation_family"):
            _envelope(family="not_a_family")

    def test_invalid_base_revision_raises(self) -> None:
        with pytest.raises(ValueError, match="SHA-40"):
            _envelope(base_revision="short")

    def test_invalid_input_hash_raises(self) -> None:
        with pytest.raises(ValueError, match="SHA-256"):
            _envelope(input_hash="not-a-hash")

    def test_invalid_operation_identity_raises(self) -> None:
        with pytest.raises(ValueError, match="operation_identity"):
            _envelope(identity="BAD IDENTITY!")

    def test_empty_declared_capabilities_raises(self) -> None:
        with pytest.raises(ValueError, match="declared_capability_families"):
            _envelope(declared_capability_families=())

    def test_missing_image_digest_raises_for_non_optional_family(self) -> None:
        with pytest.raises(ValueError, match="expected_image_digest"):
            _envelope(family="mcp_self_update", expected_image_digest="")

    def test_empty_digest_allowed_for_registry_tool_install(self) -> None:
        env = _envelope(family="mcp_registry_tool_install", expected_image_digest="")
        assert env.expected_image_digest == ""

    def test_sha256_prefix_normalized(self) -> None:
        env = _envelope(expected_image_digest=f"sha256:{_SHA64_A}")
        assert env.expected_image_digest == _SHA64_A

    def test_envelope_sha256_is_deterministic(self) -> None:
        env1 = _envelope()
        env2 = _envelope()
        assert env1.envelope_sha256 == env2.envelope_sha256

    def test_envelope_sha256_changes_with_family(self) -> None:
        env1 = _envelope(family="mcp_self_update")
        env2 = _envelope(family="mcp_broker_launcher_change")
        assert env1.envelope_sha256 != env2.envelope_sha256

    def test_envelope_is_immutable(self) -> None:
        env = _envelope()
        with pytest.raises((AttributeError, TypeError)):
            env.operation_family = "other"  # type: ignore[misc]

    def test_declared_capabilities_sorted(self) -> None:
        env = _envelope(declared_capability_families=("z.cap", "a.cap"))
        assert env.declared_capability_families == ("a.cap", "z.cap")


# ---------------------------------------------------------------------------
# Observation validation
# ---------------------------------------------------------------------------

class TestObservationValidation:
    def test_valid_observation(self) -> None:
        obs = _obs("pre_source_runtime_revision")
        assert obs.assertion == "OBSERVED"

    def test_invalid_assertion_raises(self) -> None:
        with pytest.raises(ValueError, match="unsupported assertion"):
            McpFleetObservation(
                requirement_id="x",
                value_hash=_SHA64_A,
                source="MCP_READBACK",
                assertion="RUNNING",
                bound_revision="",
                bound_digest="",
            )

    def test_invalid_value_hash_raises(self) -> None:
        with pytest.raises(ValueError, match="SHA-256"):
            _obs("pre_x", value_hash="short")

    def test_invalid_bound_revision_raises(self) -> None:
        with pytest.raises(ValueError, match="SHA-40"):
            _obs("pre_x", bound_revision="not-sha40")

    def test_sha256_prefix_normalized_in_bound_digest(self) -> None:
        obs = McpFleetObservation(
            requirement_id="post_actual_running_digest",
            value_hash=_SHA64_A,
            source="IMAGE_READBACK",
            assertion="OBSERVED",
            bound_revision=_SHA40_A,
            bound_digest=f"sha256:{_SHA64_A}",
        )
        assert obs.bound_digest == _SHA64_A

    def test_observation_sha256_deterministic(self) -> None:
        obs1 = _obs("req")
        obs2 = _obs("req")
        assert obs1.observation_sha256 == obs2.observation_sha256

    def test_observation_sha256_changes_with_assertion(self) -> None:
        obs1 = _obs("req", assertion="OBSERVED")
        obs2 = _obs("req", assertion="CONTRADICTED")
        assert obs1.observation_sha256 != obs2.observation_sha256

    def test_observation_is_immutable(self) -> None:
        obs = _obs("req")
        with pytest.raises((AttributeError, TypeError)):
            obs.assertion = "UNAVAILABLE"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# evaluate_mcp_fleet_evidence — happy path
# ---------------------------------------------------------------------------

class TestEvaluateVerified:
    @pytest.mark.parametrize("family", sorted(OPERATION_FAMILIES))
    def test_all_families_verified_with_full_observations(self, family: str) -> None:
        env = _envelope(
            family=family,
            expected_image_digest=_SHA64_A if family != "mcp_registry_tool_install" else "",
        )
        result = evaluate_mcp_fleet_evidence(env, _full_observations(family))
        assert result.verdict == VERDICT_VERIFIED, (
            f"{family}: missing={result.missing}, contradicted={result.contradicted}"
        )

    @pytest.mark.parametrize("family", sorted(OPERATION_FAMILIES))
    def test_auto_merge_always_false(self, family: str) -> None:
        env = _envelope(
            family=family,
            expected_image_digest=_SHA64_A if family != "mcp_registry_tool_install" else "",
        )
        result = evaluate_mcp_fleet_evidence(env, _full_observations(family))
        assert result.auto_merge_allowed is False

    def test_result_is_immutable(self) -> None:
        env = _envelope()
        result = evaluate_mcp_fleet_evidence(env, _full_observations("mcp_self_update"))
        with pytest.raises((AttributeError, TypeError)):
            result.verdict = "VERIFIED"  # type: ignore[misc]

    def test_envelope_sha256_propagated(self) -> None:
        env = _envelope()
        result = evaluate_mcp_fleet_evidence(env, _full_observations("mcp_self_update"))
        assert result.envelope_sha256 == env.envelope_sha256


# ---------------------------------------------------------------------------
# evaluate_mcp_fleet_evidence — BLOCKED paths
# ---------------------------------------------------------------------------

class TestEvaluateBlocked:
    def test_empty_observations_blocked(self) -> None:
        env = _envelope()
        result = evaluate_mcp_fleet_evidence(env, [])
        assert result.verdict == VERDICT_BLOCKED
        assert len(result.missing) > 0

    def test_single_missing_requirement_blocked(self) -> None:
        env = _envelope()
        obs = _full_observations("mcp_self_update")
        # Remove the last observation
        partial = obs[:-1]
        result = evaluate_mcp_fleet_evidence(env, partial)
        assert result.verdict == VERDICT_BLOCKED

    def test_unavailable_observation_does_not_satisfy(self) -> None:
        env = _envelope()
        obs = _full_observations("mcp_self_update")
        # Replace one OBSERVED with UNAVAILABLE
        replaced = [
            McpFleetObservation(
                requirement_id=o.requirement_id,
                value_hash=o.value_hash,
                source=o.source,
                assertion="UNAVAILABLE",
                bound_revision=o.bound_revision,
                bound_digest=o.bound_digest,
            )
            if o.requirement_id == "pre_source_runtime_revision"
            else o
            for o in obs
        ]
        result = evaluate_mcp_fleet_evidence(env, replaced)
        assert result.verdict == VERDICT_BLOCKED
        assert "pre_source_runtime_revision" in result.missing

    def test_patchmon_readback_without_revision_or_digest_does_not_satisfy(self) -> None:
        env = _envelope(family="patchmon_fleet_revision")
        obs = _full_observations("patchmon_fleet_revision")
        # Replace post_patchmon_fleet_readback with one having NO binding
        replaced = [
            McpFleetObservation(
                requirement_id="post_patchmon_fleet_readback",
                value_hash=_SHA64_C,
                source="PATCHMON_READBACK",
                assertion="OBSERVED",
                bound_revision="",   # no revision
                bound_digest="",     # no digest
            )
            if o.requirement_id == "post_patchmon_fleet_readback"
            else o
            for o in obs
        ]
        result = evaluate_mcp_fleet_evidence(env, replaced)
        assert result.verdict == VERDICT_BLOCKED
        assert "post_patchmon_fleet_readback" in result.missing
        assert "patchmon_health_count_lacks_revision_and_digest_binding" in result.finding_codes

    def test_patchmon_readback_revision_only_does_not_satisfy(self) -> None:
        # Issue #1101 / PR #1184 — audit_patchmon_health_count already requires
        # both revision and digest; the evaluator must agree, not return VERIFIED
        # for a one-sided binding. This test pins that contract.
        env = _envelope(family="patchmon_fleet_revision")
        obs = _full_observations("patchmon_fleet_revision")
        replaced = [
            McpFleetObservation(
                requirement_id="post_patchmon_fleet_readback",
                value_hash=_SHA64_C,
                source="PATCHMON_READBACK",
                assertion="OBSERVED",
                bound_revision=_SHA40_A,  # revision only
                bound_digest="",          # no digest
            )
            if o.requirement_id == "post_patchmon_fleet_readback"
            else o
            for o in obs
        ]
        result = evaluate_mcp_fleet_evidence(env, replaced)
        assert result.verdict == VERDICT_BLOCKED
        assert "post_patchmon_fleet_readback" in result.missing
        assert "patchmon_health_count_lacks_digest_binding" in result.finding_codes
        # The empty-binding finding must NOT mask the stronger both-binding
        # reason: the audit requires revision AND digest together.
        assert "patchmon_health_count_lacks_revision_and_digest_binding" not in result.finding_codes

    def test_patchmon_readback_digest_only_does_not_satisfy(self) -> None:
        # Symmetric case: a digest-only PatchMon readback must also be BLOCKED.
        env = _envelope(family="patchmon_fleet_revision")
        obs = _full_observations("patchmon_fleet_revision")
        replaced = [
            McpFleetObservation(
                requirement_id="post_patchmon_fleet_readback",
                value_hash=_SHA64_C,
                source="PATCHMON_READBACK",
                assertion="OBSERVED",
                bound_revision="",                # no revision
                bound_digest=f"sha256:{_SHA64_A}",  # digest only
            )
            if o.requirement_id == "post_patchmon_fleet_readback"
            else o
            for o in obs
        ]
        result = evaluate_mcp_fleet_evidence(env, replaced)
        assert result.verdict == VERDICT_BLOCKED
        assert "post_patchmon_fleet_readback" in result.missing
        assert "patchmon_health_count_lacks_revision_binding" in result.finding_codes

    def test_patchmon_readback_full_binding_satisfies(self) -> None:
        env = _envelope(family="patchmon_fleet_revision")
        result = evaluate_mcp_fleet_evidence(
            env, _full_observations("patchmon_fleet_revision")
        )
        assert result.verdict == VERDICT_VERIFIED
        assert "post_patchmon_fleet_readback" not in result.missing
        assert "patchmon_health_count_lacks_digest_binding" not in result.finding_codes
        assert "patchmon_health_count_lacks_revision_binding" not in result.finding_codes


    def test_patchmon_readback_without_capability_canary_does_not_satisfy(self) -> None:
        env = _envelope(family="patchmon_fleet_revision")
        obs = _full_observations("patchmon_fleet_revision")
        replaced = [
            McpFleetObservation(
                requirement_id=o.requirement_id,
                value_hash=o.value_hash,
                source=o.source,
                assertion=o.assertion,
                bound_revision=o.bound_revision,
                bound_digest=o.bound_digest,
                healthy_count=o.healthy_count,
                total_count=o.total_count,
                has_capability_canary=False,
            )
            if o.requirement_id == "post_patchmon_fleet_readback"
            else o
            for o in obs
        ]
        result = evaluate_mcp_fleet_evidence(env, replaced)
        assert result.verdict == VERDICT_BLOCKED
        assert "post_patchmon_fleet_readback" in result.missing
        assert "patchmon_health_count_lacks_capability_canary" in result.finding_codes

    def test_patchmon_readback_partial_fleet_does_not_satisfy(self) -> None:
        env = _envelope(family="patchmon_fleet_revision")
        obs = _full_observations("patchmon_fleet_revision")
        replaced = [
            McpFleetObservation(
                requirement_id=o.requirement_id,
                value_hash=o.value_hash,
                source=o.source,
                assertion=o.assertion,
                bound_revision=o.bound_revision,
                bound_digest=o.bound_digest,
                healthy_count=3,
                total_count=4,
                has_capability_canary=True,
            )
            if o.requirement_id == "post_patchmon_fleet_readback"
            else o
            for o in obs
        ]
        result = evaluate_mcp_fleet_evidence(env, replaced)
        assert result.verdict == VERDICT_BLOCKED
        assert "post_patchmon_fleet_readback" in result.missing
        assert "partial_fleet_reachable_not_verified" in result.finding_codes

    def test_missing_rollback_digest_blocked(self) -> None:
        # pre_rollback_digest is required for mcp_self_update; omitting it → BLOCKED
        env = _envelope(family="mcp_self_update")
        obs = [o for o in _full_observations("mcp_self_update") if o.requirement_id != "pre_rollback_digest"]
        result = evaluate_mcp_fleet_evidence(env, obs)
        assert result.verdict == VERDICT_BLOCKED
        assert "pre_rollback_digest" in result.missing

    def test_empty_bound_rollback_observation_blocked(self) -> None:
        # pre_rollback_digest present but bound_revision="" AND bound_digest=""
        # → no real prior image referenced → requirement remains unsatisfied.
        env = _envelope(family="mcp_self_update")
        obs = [
            o if o.requirement_id != "pre_rollback_digest"
            else McpFleetObservation(
                requirement_id="pre_rollback_digest",
                value_hash=_SHA64_C,
                source="IMAGE_READBACK",
                assertion="OBSERVED",
                bound_revision="",   # no revision binding
                bound_digest="",     # no digest binding
            )
            for o in _full_observations("mcp_self_update")
        ]
        result = evaluate_mcp_fleet_evidence(env, obs)
        assert result.verdict == VERDICT_BLOCKED
        assert "pre_rollback_digest" in result.missing
        assert "rollback_reference_lacks_revision_or_digest_binding" in result.finding_codes

    def test_rollback_observation_bound_only_by_revision_satisfies(self) -> None:
        # pre_rollback_digest bound to base_revision only → no mismatch, satisfies.
        env = _envelope(family="mcp_self_update")
        obs = [
            o if o.requirement_id != "pre_rollback_digest"
            else McpFleetObservation(
                requirement_id="pre_rollback_digest",
                value_hash=_SHA64_C,
                source="IMAGE_READBACK",
                assertion="OBSERVED",
                bound_revision=_SHA40_A,
                bound_digest="",
            )
            for o in _full_observations("mcp_self_update")
        ]
        result = evaluate_mcp_fleet_evidence(env, obs)
        assert result.verdict == VERDICT_VERIFIED
        assert "pre_rollback_digest" in result.satisfied
        assert "rollback_reference_lacks_revision_or_digest_binding" not in result.finding_codes

    def test_rollback_observation_bound_only_by_digest_satisfies(self) -> None:
        # pre_rollback_digest bound by digest only → no mismatch, satisfies.
        env = _envelope(family="mcp_self_update")
        obs = [
            o if o.requirement_id != "pre_rollback_digest"
            else McpFleetObservation(
                requirement_id="pre_rollback_digest",
                value_hash=_SHA64_C,
                source="IMAGE_READBACK",
                assertion="OBSERVED",
                bound_revision="",
                bound_digest=_SHA64_A,
            )
            for o in _full_observations("mcp_self_update")
        ]
        result = evaluate_mcp_fleet_evidence(env, obs)
        assert result.verdict == VERDICT_VERIFIED
        assert "pre_rollback_digest" in result.satisfied
        assert "rollback_reference_lacks_revision_or_digest_binding" not in result.finding_codes


# ---------------------------------------------------------------------------
# evaluate_mcp_fleet_evidence — CONTRADICTED paths
# ---------------------------------------------------------------------------

class TestEvaluateContradicted:
    def test_stale_revision_contradicted(self) -> None:
        env = _envelope()
        obs = _full_observations("mcp_self_update")
        # Replace one observation with a stale bound_revision
        replaced = [
            McpFleetObservation(
                requirement_id=o.requirement_id,
                value_hash=o.value_hash,
                source=o.source,
                assertion="OBSERVED",
                bound_revision=_SHA40_B,  # different from envelope.base_revision (_SHA40_A)
                bound_digest=o.bound_digest,
            )
            if o.requirement_id == "pre_source_runtime_revision"
            else o
            for o in obs
        ]
        result = evaluate_mcp_fleet_evidence(env, replaced)
        assert result.verdict == VERDICT_CONTRADICTED
        assert "pre_source_runtime_revision" in result.contradicted
        assert "observation_bound_to_stale_revision" in result.finding_codes

    def test_wrong_digest_on_post_actual_running_digest_contradicted(self) -> None:
        env = _envelope(expected_image_digest=_SHA64_A)
        obs = _full_observations("mcp_self_update")
        replaced = [
            McpFleetObservation(
                requirement_id="post_actual_running_digest",
                value_hash=_SHA64_C,
                source="IMAGE_READBACK",
                assertion="OBSERVED",
                bound_revision=_SHA40_A,
                bound_digest=_SHA64_B,  # wrong — expected _SHA64_A
            )
            if o.requirement_id == "post_actual_running_digest"
            else o
            for o in obs
        ]
        result = evaluate_mcp_fleet_evidence(env, replaced)
        assert result.verdict == VERDICT_CONTRADICTED
        assert "post_actual_running_digest" in result.contradicted
        assert "observation_digest_contradicts_expected_image" in result.finding_codes

    def test_wrong_digest_on_post_published_immutable_digest_contradicted(self) -> None:
        env = _envelope(expected_image_digest=_SHA64_A)
        obs = _full_observations("mcp_self_update")
        replaced = [
            McpFleetObservation(
                requirement_id="post_published_immutable_digest",
                value_hash=_SHA64_C,
                source="IMAGE_READBACK",
                assertion="OBSERVED",
                bound_revision=_SHA40_A,
                bound_digest=_SHA64_B,  # wrong
            )
            if o.requirement_id == "post_published_immutable_digest"
            else o
            for o in obs
        ]
        result = evaluate_mcp_fleet_evidence(env, replaced)
        assert result.verdict == VERDICT_CONTRADICTED
        assert "post_published_immutable_digest" in result.contradicted

    def test_explicit_contradicted_assertion(self) -> None:
        env = _envelope()
        obs = _full_observations("mcp_self_update")
        replaced = [
            McpFleetObservation(
                requirement_id="pre_running_image_digest",
                value_hash=_SHA64_C,
                source="IMAGE_READBACK",
                assertion="CONTRADICTED",
                bound_revision=_SHA40_A,
                bound_digest="",
            )
            if o.requirement_id == "pre_running_image_digest"
            else o
            for o in obs
        ]
        result = evaluate_mcp_fleet_evidence(env, replaced)
        assert result.verdict == VERDICT_CONTRADICTED
        assert "observation_reports_contradiction" in result.finding_codes

    def test_contradicted_takes_priority_over_missing(self) -> None:
        # Provide only one contradicted observation and zero others
        env = _envelope(family="mcp_self_update")
        contradicted_obs = McpFleetObservation(
            requirement_id="pre_source_runtime_revision",
            value_hash=_SHA64_C,
            source="MCP_READBACK",
            assertion="CONTRADICTED",
            bound_revision=_SHA40_A,
            bound_digest="",
        )
        result = evaluate_mcp_fleet_evidence(env, [contradicted_obs])
        assert result.verdict == VERDICT_CONTRADICTED


# ---------------------------------------------------------------------------
# Family-specific structural checks
# ---------------------------------------------------------------------------

class TestFamilyRequirements:
    def test_mcp_self_update_requires_pre_broker_registry_status(self) -> None:
        env = _envelope(family="mcp_self_update")
        obs = [o for o in _full_observations("mcp_self_update") if o.requirement_id != "pre_broker_registry_status"]
        result = evaluate_mcp_fleet_evidence(env, obs)
        assert result.verdict == VERDICT_BLOCKED
        assert "pre_broker_registry_status" in result.missing

    def test_mcp_self_update_requires_post_mcp_initialize_canary(self) -> None:
        env = _envelope(family="mcp_self_update")
        obs = [o for o in _full_observations("mcp_self_update") if o.requirement_id != "post_mcp_initialize_canary"]
        result = evaluate_mcp_fleet_evidence(env, obs)
        assert result.verdict == VERDICT_BLOCKED
        assert "post_mcp_initialize_canary" in result.missing

    def test_vps_deployment_requires_patchmon_fleet_readback(self) -> None:
        env = _envelope(family="vps_deployment_restart_rollback")
        obs = [o for o in _full_observations("vps_deployment_restart_rollback") if o.requirement_id != "post_patchmon_fleet_readback"]
        result = evaluate_mcp_fleet_evidence(env, obs)
        assert result.verdict == VERDICT_BLOCKED
        assert "post_patchmon_fleet_readback" in result.missing

    def test_patchmon_fleet_revision_requires_post_capability_delta(self) -> None:
        env = _envelope(family="patchmon_fleet_revision")
        obs = [o for o in _full_observations("patchmon_fleet_revision") if o.requirement_id != "post_capability_delta"]
        result = evaluate_mcp_fleet_evidence(env, obs)
        assert result.verdict == VERDICT_BLOCKED
        assert "post_capability_delta" in result.missing

    def test_docker_compose_requires_pre_container_generation(self) -> None:
        env = _envelope(family="docker_compose_container_change")
        obs = [o for o in _full_observations("docker_compose_container_change") if o.requirement_id != "pre_container_generation"]
        result = evaluate_mcp_fleet_evidence(env, obs)
        assert result.verdict == VERDICT_BLOCKED
        assert "pre_container_generation" in result.missing

    def test_registry_tool_install_verified_without_image_digest(self) -> None:
        env = _envelope(family="mcp_registry_tool_install", expected_image_digest="")
        result = evaluate_mcp_fleet_evidence(env, _full_observations("mcp_registry_tool_install"))
        assert result.verdict == VERDICT_VERIFIED

    def test_host_patch_requires_post_restart_rollback_readback(self) -> None:
        env = _envelope(family="host_patch_sovereign_runtime")
        obs = [o for o in _full_observations("host_patch_sovereign_runtime") if o.requirement_id != "post_restart_rollback_readback"]
        result = evaluate_mcp_fleet_evidence(env, obs)
        assert result.verdict == VERDICT_BLOCKED
        assert "post_restart_rollback_readback" in result.missing


# ---------------------------------------------------------------------------
# audit_patchmon_health_count
# ---------------------------------------------------------------------------

class TestAuditPatchmonHealthCount:
    def test_accepted_full_fleet_with_revision_and_digest(self) -> None:
        # Issue #1101 / PR #1184 — both bindings required for VERIFIED.
        audit = audit_patchmon_health_count(
            healthy_count=4,
            total_count=4,
            bound_revision=_SHA40_A,
            bound_digest=f"sha256:{_SHA64_A}",
            has_capability_canary=True,
        )
        assert audit.accepted is True
        assert audit.blocker is None
        assert audit.has_revision_binding is True
        assert audit.has_digest_binding is True
        assert audit.has_capability_canary is True

    def test_revision_only_blocked_for_missing_digest(self) -> None:
        # Revision-only is no longer sufficient (Issue #1101 / PR #1184).
        audit = audit_patchmon_health_count(
            healthy_count=4,
            total_count=4,
            bound_revision=_SHA40_A,
            bound_digest="",
            has_capability_canary=True,
        )
        assert audit.accepted is False
        assert audit.blocker == "patchmon_health_count_lacks_digest_binding"
        assert audit.has_revision_binding is True
        assert audit.has_digest_binding is False

    def test_digest_only_blocked_for_missing_revision(self) -> None:
        # Digest-only is no longer sufficient (Issue #1101 / PR #1184).
        audit = audit_patchmon_health_count(
            healthy_count=3,
            total_count=3,
            bound_revision="",
            bound_digest=f"sha256:{_SHA64_A}",
            has_capability_canary=True,
        )
        assert audit.accepted is False
        assert audit.blocker == "patchmon_health_count_lacks_revision_binding"
        assert audit.has_revision_binding is False
        assert audit.has_digest_binding is True

    def test_partial_fleet_blocked(self) -> None:
        audit = audit_patchmon_health_count(
            healthy_count=3,
            total_count=4,
            bound_revision=_SHA40_A,
            bound_digest=f"sha256:{_SHA64_A}",
            has_capability_canary=True,
        )
        assert audit.accepted is False
        assert audit.blocker == "partial_fleet_reachable_not_verified"

    def test_no_revision_no_digest_blocked(self) -> None:
        audit = audit_patchmon_health_count(
            healthy_count=4,
            total_count=4,
            bound_revision="",
            bound_digest="",
            has_capability_canary=True,
        )
        assert audit.accepted is False
        assert audit.blocker == "patchmon_health_count_lacks_revision_and_digest_binding"

    def test_missing_capability_canary_blocked(self) -> None:
        # Both bindings present so we reach the canary check.
        audit = audit_patchmon_health_count(
            healthy_count=4,
            total_count=4,
            bound_revision=_SHA40_A,
            bound_digest=f"sha256:{_SHA64_A}",
            has_capability_canary=False,
        )
        assert audit.accepted is False
        assert audit.blocker == "patchmon_health_count_lacks_capability_canary"

    def test_partial_fleet_takes_priority_over_missing_canary(self) -> None:
        # Partial fleet is checked first
        audit = audit_patchmon_health_count(
            healthy_count=2,
            total_count=4,
            bound_revision=_SHA40_A,
            bound_digest=f"sha256:{_SHA64_A}",
            has_capability_canary=False,
        )
        assert audit.blocker == "partial_fleet_reachable_not_verified"

    def test_partial_fleet_takes_priority_over_missing_binding(self) -> None:
        # Partial fleet is checked first even when bindings are absent.
        audit = audit_patchmon_health_count(
            healthy_count=2,
            total_count=4,
            bound_revision="",
            bound_digest="",
            has_capability_canary=False,
        )
        assert audit.blocker == "partial_fleet_reachable_not_verified"

    def test_health_counts_recorded_correctly(self) -> None:
        audit = audit_patchmon_health_count(
            healthy_count=4,
            total_count=4,
            bound_revision=_SHA40_A,
            bound_digest=f"sha256:{_SHA64_A}",
            has_capability_canary=True,
        )
        assert audit.healthy_count == 4
        assert audit.total_count == 4
        assert audit.has_revision_binding is True
        assert audit.has_digest_binding is True
        assert audit.has_capability_canary is True

    def test_audit_result_is_immutable(self) -> None:
        audit = audit_patchmon_health_count(
            healthy_count=4,
            total_count=4,
            bound_revision=_SHA40_A,
            bound_digest=f"sha256:{_SHA64_A}",
            has_capability_canary=True,
        )
        with pytest.raises((AttributeError, TypeError)):
            audit.accepted = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# evaluate_mcp_fleet_evidence — expected_current_revision freshness gate
# ---------------------------------------------------------------------------

class TestCurrentRevisionGate:
    """Issue #1101 / PR #1184 — fail-closed envelope revision freshness.

    When the caller passes ``expected_current_revision`` (the live main HEAD),
    the envelope's ``base_revision`` MUST match it. A stale envelope cannot
    masquerade as evidence for the running fleet.
    """

    def test_matching_current_revision_keeps_verified(self) -> None:
        for family in OPERATION_FAMILIES:
            env = _envelope(family=family)
            result = evaluate_mcp_fleet_evidence(
                env,
                _full_observations(family),
                expected_current_revision=env.base_revision,
            )
            assert result.verdict == VERDICT_VERIFIED, family

    def test_stale_envelope_revision_blocked(self) -> None:
        env = _envelope(family="mcp_self_update")
        # A SHA-40 that is NOT the envelope's base_revision.
        stale_sha = "f" * 40
        result = evaluate_mcp_fleet_evidence(
            env,
            _full_observations("mcp_self_update"),
            expected_current_revision=stale_sha,
        )
        assert result.verdict == VERDICT_BLOCKED
        assert "envelope_revision_stale_against_current_main" in result.finding_codes
        assert "expected_current_revision_mismatch" in result.finding_codes
        assert result.auto_merge_allowed is False

    def test_stale_envelope_blocked_even_for_blocked_family(self) -> None:
        # If the family itself has missing observations, the freshness gate
        # still takes priority — a stale envelope is BLOCKED before we ever
        # look at evidence.
        env = _envelope(family="mcp_self_update")
        stale_sha = "0" * 40
        result = evaluate_mcp_fleet_evidence(
            env,
            [],  # no observations at all
            expected_current_revision=stale_sha,
        )
        assert result.verdict == VERDICT_BLOCKED
        assert "envelope_revision_stale_against_current_main" in result.finding_codes

    def test_empty_expected_current_revision_disables_check(self) -> None:
        # Default behaviour: no caller-supplied current revision → no extra
        # check beyond the per-requirement evaluation.
        env = _envelope(family="mcp_self_update")
        result = evaluate_mcp_fleet_evidence(
            env,
            _full_observations("mcp_self_update"),
            expected_current_revision="",
        )
        assert result.verdict == VERDICT_VERIFIED

    def test_invalid_expected_current_revision_raises(self) -> None:
        env = _envelope(family="mcp_self_update")
        with pytest.raises(ValueError):
            evaluate_mcp_fleet_evidence(
                env,
                _full_observations("mcp_self_update"),
                expected_current_revision="not-a-sha-40",
            )

    def test_short_sha40_expected_current_revision_raises(self) -> None:
        env = _envelope(family="mcp_self_update")
        with pytest.raises(ValueError):
            evaluate_mcp_fleet_evidence(
                env,
                _full_observations("mcp_self_update"),
                expected_current_revision="a" * 39,
            )

    def test_matching_is_case_insensitive_on_hex(self) -> None:
        env = _envelope(family="mcp_self_update")
        # Envelope stores base_revision lowercased; uppercase hex must match.
        result = evaluate_mcp_fleet_evidence(
            env,
            _full_observations("mcp_self_update"),
            expected_current_revision=env.base_revision.upper(),
        )
        assert result.verdict == VERDICT_VERIFIED

    def test_default_kwarg_does_not_break_existing_callers(self) -> None:
        # Backwards compatibility: callers that do not pass the kwarg still
        # get exactly the same verdict they got before.
        env = _envelope(family="mcp_self_update")
        result_new = evaluate_mcp_fleet_evidence(env, _full_observations("mcp_self_update"))
        # No kwargs → expected_current_revision defaults to "" → no check.
        assert result_new.verdict == VERDICT_VERIFIED
        assert "envelope_revision_stale_against_current_main" not in result_new.finding_codes
