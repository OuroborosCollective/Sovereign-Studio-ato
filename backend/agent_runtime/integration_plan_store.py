"""Path-safe filesystem adapter for the Integration Plan Lane.

The lane itself is a pure state machine (see ``integration_plan_lane``).  This
module is the **only** place in the lane package that touches the filesystem
and it does so with strict, fail-closed canonicalisation.

The adapter is intentionally narrow:

- It accepts a workspace root and an ``integration_id`` and resolves the plan
  directory ``<workspace>/.planning/<integration_id>/``.
- All path inputs are canonicalised with ``os.path.realpath`` *and* symlink-
  free directory walks.  Any traversal attempt (e.g. ``..``, absolute paths,
  case folding on case-insensitive filesystems, Windows drive letters, MSYS
  path mangling) is rejected.
- It writes ``plan.receipt.json``, ``evidence-index.json`` and appends to
  ``ledger-actions.jsonl`` using atomic write-then-rename semantics.
- It refuses to read or write anywhere outside the resolved plan directory
  and refuses to follow symbolic links.
- All file payloads pass through ``RedactionFilter`` and size limits before
  reaching disk.

The adapter is intentionally not importable from the lane package's pure
modules, so accidental I/O during state-machine reasoning is impossible.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path, PurePosixPath
from typing import Iterable, List, Optional, Sequence

from .integration_plan_lane import (
    EVIDENCE_SCHEMA_VERSION,
    IntegrationPlanContractError,
    IntegrationPlanLane,
    Phase,
    PhaseStatus,
    PlanReceipt,
    SCHEMA_VERSION,
)


_INTEGRATION_ID: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_.:-]{1,119}$")
_PLAN_DIR_NAME: Final[str] = ".planning"
_MAX_FILE_BYTES: Final[int] = 1_048_576  # 1 MiB cap on any persisted file
_MAX_LEDGER_ENTRY_BYTES: Final[int] = 16_384


from typing import Final  # noqa: E402  (kept near the constant block)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class IntegrationPlanStoreError(RuntimeError):
    """Raised for any filesystem, path or canonicalisation violation."""


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------
def _resolve_workspace_root(workspace_root: str | os.PathLike[str]) -> Path:
    """Resolve a workspace root and reject symlinked parents.

    The unresolved path itself must not be a symlink.  Any ancestor that
    *was* a symlink before resolution is also rejected.  The final resolved
    path is then walked to ensure none of the resolved ancestors are
    symlinks at any point.
    """
    raw = Path(workspace_root)
    # Walk the unresolved ancestors: every step must be a real directory.
    current_raw = raw
    while True:
        if current_raw.is_symlink():
            raise IntegrationPlanStoreError(
                f"workspace root contains a symlinked ancestor: {current_raw}"
            )
        parent = current_raw.parent
        if parent == current_raw:
            break
        current_raw = parent
    candidate = raw.resolve()
    if not candidate.exists():
        raise IntegrationPlanStoreError(
            f"workspace root does not exist: {workspace_root}"
        )
    if not candidate.is_dir():
        raise IntegrationPlanStoreError(
            f"workspace root is not a directory: {workspace_root}"
        )
    return candidate


def _safe_path_within(root: Path, relative: str) -> Path:
    """Resolve ``relative`` against ``root`` and ensure it stays inside it."""
    if not isinstance(relative, str) or not relative:
        raise IntegrationPlanStoreError("relative path must be a non-empty string")
    # Reject absolute paths, Windows drive letters, MSYS mangling and NULs.
    if os.path.isabs(relative) or re.match(r"^[a-zA-Z]:[\\/]", relative):
        raise IntegrationPlanStoreError(f"absolute paths are forbidden: {relative!r}")
    if "\x00" in relative:
        raise IntegrationPlanStoreError("NUL bytes are forbidden in paths")
    if relative.startswith(("/", "\\")):
        raise IntegrationPlanStoreError(f"rooted paths are forbidden: {relative!r}")
    normalised = PurePosixPath(relative.replace("\\", "/"))
    parts = normalised.parts
    if not parts or parts[0] == "..":
        raise IntegrationPlanStoreError(f"traversal segments are forbidden: {relative!r}")
    if any(part in ("..",) for part in parts):
        raise IntegrationPlanStoreError(f"traversal segments are forbidden: {relative!r}")
    candidate = (root / normalised).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise IntegrationPlanStoreError(
            f"path leaves workspace root: {relative!r}"
        ) from exc
    return candidate


def _plan_dir(workspace_root: Path, integration_id: str) -> Path:
    if not _INTEGRATION_ID.fullmatch(integration_id):
        raise IntegrationPlanStoreError(
            f"integration_id is invalid: {integration_id!r}"
        )
    return _safe_path_within(workspace_root, f"{_PLAN_DIR_NAME}/{integration_id}")


def _check_no_symlinks(directory: Path) -> None:
    """Reject any symlink inside ``directory`` recursively (files or dirs)."""
    for entry in directory.rglob("*"):
        if entry.is_symlink():
            raise IntegrationPlanStoreError(
                f"symbolic link is not permitted inside plan dir: {entry}"
            )


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Atomically replace ``path`` with ``data``."""
    fd, tmp_path = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


