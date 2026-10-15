"""Causal progress leases for long-running repository executions.

SCPL deliberately separates remote liveness from material repository progress.
The contracts in this module are pure: callers provide observed epochs and
authoritative workspace fingerprints; this module never reads clocks, Git,
network state, or persistence by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Any

from .agent_run_receipts import canonical_sha256


ProgressKind = Literal[
    "A2A_STATE_TRANSITION",
    "REPOSITORY_MATERIALIZED",
    "WORKSPACE_DELTA",
    "CLOSEOUT_TRANSITION",
]
LeaseVerdict = Literal[
    "CONTINUE_VERIFIED",
    "NO_PROGRESS",
    "STALLED",
    "UNVERIFIED",
    "CONTRADICTED",
]


def progress_occurs_after_epoch(
    receipt: "CausalProgressReceiptV1",
    boundary_epoch_ms: int,
) -> bool:
    """Return whether one material progress receipt is causally after a bound epoch."""
    if boundary_epoch_ms < 0:
        raise CausalProgressContractError("boundary_epoch_ms must be non-negative")
    return receipt.observed_epoch_ms > boundary_epoch_ms


class CausalProgressContractError(ValueError):
    """Raised when a progress receipt or lease violates the canonical contract."""


def _require_sha256(value: str, field: str, *, allow_empty: bool = False) -> str:
    clean = str(value or "").strip().lower()
    if allow_empty and not clean:
        return ""
    if len(clean) != 64 or any(ch not in "0123456789abcdef" for ch in clean):
        raise CausalProgressContractError(f"{field} must be a sha256 hex digest")
    return clean


def _require_git_sha(value: str, field: str) -> str:
    clean = str(value or "").strip().lower()
    if len(clean) != 40 or any(ch not in "0123456789abcdef" for ch in clean) or clean == "0" * 40:
        raise CausalProgressContractError(f"{field} must be a non-zero full Git SHA")
    return clean


@dataclass(frozen=True, slots=True)
class CausalProgressReceiptV1:
    schema_version: str
    job_id: str
    workspace_id: str
    a2a_task_id: str
    repository: str
    repository_revision: str
    progress_kind: ProgressKind
    previous_workspace_readback_sha256: str
    current_workspace_readback_sha256: str
    previous_receipt_sha256: str
    observed_epoch_ms: int
    receipt_sha256: str

    SCHEMA_VERSION = "sovereign.causal-progress-receipt.v1"

    @classmethod
    def build(
        cls,
        *,
        job_id: str,
        workspace_id: str,
        a2a_task_id: str,
        repository: str,
        repository_revision: str,
        progress_kind: ProgressKind,
        previous_workspace_readback_sha256: str,
        current_workspace_readback_sha256: str,
        previous_receipt_sha256: str = "",
        observed_epoch_ms: int,
    ) -> "CausalProgressReceiptV1":
        if progress_kind not in {
            "A2A_STATE_TRANSITION",
            "REPOSITORY_MATERIALIZED",
            "WORKSPACE_DELTA",
            "CLOSEOUT_TRANSITION",
        }:
            raise CausalProgressContractError("unsupported progress kind")
        if observed_epoch_ms < 0:
            raise CausalProgressContractError("observed_epoch_ms must be non-negative")
        current = _require_sha256(
            current_workspace_readback_sha256,
            "current_workspace_readback_sha256",
        )
        previous = _require_sha256(
            previous_workspace_readback_sha256,
            "previous_workspace_readback_sha256",
            allow_empty=True,
        )
        predecessor = _require_sha256(
            previous_receipt_sha256,
            "previous_receipt_sha256",
            allow_empty=True,
        )
        payload = {
            "schemaVersion": cls.SCHEMA_VERSION,
            "jobId": str(job_id),
            "workspaceId": str(workspace_id),
            "a2aTaskId": str(a2a_task_id),
            "repository": str(repository),
            "repositoryRevision": _require_git_sha(repository_revision, "repository_revision"),
            "progressKind": progress_kind,
            "previousWorkspaceReadbackSha256": previous,
            "currentWorkspaceReadbackSha256": current,
            "previousReceiptSha256": predecessor,
            "observedEpochMs": int(observed_epoch_ms),
        }
        return cls(
            schema_version=cls.SCHEMA_VERSION,
            job_id=payload["jobId"],
            workspace_id=payload["workspaceId"],
            a2a_task_id=payload["a2aTaskId"],
            repository=payload["repository"],
            repository_revision=payload["repositoryRevision"],
            progress_kind=progress_kind,
            previous_workspace_readback_sha256=previous,
            current_workspace_readback_sha256=current,
            previous_receipt_sha256=predecessor,
            observed_epoch_ms=int(observed_epoch_ms),
            receipt_sha256=canonical_sha256(payload),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "jobId": self.job_id,
            "workspaceId": self.workspace_id,
            "a2aTaskId": self.a2a_task_id,
            "repository": self.repository,
            "repositoryRevision": self.repository_revision,
            "progressKind": self.progress_kind,
            "previousWorkspaceReadbackSha256": self.previous_workspace_readback_sha256,
            "currentWorkspaceReadbackSha256": self.current_workspace_readback_sha256,
            "previousReceiptSha256": self.previous_receipt_sha256,
            "observedEpochMs": self.observed_epoch_ms,
            "receiptSha256": self.receipt_sha256,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "CausalProgressReceiptV1":
        receipt = cls.build(
            job_id=str(raw.get("jobId") or ""),
            workspace_id=str(raw.get("workspaceId") or ""),
            a2a_task_id=str(raw.get("a2aTaskId") or ""),
            repository=str(raw.get("repository") or ""),
            repository_revision=str(raw.get("repositoryRevision") or ""),
            progress_kind=str(raw.get("progressKind") or ""),  # type: ignore[arg-type]
            previous_workspace_readback_sha256=str(
                raw.get("previousWorkspaceReadbackSha256") or ""
            ),
            current_workspace_readback_sha256=str(
                raw.get("currentWorkspaceReadbackSha256") or ""
            ),
            previous_receipt_sha256=str(raw.get("previousReceiptSha256") or ""),
            observed_epoch_ms=int(raw.get("observedEpochMs") or 0),
        )
        if str(raw.get("receiptSha256") or "").lower() != receipt.receipt_sha256:
            raise CausalProgressContractError("progress receipt hash mismatch")
        return receipt


def validate_progress_successor(
    previous: CausalProgressReceiptV1 | None,
    current: CausalProgressReceiptV1,
) -> None:
    """Require one append-only causal successor; task IDs may change on retry."""

    if previous is None:
        if current.previous_receipt_sha256 or current.previous_workspace_readback_sha256:
            raise CausalProgressContractError(
                "first progress receipt may not claim a predecessor"
            )
        return
    if (
        current.job_id != previous.job_id
        or current.workspace_id != previous.workspace_id
        or current.repository != previous.repository
    ):
        raise CausalProgressContractError(
            "progress receipt changed job, workspace, or repository identity"
        )
    if current.previous_receipt_sha256 != previous.receipt_sha256:
        raise CausalProgressContractError(
            "progress receipt predecessor does not match current head"
        )
    if (
        current.previous_workspace_readback_sha256
        != previous.current_workspace_readback_sha256
    ):
        raise CausalProgressContractError(
            "progress receipt workspace predecessor does not match current head"
        )
    if current.observed_epoch_ms < previous.observed_epoch_ms:
        raise CausalProgressContractError(
            "progress receipt observation time moved backwards"
        )


@dataclass(frozen=True, slots=True)
class CausalProgressLeaseV1:
    job_id: str
    a2a_task_id: str
    source_revision: str
    last_progress_receipt_sha256: str
    last_material_progress_epoch_ms: int
    max_no_progress_seconds: int
    absolute_deadline_epoch_ms: int
    verdict: LeaseVerdict
    reason: str
    lease_sha256: str

    @classmethod
    def evaluate(
        cls,
        *,
        job_id: str,
        a2a_task_id: str,
        source_revision: str,
        last_progress_receipt_sha256: str,
        last_material_progress_epoch_ms: int,
        max_no_progress_seconds: int,
        absolute_deadline_epoch_ms: int,
        observed_epoch_ms: int,
        evidence_available: bool = True,
        contradicted: bool = False,
    ) -> "CausalProgressLeaseV1":
        if max_no_progress_seconds <= 0:
            raise CausalProgressContractError("max_no_progress_seconds must be positive")
        source_revision = str(source_revision or "").strip().lower()
        if absolute_deadline_epoch_ms <= 0 or observed_epoch_ms < 0:
            raise CausalProgressContractError("absolute deadline must be positive and observed epoch non-negative")
        if last_material_progress_epoch_ms > observed_epoch_ms:
            contradicted = True
        receipt_sha = _require_sha256(
            last_progress_receipt_sha256,
            "last_progress_receipt_sha256",
            allow_empty=True,
        )
        if contradicted:
            verdict: LeaseVerdict = "CONTRADICTED"
            reason = "progress evidence contradicts the bound execution"
        elif observed_epoch_ms >= absolute_deadline_epoch_ms:
            verdict = "STALLED"
            reason = "absolute repository execution deadline reached"
        elif not evidence_available:
            verdict = "UNVERIFIED"
            reason = "material progress evidence is unavailable"
        elif (
            last_material_progress_epoch_ms > 0
            and observed_epoch_ms - last_material_progress_epoch_ms
            >= max_no_progress_seconds * 1000
        ):
            verdict = "STALLED"
            reason = "no new material repository progress within the bounded lease"
        elif last_material_progress_epoch_ms <= 0:
            verdict = "NO_PROGRESS"
            reason = "no material repository progress has been observed"
        else:
            verdict = "CONTINUE_VERIFIED"
            reason = "recent material repository progress is independently observed"
        payload = {
            "jobId": str(job_id),
            "a2aTaskId": str(a2a_task_id),
            "sourceRevision": source_revision,
            "lastProgressReceiptSha256": receipt_sha,
            "lastMaterialProgressEpochMs": int(last_material_progress_epoch_ms),
            "maxNoProgressSeconds": int(max_no_progress_seconds),
            "absoluteDeadlineEpochMs": int(absolute_deadline_epoch_ms),
            "observedEpochMs": int(observed_epoch_ms),
            "verdict": verdict,
            "reason": reason,
        }
        return cls(
            job_id=str(job_id),
            a2a_task_id=str(a2a_task_id),
            source_revision=source_revision,
            last_progress_receipt_sha256=receipt_sha,
            last_material_progress_epoch_ms=int(last_material_progress_epoch_ms),
            max_no_progress_seconds=int(max_no_progress_seconds),
            absolute_deadline_epoch_ms=int(absolute_deadline_epoch_ms),
            verdict=verdict,
            reason=reason,
            lease_sha256=canonical_sha256(payload),
        )
