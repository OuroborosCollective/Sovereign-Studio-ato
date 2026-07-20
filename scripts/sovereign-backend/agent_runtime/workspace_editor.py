"""Backend-owned Code Server launch descriptors for Sovereign workspaces.

The backend owns session, billing, LLM routing and workspace identity. This
module never accepts an arbitrary filesystem path and never lets the MCP open a
user workspace. The current shared Code Server is deliberately owner-only until
a per-workspace isolated editor runtime exists.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import re
from typing import Any
from urllib.parse import urlencode, urlparse

from .workspace_policy import repo_dir_for_workspace, validate_workspace_relative_path

_DEFAULT_EDITOR_MOUNT_ROOT = "/config/sovereign-agent-workspaces"


class WorkspaceEditorAccessError(ValueError):
    """Raised when a workspace editor launch violates the backend contract."""


def _public_code_server_url() -> str:
    candidate = os.getenv("SOVEREIGN_CODE_SERVER_PUBLIC_URL", "").strip().rstrip("/")
    if not candidate:
        raise WorkspaceEditorAccessError("code server public URL is not configured")
    parsed = urlparse(candidate)
    if parsed.scheme != "https" or not parsed.hostname:
        raise WorkspaceEditorAccessError("code server public URL must use HTTPS")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise WorkspaceEditorAccessError("code server public URL contains forbidden components")
    return candidate


def _editor_mount_root() -> str:
    raw = os.getenv("SOVEREIGN_CODE_SERVER_WORKSPACE_MOUNT", _DEFAULT_EDITOR_MOUNT_ROOT).strip()
    path = PurePosixPath(raw)
    if not path.is_absolute() or ".." in path.parts or str(path) == "/":
        raise WorkspaceEditorAccessError("code server workspace mount is invalid")
    return str(path)


def build_workspace_editor_descriptor(
    *,
    user_id: str,
    workspace_id: str,
    workspace_root: Path | None,
    sdcard_enabled: bool = False,
    sdcard_marker_sha256: str = "",
) -> dict[str, Any]:
    owner_id = os.getenv("SOVEREIGN_OWNER_ADMIN_ID", "").strip()
    if not owner_id or user_id != owner_id:
        raise WorkspaceEditorAccessError(
            "shared code server is owner-only until per-workspace editor isolation is deployed"
        )

    validate_workspace_relative_path(f"{workspace_id}/repo")
    repo = repo_dir_for_workspace(workspace_id, workspace_root)
    if not repo.is_dir() or not (repo / ".git").is_dir():
        raise WorkspaceEditorAccessError("workspace repository is not ready")

    marker = sdcard_marker_sha256.strip().lower()
    if sdcard_enabled and not re.fullmatch(r"[0-9a-f]{64}", marker):
        raise WorkspaceEditorAccessError(
            "enabled Android external-storage mirror requires a confirmed SHA-256 marker"
        )

    editor_folder = f"{_editor_mount_root()}/{workspace_id}/repo"
    public_url = _public_code_server_url()
    return {
        "ok": True,
        "status": "BACKEND_WORKSPACE_EDITOR_READY",
        "workspaceId": workspace_id,
        "workspaceAuthority": "sovereign-backend",
        "sessionAuthority": "sovereign-backend",
        "billingAuthority": "sovereign-backend",
        "llmRouteAuthority": "sovereign-backend",
        "mcpWorkspaceAuthority": False,
        "editorAccessMode": "owner_single_tenant",
        "multiTenantEditorReady": False,
        "editorFolder": editor_folder,
        "openUrl": f"{public_url}/?{urlencode({'folder': editor_folder})}",
        "storage": {
            "mode": "android_external_storage_mirror" if sdcard_enabled else "backend_workspace",
            "sdcardEnabled": bool(sdcard_enabled),
            "directRemoteMountClaimed": False,
            "nativeBridgeRequired": bool(sdcard_enabled),
            "syncMarkerSha256": marker if sdcard_enabled else None,
        },
        "credentialsReturned": False,
        "arbitraryHostPathAccepted": False,
    }
