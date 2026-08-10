"""Read-only Evidence Collectors for Sovereign capability verification.

Issue: #1099 — [Evidence/Collectors] Bestehende Readbacks und Capability Delta vereinheitlichen

Each collector is:
- Pure and idempotent — no mutations, no persisted output.
- Revision-bound — every observation carries source revision or runtime identity.
- Fail-explicit — unreachable or invalid source returns UNVERIFIABLE, never success.
- Hash-canonical — all output hashes are deterministic SHA-256 via canonical_proof_sha256.

No raw responses, secrets, database rows, or provider contents are persisted.
No new persistence layer is added; output feeds into existing receipt/evidence flows.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Final, Mapping, Sequence

from .configuration.config_sources import ConfigResolutionContract
from .configuration.receipt import ConfigReceipt, verify_receipt


# ---------------------------------------------------------------------------
# Capability status vocabulary
# ---------------------------------------------------------------------------

PRESERVED: Final[str] = "PRESERVED"
REPLACED_WITH_VERIFIED_EQUIVALENT: Final[str] = "REPLACED_WITH_VERIFIED_EQUIVALENT"
INTENTIONALLY_REMOVED: Final[str] = "INTENTIONALLY_REMOVED"
DEGRADED: Final[str] = "DEGRADED"
LOST: Final[str] = "LOST"
UNVERIFIABLE: Final[str] = "UNVERIFIABLE"

CAPABILITY_STATUSES: Final[frozenset[str]] = frozenset({
    PRESERVED,
    REPLACED_WITH_VERIFIED_EQUIVALENT,
    INTENTIONALLY_REMOVED,
    DEGRADED,
    LOST,
    UNVERIFIABLE,
})

_SHA40: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_SHA64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_.:-]{0,119}$")

_SECRET_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"github_pat_[A-Za-z0-9_]{8,}", re.IGNORECASE),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{8,}", re.IGNORECASE),
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{10,}", re.IGNORECASE),
    re.compile(r"(?:token|password|passwd|secret|api[_-]?key)\s*[=:]\s*[^\s\n]{4,}", re.IGNORECASE),
    re.compile(r"Authorization:\s*(?:Bearer\s+)?[^\s\n]+", re.IGNORECASE),
)


class CollectorContractError(ValueError):
    """A collector input violated a deterministic invariant."""


# ---------------------------------------------------------------------------
# Canonical hashing (no external dep, self-contained)
# ---------------------------------------------------------------------------

def _canonical_value(value: Any) -> Any:
    """Normalize value to a canonical JSON-serializable form (sorted keys, no floats)."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise CollectorContractError("float values are forbidden in canonical evidence")
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return {str(k): _canonical_value(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    raise CollectorContractError(f"non-serializable type in canonical evidence: {type(value).__name__}")


def canonical_evidence_sha256(value: Any) -> str:
    """Return a deterministic SHA-256 hex digest of the canonical evidence value."""
    normalized = _canonical_value(value)
    serialized = json.dumps(normalized, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _redact(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


# ---------------------------------------------------------------------------
# Collector observation — the atomic unit of evidence
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CollectorObservation:
    """Single canonical observation from a read-only collector.

    Fields
    ------
    capability_id:      Stable identifier for the observed capability.
    source_revision:    Git SHA-40 or image digest pinning the observation.
    observation_hash:   SHA-256 of the canonical observation payload.
    status:             One of CAPABILITY_STATUSES (always UNVERIFIABLE when source absent).
    cause:              Human-readable reason (mandatory, no secrets).
    collector:          Collector family that produced this observation.
    detail:             Structured, redacted detail payload (no raw secrets/rows).
    """

    capability_id: str
    source_revision: str
    observation_hash: str
    status: str
    cause: str
    collector: str
    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(str(self.capability_id or "")):
            raise CollectorContractError(f"capability_id is not a valid identifier: {self.capability_id!r}")
        if not _IDENTIFIER.fullmatch(str(self.collector or "")):
            raise CollectorContractError(f"collector is not a valid identifier: {self.collector!r}")
        if self.status not in CAPABILITY_STATUSES:
            raise CollectorContractError(f"unsupported capability status: {self.status!r}")
        if not self.cause.strip():
            raise CollectorContractError("cause must not be empty")
        if len(self.cause) > 400:
            raise CollectorContractError("cause must not exceed 400 characters")
        rev = str(self.source_revision or "").strip()
        if rev and not (_SHA40.fullmatch(rev) or _SHA64.fullmatch(rev)):
            raise CollectorContractError("source_revision must be a full Git SHA-40 or SHA-256")
        if not _SHA64.fullmatch(str(self.observation_hash or "")):
            raise CollectorContractError("observation_hash must be a SHA-256 hex digest")

    def canonical_body(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "cause": self.cause,
            "collector": self.collector,
            "detail": _canonical_value(self.detail),
            "observation_hash": self.observation_hash,
            "source_revision": self.source_revision,
            "status": self.status,
        }


def build_observation(
    *,
    capability_id: str,
    collector: str,
    status: str,
    cause: str,
    source_revision: str = "",
    detail: dict[str, Any] | None = None,
) -> CollectorObservation:
    """Build and hash a canonical CollectorObservation from raw inputs."""
    safe_detail = _canonical_value(detail or {})
    payload_for_hash = {
        "capability_id": str(capability_id or "").strip().lower(),
        "cause": str(cause or "").strip(),
        "collector": str(collector or "").strip().lower(),
        "detail": safe_detail,
        "source_revision": str(source_revision or "").strip().lower(),
        "status": str(status or "").strip().upper(),
    }
    obs_hash = canonical_evidence_sha256(payload_for_hash)
    return CollectorObservation(
        capability_id=str(capability_id or "").strip().lower(),
        source_revision=str(source_revision or "").strip().lower(),
        observation_hash=obs_hash,
        status=str(status or "").strip().upper(),
        cause=str(cause or "").strip(),
        collector=str(collector or "").strip().lower(),
        detail=dict(safe_detail),
    )


# ---------------------------------------------------------------------------
# CapabilityDelta — sortable, replayable before/after comparison
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CapabilityEntry:
    """A single capability in the delta with its status and hashes."""
    capability_id: str
    status: str
    cause: str
    baseline_hash: str
    result_hash: str
    observation_hashes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CapabilityDelta:
    """Deterministic before/after capability comparison.

    Invariants
    ----------
    - sort-stable across identical inputs
    - replayable: delta_sha256 fully covers all observation hashes
    - no REPLACED_WITH_VERIFIED_EQUIVALENT without a readback observation
    """

    operation_family: str
    baseline_revision: str
    result_revision: str
    entries: tuple[CapabilityEntry, ...]
    delta_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation_family": self.operation_family,
            "baseline_revision": self.baseline_revision,
            "result_revision": self.result_revision,
            "entry_count": len(self.entries),
            "entries": [
                {
                    "capability_id": e.capability_id,
                    "status": e.status,
                    "cause": e.cause,
                    "baseline_hash": e.baseline_hash,
                    "result_hash": e.result_hash,
                    "observation_hashes": list(e.observation_hashes),
                }
                for e in self.entries
            ],
            "delta_sha256": self.delta_sha256,
        }


def build_capability_delta(
    *,
    operation_family: str,
    baseline_revision: str,
    result_revision: str,
    baseline_observations: Sequence[CollectorObservation],
    result_observations: Sequence[CollectorObservation],
) -> CapabilityDelta:
    """Build a sortable, replayable CapabilityDelta from two observation snapshots.

    Rules
    -----
    - Missing result → LOST
    - Missing baseline → new, classified as PRESERVED (first observation)
    - Identical hash → PRESERVED
    - result status explicitly UNVERIFIABLE → UNVERIFIABLE
    - result observation hash differs → compare statuses to determine change class
    """
    baseline_map: dict[str, CollectorObservation] = {o.capability_id: o for o in baseline_observations}
    result_map: dict[str, CollectorObservation] = {o.capability_id: o for o in result_observations}

    all_ids = sorted(set(baseline_map) | set(result_map))
    entries: list[CapabilityEntry] = []

    for cap_id in all_ids:
        base = baseline_map.get(cap_id)
        result = result_map.get(cap_id)

        base_hash = base.observation_hash if base else ("0" * 64)
        result_hash = result.observation_hash if result else ("0" * 64)
        obs_hashes: tuple[str, ...] = tuple(filter(None, [
            base.observation_hash if base else None,
            result.observation_hash if result else None,
        ]))

        if result is None:
            status = LOST
            cause = "capability absent in result snapshot"
        elif result.status == UNVERIFIABLE:
            status = UNVERIFIABLE
            cause = result.cause
        elif base is None:
            status = PRESERVED
            cause = "first observation — no baseline"
        elif base_hash == result_hash:
            status = PRESERVED
            cause = "observation unchanged"
        elif result.status == INTENTIONALLY_REMOVED:
            status = INTENTIONALLY_REMOVED
            cause = result.cause
        elif result.status == REPLACED_WITH_VERIFIED_EQUIVALENT:
            status = REPLACED_WITH_VERIFIED_EQUIVALENT
            cause = result.cause
        elif result.status in (DEGRADED, LOST):
            status = result.status
            cause = result.cause
        else:
            # hash changed but status PRESERVED — treat as degraded until proven equivalent
            status = DEGRADED
            cause = f"observation changed without verified-equivalent readback (was: {base.status})"

        entries.append(CapabilityEntry(
            capability_id=cap_id,
            status=status,
            cause=cause,
            baseline_hash=base_hash,
            result_hash=result_hash,
            observation_hashes=obs_hashes,
        ))

    delta_payload = {
        "baseline_revision": str(baseline_revision or "").strip().lower(),
        "entries": [
            {
                "baseline_hash": e.baseline_hash,
                "capability_id": e.capability_id,
                "observation_hashes": list(e.observation_hashes),
                "result_hash": e.result_hash,
                "status": e.status,
            }
            for e in entries
        ],
        "operation_family": str(operation_family or "").strip().lower(),
        "result_revision": str(result_revision or "").strip().lower(),
    }
    delta_sha256 = canonical_evidence_sha256(delta_payload)

    return CapabilityDelta(
        operation_family=str(operation_family or "").strip().lower(),
        baseline_revision=str(baseline_revision or "").strip().lower(),
        result_revision=str(result_revision or "").strip().lower(),
        entries=tuple(entries),
        delta_sha256=delta_sha256,
    )


# ---------------------------------------------------------------------------
# Collector families — pure, read-only observation builders
# ---------------------------------------------------------------------------

# --- Git-Workspace collector ---

def collect_git_workspace(
    *,
    head_sha: str,
    base_sha: str,
    diff_hash: str,
    changed_paths: Sequence[str],
    status_clean: bool,
) -> CollectorObservation:
    """Bind git-workspace observation to exact HEAD SHA.

    Parameters are caller-supplied from real git output (no live I/O here).
    `diff_hash` must be SHA-256 of the canonical diff content.
    """
    head = str(head_sha or "").strip().lower()
    base = str(base_sha or "").strip().lower()
    dh = str(diff_hash or "").strip().lower()
    paths = sorted({str(p or "").strip() for p in changed_paths if str(p or "").strip()})

    if not _SHA40.fullmatch(head):
        return build_observation(
            capability_id="git.workspace",
            collector="git_workspace",
            status=UNVERIFIABLE,
            cause="head_sha is not a valid full Git SHA",
        )
    if dh and not _SHA64.fullmatch(dh):
        return build_observation(
            capability_id="git.workspace",
            collector="git_workspace",
            status=UNVERIFIABLE,
            cause="diff_hash is not a valid SHA-256",
        )

    status = PRESERVED if status_clean else DEGRADED
    cause = "workspace matches head revision" if status_clean else "uncommitted changes present"
    return build_observation(
        capability_id="git.workspace",
        collector="git_workspace",
        status=status,
        source_revision=head,
        cause=cause,
        detail={
            "base_sha": base,
            "changed_path_count": len(paths),
            "changed_paths": paths[:50],
            "diff_hash": dh,
            "head_sha": head,
            "status_clean": status_clean,
        },
    )


# --- GitHub / CI collector ---

def collect_github_ci(
    *,
    head_sha: str,
    run_id: str,
    check_name: str,
    conclusion: str,
    workflow_sha: str,
) -> CollectorObservation:
    """Bind a GitHub CI check-run observation to exact head SHA and run identity."""
    head = str(head_sha or "").strip().lower()
    wf_sha = str(workflow_sha or "").strip().lower()
    conclusion_clean = str(conclusion or "").strip().lower()
    run = str(run_id or "").strip()
    check = str(check_name or "").strip()

    if not _SHA40.fullmatch(head):
        return build_observation(
            capability_id="ci.check",
            collector="github_ci",
            status=UNVERIFIABLE,
            cause="head_sha is not a valid full Git SHA",
        )
    if not run:
        return build_observation(
            capability_id="ci.check",
            collector="github_ci",
            status=UNVERIFIABLE,
            cause="run_id is missing",
        )

    PASSING = {"success", "neutral", "skipped"}
    if conclusion_clean in PASSING:
        status = PRESERVED
        cause = f"check '{check}' passed with conclusion '{conclusion_clean}'"
    elif conclusion_clean in {"failure", "error"}:
        status = DEGRADED
        cause = f"check '{check}' failed with conclusion '{conclusion_clean}'"
    elif conclusion_clean == "cancelled":
        status = UNVERIFIABLE
        cause = f"check '{check}' was cancelled — no conclusion"
    else:
        status = UNVERIFIABLE
        cause = f"check '{check}' conclusion '{conclusion_clean}' is not actionable"

    # Contradiction: workflow SHA differs from head SHA (stale)
    if wf_sha and _SHA40.fullmatch(wf_sha) and wf_sha != head:
        status = DEGRADED
        cause = f"workflow_sha {wf_sha[:12]}… does not match head_sha {head[:12]}… — stale binding"

    cap_id = f"ci.check.{re.sub(r'[^a-z0-9]', '.', check.lower())}"
    cap_id = cap_id[:80].rstrip(".")
    if not _IDENTIFIER.fullmatch(cap_id):
        cap_id = "ci.check"

    return build_observation(
        capability_id=cap_id,
        collector="github_ci",
        status=status,
        source_revision=head,
        cause=cause,
        detail={
            "check_name": check,
            "conclusion": conclusion_clean,
            "head_sha": head,
            "run_id": run,
            "workflow_sha": wf_sha,
        },
    )


# --- MCP collector ---

def collect_mcp(
    *,
    installed_revision: str,
    image_digest: str,
    registry: str,
    protocol_version: str,
    broker_reachable: bool,
    tool_canary_ok: bool,
) -> CollectorObservation:
    """Bind MCP installation observation to image digest and revision."""
    rev = str(installed_revision or "").strip().lower()
    digest = str(image_digest or "").strip().lower()
    registry_clean = _redact(str(registry or "").strip())
    protocol = str(protocol_version or "").strip()

    if not rev:
        return build_observation(
            capability_id="mcp.installation",
            collector="mcp",
            status=UNVERIFIABLE,
            cause="installed_revision is missing",
        )
    if not digest:
        return build_observation(
            capability_id="mcp.installation",
            collector="mcp",
            status=UNVERIFIABLE,
            cause="image_digest is missing — cannot bind observation",
        )
    valid_rev = rev if (_SHA40.fullmatch(rev) or _SHA64.fullmatch(rev)) else ""
    if not broker_reachable:
        return build_observation(
            capability_id="mcp.installation",
            collector="mcp",
            status=UNVERIFIABLE,
            source_revision=valid_rev,
            cause="MCP broker is not reachable",
        )
    if not tool_canary_ok:
        return build_observation(
            capability_id="mcp.installation",
            collector="mcp",
            status=DEGRADED,
            source_revision=valid_rev,
            cause="MCP tool canary failed — installation may be partially broken",
            detail={"image_digest": digest, "protocol_version": protocol, "registry": registry_clean},
        )

    source_rev = rev if (_SHA40.fullmatch(rev) or _SHA64.fullmatch(rev)) else ""
    return build_observation(
        capability_id="mcp.installation",
        collector="mcp",
        status=PRESERVED,
        source_revision=source_rev,
        cause="MCP broker reachable and tool canary passed",
        detail={
            "broker_reachable": True,
            "image_digest": digest,
            "installed_revision": rev,
            "protocol_version": protocol,
            "registry": registry_clean,
            "tool_canary_ok": True,
        },
    )


# --- Docker / PatchMon collector ---

def collect_docker(
    *,
    started_digest: str,
    container_generation: int,
    restart_count: int,
    health_status: str,
    fleet_revision: str,
) -> CollectorObservation:
    """Bind Docker/PatchMon observation to started image digest."""
    digest = str(started_digest or "").strip().lower()
    fleet_rev = str(fleet_revision or "").strip().lower()
    health = str(health_status or "").strip().lower()

    if not digest:
        return build_observation(
            capability_id="docker.container",
            collector="docker",
            status=UNVERIFIABLE,
            cause="started_digest is missing — cannot bind container observation",
        )

    # Process liveness is NOT capability evidence
    HEALTHY = {"healthy", "passing"}
    if health not in HEALTHY:
        status = DEGRADED
        cause = f"container health status is '{health}' — not a healthy state"
    elif restart_count > 5:
        status = DEGRADED
        cause = f"container restarted {restart_count} times — instability signal"
    else:
        status = PRESERVED
        cause = f"container digest bound, health '{health}', restart count {restart_count}"

    source_rev = fleet_rev if (_SHA40.fullmatch(fleet_rev) or _SHA64.fullmatch(fleet_rev)) else digest
    return build_observation(
        capability_id="docker.container",
        collector="docker",
        status=status,
        source_revision=source_rev,
        cause=cause,
        detail={
            "container_generation": int(container_generation),
            "fleet_revision": fleet_rev,
            "health_status": health,
            "restart_count": int(restart_count),
            "started_digest": digest,
        },
    )


# --- PostgreSQL collector ---

def collect_postgres(
    *,
    connection_canary_ok: bool,
    schema_hash: str,
    migration_owner: str,
    pgvector_available: bool,
    constraint_count: int,
    index_count: int,
) -> CollectorObservation:
    """Bind PostgreSQL capability observation to schema hash."""
    sh = str(schema_hash or "").strip().lower()
    owner = _redact(str(migration_owner or "").strip())

    if not connection_canary_ok:
        return build_observation(
            capability_id="postgres.schema",
            collector="postgres",
            status=UNVERIFIABLE,
            cause="PostgreSQL connection canary failed — schema unverifiable",
        )
    if not sh or not _SHA64.fullmatch(sh):
        return build_observation(
            capability_id="postgres.schema",
            collector="postgres",
            status=UNVERIFIABLE,
            cause="schema_hash is missing or invalid — cannot bind schema observation",
        )

    return build_observation(
        capability_id="postgres.schema",
        collector="postgres",
        status=PRESERVED,
        source_revision=sh,
        cause="schema hash bound, connection canary passed",
        detail={
            "connection_canary_ok": True,
            "constraint_count": int(constraint_count),
            "index_count": int(index_count),
            "migration_owner": owner,
            "pgvector_available": bool(pgvector_available),
            "schema_hash": sh,
        },
    )


# --- Provider collector ---

def collect_provider(
    *,
    openrouter_paid_route_ok: bool,
    free_route_revision: str,
    free_llm_revolver_ok: bool,
    paid_truth_boundary_hash: str,
) -> CollectorObservation:
    """Bind provider route observation to revision and truth-boundary hash."""
    rev = str(free_route_revision or "").strip().lower()
    tb_hash = str(paid_truth_boundary_hash or "").strip().lower()

    if tb_hash and not _SHA64.fullmatch(tb_hash):
        return build_observation(
            capability_id="provider.routes",
            collector="provider",
            status=UNVERIFIABLE,
            cause="paid_truth_boundary_hash is not a valid SHA-256",
        )
    if not rev:
        return build_observation(
            capability_id="provider.routes",
            collector="provider",
            status=UNVERIFIABLE,
            cause="free_route_revision is missing — cannot bind provider observation",
        )

    if not openrouter_paid_route_ok and not free_llm_revolver_ok:
        status = LOST
        cause = "both paid and free provider routes are unavailable"
    elif not openrouter_paid_route_ok:
        status = DEGRADED
        cause = "OpenRouter paid route unavailable — free route only"
    elif not free_llm_revolver_ok:
        status = DEGRADED
        cause = "free LLM revolver unavailable — paid route only"
    else:
        status = PRESERVED
        cause = "all provider routes reachable"

    source_rev = rev if (_SHA40.fullmatch(rev) or _SHA64.fullmatch(rev)) else ""
    return build_observation(
        capability_id="provider.routes",
        collector="provider",
        status=status,
        source_revision=source_rev,
        cause=cause,
        detail={
            "free_llm_revolver_ok": bool(free_llm_revolver_ok),
            "free_route_revision": rev,
            "openrouter_paid_route_ok": bool(openrouter_paid_route_ok),
            "paid_truth_boundary_hash": tb_hash,
        },
    )


def collect_config_provenance(
    *,
    resolution: ConfigResolutionContract,
    receipt: ConfigReceipt,
) -> CollectorObservation:
    """Bind the resolved configuration projection into the evidence surface.

    This is the read-only PatchMon readback that confirms the *actually loaded*
    configuration projection matches its redacted receipt. Config-drift (a
    CONTRADICTED resolution) invalidates prior run/permission bindings and
    blocks active countermeasures instead of silently continuing — it is
    reported as ``DEGRADED`` so the evidence gate cannot advance on a drifted
    config. A resolution that failed closed (``BLOCKED``) or a tampered receipt
    yields ``UNVERIFIABLE``: the loaded config cannot be bound to any revision.
    """
    if not isinstance(resolution, ConfigResolutionContract):
        raise CollectorContractError(
            "resolution must be a ConfigResolutionContract"
        )
    if not isinstance(receipt, ConfigReceipt):
        raise CollectorContractError("receipt must be a ConfigReceipt")

    rh = str(receipt.receipt_hash or "").strip().lower()
    if not rh or not _SHA64.fullmatch(rh):
        return build_observation(
            capability_id="configuration.provenance",
            collector="config_provenance",
            status=UNVERIFIABLE,
            cause="receipt_hash is missing or not a valid SHA-256 — config projection cannot be bound",
        )
    if not verify_receipt(receipt):
        return build_observation(
            capability_id="configuration.provenance",
            collector="config_provenance",
            status=UNVERIFIABLE,
            cause="receipt failed verification — loaded config projection does not match its receipt",
        )

    rev = str(receipt.revision or "").strip().lower()
    if rev and not (_SHA40.fullmatch(rev) or _SHA64.fullmatch(rev)):
        rev = ""

    status = resolution.status
    drift = resolution.drift
    errors = resolution.errors

    if status == "RESOLVED" and drift is None and not errors:
        cap_status = PRESERVED
        cause = "configuration projection resolved and receipt verified"
    elif status == "CONTRADICTED" or drift is not None:
        cap_status = DEGRADED
        drift_kind = drift.kind if drift else "content-drift"
        cause = (
            f"config-drift ({drift_kind}) invalidates prior run/permission bindings"
        )
    elif status == "BLOCKED":
        cap_status = UNVERIFIABLE
        cause = "configuration resolution blocked — no loadable projection to bind"
    elif status == "DEGRADED":
        cap_status = DEGRADED
        cause = "configuration resolution degraded — prior bindings invalidated"
    else:
        cap_status = UNVERIFIABLE
        cause = f"unknown resolution status: {status}"

    if not rev:
        rev = (
            str(resolution.resolved_hash or "").strip().lower()
            if _SHA64.fullmatch(str(resolution.resolved_hash or ""))
            else ""
        )

    detail = {
        "receipt_hash": rh,
        "schema_hash": str(resolution.schema_hash or ""),
        "resolved_hash": str(resolution.resolved_hash or ""),
        "status": status,
        "source_count": len(resolution.source_hashes),
        "image_digest": str(receipt.image_digest or "") or None,
        "drift": None if drift is None else drift.kind,
        "errors": tuple(errors) if errors else (),
    }

    return build_observation(
        capability_id="configuration.provenance",
        collector="config_provenance",
        status=cap_status,
        source_revision=rev,
        cause=cause,
        detail=detail,
    )


__all__ = [
    "CAPABILITY_STATUSES",
    "DEGRADED",
    "INTENTIONALLY_REMOVED",
    "LOST",
    "PRESERVED",
    "REPLACED_WITH_VERIFIED_EQUIVALENT",
    "UNVERIFIABLE",
    "CapabilityDelta",
    "CapabilityEntry",
    "CollectorContractError",
    "CollectorObservation",
    "build_capability_delta",
    "build_observation",
    "canonical_evidence_sha256",
    "collect_config_provenance",
    "collect_docker",
    "collect_git_workspace",
    "collect_github_ci",
    "collect_mcp",
    "collect_postgres",
    "collect_provider",
]
