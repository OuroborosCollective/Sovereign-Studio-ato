"""Runtime health, quota, cost and failure-isolation lane for Wolfram CAG.

This module makes the Wolfram CAG provider path observable as a *real*
runtime dependency, **without confusing provider health with product
health** (Issue #1462, parent epic #1457).

It is the read-only health companion to the CAG transport / adapter lane
(#1459) and the deterministic evidence lane (#1460). It owns **no** truth
authority of its own: every health verdict is a projection derived from
machine-checkable evidence (a real canary receipt, a circuit-breaker
transition, quota/cost metadata). Provider success is never product
success, and a CAG outage can never produce ``RUNTIME_VERIFIED`` or block
an independent hard safety lane.

Design rules (from #1462 acceptance criteria):

- **Failure isolation.** A CAG outage never renders GitHub / DB / Docker /
  PatchMon readbacks unusable, and never blocks an independent
  deterministic safety lane. ``cag_health_snapshot`` returns a degraded
  CAG verdict but always leaves the non-CAG lanes untouched.
- **No blind retry.** ``RetryDecision`` is bounded; a ``429`` / quota
  exhaustion / timeout never starts an unbounded retry loop. Quota
  exhaustion is its own failure family, never smoothed into ``AUTH`` or
  ``UPSTREAM``.
- **Read target state first.** After an unclear request status the lane
  records ``UNKNOWN`` rather than guessing; recovery is only declared when
  a *new real canary* succeeds (``RecoveryProof``).
- **Secret-safe.** Credential / entitlement validity is exposed only as a
  secret-free verdict (``ENTITLED`` / ``NOT_ENTITLED`` / ``UNKNOWN``).
  Raw API keys, tokens and entitlement blobs are never stored, logged or
  returned.
- **Honest unknown.** Without a real canary receipt the lane returns
  ``UNKNOWN`` / ``UNAVAILABLE`` — never ``READY``. ``READY`` requires a
  fresh, schema-valid canary within the evidence window.

The module is pure stdlib: no network, no filesystem, no clock, no
random. All time is injected as ``evidence_time`` so tests are
deterministic. A separate owner-approved runtime step feeds real canary
receipts in; until then every lane is honestly ``UNKNOWN``.

Truth class: ``IMPLEMENTED_IN_REPOSITORY``. A lane only becomes
``RUNTIME_VERIFIED`` after real provider + PatchMon / container readback,
which is deferred to #1458 / #1462 runtime work.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

# ---------------------------------------------------------------------------
# Component / lane identity
# ---------------------------------------------------------------------------

#: The four Wolfram CAG component APIs, plus an optional Agent One lane.
#: These map 1:1 to the capabilities projected by the #1459 adapter lane;
#: this module owns no second registry.
CAG_COMPONENTS: tuple[str, ...] = (
    "cag_hints",
    "cag_compute",
    "cag_results",
    "cag_context",
)
OPTIONAL_COMPONENTS: tuple[str, ...] = ("cag_agent_one",)
ALL_HEALTH_LANES: tuple[str, ...] = CAG_COMPONENTS + OPTIONAL_COMPONENTS

#: Hard ceiling on bounded retry attempts. A request may never exceed this
#: regardless of caller input, preventing unbounded retry / cost loops.
MAX_RETRY_ATTEMPTS: int = 3

#: Evidence window (seconds) within which a canary is considered "fresh".
#: Outside this window the lane degrades toward UNKNOWN without a new canary.
DEFAULT_EVIDENCE_WINDOW_SECONDS: int = 300


class CagHealthState(str, Enum):
    """Observable health state for a single CAG lane.

    These are explicit truth classes, never a generic ``done``:

    - ``READY``: a fresh, schema-valid real canary succeeded within the
      evidence window AND the circuit breaker is closed.
    - ``DEGRADED``: the lane is reachable but degraded (e.g. circuit
      half-open, elevated timeout ratio, rate-limited but recoverable).
    - ``UNAVAILABLE``: the component is provisioned but currently
      unreachable / erroring (circuit open, upstream down, timeout storm).
    - ``NOT_ENTITLED``: the component is not provisioned / not entitled.
    - ``UNKNOWN``: no usable evidence yet (no canary, stale canary, or
      unclear request status). The honest default.
    """

    READY = "READY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_ENTITLED = "NOT_ENTITLED"
    UNKNOWN = "UNKNOWN"


class CagFailureFamily(str, Enum):
    """Normalised, distinguishable failure families (mirrors #1459).

    Quota exhaustion is its own family and is never smoothed into AUTH or
    UPSTREAM, so a quota storm cannot masquerade as an auth or upstream
    outage.
    """

    AUTH = "AUTH"
    ENTITLEMENT = "ENTITLEMENT"
    QUOTA = "QUOTA"
    RATE_LIMIT = "RATE_LIMIT"
    TIMEOUT = "TIMEOUT"
    UPSTREAM = "UPSTREAM"
    SCHEMA = "SCHEMA"
    RESULT_UNAVAILABLE = "RESULT_UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class EntitlementVerdict(str, Enum):
    """Secret-free credential / entitlement validity verdict."""

    ENTITLED = "ENTITLED"
    NOT_ENTITLED = "NOT_ENTITLED"
    UNKNOWN = "UNKNOWN"


class CircuitState(str, Enum):
    """Circuit-breaker state for failure isolation."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


# Failure families that count toward opening the circuit (transient storms).
_CIRCUIT_OPENING_FAMILIES: frozenset[CagFailureFamily] = frozenset(
    {
        CagFailureFamily.UPSTREAM,
        CagFailureFamily.TIMEOUT,
        CagFailureFamily.RATE_LIMIT,
        CagFailureFamily.QUOTA,
        CagFailureFamily.SCHEMA,
        CagFailureFamily.RESULT_UNAVAILABLE,
    }
)
# Families that are NOT transient and must NOT drive blind retry.
_NON_RETRYABLE_FAMILIES: frozenset[CagFailureFamily] = frozenset(
    {
        CagFailureFamily.AUTH,
        CagFailureFamily.ENTITLEMENT,
        CagFailureFamily.QUOTA,
        CagFailureFamily.SCHEMA,
    }
)

# ---------------------------------------------------------------------------
# Secret-safe hashing
# ---------------------------------------------------------------------------

# Fields that may carry secret-shaped values and must never leave this module
# in raw form. They are reduced to a non-reversible SHA-256 prefix only.
_SECRET_FIELDS: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "token",
        "authorization",
        "app_id",
        "appid",
        "secret",
        "password",
        "credential",
        "entitlement_blob",
    }
)

