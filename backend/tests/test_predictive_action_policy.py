"""Contract tests for the bounded Predictive Action Policy + Causal Readback.

These exercise the real live-path modules under
``backend.agent_runtime.predictive``. No production logic is copied into the
test. Fixtures are synthetic contract-shaped data; they never contain real
credentials and prove only contract behavior, not runtime truth.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from agent_runtime.predictive.action_policy import (  # noqa: E402
    ActionLevel,
    ActionPlan,
    CapabilityClass,
    LiveContext,
    PolicyVerdict,
    RejectReason,
    can_derive,
    evaluate_plan,
    make_plan,
    normalize_parameters,
    payload_hash_for,
)
from agent_runtime.predictive.causal_readback import (  # noqa: E402
    CausalVerdict,
    EvidenceWindow,
    evaluate_readback,
)


def _ctx(**overrides):
    base = dict(
        now_s=100,
        target_source_revision="abc",
        target_runtime_revision="rt1",
        target_config_fingerprint="cfg1",
        granted_capability=CapabilityClass.BOUNDED_REVERSIBLE,
    )
    base.update(overrides)
    return LiveContext(**base)


def _safe_reflex_plan(**overrides):
    base = dict(
        plan_id="p1",
        action_id="pause_intake:queue:q1",
        level=ActionLevel.SAFE_REFLEX,
        capability=CapabilityClass.BOUNDED_REVERSIBLE,
        risk_bundle_hash="riskhash",
        failure_family="queue_backpressure",
        source_revision="abc",
        runtime_revision="rt1",
        config_fingerprint="cfg1",
        parameters={"queue": "q1", "pause": True},
        ttl_s=120,
        idempotency_key="idem-1",
        created_at_s=40,
    )
    base.update(overrides)
    return make_plan(**base)


# ---------------------------------------------------------------------------
# Plan construction / binding
# ---------------------------------------------------------------------------


def test_payload_hash_is_deterministic_and_order_independent():
    h1 = payload_hash_for({"a": 1, "b": 2})
    h2 = payload_hash_for({"b": 2, "a": 1})
    assert h1 == h2
    assert h1 != payload_hash_for({"a": 1, "b": 3})
    assert normalize_parameters({"a": 1}) == '{"a":1}'


def test_make_plan_fills_payload_hash():
    plan = _safe_reflex_plan()
    assert plan.payload_hash == payload_hash_for(plan.parameters)


def test_plan_rejects_capability_level_mismatch():
    with pytest.raises(ValueError):
        _safe_reflex_plan(capability=CapabilityClass.READ_ONLY)


def test_plan_rejects_missing_idempotency_key():
    with pytest.raises(ValueError):
        ActionPlan(
            plan_id="p",
            action_id="x:y",
            level=ActionLevel.OBSERVE,
            capability=CapabilityClass.READ_ONLY,
            risk_bundle_hash="r",
            failure_family="fam",
            source_revision="a",
            runtime_revision="b",
            config_fingerprint="c",
            idempotency_key="",
        )


def test_owner_bound_level_requires_owner_bound_category():
    with pytest.raises(ValueError):
        _safe_reflex_plan(
            level=ActionLevel.OWNER_BOUND,
            capability=CapabilityClass.OWNER_BOUND,
            action_id="pause_intake:queue:q1",
        )


def test_owner_bound_category_accepted_at_level4():
    plan = make_plan(
        plan_id="p",
        action_id="db_migration:schema:v2",
        level=ActionLevel.OWNER_BOUND,
        capability=CapabilityClass.OWNER_BOUND,
        risk_bundle_hash="r",
        failure_family="fam",
        source_revision="a",
        runtime_revision="b",
        config_fingerprint="c",
        parameters={"version": 2},
        idempotency_key="k",
    )
    assert plan.level is ActionLevel.OWNER_BOUND


# ---------------------------------------------------------------------------
# Policy evaluation - success and fail-closed
# ---------------------------------------------------------------------------


def test_admit_valid_safe_reflex():
    plan = _safe_reflex_plan()
    decision = evaluate_plan(plan, _ctx(now_s=80))
    assert decision.admitted
    assert decision.verdict is PolicyVerdict.ADMIT


@pytest.mark.parametrize(
    "delta,reason",
    [
        (130, RejectReason.EXPIRED),       # beyond ttl
        (-10, RejectReason.EXPIRED),       # created in the future (now < created)
    ],
)
def test_reject_expired(delta, reason):
    plan = _safe_reflex_plan(created_at_s=0, ttl_s=120)
    decision = evaluate_plan(plan, _ctx(now_s=delta))
    assert not decision.admitted
    assert decision.reason is reason


def test_reject_stale_revision():
    plan = _safe_reflex_plan()
    decision = evaluate_plan(plan, _ctx(target_source_revision="different"))
    assert decision.reason is RejectReason.STALE_REVISION


def test_reject_stale_config():
    plan = _safe_reflex_plan()
    decision = evaluate_plan(plan, _ctx(target_config_fingerprint="different"))
    assert decision.reason is RejectReason.STALE_CONFIG


def test_reject_capability_too_low():
    plan = _safe_reflex_plan()
    decision = evaluate_plan(plan, _ctx(granted_capability=CapabilityClass.READ_ONLY))
    assert decision.reason is RejectReason.CAPABILITY_TOO_LOW


def test_reject_owner_bound_from_lower_capability():
    plan = make_plan(
        plan_id="p",
        action_id="db_migration:schema:v2",
        level=ActionLevel.OWNER_BOUND,
        capability=CapabilityClass.OWNER_BOUND,
        risk_bundle_hash="r",
        failure_family="fam",
        source_revision="abc",
        runtime_revision="rt1",
        config_fingerprint="cfg1",
        parameters={"v": 2},
        idempotency_key="k",
        created_at_s=40,
        ttl_s=120,
    )
    decision = evaluate_plan(plan, _ctx(now_s=80, granted_capability=CapabilityClass.DRAFT_PR))
    assert decision.reason is RejectReason.OWNER_BOUND_FROM_LOWER


def test_reject_idempotency_replay():
    plan = _safe_reflex_plan()
    decision = evaluate_plan(plan, _ctx(idempotency_seen={"idem-1": 1}))
    assert decision.reason is RejectReason.IDEMPOTENCY_REPLAY


def test_reject_attempt_budget_exhausted():
    plan = _safe_reflex_plan(max_attempts=2)
    decision = evaluate_plan(plan, _ctx(attempts_used=2))
    assert decision.reason is RejectReason.ATTEMPT_BUDGET_EXHAUSTED


def test_reject_payload_hash_mismatch():
    real = _safe_reflex_plan()
    # Tamper after construction (bypass frozen) to simulate integrity loss.
    object.__setattr__(real, "payload_hash", "tampered")
    decision = evaluate_plan(real, _ctx(now_s=80))
    assert decision.reason is RejectReason.PAYLOAD_HASH_MISMATCH


def test_reject_precondition_failed():
    plan = _safe_reflex_plan(preconditions=("intake_paused", "quota_available"))
    decision = evaluate_plan(plan, _ctx(now_s=80, precondition_results={"intake_paused": True, "quota_available": False}))
    assert decision.reason is RejectReason.PRECONDITION_FAILED


def test_admit_when_preconditions_all_met():
    plan = _safe_reflex_plan(preconditions=("intake_paused", "quota_available"))
    decision = evaluate_plan(plan, _ctx(now_s=80, precondition_results={"intake_paused": True, "quota_available": True}))
    assert decision.admitted


def test_reject_precondition_missing_result_is_fail_closed():
    plan = _safe_reflex_plan(preconditions=("intake_paused",))
    decision = evaluate_plan(plan, _ctx(now_s=80))  # no precondition_results
    assert decision.reason is RejectReason.PRECONDITION_FAILED


def test_checked_chain_present_on_admit():
    plan = _safe_reflex_plan()
    decision = evaluate_plan(plan, _ctx(now_s=80))
    assert "admit" in decision.checked
    assert "revision" in decision.checked
    assert "capability" in decision.checked


# ---------------------------------------------------------------------------
# Capability derivation semantics
# ---------------------------------------------------------------------------


def test_can_derive_higher_capability_satisfies_lower_level():
    assert can_derive(ActionLevel.OBSERVE, CapabilityClass.OWNER_BOUND)


def test_can_derive_owner_bound_only_from_owner_bound():
    assert not can_derive(ActionLevel.OWNER_BOUND, CapabilityClass.DRAFT_PR)
    assert can_derive(ActionLevel.OWNER_BOUND, CapabilityClass.OWNER_BOUND)


# ---------------------------------------------------------------------------
# Causal readback verdicts
# ---------------------------------------------------------------------------


def _readback_plan(**overrides):
    base = dict(
        plan_id="rp",
        action_id="shift_traffic:replica:r2",
        level=ActionLevel.BOUNDED_RECOVERY,
        capability=CapabilityClass.BOUNDED_STATELESS,
        risk_bundle_hash="r",
        failure_family="replica_sick",
        source_revision="abc",
        runtime_revision="rt1",
        config_fingerprint="cfg1",
        image_digest="sha:img1",
        parameters={"replica": "r2"},
        expected_metrics={"error_rate": "down"},
        max_effect_duration_s=30,
        ttl_s=300,
        idempotency_key="k",
        created_at_s=100,
        rollback_plan="revert_traffic",
    )
    base.update(overrides)
    return make_plan(**base)


def _win(captured_at_s, metrics=None, **parity):
    return EvidenceWindow(
        captured_at_s=captured_at_s,
        metrics=metrics or {},
        **parity,
    )


def test_effect_verified_when_metric_moves_expected_direction():
    plan = _readback_plan()
    pre = _win(100, {"error_rate": 0.9}, source_revision="abc", runtime_revision="rt1", config_fingerprint="cfg1", image_digest="sha:img1")
    post = _win(140, {"error_rate": 0.2}, source_revision="abc", runtime_revision="rt1", config_fingerprint="cfg1", image_digest="sha:img1")
    res = evaluate_readback(plan, pre, post)
    assert res.verdict is CausalVerdict.EFFECT_VERIFIED


def test_effect_contradicted_when_metric_moves_opposite():
    plan = _readback_plan()
    pre = _win(100, {"error_rate": 0.2}, source_revision="abc", runtime_revision="rt1", config_fingerprint="cfg1", image_digest="sha:img1")
    post = _win(140, {"error_rate": 0.9}, source_revision="abc", runtime_revision="rt1", config_fingerprint="cfg1", image_digest="sha:img1")
    res = evaluate_readback(plan, pre, post)
    assert res.verdict is CausalVerdict.EFFECT_CONTRADICTED
    assert "error_rate" in res.contradicted_metrics


def test_effect_not_observed_when_metric_flat():
    plan = _readback_plan()
    pre = _win(100, {"error_rate": 0.5}, source_revision="abc", runtime_revision="rt1", config_fingerprint="cfg1", image_digest="sha:img1")
    post = _win(140, {"error_rate": 0.5}, source_revision="abc", runtime_revision="rt1", config_fingerprint="cfg1", image_digest="sha:img1")
    res = evaluate_readback(plan, pre, post)
    assert res.verdict is CausalVerdict.EFFECT_NOT_OBSERVED


def test_target_changed_externally_when_revision_drifts():
    plan = _readback_plan()
    pre = _win(100, {"error_rate": 0.9}, source_revision="abc", runtime_revision="rt1", config_fingerprint="cfg1", image_digest="sha:img1")
    post = _win(140, {"error_rate": 0.1}, source_revision="abc", runtime_revision="rtCHANGED", config_fingerprint="cfg1", image_digest="sha:img1")
    res = evaluate_readback(plan, pre, post)
    assert res.verdict is CausalVerdict.TARGET_CHANGED_EXTERNALLY


def test_insufficient_post_window_when_captured_too_early():
    plan = _readback_plan(max_effect_duration_s=60)
    pre = _win(100, {"error_rate": 0.9}, source_revision="abc", runtime_revision="rt1", config_fingerprint="cfg1", image_digest="sha:img1")
    post = _win(120, {"error_rate": 0.1}, source_revision="abc", runtime_revision="rt1", config_fingerprint="cfg1", image_digest="sha:img1")
    res = evaluate_readback(plan, pre, post)
    assert res.verdict is CausalVerdict.INSUFFICIENT_POST_WINDOW
    assert not res.post_window_sufficient


def test_rollback_required_when_side_effects_and_rollback_plan():
    plan = _readback_plan()
    pre = _win(100, {"error_rate": 0.9}, source_revision="abc", runtime_revision="rt1", config_fingerprint="cfg1", image_digest="sha:img1")
    post = _win(
        140,
        {"error_rate": 0.1},
        source_revision="abc",
        runtime_revision="rt1",
        config_fingerprint="cfg1",
        image_digest="sha:img1",
    )
    object.__setattr__(post, "side_effects", ("latency_spike",))
    res = evaluate_readback(plan, pre, post)
    assert res.verdict is CausalVerdict.ROLLBACK_REQUIRED


def test_external_change_baseline_missing():
    """If pre window does not match the plan binding, the effect is not attributable."""
    plan = _readback_plan()
    pre = _win(100, {"error_rate": 0.9}, source_revision="WRONG", runtime_revision="rt1", config_fingerprint="cfg1", image_digest="sha:img1")
    post = _win(140, {"error_rate": 0.1}, source_revision="abc", runtime_revision="rt1", config_fingerprint="cfg1", image_digest="sha:img1")
    res = evaluate_readback(plan, pre, post)
    assert res.verdict is CausalVerdict.TARGET_CHANGED_EXTERNALLY
