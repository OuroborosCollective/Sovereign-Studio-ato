"""Deterministic revocation closure for durable workflow permissions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Iterable, Mapping

from .causal_progress_lease import CausalProgressReceiptV1, progress_occurs_after_epoch
from .durable_workflow import PermissionDecision, PermissionReceipt, canonical_sha256


class RevocationClosureError(ValueError):
    """Raised when revocation evidence violates the canonical contract."""


class RevocationClosureVerdict(str, Enum):
    REVOCATION_CLOSED_VERIFIED = "REVOCATION_CLOSED_VERIFIED"
    REVOCATION_PARTIAL = "REVOCATION_PARTIAL"
    UNVERIFIED = "UNVERIFIED"
    POST_REVOCATION_EFFECT_OBSERVED = "POST_REVOCATION_EFFECT_OBSERVED"
    CONTRADICTED = "CONTRADICTED"


@dataclass(frozen=True, slots=True)
class PermissionAuthorityHead:
    permission_id: str
    workflow_run_id: str
    receipt_hash: str
    receipt_sequence: int
    decision: PermissionDecision
    readback_hash: str

    def canonical(self) -> dict[str, Any]:
        return {
            "permission_id": self.permission_id,
            "workflow_run_id": self.workflow_run_id,
            "receipt_hash": self.receipt_hash,
            "receipt_sequence": self.receipt_sequence,
            "decision": self.decision.value,
        }

    def verify(self) -> bool:
        return canonical_sha256(self.canonical()) == self.readback_hash


@dataclass(frozen=True, slots=True)
class RevocationReceipt:
    permission_id: str
    workflow_run_id: str
    owner_identity: str
    repository_identity: str
    workspace_id: str
    predecessor_receipt_hash: str
    revoked_permission_receipt_hash: str
    revocation_sequence: int
    revocation_epoch_ms: int
    decision: PermissionDecision
    reason_code: str
    progress_head_sha256: str
    receipt_hash: str

    def canonical(self) -> dict[str, Any]:
        return {
            "schema_version": "sovereign.revocation-receipt.v1",
            "permission_id": self.permission_id,
            "workflow_run_id": self.workflow_run_id,
            "owner_identity": self.owner_identity,
            "repository_identity": self.repository_identity,
            "workspace_id": self.workspace_id,
            "predecessor_receipt_hash": self.predecessor_receipt_hash,
            "revoked_permission_receipt_hash": self.revoked_permission_receipt_hash,
            "revocation_sequence": self.revocation_sequence,
            "revocation_epoch_ms": self.revocation_epoch_ms,
            "decision": self.decision.value,
            "reason_code": self.reason_code,
            "progress_head_sha256": self.progress_head_sha256,
        }

    def verify(self) -> bool:
        return canonical_sha256(self.canonical()) == self.receipt_hash


@dataclass(frozen=True, slots=True)
class RevocationClosureReceipt:
    revocation_receipt_hash: str
    workflow_run_id: str
    permission_id: str
    affected_job_ids: tuple[str, ...]
    affected_effect_paths: tuple[str, ...]
    authority_head_readback_hash: str
    boundary_log_hashes: tuple[str, ...]
    progress_receipt_sha256s: tuple[str, ...]
    uncovered_effect_paths: tuple[str, ...]
    post_revocation_effects: tuple[str, ...]
    verdict: RevocationClosureVerdict
    receipt_hash: str

    def canonical(self) -> dict[str, Any]:
        return {
            "schema_version": "sovereign.revocation-closure-receipt.v1",
            "revocation_receipt_hash": self.revocation_receipt_hash,
            "workflow_run_id": self.workflow_run_id,
            "permission_id": self.permission_id,
            "affected_job_ids": list(self.affected_job_ids),
            "affected_effect_paths": list(self.affected_effect_paths),
            "authority_head_readback_hash": self.authority_head_readback_hash,
            "boundary_log_hashes": list(self.boundary_log_hashes),
            "progress_receipt_sha256s": list(self.progress_receipt_sha256s),
            "uncovered_effect_paths": list(self.uncovered_effect_paths),
            "post_revocation_effects": list(self.post_revocation_effects),
            "verdict": self.verdict.value,
        }

    def verify(self) -> bool:
        return canonical_sha256(self.canonical()) == self.receipt_hash


def create_revocation_transition(
    approved: PermissionReceipt,
    *,
    revocation_sequence: int,
    revocation_epoch_ms: int,
    reason_code: str,
    revoker_identity: str,
    progress_head_sha256: str = "",
    decision: PermissionDecision = PermissionDecision.REVOKED,
) -> tuple[PermissionReceipt, RevocationReceipt]:
    if not approved.verify() or approved.decision != PermissionDecision.APPROVED:
        raise RevocationClosureError("revocation requires the current verified APPROVED permission")
    if decision not in {PermissionDecision.REVOKED, PermissionDecision.SUPERSEDED}:
        raise RevocationClosureError("revocation decision must be REVOKED or SUPERSEDED")
    if revocation_sequence <= 0 or revocation_epoch_ms < 0:
        raise RevocationClosureError("revocation sequence/epoch is invalid")
    reason = str(reason_code or "").strip()
    revoker = str(revoker_identity or "").strip()
    if not reason or not revoker:
        raise RevocationClosureError("reason_code and revoker_identity are required")
    progress_sha = str(progress_head_sha256 or "").strip().lower()
    if progress_sha and (len(progress_sha) != 64 or any(ch not in "0123456789abcdef" for ch in progress_sha)):
        raise RevocationClosureError("progress_head_sha256 must be empty or sha256")

    revoked_permission = replace(
        approved,
        decision=decision,
        predecessor_receipt_hash=approved.receipt_hash,
        receipt_hash="",
    )
    revoked_permission = replace(
        revoked_permission,
        receipt_hash=canonical_sha256(revoked_permission.canonical()),
    )
    base = RevocationReceipt(
        permission_id=approved.permission_id,
        workflow_run_id=approved.binding.workflow_run_id,
        owner_identity=revoker,
        repository_identity=approved.binding.repository_identity,
        workspace_id=approved.binding.workspace_id,
        predecessor_receipt_hash=approved.receipt_hash,
        revoked_permission_receipt_hash=revoked_permission.receipt_hash,
        revocation_sequence=revocation_sequence,
        revocation_epoch_ms=revocation_epoch_ms,
        decision=decision,
        reason_code=reason,
        progress_head_sha256=progress_sha,
        receipt_hash="",
    )
    return revoked_permission, replace(base, receipt_hash=canonical_sha256(base.canonical()))


def require_live_permission(
    approved: PermissionReceipt,
    head: PermissionAuthorityHead | None,
) -> PermissionAuthorityHead:
    if not approved.verify() or approved.decision != PermissionDecision.APPROVED:
        raise RevocationClosureError("permission is not a valid APPROVED receipt")
    if head is None or not head.verify():
        raise RevocationClosureError("permission authority head is unreadable or invalid")
    if head.permission_id != approved.permission_id or head.workflow_run_id != approved.binding.workflow_run_id:
        raise RevocationClosureError("permission authority head identity mismatch")
    if head.receipt_hash != approved.receipt_hash or head.decision != PermissionDecision.APPROVED:
        raise RevocationClosureError("permission receipt is revoked, superseded or stale")
    return head


def evaluate_closure(
    *,
    revocation: RevocationReceipt,
    head: PermissionAuthorityHead | None,
    progress_receipts: Iterable[Mapping[str, Any]] = (),
    affected_job_ids: Iterable[str] = (),
    affected_effect_paths: Iterable[str] = (),
    boundary_log_hashes: Iterable[str] = (),
    uncovered_effect_paths: Iterable[str] = (),
    post_revocation_effects: Iterable[str] = (),
) -> RevocationClosureReceipt:
    progress_objects: list[CausalProgressReceiptV1] = []
    for raw in progress_receipts:
        progress_objects.append(CausalProgressReceiptV1.from_dict(raw))
    progress_hashes = tuple(sorted({item.receipt_sha256 for item in progress_objects}))
    post_progress = [
        item for item in progress_objects
        if progress_occurs_after_epoch(item, revocation.revocation_epoch_ms)
    ]
    effects = tuple(sorted(set(post_revocation_effects)))
    uncovered = tuple(sorted(set(uncovered_effect_paths)))

    if not revocation.verify():
        verdict = RevocationClosureVerdict.CONTRADICTED
        head_hash = ""
    elif head is None or not head.verify():
        verdict = RevocationClosureVerdict.UNVERIFIED
        head_hash = ""
    elif head.permission_id != revocation.permission_id or head.workflow_run_id != revocation.workflow_run_id:
        verdict = RevocationClosureVerdict.CONTRADICTED
        head_hash = head.readback_hash
    elif effects or post_progress:
        verdict = RevocationClosureVerdict.POST_REVOCATION_EFFECT_OBSERVED
        head_hash = head.readback_hash
    elif head.decision not in {PermissionDecision.REVOKED, PermissionDecision.SUPERSEDED}:
        verdict = RevocationClosureVerdict.CONTRADICTED
        head_hash = head.readback_hash
    elif uncovered:
        verdict = RevocationClosureVerdict.REVOCATION_PARTIAL
        head_hash = head.readback_hash
    else:
        verdict = RevocationClosureVerdict.REVOCATION_CLOSED_VERIFIED
        head_hash = head.readback_hash

    receipt = RevocationClosureReceipt(
        revocation_receipt_hash=revocation.receipt_hash,
        workflow_run_id=revocation.workflow_run_id,
        permission_id=revocation.permission_id,
        affected_job_ids=tuple(sorted(set(affected_job_ids))),
        affected_effect_paths=tuple(sorted(set(affected_effect_paths))),
        authority_head_readback_hash=head_hash,
        boundary_log_hashes=tuple(sorted(set(boundary_log_hashes))),
        progress_receipt_sha256s=progress_hashes,
        uncovered_effect_paths=uncovered,
        post_revocation_effects=effects,
        verdict=verdict,
        receipt_hash="",
    )
    return replace(receipt, receipt_hash=canonical_sha256(receipt.canonical()))
