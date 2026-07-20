from __future__ import annotations

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


def test_check_is_allowlisted(repo_runtime) -> None:
    runtime, workspace_id, _ = repo_runtime
    result = runtime.run_check(workspace_id, "git_diff_check")
    assert result["ok"] is True
    with pytest.raises(ValueError, match="nicht freigegeben"):
        runtime.run_check(workspace_id, "shell", "rm -rf /")
