"""Idle Live Awareness lane -- read-only evidence watch with consent boundary.

Issue: #1327 -- Idle Live Awareness: read-only evidence watch with consent boundary

A bounded, **non-mutating** observation lane that watches real live evidence in
idle time and reports materially relevant state transitions. It deliberately
cannot reach any mutation tool family.

Pipeline::

    Idle -> Evidence Collector -> Change Detector -> Relevance Gate -> Notification

Mutation stays structurally separated::

    Notification -> explicit Authority Gate -> Agent Run -> Mutation -> Action Receipt

This module owns only the read-only half (collect -> detect -> relevance ->
notification). The authority gate that would unlock a mutation is intentionally
**not** modelled here: a notification never carries permission.

Design rules (matching ``evidence_collectors``):
- Pure and idempotent -- no mutations, no network, no persisted output beyond the
  minimal in-memory watch state returned to the caller.
- Revision-bound -- every observation carries a source revision or runtime identity.
- Fail-explicit -- unreachable/invalid evidence returns ``UNVERIFIABLE``, never success.
- Hash-canonical -- fingerprints reuse ``canonical_evidence_sha256``.
- No secrets -- secret-shaped payloads are rejected as persistable evidence state.

No new persistence layer or truth store is added. The caller persists the
returned ``WatchState`` (already minimal and non-secret) if it needs durability.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final

from .evidence_collectors import (
    DEGRADED,
    LOST,
    PRESERVED,
    UNVERIFIABLE,
    CollectorObservation,
    _SECRET_PATTERNS,
    canonical_evidence_sha256,
)

# Re-export so callers can build observations without a second import surface.
__all__ = [
    "DEGRADED",
    "LOST",
    "PRESERVED",
    "UNVERIFIABLE",
    "MODE_OFF",
    "MODE_OBSERVE",
    "MODE_OBSERVE_NOTIFY",
    "IDLE_MODES",
    "FORBIDDEN_TOOL_FAMILIES",
    "PERMITTED_TOOL_FAMILIES",
    "SUBJECT_PR",
    "SUBJECT_RUNTIME",
    "SUBJECT_PROVIDER",
    "SUBJECT_AGENT_RUN",
    "WATCH_SUBJECT_TYPES",
    "TRIGGER_PR_TERMINAL_GREEN",
    "TRIGGER_REQUIRED_CHECK_RED",
    "TRIGGER_REVISION_MISMATCH",
    "TRIGGER_RUNTIME_DOWN",
    "TRIGGER_FREELLM_DEPLETED",
    "TRIGGER_AGENT_RUN_TERMINAL",
    "TRIGGERS",
    "TERMINAL_GREEN",
    "TERMINAL_DEGRADED",
    "TERMINAL_LOST",
    "TERMINAL_UNVERIFIABLE",
    "TERMINAL_LABELS",
    "AuthorityGrant",
    "WatchDefinition",
    "WatchState",
    "RelevanceVerdict",
    "IdleNotification",
    "IdleWatchResult",
    "IdleAwarenessContractError",
    "IdleMutationBlockedError",
    "assert_no_mutation_tool",
    "build_watch_state",
    "evaluate_relevance",
    "maybe_notify",
    "run_idle_watch",
]


# ---------------------------------------------------------------------------
# Consent / authority model
# ---------------------------------------------------------------------------

MODE_OFF: Final[str] = "off"
MODE_OBSERVE: Final[str] = "observe"
MODE_OBSERVE_NOTIFY: Final[str] = "observe+notify"

IDLE_MODES: Final[frozenset[str]] = frozenset({MODE_OFF, MODE_OBSERVE, MODE_OBSERVE_NOTIFY})

# Tool families that must NEVER be reachable from the idle lane. The idle lane is
# structurally incapable of mutation by construction; this set is the assertion
# surface that tests pin so a future change cannot silently wire one in.
FORBIDDEN_TOOL_FAMILIES: Final[frozenset[str]] = frozenset({
    "merge",
    "deploy",
    "patch",
    "workflow_dispatch",
    "db_write",
    "secret_write",
    "github_write",
    "container_write",
    "image_write",
    "mutation",
})

# The only tools the idle lane is permitted to reference (read-only probes).
PERMITTED_TOOL_FAMILIES: Final[frozenset[str]] = frozenset({
    "read",
    "evidence_collect",
    "github_read",
    "health_read",
    "runtime_read",
})

# Evidence subject types (mirrors issue scope).
SUBJECT_PR: Final[str] = "pr"
SUBJECT_RUNTIME: Final[str] = "runtime"
SUBJECT_PROVIDER: Final[str] = "provider"
SUBJECT_AGENT_RUN: Final[str] = "agent-run"

WATCH_SUBJECT_TYPES: Final[frozenset[str]] = frozenset({
    SUBJECT_PR,
    SUBJECT_RUNTIME,
    SUBJECT_PROVIDER,
    SUBJECT_AGENT_RUN,
})

# Terminal labels derived from observation statuses.
TERMINAL_GREEN: Final[str] = "green"
TERMINAL_DEGRADED: Final[str] = "degraded"
TERMINAL_LOST: Final[str] = "lost"
TERMINAL_UNVERIFIABLE: Final[str] = "unverifiable"

TERMINAL_LABELS: Final[frozenset[str]] = frozenset({
    TERMINAL_GREEN,
    TERMINAL_DEGRADED,
    TERMINAL_LOST,
    TERMINAL_UNVERIFIABLE,
})

# Material transition triggers.
TRIGGER_PR_TERMINAL_GREEN: Final[str] = "pr.terminal_green"
TRIGGER_REQUIRED_CHECK_RED: Final[str] = "pr.required_check_red"
TRIGGER_REVISION_MISMATCH: Final[str] = "runtime.revision_mismatch"
TRIGGER_RUNTIME_DOWN: Final[str] = "runtime.down"
TRIGGER_FREELLM_DEPLETED: Final[str] = "provider.freellm_depleted"
TRIGGER_AGENT_RUN_TERMINAL: Final[str] = "agent_run.terminal"

TRIGGERS: Final[frozenset[str]] = frozenset({
    TRIGGER_PR_TERMINAL_GREEN,
    TRIGGER_REQUIRED_CHECK_RED,
    TRIGGER_REVISION_MISMATCH,
    TRIGGER_RUNTIME_DOWN,
    TRIGGER_FREELLM_DEPLETED,
    TRIGGER_AGENT_RUN_TERMINAL,
})


class IdleAwarenessContractError(ValueError):
    """An idle-awareness input violated a deterministic invariant."""


class IdleMutationBlockedError(IdleAwarenessContractError):
    """Raised when a forbidden mutation tool family is reached from the idle lane."""


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_IDENTIFIER: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_.:-]{0,119}$")
_SHA64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_SHA40: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")


def _is_identifier(value: str) -> bool:
    return bool(_IDENTIFIER.fullmatch(str(value or "")))


def _is_sha64(value: str) -> bool:
    return bool(_SHA64.fullmatch(str(value or "")))


def _looks_secret(value: str) -> bool:
    """True if a string matches a known secret shape. Rejects persistable evidence."""
    text = str(value or "")
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


def _terminal_label(status: str) -> str:
    if status == PRESERVED:
        return TERMINAL_GREEN
    if status == DEGRADED:
        return TERMINAL_DEGRADED
    if status == LOST:
        return TERMINAL_LOST
    return TERMINAL_UNVERIFIABLE


def _trigger_matches_subject(trigger: str, subject_type: str) -> bool:
    if subject_type == SUBJECT_PR:
        return trigger in {TRIGGER_PR_TERMINAL_GREEN, TRIGGER_REQUIRED_CHECK_RED}
    if subject_type == SUBJECT_RUNTIME:
        return trigger in {TRIGGER_REVISION_MISMATCH, TRIGGER_RUNTIME_DOWN}
    if subject_type == SUBJECT_PROVIDER:
        return trigger == TRIGGER_FREELLM_DEPLETED
    if subject_type == SUBJECT_AGENT_RUN:
        return trigger == TRIGGER_AGENT_RUN_TERMINAL
    return False


# ---------------------------------------------------------------------------
# Structural firewall: idle lane cannot reach mutation tool families
# ---------------------------------------------------------------------------

def assert_no_mutation_tool(tool_family: str) -> None:
    """Idle-lane boundary assertion: forbidden families raise, permitted pass.

    This is the structural firewall between the read-only idle lane and any
    mutation surface. A test pins every forbidden family against it.
    """
    fam = str(tool_family or "").strip().lower()
    if not fam:
        raise IdleAwarenessContractError("tool_family must not be empty")
    if fam in FORBIDDEN_TOOL_FAMILIES:
        raise IdleMutationBlockedError(
            f"idle lane cannot reach mutation tool family {fam!r} -- consent boundary violated"
        )
    if fam not in PERMITTED_TOOL_FAMILIES:
        raise IdleAwarenessContractError(f"tool family {fam!r} is not a permitted idle read probe")


# ---------------------------------------------------------------------------
# Authority grant (visible, pausable, revocable, least-privilege)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class AuthorityGrant:
    """Standing authority for a single watch, never implicit ``always allow``.

    A grant authorizes the *idle observation lane* only. It is never a mutation
    permission: even ``MODE_OBSERVE_NOTIFY`` only authorizes emitting a
    notification, never calling a mutation tool.
    """

    watch_id: str
    mode: str
    scope: tuple[str, ...]
    rate_limit_per_hour: int
    paused: bool = False
    revoked: bool = False

    def __post_init__(self) -> None:
        if not _is_identifier(self.watch_id):
            raise IdleAwarenessContractError(f"watch_id is not a valid identifier: {self.watch_id!r}")
        if self.mode not in IDLE_MODES:
            raise IdleAwarenessContractError(f"unsupported idle mode: {self.mode!r}")
        for s in self.scope:
            if not _is_identifier(s):
                raise IdleAwarenessContractError(f"scope entry is not a valid identifier: {s!r}")
        if self.rate_limit_per_hour < 0:
            raise IdleAwarenessContractError("rate_limit_per_hour must be >= 0")

    def is_active(self) -> bool:
        """Active only when not paused, not revoked, and not Off."""
        return (not self.paused) and (not self.revoked) and self.mode != MODE_OFF

    def allows_notification(self) -> bool:
        return self.is_active() and self.mode == MODE_OBSERVE_NOTIFY


# ---------------------------------------------------------------------------
# Watch definition (subject + scope + trigger + grant binding)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class WatchDefinition:
    """A single declared watch: subject + scope + trigger + grant binding."""

    watch_id: str
    subject_type: str
    subject_id: str
    trigger: str
    grant: AuthorityGrant
    evidence_sources: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not _is_identifier(self.watch_id):
            raise IdleAwarenessContractError(f"watch_id is not a valid identifier: {self.watch_id!r}")
        if self.subject_type not in WATCH_SUBJECT_TYPES:
            raise IdleAwarenessContractError(f"unsupported subject_type: {self.subject_type!r}")
        if not str(self.subject_id or "").strip():
            raise IdleAwarenessContractError("subject_id must not be empty")
        if self.trigger not in TRIGGERS:
            raise IdleAwarenessContractError(f"unsupported trigger: {self.trigger!r}")
        if self.grant.watch_id != self.watch_id:
            raise IdleAwarenessContractError("grant.watch_id must match watch_id")
        for src in self.evidence_sources:
            if not _is_identifier(src):
                raise IdleAwarenessContractError(f"evidence_sources entry is not a valid identifier: {src!r}")
        if not _trigger_matches_subject(self.trigger, self.subject_type):
            raise IdleAwarenessContractError(
                f"trigger {self.trigger!r} does not apply to subject_type {self.subject_type!r}"
            )


# ---------------------------------------------------------------------------
# Minimal, non-secret watch state (the only thing the change detector persists)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class WatchState:
    """Minimal persisted watch state. No secrets, no unbounded tool outputs.

    A head/pr revision change invalidates the previous terminal fingerprint,
    resetting accumulated green evidence -- see ``build_watch_state``.
    """

    watch_id: str
    subject_type: str
    subject_id: str
    bound_revision: str
    terminal_fingerprint: str
    terminal_label: str
    first_observed_at: str
    last_observed_at: str
    last_observation_hash: str = ""

    def __post_init__(self) -> None:
        if not _is_identifier(self.watch_id):
            raise IdleAwarenessContractError(f"watch_id is not a valid identifier: {self.watch_id!r}")
        if not str(self.bound_revision or "").strip():
            raise IdleAwarenessContractError("bound_revision must not be empty")
        if not str(self.terminal_fingerprint or "").strip():
            raise IdleAwarenessContractError("terminal_fingerprint must not be empty")
        if self.terminal_label not in TERMINAL_LABELS:
            raise IdleAwarenessContractError(f"unsupported terminal_label: {self.terminal_label!r}")
        if not str(self.first_observed_at or "").strip():
            raise IdleAwarenessContractError("first_observed_at must not be empty")
        if not str(self.last_observed_at or "").strip():
            raise IdleAwarenessContractError("last_observed_at must not be empty")

    def is_green(self) -> bool:
        return self.terminal_label == TERMINAL_GREEN

    def is_red(self) -> bool:
        return self.terminal_label in {TERMINAL_DEGRADED, TERMINAL_LOST}


# ---------------------------------------------------------------------------
# Change detector -- fingerprint the terminal/state of an evidence snapshot
# ---------------------------------------------------------------------------

def _fingerprint(
    subject_type: str,
    subject_id: str,
    revision: str,
    terminal: str,
    detail_hash: str,
) -> str:
    payload = {
        "subject_type": str(subject_type or "").strip().lower(),
        "subject_id": str(subject_id or "").strip(),
        "revision": str(revision or "").strip().lower(),
        "terminal": str(terminal or "").strip().lower(),
        "detail_hash": str(detail_hash or "").strip().lower(),
    }
    return canonical_evidence_sha256(payload)


def build_watch_state(
    *,
    watch: WatchDefinition,
    observation: CollectorObservation,
    observed_at: str,
    previous: WatchState | None = None,
) -> WatchState:
    """Fold an observation into the minimal watch state.

    A head/revision change resets the terminal fingerprint baseline: stale green
    evidence cannot carry over to a new revision.
    """
    if observation.status not in {PRESERVED, DEGRADED, LOST, UNVERIFIABLE}:
        raise IdleAwarenessContractError(f"observation status not allowed: {observation.status!r}")
    if _looks_secret(observation.cause) or _looks_secret(observation.source_revision):
        raise IdleAwarenessContractError("secret-shaped payload rejected as watch evidence")
    for v in observation.detail.values():
        if isinstance(v, str) and _looks_secret(v):
            raise IdleAwarenessContractError("secret-shaped payload rejected as watch evidence")

    rev = str(observation.source_revision or "").strip().lower() or "unverifiable-no-revision"
    terminal = _terminal_label(observation.status)

    prior_rev = previous.bound_revision if previous else None
    first_at = previous.first_observed_at if (previous and prior_rev == rev) else observed_at

    fp = _fingerprint(watch.subject_type, watch.subject_id, rev, terminal, observation.observation_hash)

    return WatchState(
        watch_id=watch.watch_id,
        subject_type=watch.subject_type,
        subject_id=watch.subject_id,
        bound_revision=rev,
        terminal_fingerprint=fp,
        terminal_label=terminal,
        first_observed_at=first_at,
        last_observed_at=observed_at,
        last_observation_hash=observation.observation_hash,
    )


# ---------------------------------------------------------------------------
# Relevance gate -- decide whether a transition is material
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RelevanceVerdict:
    """Decision of the relevance gate for one observation against prior state."""

    material: bool
    trigger: str
    reason: str

    def __post_init__(self) -> None:
        if not str(self.reason or "").strip():
            raise IdleAwarenessContractError("relevance reason must not be empty")
        if self.material and self.trigger not in TRIGGERS:
            raise IdleAwarenessContractError(f"material verdict needs a valid trigger: {self.trigger!r}")


def evaluate_relevance(
    *,
    watch: WatchDefinition,
    observation: CollectorObservation,
    previous: WatchState | None,
) -> RelevanceVerdict:
    """Decide if an observation is a material transition worth notifying.

    No spam on identical evidence: identical fingerprint + same status + same
    revision is suppressed as a duplicate.
    """
    obs_status = observation.status
    rev = str(observation.source_revision or "").strip().lower() or "unverifiable-no-revision"
    terminal = _terminal_label(obs_status)

    # Revision mismatch / head reset is always material when watching runtime.
    if previous is not None and previous.bound_revision != rev:
        if watch.subject_type == SUBJECT_RUNTIME:
            return RelevanceVerdict(
                material=True,
                trigger=TRIGGER_REVISION_MISMATCH,
                reason=(
                    f"bound revision changed {previous.bound_revision[:12]}... -> "
                    f"{rev[:12]}...; green evidence reset"
                ),
            )
        # For PR subjects a head change resets state; fall through to the trigger logic
        # which re-evaluates green/red on the new head (and will suppress duplicates
        # only when the new head is also green AND was already green on that same head).

    if watch.trigger == TRIGGER_PR_TERMINAL_GREEN and watch.subject_type == SUBJECT_PR:
        now_green = obs_status == PRESERVED
        same_head = previous is not None and previous.bound_revision == rev
        was_green = bool(previous) and previous.is_green() and same_head
        if now_green and not was_green:
            return RelevanceVerdict(
                material=True,
                trigger=TRIGGER_PR_TERMINAL_GREEN,
                reason="all PR checks reached terminal green on the current head",
            )
        if previous is not None and same_head and now_green and was_green:
            return RelevanceVerdict(
                material=False,
                trigger=watch.trigger,
                reason="identical terminal-green evidence on the same head -- suppressed duplicate",
            )
        return RelevanceVerdict(
            material=False, trigger=watch.trigger, reason="PR not yet terminal green on this head"
        )

    if watch.trigger == TRIGGER_REQUIRED_CHECK_RED and watch.subject_type == SUBJECT_PR:
        now_red = obs_status in {DEGRADED, LOST}
        same_head = previous is not None and previous.bound_revision == rev
        was_red = bool(previous) and previous.is_red() and same_head
        if now_red and not was_red:
            return RelevanceVerdict(
                material=True,
                trigger=TRIGGER_REQUIRED_CHECK_RED,
                reason="a required PR check fell to degraded/lost",
            )
        if previous is not None and same_head and now_red == was_red:
            return RelevanceVerdict(
                material=False,
                trigger=watch.trigger,
                reason="required-check state unchanged on the same head -- suppressed duplicate",
            )
        return RelevanceVerdict(material=False, trigger=watch.trigger, reason="required check not red")

    if watch.trigger == TRIGGER_REVISION_MISMATCH and watch.subject_type == SUBJECT_RUNTIME:
        if previous is not None and previous.bound_revision != rev:
            return RelevanceVerdict(
                material=True,
                trigger=TRIGGER_REVISION_MISMATCH,
                reason="runtime revision no longer matches expected binding",
            )
        return RelevanceVerdict(
            material=False, trigger=watch.trigger, reason="runtime revision matches expected binding"
        )

    if watch.trigger == TRIGGER_RUNTIME_DOWN and watch.subject_type == SUBJECT_RUNTIME:
        now_down = obs_status == LOST
        same_rev = previous is not None and previous.bound_revision == rev
        was_down = bool(previous) and previous.terminal_label == TERMINAL_LOST and same_rev
        if now_down and not was_down:
            return RelevanceVerdict(
                material=True, trigger=TRIGGER_RUNTIME_DOWN,
                reason="backend/MCP/PatchMon runtime fell to LOST",
            )
        if previous is not None and same_rev and now_down == was_down:
            return RelevanceVerdict(
                material=False, trigger=watch.trigger,
                reason="runtime down state unchanged on same revision -- suppressed duplicate",
            )
        return RelevanceVerdict(material=False, trigger=watch.trigger, reason="runtime not down")

    if watch.trigger == TRIGGER_FREELLM_DEPLETED and watch.subject_type == SUBJECT_PROVIDER:
        depleted = obs_status == LOST
        same_rev = previous is not None and previous.bound_revision == rev
        was_depleted = bool(previous) and previous.terminal_label == TERMINAL_LOST and same_rev
        if depleted and not was_depleted:
            return RelevanceVerdict(
                material=True, trigger=TRIGGER_FREELLM_DEPLETED,
                reason="free-LLM-ready route count fell to 0",
            )
        if not depleted and was_depleted and previous is not None and same_rev:
            return RelevanceVerdict(
                material=True, trigger=TRIGGER_FREELLM_DEPLETED,
                reason="free-LLM-ready routes recovered from 0",
            )
        if previous is not None and same_rev and depleted == was_depleted:
            return RelevanceVerdict(
                material=False, trigger=watch.trigger,
                reason="free-LLM depletion state unchanged -- suppressed duplicate",
            )
        return RelevanceVerdict(
            material=False, trigger=watch.trigger, reason="free-LLM routes not depleted"
        )

    if watch.trigger == TRIGGER_AGENT_RUN_TERMINAL and watch.subject_type == SUBJECT_AGENT_RUN:
        terminal_now = obs_status in {PRESERVED, DEGRADED, LOST}
        fp = _fingerprint(watch.subject_type, watch.subject_id, rev, terminal, observation.observation_hash)
        if terminal_now and (previous is None or previous.terminal_fingerprint != fp):
            return RelevanceVerdict(
                material=True, trigger=TRIGGER_AGENT_RUN_TERMINAL,
                reason="agent run reached a terminal state",
            )
        return RelevanceVerdict(
            material=False, trigger=watch.trigger, reason="agent run not terminal or unchanged"
        )

    return RelevanceVerdict(
        material=False, trigger=watch.trigger, reason="no material transition matched"
    )


# ---------------------------------------------------------------------------
# Notification builder (relevance + grant -> notification, never permission)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class IdleNotification:
    """A material transition notification. Carries evidence + authority basis, never permission."""

    watch_id: str
    subject_type: str
    subject_id: str
    trigger: str
    observed_revision: str
    evidence_refs: tuple[str, ...]
    authority_basis: str
    notification_hash: str

    def __post_init__(self) -> None:
        if not _is_identifier(self.watch_id):
            raise IdleAwarenessContractError(f"watch_id is not a valid identifier: {self.watch_id!r}")
        if self.trigger not in TRIGGERS:
            raise IdleAwarenessContractError(f"unsupported trigger in notification: {self.trigger!r}")
        if not str(self.authority_basis or "").strip():
            raise IdleAwarenessContractError("authority_basis must not be empty")
        if not str(self.observed_revision or "").strip():
            raise IdleAwarenessContractError("observed_revision must not be empty")
        if not _is_sha64(self.notification_hash):
            raise IdleAwarenessContractError("notification_hash must be a SHA-256 hex digest")


def maybe_notify(
    *,
    watch: WatchDefinition,
    observation: CollectorObservation,
    verdict: RelevanceVerdict,
    observed_at: str,
) -> IdleNotification | None:
    """Emit a notification only when the grant allows it and the verdict is material.

    Even with ``MODE_OBSERVE_NOTIFY``, the result is a notification -- it never
    authorizes a mutation. ``None`` means suppressed (Off / paused / revoked /
    observe-only / not material / duplicate).
    """
    if not verdict.material:
        return None
    if not watch.grant.allows_notification():
        return None
    rev = str(observation.source_revision or "").strip().lower() or "unverifiable-no-revision"
    authority_basis = (
        f"idle grant {watch.grant.watch_id} mode={watch.grant.mode} "
        f"scope={','.join(watch.grant.scope) or 'none'} rate={watch.grant.rate_limit_per_hour}/h"
    )
    payload = {
        "watch_id": watch.watch_id,
        "subject_type": watch.subject_type,
        "subject_id": str(watch.subject_id),
        "trigger": verdict.trigger,
        "observed_revision": rev,
        "evidence_refs": [observation.observation_hash],
        "authority_basis": authority_basis,
        "observed_at": str(observed_at),
    }
    nhash = canonical_evidence_sha256(payload)
    return IdleNotification(
        watch_id=watch.watch_id,
        subject_type=watch.subject_type,
        subject_id=str(watch.subject_id),
        trigger=verdict.trigger,
        observed_revision=rev,
        evidence_refs=(observation.observation_hash,),
        authority_basis=authority_basis,
        notification_hash=nhash,
    )


# ---------------------------------------------------------------------------
# Top-level pipeline step: Idle -> Collect -> Detect -> Relevance -> Notify
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class IdleWatchResult:
    """Full result of one idle watch tick."""

    watch_id: str
    new_state: WatchState
    verdict: RelevanceVerdict
    notification: IdleNotification | None


def run_idle_watch(
    *,
    watch: WatchDefinition,
    observation: CollectorObservation,
    observed_at: str,
    previous: WatchState | None = None,
) -> IdleWatchResult:
    """Run one read-only idle watch tick: detect -> relevance -> notify.

    No mutation tool is ever invoked here. The structural firewall is asserted
    up front so the lane can only consume read-only evidence.
    """
    assert_no_mutation_tool("evidence_collect")

    new_state = build_watch_state(
        watch=watch, observation=observation, observed_at=observed_at, previous=previous
    )
    verdict = evaluate_relevance(watch=watch, observation=observation, previous=previous)
    notification = maybe_notify(
        watch=watch, observation=observation, verdict=verdict, observed_at=observed_at
    )
    return IdleWatchResult(
        watch_id=watch.watch_id,
        new_state=new_state,
        verdict=verdict,
        notification=notification,
    )