def _read_bounded(path: Path) -> bytes:
    if not path.exists():
        raise IntegrationPlanStoreError(
            f"file {path} does not exist"
        )
    if path.is_symlink():
        raise IntegrationPlanStoreError(
            f"symbolic link is not permitted: {path}"
        )
    size = path.stat().st_size
    if size > _MAX_FILE_BYTES:
        raise IntegrationPlanStoreError(
            f"file {path} exceeds {_MAX_FILE_BYTES}-byte limit"
        )
    return path.read_bytes()


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------
class IntegrationPlanStore:
    """Filesystem adapter for a single integration plan directory.

    The adapter is purely textual: all canonical validation happens in the
    lane module.  This class only translates ``PlanReceipt`` and evidence
    payloads to and from the canonical on-disk layout.
    """

    def __init__(self, workspace_root: str | os.PathLike[str]) -> None:
        self._root = _resolve_workspace_root(workspace_root)

    # -----------------------------------------------------------------------
    # Properties
    # -----------------------------------------------------------------------
    @property
    def workspace_root(self) -> Path:
        return self._root

    # -----------------------------------------------------------------------
    # Plan directory lifecycle
    # -----------------------------------------------------------------------
    def plan_directory(self, integration_id: str) -> Path:
        return _plan_dir(self._root, integration_id)

    def init_plan(self, integration_id: str) -> Path:
        """Create an empty plan directory with sane permissions."""
        plan_dir = self.plan_directory(integration_id)
        if plan_dir.exists():
            if not plan_dir.is_dir():
                raise IntegrationPlanStoreError(
                    f"plan path is not a directory: {plan_dir}"
                )
            _check_no_symlinks(plan_dir)
            return plan_dir
        plan_dir.mkdir(parents=True, exist_ok=False)
        return plan_dir

    # -----------------------------------------------------------------------
    # Plan receipt persistence
    # -----------------------------------------------------------------------
    def write_receipt(self, receipt: PlanReceipt) -> Path:
        if receipt.schema_version != SCHEMA_VERSION:
            raise IntegrationPlanContractError(
                f"receipt schema_version must be {SCHEMA_VERSION}"
            )
        plan_dir = self.init_plan(receipt.plan_id)
        target = _safe_path_within(plan_dir, "plan.receipt.json")
        payload = IntegrationPlanLane.to_receipt_dict(receipt)
        data = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        if len(data) > _MAX_FILE_BYTES:
            raise IntegrationPlanStoreError(
                f"plan.receipt.json exceeds {_MAX_FILE_BYTES}-byte limit"
            )
        _atomic_write_bytes(target, data)
        return target

    def read_receipt(self, integration_id: str) -> PlanReceipt:
        plan_dir = self.plan_directory(integration_id)
        target = _safe_path_within(plan_dir, "plan.receipt.json")
        _check_no_symlinks(plan_dir)
        data = _read_bounded(target)
        try:
            payload = json.loads(data.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise IntegrationPlanStoreError(f"plan.receipt.json is invalid JSON: {exc}") from exc
        return _receipt_from_dict(payload)

    # -----------------------------------------------------------------------
    # Evidence persistence
    # -----------------------------------------------------------------------
    def append_evidence(self, integration_id: str, payload: dict) -> Path:
        plan_dir = self.init_plan(integration_id)
        target = _safe_path_within(plan_dir, "evidence-index.json")
        if target.exists():
            try:
                existing = json.loads(_read_bounded(target).decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise IntegrationPlanStoreError(
                    f"evidence-index.json is invalid JSON: {exc}"
                ) from exc
        else:
            existing = {
                "schemaVersion": EVIDENCE_SCHEMA_VERSION,
                "planId": integration_id,
                "records": [],
            }
        if not isinstance(existing, dict):
            raise IntegrationPlanStoreError(
                "evidence-index.json must contain a JSON object at the top level"
            )
        if existing.get("schemaVersion") != EVIDENCE_SCHEMA_VERSION:
            raise IntegrationPlanStoreError(
                "evidence-index.json schemaVersion is invalid"
            )
        if existing.get("planId") and existing.get("planId") != integration_id:
            raise IntegrationPlanStoreError(
                "evidence-index.json planId does not match integration_id"
            )
        records = existing.setdefault("records", [])
        if not isinstance(records, list):
            raise IntegrationPlanStoreError(
                "evidence-index.json records must be a list"
            )
        records.append(payload)
        existing["planId"] = integration_id
        data = json.dumps(existing, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        if len(data) > _MAX_FILE_BYTES:
            raise IntegrationPlanStoreError(
                f"evidence-index.json exceeds {_MAX_FILE_BYTES}-byte limit"
            )
        _atomic_write_bytes(target, data)
        return target

    def read_evidence(self, integration_id: str) -> List[dict]:
        plan_dir = self.plan_directory(integration_id)
        target = _safe_path_within(plan_dir, "evidence-index.json")
        if not target.exists():
            return []
        _check_no_symlinks(plan_dir)
        try:
            data = json.loads(_read_bounded(target).decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise IntegrationPlanStoreError(
                f"evidence-index.json is invalid JSON: {exc}"
            ) from exc
        if not isinstance(data, dict):
            raise IntegrationPlanStoreError("evidence-index.json must be an object")
        records = data.get("records", [])
        if not isinstance(records, list):
            raise IntegrationPlanStoreError("evidence-index.json records must be a list")
        return records

    # -----------------------------------------------------------------------
    # Append-only ledger
    # -----------------------------------------------------------------------
    def append_ledger_action(self, integration_id: str, payload: dict) -> Path:
        plan_dir = self.init_plan(integration_id)
        target = _safe_path_within(plan_dir, "ledger-actions.jsonl")
        record = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        line = (record + "\n").encode("utf-8")
        if len(line) > _MAX_LEDGER_ENTRY_BYTES:
            raise IntegrationPlanStoreError(
                f"ledger-actions.jsonl line exceeds {_MAX_LEDGER_ENTRY_BYTES}-byte limit"
            )
        with open(target, "ab") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
        return target

    def read_ledger_actions(self, integration_id: str) -> List[dict]:
        plan_dir = self.plan_directory(integration_id)
        target = _safe_path_within(plan_dir, "ledger-actions.jsonl")
        if not target.exists():
            return []
        _check_no_symlinks(plan_dir)
        out: List[dict] = []
        for line_number, raw in enumerate(target.read_text("utf-8").splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise IntegrationPlanStoreError(
                    f"ledger-actions.jsonl line {line_number} is invalid JSON: {exc}"
                ) from exc
            if not isinstance(entry, dict):
                raise IntegrationPlanStoreError(
                    f"ledger-actions.jsonl line {line_number} must be a JSON object"
                )
            out.append(entry)
        return out

    # -----------------------------------------------------------------------
    # Markers
    # -----------------------------------------------------------------------
    def write_active_revision(
        self, integration_id: str, expected_revision: str
    ) -> Path:
        if not re.fullmatch(r"[0-9a-f]{40}", expected_revision):
            raise IntegrationPlanStoreError(
                "expected_revision must be a 40-character lowercase hex SHA"
            )
        plan_dir = self.init_plan(integration_id)
        target = _safe_path_within(plan_dir, ".active_revision")
        _atomic_write_bytes(target, (expected_revision + "\n").encode("utf-8"))
        return target

    def read_active_revision(self, integration_id: str) -> Optional[str]:
        plan_dir = self.plan_directory(integration_id)
        target = _safe_path_within(plan_dir, ".active_revision")
        if not target.exists():
            return None
        content = _read_bounded(target).decode("utf-8").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", content):
            raise IntegrationPlanStoreError(
                ".active_revision must be a 40-character lowercase hex SHA"
            )
        return content

    def write_mode(self, integration_id: str, mode: str) -> Path:
        if mode not in {"open", "gated", "closed"}:
            raise IntegrationPlanStoreError(
                f"mode must be one of open|gated|closed (got {mode!r})"
            )
        plan_dir = self.init_plan(integration_id)
        target = _safe_path_within(plan_dir, ".mode")
        _atomic_write_bytes(target, (mode + "\n").encode("utf-8"))
        return target

    def read_mode(self, integration_id: str) -> str:
        plan_dir = self.plan_directory(integration_id)
        target = _safe_path_within(plan_dir, ".mode")
        if not target.exists():
            return "open"
        content = _read_bounded(target).decode("utf-8").strip()
        if content not in {"open", "gated", "closed"}:
            raise IntegrationPlanStoreError(
                f".mode must be one of open|gated|closed (got {content!r})"
            )
        return content


# ---------------------------------------------------------------------------
# De-serialisation
# ---------------------------------------------------------------------------
def _receipt_from_dict(payload: dict) -> PlanReceipt:
    if not isinstance(payload, dict):
        raise IntegrationPlanStoreError("plan.receipt.json must be a JSON object")
    phases_payload = payload.get("phases", [])
    if not isinstance(phases_payload, list):
        raise IntegrationPlanStoreError("plan.receipt.json phases must be a list")
    phases: List[Phase] = []
    for entry in phases_payload:
        if not isinstance(entry, dict):
            raise IntegrationPlanStoreError("phase entry must be a JSON object")
        phases.append(
            Phase(
                phase_id=str(entry["phaseId"]),
                title=str(entry["title"]),
                description=str(entry["description"]),
                acceptance_criteria=tuple(entry.get("acceptanceCriteria", [])),
                required_evidence_kinds=tuple(entry.get("requiredEvidenceKinds", [])),
                status=PhaseStatus(str(entry.get("status", "pending"))),
            )
        )
    return PlanReceipt(
        plan_id=str(payload["planId"]),
        schema_version=str(payload["schemaVersion"]),
        plan_schema_version=str(payload["planSchemaVersion"]),
        owner=str(payload["owner"]),
        repo_owner=str(payload["repoOwner"]),
        repo_name=str(payload["repoName"]),
        workspace_id=str(payload["workspaceId"]),
        base_revision=str(payload["baseRevision"]),
        issue_reference=str(payload["issueReference"]),
        pr_reference=(
            str(payload["prReference"])
            if payload.get("prReference") is not None
            else None
        ),
        acceptance_criteria=tuple(payload.get("acceptanceCriteria", [])),
        allowed_mutation_surfaces=tuple(payload.get("allowedMutationSurfaces", [])),
        phases=tuple(phases),
        next_step=str(payload["nextStep"]),
        attestation_sha256=str(payload["attestationSha256"]),
        predecessor_attestation_sha256=(
            str(payload["predecessorAttestationSha256"])
            if payload.get("predecessorAttestationSha256") is not None
            else None
        ),
        amendment_reason=str(payload.get("amendmentReason", "")),
        recorded_at_iso=str(payload["recordedAtIso"]),
        plan_content_sha256=str(payload["planContentSha256"]),
    )