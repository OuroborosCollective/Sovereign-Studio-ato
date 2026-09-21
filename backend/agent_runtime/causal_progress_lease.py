"""Deterministic material-progress receipts and bounded continuation leases.

SCPL deliberately separates liveness from progress. A heartbeat, tasks/get poll,
UI activity, or repeated workspace state can never renew the lease. Only a new
authoritative workspace readback may produce a material-progress receipt.

The module is pure: it performs no Git, database, network, or clock I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Final, Mapping, Sequence

from .agent_run_receipts import ReceiptContractError, canonical_sha256


SCHEMA_VERSION: Final[str] = "sovereign.causal-progress-receipt.v1"
ZERO_SHA256: Final[str] = "0" * 64
_SHA40: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_SHA64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_PROGRESS_KINDS: Final[frozenset[str]] = frozenset({
    "A2A_STATE_TRANSITION",
    "REPOSITORY_MATERIALIZED",
    "WORKSPACE_DELTA",
    "CLOSEOUT_TRANSITION",
})
_MATERIAL_PROGRESS_KINDS: Final[frozenset[str]] = frozenset({
    "A2A_STATE_TRANSITION",
    "WORKSPACE_DELTA",
    "CLOSEOUT_TRANSITION",
})


def _bounded_text(value: Any, *, field: str, limit: int = 240) -> str:
    text = " ".join(str(value or "").replace("\\x00", "").split())
    if not text or len(text) > limit:
        raise ReceiptContractError(f"{field} is missing or exceeds {limit} chars")
    return text


def _sha64(value: Any, *, field: str, allow_zero: bool = False) -> str:
    text = str(value or "").strip().lower()
    if not _SHA64.fullmatch(text):
        raise ReceiptContractError(f"{field} must be a lowercase SHA-256")
    if not allow_zero and text == ZERO_SHA256:
        raise ReceiptContractError(f"{field} must not be zero")
    return text


def _sha40(value: Any, *, field: str) -> str:
    text = str(value or "").strip().lower()
    if not _SHA40.fullmatch(text):
        raise ReceiptContractError(f"{field} must be a full lowercase Git SHA")
    return text


@dataclass(frozen=True, slots=True)
class CausalProgressReceiptV1:
    sequence: int
    job_id: str
    workspace_id: str
    a2a_task_id: str
    repository: str
    repository_revision: str
    progress_kind: str
    previous_workspace_readback_sha256: str
    current_workspace_readback_sha256: str
    previous_receipt_sha256: str
    receipt_sha256: str

    def body(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "sequence": self.sequence,
            "jobId": self.job_id,
            "workspaceId": self.workspace_id,
            "a2aTaskId": self.a2a_task_id,
            "repository": self.repository,
            "repositoryRevision": self.repository_revision,
            "progressKind": self.progress_kind,
            "previousWorkspaceReadbackSha256": self.previous_workspace_readback_sha256,
            "currentWorkspaceReadbackSha256": self.current_workspace_readback_sha256,
            "previousReceiptSha256": self.previous_receipt_sha256,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.body(), "receiptSha256": self.receipt_sha256}

    @property
    def material(self) -> bool:
        return self.progress_kind in _MATERIAL_PROGRESS_KINDS

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CausalProgressReceiptV1":
        if str(value.get("schemaVersion") or "") != SCHEMA_VERSION:
            raise ReceiptContractError("unsupported causal progress receipt schema")
        sequence = int(value.get("sequence"))
        if sequence < 0:
            raise ReceiptContractError("causal progress sequence must be non-negative")
        progress_kind = str(value.get("progressKind") or "").strip().upper()
        if progress_kind not in _ALLOWED_PROGRESS_KINDS:
            raise ReceiptContractError("unsupported causal progress kind")
        receipt = cls(
            sequence=sequence,
            job_id=_bounded_text(value.get("jobId"), field="jobId", limit=160),
            workspace_id=_bounded_text(value.get("workspaceId"), field="workspaceId", limit=160),
            a2a_task_id=_bounded_text(value.get("a2aTaskId"), field="a2aTaskId", limit=240),
            repository=_bounded_text(value.get("repository"), field="repository", limit=500),
            repository_revision=_sha40(value.get("repositoryRevision"), field="repositoryRevision"),
            progress_kind=progress_kind,
            previous_workspace_readback_sha256=_sha64(
                value.get("previousWorkspaceReadbackSha256"),
                field="previousWorkspaceReadbackSha256",
                allow_zero=True,
            ),
            current_workspace_readback_sha256=_sha64(
                value.get("currentWorkspaceReadbackSha256"),
                field="currentWorkspaceReadbackSha256",
            ),
            previous_receipt_sha256=_sha64(
                value.get("previousReceiptSha256"),
                field="previousReceiptSha256",
                allow_zero=True,
            ),
            receipt_sha256=_sha64(value.get("receiptSha256"), field="receiptSha256"),
        )
        if canonical_sha256(receipt.body()) != receipt.receipt_sha256:
            raise ReceiptContractError("causal progress receipt hash mismatch")
        return receipt


def build_causal_progress_receipt(
    *,
    sequence: int,
    job_id: str,
    workspace_id: str,
    a2a_task_id: str,
    repository: str,
    repository_revision: str,
    progress_kind: str,
    previous_workspace_readback_sha256: str,
    current_workspace_readback_sha256: str,
    previous_receipt_sha256: str,
) -> CausalProgressReceiptV1:
    body = {
        "schemaVersion": SCHEMA_VERSION,
        "sequence": int(sequence),
        "jobId": job_id,
        "workspaceId": workspace_id,
        "a2aTaskId": a2a_task_id,
        "repository": repository,
        "repositoryRevision": repository_revision,
        "progressKind": str(progress_kind or "").upper(),
        "previousWorkspaceReadbackSha256": str(previous_workspace_readback_sha256 or "").lower(),
        "currentWorkspaceReadbackSha256": str(current_workspace_readback_sha256 or "").lower(),
        "previousReceiptSha256": str(previous_receipt_sha256 or "").lower(),
    }
    if body["previousWorkspaceReadbackSha256"] == body["currentWorkspaceReadbackSha256"]:
        raise ReceiptContractError("identical workspace state is not new progress")
    body["receiptSha256"] = canonical_sha256(body)
    receipt = CausalProgressReceiptV1.from_dict(body)
    if receipt.sequence == 0:
        if receipt.previous_receipt_sha256 != ZERO_SHA256:
            raise ReceiptContractError("first progress receipt must start from zero predecessor")
        if receipt.previous_workspace_readback_sha256 != ZERO_SHA256:
            raise ReceiptContractError("first progress receipt must start from zero workspace predecessor")
    else:
        if receipt.previous_receipt_sha256 == ZERO_SHA256:
            raise ReceiptContractError("non-initial progress receipt requires a predecessor")
        if receipt.previous_workspace_readback_sha256 == ZERO_SHA256:
            raise ReceiptContractError("non-initial progress receipt requires a workspace predecessor")
    return receipt


def validate_causal_progress_chain(
    receipts: Sequence[Mapping[str, Any] | CausalProgressReceiptV1],
) -> tuple[CausalProgressReceiptV1, ...]:
    parsed: list[CausalProgressReceiptV1] = []
    seen_workspace_states: set[str] = set()
    previous_receipt_sha256 = ZERO_SHA256
    previous_workspace_sha256 = ZERO_SHA256
    binding: tuple[str, str, str, str, str] | None = None

    for expected_sequence, raw in enumerate(receipts):
        receipt = raw if isinstance(raw, CausalProgressReceiptV1) else CausalProgressReceiptV1.from_dict(raw)
        if receipt.sequence != expected_sequence:
            raise ReceiptContractError("causal progress sequence is not contiguous")
        if receipt.previous_receipt_sha256 != previous_receipt_sha256:
            raise ReceiptContractError("causal progress predecessor receipt mismatch")
        if receipt.previous_workspace_readback_sha256 != previous_workspace_sha256:
            raise ReceiptContractError("causal progress predecessor workspace mismatch")
        current_binding = (
            receipt.job_id,
            receipt.workspace_id,
            receipt.a2a_task_id,
            receipt.repository,
            receipt.repository_revision,
        )
        if binding is None:
            binding = current_binding
        elif current_binding != binding:
            raise ReceiptContractError("causal progress binding changed inside one chain")
        if receipt.current_workspace_readback_sha256 in seen_workspace_states:
            raise ReceiptContractError("causal progress chain repeated a previously attested workspace state")
        seen_workspace_states.add(receipt.current_workspace_readback_sha256)
        parsed.append(receipt)
        previous_receipt_sha256 = receipt.receipt_sha256
        previous_workspace_sha256 = receipt.current_workspace_readback_sha256
    return tuple(parsed)


def workspace_readback_is_new(
    current_workspace_readback_sha256: str,
    receipts: Sequence[CausalProgressReceiptV1],
) -> bool:
    current = _sha64(
        current_workspace_readback_sha256,
        field="currentWorkspaceReadbackSha256",
    )
    return all(receipt.current_workspace_readback_sha256 != current for receipt in receipts)


@dataclass(frozen=True, slots=True)
class CausalProgressLeaseDecision:
    verdict: str
    reason: str
    lease_expires_epoch_ms: int
    absolute_deadline_epoch_ms: int


def assess_causal_progress_lease(
    *,
    now_epoch_ms: int,
    started_epoch_ms: int,
    last_material_progress_epoch_ms: int,
    max_no_progress_seconds: int,
    absolute_deadline_seconds: int,
    material_progress_observed: bool,
) -> CausalProgressLeaseDecision:
    now = int(now_epoch_ms)
    started = int(started_epoch_ms)
    last_progress = int(last_material_progress_epoch_ms)
    no_progress_ms = int(max_no_progress_seconds) * 1000
    absolute_ms = int(absolute_deadline_seconds) * 1000

    if now < 0 or started < 0 or last_progress < 0:
        return CausalProgressLeaseDecision("CONTRADICTED", "negative epoch is invalid", 0, 0)
    if no_progress_ms <= 0 or absolute_ms <= 0:
        return CausalProgressLeaseDecision("CONTRADICTED", "lease bounds must be positive", 0, 0)
    if started > now or last_progress > now:
        return CausalProgressLeaseDecision("CONTRADICTED", "progress chronology is in the future", 0, 0)
    if last_progress < started:
        return CausalProgressLeaseDecision("CONTRADICTED", "progress predates job start", 0, 0)

    lease_expires = last_progress + no_progress_ms
    absolute_deadline = started + absolute_ms

    if now >= absolute_deadline:
        return CausalProgressLeaseDecision(
            "STALLED",
            "absolute repository execution deadline reached",
            lease_expires,
            absolute_deadline,
        )
    if now >= lease_expires:
        return CausalProgressLeaseDecision(
            "STALLED",
            "no new material repository progress within the bounded lease",
            lease_expires,
            absolute_deadline,
        )
    if material_progress_observed:
        return CausalProgressLeaseDecision(
            "CONTINUE_VERIFIED",
            "new authoritative workspace state observed",
            lease_expires,
            absolute_deadline,
        )
    return CausalProgressLeaseDecision(
        "NO_PROGRESS",
        "task remains within lease but no new material workspace state was observed",
        lease_expires,
        absolute_deadline,
    )
