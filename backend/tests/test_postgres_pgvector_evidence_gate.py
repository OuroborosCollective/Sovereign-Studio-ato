"""Tests for postgres_pgvector_evidence_gate.py — Issue #1102 (DB half).

Covers:
- Envelope validation (all five families, required fields, Areloria-Wasd fence)
- Observation validation (assertion values, revision binding)
- evaluate_postgres_evidence — VERIFIED, CONTRADICTED, BLOCKED for each family
- Fail-closed invariants:
  - Stale revision → CONTRADICTED
  - UNAVAILABLE → requirement unsatisfied (BLOCKED)
  - Areloria-Wasd overlap in pre_no_areloria_wasd_overlap → CONTRADICTED +
    finding_code areloria_wasd_overlap_detected
  - Contradicted takes priority over missing
  - post_constraint_index_readback UNAVAILABLE → BLOCKED (not VERIFIED)
  - auto_merge_allowed is always False
- audit_areloria_wasd_fence (clear + each overlap pattern)
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent_runtime.postgres_pgvector_evidence_gate import (
    OPERATION_FAMILIES,
    VERDICT_BLOCKED,
    VERDICT_CONTRADICTED,
    VERDICT_VERIFIED,
    AraeloriaWasdFenceAudit,
    PostgresEvidenceEnvelope,
    PostgresEvidenceResult,
    PostgresObservation,
    audit_areloria_wasd_fence,
    evaluate_postgres_evidence,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SHA40_A = "a" * 40
_SHA40_B = "b" * 40
_SHA64_A = "a" * 64
_SHA64_B = "b" * 64
_SHA64_C = "c" * 64


def _envelope(
    family: str = "postgres_schema_migration",
    *,
    identity: str = "mig.abc-001",
    repository: str = "owner/repo",
    base_revision: str = _SHA40_A,
    migration_hash: str = _SHA64_A,
    schema_inventory_hash: str = _SHA64_B,
    declared_tables: tuple[str, ...] = ("users",),
    areloria_wasd_excluded: bool = True,
) -> PostgresEvidenceEnvelope:
    return PostgresEvidenceEnvelope(
        operation_family=family,
        operation_identity=identity,
        repository=repository,
        base_revision=base_revision,
        migration_hash=migration_hash,
        schema_inventory_hash=schema_inventory_hash,
        declared_tables=declared_tables,
        areloria_wasd_excluded=areloria_wasd_excluded,
    )


def _obs(
    requirement_id: str,
    *,
    value_hash: str = _SHA64_C,
    source: str = "DATABASE_READBACK",
    assertion: str = "OBSERVED",
    bound_revision: str = _SHA40_A,
) -> PostgresObservation:
    return PostgresObservation(
        requirement_id=requirement_id,
        value_hash=value_hash,
        source=source,
        assertion=assertion,
        bound_revision=bound_revision,
    )


def _full_observations(family: str) -> list[PostgresObservation]:
    from agent_runtime.postgres_pgvector_evidence_gate import _FAMILY_REQUIREMENTS
    return [
        PostgresObservation(
            requirement_id=req_id,
            value_hash=_SHA64_C,
            source="DATABASE_READBACK",
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

    def test_invalid_migration_hash_raises(self) -> None:
        with pytest.raises(ValueError, match="SHA-256"):
            _envelope(migration_hash="bad")

    def test_invalid_schema_inventory_hash_raises(self) -> None:
        with pytest.raises(ValueError, match="SHA-256"):
            _envelope(schema_inventory_hash="bad")

    def test_invalid_operation_identity_raises(self) -> None:
        with pytest.raises(ValueError, match="operation_identity"):
            _envelope(identity="INVALID IDENTITY!")

    def test_empty_declared_tables_raises(self) -> None:
        with pytest.raises(ValueError, match="declared_tables"):
            _envelope(declared_tables=())

    def test_areloria_wasd_excluded_false_raises(self) -> None:
        with pytest.raises(ValueError, match="areloria_wasd_excluded"):
            _envelope(areloria_wasd_excluded=False)

    def test_envelope_sha256_is_deterministic(self) -> None:
        env1 = _envelope()
        env2 = _envelope()
        assert env1.envelope_sha256 == env2.envelope_sha256

    def test_envelope_sha256_changes_with_family(self) -> None:
        env1 = _envelope(family="postgres_schema_migration")
        env2 = _envelope(family="pgvector_extension_change")
        assert env1.envelope_sha256 != env2.envelope_sha256

    def test_envelope_is_immutable(self) -> None:
        env = _envelope()
        with pytest.raises((AttributeError, TypeError)):
            env.operation_family = "other"  # type: ignore[misc]

    def test_declared_tables_sorted(self) -> None:
        env = _envelope(declared_tables=("zzz_table", "aaa_table"))
        assert env.declared_tables == ("aaa_table", "zzz_table")


# ---------------------------------------------------------------------------
# Observation validation
# ---------------------------------------------------------------------------

class TestObservationValidation:
    def test_valid_observation(self) -> None:
        obs = _obs("pre_migration_identity")
        assert obs.assertion == "OBSERVED"

    def test_invalid_assertion_raises(self) -> None:
        with pytest.raises(ValueError, match="unsupported assertion"):
            PostgresObservation(
                requirement_id="x",
                value_hash=_SHA64_A,
                source="DATABASE_READBACK",
                assertion="EXIT_CODE_ZERO",
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

    def test_observation_sha256_changes_with_assertion(self) -> None:
        obs1 = _obs("req", assertion="OBSERVED")
        obs2 = _obs("req", assertion="CONTRADICTED")
        assert obs1.observation_sha256 != obs2.observation_sha256

    def test_observation_is_immutable(self) -> None:
        obs = _obs("req")
        with pytest.raises((AttributeError, TypeError)):
            obs.assertion = "UNAVAILABLE"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# evaluate_postgres_evidence — happy path
# ---------------------------------------------------------------------------

class TestEvaluateVerified:
    @pytest.mark.parametrize("family", sorted(OPERATION_FAMILIES))
    def test_all_families_verified_with_full_observations(self, family: str) -> None:
        env = _envelope(family=family)
        result = evaluate_postgres_evidence(env, _full_observations(family))
        assert result.verdict == VERDICT_VERIFIED, (
            f"{family}: missing={result.missing}, contradicted={result.contradicted}"
        )

    @pytest.mark.parametrize("family", sorted(OPERATION_FAMILIES))
    def test_auto_merge_always_false(self, family: str) -> None:
        env = _envelope(family=family)
        result = evaluate_postgres_evidence(env, _full_observations(family))
        assert result.auto_merge_allowed is False

    def test_result_is_immutable(self) -> None:
        env = _envelope()
        result = evaluate_postgres_evidence(env, _full_observations("postgres_schema_migration"))
        with pytest.raises((AttributeError, TypeError)):
            result.verdict = "VERIFIED"  # type: ignore[misc]

    def test_envelope_sha256_propagated(self) -> None:
        env = _envelope()
        result = evaluate_postgres_evidence(env, _full_observations("postgres_schema_migration"))
        assert result.envelope_sha256 == env.envelope_sha256


# ---------------------------------------------------------------------------
# evaluate_postgres_evidence — BLOCKED paths
# ---------------------------------------------------------------------------

class TestEvaluateBlocked:
    def test_empty_observations_blocked(self) -> None:
        env = _envelope()
        result = evaluate_postgres_evidence(env, [])
        assert result.verdict == VERDICT_BLOCKED
        assert len(result.missing) > 0

    def test_single_missing_requirement_blocked(self) -> None:
        env = _envelope(family="postgres_schema_migration")
        obs = [o for o in _full_observations("postgres_schema_migration") if o.requirement_id != "post_rollback_reference"]
        result = evaluate_postgres_evidence(env, obs)
        assert result.verdict == VERDICT_BLOCKED
        assert "post_rollback_reference" in result.missing

    def test_unavailable_post_constraint_index_readback_blocked(self) -> None:
        """An existing table without verified constraints/indexes is not full success."""
        env = _envelope(family="postgres_schema_migration")
        obs = [
            PostgresObservation(
                requirement_id="post_constraint_index_readback",
                value_hash=_SHA64_C,
                source="DATABASE_READBACK",
                assertion="UNAVAILABLE",
                bound_revision=_SHA40_A,
            )
            if o.requirement_id == "post_constraint_index_readback"
            else o
            for o in _full_observations("postgres_schema_migration")
        ]
        result = evaluate_postgres_evidence(env, obs)
        assert result.verdict == VERDICT_BLOCKED
        assert "post_constraint_index_readback" in result.missing

    def test_unavailable_rollback_reference_blocked(self) -> None:
        env = _envelope(family="postgres_data_migration")
        obs = [
            PostgresObservation(
                requirement_id="post_rollback_reference",
                value_hash=_SHA64_C,
                source="DATABASE_READBACK",
                assertion="UNAVAILABLE",
                bound_revision=_SHA40_A,
            )
            if o.requirement_id == "post_rollback_reference"
            else o
            for o in _full_observations("postgres_data_migration")
        ]
        result = evaluate_postgres_evidence(env, obs)
        assert result.verdict == VERDICT_BLOCKED
        assert "post_rollback_reference" in result.missing

    def test_pgvector_family_requires_post_pgvector_canary(self) -> None:
        env = _envelope(family="pgvector_extension_change")
        obs = [o for o in _full_observations("pgvector_extension_change") if o.requirement_id != "post_pgvector_canary"]
        result = evaluate_postgres_evidence(env, obs)
        assert result.verdict == VERDICT_BLOCKED
        assert "post_pgvector_canary" in result.missing

    def test_data_migration_requires_row_count_observations(self) -> None:
        env = _envelope(family="postgres_data_migration")
        obs = [o for o in _full_observations("postgres_data_migration") if o.requirement_id not in ("pre_row_count_baseline", "post_row_count_readback")]
        result = evaluate_postgres_evidence(env, obs)
        assert result.verdict == VERDICT_BLOCKED
        assert "pre_row_count_baseline" in result.missing
        assert "post_row_count_readback" in result.missing


# ---------------------------------------------------------------------------
# evaluate_postgres_evidence — CONTRADICTED paths
# ---------------------------------------------------------------------------

class TestEvaluateContradicted:
    def test_stale_revision_contradicted(self) -> None:
        env = _envelope()
        obs = [
            PostgresObservation(
                requirement_id="pre_migration_identity",
                value_hash=_SHA64_C,
                source="REPOSITORY_READBACK",
                assertion="OBSERVED",
                bound_revision=_SHA40_B,  # stale
            )
            if o.requirement_id == "pre_migration_identity"
            else o
            for o in _full_observations("postgres_schema_migration")
        ]
        result = evaluate_postgres_evidence(env, obs)
        assert result.verdict == VERDICT_CONTRADICTED
        assert "pre_migration_identity" in result.contradicted
        assert "observation_bound_to_stale_revision" in result.finding_codes

    def test_areloria_wasd_overlap_contradicted(self) -> None:
        env = _envelope()
        obs = [
            PostgresObservation(
                requirement_id="pre_no_areloria_wasd_overlap",
                value_hash=_SHA64_C,
                source="REPOSITORY_READBACK",
                assertion="CONTRADICTED",
                bound_revision=_SHA40_A,
            )
            if o.requirement_id == "pre_no_areloria_wasd_overlap"
            else o
            for o in _full_observations("postgres_schema_migration")
        ]
        result = evaluate_postgres_evidence(env, obs)
        assert result.verdict == VERDICT_CONTRADICTED
        assert "pre_no_areloria_wasd_overlap" in result.contradicted
        assert "areloria_wasd_overlap_detected" in result.finding_codes

    def test_explicit_contradicted_assertion(self) -> None:
        env = _envelope()
        obs = [
            PostgresObservation(
                requirement_id="pre_schema_inventory",
                value_hash=_SHA64_C,
                source="DATABASE_READBACK",
                assertion="CONTRADICTED",
                bound_revision=_SHA40_A,
            )
            if o.requirement_id == "pre_schema_inventory"
            else o
            for o in _full_observations("postgres_schema_migration")
        ]
        result = evaluate_postgres_evidence(env, obs)
        assert result.verdict == VERDICT_CONTRADICTED

    def test_contradicted_takes_priority_over_missing(self) -> None:
        env = _envelope()
        contradicted_obs = PostgresObservation(
            requirement_id="pre_migration_identity",
            value_hash=_SHA64_C,
            source="DATABASE_READBACK",
            assertion="CONTRADICTED",
            bound_revision=_SHA40_A,
        )
        result = evaluate_postgres_evidence(env, [contradicted_obs])
        assert result.verdict == VERDICT_CONTRADICTED

    def test_backup_restore_requires_post_restore_readback(self) -> None:
        env = _envelope(family="postgres_backup_restore_rollback")
        obs = [o for o in _full_observations("postgres_backup_restore_rollback") if o.requirement_id != "post_restore_readback"]
        result = evaluate_postgres_evidence(env, obs)
        assert result.verdict == VERDICT_BLOCKED
        assert "post_restore_readback" in result.missing


# ---------------------------------------------------------------------------
# audit_areloria_wasd_fence
# ---------------------------------------------------------------------------

class TestAuditAraeloriaWasdFence:
    def test_clear_for_sovereign_tables(self) -> None:
        audit = audit_areloria_wasd_fence(["users", "jobs", "agent_runs", "proof_envelopes"])
        assert audit.clear is True
        assert audit.blocker is None
        assert audit.overlap_tables == ()

    def test_areloria_in_name_blocked(self) -> None:
        audit = audit_areloria_wasd_fence(["areloria_characters"])
        assert audit.clear is False
        assert "areloria_characters" in audit.overlap_tables

    def test_wasd_in_name_blocked(self) -> None:
        audit = audit_areloria_wasd_fence(["wasd_game_state"])
        assert audit.clear is False

    def test_mmorpg_in_name_blocked(self) -> None:
        audit = audit_areloria_wasd_fence(["mmorpg_world_map"])
        assert audit.clear is False

    def test_player_char_prefix_blocked(self) -> None:
        audit = audit_areloria_wasd_fence(["player_characters"])
        assert audit.clear is False

    def test_quest_prefix_blocked(self) -> None:
        audit = audit_areloria_wasd_fence(["quest_log"])
        assert audit.clear is False

    def test_guild_prefix_blocked(self) -> None:
        audit = audit_areloria_wasd_fence(["guild_members"])
        assert audit.clear is False

    def test_multiple_overlapping_tables(self) -> None:
        audit = audit_areloria_wasd_fence(["quest_log", "users", "guild_bank"])
        assert audit.clear is False
        assert len(audit.overlap_tables) == 2
        assert "quest_log" in audit.overlap_tables
        assert "guild_bank" in audit.overlap_tables

    def test_result_is_immutable(self) -> None:
        audit = audit_areloria_wasd_fence(["users"])
        with pytest.raises((AttributeError, TypeError)):
            audit.clear = False  # type: ignore[misc]
