"""Causal Progress Lease contracts for long-running repository execution.

SCPL deliberately separates remote liveness from material repository progress.
Only independently read Git/workspace identities can renew material progress.
Heartbeats, tasks/get polling, UI activity and agent text are never progress.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Literal, Mapping, Sequence


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


class CausalProgressContractError(ValueError):
    """Raised when a progress receipt or lease violates its canonical contract."""


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_sha256(value: str, field: str, *, allow_empty: bool = False) -> str:
    clean = str(value or "").strip().lower()
    if allow_empty and not clean:
        return ""
    if len(clean) != 64 or any(ch not in "0123456789abcdef" for ch in clean):
        raise CausalProgressContractError(f"{field} must be a lowercase sha256")
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
    observed_at_epoch_ms: int
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
        previous_receipt_sha256: str,
        observed_at_epoch_ms: int,
    ) -> "CausalProgressReceiptV1":
        current = _require_sha256(current_workspace_readback_sha256, "current_workspace_readback_sha256")
        previous_workspace = _require_sha256(
            previous_workspace_readback_sha256,
            "previous_workspace_readback_sha256",
            allow_empty=True,
        )
        predecessor = _require_sha256(
            previous_receipt_sha256,
            "previous_receipt_sha256",
            allow_empty=True,
        )
        if previous_workspace and previous_workspace == current:
            raise CausalProgressContractError("identical workspace readback is not material progress")
        if progress_kind not in {
            "A2A_STATE_TRANSITION",
            "REPOSITORY_MATERIALIZED",
            "WORKSPACE_DELTA",
            "CLOSEOUT_TRANSITION",
        }:
            raise CausalProgressContractError("unsupported progress_kind")
        if not str(job_id).strip() or not str(workspace_id).strip() or not str(a2a_task_id).strip():
            raise CausalProgressContractError("job/workspace/task identity is required")
        if observed_at_epoch_ms < 0:
            raise CausalProgressContractError("observed_at_epoch_ms must be non-negative")
        payload = {
            "schemaVersion": cls.SCHEMA_VERSION,
            "jobId": str(job_id),
            "workspaceId": str(workspace_id),
            "a2aTaskId": str(a2a_task_id),
            "repository": str(repository),
            "repositoryRevision": str(repository_revision).lower(),
            "progressKind": progress_kind,
            "previousWorkspaceReadbackSha256": previous_workspace,
            "currentWorkspaceReadbackSha256": current,
            "previousReceiptSha256": predecessor,
            "observedAtEpochMs": int(observed_at_epoch_ms),
        }
        return cls(
            schema_version=cls.SCHEMA_VERSION,
            job_id=payload["jobId"],
            workspace_id=payload["workspaceId"],
            a2a_task_id=payload["a2aTaskId"],
            repository=payload["repository"],
            repository_revision=payload["repositoryRevision"],
            progress_kind=progress_kind,
            previous_workspace_readback_sha256=previous_workspace,
            current_workspace_readback_sha256=current,
            previous_receipt_sha256=predecessor,
            observed_at_epoch_ms=int(observed_at_epoch_ms),
            receipt_sha256=_canonical_sha256(payload),
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
            "observedAtEpochMs": self.observed_at_epoch_ms,
            "receiptSha256": self.receipt_sha256,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "CausalProgressReceiptV1":
        built = cls.build(
            job_id=str(raw.get("jobId") or ""),
            workspace_id=str(raw.get("workspaceId") or ""),
            a2a_task_id=str(raw.get("a2aTaskId") or ""),
            repository=str(raw.get("repository") or ""),
            repository_revision=str(raw.get("repositoryRevision") or ""),
            progress_kind=str(raw.get("progressKind") or ""),  # type: ignore[arg-type]
            previous_workspace_readback_sha256=str(raw.get("previousWorkspaceReadbackSha256") or ""),
            current_workspace_readback_sha256=str(raw.get("currentWorkspaceReadbackSha256") or ""),
            previous_receipt_sha256=str(raw.get("previousReceiptSha256") or ""),
            observed_at_epoch_ms=int(raw.get("observedAtEpochMs") or 0),
        )
        supplied = _require_sha256(str(raw.get("receiptSha256") or ""), "receiptSha256")
        if supplied != built.receipt_sha256:
            raise CausalProgressContractError("progress receipt hash mismatch")
        return built


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

    SCHEMA_VERSION = "sovereign.causal-progress-lease.v1"

    @classmethod
    def evaluate(
        cls,
        *,
        job_id: str,
        a2a_task_id: str,
        source_revision: str,
        latest_receipt: CausalProgressReceiptV1 | None,
        created_at_epoch_ms: int,
        observed_at_epoch_ms: int,
        max_no_progress_seconds: int,
        absolute_deadline_epoch_ms: int,
        readback_available: bool,
    ) -> "CausalProgressLeaseV1":
        if max_no_progress_seconds <= 0:
            raise CausalProgressContractError("max_no_progress_seconds must be positive")
        if absolute_deadline_epoch_ms <= created_at_epoch_ms:
            raise CausalProgressContractError("absolute deadline must follow creation")
        last_epoch = latest_receipt.observed_at_epoch_ms if latest_receipt else created_at_epoch_ms
        receipt_hash = latest_receipt.receipt_sha256 if latest_receipt else ""
        if latest_receipt and (
            latest_receipt.job_id != job_id
            or latest_receipt.a2a_task_id != a2a_task_id
            or latest_receipt.repository_revision != source_revision.lower()
        ):
            verdict: LeaseVerdict = "CONTRADICTED"
            reason = "latest progress receipt is bound to another execution identity"
        elif observed_at_epoch_ms >= absolute_deadline_epoch_ms:
            verdict = "STALLED"
            reason = "absolute repository execution deadline reached"
        elif not readback_available:
            verdict = "UNVERIFIED"
            reason = "material workspace readback unavailable"
        elif observed_at_epoch_ms - last_epoch >= max_no_progress_seconds * 1000:
            verdict = "NO_PROGRESS"
            reason = "no new material workspace state within the progress lease"
        else:
            verdict = "CONTINUE_VERIFIED"
            reason = "bounded continuation is supported by the current progress lease"
        payload = {
            "schemaVersion": cls.SCHEMA_VERSION,
            "jobId": job_id,
            "a2aTaskId": a2a_task_id,
            "sourceRevision": source_revision.lower(),
            "lastProgressReceiptSha256": receipt_hash,
            "lastMaterialProgressEpochMs": last_epoch,
            "maxNoProgressSeconds": int(max_no_progress_seconds),
            "absoluteDeadlineEpochMs": int(absolute_deadline_epoch_ms),
            "verdict": verdict,
            "reason": reason,
        }
        return cls(
            job_id=job_id,
            a2a_task_id=a2a_task_id,
            source_revision=source_revision.lower(),
            last_progress_receipt_sha256=receipt_hash,
            last_material_progress_epoch_ms=last_epoch,
            max_no_progress_seconds=int(max_no_progress_seconds),
            absolute_deadline_epoch_ms=int(absolute_deadline_epoch_ms),
            verdict=verdict,
            reason=reason,
            lease_sha256=_canonical_sha256(payload),
        )


def latest_progress_receipt(
    receipts: Sequence[CausalProgressReceiptV1],
    *,
    job_id: str,
    workspace_id: str,
    a2a_task_id: str,
    repository_revision: str,
) -> CausalProgressReceiptV1 | None:
    previous_hash = ""
    previous_workspace_hash = ""
    previous_epoch_ms = -1
    latest: CausalProgressReceiptV1 | None = None
    for receipt in receipts:
        if (
            receipt.job_id != job_id
            or receipt.workspace_id != workspace_id
            or receipt.a2a_task_id != a2a_task_id
            or receipt.repository_revision != repository_revision.lower()
        ):
            raise CausalProgressContractError("progress receipt identity mismatch")
        if receipt.previous_receipt_sha256 != previous_hash:
            raise CausalProgressContractError("progress receipt predecessor chain mismatch")
        if receipt.previous_workspace_readback_sha256 != previous_workspace_hash:
            raise CausalProgressContractError("progress workspace predecessor mismatch")
        if receipt.observed_at_epoch_ms <= previous_epoch_ms:
            raise CausalProgressContractError("progress receipt time must increase monotonically")
        previous_hash = receipt.receipt_sha256
        previous_workspace_hash = receipt.current_workspace_readback_sha256
        previous_epoch_ms = receipt.observed_at_epoch_ms
        latest = receipt
    return latest


def seen_workspace_readbacks(receipts: Sequence[CausalProgressReceiptV1]) -> frozenset[str]:
    return frozenset(receipt.current_workspace_readback_sha256 for receipt in receipts)
