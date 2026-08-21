#!/usr/bin/env python3
"""Sovereign GitHub Patch MCP Server"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import os
from pathlib import Path
import secrets
import sys
from typing import Any, AsyncIterator, Literal

import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

os.environ["MCP_ALLOWED_HOSTS"] = "*"

GITHUB_API = os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/")
USER_AGENT = os.getenv("USER_AGENT", "sovereign-github-patch-mcp/1.0")
SOVEREIGN_PATCH_URL = os.getenv(
    "SOVEREIGN_PATCH_URL",
    "https://sovereign-studio-worker.projectouroboroscollective.workers.dev/git/patch",
)
SOVEREIGN_PATCH_BEARER = os.getenv("SOVEREIGN_PATCH_BEARER", "").strip()
_SHARED_AUTH_DIR = Path(__file__).resolve().parents[1] / "sovereign-legacy-mcp-common"
if not _SHARED_AUTH_DIR.is_dir():
    raise RuntimeError("canonical legacy MCP GitHub App adapter is unavailable")
sys.path.insert(0, str(_SHARED_AUTH_DIR))
from github_app_auth import GitHubAppInstallationAuth, GitHubAppInstallationConfig


class McpToolError(RuntimeError): pass

class PatchBlock(BaseModel):
    search: str = Field(..., description="Exact text that must exist in the target file.")
    replace: str = Field(..., description="Replacement text.")

class RepositoryResult(BaseModel):
    owner: str; repo: str; default_branch: str; private: bool; html_url: str; description: str | None = None

class BranchResult(BaseModel):
    name: str; sha: str; protected: bool = False

class DirectoryEntry(BaseModel):
    name: str; path: str; type: Literal["file", "dir", "symlink", "submodule", "unknown"]
    size: int | None = None; sha: str | None = None; html_url: str | None = None

class FileContentResult(BaseModel):
    owner: str; repo: str; path: str; ref: str | None; sha: str; size: int; encoding: Literal["utf-8"]; content: str

class SearchResultItem(BaseModel):
    name: str; path: str; sha: str; html_url: str; repository: str

class SearchResults(BaseModel):
    total_count: int; incomplete_results: bool; items: list[SearchResultItem]

class PullRequestResult(BaseModel):
    owner: str; repo: str; branch_name: str; sha: str; pr_url: str

class WorkerPatchResult(BaseModel):
    ok: bool; worker_url: str; status_code: int; result: Any

def _assert_repo(owner: str, repo: str, write: bool = False) -> None:
    allowed = os.getenv("ALLOWED_REPOS", "").strip()
    if not allowed:
        raise McpToolError("ALLOWED_REPOS is not configured.")
    if allowed != "*":
        allowed_list = [r.strip() for r in allowed.split(",")]
        full_name = f"{owner}/{repo}"
        if full_name not in allowed_list and f"{owner}/*" not in allowed_list:
            raise McpToolError(f"Repository {full_name} is not in ALLOWED_REPOS.")

@asynccontextmanager
async def _github_headers() -> AsyncIterator[dict[str, str]]:
    """Issue one repository-scoped GitHub App token for one API operation."""
    try:
        auth = GitHubAppInstallationAuth(GitHubAppInstallationConfig.from_env())
        async with auth.headers() as headers:
            yield {**headers, "User-Agent": USER_AGENT}
    except RuntimeError as exc:
        raise McpToolError("GitHub App installation authentication is unavailable.") from exc


async def _get(url: str) -> Any:
    async with _github_headers() as headers:
        async with httpx.AsyncClient(headers=headers, timeout=30) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.json()

async def _get_file(owner: str, repo: str, path: str, ref: str | None = None) -> dict:
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
    if ref:
        url += f"?ref={ref}"
    return await _get(url)

def _decode_github_content(item: dict) -> str:
    if item.get("encoding") == "base64":
        return base64.b64decode(item["content"]).decode("utf-8")
    return item["content"]

def _apply_blocks(content: str, blocks: list[PatchBlock], *, require_unique: bool = True) -> tuple[str, list[str]]:
    updated = content
    applied: list[str] = []
    for index, block in enumerate(blocks):
        if block.search not in updated:
            raise McpToolError(f"Block {index}: search string not found.")
        count = updated.count(block.search)
        if require_unique and count > 1:
            raise McpToolError(f"Block {index}: search string is not unique ({count} occurrences).")
        updated = updated.replace(block.search, block.replace, 1 if require_unique else count)
        applied.append(f"block {index}: {count} match(es)")
    return updated, applied

async def _create_full_replace_pr(owner: str, repo: str, path: str, new_content: str,
    message: str, base_branch: str, branch_name: str, pr_title: str, pr_body: str) -> PullRequestResult:
    async with _github_headers() as headers:
        async with httpx.AsyncClient(headers=headers, timeout=30) as client:
            r = await client.get(f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}?ref={base_branch}")
            r.raise_for_status()
            sha = r.json()["sha"]
            r = await client.get(f"{GITHUB_API}/repos/{owner}/{repo}/git/refs/heads/{base_branch}")
            r.raise_for_status()
            base_sha = r.json()["object"]["sha"]
            r = await client.post(f"{GITHUB_API}/repos/{owner}/{repo}/git/refs", json={"ref": f"refs/heads/{branch_name}", "sha": base_sha})
            r.raise_for_status()
            encoded_content = base64.b64encode(new_content.encode()).decode()
            r = await client.put(f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}", json={"message": message, "content": encoded_content, "sha": sha, "branch": branch_name})
            r.raise_for_status()
            r = await client.post(f"{GITHUB_API}/repos/{owner}/{repo}/pulls", json={"title": pr_title, "body": pr_body, "head": branch_name, "base": base_branch})
            r.raise_for_status()
            pr_data = r.json()
    return PullRequestResult(owner=owner, repo=repo, branch_name=branch_name, sha=base_sha, pr_url=pr_data["html_url"])

mcp = FastMCP("Sovereign GitHub Patch MCP")

@mcp.tool()
async def github_get_repository(owner: str, repo: str) -> RepositoryResult:
    _assert_repo(owner, repo)
    data = await _get(f"{GITHUB_API}/repos/{owner}/{repo}")
    return RepositoryResult(owner=owner, repo=repo, default_branch=data["default_branch"], private=data["private"], html_url=data["html_url"], description=data.get("description"))

@mcp.tool()
async def github_list_branches(owner: str, repo: str) -> list[BranchResult]:
    _assert_repo(owner, repo)
    data = await _get(f"{GITHUB_API}/repos/{owner}/{repo}/branches")
    return [BranchResult(name=b["name"], sha=b["commit"]["sha"], protected=b.get("protected", False)) for b in data]

@mcp.tool()
async def github_list_directory(owner: str, repo: str, path: str = "") -> list[DirectoryEntry]:
    _assert_repo(owner, repo)
    data = await _get(f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}")
    if not isinstance(data, list):
        data = [data]
    return [DirectoryEntry(name=item["name"], path=item["path"], type=item["type"], size=item.get("size"), sha=item.get("sha"), html_url=item.get("html_url")) for item in data]

@mcp.tool()
async def github_read_file(owner: str, repo: str, path: str, ref: str | None = None) -> FileContentResult:
    _assert_repo(owner, repo)
    item = await _get_file(owner, repo, path, ref)
    return FileContentResult(owner=owner, repo=repo, path=path, ref=ref, sha=item["sha"], size=item.get("size", 0), encoding="utf-8", content=_decode_github_content(item))

@mcp.tool()
async def github_search_code(owner: str, repo: str, query: str) -> SearchResults:
    _assert_repo(owner, repo)
    data = await _get(f"{GITHUB_API}/search/code?q={query}+repo:{owner}/{repo}&per_page=20")
    return SearchResults(total_count=data["total_count"], incomplete_results=data["incomplete_results"], items=[SearchResultItem(name=item["name"], path=item["path"], sha=item["sha"], html_url=item["html_url"], repository=f"{owner}/{repo}") for item in data.get("items", [])])

@mcp.tool()
async def github_preview_search_replace_patch(owner: str, repo: str, path: str, blocks: list[PatchBlock]) -> str:
    _assert_repo(owner, repo)
    item = await _get_file(owner, repo, path)
    original = _decode_github_content(item)
    patched, applied = _apply_blocks(original, blocks)
    return "\n".join([f"Would apply {len(applied)} block(s):"] + applied)

@mcp.tool()
async def github_full_file_replace_pr(owner: str, repo: str, path: str, new_content: str, message: str,
    branch_name: str | None = None, base_branch: str | None = None, pr_title: str | None = None, pr_body: str | None = None) -> PullRequestResult:
    _assert_repo(owner, repo, write=True)
    item = await _get_file(owner, repo, path)
    base = base_branch or "main"
    branch = branch_name or f"sovereign-patch-{secrets.token_hex(4)}"
    body = pr_body or f"Created by Sovereign GitHub Patch MCP.\n\nReplaced content of {path}."
    return await _create_full_replace_pr(owner=owner, repo=repo, path=path, new_content=new_content, message=message, base_branch=base, branch_name=branch, pr_title=pr_title or message, pr_body=body)

@mcp.tool()
async def github_apply_search_replace_pr(owner: str, repo: str, path: str, message: str, blocks: list[PatchBlock],
    branch_name: str | None = None, base_branch: str | None = None, pr_title: str | None = None, pr_body: str | None = None) -> PullRequestResult:
    _assert_repo(owner, repo, write=True)
    item = await _get_file(owner, repo, path)
    original = _decode_github_content(item)
    base = base_branch or "main"
    branch = branch_name or f"sovereign-patch-{secrets.token_hex(4)}"
    patched, applied = _apply_blocks(original, blocks, require_unique=True)
    if patched == original:
        raise McpToolError("Patch produced no changes.")
    body = pr_body or ("Created by Sovereign GitHub Patch MCP.\n\nApplied SEARCH/REPLACE blocks:\n" + "\n".join(f"- {line}" for line in applied))
    return await _create_full_replace_pr(owner=owner, repo=repo, path=path, new_content=patched, message=message, base_branch=base, branch_name=branch, pr_title=pr_title or message, pr_body=body)

@mcp.tool(name="apply_patch")
async def apply_patch(owner: str, repo: str, path: str, message: str, blocks: list[PatchBlock]) -> WorkerPatchResult:
    _assert_repo(owner, repo, write=True)
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    if SOVEREIGN_PATCH_BEARER:
        headers["Authorization"] = f"Bearer {SOVEREIGN_PATCH_BEARER}"
    payload = {"owner": owner, "repo": repo, "path": path, "message": message, "blocks": [b.model_dump() for b in blocks]}
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(SOVEREIGN_PATCH_URL, headers=headers, json=payload)
    try:
        body = r.json()
    except Exception:
        body = r.text
    if r.status_code >= 400:
        raise McpToolError(f"Sovereign Patch Worker error {r.status_code}: {body}")
    return WorkerPatchResult(ok=True, worker_url=SOVEREIGN_PATCH_URL, status_code=r.status_code, result=body)

# Create app with lifespan to initialize MCP session manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield

app = FastAPI(title="Sovereign MCP", lifespan=lifespan)
app.mount("/", mcp.streamable_http_app())

@app.get("/health")
async def health() -> dict[str, str]:
    return {"ok": "true", "service": "sovereign-github-patch-mcp"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