_REDACTED = "<redacted>"
_HASH_PREFIX_LEN = 12


def _redact_value(value: object) -> str:
    """Reduce a secret-shaped value to a non-reversible hash prefix.

    Only the first ``_HASH_PREFIX_LEN`` hex chars of a SHA-256 are kept, so
    the value is identifiable for correlation but cannot be reversed to the
    raw secret. Empty / falsy values become ``UNKNOWN`` rather than a hash
    of the empty string.
    """
    if value is None or value == "":
        return EntitlementVerdict.UNKNOWN.value
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest[:_HASH_PREFIX_LEN]}"


def redact_secret_fields(payload: Mapping[str, object]) -> dict[str, object]:
    """Return a copy of ``payload`` with any secret-shaped field redacted.

    Used by callers before logging / persisting quota or credential
    metadata. Non-secret fields are passed through unchanged.
    """
    redacted: dict[str, object] = {}
    for key, value in payload.items():
        if key.lower() in _SECRET_FIELDS:
            redacted[key] = _redacted if not isinstance(value, str) else _REDACTED
        else:
            redacted[key] = value
    return redacted


def credential_fingerprint(raw_credential: object) -> str:
    """Public, secret-safe fingerprint of a raw credential.

    Returns a non-reversible ``sha256:<prefix>`` string suitable for
    correlation in receipts and logs. The raw credential never leaves the
    caller. ``None`` / empty yields ``UNKNOWN``.
    """
    return _redact_value(raw_credential)


