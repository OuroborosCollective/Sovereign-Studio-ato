"""Registry-/install-admission boundary for Observed Tool Behavior Attestation (OTBA).

Issue #1452 (OTBA 3/5). This module makes the OTBA behavior receipt a *real* promotion
boundary for the existing tool-/MCP-install path. A locally executable (``LOCAL_OCI``)
tool may not be promoted to a productively usable state after a relevant
image-/revision-/capability change unless a behavior attestation is present, non-
contradictory and contract-conforming.

Design contract
---------------
- This lane creates **no second registry store** and **no second deployment engine**.
  It only extends the existing evidence-/registry-gate contract with a fail-closed
  behavior-admission check.
- It performs no network, database, filesystem, clock or random access. It is pure
  deterministic evaluation over already-collected evidence.
- A positive admission requires a real ``ObservedToolBehaviorReceipt`` produced by the
  #1451 runtime lane (OTBA 2/5) whose ``verdict == BEHAVIOR_VERIFIED`` *and* whose bound
  identity matches the current authoritative identity exactly.
- Drift in any identity dimension invalidates a previously positive receipt deterministically.
- Remote MCP tools are never presented as having full local behavior fidelity.
- Enforcement is tiered (``observe_only`` / ``warn`` / ``enforce_local_oci``). No global
  enforcement activation is implied; ``#1454`` benchmark governs that.
- ``auto_merge_allowed`` is always ``False``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Final

from tool_behavior_attestation import ObservedToolBehaviorReceipt

# ---------------------------------------------------------------------------
# Schema / constants
# ---------------------------------------------------------------------------

ADMISSION_SCHEMA: Final[str] = "sovereign.tool-behavior-admission.v1"

_SHA256: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_SHA40: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")

# Execution kinds understood by the admission boundary. ``LOCAL_OCI`` is the only kind
# that can carry full local behavior fidelity and therefore the only kind subject to the
# hard ``post_observed_tool_behavior`` requirement.
EXECUTION_KINDS: Final[frozenset[str]] = frozenset({"LOCAL_OCI", "REMOTE_MCP", "HOST_BROKER"})

# Enforcement tiers, ordered from weakest to strongest.
TIER_OBSERVE_ONLY: Final[str] = "observe_only"
TIER_WARN: Final[str] = "warn"
TIER_ENFORCE_LOCAL_OCI: Final[str] = "enforce_local_oci"
TIERS: Final[tuple[str, ...]] = (TIER_OBSERVE_ONLY, TIER_WARN, TIER_ENFORCE_LOCAL_OCI)

# Admission verdicts.
ADMIT_BLOCKED: Final[str] = "BLOCKED"
ADMIT_REMOTE_PARTIAL: Final[str] = "REMOTE_PARTIAL"
ADMIT_ALLOWED: Final[str] = "ALLOWED"

# Requirement id appended to the install requirement set for LOCAL_OCI tools.
REQUIREMENT_POST_OBSERVED_TOOL_BEHAVIOR: Final[str] = "post_observed_tool_behavior"

# Finding codes.
FINDING_NO_RECEIPT: Final[str] = "tool_behavior_receipt_missing"
FINDING_NOT_VERIFIED: Final[str] = "tool_behavior_not_attested"
FINDING_DRIFT_IMAGE_DIGEST: Final[str] = "receipt_drift_image_digest"
FINDING_DRIFT_REPO_REVISION: Final[str] = "receipt_drift_repository_revision"
FINDING_DRIFT_REGISTRY_REVISION: Final[str] = "receipt_drift_tool_registry_revision"
FINDING_DRIFT_CONTRACT_HASH: Final[str] = "receipt_drift_behavior_contract_hash"
FINDING_DRIFT_CANARY_INPUT: Final[str] = "receipt_drift_canary_input"
FINDING_DRIFT_CAPABILITY_CONTRACT: Final[str] = "receipt_drift_capability_contract"
FINDING_DRIFT_SANDBOX_TRACER: Final[str] = "receipt_drift_sandbox_tracer_version"
FINDING_RECEIPT_TAMPERED: Final[str] = "receipt_tamper_detected"
FINDING_REMOTE_NOT_LOCAL_FIDELITY: Final[str] = "remote_partial_not_full_local_attestation"


def requirements_for_tool_install(*, execution_kind: str) -> tuple[str, ...]:
    """Return the install-evidence requirement set for the given execution kind.

    Extends the base ``mcp_registry_tool_install`` requirement set with the OTBA
    behavior requirement for locally containerized tools. Remote/broker tools keep
    the base set; their behavior fidelity is reported separately as ``REMOTE_PARTIAL``
    and must never be presented as a full local attestation.
    """
    kind = _validate_kind(execution_kind)
    requirements = (
        "pre_source_runtime_revision",
        "pre_registry_tool_status",
        "pre_declared_capabilities",
        "post_actual_running_digest",
        "post_mcp_initialize_canary",
        "post_capability_delta",
    )
    if kind == "LOCAL_OCI":
        requirements = requirements + (REQUIREMENT_POST_OBSERVED_TOOL_BEHAVIOR,)
    return requirements


def _validate_kind(value: Any) -> str:
    kind = str(value or "").strip().upper()
    if kind not in EXECUTION_KINDS:
        raise ValueError(f"execution_kind must be one of {sorted(EXECUTION_KINDS)}")
    return kind


def _validate_tier(value: Any) -> str:
    tier = str(value or "").strip().lower()
    if tier not in TIERS:
        raise ValueError(f"enforcement_tier must be one of {TIERS}")
    return tier


def _validate_hash(value: Any, field: str, *, optional: bool = False) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        if optional:
            return ""
        raise ValueError(f"{field} must be a SHA-256")
    if not _SHA256.fullmatch(raw):
        raise ValueError(f"{field} must be a SHA-256")
    return raw


def _validate_revision(value: Any, *, field: str) -> str:
    raw = str(value or "").strip().lower()
    if not _SHA40.fullmatch(raw):
        raise ValueError(f"{field} must be a full Git SHA-40")
    return raw


# ---------------------------------------------------------------------------
# Authoritative admission identity
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ToolAdmissionIdentity:
    """The current authoritative identity a behavior receipt must match exactly.

    Any drift between these values and the values bound into a previously positive
    receipt invalidates that receipt. Fields that the receipt does not natively carry
    (``capability_contract_sha256`` and ``sandbox_tracer_version``) are supplied by the
    caller as the *receipt-claimed* values alongside the receipt; the admission layer
    compares them against these authoritative values. A field that the identity marks
    as required (non-empty) but for which no receipt claim is supplied is treated as a
    drift — fail-closed, no silent reuse.
    """

    tool_id: str
    execution_kind: str
    repository_revision: str
    tool_registry_revision: str
    image_digest: str | None
    behavior_contract_sha256: str
    canary_input_sha256: str
    capability_contract_sha256: str
    sandbox_tracer_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.tool_id, str) or not self.tool_id.strip():
            raise ValueError("tool_id must be a non-empty string")
        kind = _validate_kind(self.execution_kind)
        object.__setattr__(self, "tool_id", str(self.tool_id).strip())
        object.__setattr__(self, "execution_kind", kind)
        object.__setattr__(self, "repository_revision", _validate_revision(self.repository_revision, field="repository_revision"))
        object.__setattr__(self, "tool_registry_revision", _validate_revision(self.tool_registry_revision, field="tool_registry_revision"))
        digest = str(self.image_digest or "").strip().lower()
        if digest:
            digest = _strip_sha_prefix(digest)
            if not _SHA256.fullmatch(digest):
                raise ValueError("image_digest must be a SHA-256 digest or None")
        object.__setattr__(self, "image_digest", digest or None)
        object.__setattr__(self, "behavior_contract_sha256", _validate_hash(self.behavior_contract_sha256, field="behavior_contract_sha256"))
        object.__setattr__(self, "canary_input_sha256", _validate_hash(self.canary_input_sha256, field="canary_input_sha256"))
        # capability_contract_sha256 and sandbox_tracer_version are optional in shape;
        # a LOCAL_OCI identity that requires them enforces presence at admission time.
        cap = str(self.capability_contract_sha256 or "").strip().lower()
        if cap:
            cap = _validate_hash(cap, field="capability_contract_sha256", optional=True)
        object.__setattr__(self, "capability_contract_sha256", cap)
        object.__setattr__(self, "sandbox_tracer_version", str(self.sandbox_tracer_version or "").strip())


def _strip_sha_prefix(value: str) -> str:
    v = value.strip().lower()
    if v.startswith("sha256:"):
        return v[len("sha256:"):]
    return v


# ---------------------------------------------------------------------------
# Receipt-claimed bindings (for fields the receipt schema does not carry)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ReceiptClaimedBindings:
    """Values the receipt lane recorded alongside a receipt for drift-relevant fields
    that the receipt schema itself does not bind cryptographically.

    These are honest metadata: the admission layer compares them to the authoritative
    ``ToolAdmissionIdentity``. If a binding is required by the identity but absent here,
    the receipt is treated as drifted (fail-closed) rather than reused silently.
    """

    capability_contract_sha256: str = ""
    sandbox_tracer_version: str = ""

    def __post_init__(self) -> None:
        cap = str(self.capability_contract_sha256 or "").strip().lower()
        if cap:
            cap = _validate_hash(cap, field="capability_contract_sha256", optional=True)
        object.__setattr__(self, "capability_contract_sha256", cap)
        object.__setattr__(self, "sandbox_tracer_version", str(self.sandbox_tracer_version or "").strip())


# ---------------------------------------------------------------------------
# Admission result
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ToolAdmissionResult:
    """Fail-closed admission verdict for one tool-install promotion.

    ``verdict`` is the *honest* receipt-derived admission state (ALLOWED / BLOCKED /
    REMOTE_PARTIAL), computed identically regardless of tier so the truth is never
    hidden. ``promotion_blocked`` is True only under ``enforce_local_oci`` when the
    receipt does not grant ALLOWED; under ``observe_only`` / ``warn`` the same honest
    state is exposed but promotion is not gated, so ``promotion_blocked`` is False —
    shadow/warn tiers never mutate the productive registry state.
    """

    verdict: str
    promotion_blocked: bool
    execution_kind: str
    enforcement_tier: str
    receipt_sha256: str
    satisfied: tuple[str, ...]
    missing: tuple[str, ...]
    contradicted: tuple[str, ...]
    finding_codes: tuple[str, ...]
    auto_merge_allowed: bool  # always False


# ---------------------------------------------------------------------------
# Drift evaluation
# ---------------------------------------------------------------------------

def _drift_findings(
    *,
    receipt: ObservedToolBehaviorReceipt,
    identity: ToolAdmissionIdentity,
    claimed: ReceiptClaimedBindings,
) -> tuple[list[str], list[str]]:
    """Return (drift_findings, contradicted_requirement_ids) for identity mismatches.

    A drift in any identity dimension invalidates the receipt. The contradicted
    requirement is ``post_observed_tool_behavior`` because the receipt no longer
    attests the identity the install is bound to.
    """
    findings: list[str] = []
    contradicted: list[str] = []

    def _drift(code: str) -> None:
        findings.append(code)
        contradicted.append(REQUIREMENT_POST_OBSERVED_TOOL_BEHAVIOR)

    # image_digest (receipt may carry a 'sha256:' prefix; compare on bare hex)
    receipt_digest = _strip_sha_prefix(receipt.image_digest or "")
    identity_digest = identity.image_digest or ""
    if receipt_digest != identity_digest:
        _drift(FINDING_DRIFT_IMAGE_DIGEST)

    # repository_revision
    if receipt.repository_revision != identity.repository_revision:
        _drift(FINDING_DRIFT_REPO_REVISION)

    # tool_registry_revision
    if receipt.tool_registry_revision != identity.tool_registry_revision:
        _drift(FINDING_DRIFT_REGISTRY_REVISION)

    # behavior_contract_sha256
    if receipt.behavior_contract_sha256 != identity.behavior_contract_sha256:
        _drift(FINDING_DRIFT_CONTRACT_HASH)

    # canary_input_sha256
    if receipt.canary_input_sha256 != identity.canary_input_sha256:
        _drift(FINDING_DRIFT_CANARY_INPUT)

    # capability_contract_sha256 (carried alongside the receipt, not in its schema)
    if identity.capability_contract_sha256:
        if claimed.capability_contract_sha256 != identity.capability_contract_sha256:
            _drift(FINDING_DRIFT_CAPABILITY_CONTRACT)

    # sandbox_tracer_version
    if identity.sandbox_tracer_version:
        if claimed.sandbox_tracer_version != identity.sandbox_tracer_version:
            _drift(FINDING_DRIFT_SANDBOX_TRACER)

    return findings, contradicted


# ---------------------------------------------------------------------------
# Fail-closed admission evaluation
# ---------------------------------------------------------------------------

def evaluate_tool_admission(
    *,
    identity: ToolAdmissionIdentity,
    receipt: ObservedToolBehaviorReceipt | None,
    claimed_bindings: ReceiptClaimedBindings | None = None,
    enforcement_tier: str = TIER_OBSERVE_ONLY,
    mcp_initialize_passed: bool = False,
    signed_image: bool = False,
    ui_override_flag: bool = False,
) -> ToolAdmissionResult:
    """Evaluate whether a tool-install may be promoted to a productive state.

    Parameters
    ----------
    identity
        The current authoritative identity the install is bound to.
    receipt
        The behavior receipt produced by the #1451 runtime lane, or ``None`` when no
        receipt exists yet.
    claimed_bindings
        Receipt-claimed values for drift fields the receipt schema does not carry
        natively (capability contract, sandbox/tracer version).
    enforcement_tier
        One of ``observe_only`` / ``warn`` / ``enforce_local_oci``. Only
        ``enforce_local_oci`` hard-blocks promotion; the other tiers compute the same
        honest verdict but do not gate promotion.
    mcp_initialize_passed
        Whether an MCP initialize canary passed. A pass here can *never* override a
        missing or negative behavior receipt.
    signed_image
        Whether the image is cosign-signed. Signing can *never* override a behavior
        violation.
    ui_override_flag
        A workflow/UI-supplied flag. It can *never* upgrade the admission verdict.

    Verdict rules
    -------------
    ALLOWED
        ``LOCAL_OCI`` with a real ``BEHAVIOR_VERIFIED`` receipt whose identity matches
        exactly and whose hash is self-consistent.
    REMOTE_PARTIAL
        ``REMOTE_MCP`` tools. They may be admitted via the existing gateway/capability/
        effect evidence path but are never presented as full local behavior attestation.
    BLOCKED
        ``LOCAL_OCI`` under ``enforce_local_oci`` with a missing, tampered, drifted,
        non-verified, contradicted or violating receipt. Override signals
        (``mcp_initialize_passed``, ``signed_image``, ``ui_override_flag``) cannot
        change a BLOCKED verdict.
    """
    tier = _validate_tier(enforcement_tier)
    claimed = claimed_bindings or ReceiptClaimedBindings()

    satisfied: list[str] = []
    missing: list[str] = []
    contradicted: list[str] = []
    findings: list[str] = []

    # Remote MCP tools are never full local-fidelity. They are reported as
    # REMOTE_PARTIAL so the UI/API can show the gap honestly. They may still proceed
    # through the existing gateway evidence path; OTBA does not grant capabilities.
    if identity.execution_kind == "REMOTE_MCP":
        return ToolAdmissionResult(
            verdict=ADMIT_REMOTE_PARTIAL,
            promotion_blocked=False,
            execution_kind=identity.execution_kind,
            enforcement_tier=tier,
            receipt_sha256=receipt.receipt_sha256 if receipt else "",
            satisfied=(),
            missing=(),
            contradicted=(),
            finding_codes=(FINDING_REMOTE_NOT_LOCAL_FIDELITY,),
            auto_merge_allowed=False,
        )

    # HOST_BROKER tools are not subject to the LOCAL_OCI hard behavior requirement in
    # this lane (their fidelity contract is established elsewhere). Report honestly
    # without granting a behavior-verified status they did not earn here.
    if identity.execution_kind == "HOST_BROKER":
        return ToolAdmissionResult(
            verdict=ADMIT_REMOTE_PARTIAL,
            promotion_blocked=False,
            execution_kind=identity.execution_kind,
            enforcement_tier=tier,
            receipt_sha256=receipt.receipt_sha256 if receipt else "",
            satisfied=(),
            missing=(),
            contradicted=(),
            finding_codes=("host_broker_not_local_oci_behavior_attested",),
            auto_merge_allowed=False,
        )

    # --- LOCAL_OCI path: the behavior receipt is a hard promotion requirement. ---

    # No receipt at all.
    if receipt is None:
        missing.append(REQUIREMENT_POST_OBSERVED_TOOL_BEHAVIOR)
        findings.append(FINDING_NO_RECEIPT)
        return _finalize(
            identity=identity, tier=tier,
            satisfied=tuple(satisfied), missing=tuple(missing),
            contradicted=tuple(contradicted), findings=tuple(findings),
            receipt_sha256="",
        )

    # Tamper detection: a receipt whose stored hash disagrees with its canonical record
    # cannot be trusted and cannot satisfy the requirement.
    if not receipt.verify():
        contradicted.append(REQUIREMENT_POST_OBSERVED_TOOL_BEHAVIOR)
        findings.append(FINDING_RECEIPT_TAMPERED)
        return _finalize(
            identity=identity, tier=tier,
            satisfied=tuple(satisfied), missing=tuple(missing),
            contradicted=tuple(contradicted), findings=tuple(findings),
            receipt_sha256=receipt.receipt_sha256,
        )

    # Identity drift: any dimension mismatch invalidates the receipt.
    drift_findings, drift_contradicted = _drift_findings(
        receipt=receipt, identity=identity, claimed=claimed,
    )
    if drift_findings:
        findings.extend(drift_findings)
        contradicted.extend(drift_contradicted)
        return _finalize(
            identity=identity, tier=tier,
            satisfied=tuple(satisfied), missing=tuple(missing),
            contradicted=tuple(contradicted), findings=tuple(findings),
            receipt_sha256=receipt.receipt_sha256,
        )

    # The receipt binds the right identity. Now honor its verdict exactly.
    verdict = receipt.verdict
    if verdict != "BEHAVIOR_VERIFIED":
        # BEHAVIOR_VIOLATION / UNVERIFIED / CONTRADICTED / REMOTE_PARTIAL all block.
        findings.append(FINDING_NOT_VERIFIED)
        findings.append(f"RECEIPT_VERDICT:{verdict}")
        contradicted.append(REQUIREMENT_POST_OBSERVED_TOOL_BEHAVIOR)
        return _finalize(
            identity=identity, tier=tier,
            satisfied=tuple(satisfied), missing=tuple(missing),
            contradicted=tuple(contradicted), findings=tuple(findings),
            receipt_sha256=receipt.receipt_sha256,
        )

    # BEHAVIOR_VERIFIED on the exact matching identity. The requirement is satisfied.
    satisfied.append(REQUIREMENT_POST_OBSERVED_TOOL_BEHAVIOR)
    return _finalize(
        identity=identity, tier=tier,
        satisfied=tuple(satisfied), missing=tuple(missing),
        contradicted=tuple(contradicted), findings=tuple(findings),
        receipt_sha256=receipt.receipt_sha256,
    )


def _finalize(
    *,
    identity: ToolAdmissionIdentity,
    tier: str,
    satisfied: tuple[str, ...],
    missing: tuple[str, ...],
    contradicted: tuple[str, ...],
    findings: tuple[str, ...],
    receipt_sha256: str,
) -> ToolAdmissionResult:
    """Apply the enforcement tier to produce the final verdict.

    ``verdict`` is the honest receipt-derived admission state, computed identically
    for every tier so the truth is never hidden. ``promotion_blocked`` is True only
    when the receipt does not grant ALLOWED *and* the tier is ``enforce_local_oci``.
    Under ``observe_only`` / ``warn`` the same honest state is exposed but promotion is
    not gated, so a shadow/warn tier never mutates the productive registry state.

    Override signals are deliberately ignored: no caller flag, signature or initialize
    canary can upgrade the verdict. They are accepted only as informational context
    that does not affect the result.
    """
    has_block_evidence = bool(missing) or bool(contradicted)

    if identity.execution_kind == "LOCAL_OCI":
        verdict = ADMIT_BLOCKED if has_block_evidence else ADMIT_ALLOWED
        promotion_blocked = has_block_evidence and tier == TIER_ENFORCE_LOCAL_OCI
    else:
        verdict = ADMIT_REMOTE_PARTIAL
        promotion_blocked = False

    return ToolAdmissionResult(
        verdict=verdict,
        promotion_blocked=promotion_blocked,
        execution_kind=identity.execution_kind,
        enforcement_tier=tier,
        receipt_sha256=receipt_sha256,
        satisfied=tuple(sorted(satisfied)),
        missing=tuple(sorted(missing)),
        contradicted=tuple(sorted(contradicted)),
        finding_codes=tuple(sorted(set(findings))),
        auto_merge_allowed=False,
    )


__all__ = [
    "ADMISSION_SCHEMA",
    "ADMIT_ALLOWED",
    "ADMIT_BLOCKED",
    "ADMIT_REMOTE_PARTIAL",
    "EXECUTION_KINDS",
    "FINDING_DRIFT_CANARY_INPUT",
    "FINDING_DRIFT_CAPABILITY_CONTRACT",
    "FINDING_DRIFT_CONTRACT_HASH",
    "FINDING_DRIFT_IMAGE_DIGEST",
    "FINDING_DRIFT_REGISTRY_REVISION",
    "FINDING_DRIFT_REPO_REVISION",
    "FINDING_DRIFT_SANDBOX_TRACER",
    "FINDING_NO_RECEIPT",
    "FINDING_NOT_VERIFIED",
    "FINDING_RECEIPT_TAMPERED",
    "FINDING_REMOTE_NOT_LOCAL_FIDELITY",
    "REQUIREMENT_POST_OBSERVED_TOOL_BEHAVIOR",
    "ReceiptClaimedBindings",
    "TIERS",
    "TIER_ENFORCE_LOCAL_OCI",
    "TIER_OBSERVE_ONLY",
    "TIER_WARN",
    "ToolAdmissionIdentity",
    "ToolAdmissionResult",
    "evaluate_tool_admission",
    "requirements_for_tool_install",
]
