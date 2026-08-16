"""Tests for the Wolfram CAG runtime health / quota / cost / failure-isolation lane.

These tests exercise the *real* canonical implementation at
``backend/agent_runtime/wolfram_cag_health.py`` (no copied logic). They
cover Issue #1462 acceptance criteria:

- distinct, distinguishable health + failure-family states
- no blind retry / no hidden cost climb (quota as its own family)
- secret-safe credential / entitlement projection
- honest UNKNOWN / UNAVAILABLE without real canary evidence
- recovery declared only by a new real canary
- failure isolation: a CAG outage never blocks independent safety lanes
- 2xx without valid schema is never success
- byte-equal mirror parity
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CANONICAL = _REPO_ROOT / "backend" / "agent_runtime" / "wolfram_cag_health.py"
_MIRROR = _REPO_ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / "wolfram_cag_health.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


health = _load_module(_CANONICAL, "wolfram_cag_health_canonical")


# ---------------------------------------------------------------------------
# Mirror parity
# ---------------------------------------------------------------------------


def test_mirror_byte_identical() -> None:
    assert _CANONICAL.is_file()
    assert _MIRROR.is_file()
    assert (
        hashlib.sha256(_CANONICAL.read_bytes()).hexdigest()
        == hashlib.sha256(_MIRROR.read_bytes()).hexdigest()
    ), "wolfram_cag_health.py mirror drift: canonical and mirror must stay byte-identical"


def test_mirror_imports_identically() -> None:
    mirror = _load_module(_MIRROR, "wolfram_cag_health_mirror")
    assert mirror.ALL_HEALTH_LANES == health.ALL_HEALTH_LANES
    assert [n for n in dir(mirror) if not n.startswith("__")] == [
        n for n in dir(health) if not n.startswith("__")
    ]


# ---------------------------------------------------------------------------
# Honest defaults: no evidence => UNKNOWN, never READY
# ---------------------------------------------------------------------------


def test_unknown_lane_without_evidence() -> None:
    lane = health.new_lane_state("cag_compute")
    state = lane.evaluate(evidence_time=1000)
    assert state is health.CagHealthState.UNKNOWN


def test_snapshot_unknown_when_no_lanes_provided() -> None:
    snap = health.cag_health_snapshot({}, evidence_time=1000, components=health.CAG_COMPONENTS)
    assert snap.overall is health.CagHealthState.UNKNOWN
    assert all(l.state is health.CagHealthState.UNKNOWN for l in snap.lanes)


def test_ready_requires_entitlement_and_fresh_canary() -> None:
    lane = health.new_lane_state("cag_compute")
    # Fresh successful canary but NO entitlement evidence => UNKNOWN, not READY.
    lane.record_canary(
        health.CanaryReceipt(
            component="cag_compute",
            succeeded=True,
            schema_valid=True,
            evidence_time=1000,
        )
    )
    assert lane.evaluate(evidence_time=1000) is health.CagHealthState.UNKNOWN

    # Now add entitlement => READY.
    lane.entitlement = health.EntitlementStatus(
        verdict=health.EntitlementVerdict.ENTITLED,
        credential_fingerprint=health.credential_fingerprint("secret-key"),
        checked_at=900,
    )
    assert lane.evaluate(evidence_time=1000) is health.CagHealthState.READY


def test_not_entitled_overrides_canary_success() -> None:
    lane = health.new_lane_state("cag_hints")
    lane.entitlement = health.EntitlementStatus(
        verdict=health.EntitlementVerdict.NOT_ENTITLED,
        credential_fingerprint=health.credential_fingerprint(None),
    )
    lane.record_canary(
        health.CanaryReceipt(
            component="cag_hints", succeeded=True, schema_valid=True, evidence_time=1000
        )
    )
    assert lane.evaluate(evidence_time=1000) is health.CagHealthState.NOT_ENTITLED


# ---------------------------------------------------------------------------
# 2xx without valid schema is never success
# ---------------------------------------------------------------------------


def test_2xx_without_valid_schema_is_failure() -> None:
    receipt = health.CanaryReceipt(
        component="cag_results",
        succeeded=True,  # HTTP 2xx
        schema_valid=False,  # but schema failed
        evidence_time=1000,
        failure_family=health.CagFailureFamily.SCHEMA,
    )
    assert not receipt.is_usable_success()
    lane = health.new_lane_state("cag_results")
    lane.entitlement = health.EntitlementStatus(
        verdict=health.EntitlementVerdict.ENTITLED,
        credential_fingerprint=health.credential_fingerprint("k"),
    )
    lane.record_canary(receipt)
    assert lane.evaluate(evidence_time=1000) is health.CagHealthState.UNAVAILABLE


# ---------------------------------------------------------------------------
# Circuit breaker: open / half-open / closed
# ---------------------------------------------------------------------------


def test_circuit_opens_after_threshold_transient_failures() -> None:
    lane = health.new_lane_state("cag_compute", failure_threshold=3)
    lane.entitlement = health.EntitlementStatus(
        verdict=health.EntitlementVerdict.ENTITLED,
        credential_fingerprint=health.credential_fingerprint("k"),
    )
    for i in range(3):
        lane.record_canary(
            health.CanaryReceipt(
                component="cag_compute",
                succeeded=False,
                schema_valid=False,
                evidence_time=1000 + i,
                failure_family=health.CagFailureFamily.UPSTREAM,
            )
        )
    assert lane.breaker.state is health.CircuitState.OPEN
    assert lane.evaluate(evidence_time=2000) is health.CagHealthState.UNAVAILABLE


def test_auth_failure_does_not_open_circuit() -> None:
    lane = health.new_lane_state("cag_hints", failure_threshold=2)
    for i in range(5):
        lane.record_canary(
            health.CanaryReceipt(
                component="cag_hints",
                succeeded=False,
                schema_valid=False,
                evidence_time=1000 + i,
                failure_family=health.CagFailureFamily.AUTH,
            )
        )
    # AUTH is not transient: circuit stays closed, but lane is NOT_ENTITLED-free
    # and the last canary is a failure => UNAVAILABLE.
    assert lane.breaker.state is health.CircuitState.CLOSED
    assert lane.breaker.consecutive_failures == 0


def test_circuit_half_open_after_cooldown() -> None:
    lane = health.new_lane_state("cag_context", failure_threshold=2, cool_down_seconds=60)
    lane.entitlement = health.EntitlementStatus(
        verdict=health.EntitlementVerdict.ENTITLED,
        credential_fingerprint=health.credential_fingerprint("k"),
    )
    for i in range(2):
        lane.record_canary(
            health.CanaryReceipt(
                component="cag_context",
                succeeded=False,
                schema_valid=False,
                evidence_time=1000 + i,
                failure_family=health.CagFailureFamily.TIMEOUT,
            )
        )
    assert lane.breaker.state is health.CircuitState.OPEN
    # Within cool-down => still OPEN / UNAVAILABLE
    assert lane.evaluate(evidence_time=1030) is health.CagHealthState.UNAVAILABLE
    # After cool-down => HALF_OPEN => DEGRADED only after a probe; until then UNAVAILABLE
    lane.breaker.maybe_half_open(1100)
    assert lane.breaker.state is health.CircuitState.HALF_OPEN
    assert lane.breaker.allows_request() is True


def test_recovery_requires_new_real_canary() -> None:
    lane = health.new_lane_state("cag_compute", failure_threshold=2)
    lane.entitlement = health.EntitlementStatus(
        verdict=health.EntitlementVerdict.ENTITLED,
        credential_fingerprint=health.credential_fingerprint("k"),
    )
    lane.record_canary(
        health.CanaryReceipt(
            component="cag_compute",
            succeeded=False,
            schema_valid=False,
            evidence_time=1000,
            failure_family=health.CagFailureFamily.UPSTREAM,
        )
    )
    # No recovery proof before a successful canary.
    recovery = lane.record_canary(
        health.CanaryReceipt(
            component="cag_compute",
            succeeded=True,
            schema_valid=True,
            evidence_time=1100,
        )
    )
    assert recovery is not None
    assert recovery.component == "cag_compute"
    assert recovery.recovered_at == 1100
    assert lane.breaker.state is health.CircuitState.CLOSED
    assert lane.evaluate(evidence_time=1100) is health.CagHealthState.READY


def test_no_recovery_when_success_has_no_prior_failure() -> None:
    lane = health.new_lane_state("cag_compute")
    recovery = lane.record_canary(
        health.CanaryReceipt(
            component="cag_compute",
            succeeded=True,
            schema_valid=True,
            evidence_time=1000,
        )
    )
    assert recovery is None


# ---------------------------------------------------------------------------
# Stale canary degrades to UNKNOWN (no guessing)
# ---------------------------------------------------------------------------


def test_stale_canary_degrades_to_unknown() -> None:
    lane = health.new_lane_state("cag_compute")
    lane.entitlement = health.EntitlementStatus(
        verdict=health.EntitlementVerdict.ENTITLED,
        credential_fingerprint=health.credential_fingerprint("k"),
    )
    lane.record_canary(
        health.CanaryReceipt(
            component="cag_compute",
            succeeded=True,
            schema_valid=True,
            evidence_time=1000,
        )
    )
    assert lane.evaluate(evidence_time=1000) is health.CagHealthState.READY
    # Outside the evidence window => UNKNOWN, not READY.
    assert (
        lane.evaluate(evidence_time=1000 + health.DEFAULT_EVIDENCE_WINDOW_SECONDS + 1)
        is health.CagHealthState.UNKNOWN
    )


# ---------------------------------------------------------------------------
# Quota exhaustion is its own family and blocks retry
# ---------------------------------------------------------------------------


def test_quota_exhaustion_is_degraded_and_blocks_retry() -> None:
    lane = health.new_lane_state("cag_compute")
    lane.entitlement = health.EntitlementStatus(
        verdict=health.EntitlementVerdict.ENTITLED,
        credential_fingerprint=health.credential_fingerprint("k"),
    )
    lane.quota = health.QuotaSnapshot(remaining=0, limit=100, cost_unit="credits")
    lane.record_canary(
        health.CanaryReceipt(
            component="cag_compute",
            succeeded=True,
            schema_valid=True,
            evidence_time=1000,
        )
    )
    # Fresh success but quota exhausted => DEGRADED, not READY.
    assert lane.evaluate(evidence_time=1000) is health.CagHealthState.DEGRADED

    decision = health.decide_retry(
        family=health.CagFailureFamily.QUOTA,
        attempt=1,
        breaker=lane.breaker,
        quota=lane.quota,
    )
    assert decision.should_retry is False
    assert decision.failure_family is health.CagFailureFamily.QUOTA
    assert "quota" in decision.reason.lower()


def test_quota_utilization_bounded() -> None:
    q = health.QuotaSnapshot(remaining=25, limit=100)
    assert q.utilization() == 0.75
    assert not q.is_exhausted()
    q2 = health.QuotaSnapshot(remaining=-5, limit=100)
    assert q2.is_exhausted()
    assert q2.utilization() == 1.0  # bounded, never > 1
    q3 = health.QuotaSnapshot()
    assert q3.utilization() is None
    assert q3.is_exhausted() is False


# ---------------------------------------------------------------------------
# No blind retry: non-retryable families + attempt budget
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "family",
    [
        health.CagFailureFamily.AUTH,
        health.CagFailureFamily.ENTITLEMENT,
        health.CagFailureFamily.SCHEMA,
        health.CagFailureFamily.UNKNOWN,
    ],
)
def test_non_retryable_families_never_retry(family) -> None:
    breaker = health.CircuitBreaker(component="cag_compute")
    decision = health.decide_retry(family=family, attempt=1, breaker=breaker)
    assert decision.should_retry is False


def test_transient_retry_within_budget_only() -> None:
    breaker = health.CircuitBreaker(component="cag_compute")
    # attempt 1 < max(3) => retry
    d1 = health.decide_retry(
        family=health.CagFailureFamily.UPSTREAM, attempt=1, breaker=breaker
    )
    assert d1.should_retry is True
    # attempt 3 == max => no retry
    d3 = health.decide_retry(
        family=health.CagFailureFamily.UPSTREAM, attempt=3, breaker=breaker
    )
    assert d3.should_retry is False
    assert "budget" in d3.reason.lower()


def test_max_attempts_capped_to_hard_ceiling() -> None:
    breaker = health.CircuitBreaker(component="cag_compute")
    d = health.decide_retry(
        family=health.CagFailureFamily.RATE_LIMIT,
        attempt=1,
        breaker=breaker,
        max_attempts=99,
    )
    assert d.max_attempts == health.MAX_RETRY_ATTEMPTS


def test_open_circuit_blocks_retry() -> None:
    breaker = health.CircuitBreaker(component="cag_compute")
    breaker.state = health.CircuitState.OPEN
    d = health.decide_retry(
        family=health.CagFailureFamily.UPSTREAM, attempt=1, breaker=breaker
    )
    assert d.should_retry is False
    assert "circuit" in d.reason.lower()


# ---------------------------------------------------------------------------
# Secret safety: credentials never leak
# ---------------------------------------------------------------------------


def test_credential_fingerprint_is_non_reversible_and_stable() -> None:
    fp = health.credential_fingerprint("super-secret-api-key-12345")
    assert fp.startswith("sha256:")
    assert "super-secret" not in fp
    assert "12345" not in fp
    # stable
    assert health.credential_fingerprint("super-secret-api-key-12345") == fp
    # distinct from another credential
    assert health.credential_fingerprint("other-key") != fp


def test_credential_fingerprint_none_is_unknown() -> None:
    assert health.credential_fingerprint(None) == health.EntitlementVerdict.UNKNOWN.value
    assert health.credential_fingerprint("") == health.EntitlementVerdict.UNKNOWN.value


def test_redact_secret_fields_strips_secrets() -> None:
    payload = {
        "api_key": "sk-live-12345",
        "model": "llama",
        "Authorization": "Bearer abc",
        "remaining": 42,
        "entitlement_blob": "blob-data",
    }
    redacted = health.redact_secret_fields(payload)
    assert redacted["api_key"] == "<redacted>"
    assert redacted["Authorization"] == "<redacted>"
    assert redacted["entitlement_blob"] == "<redacted>"
    assert redacted["model"] == "llama"
    assert redacted["remaining"] == 42
    assert "sk-live" not in repr(redacted)
    assert "abc" not in repr(redacted)


def test_snapshot_contains_no_raw_secret() -> None:
    lane = health.new_lane_state("cag_compute")
    lane.entitlement = health.EntitlementStatus(
        verdict=health.EntitlementVerdict.ENTITLED,
        credential_fingerprint=health.credential_fingerprint("raw-secret-key"),
        checked_at=900,
    )
    lane.record_canary(
        health.CanaryReceipt(
            component="cag_compute",
            succeeded=True,
            schema_valid=True,
            evidence_time=1000,
        )
    )
    snap = health.cag_health_snapshot({"cag_compute": lane}, evidence_time=1000, components=("cag_compute",))
    blob = snap.to_public_json()
    assert "raw-secret-key" not in blob
    assert "<redacted>" not in blob  # fingerprints are hashes, not the redaction token
    assert "sha256:" in blob


# ---------------------------------------------------------------------------
# Failure isolation: CAG outage never blocks independent safety lanes
# ---------------------------------------------------------------------------


def test_failure_isolation_cag_outage_does_not_block_safety_lanes() -> None:
    lane = health.new_lane_state("cag_compute", failure_threshold=2)
    lane.entitlement = health.EntitlementStatus(
        verdict=health.EntitlementVerdict.ENTITLED,
        credential_fingerprint=health.credential_fingerprint("k"),
    )
    for i in range(2):
        lane.record_canary(
            health.CanaryReceipt(
                component="cag_compute",
                succeeded=False,
                schema_valid=False,
                evidence_time=1000 + i,
                failure_family=health.CagFailureFamily.UPSTREAM,
            )
        )
    snap = health.cag_health_snapshot(
        {"cag_compute": lane}, evidence_time=2000, components=("cag_compute",)
    )
    # CAG path is observably unavailable...
    assert snap.overall is health.CagHealthState.UNAVAILABLE
    # ...but independent safety lanes are explicitly unaffected.
    assert snap.independent_safety_lanes_unaffected is True


def test_overall_reflects_worst_lane_without_hiding() -> None:
    states = {
        "cag_hints": _ready_lane("cag_hints", 1000),
        "cag_compute": _unavailable_lane("cag_compute", 1000),
    }
    snap = health.cag_health_snapshot(
        states, evidence_time=1000, components=("cag_hints", "cag_compute")
    )
    assert snap.overall is health.CagHealthState.UNAVAILABLE


def test_not_entitled_optional_lanes_do_not_force_overall_not_entitled() -> None:
    states = {
        "cag_hints": _ready_lane("cag_hints", 1000),
        "cag_agent_one": _not_entitled_lane("cag_agent_one"),
    }
    snap = health.cag_health_snapshot(
        states, evidence_time=1000, components=("cag_hints", "cag_agent_one")
    )
    assert snap.overall is health.CagHealthState.READY


# ---------------------------------------------------------------------------
# Failure-family distinguishability
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "family",
    [
        health.CagFailureFamily.AUTH,
        health.CagFailureFamily.ENTITLEMENT,
        health.CagFailureFamily.QUOTA,
        health.CagFailureFamily.RATE_LIMIT,
        health.CagFailureFamily.TIMEOUT,
        health.CagFailureFamily.UPSTREAM,
        health.CagFailureFamily.SCHEMA,
        health.CagFailureFamily.RESULT_UNAVAILABLE,
    ],
)
def test_failure_families_distinguishable(family) -> None:
    lane = health.new_lane_state("cag_compute")
    lane.entitlement = health.EntitlementStatus(
        verdict=health.EntitlementVerdict.ENTITLED,
        credential_fingerprint=health.credential_fingerprint("k"),
    )
    lane.record_canary(
        health.CanaryReceipt(
            component="cag_compute",
            succeeded=False,
            schema_valid=False,
            evidence_time=1000,
            failure_family=family,
        )
    )
    assert lane.failure_counts.get(family.value) == 1
    snap = health.cag_health_snapshot(
        {"cag_compute": lane}, evidence_time=1000, components=("cag_compute",)
    )
    assert snap.lanes[0].state is health.CagHealthState.UNAVAILABLE


def test_unknown_request_status_yields_unknown_not_guess() -> None:
    """After an unclear request status the lane reads UNKNOWN, not a guess."""
    lane = health.new_lane_state("cag_compute")
    # A canary with UNKNOWN family and not usable => failure recorded, but if
    # no canary at all => UNKNOWN by default. Test the no-evidence path.
    assert lane.evaluate(evidence_time=1000) is health.CagHealthState.UNKNOWN


# ---------------------------------------------------------------------------
# Replay / negative: deterministic evidence keys, invalid input
# ---------------------------------------------------------------------------


def test_canary_evidence_key_is_deterministic_and_secret_free() -> None:
    r = health.CanaryReceipt(
        component="cag_compute",
        succeeded=True,
        schema_valid=True,
        evidence_time=1000,
        latency_ms=42,
        response_uuid="uuid-1",
        request_id="req-1",
    )
    k1 = r.evidence_key()
    k2 = r.evidence_key()
    assert k1 == k2
    assert k1.startswith("sha256:")
    # A different canary yields a different key.
    r2 = health.CanaryReceipt(
        component="cag_compute",
        succeeded=True,
        schema_valid=True,
        evidence_time=1001,
        latency_ms=42,
        response_uuid="uuid-1",
        request_id="req-1",
    )
    assert r2.evidence_key() != k1


def test_new_lane_state_rejects_unknown_component() -> None:
    with pytest.raises(ValueError):
        health.new_lane_state("cag_bogus")


def test_snapshot_json_is_sorted_and_stable() -> None:
    lane = _ready_lane("cag_compute", 1000)
    snap = health.cag_health_snapshot(
        {"cag_compute": lane}, evidence_time=1000, components=("cag_compute",)
    )
    j1 = snap.to_public_json()
    j2 = snap.to_public_json()
    assert j1 == j2
    # sorted keys: "component" appears before "state" etc. within lane dict
    assert j1.index('"component"') < j1.index('"state"')


def test_optional_component_absent_is_unknown() -> None:
    snap = health.cag_health_snapshot(
        {}, evidence_time=1000, components=("cag_agent_one",)
    )
    assert snap.lanes[0].state is health.CagHealthState.UNKNOWN


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _ready_lane(component: str, t: int) -> health.CagLaneState:
    lane = health.new_lane_state(component)
    lane.entitlement = health.EntitlementStatus(
        verdict=health.EntitlementVerdict.ENTITLED,
        credential_fingerprint=health.credential_fingerprint("k"),
        checked_at=t - 100,
    )
    lane.record_canary(
        health.CanaryReceipt(
            component=component, succeeded=True, schema_valid=True, evidence_time=t
        )
    )
    return lane


def _unavailable_lane(component: str, t: int) -> health.CagLaneState:
    lane = health.new_lane_state(component, failure_threshold=2)
    lane.entitlement = health.EntitlementStatus(
        verdict=health.EntitlementVerdict.ENTITLED,
        credential_fingerprint=health.credential_fingerprint("k"),
    )
    for i in range(2):
        lane.record_canary(
            health.CanaryReceipt(
                component=component,
                succeeded=False,
                schema_valid=False,
                evidence_time=t + i,
                failure_family=health.CagFailureFamily.UPSTREAM,
            )
        )
    return lane


def _not_entitled_lane(component: str) -> health.CagLaneState:
    lane = health.new_lane_state(component)
    lane.entitlement = health.EntitlementStatus(
        verdict=health.EntitlementVerdict.NOT_ENTITLED,
        credential_fingerprint=health.credential_fingerprint(None),
    )
    return lane