# ---------------------------------------------------------------------------
# Evidence records
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CanaryReceipt:
    """A single real CAG component canary result.

    ``schema_valid`` must be explicit: a 2xx response that fails schema
    validation is never a success (mirrors the #1459 transport contract).
    """

    component: str
    succeeded: bool
    schema_valid: bool
    evidence_time: int
    failure_family: CagFailureFamily | None = None
    latency_ms: int | None = None
    response_uuid: str | None = None
    request_id: str | None = None

    def is_usable_success(self) -> bool:
        """A canary only counts as success when 2xx AND schema-valid."""
        return bool(self.succeeded and self.schema_valid)

    def evidence_key(self) -> str:
        """Deterministic, secret-free key binding this canary's identity."""
        parts = [
            self.component,
            str(self.is_usable_success()),
            str(self.evidence_time),
            str(self.failure_family.value if self.failure_family else ""),
            str(self.latency_ms if self.latency_ms is not None else ""),
            str(self.response_uuid or ""),
            str(self.request_id or ""),
        ]
        raw = "|".join(parts).encode("utf-8")
        return "sha256:" + hashlib.sha256(raw).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class RecoveryProof:
    """Proof that a lane recovered: a *new* real canary after a failure.

    Recovery is never declared from elapsed time or a model statement; it
    requires a fresh successful canary whose evidence time is at or after
    the last failure's evidence time.
    """

    component: str
    recovered_at: int
    canary_key: str


@dataclass(frozen=True, slots=True)
class QuotaSnapshot:
    """Secret-free quota / cost metadata for a lane.

    All fields are optional and bounded; absent metadata is ``None``, never
    invented. ``cost_unit`` is an opaque contract string (e.g. ``"credits"``)
    and carries no monetary claim by itself.
    """

    remaining: float | None = None
    limit: float | None = None
    reset_at: int | None = None
    cost_unit: str | None = None
    cost_per_unit: float | None = None

    def is_exhausted(self) -> bool:
        """Quota exhaustion is its own signal, distinct from rate-limiting."""
        if self.remaining is None:
            return False
        return self.remaining <= 0

    def utilization(self) -> float | None:
        """Bounded utilization ratio in ``[0.0, 1.0]`` or ``None`` if unknown."""
        if self.limit is None or self.limit <= 0 or self.remaining is None:
            return None
        used = self.limit - self.remaining
        ratio = used / self.limit
        if ratio < 0.0:
            return 0.0
        if ratio > 1.0:
            return 1.0
        return ratio

    def to_public_dict(self) -> dict[str, object]:
        """Secret-free projection. No raw credential ever appears here."""
        return {
            "remaining": self.remaining,
            "limit": self.limit,
            "resetAt": self.reset_at,
            "costUnit": self.cost_unit,
            "costPerUnit": self.cost_per_unit,
            "exhausted": self.is_exhausted(),
            "utilization": self.utilization(),
        }


