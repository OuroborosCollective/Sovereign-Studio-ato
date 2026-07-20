from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.workspace_editor import (  # noqa: E402
    WorkspaceEditorAccessError,
    build_workspace_editor_descriptor,
)


def _ready_repo(root: Path, workspace_id: str) -> None:
    (root / workspace_id / "repo" / ".git").mkdir(parents=True)


def test_backend_owns_workspace_editor_descriptor(tmp_path: Path, monkeypatch) -> None:
    workspace_id = "agent-editor-1"
    _ready_repo(tmp_path, workspace_id)
    monkeypatch.setenv("SOVEREIGN_OWNER_ADMIN_ID", "owner-1")
    monkeypatch.setenv("SOVEREIGN_CODE_SERVER_PUBLIC_URL", "https://code.arelorian.de")

    result = build_workspace_editor_descriptor(
        user_id="owner-1",
        workspace_id=workspace_id,
        workspace_root=tmp_path,
    )

    assert result["workspaceAuthority"] == "sovereign-backend"
    assert result["sessionAuthority"] == "sovereign-backend"
    assert result["billingAuthority"] == "sovereign-backend"
    assert result["llmRouteAuthority"] == "sovereign-backend"
    assert result["mcpWorkspaceAuthority"] is False
    assert result["editorAccessMode"] == "owner_single_tenant"
    assert result["multiTenantEditorReady"] is False
    assert result["editorFolder"] == f"/config/sovereign-agent-workspaces/{workspace_id}/repo"
    assert "folder=%2Fconfig%2Fsovereign-agent-workspaces%2F" in result["openUrl"]


def test_shared_editor_blocks_non_owner_and_unready_repo(tmp_path: Path, monkeypatch) -> None:
    workspace_id = "agent-editor-2"
    _ready_repo(tmp_path, workspace_id)
    monkeypatch.setenv("SOVEREIGN_OWNER_ADMIN_ID", "owner-1")
    monkeypatch.setenv("SOVEREIGN_CODE_SERVER_PUBLIC_URL", "https://code.arelorian.de")

    with pytest.raises(WorkspaceEditorAccessError, match="owner-only"):
        build_workspace_editor_descriptor(
            user_id="user-2",
            workspace_id=workspace_id,
            workspace_root=tmp_path,
        )

    with pytest.raises(WorkspaceEditorAccessError, match="not ready"):
        build_workspace_editor_descriptor(
            user_id="owner-1",
            workspace_id="agent-missing",
            workspace_root=tmp_path,
        )


def test_sdcard_contract_is_truthful_and_requires_marker(tmp_path: Path, monkeypatch) -> None:
    workspace_id = "agent-editor-3"
    _ready_repo(tmp_path, workspace_id)
    monkeypatch.setenv("SOVEREIGN_OWNER_ADMIN_ID", "owner-1")
    monkeypatch.setenv("SOVEREIGN_CODE_SERVER_PUBLIC_URL", "https://code.arelorian.de")
    marker = hashlib.sha256(b"android-storage-grant").hexdigest()

    result = build_workspace_editor_descriptor(
        user_id="owner-1",
        workspace_id=workspace_id,
        workspace_root=tmp_path,
        sdcard_enabled=True,
        sdcard_marker_sha256=marker,
    )
    assert result["storage"]["mode"] == "android_external_storage_mirror"
    assert result["storage"]["directRemoteMountClaimed"] is False
    assert result["storage"]["nativeBridgeRequired"] is True
    assert result["storage"]["syncMarkerSha256"] == marker

    with pytest.raises(WorkspaceEditorAccessError, match="SHA-256"):
        build_workspace_editor_descriptor(
            user_id="owner-1",
            workspace_id=workspace_id,
            workspace_root=tmp_path,
            sdcard_enabled=True,
        )
