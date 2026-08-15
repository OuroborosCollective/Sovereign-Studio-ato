"""
Predictive Action Policy - Python Backend Contract

Implements the versioned, revision-bound Predictive Action Plan contract and the
deterministic policy that decides whether a candidate action is admissible. This
module is a pure data/evidence contract: it does NOT execute actions, it does NOT
touch the network, filesystem, database or any runtime. It only binds, validates
and fail-closes.

Canonical ownership:
    - Execution projection lives in the TypeScript runtime
      (src/features/product/runtime/sovereignPredictiveActionRuntime.ts and
      sovereignPredictiveRuntimePolicy.ts). This module MUST NOT become a second
      execution runtime.
    - Signals / windows / features live in backend/agent_runtime/predictive/
      signal_pipeline.py. This module consumes their revision/config fingerprints
      but does not duplicate signal processing.

Action levels (see docs/architecture/BOUNDED_PREDICTIVE_SELF_HEALING.md):
    Level 0 - Observe          (no runtime mutation, projection only)
    Level 1 - Prepared Safe Reflex (reversible, pre-defined, bounded)
    Level 2 - Bounded Runtime Recovery (stateless replica restart / isolate / stop)
    Level 3 - Swarm Repair     (isolated workspace, ends at most in a Draft PR)
    Level 4 - Owner-bound Only (never derived from lower capabilities)

A plan is admissible only when all of: not expired, revision-bound matches the
target, config-bound matches, capability class permitted for the action level,
payload hash matches the normalized parameters, idempotency key is fresh, TTL and
attempt budget not exhausted, and pre-conditions hold. Otherwise the policy
rejects with an explicit fail-closed reason.

@module agent_runtime.predictive.action_policy
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Tuple


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ActionLevel(Enum):
    """Bounded self-healing action levels. Higher levels never derive from lower."""

    OBSERVE = 0
    SAFE_REFLEX = 1
    BOUNDED_RECOVERY = 2
    SWARM_REPAIR = 3
    OWNER_BOUND = 4


class CapabilityClass(Enum):
    """Capability classes that the policy may reduce (never expand).

    Context Trust / Capability Manifest may only restrict an action, never widen it.
    """

    READ_ONLY = "read_only"
    BOUNDED_REVERSIBLE = "bounded_reversible"
    BOUNDED_STATELESS = "bounded_stateless"
    DRAFT_PR = "draft_pr"
    OWNER_BOUND = "owner_bound"


class PolicyVerdict(Enum):
    ADMIT = "ADMIT"
    REJECT = "REJECT"


class RejectReason(Enum):
    """Fail-closed rejection reasons. Every rejection carries exactly one."""

    EXPIRED = "EXPIRED"                          # TTL elapsed
    STALE_REVISION = "STALE_REVISION"            # target revision changed
    STALE_CONFIG = "STALE_CONFIG"                # config fingerprint changed
    CAPABILITY_TOO_LOW = "CAPABILITY_TOO_LOW"    # level needs higher capability class
    OWNER_BOUND_FROM_LOWER = "OWNER_BOUND_FROM_LOWER"  # Level 4 from a lower cap
    PAYLOAD_HASH_MISMATCH = "PAYLOAD_HASH_MISMATCH"
    IDEMPOTENCY_REPLAY = "IDEMPOTENCY_REPLAY"    # already executed within window
    ATTEMPT_BUDGET_EXHAUSTED = "ATTEMPT_BUDGET_EXHAUSTED"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    UNKNOWN_ACTION = "UNKNOWN_ACTION"
    UNKNOWN_LEVEL = "UNKNOWN_LEVEL"
    INVALID_PLAN = "INVALID_PLAN"


# Mapping: which capability class is required at minimum for each action level.
# Level 4 (OWNER_BOUND) requires OWNER_BOUND capability and can NEVER be derived
# from a lower capability class.
LEVEL_MIN_CAPABILITY: Dict[ActionLevel, CapabilityClass] = {
    ActionLevel.OBSERVE: CapabilityClass.READ_ONLY,
    ActionLevel.SAFE_REFLEX: CapabilityClass.BOUNDED_REVERSIBLE,
    ActionLevel.BOUNDED_RECOVERY: CapabilityClass.BOUNDED_STATELESS,
    ActionLevel.SWARM_REPAIR: CapabilityClass.DRAFT_PR,
    ActionLevel.OWNER_BOUND: CapabilityClass.OWNER_BOUND,
}

# Owner-bound-only actions: never autonomous. These categories require explicit
# owner binding and cannot be produced by a Level <= 3 reflex.
OWNER_BOUND_CATEGORIES = frozenset(
    {
        "db_migration",
        "permanent_data_change",
        "secret_credential",
        "permission_change",
        "github_ruleset",
        "branch_protection",
        "merge",
        "irreversible_delete",
        "new_production_target",
        "new_egress_capability",
        "truth_boundary_change",
    }
)

CONTRACT_VERSION = 1


# ---------------------------------------------------------------------------
# Plan dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActionPlan:
    """Revision/config/capability/payload-bound Predictive Action Plan.

    A plan is the bound candidate produced by the Predictive Lane. It is NOT an
    execution. Admissibility is decided by :func:`evaluate_plan`.
    """

    plan_id: str
    action_id: str
    level: ActionLevel
    capability: CapabilityClass
    # Binding
    risk_bundle_hash: str
    failure_family: str
    # Revisions that must match the live target at evaluation time
    source_revision: str
    runtime_revision: str
    config_fingerprint: str
    model_revision: Optional[str] = None
    index_revision: Optional[str] = None
    image_digest: Optional[str] = None
    # Normalized parameters and their payload hash
    parameters: Mapping[str, Any] = field(default_factory=dict)
    payload_hash: str = ""
    # Guardrails
    preconditions: Tuple[str, ...] = ()
    block_reasons: Tuple[str, ...] = ()
    expected_effect: str = ""
    expected_metrics: Mapping[str, str] = field(default_factory=dict)
    max_effect_duration_s: int = 300
    ttl_s: int = 120
    idempotency_key: str = ""
    max_attempts: int = 1
    rollback_plan: str = ""
    required_post_readbacks: Tuple[str, ...] = ()
    escalation: str = ""
    created_at_s: int = 0
    contract_version: int = CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not self.plan_id:
            raise ValueError("plan_id is required")
        if not self.action_id:
            raise ValueError("action_id is required")
        if self.capability is not LEVEL_MIN_CAPABILITY[self.level]:
            # Allow higher capability than the minimum? No: capability must be
            # exactly the level's class to keep the binding strict and auditable.
            raise ValueError(
                f"capability {self.capability.value} does not match level "
                f"{self.level.name} minimum {LEVEL_MIN_CAPABILITY[self.level].value}"
            )
        if not self.risk_bundle_hash:
            raise ValueError("risk_bundle_hash is required")
        if not self.source_revision or not self.runtime_revision:
            raise ValueError("source/runtime revision binding is required")
        if not self.config_fingerprint:
            raise ValueError("config_fingerprint binding is required")
        if not self.idempotency_key:
            raise ValueError("idempotency_key is required")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.ttl_s <= 0:
            raise ValueError("ttl_s must be > 0")
        if self.level is ActionLevel.OWNER_BOUND and not _is_owner_bound_category(self.action_id):
            # Level 4 must be an explicitly owner-bound category.
            raise ValueError("OWNER_BOUND level requires an owner-bound action_id category")
        # payload_hash must match parameters (caller computes it; we verify shape)
        expected = payload_hash_for(self.parameters)
        if not self.payload_hash:
            object.__setattr__(self, "payload_hash", expected)
        elif self.payload_hash != expected:
            raise ValueError("payload_hash does not match normalized parameters")


@dataclass(frozen=True)
class LiveContext:
    """The live target state observed independently at evaluation time."""

    now_s: int
    target_source_revision: str
    target_runtime_revision: str
    target_config_fingerprint: str
    target_model_revision: Optional[str] = None
    target_index_revision: Optional[str] = None
    target_image_digest: Optional[str] = None
    granted_capability: CapabilityClass = CapabilityClass.READ_ONLY
    idempotency_seen: Mapping[str, int] = field(default_factory=dict)
    attempts_used: int = 0
    precondition_results: Mapping[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyDecision:
    verdict: PolicyVerdict
    reason: Optional[RejectReason] = None
    detail: str = ""
    checked: Tuple[str, ...] = ()

    @property
    def admitted(self) -> bool:
        return self.verdict is PolicyVerdict.ADMIT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def normalize_parameters(parameters: Mapping[str, Any]) -> str:
    """Deterministic canonical encoding of parameters for hashing.

    Sorts keys and serializes with separators to make the hash stable across
    processes and runs. Non-JSON-serializable values raise so secrets/objects
    never silently corrupt the binding.
    """
    return json.dumps(parameters, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def payload_hash_for(parameters: Mapping[str, Any]) -> str:
    return hashlib.sha256(normalize_parameters(parameters).encode("utf-8")).hexdigest()


def _is_owner_bound_category(action_id: str) -> bool:
    prefix, _, _ = action_id.partition(":")
    return prefix in OWNER_BOUND_CATEGORIES


def can_derive(target_level: ActionLevel, granted: CapabilityClass) -> bool:
    """Whether the granted capability class can satisfy the target level's minimum.

    Level 4 is special: it can NEVER be derived from a lower capability class.
    """
    if target_level is ActionLevel.OWNER_BOUND:
        return granted is CapabilityClass.OWNER_BOUND
    required = LEVEL_MIN_CAPABILITY[target_level]
    return _capability_rank(granted) >= _capability_rank(required)


_CAPABILITY_RANK: Dict[CapabilityClass, int] = {
    CapabilityClass.READ_ONLY: 0,
    CapabilityClass.BOUNDED_REVERSIBLE: 1,
    CapabilityClass.BOUNDED_STATELESS: 2,
    CapabilityClass.DRAFT_PR: 3,
    CapabilityClass.OWNER_BOUND: 4,
}


def _capability_rank(c: CapabilityClass) -> int:
    return _CAPABILITY_RANK[c]


def _is_stale_revision(plan: ActionPlan, ctx: LiveContext) -> bool:
    if plan.source_revision != ctx.target_source_revision:
        return True
    if plan.runtime_revision != ctx.target_runtime_revision:
        return True
    if plan.model_revision is not None and ctx.target_model_revision is not None:
        if plan.model_revision != ctx.target_model_revision:
            return True
    if plan.index_revision is not None and ctx.target_index_revision is not None:
        if plan.index_revision != ctx.target_index_revision:
            return True
    if plan.image_digest is not None and ctx.target_image_digest is not None:
        if plan.image_digest != ctx.target_image_digest:
            return True
    return False


# ---------------------------------------------------------------------------
# Policy evaluation
# ---------------------------------------------------------------------------


def evaluate_plan(plan: ActionPlan, ctx: LiveContext) -> PolicyDecision:
    """Deterministically decide whether a plan is admissible right now.

    Fail-closed: any unresolved check rejects the plan. The first failing check
    wins so the reason is explicit and auditable. Order matters: expiry and
    staleness are checked before capability so a stale plan is never admitted by
    a coincidentally-high capability.
    """
    checked: List[str] = []

    # 1. Expiry (TTL)
    checked.append("ttl")
    age = ctx.now_s - plan.created_at_s
    if age < 0 or age > plan.ttl_s:
        return PolicyDecision(
            PolicyVerdict.REJECT,
            RejectReason.EXPIRED,
            f"plan age {age}s exceeds ttl {plan.ttl_s}s",
            tuple(checked),
        )

    # 2. Attempt budget
    checked.append("attempt_budget")
    if ctx.attempts_used >= plan.max_attempts:
        return PolicyDecision(
            PolicyVerdict.REJECT,
            RejectReason.ATTEMPT_BUDGET_EXHAUSTED,
            f"attempts_used {ctx.attempts_used} >= max_attempts {plan.max_attempts}",
            tuple(checked),
        )

    # 3. Idempotency replay
    checked.append("idempotency")
    if ctx.idempotency_seen.get(plan.idempotency_key, 0) >= 1:
        return PolicyDecision(
            PolicyVerdict.REJECT,
            RejectReason.IDEMPOTENCY_REPLAY,
            f"idempotency_key {plan.idempotency_key} already executed",
            tuple(checked),
        )

    # 4. Revision binding (stale rejection)
    checked.append("revision")
    if _is_stale_revision(plan, ctx):
        return PolicyDecision(
            PolicyVerdict.REJECT,
            RejectReason.STALE_REVISION,
            "plan revision binding does not match live target",
            tuple(checked),
        )

    # 5. Config binding
    checked.append("config")
    if plan.config_fingerprint != ctx.target_config_fingerprint:
        return PolicyDecision(
            PolicyVerdict.REJECT,
            RejectReason.STALE_CONFIG,
            "config_fingerprint does not match live target",
            tuple(checked),
        )

    # 6. Capability derivation (Level 4 cannot come from lower)
    checked.append("capability")
    if not can_derive(plan.level, ctx.granted_capability):
        if plan.level is ActionLevel.OWNER_BOUND and ctx.granted_capability is not CapabilityClass.OWNER_BOUND:
            return PolicyDecision(
                PolicyVerdict.REJECT,
                RejectReason.OWNER_BOUND_FROM_LOWER,
                "Level 4 action cannot be derived from a lower capability class",
                tuple(checked),
            )
        return PolicyDecision(
            PolicyVerdict.REJECT,
            RejectReason.CAPABILITY_TOO_LOW,
            f"granted {ctx.granted_capability.value} cannot satisfy level {plan.level.name}",
            tuple(checked),
        )

    # 7. Payload hash (integrity of normalized parameters)
    checked.append("payload_hash")
    if plan.payload_hash != payload_hash_for(plan.parameters):
        return PolicyDecision(
            PolicyVerdict.REJECT,
            RejectReason.PAYLOAD_HASH_MISMATCH,
            "payload_hash does not match normalized parameters",
            tuple(checked),
        )

    # 8. Pre-conditions: every declared precondition name must be present and
    # True in the live context's precondition_results. A missing or False
    # result is fail-closed.
    checked.append("preconditions")
    if plan.preconditions:
        if not all(ctx.precondition_results.get(name, False) for name in plan.preconditions):
            missing = tuple(
                n for n in plan.preconditions if not ctx.precondition_results.get(n, False)
            )
            return PolicyDecision(
                PolicyVerdict.REJECT,
                RejectReason.PRECONDITION_FAILED,
                f"preconditions not met: {missing}",
                tuple(checked),
            )

    checked.append("admit")
    return PolicyDecision(PolicyVerdict.ADMIT, None, "all checks passed", tuple(checked))


def make_plan(**kwargs: Any) -> ActionPlan:
    """Convenience constructor that fills payload_hash when omitted.

    Keeps test fixtures terse while still enforcing the binding.
    """
    params = dict(kwargs.get("parameters") or {})
    if "payload_hash" not in kwargs or not kwargs.get("payload_hash"):
        kwargs["payload_hash"] = payload_hash_for(params)
    return ActionPlan(**kwargs)