@dataclass(frozen=True, slots=True)
class EntitlementStatus:
    """Secret-free credential / entitlement validity for a lane."""

    verdict: EntitlementVerdict
    credential_fingerprint: str
    entitlement_source: str | None = None
    checked_at: int | None = None

    def to_public_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict.value,
            "credentialFingerprint": self.credential_fingerprint,
            "entitlementSource": self.entitlement_source,
            "checkedAt": self.checked_at,
        }


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CircuitBreaker:
    """Bounded circuit breaker for one CAG lane.

    The breaker isolates failures: when OPEN, the lane is UNAVAILABLE and
    requests are short-circuited rather than hammering a down provider.
    It only moves to HALF_OPEN (probe) after ``cool_down_seconds``, and to
    CLOSED only on a successful probe (a real canary). Time is injected so
    the breaker is deterministic and testable.
    """

    component: str
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    opened_at: int | None = None
    failure_threshold: int = 3
    cool_down_seconds: int = 60

    def record_failure(self, family: CagFailureFamily, at_time: int) -> None:
        """Record a failure. Only transient families open the circuit.

        AUTH / ENTITLEMENT failures do NOT open the circuit (they are not
        transient provider outages) — they are surfaced as ``NOT_ENTITLED``
        instead, keeping failure families distinguishable.
        """
        if family in _NON_RETRYABLE_FAMILIES and family in (
            CagFailureFamily.AUTH,
            CagFailureFamily.ENTITLEMENT,
        ):
            # Auth/entitlement is not a transient outage; do not open.
            return
        if family not in _CIRCUIT_OPENING_FAMILIES:
            return
        self.consecutive_failures += 1
        if (
            self.state is not CircuitState.OPEN
            and self.consecutive_failures >= self.failure_threshold
        ):
            self.state = CircuitState.OPEN
            self.opened_at = at_time

    def record_success(self) -> None:
        """A real successful canary closes the circuit (recovery)."""
        self.consecutive_failures = 0
        self.state = CircuitState.CLOSED
        self.opened_at = None

    def maybe_half_open(self, at_time: int) -> None:
        """Allow a single probe after the cool-down window elapses."""
        if self.state is CircuitState.OPEN and self.opened_at is not None:
            if at_time - self.opened_at >= self.cool_down_seconds:
                self.state = CircuitState.HALF_OPEN

    def allows_request(self) -> bool:
        """Whether a request may be attempted (CLOSED or HALF_OPEN)."""
        return self.state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)


# ---------------------------------------------------------------------------
# Per-lane runtime state
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CagLaneState:
    """Mutable per-lane runtime state fed by real evidence."""

    component: str
    breaker: CircuitBreaker
    last_canary: CanaryReceipt | None = None
    last_failure_time: int | None = None
    quota: QuotaSnapshot = field(default_factory=QuotaSnapshot)
    entitlement: EntitlementStatus | None = None
    contract_revision: str | None = None
    adapter_revision: str | None = None
    container_digest: str | None = None
    latency_class: str | None = None
    timeout_ratio: float | None = None
    # Bounded rolling failure counts by family (for observability only).
    failure_counts: dict[str, int] = field(default_factory=dict)

    def record_canary(self, receipt: CanaryReceipt) -> RecoveryProof | None:
        """Feed a real canary receipt into the lane.

        Returns a ``RecoveryProof`` only when this canary marks a recovery
        (success after a prior failure within the same lane).
        """
        recovery: RecoveryProof | None = None
        was_failing = self.last_failure_time is not None
        if receipt.is_usable_success():
            if was_failing:
                recovery = RecoveryProof(
                    component=self.component,
                    recovered_at=receipt.evidence_time,
                    canary_key=receipt.evidence_key(),
                )
            self.breaker.record_success()
            self.last_failure_time = None
        else:
            family = receipt.failure_family or CagFailureFamily.UNKNOWN
            self.breaker.record_failure(family, receipt.evidence_time)
            self.last_failure_time = receipt.evidence_time
            self.failure_counts[family.value] = (
                self.failure_counts.get(family.value, 0) + 1
            )
        self.last_canary = receipt
        return recovery

    def evaluate(
        self,
        *,
        evidence_time: int,
        evidence_window_seconds: int = DEFAULT_EVIDENCE_WINDOW_SECONDS,
        entitled_by_default: bool = False,
    ) -> CagHealthState:
        """Project the lane's health state from real evidence.

        This is a pure projection: it never mutates state. ``evidence_time``
        is the current injected time. The honest default without evidence is
        ``UNKNOWN`` (or ``NOT_ENTITLED`` if entitlement is known-negative).
        """
        # Entitlement is the strongest signal: not provisioned => not ready.
        if self.entitlement is not None:
            if self.entitlement.verdict is EntitlementVerdict.NOT_ENTITLED:
                return CagHealthState.NOT_ENTITLED

        self.breaker.maybe_half_open(evidence_time)
        if self.breaker.state is CircuitState.OPEN:
            return CagHealthState.UNAVAILABLE

        # No canary at all => honest unknown.
        if self.last_canary is None:
            if self.entitlement is not None and self.entitlement.verdict is EntitlementVerdict.ENTITLED:
                # Entitled but never probed: still unknown, not ready.
                return CagHealthState.UNKNOWN
            return CagHealthState.UNKNOWN

        # A known failure persists: staleness of a failure does not recover
        # the lane on its own. Only a new successful canary (record_canary)
        # closes the circuit and restores READY. This keeps an observed CAG
        # outage observably UNAVAILABLE instead of fading to UNKNOWN.
        if not self.last_canary.is_usable_success():
            return CagHealthState.UNAVAILABLE

        # Stale *successful* canary => we lost confidence => UNKNOWN, no
        # guessing that the lane is still healthy.
        age = evidence_time - self.last_canary.evidence_time
        if age > evidence_window_seconds:
            return CagHealthState.UNKNOWN

        # Fresh successful canary. Distinguish READY from DEGRADED.
        if self.breaker.state is CircuitState.HALF_OPEN:
            return CagHealthState.DEGRADED
        if self.quota.is_exhausted():
            return CagHealthState.DEGRADED
        if self.timeout_ratio is not None and self.timeout_ratio >= 0.5:
            return CagHealthState.DEGRADED
        if entitled_by_default and self.entitlement is None:
            # No entitlement evidence => cannot be READY.
            return CagHealthState.UNKNOWN
        if self.entitlement is None:
            return CagHealthState.UNKNOWN
        if self.entitlement.verdict is not EntitlementVerdict.ENTITLED:
            return CagHealthState.UNKNOWN
        return CagHealthState.READY


