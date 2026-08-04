"""Fail-closed evidence gate for MCP, Docker, PatchMon and Deployment operations.

Issue: #1101 — [Evidence/Fleet] MCP, Docker, PatchMon und Deployment revisionsgebunden absichern

Protected operation families
-----------------------------
- mcp_self_update                   MCP immutable-image build and self-update
- mcp_registry_tool_install         Registry/tool installation changes
- mcp_broker_launcher_change        Broker/launcher/host-worker changes
- docker_compose_container_change   Docker-Compose and container changes
- vps_deployment_restart_rollback   VPS deployment, restart and rollback
- patchmon_fleet_revision           PatchMon revision, health-lane and fleet actions
- host_patch_sovereign_runtime      Host patching that affects Sovereign runtimes

Fail-closed invariants
----------------------
- No MCP self-update to an unpublished or unverified image.
- ``running``, process liveness, or HTTP-200 alone does not satisfy a capability requirement.
  Collectors that observe only liveness must submit their observation as ``UNAVAILABLE``.
- Expected revision/digest and real readback must match exactly; a mismatch → CONTRADICTED.
- PatchMon provides evidence but does not itself decide VERIFIED.
- Rollback must reference a real, revision-bound existing digest. A pre_rollback_digest
  observation with neither a ``bound_revision`` nor a ``bound_digest`` cannot satisfy
  the requirement and yields ``BLOCKED_BY_MISSING_EVIDENCE`` with finding code
  ``rollback_reference_lacks_revision_or_digest_binding``.
- A post-mutation restart/rollback readback must also bind to a real revision or
  digest. A post_restart_rollback_readback observation with neither a
  ``bound_revision`` nor a ``bound_digest`` cannot satisfy the requirement and
  yields ``BLOCKED_BY_MISSING_EVIDENCE`` with finding code
  ``post_restart_rollback_readback_lacks_revision_or_digest_binding``.
- A partially reachable fleet is BLOCKED, never VERIFIED.
- ``auto_merge_allowed`` is always ``False``; the literal is immutable in the result dataclass.
- No raw prompt, repository content, token, or credential may appear in any evidence field.

This module contains no network, database, filesystem, clock, or random access.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Final, Sequence


_SHA40: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_SHA64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_.:-]{1,119}$")

MCP_FLEET_EVIDENCE_SCHEMA: Final[str] = "sovereign.mcp-fleet-deployment-evidence-gate.v1"

VERDICT_VERIFIED: Final[str] = "VERIFIED"
VERDICT_CONTRADICTED: Final[str] = "CONTRADICTED"
VERDICT_BLOCKED: Final[str] = "BLOCKED_BY_MISSING_EVIDENCE"

# All protected operation families
OPERATION_FAMILIES: Final[frozenset[str]] = frozenset({
    "docker_compose_container_change",
    "host_patch_sovereign_runtime",
    "mcp_broker_launcher_change",
    "mcp_registry_tool_install",
    "mcp_self_update",
    "patchmon_fleet_revision",
    "vps_deployment_restart_rollback",
})

# ---------------------------------------------------------------------------
# Per-family pre- and post-mutation evidence requirements
#
# Convention for requirement_id naming:
#   pre_*  — must be observed BEFORE mutation starts
#   post_* — must be observed AFTER mutation completes
#
# Both groups are evaluated together; the caller is responsible for
# providing observations from the correct phase.
# ---------------------------------------------------------------------------
_FAMILY_REQUIREMENTS: Final[dict[str, tuple[str, ...]]] = {
    "mcp_self_update": (
        # Pre-mutation
        "pre_source_runtime_revision",
        "pre_running_image_digest",
        "pre_mcp_protocol_status",
        "pre_broker_registry_status",
        "pre_rollback_digest",
        "pre_declared_capabilities",
        # Post-mutation
        "post_published_immutable_digest",
        "post_actual_running_digest",
        "post_mcp_initialize_canary",
        "post_capability_delta",
    ),
    "mcp_registry_tool_install": (
        "pre_source_runtime_revision",
        "pre_registry_tool_status",
        "pre_declared_capabilities",
        "post_actual_running_digest",
        "post_mcp_initialize_canary",
        "post_capability_delta",
    ),
    "mcp_broker_launcher_change": (
        "pre_source_runtime_revision",
        "pre_running_image_digest",
        "pre_broker_registry_status",
        "pre_rollback_digest",
        "pre_declared_capabilities",
        "post_actual_running_digest",
        "post_mcp_initialize_canary",
        "post_capability_delta",
    ),
    "docker_compose_container_change": (
        "pre_source_runtime_revision",
        "pre_running_image_digest",
        "pre_container_generation",
        "pre_rollback_digest",
        "pre_declared_capabilities",
        "post_published_immutable_digest",
        "post_actual_running_digest",
        "post_restart_rollback_readback",
        "post_capability_delta",
    ),
    "vps_deployment_restart_rollback": (
        "pre_source_runtime_revision",
        "pre_running_image_digest",
        "pre_mcp_protocol_status",
        "pre_container_generation",
        "pre_rollback_digest",
        "pre_declared_capabilities",
        "post_published_immutable_digest",
        "post_actual_running_digest",
        "post_mcp_initialize_canary",
        "post_patchmon_fleet_readback",
        "post_restart_rollback_readback",
        "post_capability_delta",
    ),
    "patchmon_fleet_revision": (
        "pre_source_runtime_revision",
        "pre_running_image_digest",
        "pre_container_generation",
        "pre_rollback_digest",
        "pre_declared_capabilities",
        "post_patchmon_fleet_readback",
        "post_restart_rollback_readback",
        "post_capability_delta",
    ),
    "host_patch_sovereign_runtime": (
        "pre_source_runtime_revision",
        "pre_running_image_digest",
        "pre_mcp_protocol_status",
        "pre_container_generation",
        "pre_rollback_digest",
        "pre_declared_capabilities",
        "post_actual_running_digest",
        "post_mcp_initialize_canary",
        "post_patchmon_fleet_readback",
        "post_restart_rollback_readback",
        "post_capability_delta",
    ),
}


def _canonical_sha256(value: Any) -> str:
    def _canonical(v: Any) -> Any:
        if v is None or isinstance(v, bool):
            return v
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            raise ValueError("float forbidden in mcp-fleet evidence")
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            return {str(k): _canonical(val) for k, val in sorted(v.items())}
        if isinstance(v, (list, tuple)):
            return [_canonical(item) for item in v]
        raise ValueError(f"non-serializable type: {type(v).__name__}")
    serialized = json.dumps(_canonical(value), separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _normalize_digest(raw: str) -> str:
    """Normalize a Docker/OCI image digest to bare lowercase hex.

    Accepts ``sha256:<64-hex>`` or a bare 64-hex string.
    Returns the bare 64-hex form, or empty string if the input is invalid.
    """
    cleaned = str(raw or "").strip().lower()
    if cleaned.startswith("sha256:"):
        cleaned = cleaned[len("sha256:"):]
    return cleaned if _SHA64.fullmatch(cleaned) else ""


# ---------------------------------------------------------------------------
# Evidence envelope
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class McpFleetEvidenceEnvelope:
    """Immutable evidence envelope for one fleet/deployment operation.

    Fields
    ------
    operation_family
        One of the seven OPERATION_FAMILIES.
    operation_identity
        Caller-supplied, opaque, non-secret identifier for this specific
        operation instance (e.g. a job ID or a deterministic hash of the
        operation parameters). Must match ``_IDENTIFIER``.
    repository
        Canonical ``owner/repo`` of the sovereign repository the operation
        is bound to.
    base_revision
        Full Git SHA-40 of the repository HEAD at envelope-creation time.
    expected_image_digest
        SHA-256 digest (bare hex or ``sha256:`` prefixed) of the immutable
        image that MUST be published BEFORE the operation may run.
        Pass an empty string only for ``mcp_registry_tool_install`` where
        the operation does not build/run an image.
    input_hash
        SHA-256 of the canonical operation parameters supplied by the caller.
    declared_capability_families
        Sorted tuple of capability family identifiers the caller declares are
        affected by this operation. At least one entry is required.
    """

    operation_family: str
    operation_identity: str
    repository: str
    base_revision: str
    expected_image_digest: str  # bare SHA-256 hex; empty for tool-only families
    input_hash: str
    declared_capability_families: tuple[str, ...]
    envelope_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        family = str(self.operation_family or "").strip().lower()
        if family not in OPERATION_FAMILIES:
            raise ValueError(f"unknown operation_family: {family!r}")
        if not _IDENTIFIER.fullmatch(str(self.operation_identity or "").strip()):
            raise ValueError("operation_identity must match [a-z][a-z0-9_.:-]{1,119}")
        if not _SHA40.fullmatch(str(self.base_revision or "").strip().lower()):
            raise ValueError("base_revision must be a full Git SHA-40")
        if not _SHA64.fullmatch(str(self.input_hash or "").strip().lower()):
            raise ValueError("input_hash must be a SHA-256")

        # Normalize image digest; empty string is only valid for families that
        # do not build/run an immutable image.
        normalized_digest = _normalize_digest(str(self.expected_image_digest or ""))
        _DIGEST_OPTIONAL_FAMILIES: frozenset[str] = frozenset({
            "mcp_registry_tool_install",
        })
        if not normalized_digest and family not in _DIGEST_OPTIONAL_FAMILIES:
            raise ValueError(
                f"expected_image_digest is required for operation_family {family!r}"
            )

        if not self.declared_capability_families:
            raise ValueError("declared_capability_families must not be empty")

        object.__setattr__(self, "operation_family", family)
        object.__setattr__(self, "base_revision", str(self.base_revision).strip().lower())
        object.__setattr__(self, "input_hash", str(self.input_hash).strip().lower())
        object.__setattr__(self, "expected_image_digest", normalized_digest)
        object.__setattr__(
            self,
            "declared_capability_families",
            tuple(sorted(str(c).strip() for c in self.declared_capability_families if str(c).strip())),
        )
        sha = _canonical_sha256(self._body())
        object.__setattr__(self, "envelope_sha256", sha)

    def _body(self) -> dict[str, Any]:
        return {
            "base_revision": str(self.base_revision),
            "declared_capability_families": list(self.declared_capability_families),
            "expected_image_digest": str(self.expected_image_digest),
            "input_hash": str(self.input_hash),
            "operation_family": str(self.operation_family),
            "operation_identity": str(self.operation_identity),
            "repository": str(self.repository),
            "schema_version": MCP_FLEET_EVIDENCE_SCHEMA,
        }


# ---------------------------------------------------------------------------
# Evidence observation
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class McpFleetObservation:
    """Single collected observation for one fleet/deployment evidence requirement.

    Fail-closed guidance for collectors
    ------------------------------------
    - An observation that captures only process liveness, HTTP-200, or a
      running flag WITHOUT a verified revision or digest MUST be submitted
      with ``assertion="UNAVAILABLE"``.  The gate treats UNAVAILABLE as
      insufficient; the requirement remains unsatisfied.
    - A PatchMon health-count observation (e.g. 4/4 workers healthy) MUST
      be accompanied by a separate observation carrying revision + digest +
      capability canary evidence.  The health count alone is UNAVAILABLE.
    - A rollback observation without a real, revision-bound digest MUST be
      submitted as UNAVAILABLE (rollback reference does not yet exist).
    - An observation whose ``bound_revision`` or ``bound_digest`` differs
      from the envelope values MUST be submitted as CONTRADICTED.
    """

    requirement_id: str
    value_hash: str         # SHA-256 of the canonical observation payload
    source: str             # e.g. "MCP_READBACK", "PATCHMON_READBACK", "IMAGE_READBACK"
    assertion: str          # "OBSERVED" | "CONTRADICTED" | "UNAVAILABLE"
    bound_revision: str     # git SHA-40; must match envelope.base_revision when non-empty
    bound_digest: str       # bare SHA-256; must match envelope.expected_image_digest when non-empty

    def __post_init__(self) -> None:
        assertion = str(self.assertion or "").strip().upper()
        if assertion not in {"OBSERVED", "CONTRADICTED", "UNAVAILABLE"}:
            raise ValueError(f"unsupported assertion: {assertion!r}")
        object.__setattr__(self, "assertion", assertion)

        if not _SHA64.fullmatch(str(self.value_hash or "").strip().lower()):
            raise ValueError("value_hash must be a SHA-256")
        object.__setattr__(self, "value_hash", str(self.value_hash).strip().lower())

        rev = str(self.bound_revision or "").strip().lower()
        if rev and not _SHA40.fullmatch(rev):
            raise ValueError("bound_revision must be a full Git SHA-40 or empty string")
        object.__setattr__(self, "bound_revision", rev)

        digest = _normalize_digest(str(self.bound_digest or ""))
        object.__setattr__(self, "bound_digest", digest)

    @property
    def observation_sha256(self) -> str:
        return _canonical_sha256({
            "assertion": self.assertion,
            "bound_digest": self.bound_digest,
            "bound_revision": self.bound_revision,
            "requirement_id": self.requirement_id,
            "source": self.source,
            "value_hash": self.value_hash,
        })


# ---------------------------------------------------------------------------
# Evaluation result
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class McpFleetEvidenceResult:
    """Fail-closed verdict for one fleet/deployment operation."""

    verdict: str
    operation_family: str
    envelope_sha256: str
    satisfied: tuple[str, ...]
    missing: tuple[str, ...]
    contradicted: tuple[str, ...]
    finding_codes: tuple[str, ...]
    auto_merge_allowed: bool  # always False


# ---------------------------------------------------------------------------
# Fail-closed evaluation
# ---------------------------------------------------------------------------

def evaluate_mcp_fleet_evidence(
    envelope: McpFleetEvidenceEnvelope,
    observations: Sequence[McpFleetObservation],
    *,
    expected_current_revision: str = "",
) -> McpFleetEvidenceResult:
    """Evaluate fail-closed evidence for a fleet/deployment operation.

    Parameters
    ----------
    envelope
        The evidence envelope claiming the operation outcome.
    observations
        The observations supplied as evidence.
    expected_current_revision
        Optional SHA-40 of the repository's *current* ``main`` HEAD. When
        supplied (non-empty), the envelope's ``base_revision`` MUST equal it
        exactly. A mismatch produces a BLOCKED verdict with
        ``envelope_revision_stale_against_current_main`` so a stale envelope
        cannot masquerade as evidence for the live revision (Issue #1101 /
        PR #1184). Default empty string disables the check for callers that
        legitimately want to evaluate a historical envelope.

    Verdict rules
    -------------
    VERIFIED
        Every requirement for the family has at least one OBSERVED observation
        with matching bound_revision (when non-empty) and matching bound_digest
        (when non-empty and the envelope carries an expected_image_digest).

    CONTRADICTED
        Any requirement has an observation whose bound_revision/bound_digest
        contradicts the envelope, or whose assertion is CONTRADICTED.
        Contradictions take priority over missing evidence.

    BLOCKED_BY_MISSING_EVIDENCE
        One or more requirements have no satisfying observation (missing or
        UNAVAILABLE only).

    Additional invariants enforced here
    ------------------------------------
    - For families that require ``post_published_immutable_digest``, an
      observation for that requirement whose ``bound_digest`` does not match
      ``envelope.expected_image_digest`` is CONTRADICTED.
    - For ``post_actual_running_digest``, a ``bound_digest`` mismatch with
      ``envelope.expected_image_digest`` is CONTRADICTED (the wrong image
      is running).
    - A PatchMon fleet readback observation that carries no bound_digest and
      no bound_revision is treated as UNAVAILABLE regardless of its assertion
      field (liveness-only bypass guard).
    """
    required = _FAMILY_REQUIREMENTS.get(envelope.operation_family, ())

    # Revision-freshness gate: when the caller supplies the live main HEAD,
    # the envelope MUST claim that exact revision. This blocks stale
    # envelopes from being mistaken for evidence about the running fleet.
    expected_rev = str(expected_current_revision or "").strip().lower()
    if expected_rev:
        if not _SHA40.fullmatch(expected_rev):
            raise ValueError("expected_current_revision must be a full Git SHA-40 or empty string")
        if envelope.base_revision != expected_rev:
            return McpFleetEvidenceResult(
                verdict=VERDICT_BLOCKED,
                operation_family=envelope.operation_family,
                envelope_sha256=envelope.envelope_sha256,
                satisfied=(),
                missing=(),
                contradicted=(),
                finding_codes=(
                    "envelope_revision_stale_against_current_main",
                    "expected_current_revision_mismatch",
                ),
                auto_merge_allowed=False,
            )

    obs_by_req: dict[str, list[McpFleetObservation]] = {}
    for obs in observations:
        obs_by_req.setdefault(obs.requirement_id, []).append(obs)

    satisfied: set[str] = set()
    missing: set[str] = set()
    contradicted: set[str] = set()
    findings: set[str] = set()

    # Families where post_*_digest observations must bind to expected_image_digest
    _DIGEST_BOUND_REQUIREMENTS: frozenset[str] = frozenset({
        "post_published_immutable_digest",
        "post_actual_running_digest",
    })

    for req_id in required:
        candidates = obs_by_req.get(req_id, [])
        if not candidates:
            missing.add(req_id)
            findings.add("required_observation_missing")
            continue

        req_satisfied = False
        req_contradicted = False

        for obs in candidates:
            # Liveness-only bypass guard: a PatchMon fleet readback that carries
            # neither a revision nor a digest provides no revision binding and
            # cannot satisfy the requirement.
            if (
                req_id == "post_patchmon_fleet_readback"
                and not obs.bound_revision
                and not obs.bound_digest
                and obs.assertion == "OBSERVED"
            ):
                findings.add("patchmon_readback_lacks_revision_or_digest_binding")
                continue

            # Empty-binding bypass guard: a rollback observation that references
            # neither a revision nor a digest cannot point to a real prior
            # image, so it cannot satisfy the rollback requirement either.
            if (
                req_id == "pre_rollback_digest"
                and not obs.bound_revision
                and not obs.bound_digest
                and obs.assertion == "OBSERVED"
            ):
                findings.add("rollback_reference_lacks_revision_or_digest_binding")
                continue

            # Post-mutation readback guard: a post_restart_rollback_readback
            # observation that carries neither a revision nor a digest provides
            # no evidence the restart/rollback actually landed on a known
            # image, so it cannot satisfy the post-mutation requirement.
            if (
                req_id == "post_restart_rollback_readback"
                and not obs.bound_revision
                and not obs.bound_digest
                and obs.assertion == "OBSERVED"
            ):
                findings.add("post_restart_rollback_readback_lacks_revision_or_digest_binding")
                continue

            # Revision binding check
            if obs.bound_revision and obs.bound_revision != envelope.base_revision:
                req_contradicted = True
                findings.add("observation_bound_to_stale_revision")
                continue

            # Digest binding check for post-mutation image requirements
            if (
                req_id in _DIGEST_BOUND_REQUIREMENTS
                and envelope.expected_image_digest
                and obs.bound_digest
                and obs.bound_digest != envelope.expected_image_digest
            ):
                req_contradicted = True
                findings.add("observation_digest_contradicts_expected_image")
                continue

            if obs.assertion == "CONTRADICTED":
                req_contradicted = True
                findings.add("observation_reports_contradiction")
                continue

            if obs.assertion == "UNAVAILABLE":
                findings.add("observation_unavailable")
                continue

            req_satisfied = True

        if req_contradicted:
            contradicted.add(req_id)
        elif req_satisfied:
            satisfied.add(req_id)
        else:
            missing.add(req_id)

    if contradicted:
        verdict = VERDICT_CONTRADICTED
    elif missing:
        verdict = VERDICT_BLOCKED
    else:
        verdict = VERDICT_VERIFIED

    return McpFleetEvidenceResult(
        verdict=verdict,
        operation_family=envelope.operation_family,
        envelope_sha256=envelope.envelope_sha256,
        satisfied=tuple(sorted(satisfied)),
        missing=tuple(sorted(missing)),
        contradicted=tuple(sorted(contradicted)),
        finding_codes=tuple(sorted(findings)),
        auto_merge_allowed=False,
    )


# ---------------------------------------------------------------------------
# Patchmon health-count audit
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PatchmonHealthAudit:
    """Audit result for a PatchMon fleet health-count claim."""

    accepted: bool
    blocker: str | None
    healthy_count: int
    total_count: int
    has_revision_binding: bool
    has_digest_binding: bool
    has_capability_canary: bool


def audit_patchmon_health_count(
    *,
    healthy_count: int,
    total_count: int,
    bound_revision: str,
    bound_digest: str,
    has_capability_canary: bool,
) -> PatchmonHealthAudit:
    """Verify that a PatchMon health-count claim is accompanied by required bindings.

    A health-count such as "4/4 workers healthy" is only accepted when ALL of:
    - bound_revision is a valid SHA-40 (revision binding), AND
    - bound_digest is a valid SHA-256 (digest binding), AND
    - has_capability_canary is True (a tool-canary was executed, not just a ping).

    Revision-only or digest-only is no longer sufficient: Issue #1101 / PR #1184
    require both the revision AND the digest to be bound so that a healthy
    fleet on a stale revision with an unknown image (or vice versa) cannot
    masquerade as VERIFIED.

    If the fleet is partially reachable (healthy_count < total_count) the claim
    is rejected with a dedicated blocker code — a partial fleet is never VERIFIED.
    """
    rev_ok = _SHA40.fullmatch(str(bound_revision or "").strip().lower()) is not None
    digest_ok = _SHA64.fullmatch(_normalize_digest(str(bound_digest or ""))) if bound_digest else False
    has_binding = rev_ok and bool(digest_ok)

    if healthy_count < total_count:
        return PatchmonHealthAudit(
            accepted=False,
            blocker="partial_fleet_reachable_not_verified",
            healthy_count=healthy_count,
            total_count=total_count,
            has_revision_binding=rev_ok,
            has_digest_binding=bool(digest_ok),
            has_capability_canary=has_capability_canary,
        )

    if not has_binding:
        # Either revision OR digest is missing. The blocker code distinguishes
        # the two cases so callers can tell which binding was absent, while
        # preserving the original "lacks_revision_and_digest_binding" code
        # for the fully-empty case.
        if not rev_ok and not digest_ok:
            blocker = "patchmon_health_count_lacks_revision_and_digest_binding"
        elif not rev_ok:
            blocker = "patchmon_health_count_lacks_revision_binding"
        else:
            blocker = "patchmon_health_count_lacks_digest_binding"
        return PatchmonHealthAudit(
            accepted=False,
            blocker=blocker,
            healthy_count=healthy_count,
            total_count=total_count,
            has_revision_binding=rev_ok,
            has_digest_binding=bool(digest_ok),
            has_capability_canary=has_capability_canary,
        )

    if not has_capability_canary:
        return PatchmonHealthAudit(
            accepted=False,
            blocker="patchmon_health_count_lacks_capability_canary",
            healthy_count=healthy_count,
            total_count=total_count,
            has_revision_binding=rev_ok,
            has_digest_binding=bool(digest_ok),
            has_capability_canary=False,
        )

    return PatchmonHealthAudit(
        accepted=True,
        blocker=None,
        healthy_count=healthy_count,
        total_count=total_count,
        has_revision_binding=rev_ok,
        has_digest_binding=bool(digest_ok),
        has_capability_canary=True,
    )


__all__ = [
    "MCP_FLEET_EVIDENCE_SCHEMA",
    "OPERATION_FAMILIES",
    "VERDICT_BLOCKED",
    "VERDICT_CONTRADICTED",
    "VERDICT_VERIFIED",
    "McpFleetEvidenceEnvelope",
    "McpFleetEvidenceResult",
    "McpFleetObservation",
    "PatchmonHealthAudit",
    "audit_patchmon_health_count",
    "evaluate_mcp_fleet_evidence",
]
