"""Deterministic claim-verification and computation evidence receipts for
Wolfram CAG (Issue #1460, parent epic #1457, depends on #1459).

This module turns CAG (Computational Authority Grounding) results into an
*independent evidence lane*: agent claims are verified against a normalized
CAG result instead of treating Wolfram output as blind truth. It produces a
versioned, closed ``WolframCagReceiptV1`` that binds every required
identity axis and yields an explicit verdict::

    SUPPORTED | CONTRADICTED | INCONCLUSIVE | UNAVAILABLE

Design rules (from #1460 acceptance criteria):

- **Versioned and closed schema.** ``SCHEMA_VERSION`` is the single
  contract string; ``to_receipt_dict`` emits a fixed key set and
  ``validate_closed`` rejects unknown fields. The schema is append-only:
  future changes require a new ``.v2`` module, never an in-place mutation.
- **Secret-free canonicalization.** Inputs and results are canonicalised
  (sorted UTF-8 JSON, floats serialised via ``repr`` to avoid float noise
  drift) and SHA-256 hashed. Secret-shaped fields are rejected at the
  boundary, never stored, logged or hashed in raw form.
- **Per-type precision / tolerance.** Each ``ResultType`` carries an
  explicit ``ToleranceRule`` (absolute, relative, exact flag). Float /
  precision differences are *evaluated* against that rule, never asserted
  as byte equality and never smoothed away.
- **Determinism, not wall-clock identity.** Two receipts with the same
  normalised input + same contract + same result type share a
  ``comparable_shape_key``. Wall-clock time is metadata only; it is never
  a causal identity and never equates two receipts.
- **CAG is a counter-check.** A CAG verdict never replaces PatchMon,
  GitHub, DB or container readback. ``independent_safety_lanes_unaffected``
  is always True by construction; the receipt carries an explicit
  ``does_not_replace`` notice.
- **Honest verdicts.** A missing provider result is ``UNAVAILABLE``; a
  result that cannot be mapped onto the claim's comparable axis is
  ``INCONCLUSIVE``. A claim that disagrees with the result beyond the
  tolerance rule is ``CONTRADICTED``. A contradiction between an LLM and
  CAG stays visible: the verdict is immutable and a Judge may not smooth
  ``CONTRADICTED`` toward ``SUPPORTED`` (``judge_may_not_smooth`` flag).
- **Attestation binding.** The receipt can be bound to an OTBA-style
  attestation (#1450) via ``bind_attestation`` without the receipt owning
  the attestation truth.

The module is pure stdlib: no network, no filesystem, no clock, no random.
All time is injected (``evidence_time``) so tests are deterministic.

Truth class: ``IMPLEMENTED_IN_REPOSITORY``. A receipt only becomes
``RUNTIME_VERIFIED`` after real provider + target-system readback, which is
deferred to #1458 / #1462 runtime work.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Mapping, Sequence

# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------
SCHEMA_VERSION: Final[str] = "sovereign.wolfram-cag-receipt.v1"

#: Canonicalisation contract string. Floats are serialised through
#: ``repr`` so that, e.g., ``3.14159`` and ``3.141590`` do not drift, while
#: genuinely different values remain distinguishable. Sorting is stable.
_CANONICALIZATION: Final[str] = "utf8-json-sorted-repr-floats-v1"

# ---------------------------------------------------------------------------
# Bounded limits
# ---------------------------------------------------------------------------
_MAX_EXPRESSION_BYTES: Final[int] = 8192
_MAX_ASSUMPTIONS: Final[int] = 32
_MAX_ASSUMPTION_BYTES: Final[int] = 512
_MAX_PROVENANCE_BYTES: Final[int] = 4096
_MAX_PROVENANCE_ITEMS: Final[int] = 16
_MAX_COST_META_BYTES: Final[int] = 2048
_MAX_ID_BYTES: Final[int] = 256

# ---------------------------------------------------------------------------
# Identifier / revision regex (shared shape with the evidence family)
# ---------------------------------------------------------------------------
_SHA40: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_SHA64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_IMAGE_DIGEST: Final[re.Pattern[str]] = re.compile(r"^sha256:[0-9a-f]{64}$")
_CONTRACT_REV: Final[re.Pattern[str]] = re.compile(
    r"^[a-z][a-z0-9_.\-:]{0,127}$"
)
# Provider request / response ids are opaque but bounded.
_PROVIDER_ID: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_.\-:]{1,128}$")

# ---------------------------------------------------------------------------
# Secret / sensitive material patterns (reject at boundary)
# ---------------------------------------------------------------------------
_SECRET_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"(?i)bearer\s+[a-z0-9\-._~+/]{8,}", re.IGNORECASE),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    re.compile(r"(?i)(password|passwd|secret|token|api[_\-]?key)\s*[:=]\s*\S{4,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]+ KEY-----"),
    re.compile(r"(?i)(postgres|mysql|mongodb)://[^@]+:[^@]+@"),
)

# Field names that may carry secret-shaped values.
_SECRET_FIELDS: Final[frozenset[str]] = frozenset(
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
        "cookie",
        "private_key",
    }
)

_REDACTED = "<redacted>"


class CagReceiptError(ValueError):
    """A receipt input violated a deterministic or secret-safety invariant."""


# ---------------------------------------------------------------------------
# Verdict (explicit truth classes, never a generic ``done``)
# ---------------------------------------------------------------------------

class CagVerdict(str, Enum):
    """Verdict of an agent claim against a CAG result.

    These are explicit, closed truth classes:

    - ``SUPPORTED``: the claim agrees with the CAG result within the
      per-type tolerance rule.
    - ``CONTRADICTED``: the claim disagrees with the CAG result beyond the
      tolerance rule. An LLM/CAG contradiction stays visible here and may
      not be smoothed by a Judge.
    - ``INCONCLUSIVE``: a result exists but the claim cannot be mapped onto
      a comparable axis (e.g. qualitative claim vs. numeric result, missing
      unit conversion factor). The claim is neither supported nor refuted.
    - ``UNAVAILABLE``: the provider returned no usable result (outage,
      quota, timeout, missing data). Technically not checkable via CAG.
    """

    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    UNAVAILABLE = "UNAVAILABLE"


# ---------------------------------------------------------------------------
# Normalised result type (mirrors the #1460 Prüffälle)
# ---------------------------------------------------------------------------

class ResultType(str, Enum):
    """Canonical CAG result type. Each carries its own tolerance rule."""

    EXACT_ARITHMETIC = "exact_arithmetic"
    SYMBOLIC_ALGEBRA = "symbolic_algebra"
    UNIT_DIMENSION = "unit_dimension"
    NUMERICAL_APPROXIMATION = "numerical_approximation"
    STATISTICS_DISTRIBUTION = "statistics_distribution"
    OPTIMIZATION_CONSTRAINT = "optimization_constraint"
    TIME_DATE = "time_date"
    STRUCTURED_FACT = "structured_fact"


# ---------------------------------------------------------------------------
# Per-type tolerance / precision rule
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ToleranceRule:
    """Explicit precision / tolerance rule for one result type.

    Float / precision differences are evaluated against this rule, never
    asserted as byte equality. ``exact`` True means the comparison is
    integer / canonical-string equality (tolerance fields are 0 and used
    only as a documented zero, not as a fuzzy band).
    """

    result_type: ResultType
    absolute: float
    relative: float
    exact: bool

    def within(self, a: float, b: float) -> bool:
        """Whether ``a`` and ``b`` agree under this rule."""
        if self.exact:
            return a == b
        diff = abs(a - b)
        if diff <= self.absolute:
            return True
        scale = max(abs(a), abs(b), 1.0)
        return diff <= self.relative * scale


#: Closed default table: one explicit rule per result type. A caller may
#: pass an override only for ``numerical_approximation`` /
#: ``statistics_distribution`` (caller-supplied precision is the contract);
#: for all other types the default is authoritative and closed.
_DEFAULT_TOLERANCE: Final[Mapping[ResultType, ToleranceRule]] = {
    ResultType.EXACT_ARITHMETIC: ToleranceRule(
        ResultType.EXACT_ARITHMETIC, absolute=0.0, relative=0.0, exact=True
    ),
    ResultType.SYMBOLIC_ALGEBRA: ToleranceRule(
        ResultType.SYMBOLIC_ALGEBRA, absolute=0.0, relative=0.0, exact=True
    ),
    ResultType.UNIT_DIMENSION: ToleranceRule(
        # Unit conversion may introduce float rounding; a defined tiny band
        # is *explicit* rather than asserting byte equality.
        ResultType.UNIT_DIMENSION, absolute=1e-9, relative=1e-9, exact=False
    ),
    ResultType.NUMERICAL_APPROXIMATION: ToleranceRule(
        # Default; callers normally override with an explicit precision.
        ResultType.NUMERICAL_APPROXIMATION,
        absolute=1e-6,
        relative=1e-6,
        exact=False,
    ),
    ResultType.STATISTICS_DISTRIBUTION: ToleranceRule(
        ResultType.STATISTICS_DISTRIBUTION,
        absolute=1e-6,
        relative=1e-6,
        exact=False,
    ),
    ResultType.OPTIMIZATION_CONSTRAINT: ToleranceRule(
        # Feasibility is exact (boolean); optimum value uses a small band.
        ResultType.OPTIMIZATION_CONSTRAINT,
        absolute=1e-9,
        relative=1e-9,
        exact=False,
    ),
    ResultType.TIME_DATE: ToleranceRule(
        # Compared at second granularity after timezone normalisation.
        ResultType.TIME_DATE, absolute=0.0, relative=0.0, exact=True
    ),
    ResultType.STRUCTURED_FACT: ToleranceRule(
        ResultType.STRUCTURED_FACT, absolute=0.0, relative=0.0, exact=True
    ),
}


def tolerance_for(
    result_type: ResultType,
    *,
    override: ToleranceRule | None = None,
) -> ToleranceRule:
    """Return the authoritative tolerance rule for a result type.

    Overrides are only honoured for the approximation / statistics families
    where caller-supplied precision *is* the contract; for all other types
    the closed default is authoritative, so a caller cannot loosen an exact
    comparison into a fuzzy one.
    """
    if override is not None and override.result_type is result_type:
        if result_type in (
            ResultType.NUMERICAL_APPROXIMATION,
            ResultType.STATISTICS_DISTRIBUTION,
        ):
            return override
    return _DEFAULT_TOLERANCE[result_type]


# ---------------------------------------------------------------------------
# Canonical SHA-256 helpers
# ---------------------------------------------------------------------------

def _canonical_json(value: object) -> str:
    """Deterministic JSON: sorted keys, ASCII, tight separators, floats via
    ``repr`` so equal-by-value floats serialise identically without losing
    distinguishability."""
    return json.dumps(
        value, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
        default=_json_default,
    )


def _json_default(obj: object) -> str:
    if isinstance(obj, Enum):
        return obj.value
    return str(obj)


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Secret guard
# ---------------------------------------------------------------------------

def _contains_secret(text: str) -> bool:
    return any(pat.search(text) for pat in _SECRET_PATTERNS)


def _assert_secret_free(text: str, *, field: str) -> None:
    if _contains_secret(text):
        raise CagReceiptError(
            f"{field} contains secret-shaped material and cannot be stored "
            "in a CAG receipt."
        )


def _redact_secret_fields(payload: Mapping[str, object]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in payload.items():
        if key.lower() in _SECRET_FIELDS:
            out[key] = _REDACTED
        else:
            out[key] = value
    return out


# ---------------------------------------------------------------------------
# Normalised input
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CagInput:
    """Normalised, secret-free CAG input bound to a contract.

    ``expression`` is the canonicalised query string (e.g. ``"2 + 2"``,
    ``"integrate x^2 dx"``, ``"population of Germany"``). ``units``,
    ``assumptions`` and ``domain`` carry the dimensional / modelling
    context the CAG provider resolved.
    """

    expression: str
    units: str | None = None
    assumptions: tuple[str, ...] = ()
    domain: str | None = None

    def __post_init__(self) -> None:
        if not self.expression:
            raise CagReceiptError("expression is required")
        if len(self.expression.encode("utf-8")) > _MAX_EXPRESSION_BYTES:
            raise CagReceiptError("expression exceeds the byte limit")
        _assert_secret_free(self.expression, field="expression")
        if self.units is not None:
            _assert_secret_free(self.units, field="units")
        if self.domain is not None:
            _assert_secret_free(self.domain, field="domain")
        if len(self.assumptions) > _MAX_ASSUMPTIONS:
            raise CagReceiptError("too many assumptions")
        for i, a in enumerate(self.assumptions):
            if not a:
                raise CagReceiptError(f"assumption {i} is empty")
            if len(a.encode("utf-8")) > _MAX_ASSUMPTION_BYTES:
                raise CagReceiptError(f"assumption {i} exceeds the byte limit")
            _assert_secret_free(a, field=f"assumption {i}")

    def canonical_dict(self) -> dict[str, object]:
        return {
            "expression": self.expression,
            "units": self.units,
            "assumptions": list(self.assumptions),
            "domain": self.domain,
        }

    def input_hash(self) -> str:
        """Secret-free SHA-256 over the canonical input."""
        return _canonical_sha256(self.canonical_dict())


# ---------------------------------------------------------------------------
# Provenance (for structured Wolfram|Alpha-style facts)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Provenance:
    """Herkunftsmetadaten for structured facts. Secret-free and bounded."""

    source: str
    retrieved_at: int | None = None
    source_url: str | None = None
    source_id: str | None = None
    extra: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source:
            raise CagReceiptError("provenance source is required")
        if len(self.source.encode("utf-8")) > _MAX_ID_BYTES:
            raise CagReceiptError("provenance source exceeds the byte limit")
        _assert_secret_free(self.source, field="provenance.source")
        if self.source_url is not None:
            _assert_secret_free(self.source_url, field="provenance.source_url")
        if self.source_id is not None:
            if not _PROVIDER_ID.match(self.source_id):
                raise CagReceiptError("provenance source_id is not a valid id")
        if len(self.extra) > _MAX_PROVENANCE_ITEMS:
            raise CagReceiptError("too many provenance extras")
        for k, v in self.extra.items():
            if not isinstance(v, str):
                raise CagReceiptError("provenance extra values must be strings")
            _assert_secret_free(v, field=f"provenance.extra.{k}")

    def canonical_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "retrievedAt": self.retrieved_at,
            "sourceUrl": self.source_url,
            "sourceId": self.source_id,
            "extra": dict(sorted(self.extra.items())),
        }


# ---------------------------------------------------------------------------
# Cost / quota metadata (secret-free)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CostMetadata:
    """Optional runtime / cost / quota metadata. All fields optional.

    No raw credential ever appears here. ``cost_unit`` is an opaque
    contract string (e.g. ``"credits"``) and carries no monetary claim.
    """

    runtime_ms: int | None = None
    cost_unit: str | None = None
    cost_per_unit: float | None = None
    units_consumed: float | None = None
    quota_remaining: float | None = None

    def canonical_dict(self) -> dict[str, object]:
        return {
            "runtimeMs": self.runtime_ms,
            "costUnit": self.cost_unit,
            "costPerUnit": self.cost_per_unit,
            "unitsConsumed": self.units_consumed,
            "quotaRemaining": self.quota_remaining,
        }


# ---------------------------------------------------------------------------
# Normalised CAG result + agent claim
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CagResult:
    """Normalised CAG result for one result type.

    ``canonical_value`` is the canonical string form (exact integers,
    normalised symbolic form, ISO-8601 timestamp, structured fact key).
    ``numeric_value`` is the float projection used for tolerance-based
    comparison (may be ``None`` for purely symbolic / structured results).
    ``units`` is the result's unit string. ``available`` is False when the
    provider returned no usable result.
    """

    result_type: ResultType
    canonical_value: str | None
    numeric_value: float | None = None
    units: str | None = None
    available: bool = True
    provenance: Provenance | None = None
    raw: str | None = None

    def __post_init__(self) -> None:
        if self.available and not self.canonical_value:
            raise CagReceiptError(
                "an available result requires a canonical_value"
            )
        if self.canonical_value is not None:
            if len(self.canonical_value.encode("utf-8")) > _MAX_EXPRESSION_BYTES:
                raise CagReceiptError("canonical_value exceeds the byte limit")
            _assert_secret_free(self.canonical_value, field="canonical_value")
        if self.units is not None:
            _assert_secret_free(self.units, field="result.units")
        if self.raw is not None:
            if len(self.raw.encode("utf-8")) > _MAX_EXPRESSION_BYTES:
                raise CagReceiptError("raw result exceeds the byte limit")
            _assert_secret_free(self.raw, field="raw")

    def canonical_dict(self) -> dict[str, object]:
        return {
            "resultType": self.result_type.value,
            "canonicalValue": self.canonical_value,
            "numericValue": self.numeric_value,
            "units": self.units,
            "available": self.available,
            "provenance": (
                self.provenance.canonical_dict() if self.provenance else None
            ),
            # ``raw`` is intentionally excluded from the canonical hash: it
            # is debugging context only, never a truth identity.
        }

    def result_hash(self) -> str:
        """Secret-free SHA-256 over the canonical result (excludes raw)."""
        return _canonical_sha256(self.canonical_dict())


@dataclass(frozen=True, slots=True)
class CagClaim:
    """An agent's verifiable claim to be checked against the CAG result.

    ``claim_value`` is the canonical string the agent asserted.
    ``claim_numeric`` is its float projection (for tolerance comparison).
    ``claim_units`` is the agent's asserted units. For
    ``optimization_constraint`` claims, ``feasible`` carries the agent's
    feasibility assertion. At least one of ``claim_value``,
    ``claim_numeric`` or ``feasible`` must be set; a numeric-only claim
    (e.g. ``π ≈ 3.14159``) is allowed without a canonical string.
    """

    claim_value: str | None = None
    claim_numeric: float | None = None
    claim_units: str | None = None
    feasible: bool | None = None

    def __post_init__(self) -> None:
        if self.claim_value is None and self.claim_numeric is None and self.feasible is None:
            raise CagReceiptError(
                "a claim must carry a value, numeric value or feasibility"
            )
        if self.claim_value is not None:
            if len(self.claim_value.encode("utf-8")) > _MAX_EXPRESSION_BYTES:
                raise CagReceiptError("claim_value exceeds the byte limit")
            _assert_secret_free(self.claim_value, field="claim_value")
        if self.claim_units is not None:
            _assert_secret_free(self.claim_units, field="claim_units")

    def canonical_dict(self) -> dict[str, object]:
        return {
            "claimValue": self.claim_value,
            "claimNumeric": self.claim_numeric,
            "claimUnits": self.claim_units,
            "feasible": self.feasible,
        }


# ---------------------------------------------------------------------------
# The versioned, closed receipt
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class WolframCagReceiptV1:
    """Versioned, closed CAG evidence receipt (Issue #1460).

    Binds: Sovereign run / tool chain / step; repository / runtime
    revision; component + endpoint / contract version; normalised input +
    input hash; units / assumptions / domain; time / output limits;
    provider request / response id; normalised result type + result hash;
    tolerance rule; runtime + cost / quota metadata; verdict. All hashes
    are secret-free and deterministic.

    A CAG verdict never replaces PatchMon, GitHub, DB or container readback
    (``independent_safety_lanes_unaffected`` is always True; a Judge may
    not smooth ``CONTRADICTED`` — ``judge_may_not_smooth`` is True).
    """

    # Identity binding
    sovereign_run: str
    tool_chain: str
    step: str
    repository_revision: str | None
    runtime_revision: str | None
    component: str
    endpoint_contract_version: str

    # Input
    cag_input: CagInput

    # Limits
    time_limit_ms: int | None
    output_limit_bytes: int | None

    # Provider ids (opaque, secret-free)
    provider_request_id: str | None
    provider_response_id: str | None

    # Result
    cag_result: CagResult
    claim: CagClaim

    # Tolerance
    tolerance: ToleranceRule

    # Cost / quota
    cost: CostMetadata

    # Verdict
    verdict: CagVerdict
    verdict_reason: str

    # Time (metadata only, never causal identity)
    evidence_time: int

    # Attestation binding (OTBA-style, #1450). None until explicitly bound.
    attestation_id: str | None = None
    attestation_hash: str | None = None

    # Immutable truth-class flags
    independent_safety_lanes_unaffected: bool = True
    judge_may_not_smooth: bool = True
    does_not_replace: tuple[str, ...] = (
        "patchmon",
        "github",
        "database",
        "container_readback",
    )

    def __post_init__(self) -> None:
        for name, val in (
            ("sovereign_run", self.sovereign_run),
            ("tool_chain", self.tool_chain),
            ("step", self.step),
            ("component", self.component),
            ("endpoint_contract_version", self.endpoint_contract_version),
        ):
            if not val:
                raise CagReceiptError(f"{name} is required")
            if len(val.encode("utf-8")) > _MAX_ID_BYTES:
                raise CagReceiptError(f"{name} exceeds the byte limit")
        if not _CONTRACT_REV.match(self.endpoint_contract_version):
            raise CagReceiptError(
                "endpoint_contract_version is not a valid contract revision"
            )
        for label, rev in (
            ("repository_revision", self.repository_revision),
            ("runtime_revision", self.runtime_revision),
        ):
            if rev is not None and not (
                _SHA40.match(rev) or _SHA64.match(rev) or _IMAGE_DIGEST.match(rev)
            ):
                raise CagReceiptError(
                    f"{label} must be a 40/64-char hex sha or image digest"
                )
        for label, pid in (
            ("provider_request_id", self.provider_request_id),
            ("provider_response_id", self.provider_response_id),
        ):
            if pid is not None and not _PROVIDER_ID.match(pid):
                raise CagReceiptError(f"{label} is not a valid provider id")
        if self.tolerance.result_type is not self.cag_result.result_type:
            raise CagReceiptError(
                "tolerance result_type must match the CAG result type"
            )
        if self.attestation_id is not None and not self.attestation_hash:
            raise CagReceiptError(
                "attestation_hash is required when attestation_id is set"
            )
        if self.attestation_hash is not None and not (
            _SHA64.match(self.attestation_hash)
        ):
            raise CagReceiptError("attestation_hash must be a 64-char hex sha")

    # -- deterministic hashes ------------------------------------------------

    def input_hash(self) -> str:
        return self.cag_input.input_hash()

    def result_hash(self) -> str:
        return self.cag_result.result_hash()

    def comparable_shape_key(self) -> str:
        """Deterministic key for *comparable shape*, not causal identity.

        Same normalised input + same contract + same result type => same
        key. Float noise in the result value does NOT change this key, so
        two receipts over the same shape are comparable without asserting
        byte equality of their float projections.
        """
        parts = {
            "inputHash": self.input_hash(),
            "contract": self.endpoint_contract_version,
            "resultType": self.cag_result.result_type.value,
        }
        return "sha256:" + _canonical_sha256(parts)[:32]

    def receipt_hash(self) -> str:
        """Tamper-evident SHA-256 over the closed receipt body.

        Computed over the body *without* the ``receiptHash`` field itself,
        so the hash is self-consistent (no recursion) and any mutation of
        any bound field invalidates it.
        """
        return _canonical_sha256(self._body_dict())

    def _body_dict(self) -> dict[str, object]:
        """The closed receipt body excluding the self-referential
        ``receiptHash`` field."""
        return {
            "schemaVersion": SCHEMA_VERSION,
            "canonicalization": _CANONICALIZATION,
            "sovereignRun": self.sovereign_run,
            "toolChain": self.tool_chain,
            "step": self.step,
            "repositoryRevision": self.repository_revision,
            "runtimeRevision": self.runtime_revision,
            "component": self.component,
            "endpointContractVersion": self.endpoint_contract_version,
            "input": self.cag_input.canonical_dict(),
            "inputHash": self.input_hash(),
            "timeLimitMs": self.time_limit_ms,
            "outputLimitBytes": self.output_limit_bytes,
            "providerRequestId": self.provider_request_id,
            "providerResponseId": self.provider_response_id,
            "result": self.cag_result.canonical_dict(),
            "resultHash": self.result_hash(),
            "comparableShapeKey": self.comparable_shape_key(),
            "claim": self.claim.canonical_dict(),
            "tolerance": {
                "resultType": self.tolerance.result_type.value,
                "absolute": self.tolerance.absolute,
                "relative": self.tolerance.relative,
                "exact": self.tolerance.exact,
            },
            "cost": self.cost.canonical_dict(),
            "verdict": self.verdict.value,
            "verdictReason": self.verdict_reason,
            "evidenceTime": self.evidence_time,
            "attestationId": self.attestation_id,
            "attestationHash": self.attestation_hash,
            "independentSafetyLanesUnaffected": (
                self.independent_safety_lanes_unaffected
            ),
            "judgeMayNotSmooth": self.judge_may_not_smooth,
            "doesNotReplace": list(self.does_not_replace),
        }

    # -- closed projection ---------------------------------------------------

    def to_receipt_dict(self) -> dict[str, object]:
        """Closed, versioned, secret-free projection.

        The key set is fixed by the schema version; ``validate_closed``
        rejects any dict with extra keys.
        """
        body = self._body_dict()
        body["receiptHash"] = self.receipt_hash()
        return body

    def to_public_json(self) -> str:
        """Deterministic, secret-free JSON projection (sorted keys)."""
        return json.dumps(
            self.to_receipt_dict(),
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        )

    def bind_attestation(
        self, *, attestation_id: str, attestation_hash: str
    ) -> "WolframCagReceiptV1":
        """Return a new receipt bound to an OTBA-style attestation (#1450).

        The receipt does not own the attestation truth; it only records the
        binding so a downstream Judge can correlate. The attestation hash
        is a 64-char hex sha; the raw attestation blob never enters the
        receipt.
        """
        if not attestation_id:
            raise CagReceiptError("attestation_id is required")
        if not _PROVIDER_ID.match(attestation_id):
            raise CagReceiptError("attestation_id is not a valid id")
        if not _SHA64.match(attestation_hash):
            raise CagReceiptError("attestation_hash must be a 64-char hex sha")
        # Replace rather than mutate (frozen dataclass).
        import dataclasses as _dc

        return _dc.replace(
            self,
            attestation_id=attestation_id,
            attestation_hash=attestation_hash,
        )


# ---------------------------------------------------------------------------
# Closed-schema validation
# ---------------------------------------------------------------------------

_CLOSED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schemaVersion",
        "canonicalization",
        "sovereignRun",
        "toolChain",
        "step",
        "repositoryRevision",
        "runtimeRevision",
        "component",
        "endpointContractVersion",
        "input",
        "inputHash",
        "timeLimitMs",
        "outputLimitBytes",
        "providerRequestId",
        "providerResponseId",
        "result",
        "resultHash",
        "comparableShapeKey",
        "claim",
        "tolerance",
        "cost",
        "verdict",
        "verdictReason",
        "evidenceTime",
        "attestationId",
        "attestationHash",
        "independentSafetyLanesUnaffected",
        "judgeMayNotSmooth",
        "doesNotReplace",
        "receiptHash",
    }
)


def validate_closed(payload: Mapping[str, object]) -> None:
    """Reject any payload whose keys are not exactly the closed v1 key set.

    The schema is closed: adding a field requires a new ``.v2`` module, so
    a caller / Judge cannot smuggle extra truth into a v1 receipt.
    """
    keys = set(payload.keys())
    extra = keys - _CLOSED_KEYS
    if extra:
        raise CagReceiptError(
            f"receipt payload has unknown keys for {SCHEMA_VERSION}: "
            f"{sorted(extra)}"
        )
    missing = _CLOSED_KEYS - keys
    if missing:
        raise CagReceiptError(
            f"receipt payload is missing closed-schema keys: {sorted(missing)}"
        )
    if payload.get("schemaVersion") != SCHEMA_VERSION:
        raise CagReceiptError(
            f"schemaVersion must be {SCHEMA_VERSION!r} for this lane"
        )


# ---------------------------------------------------------------------------
# Verdict computation (the counter-check)
# ---------------------------------------------------------------------------

def _can_compare_units(
    claim: CagClaim, result: CagResult, *, factor: float | None
) -> bool:
    if claim.claim_units is None or result.units is None:
        return True
    if claim.claim_units == result.units:
        return True
    return factor is not None


def compute_verdict(
    *,
    claim: CagClaim,
    result: CagResult,
    tolerance: ToleranceRule,
    unit_conversion_factor: float | None = None,
) -> tuple[CagVerdict, str]:
    """Compute the verdict of ``claim`` against ``result``.

    - No available result => ``UNAVAILABLE``.
    - Claim and result not on a comparable axis => ``INCONCLUSIVE``.
    - Within tolerance => ``SUPPORTED``; otherwise ``CONTRADICTED``.

    The verdict is a pure function of (claim, result, tolerance, factor);
    no wall-clock, no network, no smoothing toward SUPPORTED.
    """
    if not result.available or result.canonical_value is None:
        return (
            CagVerdict.UNAVAILABLE,
            "provider returned no usable result; claim is technically "
            "not checkable via CAG",
        )

    rt = result.result_type

    # Optimization / constraint: feasibility is a boolean axis.
    if rt is ResultType.OPTIMIZATION_CONSTRAINT:
        if claim.feasible is None and claim.claim_numeric is None:
            return (
                CagVerdict.INCONCLUSIVE,
                "claim carries neither feasibility nor an optimum value; "
                "no comparable axis",
            )
        if claim.feasible is not None:
            # Feasibility is stored in canonical_value as "feasible"/"infeasible".
            res_feasible = result.canonical_value.strip().lower() == "feasible"
            if claim.feasible != res_feasible:
                return (
                    CagVerdict.CONTRADICTED,
                    "claim feasibility contradicts the CAG feasibility verdict",
                )
            if claim.claim_numeric is None:
                return (
                    CagVerdict.SUPPORTED,
                    "claim feasibility agrees with the CAG feasibility verdict",
                )
        # Fall through to optimum-value comparison if a numeric optimum was claimed.
        if claim.claim_numeric is not None and result.numeric_value is not None:
            if tolerance.within(claim.claim_numeric, result.numeric_value):
                return (
                    CagVerdict.SUPPORTED,
                    "claim optimum value agrees with the CAG result within "
                    "the tolerance rule",
                )
            return (
                CagVerdict.CONTRADICTED,
                "claim optimum value disagrees with the CAG result beyond "
                "the tolerance rule",
            )
        return (
            CagVerdict.INCONCLUSIVE,
            "result carries no numeric optimum to compare against the claim",
        )

    # Structured fact: exact canonical-string equality.
    if rt is ResultType.STRUCTURED_FACT:
        if claim.claim_value is None:
            return (
                CagVerdict.INCONCLUSIVE,
                "claim carries no value to match a structured fact",
            )
        if claim.claim_value.strip() == result.canonical_value.strip():
            return (
                CagVerdict.SUPPORTED,
                "claim matches the structured CAG fact exactly",
            )
        return (
            CagVerdict.CONTRADICTED,
            "claim contradicts the structured CAG fact",
        )

    # Symbolic / exact arithmetic: canonical-string equality.
    if rt in (ResultType.SYMBOLIC_ALGEBRA, ResultType.EXACT_ARITHMETIC):
        if claim.claim_value is None and claim.claim_numeric is None:
            return (
                CagVerdict.INCONCLUSIVE,
                "claim carries no value to compare against the exact result",
            )
        if claim.claim_value is not None:
            if claim.claim_value.strip() == result.canonical_value.strip():
                return (
                    CagVerdict.SUPPORTED,
                    "claim canonical value equals the exact CAG result",
                )
            return (
                CagVerdict.CONTRADICTED,
                "claim canonical value contradicts the exact CAG result",
            )
        # Numeric projection of an exact result: compare exactly.
        if result.numeric_value is not None and claim.claim_numeric is not None:
            if tolerance.within(claim.claim_numeric, result.numeric_value):
                return (
                    CagVerdict.SUPPORTED,
                    "claim numeric projection equals the exact CAG result",
                )
            return (
                CagVerdict.CONTRADICTED,
                "claim numeric projection contradicts the exact CAG result",
            )
        return (
            CagVerdict.INCONCLUSIVE,
            "result carries no comparable numeric projection",
        )

    # Time / date: canonical ISO-8601 string equality (timezone-normalised).
    if rt is ResultType.TIME_DATE:
        if claim.claim_value is None:
            return (
                CagVerdict.INCONCLUSIVE,
                "claim carries no date/time value to compare",
            )
        if claim.claim_value.strip() == result.canonical_value.strip():
            return (
                CagVerdict.SUPPORTED,
                "claim date/time equals the normalised CAG result",
            )
        return (
            CagVerdict.CONTRADICTED,
            "claim date/time contradicts the normalised CAG result",
        )

    # Numeric / unit / statistics: tolerance-based comparison.
    if rt in (
        ResultType.NUMERICAL_APPROXIMATION,
        ResultType.UNIT_DIMENSION,
        ResultType.STATISTICS_DISTRIBUTION,
    ):
        if claim.claim_numeric is None or result.numeric_value is None:
            return (
                CagVerdict.INCONCLUSIVE,
                "claim and result are not both on a numeric comparable axis",
            )
        if not _can_compare_units(claim, result, factor=unit_conversion_factor):
            return (
                CagVerdict.INCONCLUSIVE,
                "claim and result units differ and no conversion factor "
                "is declared; cannot compare",
            )
        claim_val = claim.claim_numeric
        if (
            rt is ResultType.UNIT_DIMENSION
            and unit_conversion_factor is not None
            and claim.claim_units is not None
            and result.units is not None
            and claim.claim_units != result.units
        ):
            claim_val = claim.claim_numeric * unit_conversion_factor
        if tolerance.within(claim_val, result.numeric_value):
            return (
                CagVerdict.SUPPORTED,
                "claim agrees with the CAG result within the tolerance rule",
            )
        return (
            CagVerdict.CONTRADICTED,
            "claim disagrees with the CAG result beyond the tolerance rule",
        )

    return (
        CagVerdict.INCONCLUSIVE,
        f"no comparison rule is defined for result type {rt.value}",
    )


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_receipt(
    *,
    sovereign_run: str,
    tool_chain: str,
    step: str,
    repository_revision: str | None,
    runtime_revision: str | None,
    component: str,
    endpoint_contract_version: str,
    cag_input: CagInput,
    cag_result: CagResult,
    claim: CagClaim,
    time_limit_ms: int | None = None,
    output_limit_bytes: int | None = None,
    provider_request_id: str | None = None,
    provider_response_id: str | None = None,
    cost: CostMetadata | None = None,
    evidence_time: int,
    tolerance_override: ToleranceRule | None = None,
    unit_conversion_factor: float | None = None,
) -> WolframCagReceiptV1:
    """Validate inputs, compute the verdict and build a closed receipt.

    The verdict is computed *from* the claim and result; it is never an
    input. This keeps the counter-check honest: a caller cannot inject a
    ``SUPPORTED`` verdict for a contradicted claim.
    """
    tolerance = tolerance_for(
        cag_result.result_type, override=tolerance_override
    )
    verdict, reason = compute_verdict(
        claim=claim,
        result=cag_result,
        tolerance=tolerance,
        unit_conversion_factor=unit_conversion_factor,
    )
    return WolframCagReceiptV1(
        sovereign_run=sovereign_run,
        tool_chain=tool_chain,
        step=step,
        repository_revision=repository_revision,
        runtime_revision=runtime_revision,
        component=component,
        endpoint_contract_version=endpoint_contract_version,
        cag_input=cag_input,
        time_limit_ms=time_limit_ms,
        output_limit_bytes=output_limit_bytes,
        provider_request_id=provider_request_id,
        provider_response_id=provider_response_id,
        cag_result=cag_result,
        claim=claim,
        tolerance=tolerance,
        cost=cost or CostMetadata(),
        verdict=verdict,
        verdict_reason=reason,
        evidence_time=evidence_time,
    )


__all__ = [
    "SCHEMA_VERSION",
    "CagReceiptError",
    "CagVerdict",
    "ResultType",
    "ToleranceRule",
    "tolerance_for",
    "CagInput",
    "Provenance",
    "CostMetadata",
    "CagResult",
    "CagClaim",
    "WolframCagReceiptV1",
    "validate_closed",
    "compute_verdict",
    "build_receipt",
]