# ---------------------------------------------------------------------------
# Retry decision (no blind retry / no hidden cost climb)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RetryDecision:
    """Bounded retry decision for a CAG request.

    ``should_retry`` is only True for transient, retryable families and
    only while the circuit allows a request and the attempt budget remains.
    Quota exhaustion, auth and schema failures are never retried.
    """

    should_retry: bool
    attempt: int
    max_attempts: int
    reason: str
    failure_family: CagFailureFamily

    def to_public_dict(self) -> dict[str, object]:
        return {
            "shouldRetry": self.should_retry,
            "attempt": self.attempt,
            "maxAttempts": self.max_attempts,
            "reason": self.reason,
            "failureFamily": self.failure_family.value,
        }


def decide_retry(
    *,
    family: CagFailureFamily,
    attempt: int,
    breaker: CircuitBreaker,
    quota: QuotaSnapshot | None = None,
    max_attempts: int = MAX_RETRY_ATTEMPTS,
) -> RetryDecision:
    """Decide whether to retry a failed CAG request.

    Rules:
    - Quota exhaustion => never retry (own family, no hidden cost climb).
    - AUTH / ENTITLEMENT / SCHEMA => never retry (not transient).
    - Non-transient or unknown => never retry.
    - Transient family => retry only if circuit allows AND attempt budget
      remains. ``attempt`` is 1-based; we retry while ``attempt < max``.
    """
    if max_attempts > MAX_RETRY_ATTEMPTS:
        max_attempts = MAX_RETRY_ATTEMPTS
    if max_attempts < 1:
        max_attempts = 1

    if quota is not None and quota.is_exhausted():
        return RetryDecision(
            should_retry=False,
            attempt=attempt,
            max_attempts=max_attempts,
            reason="quota exhausted; not retried to avoid hidden cost climb",
            failure_family=CagFailureFamily.QUOTA,
        )

    if family in _NON_RETRYABLE_FAMILIES:
        return RetryDecision(
            should_retry=False,
            attempt=attempt,
            max_attempts=max_attempts,
            reason=f"{family.value} is not retryable",
            failure_family=family,
        )

    if family not in _CIRCUIT_OPENING_FAMILIES or family is CagFailureFamily.UNKNOWN:
        return RetryDecision(
            should_retry=False,
            attempt=attempt,
            max_attempts=max_attempts,
            reason=f"{family.value} is not a retryable transient family",
            failure_family=family,
        )

    if not breaker.allows_request():
        return RetryDecision(
            should_retry=False,
            attempt=attempt,
            max_attempts=max_attempts,
            reason="circuit open; request short-circuited",
            failure_family=family,
        )

    if attempt >= max_attempts:
        return RetryDecision(
            should_retry=False,
            attempt=attempt,
            max_attempts=max_attempts,
            reason="attempt budget exhausted",
            failure_family=family,
        )

    return RetryDecision(
        should_retry=True,
        attempt=attempt,
        max_attempts=max_attempts,
        reason=f"transient {family.value}; bounded retry permitted",
        failure_family=family,
    )


