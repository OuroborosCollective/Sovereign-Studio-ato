from __future__ import annotations

from pathlib import Path

import pytest

from policy import safe_repo_path, validate_branch, validate_container, validate_patch_blocks, validate_workspace_id


def test_workspace_and_branch_accept_only_operator_scope() -> None:
    assert validate_workspace_id("job-abcdef123456") == "job-abcdef123456"
    assert validate_branch("sovereign/chatgpt/fix-menu") == "sovereign/chatgpt/fix-menu"
    with pytest.raises(ValueError):
        validate_workspace_id("../../root")
    with pytest.raises(ValueError):
        validate_branch("main")
    with pytest.raises(ValueError):
        validate_branch("feature/unrestricted")


def test_container_aliases_resolve_only_to_allowlisted_canonical_names() -> None:
    allowed = ("sovereign-backend", "sovereign-chatgpt-mcp")

    assert validate_container("sovereign-mcp", allowed) == "sovereign-chatgpt-mcp"
    assert validate_container("mcp", allowed) == "sovereign-chatgpt-mcp"
    assert validate_container("sovereign-backend", allowed) == "sovereign-backend"
    with pytest.raises(ValueError):
        validate_container("unrelated-root-container", allowed)
    assert validate_container("apache-tika-2l6t-tika-1", allowed, allow_any=True) == "apache-tika-2l6t-tika-1"
    with pytest.raises(ValueError):
        validate_container("../../docker.sock", allowed, allow_any=True)


def test_repo_path_blocks_escape_and_secrets(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    assert safe_repo_path(repo, "src/menu.tsx") == (repo / "src/menu.tsx").resolve()
    for blocked in ("../outside", ".env", ".git/config", "credentials/token.txt", "key.pem"):
        with pytest.raises(ValueError):
            safe_repo_path(repo, blocked)


def test_patch_blocks_require_real_exact_search() -> None:
    validate_patch_blocks([{"search": "old", "replace": "new"}])
    with pytest.raises(ValueError):
        validate_patch_blocks([])
    with pytest.raises(ValueError):
        validate_patch_blocks([{"search": "", "replace": "new"}])
    with pytest.raises(ValueError):
        validate_patch_blocks([{"search": "x", "replace": "x" * 70000}])
