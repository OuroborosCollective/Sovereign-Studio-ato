"""
Causal Readback - Python Backend Contract

Deterministically classifies whether a bound action produced its expected effect,
using two independent evidence windows (pre-action and post-action) and parity
checks against the action's bound revisions/digests/config. This module never
trusts a tool result, model answer or exit code as causal proof. An execution
that "succeeded" remains ``SUCCEEDED_UNVERIFIED`` until the readback verdict is
established.

This is a pure contract: no network, no DB, no execution. The windows are passed
in by the caller, who is responsible for collecting real evidence.

@module agent_runtime.predictive.causal_readback
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional, Tuple

from .action_policy import ActionPlan


class CausalVerdict(Enum):
    EFFECT_VERIFIED = "EFFECT_VERIFIED"
    EFFECT_NOT_OBSERVED = "EFFECT_NOT_OBSERVED"
    EFFECT_CONTRADICTED = "EFFECT_CONTRADICTED"
    TARGET_CHANGED_EXTERNALLY = "TARGET_CHANGED_EXTERNALLY"
    INSUFFICIENT_POST_WINDOW = "INSUFFICIENT_POST_WINDOW"
    ROLLBACK_REQUIRED = "ROLLBACK_REQUIRED"


@dataclass(frozen=True)
class EvidenceWindow:
    """A snapshot of real target state at a point in time.

    ``metrics`` holds observed metric values keyed by the plan's expected_metrics
    keys; ``parity`` holds the observed revisions/digests/config at this moment.
    """

    captured_at_s: int
    metrics: Mapping[str, float] = field(default_factory=dict)
    source_revision: Optional[str] = None
    runtime_revision: Optional[str] = None
    config_fingerprint: Optional[str] = None
    image_digest: Optional[str] = None
    side_effects: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ReadbackResult:
    verdict: CausalVerdict
    detail: str = ""
    matched_metrics: Tuple[str, ...] = ()
    contradicted_metrics: Tuple[str, ...] = ()
    external_change: bool = False
    post_window_sufficient: bool = True


def evaluate_readback(
    plan: ActionPlan,
    pre: EvidenceWindow,
    post: EvidenceWindow,
) -> ReadbackResult:
    """Classify the effect of a bound action from real pre/post evidence.

    Decision order (first match wins):

    1. Parity drift -> TARGET_CHANGED_EXTERNALLY. If the post-action target
       revision/digest/config no longer matches the plan's binding (and the
       pre-action matched it), the target was changed by something other than
       this action; the observed effect cannot be attributed causally.
    2. Insufficient post window -> INSUFFICIENT_POST_WINDOW. The post window
       must be captured after the action and after the plan's max_effect_duration.
    3. Side effects present in post -> ROLLBACK_REQUIRED when the plan declared a
       rollback plan and unexpected negative side effects are observed.
    4. Expected metric movement -> EFFECT_VERIFIED when every declared expected
       metric is observed and moved in the expected direction; EFFECT_CONTRADICTED
       when at least one moved opposite to expected; else EFFECT_NOT_OBSERVED.

    An improvement after the action is NOT automatically causal.
    """
    # 1. Parity: did the target change externally?
    external = _target_changed_externally(plan, pre, post)
    if external:
        return ReadbackResult(
            CausalVerdict.TARGET_CHANGED_EXTERNALLY,
            "post-action target binding drifted from plan; effect not attributable",
            external_change=True,
            post_window_sufficient=True,
        )

    # 2. Post window sufficiency
    min_post_s = plan.created_at_s + plan.max_effect_duration_s
    if post.captured_at_s < min_post_s:
        return ReadbackResult(
            CausalVerdict.INSUFFICIENT_POST_WINDOW,
            f"post captured at {post.captured_at_s} before settle time {min_post_s}",
            post_window_sufficient=False,
        )

    # 3. Negative side effects -> rollback required (only if plan can roll back)
    if post.side_effects and plan.rollback_plan:
        return ReadbackResult(
            CausalVerdict.ROLLBACK_REQUIRED,
            f"unexpected side effects observed: {', '.join(post.side_effects)}",
            post_window_sufficient=True,
        )

    # 4. Expected metric movement
    matched, contradicted = _classify_metrics(plan, pre, post)
    if contradicted:
        return ReadbackResult(
            CausalVerdict.EFFECT_CONTRADICTED,
            f"metrics contradicted expected direction: {', '.join(contradicted)}",
            matched_metrics=tuple(matched),
            contradicted_metrics=tuple(contradicted),
            post_window_sufficient=True,
        )
    if len(matched) == len(plan.expected_metrics) and plan.expected_metrics:
        return ReadbackResult(
            CausalVerdict.EFFECT_VERIFIED,
            "all expected metrics moved in expected direction",
            matched_metrics=tuple(matched),
            post_window_sufficient=True,
        )
    return ReadbackResult(
        CausalVerdict.EFFECT_NOT_OBSERVED,
        "expected metric movement not observed in post window",
        matched_metrics=tuple(matched),
        post_window_sufficient=True,
    )


def _target_changed_externally(plan: ActionPlan, pre: EvidenceWindow, post: EvidenceWindow) -> bool:
    """True when pre matched the plan binding but post drifted away from it.

    If pre did not match, we cannot establish the baseline; that is treated as
    external change (cannot attribute the effect).
    """
    if not _window_matches_plan(plan, pre):
        return True
    return not _window_matches_plan(plan, post)


def _window_matches_plan(plan: ActionPlan, w: EvidenceWindow) -> bool:
    if w.source_revision is not None and w.source_revision != plan.source_revision:
        return False
    if w.runtime_revision is not None and w.runtime_revision != plan.runtime_revision:
        return False
    if w.config_fingerprint is not None and w.config_fingerprint != plan.config_fingerprint:
        return False
    if w.image_digest is not None and plan.image_digest is not None:
        if w.image_digest != plan.image_digest:
            return False
    return True


def _classify_metrics(
    plan: ActionPlan, pre: EvidenceWindow, post: EvidenceWindow
) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """Return (matched, contradicted) metric keys against declared expectations.

    ``plan.expected_metrics`` maps a metric key to a direction token in
    ``{"up", "down", "flat"}``. A metric is matched when the post value moved
    in the expected direction relative to the pre value; contradicted when it
    moved opposite. Metrics absent from either window are neither (not observed).
    """
    direction_rank = {"up": 1, "flat": 0, "down": -1}
    matched = []
    contradicted = []
    for key, direction in plan.expected_metrics.items():
        if direction not in direction_rank:
            continue
        if key not in pre.metrics or key not in post.metrics:
            continue
        delta = post.metrics[key] - pre.metrics[key]
        want = direction_rank[direction]
        if want == 0:
            ok = abs(delta) < 1e-9
        elif want > 0:
            ok = delta > 0
        else:
            ok = delta < 0
        opposite = (want > 0 and delta < 0) or (want < 0 and delta > 0)
        if opposite:
            contradicted.append(key)
        elif ok:
            matched.append(key)
    return tuple(matched), tuple(contradicted)