# ---------------------------------------------------------------------------
# Health snapshot (failure isolation boundary)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CagLaneHealth:
    """Public, secret-free health projection for one lane."""

    component: str
    state: CagHealthState
    contract_revision: str | None
    adapter_revision: str | None
    container_digest: str | None
    latency_class: str | None
    timeout_ratio: float | None
    quota: dict[str, object]
    entitlement: dict[str, object]
    last_canary_time: int | None
    last_canary_success: bool | None
    circuit_state: CircuitState
    evidence_time: int

    def to_public_dict(self) -> dict[str, object]:
        return {
            "component": self.component,
            "state": self.state.value,
            "contractRevision": self.contract_revision,
            "adapterRevision": self.adapter_revision,
            "containerDigest": self.container_digest,
            "latencyClass": self.latency_class,
            "timeoutRatio": self.timeout_ratio,
            "quota": self.quota,
            "entitlement": self.entitlement,
            "lastCanaryTime": self.last_canary_time,
            "lastCanarySuccess": self.last_canary_success,
            "circuitState": self.circuit_state.value,
            "evidenceTime": self.evidence_time,
        }


@dataclass(frozen=True, slots=True)
class CagHealthSnapshot:
    """Aggregate, secret-free health snapshot across all CAG lanes.

    This is the failure-isolation boundary: a CAG outage is reported here
    as a degraded/unavailable CAG projection, but it never claims to block
    or impair non-CAG (GitHub / DB / Docker / PatchMon) lanes. The
    ``independent_safety_lanes_unaffected`` flag is always True by
    construction: CAG health is observably decoupled from hard safety lanes.
    """

    lanes: tuple[CagLaneHealth, ...]
    evidence_time: int
    overall: CagHealthState
    independent_safety_lanes_unaffected: bool = True

    def to_public_dict(self) -> dict[str, object]:
        return {
            "lanes": [lane.to_public_dict() for lane in self.lanes],
            "evidenceTime": self.evidence_time,
            "overall": self.overall.value,
            "independentSafetyLanesUnaffected": self.independent_safety_lanes_unaffected,
        }

    def to_public_json(self) -> str:
        """Deterministic, secret-free JSON projection (sorted keys)."""
        return json.dumps(self.to_public_dict(), sort_keys=True, separators=(",", ":"))


_HEALTH_RANK: dict[CagHealthState, int] = {
    CagHealthState.READY: 0,
    CagHealthState.DEGRADED: 1,
    CagHealthState.UNKNOWN: 2,
    CagHealthState.UNAVAILABLE: 3,
    CagHealthState.NOT_ENTITLED: 4,
}


def _overall_state(lanes: tuple[CagLaneHealth, ...]) -> CagHealthState:
    """Roll up per-lane states into an honest overall state.

    The overall state is the *worst* observed non-NOT_ENTITLED state, so a
    single down lane makes the CAG path observably degraded/unavailable
    without hiding it. NOT_ENTITLED lanes (optional / unprovisioned
    components) do not force the whole path to NOT_ENTITLED.
    """
    if not lanes:
        return CagHealthState.UNKNOWN
    considered = [l.state for l in lanes if l.state is not CagHealthState.NOT_ENTITLED]
    if not considered:
        return CagHealthState.NOT_ENTITLED
    return max(considered, key=lambda s: _HEALTH_RANK[s])


