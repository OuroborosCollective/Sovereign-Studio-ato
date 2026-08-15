"""Rebuildable, read-only, redacting read models for the operator projection.

Issue #1174 requires NocoDB to read only from a dedicated, rebuildable operator
projection and to never expose secrets, raw private logs, or an editable green
status field that could masquerade as runtime truth.

A ``ReadModelProjector`` consumes already-canonical runtime records and emits a
deterministic, redacted, rebuildable projection. It is deliberately side-effect
free: it performs no DB writes, no Docker/GitHub actions, and no network calls.
Output statuses are *projections* (``SUCCEEDED_UNVERIFIED`` / ``VERIFIED`` /
``CONTRADICTED`` / ``UNKNOWN`` / ``BLOCKED``), never authoritative verdicts.

The projection is rebuildable: ``project`` is a pure function of its inputs, so
the same canonical records always yield byte-identical projection rows (guarded
by ``test_operator_projection_read_only``).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from ..contracts import sanitize_agent_text

ProjectionStatus = str

# Projection-only status vocabulary. These are explicitly *not* runtime truth;
# they are bounded summaries derived from canonical records.
PROJECTION_STATUSES: frozenset[ProjectionStatus] = frozenset(
    {
        "SUCCEEDED_UNVERIFIED",
        "VERIFIED",
        "CONTRADICTED",
        "BLOCKED",
        "UNKNOWN",
        "OPERATOR_PROJECTION_UNAVAILABLE",
    }
)

# Fields that may carry secrets/PII and must never be projected verbatim. The
# projector drops any of these keys entirely rather than redacting in place,
# so a secret can never leak through a renamed or nested alias.
_FORBIDDEN_PROJECTION_FIELDS: frozenset[str] = frozenset(
    {
        "secret",
        "secrets",
        "api_key",
        "apikey",
        "api_keys",
        "token",
        "tokens",
        "access_token",
        "refresh_token",
        "private_key",
        "password",
        "passwd",
        "credential",
        "credentials",
        "authorization",
        "raw_logs",
        "env",
        "environment",
    }
)

# Top-level record kinds the projection supports. Each kind maps to a stable
# row "view" name without exposing canonical ownership.
SUPPORTED_RECORD_KINDS: frozenset[str] = frozenset(
    {
        "incident",
        "runtime_node",
        "risk_bundle",
        "scann_match",
        "wolfram_validation",
        "action_candidate",
        "approval_status",
        "runtime_readback",
    }
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def projection_row_hash(row: Mapping[str, Any]) -> str:
    """Deterministic identity hash for a single projection row.

    Excludes the hash itself and any volatile metadata so the row is rebuildable.
    """
    payload = {k: v for k, v in row.items() if k not in {"rowHash"}}
    return "sha256:" + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProjectionRow:
    view: str
    record_id: str
    status: ProjectionStatus
    summary: str
    source_receipt_hashes: tuple[str, ...]
    row_hash: str
    raw_forbidden_keys: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "view": self.view,
            "recordId": self.record_id,
            "status": self.status,
            "summary": self.summary,
            "sourceReceiptHashes": list(self.source_receipt_hashes),
            "rowHash": self.row_hash,
            "droppedForbiddenKeys": list(self.raw_forbidden_keys),
        }


def _is_secret_shaped(value: Any) -> bool:
    """Reuse the canonical secret scanner on any string within the record."""
    if not isinstance(value, str):
        return False
    masked = sanitize_agent_text(value, max_length=len(value) + 16)
    return "[redacted]" in masked


def _redact_summary(raw_summary: Any) -> str:
    """Cap and secret-mask a human summary before it leaves the projection."""
    return sanitize_agent_text(str(raw_summary or ""), 2000)


def _collect_forbidden(record: Mapping[str, Any]) -> tuple[str, ...]:
    found: list[str] = []
    for key in record:
        normalized = str(key).lower()
        if normalized in _FORBIDDEN_PROJECTION_FIELDS:
            found.append(str(key))
    return tuple(found)


def _normalize_status(raw_status: Any) -> ProjectionStatus:
    if raw_status is None:
        return "UNKNOWN"
    status = str(raw_status)
    if status in PROJECTION_STATUSES:
        return status
    # Never trust an unknown/canonical verdict string as a green projection.
    return "UNKNOWN"


def _receipt_hashes(raw: Any) -> tuple[str, ...]:
    values = raw if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)) else [raw]
    out: list[str] = []
    for value in values:
        if isinstance(value, str) and value:
            out.append(value)
    # Preserve order, drop duplicates.
    seen: set[str] = set()
    unique: list[str] = []
    for value in out:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return tuple(unique)


class ReadModelProjector:
    """Pure, rebuildable, read-only projector for the operator surface."""

    def project(self, records: Iterable[Mapping[str, Any]]) -> list[ProjectionRow]:
        rows: list[ProjectionRow] = []
        for index, record in enumerate(records):
            if not isinstance(record, Mapping):
                continue
            rows.append(self._project_record(record, index))
        return rows

    def _project_record(self, record: Mapping[str, Any], index: int) -> ProjectionRow:
        kind = str(record.get("kind") or record.get("view") or "").strip().lower()
        view = kind if kind in SUPPORTED_RECORD_KINDS else "unknown"
        record_id = str(record.get("id") or record.get("recordId") or f"row-{index}")
        status = _normalize_status(record.get("status"))
        summary = _redact_summary(record.get("summary") or record.get("title") or "")
        forbidden = _collect_forbidden(record)
        receipts = _receipt_hashes(record.get("sourceReceiptHashes") or record.get("receipts"))

        # Defense-in-depth: if any surviving summary still scans as secret-shaped,
        # degrade the projection rather than emit it.
        if _is_secret_shaped(summary):
            summary = "[redacted:secret-shaped summary]"
            status = "UNKNOWN"

        row = {
            "view": view,
            "recordId": record_id,
            "status": status,
            "summary": summary,
            "sourceReceiptHashes": list(receipts),
        }
        row_hash = projection_row_hash(row)
        return ProjectionRow(
            view=view,
            record_id=record_id,
            status=status,
            summary=summary,
            source_receipt_hashes=receipts,
            row_hash=row_hash,
            raw_forbidden_keys=forbidden,
        )

    def to_view_payload(self, records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        """Materialize a JSON-serializable view payload suitable for NocoDB views."""
        rows = self.project(records)
        return {
            "schemaVersion": "operator-projection-views.v1",
            "rows": [row.to_dict() for row in rows],
            "provenance": {
                "rebuildable": True,
                "readOnly": True,
                "containsSecrets": False,
                "authoritative": False,
            },
        }


__all__ = [
    "PROJECTION_STATUSES",
    "SUPPORTED_RECORD_KINDS",
    "ProjectionRow",
    "ReadModelProjector",
    "projection_row_hash",
]
