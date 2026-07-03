#!/usr/bin/env python3
"""Sovereign Search/Replace Runner.

Reads a JSON patch file, validates strict SEARCH/REPLACE blocks, and either
prints a dry-run preview or writes the patched target file to a branch and opens
a Draft PR. It never writes directly to main.
"""

from __future__ import annotations

import base64
import difflib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

MAX_BLOCKS = 20
MAX_BLOCK_BYTES = 8_000
MAX_FILE_BYTES = 500_000
DEFAULT_REPO = "OuroborosCollective/Sovereign-Studio-ato"
DEFAULT_BASE = "main"
SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_patch(path: str) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as error:
        fail(f"Patch-Datei kann nicht gelesen werden: {error}")
    if not isinstance(data, dict):
        fail("Patch-Datei muss ein JSON-Objekt sein")
    return data


class GitHubApi:
    def __init__(self, repo: str, token: str) -> None:
        if not token:
            fail("GITHUB_TOKEN ist erforderlich")
        self.repo = repo
        self.base_url = f"https://api.github.com/repos/{repo}"
        self.token = token

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                text = response.read().decode("utf-8")
                return json.loads(text) if text else {}
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub API {method} {path} failed: HTTP {error.code}: {detail[:500]}") from error


def encoded_path(path: str) -> str:
    return urllib.parse.quote(path, safe="/")


def encoded_ref(ref: str) -> str:
    return urllib.parse.quote(ref, safe="")


def read_file(api: GitHubApi, path: str, ref: str) -> tuple[str, str]:
    data = api.request("GET", f"/contents/{encoded_path(path)}?ref={encoded_ref(ref)}")
    sha = str(data.get("sha") or "")
    raw = str(data.get("content") or "")
    if not sha or not raw:
        fail(f"Zieldatei konnte nicht gelesen werden: {path}@{ref}")
    content = base64.b64decode(raw).decode("utf-8")
    return sha, content


def validate_blocks(content: str, blocks: Any) -> list[dict[str, str]]:
    if not isinstance(blocks, list) or not blocks:
        fail("patch.blocks muss eine nicht-leere Liste sein")
    if len(blocks) > MAX_BLOCKS:
        fail(f"Zu viele Blöcke: {len(blocks)} (max {MAX_BLOCKS})")
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        fail(f"Datei ist zu groß: max {MAX_FILE_BYTES} Bytes")

    normalized: list[dict[str, str]] = []
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            fail(f"Block {index}: muss ein Objekt sein")
        search = block.get("search")
        replace = block.get("replace")
        if not isinstance(search, str) or not search:
            fail(f"Block {index}: search darf nicht leer sein")
        if not isinstance(replace, str):
            fail(f"Block {index}: replace muss ein String sein")
        if len(search.encode("utf-8")) > MAX_BLOCK_BYTES or len(replace.encode("utf-8")) > MAX_BLOCK_BYTES:
            fail(f"Block {index}: search/replace überschreitet {MAX_BLOCK_BYTES} Bytes")
        count = content.count(search)
        if count != 1:
            fail(f"Block {index}: search muss genau 1x vorkommen, gefunden: {count}")
        normalized.append({"search": search, "replace": replace})
    return normalized


def apply_blocks(content: str, blocks: list[dict[str, str]]) -> str:
    updated = content
    for block in blocks:
        updated = updated.replace(block["search"], block["replace"], 1)
    return updated


def print_diff(path: str, before: str, after: str) -> None:
    print("\n=== DIFF PREVIEW ===\n")
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    )
    print("".join(diff)[:20_000])


def resolve_ref_sha(api: GitHubApi, ref: str) -> str:
    if SHA_RE.fullmatch(ref):
        return ref
    data = api.request("GET", f"/git/ref/heads/{urllib.parse.quote(ref, safe='/')}")
    sha = data.get("object", {}).get("sha")
    if not isinstance(sha, str) or not sha:
        fail(f"Branch SHA nicht gefunden: {ref}")
    return sha