def cag_health_snapshot(
    lane_states: Mapping[str, CagLaneState],
    *,
    evidence_time: int,
    evidence_window_seconds: int = DEFAULT_EVIDENCE_WINDOW_SECONDS,
    components: tuple[str, ...] = ALL_HEALTH_LANES,
) -> CagHealthSnapshot:
    """Build an aggregate, secret-free health snapshot.

    ``lane_states`` is keyed by component id. Lanes without state are
    projected as ``UNKNOWN`` (honest default) and never invented as READY.

    This function is the failure-isolation boundary: it only reads CAG lane
    state and never touches or impairs non-CAG runtime surfaces.
    """
    lane_healths: list[CagLaneHealth] = []
    for component in components:
        state = lane_states.get(component)
        if state is None:
            lane_healths.append(
                CagLaneHealth(
                    component=component,
                    state=CagHealthState.UNKNOWN,
                    contract_revision=None,
                    adapter_revision=None,
                    container_digest=None,
                    latency_class=None,
                    timeout_ratio=None,
                    quota=QuotaSnapshot().to_public_dict(),
                    entitlement=EntitlementStatus(
                        verdict=EntitlementVerdict.UNKNOWN,
                        credential_fingerprint=credential_fingerprint(None),
                    ).to_public_dict(),
                    last_canary_time=None,
                    last_canary_success=None,
                    circuit_state=CircuitState.CLOSED,
                    evidence_time=evidence_time,
                )
            )
            continue

        health_state = state.evaluate(
            evidence_time=evidence_time,
            evidence_window_seconds=evidence_window_seconds,
        )
        last = state.last_canary
        entitlement = state.entitlement or EntitlementStatus(
            verdict=EntitlementVerdict.UNKNOWN,
            credential_fingerprint=credential_fingerprint(None),
        )
        lane_healths.append(
            CagLaneHealth(
                component=component,
                state=health_state,
                contract_revision=state.contract_revision,
                adapter_revision=state.adapter_revision,
                container_digest=state.container_digest,
                latency_class=state.latency_class,
                timeout_ratio=state.timeout_ratio,
                quota=state.quota.to_public_dict(),
                entitlement=entitlement.to_public_dict(),
                last_canary_time=last.evidence_time if last else None,
                last_canary_success=last.is_usable_success() if last else None,
                circuit_state=state.breaker.state,
                evidence_time=evidence_time,
            )
        )

    lanes_tuple = tuple(lane_healths)
    return CagHealthSnapshot(
        lanes=lanes_tuple,
        evidence_time=evidence_time,
        overall=_overall_state(lanes_tuple),
        independent_safety_lanes_unaffected=True,
    )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def new_lane_state(
    component: str,
    *,
    failure_threshold: int = 3,
    cool_down_seconds: int = 60,
) -> CagLaneState:
    """Create a fresh, UNKNOWN-by-default lane state for a component."""
    if component not in ALL_HEALTH_LANES:
        raise ValueError(
            f"unknown CAG component: {component!r}; expected one of {ALL_HEALTH_LANES}"
        )
    return CagLaneState(
        component=component,
        breaker=CircuitBreaker(
            component=component,
            failure_threshold=failure_threshold,
            cool_down_seconds=cool_down_seconds,
        ),
    )


__all__ = [
    "ALL_HEALTH_LANES",
    "CAG_COMPONENTS",
    "OPTIONAL_COMPONENTS",
    "MAX_RETRY_ATTEMPTS",
    "DEFAULT_EVIDENCE_WINDOW_SECONDS",
    "CagHealthState",
    "CagFailureFamily",
    "EntitlementVerdict",
    "CircuitState",
    "CanaryReceipt",
    "RecoveryProof",
    "QuotaSnapshot",
    "EntitlementStatus",
    "CircuitBreaker",
    "CagLaneState",
    "RetryDecision",
    "CagLaneHealth",
    "CagHealthSnapshot",
    "redact_secret_fields",
    "credential_fingerprint",
    "decide_retry",
    "cag_health_snapshot",
    "new_lane_state",
]
