"""Deterministic Wolfram CAG claim verification and computation evidence receipts.

This module implements the evidence/judge lane for issue #1460 of the
Wolfram CAG foundation epic (#1457). It consumes the bounded, secret-free
transport evidence produced by the CAG Component adapter (#1459) and turns a
CAG result plus an agent claim into a versioned, hash-bound, secret-free
``WolframCagReceiptV1`` carrying one verdict::

    SUPPORTED | CONTRADICTED | INCONCLUSIVE | UNAVAILABLE

Truth boundaries (see #1457 / #1460)
------------------------------------
- A CAG result is a *counter-check*. It is never allowed to self-assert
  ``VERIFIED``; that truth class stays reserved for the Sovereign
  evidence/judge / proof-verdict lane. This module deliberately exposes no
  ``VERIFIED`` member.
- No mocks or stubs live in the truth path. Without a real transport receipt
  that carries a READY component and a real result, the honest verdict is
  ``UNAVAILABLE`` / ``INCONCLUSIVE``.
- No secret value is ever returned, logged, hashed or persisted. Inputs and
  results are canonicalized through a secret-guarded, allowlist-filtered
  canonicalizer before hashing.
- Input, component, contract version, request/response metadata and result are
  hash/revision bound. Float/precision differences are never claimed as byte
  equality; they are evaluated against explicit, per-result-type tolerance
  rules.
- A CAG receipt can never replace PatchMon, GitHub, DB, container or runtime
  readback evidence. It is bounded compute/knowledge evidence only.
- No wall-clock time is used as causal identity; ``recorded_at`` is optional,
  non-canonical provenance and excluded from the receipt hash.

The module is pure stdlib and performs no network, filesystem, clock or random
access. It accepts only canonical observations produced elsewhere.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final, Mapping, Sequence

# ---------------------------------------------------------------------------
# Schema + identity constants
# ---------------------------------------------------------------------------

RECEIPT_SCHEMA_VERSION: Final[str] = "sovereign.wolfram-cag-receipt.v1"
CONTRACT_VERSION: Final[str] = "wolfram-cag-transport.v1"

# The four provisioned CAG Component APIs (mirror of the transport adapter).
CAG_COMPONENTS: Final[tuple[str, ...]] = (
    "wolfram.cag.hints",
    "wolfram.cag.compute",
    "wolfram.cag.results",
    "wolfram.cag.context",
)

# Canonical result types a normalized CAG result may carry.
RESULT_TYPES: Final[tuple[str, ...]] = (
    "exact_number",
    "symbolic_expression",
    "unit_dimension",
    "unit_conversion",
    "numeric_approximation",
    "statistic",
    "optimization",
    "datetime_calculation",
    "structured_fact",
    "text_hint",
)

_HASH64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_SHA40: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_COMPONENT_ID: Final[re.Pattern[str]] = re.compile(r"^wolfram\.cag\.(hints|compute|results|context)$")
_RESULT_TYPE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_IDENTIFIER: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,119}$")
_BOUND_SUMMARY: Final[re.Pattern[str]] = re.compile(r"[\x00-\x1f\x7f]")

# Secret-shaped field markers, mirroring the agent-run-receipt contract. Any
# field whose casefolded key contains one of these markers is rejected unless
# it is a known safe boolean.
_SECRET_KEY_MARKERS: Final[tuple[str, ...]] = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "private_key",
    "client_secret",
    "cookie",
    "raw_prompt",
    "prompt_text",
    "file_content",
    "database_row",
)
_SECRET_SAFE_BOOLEAN_KEYS: Final[frozenset[str]] = frozenset({
    "secretvaluesreturned",
    "secret_values_returned",
    "rawsecretspersisted",
    "raw_secrets_persisted",
    "mcp_revision_verified",
})

# Implicit time fields are forbidden inside canonicalized values so that no
# wall-clock value can become causal identity.
_IMPLICIT_TIME_KEYS: Final[frozenset[str]] = frozenset({
    "created_at",
    "current_time",
    "epoch",
    "now",
    "observed_at",
    "timestamp",
    "updated_at",
})

TRUTH_NOTICE: Final[str] = (
    "CAG evidence is a supplemental compute/knowledge counter-check. It cannot "
    "verify repository, runtime, deployment, PatchMon, ARE or Kappa truth, and "
    "no CAG result may self-assert VERIFIED."
)


class CagEvidenceError(ValueError):
    """A CAG evidence input violated a deterministic or truth-boundary invariant."""


class CagEvidenceVerdict(str, Enum):
    """Bounded verdicts for a CAG-backed claim check.

    There is intentionally no ``VERIFIED`` member. ``VERIFIED`` is reserved for
    the Sovereign proof-verdict / evidence lane and can never be produced by a
    CAG result alone.
    """

    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    UNAVAILABLE = "UNAVAILABLE"


# ---------------------------------------------------------------------------
# Secret-safe canonicalization
# ---------------------------------------------------------------------------

def _normalize_text(value: str, label: str, *, maximum: int = 2000) -> str:
    normalized = unicodedata.normalize("NFC", str(value or "")).strip()
    if not normalized:
        raise CagEvidenceError(f"{label} must contain at least one non-whitespace character")
    if len(normalized) > maximum:
        raise CagEvidenceError(f"{label} must not exceed {maximum} characters")
    if _BOUND_SUMMARY.search(normalized):
        raise CagEvidenceError(f"{label} must not contain control characters")
    return normalized


def _normalize_identifier(value: str, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _IDENTIFIER.fullmatch(normalized):
        raise CagEvidenceError(f"{label} must be a canonical identifier")
    return normalized


def _normalize_component(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _COMPONENT_ID.fullmatch(normalized):
        raise CagEvidenceError("component_id must be one of the four CAG components")
    return normalized


def _normalize_result_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _RESULT_TYPE.fullmatch(normalized):
        raise CagEvidenceError("result_type must be a canonical result type identifier")
    if normalized not in RESULT_TYPES:
        raise CagEvidenceError(f"result_type must be one of {RESULT_TYPES}")
    return normalized


def _normalize_sha64(value: str, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _HASH64.fullmatch(normalized):
        raise CagEvidenceError(f"{label} must be a lowercase SHA-256")
    return normalized


def _normalize_optional_sha64(value: str, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return ""
    if not _HASH64.fullmatch(normalized):
        raise CagEvidenceError(f"{label} must be a lowercase SHA-256 or empty")
    return normalized


def _normalize_revision(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return ""
    if not _SHA40.fullmatch(normalized):
        raise CagEvidenceError("runtime_revision must be a lowercase full Git SHA or empty")
    return normalized


def _reject_implicit_time(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            if not isinstance(raw_key, str):
                raise CagEvidenceError(f"non-string object key is forbidden at {path}")
            if raw_key.strip().lower() in _IMPLICIT_TIME_KEYS:
                raise CagEvidenceError(f"implicit time field is forbidden at {path}.{raw_key}")
            _reject_implicit_time(item, path=f"{path}.{raw_key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _reject_implicit_time(item, path=f"{path}[{index}]")


def canonical_cag_value(value: Any, *, path: str = "$") -> Any:
    """Return a JSON-safe, secret-guarded canonical value or fail closed.

    Floats are rejected (precision is handled via explicit tolerance rules, not
    via byte equality). Secret-shaped keys are forbidden unless they are a
    known safe boolean. Implicit time keys are forbidden so no wall-clock value
    can become causal identity.
    """
    _reject_implicit_time(value, path=path)
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        raise CagEvidenceError(f"floating-point value is forbidden at {path}; use tolerance rules")
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, bytes):
        return {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for raw_key, item in value.items():
            if not isinstance(raw_key, str):
                raise CagEvidenceError(f"non-string object key is forbidden at {path}")
            key = unicodedata.normalize("NFC", raw_key)
            folded = key.casefold()
            if any(marker in folded for marker in _SECRET_KEY_MARKERS):
                if folded not in _SECRET_SAFE_BOOLEAN_KEYS or not isinstance(item, bool):
                    raise CagEvidenceError(f"secret-shaped field is forbidden at {path}.{key}")
            output[key] = canonical_cag_value(item, path=f"{path}.{key}")
        return output
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [canonical_cag_value(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    raise CagEvidenceError(f"unsupported canonical type {type(value).__name__} at {path}")


def canonical_cag_bytes(value: Any) -> bytes:
    normalized = canonical_cag_value(value)
    _reject_implicit_time(normalized)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_cag_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_cag_bytes(value)).hexdigest()


# ---------------------------------------------------------------------------
# Tolerance rules
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ToleranceRule:
    """Explicit numeric tolerance/precision rule per result type.

    ``absolute`` and ``relative`` are mutually interpretable: a numeric claim
    is SUPPORTED when ``abs(claim - reference) <= absolute + relative * abs(reference)``.
    ``significant_digits`` (>=1) bounds the number of significant digits that
    may be compared before the tolerance rule takes over.
    """

    absolute: str = "0"
    relative: str = "0"
    significant_digits: int = 6

    def __post_init__(self) -> None:
        abs_value = self._parse_decimal(self.absolute, "absolute")
        rel_value = self._parse_decimal(self.relative, "relative")
        if abs_value < 0 or rel_value < 0:
            raise CagEvidenceError("tolerance values must be non-negative")
        if isinstance(self.significant_digits, bool) or not isinstance(self.significant_digits, int):
            raise CagEvidenceError("significant_digits must be an integer")
        if self.significant_digits < 1 or self.significant_digits > 18:
            raise CagEvidenceError("significant_digits must be in 1..18")

    @staticmethod
    def _parse_decimal(value: str, label: str) -> float:
        text = str(value or "").strip()
        if not text:
            return 0.0
        try:
            parsed = float(text)
        except (TypeError, ValueError) as exc:
            raise CagEvidenceError(f"{label} must be a decimal string") from exc
        if math.isnan(parsed) or math.isinf(parsed):
            raise CagEvidenceError(f"{label} must be finite")
        return parsed

    def canonical_body(self) -> dict[str, Any]:
        return {
            "absolute": str(self.absolute),
            "relative": str(self.relative),
            "significant_digits": int(self.significant_digits),
        }

    def within(self, claim: float, reference: float) -> bool:
        """True when ``claim`` is within tolerance of ``reference``."""
        if math.isnan(claim) or math.isnan(reference) or math.isinf(claim) or math.isinf(reference):
            return False
        abs_tol = self._parse_decimal(self.absolute, "absolute")
        rel_tol = self._parse_decimal(self.relative, "relative")
        return abs(claim - reference) <= abs_tol + rel_tol * abs(reference)


# Default tolerance rules per result type. Exact/symbolic/unit/statistic/
# datetime/fact types default to exact comparison; numeric_approximation and
# optimization default to a bounded relative tolerance.
DEFAULT_TOLERANCE_RULES: Final[Mapping[str, ToleranceRule]] = {
    "exact_number": ToleranceRule("0", "0", 18),
    "symbolic_expression": ToleranceRule("0", "0", 18),
    "unit_dimension": ToleranceRule("0", "0", 12),
    "unit_conversion": ToleranceRule("0", "0", 18),
    "numeric_approximation": ToleranceRule("1e-12", "1e-9", 9),
    "statistic": ToleranceRule("0", "0", 12),
    "optimization": ToleranceRule("1e-9", "1e-6", 9),
    "datetime_calculation": ToleranceRule("0", "0", 18),
    "structured_fact": ToleranceRule("0", "0", 18),
    "text_hint": ToleranceRule("0", "0", 12),
}


# ---------------------------------------------------------------------------
# Normalized CAG result
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class NormalizedCagResult:
    """A secret-free, normalized projection of one CAG component result.

    This is the bounded shape the evidence lane consumes. It must never carry a
    credential. ``reference_value`` / ``claim_value`` are optional string
    projections used only by the comparison helpers; the authoritative binding
    is the canonical hash.
    """

    component_id: str
    result_type: str
    domain: str
    assumptions: tuple[str, ...]
    units: str
    reference_value: str
    claim_value: str
    provider_request_id: str
    provider_response_uuid: str
    response_status: int
    component_ready: bool
    raw_payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _normalize_component(self.component_id))
        object.__setattr__(self, "result_type", _normalize_result_type(self.result_type))
        object.__setattr__(self, "domain", _normalize_text(self.domain, "domain", maximum=120))
        assumptions = tuple(
            _normalize_text(item, "assumption", maximum=300) for item in self.assumptions
        )
        object.__setattr__(self, "assumptions", assumptions)
        object.__setattr__(self, "units", _normalize_text(self.units, "units", maximum=60) if self.units else "")
        object.__setattr__(self, "reference_value", str(self.reference_value or "").strip())
        object.__setattr__(self, "claim_value", str(self.claim_value or "").strip())
        object.__setattr__(
            self,
            "provider_request_id",
            _normalize_text(self.provider_request_id, "provider_request_id", maximum=200)
            if self.provider_request_id else "",
        )
        object.__setattr__(
            self,
            "provider_response_uuid",
            _normalize_text(self.provider_response_uuid, "provider_response_uuid", maximum=200)
            if self.provider_response_uuid else "",
        )
        if isinstance(self.response_status, bool) or not isinstance(self.response_status, int):
            raise CagEvidenceError("response_status must be an integer")
        if self.response_status < 0 or self.response_status > 599:
            raise CagEvidenceError("response_status must be a valid HTTP status code")
        object.__setattr__(self, "component_ready", bool(self.component_ready))
        # raw_payload is canonicalized lazily; validate secret-safety eagerly.
        canonical_cag_value(self.raw_payload, path="raw_payload")

    def canonical_body(self) -> dict[str, Any]:
        return {
            "assumptions": list(self.assumptions),
            "claim_value": self.claim_value,
            "component_id": self.component_id,
            "component_ready": self.component_ready,
            "domain": self.domain,
            "provider_request_id": self.provider_request_id,
            "provider_response_uuid": self.provider_response_uuid,
            "raw_payload": canonical_cag_value(self.raw_payload, path="raw_payload"),
            "reference_value": self.reference_value,
            "response_status": self.response_status,
            "result_type": self.result_type,
            "units": self.units,
        }

    @property
    def result_hash(self) -> str:
        return canonical_cag_sha256(self.canonical_body())


# ---------------------------------------------------------------------------
# Claim contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CagClaim:
    """A bounded, verifiable agent claim submitted for a CAG counter-check."""

    claim_text: str
    claim_value: str
    expected_result_type: str
    domain: str
    sovereign_run_id: str
    runtime_revision: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim_text", _normalize_text(self.claim_text, "claim_text", maximum=1000))
        object.__setattr__(self, "claim_value", str(self.claim_value or "").strip())
        object.__setattr__(self, "expected_result_type", _normalize_result_type(self.expected_result_type))
        object.__setattr__(self, "domain", _normalize_text(self.domain, "domain", maximum=120))
        object.__setattr__(
            self,
            "sovereign_run_id",
            _normalize_identifier(self.sovereign_run_id, "sovereign_run_id"),
        )
        object.__setattr__(self, "runtime_revision", _normalize_revision(self.runtime_revision))

    def canonical_body(self) -> dict[str, Any]:
        return {
            "claim_text": self.claim_text,
            "claim_value": self.claim_value,
            "domain": self.domain,
            "expected_result_type": self.expected_result_type,
            "runtime_revision": self.runtime_revision,
            "sovereign_run_id": self.sovereign_run_id,
        }

    @property
    def claim_hash(self) -> str:
        return canonical_cag_sha256(self.canonical_body())


# ---------------------------------------------------------------------------
# Receipt
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class WolframCagReceiptV1:
    """Versioned, secret-free, hash-bound CAG evidence receipt (#1460).

    Binds: Sovereign run/claim, runtime revision (if relevant), component +
    contract version, normalized input + input hash, units/assumptions/domain,
    output/time limits, provider request/response ids, normalized result type +
    result hash, tolerance rule, latency/quota/cost metadata and a bounded
    verdict. ``recorded_at`` is optional non-canonical provenance and excluded
    from the receipt hash. The receipt never carries a credential and never
    self-asserts VERIFIED.
    """

    schema_version: str
    sovereign_run_id: str
    claim_hash: str
    runtime_revision: str
    component_id: str
    contract_version: str
    input_text: str
    input_hash: str
    domain: str
    units: str
    assumptions: tuple[str, ...]
    timeout_seconds: int
    max_output_bytes: int
    provider_request_id: str
    provider_response_uuid: str
    response_status: int
    component_ready: bool
    result_type: str
    result_hash: str
    tolerance: ToleranceRule
    latency_ms: int
    quota_class: str
    cost_class: str
    verdict: CagEvidenceVerdict
    finding_codes: tuple[str, ...]
    bounded_summary: str
    recorded_at: str
    truth_notice: str = TRUTH_NOTICE

    def __post_init__(self) -> None:
        if self.schema_version != RECEIPT_SCHEMA_VERSION:
            raise CagEvidenceError("unsupported receipt schema version")
        object.__setattr__(self, "sovereign_run_id", _normalize_identifier(self.sovereign_run_id, "sovereign_run_id"))
        object.__setattr__(self, "claim_hash", _normalize_sha64(self.claim_hash, "claim_hash"))
        object.__setattr__(self, "runtime_revision", _normalize_revision(self.runtime_revision))
        object.__setattr__(self, "component_id", _normalize_component(self.component_id))
        if self.contract_version != CONTRACT_VERSION:
            raise CagEvidenceError("contract_version must match the CAG transport contract")
        object.__setattr__(self, "input_text", _normalize_text(self.input_text, "input_text", maximum=4000))
        object.__setattr__(self, "input_hash", _normalize_sha64(self.input_hash, "input_hash"))
        object.__setattr__(self, "domain", _normalize_text(self.domain, "domain", maximum=120))
        object.__setattr__(self, "units", _normalize_text(self.units, "units", maximum=60) if self.units else "")
        assumptions = tuple(
            _normalize_text(item, "assumption", maximum=300) for item in self.assumptions
        )
        object.__setattr__(self, "assumptions", assumptions)
        if isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, int):
            raise CagEvidenceError("timeout_seconds must be an integer")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 60:
            raise CagEvidenceError("timeout_seconds must be in (0, 60]")
        if isinstance(self.max_output_bytes, bool) or not isinstance(self.max_output_bytes, int):
            raise CagEvidenceError("max_output_bytes must be an integer")
        if self.max_output_bytes <= 0 or self.max_output_bytes > 1_000_000:
            raise CagEvidenceError("max_output_bytes must be in (0, 1000000]")
        object.__setattr__(
            self,
            "provider_request_id",
            _normalize_text(self.provider_request_id, "provider_request_id", maximum=200)
            if self.provider_request_id else "",
        )
        object.__setattr__(
            self,
            "provider_response_uuid",
            _normalize_text(self.provider_response_uuid, "provider_response_uuid", maximum=200)
            if self.provider_response_uuid else "",
        )
        if isinstance(self.response_status, bool) or not isinstance(self.response_status, int):
            raise CagEvidenceError("response_status must be an integer")
        if self.response_status < 0 or self.response_status > 599:
            raise CagEvidenceError("response_status must be a valid HTTP status code")
        object.__setattr__(self, "component_ready", bool(self.component_ready))
        object.__setattr__(self, "result_type", _normalize_result_type(self.result_type))
        object.__setattr__(self, "result_hash", _normalize_sha64(self.result_hash, "result_hash"))
        if not isinstance(self.tolerance, ToleranceRule):
            raise CagEvidenceError("tolerance must be a ToleranceRule")
        if isinstance(self.latency_ms, bool) or not isinstance(self.latency_ms, int):
            raise CagEvidenceError("latency_ms must be an integer")
        if self.latency_ms < 0:
            raise CagEvidenceError("latency_ms must be non-negative")
        object.__setattr__(self, "quota_class", _normalize_text(self.quota_class, "quota_class", maximum=60) if self.quota_class else "UNKNOWN")
        object.__setattr__(self, "cost_class", _normalize_text(self.cost_class, "cost_class", maximum=60) if self.cost_class else "UNKNOWN")
        if not isinstance(self.verdict, CagEvidenceVerdict):
            raise CagEvidenceError("verdict must be a CagEvidenceVerdict")
        findings = tuple(sorted({_normalize_identifier(item, "finding_code") for item in self.finding_codes}))
        object.__setattr__(self, "finding_codes", findings)
        object.__setattr__(self, "bounded_summary", _normalize_text(self.bounded_summary, "bounded_summary", maximum=400) if self.bounded_summary else "")
        object.__setattr__(
            self,
            "recorded_at",
            _normalize_text(self.recorded_at, "recorded_at", maximum=60) if self.recorded_at else "",
        )
        # Verdict/finding consistency.
        if self.verdict is CagEvidenceVerdict.SUPPORTED and self.finding_codes:
            raise CagEvidenceError("SUPPORTED must not carry finding codes")
        if self.verdict is CagEvidenceVerdict.CONTRADICTED and not any(
            code.startswith("contradicted") for code in self.finding_codes
        ):
            raise CagEvidenceError("CONTRADICTED requires a contradicted* finding code")
        if self.verdict is CagEvidenceVerdict.UNAVAILABLE and not self.finding_codes:
            raise CagEvidenceError("UNAVAILABLE requires a finding code")

    def canonical_body(self) -> dict[str, Any]:
        # recorded_at is intentionally excluded from the canonical hash: it is
        # non-causal provenance, never causal identity.
        return {
            "assumptions": list(self.assumptions),
            "bounded_summary": self.bounded_summary,
            "claim_hash": self.claim_hash,
            "component_id": self.component_id,
            "component_ready": self.component_ready,
            "contract_version": self.contract_version,
            "cost_class": self.cost_class,
            "domain": self.domain,
            "finding_codes": list(self.finding_codes),
            "input_hash": self.input_hash,
            "input_text": self.input_text,
            "latency_ms": self.latency_ms,
            "max_output_bytes": self.max_output_bytes,
            "provider_request_id": self.provider_request_id,
            "provider_response_uuid": self.provider_response_uuid,
            "quota_class": self.quota_class,
            "response_status": self.response_status,
            "result_hash": self.result_hash,
            "result_type": self.result_type,
            "runtime_revision": self.runtime_revision,
            "schema_version": self.schema_version,
            "sovereign_run_id": self.sovereign_run_id,
            "timeout_seconds": self.timeout_seconds,
            "tolerance": self.tolerance.canonical_body(),
            "units": self.units,
            "verdict": self.verdict.value,
        }

    @property
    def receipt_sha256(self) -> str:
        return canonical_cag_sha256(self.canonical_body())

    def to_dict(self) -> dict[str, Any]:
        body = self.canonical_body()
        body["recorded_at"] = self.recorded_at
        body["truth_notice"] = self.truth_notice
        body["receipt_sha256"] = self.receipt_sha256
        return body


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------

def _parse_number(text: str) -> float | None:
    cleaned = str(text or "").strip().replace(",", "")
    if not cleaned:
        return None
    try:
        value = float(cleaned)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def compare_numeric_claim(
    claim_value: str,
    reference_value: str,
    tolerance: ToleranceRule,
) -> CagEvidenceVerdict:
    """Compare a numeric claim against a reference under a tolerance rule.

    Returns SUPPORTED / CONTRADICTED / INCONCLUSIVE. Non-numeric or mismatched
    values are INCONCLUSIVE, never silently SUPPORTED.
    """
    claim = _parse_number(claim_value)
    reference = _parse_number(reference_value)
    if claim is None or reference is None:
        return CagEvidenceVerdict.INCONCLUSIVE
    if tolerance.within(claim, reference):
        return CagEvidenceVerdict.SUPPORTED
    return CagEvidenceVerdict.CONTRADICTED


def compare_exact_claim(claim_value: str, reference_value: str) -> CagEvidenceVerdict:
    """Case-/whitespace-insensitive exact comparison for symbolic/fact results."""
    claim = str(claim_value or "").strip().casefold()
    reference = str(reference_value or "").strip().casefold()
    if not claim or not reference:
        return CagEvidenceVerdict.INCONCLUSIVE
    if claim == reference:
        return CagEvidenceVerdict.SUPPORTED
    return CagEvidenceVerdict.CONTRADICTED


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class VerificationInput:
    """The bounded inputs to ``verify_cag_claim``.

    ``transport_receipt`` is an optional projection of the #1459 transport
    receipt (a mapping). When it carries a non-READY component_status or a
    non-2xx response, the verdict is honestly UNAVAILABLE regardless of the
    normalized result, because no real CAG result is present.
    """

    claim: CagClaim
    input_text: str
    result: NormalizedCagResult
    tolerance: ToleranceRule
    timeout_seconds: int = 15
    max_output_bytes: int = 1_000_000
    latency_ms: int = 0
    quota_class: str = "UNKNOWN"
    cost_class: str = "UNKNOWN"
    recorded_at: str = ""
    transport_receipt: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_text", _normalize_text(self.input_text, "input_text", maximum=4000))
        if isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, int):
            raise CagEvidenceError("timeout_seconds must be an integer")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 60:
            raise CagEvidenceError("timeout_seconds must be in (0, 60]")
        if isinstance(self.max_output_bytes, bool) or not isinstance(self.max_output_bytes, int):
            raise CagEvidenceError("max_output_bytes must be an integer")
        if self.max_output_bytes <= 0 or self.max_output_bytes > 1_000_000:
            raise CagEvidenceError("max_output_bytes must be in (0, 1000000]")
        if isinstance(self.latency_ms, bool) or not isinstance(self.latency_ms, int) or self.latency_ms < 0:
            raise CagEvidenceError("latency_ms must be a non-negative integer")
        if self.transport_receipt is not None and not isinstance(self.transport_receipt, Mapping):
            raise CagEvidenceError("transport_receipt must be a mapping or None")
        if not isinstance(self.tolerance, ToleranceRule):
            raise CagEvidenceError("tolerance must be a ToleranceRule")


def _transport_unavailable(transport_receipt: Mapping[str, Any] | None) -> str | None:
    """Return a finding code when the transport honestly has no real result."""
    if transport_receipt is None:
        return "unavailable_no_transport_receipt"
    status = str(transport_receipt.get("component_status") or "").strip().upper()
    verdict = str(transport_receipt.get("verdict") or "").strip().upper()
    response_status = transport_receipt.get("response_status")
    if status in {"NOT_ENTITLED", "UNAVAILABLE", "UNKNOWN", "DEGRADED"}:
        return f"unavailable_component_status_{status.lower()}"
    if verdict == "UNAVAILABLE":
        return "unavailable_transport_verdict"
    if isinstance(response_status, int) and not (200 <= response_status < 300):
        return "unavailable_non_2xx_response"
    return None


def verify_cag_claim(inputs: VerificationInput) -> WolframCagReceiptV1:
    """Produce a deterministic, secret-free CAG evidence receipt for a claim.

    The verifier is fail-closed and honest:
    - Without a real transport receipt (READY, 2xx, non-UNAVAILABLE verdict) the
      verdict is UNAVAILABLE. No mock result is ever promoted to SUPPORTED.
    - A component/result-type mismatch between claim and result is INCONCLUSIVE.
    - Numeric claims use the explicit tolerance rule; symbolic/fact claims use
      exact comparison. A contradiction stays a contradiction and is never
      smoothed away by the judge.
    - The verdict is bound to the canonical input/result hashes.
    """
    claim = inputs.claim
    result = inputs.result

    if claim.expected_result_type != result.result_type:
        return _build_receipt(
            inputs,
            verdict=CagEvidenceVerdict.INCONCLUSIVE,
            finding_codes=("inconclusive_result_type_mismatch",),
            summary="claim expected result type differs from CAG result type",
        )

    unavailable = _transport_unavailable(inputs.transport_receipt)
    if unavailable is not None:
        return _build_receipt(
            inputs,
            verdict=CagEvidenceVerdict.UNAVAILABLE,
            finding_codes=(unavailable,),
            summary="no real CAG result available; component not provisioned or transport unavailable",
        )

    if not result.component_ready:
        return _build_receipt(
            inputs,
            verdict=CagEvidenceVerdict.UNAVAILABLE,
            finding_codes=("unavailable_component_not_ready",),
            summary="CAG component reported not ready",
        )

    if claim.domain.casefold() != result.domain.casefold():
        return _build_receipt(
            inputs,
            verdict=CagEvidenceVerdict.INCONCLUSIVE,
            finding_codes=("inconclusive_domain_mismatch",),
            summary="claim domain differs from CAG result domain",
        )

    # Numeric result types are compared under the tolerance rule; the remaining
    # types use exact comparison.
    numeric_types = {"numeric_approximation", "statistic", "optimization", "exact_number", "unit_conversion"}
    if result.result_type in numeric_types and result.reference_value and claim.claim_value:
        comparison = compare_numeric_claim(claim.claim_value, result.reference_value, inputs.tolerance)
    elif result.reference_value and claim.claim_value:
        comparison = compare_exact_claim(claim.claim_value, result.reference_value)
    else:
        return _build_receipt(
            inputs,
            verdict=CagEvidenceVerdict.INCONCLUSIVE,
            finding_codes=("inconclusive_missing_values",),
            summary="claim or reference value missing; cannot decide",
        )

    if comparison is CagEvidenceVerdict.SUPPORTED:
        return _build_receipt(
            inputs,
            verdict=CagEvidenceVerdict.SUPPORTED,
            finding_codes=(),
            summary="CAG counter-check supports the claim within the tolerance rule",
        )
    if comparison is CagEvidenceVerdict.CONTRADICTED:
        return _build_receipt(
            inputs,
            verdict=CagEvidenceVerdict.CONTRADICTED,
            finding_codes=("contradicted_value_mismatch",),
            summary="CAG counter-check contradicts the claim",
        )
    return _build_receipt(
        inputs,
        verdict=CagEvidenceVerdict.INCONCLUSIVE,
        finding_codes=("inconclusive_unparseable_values",),
        summary="claim or reference value could not be parsed for comparison",
    )


def _build_receipt(
    inputs: VerificationInput,
    *,
    verdict: CagEvidenceVerdict,
    finding_codes: tuple[str, ...],
    summary: str,
) -> WolframCagReceiptV1:
    claim = inputs.claim
    result = inputs.result
    return WolframCagReceiptV1(
        schema_version=RECEIPT_SCHEMA_VERSION,
        sovereign_run_id=claim.sovereign_run_id,
        claim_hash=claim.claim_hash,
        runtime_revision=claim.runtime_revision,
        component_id=result.component_id,
        contract_version=CONTRACT_VERSION,
        input_text=inputs.input_text,
        input_hash=canonical_cag_sha256(inputs.input_text),
        domain=result.domain,
        units=result.units,
        assumptions=result.assumptions,
        timeout_seconds=inputs.timeout_seconds,
        max_output_bytes=inputs.max_output_bytes,
        provider_request_id=result.provider_request_id,
        provider_response_uuid=result.provider_response_uuid,
        response_status=result.response_status,
        component_ready=result.component_ready,
        result_type=result.result_type,
        result_hash=result.result_hash,
        tolerance=inputs.tolerance,
        latency_ms=inputs.latency_ms,
        quota_class=inputs.quota_class,
        cost_class=inputs.cost_class,
        verdict=verdict,
        finding_codes=finding_codes,
        bounded_summary=summary,
        recorded_at=inputs.recorded_at,
    )


def unavailable_receipt(inputs: VerificationInput) -> WolframCagReceiptV1:
    """The honest fail-closed receipt when no real provisioning evidence exists.

    This is the canonical path for issue #1460 until #1458 supplies real
    entitlement evidence: every CAG counter-check resolves honestly to
    UNAVAILABLE. It is real, deterministic, secret-free evidence, not a mock.
    """
    return _build_receipt(
        inputs,
        verdict=CagEvidenceVerdict.UNAVAILABLE,
        finding_codes=("unavailable_no_provisioning_evidence",),
        summary="no provisioning evidence; CAG counter-check unavailable",
    )


__all__ = [
    "CONTRACT_VERSION",
    "CAG_COMPONENTS",
    "CagClaim",
    "CagEvidenceError",
    "CagEvidenceVerdict",
    "DEFAULT_TOLERANCE_RULES",
    "NormalizedCagResult",
    "RECEIPT_SCHEMA_VERSION",
    "RESULT_TYPES",
    "TRUTH_NOTICE",
    "ToleranceRule",
    "VerificationInput",
    "WolframCagReceiptV1",
    "canonical_cag_bytes",
    "canonical_cag_sha256",
    "canonical_cag_value",
    "compare_exact_claim",
    "compare_numeric_claim",
    "unavailable_receipt",
    "verify_cag_claim",
]
