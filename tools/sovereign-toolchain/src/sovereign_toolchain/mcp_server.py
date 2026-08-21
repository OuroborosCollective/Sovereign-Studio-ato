from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .core import (
    TOOL_DEFINITIONS,
    apply_backend_guardrails_patch_pr,
    apply_patch_worker,
    archive_reader,
    briefing,
    dispatch_tool,
    github_apply_search_replace_pr,
    github_read_file,
    make_patch_payload,
    plan_sandbox_commands,
    preview_search_replace,
)

mcp = FastMCP("Sovereign Universal Toolchain", stateless_http=True, json_response=True)

@mcp.tool()
def toolchain_manifest() -> dict[str, Any]:
    """Read-only: Return tool definitions for agents, no-code workspaces and routers."""
    return {"name": "Sovereign Universal Toolchain", "tools": TOOL_DEFINITIONS}

@mcp.tool()
def toolchain_briefing(include_rules: bool = True) -> dict[str, Any]:
    """Read-only: Return reusable project + sandbox briefing for agents."""
    return briefing(include_rules)

@mcp.tool()
def list_archive_files(source: str = "studio", prefix: str = "", glob: str = "*", limit: int = 100) -> dict[str, Any]:
    """Read-only: List text-like files inside the mounted Studio/Sandbox archives."""
    return archive_reader.list_files(source, prefix, glob, limit)

@mcp.tool()
def read_archive_text(source: str, path: str, max_chars: int = 20000) -> dict[str, Any]:
    """Read-only: Read a text file from a mounted source archive."""
    return archive_reader.read_text(source, path, max_chars)

@mcp.tool()
def plan_sandbox_commands_tool(goal: str = "verify") -> dict[str, Any]:
    """Read-only: Plan safe sandbox commands; does not execute shell commands."""
    return plan_sandbox_commands(goal)

@mcp.tool()
def preview_search_replace_tool(path: str, content: str, blocks: list[dict[str, str]]) -> dict[str, Any]:
    """Read-only: Preview strict SEARCH/REPLACE blocks and return a unified diff."""
    return preview_search_replace(path, content, blocks)

@mcp.tool()
def make_patch_payload_tool(owner: str, repo: str, path: str, message: str, blocks: list[dict[str, str]], expected_sha: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Read-only: Build a Sovereign Patch Worker payload without sending it."""
    return make_patch_payload(owner, repo, path, message, blocks, expected_sha, dry_run)

@mcp.tool()
def github_read_file_tool(owner: str, repo: str, path: str, ref: str | None = None, max_chars: int = 60000) -> dict[str, Any]:
    """Read-only: Read one GitHub file through the Contents API."""
    return github_read_file(owner, repo, path, ref, max_chars)

@mcp.tool()
def github_apply_search_replace_pr_tool(owner: str, repo: str, path: str, message: str, blocks: list[dict[str, str]], branch_name: str | None = None, title: str | None = None, body: str | None = None, base_branch: str | None = None, expected_sha: str | None = None, confirm: bool = False) -> dict[str, Any]:
    """Write action: Apply strict blocks and create a Draft PR using full-file replacement only."""
    return github_apply_search_replace_pr(owner, repo, path, message, blocks, branch_name, title, body, base_branch, expected_sha, confirm)

@mcp.tool()
def apply_patch_worker_tool(owner: str, repo: str, path: str, message: str, blocks: list[dict[str, str]], expected_sha: str | None = None, confirm: bool = False) -> dict[str, Any]:
    """Write action: Send /git/patch payload to the configured Patch Worker after confirm=True."""
    return apply_patch_worker(owner, repo, path, message, blocks, expected_sha, confirm)

@mcp.tool()
def apply_backend_guardrails_patch_pr_tool(
    owner: str = "OuroborosCollective",
    repo: str = "Sovereign-Studio-ato",
    base_branch: str = "main",
    patch_branch: str = "sovereign/apply-toolchain-guardrails",
    target_path: str = "scripts/sovereign-backend/app.py",
    message: str = "fix(toolchain): apply backend patch guardrails",
    title: str = "fix(toolchain): apply backend patch guardrails",
    body: str = "Applies the verified Toolchain backend guardrails patch from scripts/patches/apply_toolchain_patch_guardrails.py.",
    expected_sha: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Write action: Apply the embedded backend guardrail patch and open a Draft PR."""
    return apply_backend_guardrails_patch_pr(owner, repo, base_branch, patch_branch, target_path, message, title, body, expected_sha, confirm)

@mcp.tool()
def dispatch_tool_by_name(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Router: Invoke any tool by name. Useful for generic LLM routers and no-code adapters."""
    return dispatch_tool(name, args)

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
