from __future__ import annotations

import hashlib

import pytest


def test_read_patch_new_file_and_diff(repo_runtime) -> None:
    runtime, workspace_id, _ = repo_runtime
    before = runtime.read_file(workspace_id, "src/menu.tsx")
    assert before["content"] == "export const label = 'Old';\n"

    patched = runtime.apply_search_replace(
        workspace_id,
        "src/menu.tsx",
        [{"search": "'Old'", "replace": "'New menu'"}],
        expected_sha256=before["sha256"],
    )
    assert patched["before_sha256"] == before["sha256"]
    assert runtime.read_file(workspace_id, "src/menu.tsx")["content"] == "export const label = 'New menu';\n"

    created = runtime.write_new_file(workspace_id, "src/NewMenu.tsx", "export function NewMenu() { return null; }\n")
    assert created["bytes"] > 0
    diff = runtime.git_diff(workspace_id)
    assert diff["ok"] is True
    assert "src/menu.tsx" in diff["status"]
    assert "src/NewMenu.tsx" in diff["status"]


def test_patch_fails_closed_on_stale_hash_or_ambiguous_match(repo_runtime) -> None:
    runtime, workspace_id, repo = repo_runtime
    with pytest.raises(ValueError, match="verändert"):
        runtime.apply_search_replace(
            workspace_id,
            "src/menu.tsx",
            [{"search": "Old", "replace": "New"}],
            expected_sha256="0" * 64,
        )

    (repo / "src" / "menu.tsx").write_text("Old Old\n", "utf-8")
    with pytest.raises(ValueError, match="exakt einmal"):
        runtime.apply_search_replace(
            workspace_id,
            "src/menu.tsx",
            [{"search": "Old", "replace": "New"}],
        )


def test_search_reads_real_workspace_files(repo_runtime) -> None:
    runtime, workspace_id, _ = repo_runtime
    result = runtime.search_text(workspace_id, "runtime truth")
    assert result["results"] == [
        {"path": "README.md", "line": 1, "text": "Sovereign runtime truth"}
    ]


def test_code_server_workspace_descriptor_is_bounded_and_sdcard_truthful(repo_runtime, monkeypatch) -> None:
    runtime, workspace_id, repo = repo_runtime
    monkeypatch.setenv("SOVEREIGN_CODE_SERVER_PUBLIC_URL", "https://code.arelorian.de")

    result = runtime.code_server_workspace_descriptor(workspace_id)
    assert result["ok"] is True
    assert result["hostRepoPath"] == str(repo)
    assert result["editorFolder"] == f"/config/sovereign-workspaces/{workspace_id}/repo"
    assert "folder=%2Fconfig%2Fsovereign-workspaces%2F" in result["openUrl"]
    assert result["storage"]["directRemoteMountClaimed"] is False
    assert result["credentialsReturned"] is False

    marker = hashlib.sha256(b"android-sdcard-grant").hexdigest()
    mirrored = runtime.code_server_workspace_descriptor(
        workspace_id,
        sdcard_enabled=True,
        sdcard_marker_sha256=marker,
    )
    assert mirrored["storage"]["mode"] == "android_external_storage_mirror"
    assert mirrored["storage"]["nativeBridgeRequired"] is True
    assert mirrored["storage"]["syncMarkerSha256"] == marker

    with pytest.raises(ValueError, match="SHA-256-Marker"):
        runtime.code_server_workspace_descriptor(workspace_id, sdcard_enabled=True)


def test_code_server_workspace_descriptor_rejects_unsafe_public_url(repo_runtime, monkeypatch) -> None:
    runtime, workspace_id, _ = repo_runtime
    monkeypatch.setenv("SOVEREIGN_CODE_SERVER_PUBLIC_URL", "http://code.arelorian.de")
    with pytest.raises(ValueError, match="HTTPS"):
        runtime.code_server_workspace_descriptor(workspace_id)


def test_check_is_allowlisted(repo_runtime) -> None:
    runtime, workspace_id, _ = repo_runtime
    result = runtime.run_check(workspace_id, "git_diff_check")
    assert result["ok"] is True
    with pytest.raises(ValueError, match="nicht freigegeben"):
        runtime.run_check(workspace_id, "shell", "rm -rf /")
