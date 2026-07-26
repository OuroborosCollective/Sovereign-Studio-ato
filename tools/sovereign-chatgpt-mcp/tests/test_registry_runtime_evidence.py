from __future__ import annotations

import hashlib
import inspect
import json

from github_admin import GitHubAdminRuntime
import server


def test_live_registry_evidence_matches_active_fastmcp_names() -> None:
    names = sorted(
        str(getattr(tool, "name", ""))
        for tool in server.mcp._tool_manager.list_tools()
        if str(getattr(tool, "name", ""))
    )
    expected_hash = hashlib.sha256(
        json.dumps(names, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    evidence = server._live_mcp_registry_evidence()

    assert evidence == {
        "registry_tool_count": len(names),
        "registry_tool_names_sha256": expected_hash,
        "registry_runtime_verified": True,
    }
    assert "registry_tool_names" not in evidence


def test_direct_mcp_self_update_is_fail_closed_by_default() -> None:
    admin_default = inspect.signature(GitHubAdminRuntime.merge_pr).parameters[
        "self_update_after_merge"
    ].default
    tool_default = inspect.signature(server.repository_merge_pr).parameters[
        "self_update_after_merge"
    ].default

    assert admin_default is False
    assert tool_default is False