def ensure_branch(api: GitHubApi, branch: str, source_sha: str) -> None:
    payload = {"ref": f"refs/heads/{branch}", "sha": source_sha}
    try:
        api.request("POST", "/git/refs", payload)
        print(f"✓ Branch erstellt: {branch}")
    except RuntimeError as error:
        if "Reference already exists" in str(error) or "already exists" in str(error):
            print(f"✓ Branch existiert bereits: {branch}")
            return
        raise


def update_file(api: GitHubApi, branch: str, path: str, sha: str, content: str, message: str) -> str:
    payload = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "sha": sha,
        "branch": branch,
    }
    data = api.request("PUT", f"/contents/{encoded_path(path)}", payload)
    commit = data.get("commit", {}).get("sha")
    if not isinstance(commit, str) or not commit:
        fail("Commit-SHA fehlt nach Datei-Update")
    return commit


def create_pr(api: GitHubApi, branch: str, base: str, title: str, body: str) -> str:
    payload = {"title": title, "head": branch, "base": base, "body": body, "draft": True}
    try:
        data = api.request("POST", "/pulls", payload)
        return str(data.get("html_url") or "")
    except RuntimeError as error:
        if "A pull request already exists" in str(error) or "pull request already exists" in str(error).lower():
            return "already exists"
        raise


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        fail("Usage: search_replace_runner.py <patch_file.json>")
    patch = read_patch(argv[1])
    repo = os.environ.get("REPO_FULL_NAME", DEFAULT_REPO)
    env_base = os.environ.get("BASE_BRANCH", DEFAULT_BASE)
    target = str(patch.get("target") or "").strip()
    if not target:
        fail("patch.target ist erforderlich")

    source_ref = str(
        patch.get("source_ref")
        or patch.get("source_branch")
        or patch.get("base_branch")
        or env_base
    ).strip()
    branch_base_ref = str(patch.get("branch_base_ref") or source_ref).strip()
    patch_branch = str(os.environ.get("PATCH_BRANCH") or patch.get("branch") or f"sovereign/patch-{int(time.time())}").strip()
    commit_message = str(patch.get("commit_message") or "chore: apply search/replace patch")
    pr_title = str(os.environ.get("PR_TITLE") or patch.get("pr_title") or commit_message)
    pr_body = str(os.environ.get("PR_BODY") or patch.get("pr_body") or "Search/Replace Patch via Sovereign Toolchain")
    dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"
    expected_sha = str(patch.get("expectedSha") or patch.get("expected_sha") or patch.get("base_sha") or "").strip()

    api = GitHubApi(repo, os.environ.get("GITHUB_TOKEN", ""))
    current_sha, before = read_file(api, target, source_ref)
    print(f"Target: {target}")
    print(f"Source ref: {source_ref} @ {current_sha}")
    print(f"Branch base ref: {branch_base_ref}")
    print(f"Patch branch: {patch_branch}")
    print(f"Dry run: {dry_run}")

    if expected_sha and current_sha != expected_sha:
        fail(f"SHA mismatch. Erwartet {expected_sha}, aktuell {current_sha}")

    blocks = validate_blocks(before, patch.get("blocks"))
    after = apply_blocks(before, blocks)
    print(f"✓ Validiert: {len(blocks)} Blöcke")
    print_diff(target, before, after)

    if dry_run:
        print("✓ Dry Run abgeschlossen. Keine Änderungen geschrieben.")
        return

    base_sha = resolve_ref_sha(api, branch_base_ref)
    ensure_branch(api, patch_branch, base_sha)
    branch_file_sha, _ = read_file(api, target, patch_branch)
    commit_sha = update_file(api, patch_branch, target, branch_file_sha, after, commit_message)
    pr_url = create_pr(api, patch_branch, env_base, pr_title, pr_body)
    print("✓ SEARCH/REPLACE PATCH ERFOLGREICH")
    print(f"Commit: {commit_sha}")
    print(f"PR: {pr_url}")


if __name__ == "__main__":
    main(sys.argv)
