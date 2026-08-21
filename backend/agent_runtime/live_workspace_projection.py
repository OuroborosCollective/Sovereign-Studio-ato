"""Receipt-bound IDE and terminal projection requests.

This module deliberately follows canonical tool execution.  It never invokes a
repository tool, starts a process, opens a shell, changes a worktree, or assigns a
success verdict.  It derives a bounded projection request from an already produced
ToolResult and from a fresh workspace readback.  A UI or desktop adapter may display
that request, but must not upgrade its evidence class.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

from .contracts import sanitize_agent_text
from .tools.base import ToolResult
from .workspace_policy import (
    WorkspacePolicyError,
    repo_dir_for_workspace,
    validate_workspace_relative_path,
)

PROJECTION_SCHEMA_VERSION = "sovereign.live-workspace-projection.v1"
PROJECTION_STATES = frozenset({"REQUESTED", "VISIBLE", "UNAVAILABLE", "STALE"})
PROJECTION_KINDS = frozenset({"IDE_FILE", "IDE_DIFF", "TERMINAL", "WINDOW_FOCUS"})
SOURCE_KINDS = frozenset({"REPOSITORY", "GIT", "PROCESS"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHA40 = re.compile(r"^[0-9a-f]{40}$")


class ProjectionContractError(ValueError):
    """Raised when a projection cannot be bound to a canonical action/readback."""


def _canonical_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return sha256(encoded).hexdigest()


def _hash_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _head(repo: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            text=True,
            capture_output=True,
            timeout=10,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProjectionContractError("workspace Git head is unreadable") from exc
    head = completed.stdout.strip().lower()
    if not _SHA40.fullmatch(head):
        raise ProjectionContractError("workspace Git head is invalid")
    return head


def _repo_for_job(job: Any, workspace_root: Path | None) -> Path:
    workspace_id = str(getattr(job, "workspace_id", "") or "").strip()
    if not workspace_id:
        raise ProjectionContractError("job workspace identity is unavailable")
    try:
        repo = repo_dir_for_workspace(workspace_id, workspace_root).resolve()
    except WorkspacePolicyError as exc:
        raise ProjectionContractError("job workspace identity is invalid") from exc
    if not repo.is_dir() or not (repo / ".git").is_dir():
        raise ProjectionContractError("job workspace repository is unavailable")
    return repo


def _safe_file_readback(repo: Path, raw_path: object) -> tuple[str, str]:
    relative = validate_workspace_relative_path(str(raw_path or ""))
    target = (repo / relative).resolve()
    if repo not in target.parents or not target.is_file():
        raise ProjectionContractError("projection file path is unavailable in bound worktree")
    return relative, sha256(target.read_bytes()).hexdigest()


def _receipt_ref(result: ToolResult) -> str:
    metadata = result.metadata if isinstance(result.metadata, Mapping) else {}
    value = str(metadata.get("providerNeutralEvidenceSha256") or "").strip().lower()
    if _SHA256.fullmatch(value):
        return value
    payload = {
        "tool": str(result.tool or ""),
        "status": str(result.status or ""),
        "exitCode": result.exit_code,
        "changedFiles": list(result.changed_files or ()),
        "diffSummary": str(result.diff_summary or ""),
        "testSummary": str(result.test_summary or ""),
    }
    return _canonical_hash(payload)


def _action_id(result: ToolResult) -> str:
    metadata = result.metadata if isinstance(result.metadata, Mapping) else {}
    action_id = str(metadata.get("actionId") or metadata.get("callId") or "").strip()
    if not action_id or len(action_id) > 160:
        raise ProjectionContractError("canonical action identity is unavailable")
    return action_id


@dataclass(frozen=True)
class ProjectionRequestV1:
    projection_id: str
    job_id: str
    workspace_id: str
    action_id: str
    source_kind: str
    projection_kind: str
    projection_state: str
    repository_head: str | None
    source_receipt_ref: str
    source_identity_hash: str
    payload: Mapping[str, Any]
    projection_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": PROJECTION_SCHEMA_VERSION,
            "projectionId": self.projection_id,
            "jobId": self.job_id,
            "workspaceId": self.workspace_id,
            "actionId": self.action_id,
            "sourceKind": self.source_kind,
            "projectionKind": self.projection_kind,
            "projectionState": self.projection_state,
            "repositoryHead": self.repository_head,
            "sourceReceiptRef": self.source_receipt_ref,
            "sourceIdentityHash": self.source_identity_hash,
            "payload": dict(self.payload),
            "projectionHash": self.projection_hash,
            "authoritative": False,
            "claim": "OBSERVED",
        }


def _build(
    *,
    job: Any,
    result: ToolResult,
    source_kind: str,
    projection_kind: str,
    projection_state: str,
    repository_head: str | None,
    payload: Mapping[str, Any],
) -> ProjectionRequestV1:
    if source_kind not in SOURCE_KINDS or projection_kind not in PROJECTION_KINDS:
        raise ProjectionContractError("projection source or kind is unsupported")
    if projection_state not in PROJECTION_STATES:
        raise ProjectionContractError("projection state is unsupported")
    job_id = str(getattr(job, "job_id", "") or "").strip()
    workspace_id = str(getattr(job, "workspace_id", "") or "").strip()
    if not job_id or not workspace_id:
        raise ProjectionContractError("job identity is unavailable")
    source_receipt_ref = _receipt_ref(result)
    action_id = _action_id(result)
    source_identity_hash = _canonical_hash({
        "jobId": job_id,
        "workspaceId": workspace_id,
        "actionId": action_id,
        "sourceReceiptRef": source_receipt_ref,
        "repositoryHead": repository_head,
    })
    unsigned = {
        "schemaVersion": PROJECTION_SCHEMA_VERSION,
        "jobId": job_id,
        "workspaceId": workspace_id,
        "actionId": action_id,
        "sourceKind": source_kind,
        "projectionKind": projection_kind,
        "projectionState": projection_state,
        "repositoryHead": repository_head,
        "sourceReceiptRef": source_receipt_ref,
        "sourceIdentityHash": source_identity_hash,
        "payload": dict(payload),
    }
    projection_hash = _canonical_hash(unsigned)
    return ProjectionRequestV1(
        projection_id=f"projection-{projection_hash[:24]}",
        job_id=job_id,
        workspace_id=workspace_id,
        action_id=action_id,
        source_kind=source_kind,
        projection_kind=projection_kind,
        projection_state=projection_state,
        repository_head=repository_head,
        source_receipt_ref=source_receipt_ref,
        source_identity_hash=source_identity_hash,
        payload=dict(payload),
        projection_hash=projection_hash,
    )


def projection_for_tool_result(
    *,
    job: Any,
    route_action: str,
    parameters: Mapping[str, Any],
    result: ToolResult,
    workspace_root: Path | None,
) -> ProjectionRequestV1:
    """Build one request after canonical execution and fresh bound readback.

    A failed or blocked tool is still represented honestly as unavailable; callers
    persist it only as an observation event.  No projection can change ``result``.
    """
    action = str(route_action or "").strip()
    if result.status != "done":
        return _build(
            job=job,
            result=result,
            source_kind="PROCESS" if action == "test" else "REPOSITORY",
            projection_kind="TERMINAL" if action == "test" else "WINDOW_FOCUS",
            projection_state="UNAVAILABLE",
            repository_head=None,
            payload={"reason": "canonical_action_not_completed"},
        )

    repo = _repo_for_job(job, workspace_root)
    head = _head(repo)
    if action == "file":
        raw_path = parameters.get("path") or parameters.get("relativePath")
        path, content_sha = _safe_file_readback(repo, raw_path)
        mode = str(parameters.get("mode") or parameters.get("action") or ("write" if "content" in parameters else "read")).lower()
        return _build(
            job=job,
            result=result,
            source_kind="REPOSITORY",
            projection_kind="IDE_FILE",
            projection_state="REQUESTED",
            repository_head=head,
            payload={"path": path, "contentSha256": content_sha, "mode": "write" if mode == "write" else "read"},
        )
    if action == "diff":
        diff_text = str(result.output or result.stdout or "")
        return _build(
            job=job,
            result=result,
            source_kind="GIT",
            projection_kind="IDE_DIFF",
            projection_state="REQUESTED",
            repository_head=head,
            payload={"diffSha256": _hash_text(diff_text), "changedFiles": list(result.changed_files or ())[:64]},
        )
    if action == "test":
        output = sanitize_agent_text(str(result.output or result.stdout or ""), 16_000)
        return _build(
            job=job,
            result=result,
            source_kind="PROCESS",
            projection_kind="TERMINAL",
            projection_state="REQUESTED",
            repository_head=head,
            payload={
                "streamSequence": 1,
                "channel": "STDOUT",
                "chunk": output,
                "chunkSha256": _hash_text(output),
                "exitCode": result.exit_code,
                "processState": "EXITED",
            },
        )
    return _build(
        job=job,
        result=result,
        source_kind="REPOSITORY",
        projection_kind="WINDOW_FOCUS",
        projection_state="UNAVAILABLE",
        repository_head=head,
        payload={"reason": "projection_not_supported_for_action"},
    )


def public_projection_event(request: ProjectionRequestV1) -> dict[str, Any]:
    """Return the redacted persistence/read-model payload for a projection request."""
    return request.to_dict()


__all__ = [
    "PROJECTION_SCHEMA_VERSION",
    "ProjectionContractError",
    "ProjectionRequestV1",
    "projection_for_tool_result",
    "public_projection_event",
]
