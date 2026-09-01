from __future__ import annotations

import asyncio
import base64
import dataclasses
import difflib
import fnmatch
import hashlib
import json
import os
import py_compile
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from github_app_auth import GitHubAppInstallationAuth, GitHubAppInstallationConfig

from .ci_evidence import build_ci_evidence_receipt, build_revision_guardian_receipt

DEFAULT_WORKER_URL = "https://sovereign-studio-worker.projectouroboroscollective.workers.dev/git/patch"
DEFAULT_REPO = "OuroborosCollective/Sovereign-Studio-ato"
DEFAULT_TARGET_PATH = "scripts/sovereign-backend/app.py"
DEFAULT_PATCH_BRANCH = "sovereign/apply-toolchain-guardrails"
DEFAULT_COMMIT_MESSAGE = "fix(toolchain): apply backend patch guardrails"
DEFAULT_PR_BODY = "Applies the verified Toolchain backend guardrails patch from scripts/patches/apply_toolchain_patch_guardrails.py."

_WORKFLOW_FILE_RE = re.compile(r"^[A-Za-z0-9_.-]+\.ya?ml$")

TEXT_SUFFIXES = {
    ".md", ".txt", ".json", ".yml", ".yaml", ".toml", ".ini", ".env",
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".css", ".scss", ".html",
    ".py", ".sh", ".gradle", ".kt", ".java", ".xml", ".properties",
}

HEAVY_PREFIXES = (
    "node_modules/",
    ".pnpm-store/",
    ".ms-playwright/",
    ".corepack/",
    "android/.gradle/",
    "android/build/",
    "dist/",
    "build/",
)

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "toolchain_briefing",
        "description": "Return reusable project + sandbox briefing for agents and no-code workspaces.",
        "write_action": False,
        "input_schema": {"type": "object", "properties": {"include_rules": {"type": "boolean", "default": True}}},
    },
    {
        "name": "list_archive_files",
        "description": "List text-like files inside the mounted Studio/Sandbox archives.",
        "write_action": False,
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "enum": ["studio", "sandbox"], "default": "studio"},
                "prefix": {"type": "string", "default": ""},
                "glob": {"type": "string", "default": "*"},
                "limit": {"type": "integer", "default": 100}
            }
        },
    },
    {
        "name": "read_archive_text",
        "description": "Read a small text file from the mounted archives.",
        "write_action": False,
        "input_schema": {
            "type": "object",
            "required": ["source", "path"],
            "properties": {
                "source": {"type": "string", "enum": ["studio", "sandbox"]},
                "path": {"type": "string"},
                "max_chars": {"type": "integer", "default": 20000}
            }
        },
    },
    {
        "name": "plan_sandbox_commands",
        "description": "Return safe sandbox command plans; does not execute commands.",
        "write_action": False,
        "input_schema": {"type": "object", "properties": {"goal": {"type": "string", "default": "verify"}}},
    },
    {
        "name": "preview_search_replace",
        "description": "Apply strict SEARCH/REPLACE blocks to provided content and return a diff.",
        "write_action": False,
        "input_schema": {
            "type": "object",
            "required": ["path", "content", "blocks"],
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "blocks": {"type": "array", "items": {"type": "object", "required": ["search", "replace"], "properties": {"search": {"type": "string"}, "replace": {"type": "string"}}}}
            }
        },
    },
    {
        "name": "make_patch_payload",
        "description": "Create a Sovereign Patch Worker payload without sending it.",
        "write_action": False,
        "input_schema": {
            "type": "object",
            "required": ["owner", "repo", "path", "message", "blocks"],
            "properties": {
                "owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"},
                "message": {"type": "string"}, "blocks": {"type": "array"},
                "expected_sha": {"type": "string"}, "dry_run": {"type": "boolean", "default": False}
            }
        },
    },
    {
        "name": "sovereign_ci_evidence_receipt",
        "description": "Normalize one GitHub Actions observation into deterministic observation-only evidence for n8n delivery de-duplication. Never creates VERIFIED truth.",
        "write_action": False,
        "input_schema": {
            "type": "object",
            "required": [
                "repository",
                "workflow_id",
                "workflow_name",
                "workflow_selector",
                "branch",
                "branch_head_sha",
                "run_id",
                "head_sha",
                "status",
                "jobs",
            ],
            "properties": {
                "repository": {"type": "string"},
                "workflow_id": {"type": "integer", "minimum": 1},
                "workflow_name": {"type": "string"},
                "workflow_selector": {"type": "string"},
                "branch": {"type": "string"},
                "branch_head_sha": {"type": "string"},
                "run_id": {"type": "integer", "minimum": 1},
                "head_sha": {"type": "string"},
                "expected_head_sha": {"type": "string"},
                "status": {"type": "string"},
                "conclusion": {"type": ["string", "null"]},
                "jobs": {"type": "array"},
                "previous_fingerprint": {"type": "string"}
            }
        },
    },
    {
        "name": "sovereign_revision_guardian_receipt",
        "description": "Compare Git/build/deploy/health/image/schema identities into deterministic observation-only PASS/DRIFT evidence. Never creates VERIFIED truth.",
        "write_action": False,
        "input_schema": {
            "type": "object",
            "required": ["repository", "expected_revision", "git_revision", "build_revision", "deploy_revision", "health_revision", "expected_image_digest", "image_digest", "health_status", "schema_readback"],
            "properties": {
                "repository": {"type": "string"},
                "expected_revision": {"type": "string"},
                "git_revision": {"type": "string"},
                "build_revision": {"type": "string"},
                "deploy_revision": {"type": "string"},
                "health_revision": {"type": "string"},
                "expected_image_digest": {"type": "string"},
                "image_digest": {"type": "string"},
                "health_status": {"type": "string"},
                "schema_readback": {"type": "string"},
                "previous_fingerprint": {"type": "string"}
            }
        },
    },
    {
        "name": "github_actions_run_evidence",
        "description": "Read one exact workflow's latest or selected GitHub Actions run through the scoped GitHub App and normalize workflow/run/job/step evidence for n8n. Read-only.",
        "write_action": False,
        "input_schema": {
            "type": "object",
            "required": ["owner", "repo", "workflow_id"],
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "workflow_id": {
                    "oneOf": [
                        {"type": "integer", "minimum": 1},
                        {"type": "string"}
                    ]
                },
                "branch": {"type": "string", "default": "main"},
                "run_id": {"type": "integer", "minimum": 1},
                "previous_fingerprint": {"type": "string"}
            }
        },
    },
    {
        "name": "github_read_file",
        "description": "Read one GitHub file through the Contents API.",
        "write_action": False,
        "input_schema": {"type": "object", "required": ["owner", "repo", "path"], "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "ref": {"type": "string"}}},
    },
    {
        "name": "github_apply_search_replace_pr",
        "description": "Read GitHub file, apply strict blocks, then create Draft PR using full-file replacement only.",
        "write_action": True,
        "requires_confirm": True,
        "input_schema": {"type": "object", "required": ["owner", "repo", "path", "message", "blocks"], "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "message": {"type": "string"}, "blocks": {"type": "array"}, "branch_name": {"type": "string"}, "title": {"type": "string"}, "body": {"type": "string"}, "base_branch": {"type": "string", "default": "main"}, "expected_sha": {"type": "string"}, "confirm": {"type": "boolean", "default": False}}},
    },
    {
        "name": "apply_patch_worker",
        "description": "Send the Sovereign Patch Worker /git/patch payload after confirmation.",
        "write_action": True,
        "requires_confirm": True,
        "input_schema": {"type": "object", "required": ["owner", "repo", "path", "message", "blocks"], "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "message": {"type": "string"}, "blocks": {"type": "array"}, "expected_sha": {"type": "string"}, "confirm": {"type": "boolean", "default": False}}},
    },
    {
        "name": "apply_backend_guardrails_patch_pr",
        "description": "Apply the embedded backend guardrail patch to scripts/sovereign-backend/app.py and open a Draft PR. No direct main write.",
        "write_action": True,
        "requires_confirm": True,
        "input_schema": {"type": "object", "properties": {"owner": {"type": "string", "default": "OuroborosCollective"}, "repo": {"type": "string", "default": "Sovereign-Studio-ato"}, "base_branch": {"type": "string", "default": "main"}, "patch_branch": {"type": "string", "default": "sovereign/apply-toolchain-guardrails"}, "target_path": {"type": "string", "default": "scripts/sovereign-backend/app.py"}, "message": {"type": "string"}, "title": {"type": "string"}, "body": {"type": "string"}, "expected_sha": {"type": "string"}, "confirm": {"type": "boolean", "default": False}}},
    },
]

def project_root() -> Path:
    return Path(__file__).resolve().parents[2]

def data_path(name: str) -> Path:
    return project_root() / "data" / name

def script_path(name: str) -> Path:
    return project_root() / "scripts" / "patches" / name

def load_profile() -> dict[str, Any]:
    path = data_path("sovereign_archive_profile.json")
    if not path.exists():
        return {"error": "profile_missing", "hint": "Run scripts/regenerate_profile.py or mount archives."}
    return json.loads(path.read_text(encoding="utf-8"))

def load_source_manifest() -> dict[str, Any]:
    path = data_path("source_manifest.json")
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

def safe_error(error: object) -> str:
    text = str(error or "Unknown toolchain error")
    lowered = text.lower()
    sensitive = ("authorization", "bearer ", "token", "secret", "api_key", "access_token", "password", "github_token")
    if any(marker in lowered for marker in sensitive):
        return "Toolchain error; details hidden because they may contain credentials."
    return text[:700]

def safe_rel(path: str) -> str:
    path = (path or "").replace("\\", "/").strip()
    if not path:
        raise ValueError("path must not be empty")
    if path.startswith("/") or path.startswith("~"):
        raise ValueError("absolute paths are not allowed")
    parts = [p for p in path.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ValueError("parent traversal is not allowed")
    return "/".join(parts)

def safe_prefix(prefix: str | None) -> str:
    if not prefix:
        return ""
    return safe_rel(prefix).rstrip("/")

def is_text_name(name: str) -> bool:
    p = Path(name)
    if p.name in {"Dockerfile", "Makefile", ".gitignore", ".gitattributes", ".npmrc"}:
        return True
    if p.name.startswith(".env"):
        return True
    return p.suffix.lower() in TEXT_SUFFIXES

def is_heavy(path: str) -> bool:
    path = path.lstrip("./")
    return path.startswith(HEAVY_PREFIXES) or any(f"/{prefix}" in path for prefix in HEAVY_PREFIXES)

def truncate(text: str, max_chars: int) -> tuple[str, bool]:
    max_chars = max(500, min(int(max_chars), 200_000))
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True

def unified_diff(before: str, after: str, path: str, max_chars: int = 60_000) -> dict[str, Any]:
    diff = "".join(difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    ))
    return {"diff": diff[:max_chars], "truncated": len(diff) > max_chars, "diff_chars": len(diff)}

def apply_blocks(content: str, blocks: list[dict[str, str]]) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("blocks must be a non-empty list")
    if len(blocks) > int(os.getenv("MAX_PATCH_BLOCKS", "20")):
        raise ValueError("too many patch blocks")
    if len(content.encode("utf-8")) > int(os.getenv("MAX_PATCH_FILE_BYTES", "500000")):
        raise ValueError("file too large for guarded patch")
    updated = content
    report: list[dict[str, Any]] = []
    for index, block in enumerate(blocks):
        search = block.get("search", "") if isinstance(block, dict) else ""
        replace = block.get("replace", "") if isinstance(block, dict) else ""
        if not isinstance(search, str) or not isinstance(replace, str):
            raise ValueError(f"block {index}: search/replace must be strings")
        if not search:
            raise ValueError(f"block {index}: search must not be empty")
        if len(search.encode("utf-8")) > 8000 or len(replace.encode("utf-8")) > 8000:
            raise ValueError(f"block {index}: search/replace exceeds size limit")
        count = updated.count(search)
        if count != 1:
            raise ValueError(f"block {index}: search must occur exactly once, found {count}")
        updated = updated.replace(search, replace, 1)
        report.append({"index": index, "match_count": 1, "delta_chars": len(replace) - len(search)})
    return updated, report

@dataclass(frozen=True)
class GitHubContent:
    content: str
    sha: str
    html_url: str | None
    size: int

_GITHUB_READ_ONLY_ENV = "SOVEREIGN_TOOLCHAIN_GITHUB_READ_ONLY"
_READ_ONLY_GITHUB_PERMISSIONS = {"actions": "read", "contents": "read"}


class _ReadOnlyGitHubAppInstallationAuth(GitHubAppInstallationAuth):
    """Mint a lane-scoped token whose requested permissions are read-only."""

    def _issue_token_sync(self) -> str:
        app_jwt = self._app_jwt()
        repository_name = self.config.repository.split("/", 1)[1]
        request_body = {
            "repositories": [repository_name],
            "permissions": dict(_READ_ONLY_GITHUB_PERMISSIONS),
        }
        request = urllib.request.Request(
            f"https://api.github.com/app/installations/{self.config.installation_id}/access_tokens",
            data=json.dumps(request_body, separators=(",", ":")).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                status = getattr(response, "status", None)
                if status is None:
                    status = response.getcode()
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"GitHub App installation token request rejected: HTTP {exc.code}"
            ) from exc
        except (OSError, urllib.error.URLError) as exc:
            raise RuntimeError("GitHub App installation token request failed") from exc
        if status != 201:
            raise RuntimeError(
                f"GitHub App installation token request rejected: HTTP {status}"
            )
        try:
            payload = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("GitHub App installation token response is invalid") from exc
        token = str(payload.get("token") or "").strip() if isinstance(payload, dict) else ""
        if len(token) < 20 or any(character.isspace() for character in token):
            raise RuntimeError("GitHub App installation token response is invalid")
        return token

    async def _issue_token(self) -> str:
        return await asyncio.to_thread(self._issue_token_sync)


class GitHubClient:
    def __init__(self, repository: str | None = None) -> None:
        config = GitHubAppInstallationConfig.from_env()
        selected_repository = config.repository if repository is None else repository
        if (
            not isinstance(selected_repository, str)
            or selected_repository != selected_repository.strip()
            or selected_repository.count("/") != 1
        ):
            raise PermissionError("Repository is not allowlisted")
        owner, repo = selected_repository.split("/", 1)
        if not owner or not repo:
            raise PermissionError("Repository is not allowlisted")
        allowed_repo(owner, repo)
        scoped_config = dataclasses.replace(config, repository=selected_repository)
        read_only_flag = os.getenv(_GITHUB_READ_ONLY_ENV, "")
        if read_only_flag not in {"", "0", "1"}:
            raise RuntimeError(
                f"{_GITHUB_READ_ONLY_ENV} must be unset, 0, or 1"
            )
        auth_type = (
            _ReadOnlyGitHubAppInstallationAuth
            if read_only_flag == "1"
            else GitHubAppInstallationAuth
        )
        self.auth = auth_type(scoped_config)
        self.api = os.getenv("GITHUB_API_BASE", "https://api.github.com").rstrip("/")

    def _request(self, method: str, path_or_url: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = path_or_url if path_or_url.startswith("http") else f"{self.api}{path_or_url}"
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        with self.auth.token() as issued:
            headers = {
                "Authorization": f"Bearer {issued}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "sovereign-universal-toolchain/1.0",
            }
            if body is not None:
                headers["Content-Type"] = "application/json"
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=int(os.getenv("GITHUB_TIMEOUT_SECONDS", "60"))) as resp:
                    raw = resp.read().decode("utf-8")
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"GitHub API {e.code}: {raw[:1000]}") from e

    def repo(self, owner: str, repo: str) -> dict[str, Any]:
        return self._request("GET", f"/repos/{owner}/{repo}")

    def branch_sha(self, owner: str, repo: str, branch: str) -> str:
        data = self._request("GET", f"/repos/{owner}/{repo}/git/ref/heads/{urllib.parse.quote(branch, safe='')}")
        return data["object"]["sha"]

    def ensure_branch(self, owner: str, repo: str, branch: str, from_sha: str) -> dict[str, Any]:
        payload = {"ref": f"refs/heads/{branch}", "sha": from_sha}
        try:
            data = self._request("POST", f"/repos/{owner}/{repo}/git/refs", payload)
            return {"created": True, "branch": branch, "sha": data.get("object", {}).get("sha", from_sha)}
        except RuntimeError as e:
            if "Reference already exists" in str(e) or "422" in str(e):
                return {"created": False, "branch": branch, "sha": from_sha, "reason": "branch already exists"}
            raise

    def read_file(self, owner: str, repo: str, path: str, ref: str | None = None) -> GitHubContent:
        path = safe_rel(path)
        encoded = urllib.parse.quote(path, safe="/")
        query = f"?ref={urllib.parse.quote(ref, safe='')}" if ref else ""
        data = self._request("GET", f"/repos/{owner}/{repo}/contents/{encoded}{query}")
        if data.get("type") != "file":
            raise ValueError(f"GitHub path is not a file: {path}")
        raw = base64.b64decode((data.get("content") or "").replace("\n", ""))
        return GitHubContent(
            content=raw.decode("utf-8"),
            sha=data["sha"],
            html_url=data.get("html_url"),
            size=int(data.get("size") or len(raw)),
        )

    def update_file(self, owner: str, repo: str, path: str, content: str, message: str, branch: str, sha: str) -> dict[str, Any]:
        path = safe_rel(path)
        encoded = urllib.parse.quote(path, safe="/")
        payload = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "sha": sha,
            "branch": branch,
        }
        return self._request("PUT", f"/repos/{owner}/{repo}/contents/{encoded}", payload)

    def create_pr(self, owner: str, repo: str, title: str, head: str, base: str, body: str, draft: bool = True) -> dict[str, Any]:
        payload = {"title": title, "head": head, "base": base, "body": body, "draft": bool(draft)}
        try:
            return self._request("POST", f"/repos/{owner}/{repo}/pulls", payload)
        except RuntimeError as e:
            if "A pull request already exists" in str(e):
                return {"html_url": None, "already_exists": True, "message": "A pull request already exists for this branch."}
            raise

def allowed_repo(owner: str, repo: str) -> None:
    slug = f"{owner}/{repo}".lower()
    raw = os.getenv("ALLOWED_REPOS", "OuroborosCollective/Sovereign-Studio-ato").strip()
    allowed = {x.strip().lower() for x in raw.split(",") if x.strip()}
    if "*" not in allowed and slug not in allowed:
        raise PermissionError(f"Repo {owner}/{repo} is not in ALLOWED_REPOS")

def assert_expected_sha(current_sha: str, expected_sha: str | None) -> None:
    if expected_sha and current_sha != expected_sha:
        raise RuntimeError("SHA mismatch: file changed since preview. Reload and preview again.")

def briefing(include_rules: bool = True) -> dict[str, Any]:
    profile = load_profile()
    manifest = load_source_manifest()
    out = {
        "name": "Sovereign Universal Toolchain",
        "interfaces": ["MCP Streamable HTTP /mcp", "REST /v1/tools/{name}", "OpenAPI /openapi.json", "CLI scripts"],
        "purpose": "Reusable repo, sandbox and guarded patch toolchain for LLM agents, no-code workspaces and ChatGPT connectors.",
        "default_write_policy": {
            "direct_main_push": False,
            "write_modes": ["preview only", "Draft PR via GitHub full-file replacement", "external patch worker with confirm=True"],
            "requires": ["ALLOWED_REPOS", "GitHub App installation access", "confirm=True for write actions"],
        },
        "project_profile": profile.get("project", {}),
        "source_archives": profile.get("source_archives", manifest.get("generated_from", [])),
        "recommended_tools": [t["name"] for t in TOOL_DEFINITIONS],
    }
    if include_rules:
        out["sovereign_rules"] = profile.get("sovereign_rules", {
            "never_write_directly_to_main": True,
            "use_draft_prs_for_changes": True,
            "preview_patch_before_apply": True,
        })
    return out

class ArchiveReader:
    def __init__(self) -> None:
        self.studio_zip = os.getenv("SOVEREIGN_STUDIO_ZIP", "").strip()
        self.sandbox_zip = os.getenv("SOVEREIGN_SANDBOX_ZIP", "").strip()

    def zip_path(self, source: Literal["studio", "sandbox"]) -> Path:
        raw = self.studio_zip if source == "studio" else self.sandbox_zip
        if not raw:
            raise FileNotFoundError(f"{source} archive is not mounted. Set SOVEREIGN_{source.upper()}_ZIP.")
        path = Path(raw)
        if not path.exists():
            raise FileNotFoundError(f"{source} archive not found: {path}")
        return path

    def _zip_has_nested_tar(self, z: zipfile.ZipFile) -> str | None:
        for name in z.namelist():
            if name.endswith(".tar.gz") or name.endswith(".tgz"):
                return name
        return None

    def _iter_text_entries(self, source: Literal["studio", "sandbox"]):
        """Yield (logical_name, read_callable) for text-like archive entries.

        Studio archives are normal ZIPs. The sandbox upload is often a ZIP containing
        one large tar.gz, so this supports both shapes without requiring extraction.
        """
        zpath = self.zip_path(source)
        with zipfile.ZipFile(zpath) as z:
            nested = self._zip_has_nested_tar(z)
            if source == "sandbox" and nested:
                import tarfile
                with z.open(nested) as nested_stream:
                    with tarfile.open(fileobj=nested_stream, mode="r:gz") as tar:
                        for member in tar:
                            if not member.isfile():
                                continue
                            name = member.name
                            if is_heavy(name) or not is_text_name(name):
                                continue
                            def reader(n=name):
                                f = tar.extractfile(n)
                                if f is None:
                                    raise FileNotFoundError(n)
                                return f.read()
                            yield name, reader
            else:
                for name in z.namelist():
                    if name.endswith("/") or is_heavy(name) or not is_text_name(name):
                        continue
                    yield name, lambda n=name: z.read(n)

    def list_files(self, source: Literal["studio", "sandbox"], prefix: str = "", glob: str = "*", limit: int = 100) -> dict[str, Any]:
        prefix = safe_prefix(prefix)
        limit = max(1, min(int(limit), 500))
        matches: list[str] = []
        scanned = 0
        for name, _reader in self._iter_text_entries(source):
            scanned += 1
            rel = name
            if prefix and prefix not in rel:
                continue
            if glob and not fnmatch.fnmatch(Path(rel).name, glob) and not fnmatch.fnmatch(rel, glob):
                continue
            matches.append(rel)
            if len(matches) >= limit:
                break
        return {"source": source, "prefix": prefix, "glob": glob, "count": len(matches), "scanned": scanned, "files": matches}

    def read_text(self, source: Literal["studio", "sandbox"], path: str, max_chars: int = 20000) -> dict[str, Any]:
        rel = safe_rel(path)
        for name, reader in self._iter_text_entries(source):
            if name == rel or name.endswith("/" + rel):
                raw = reader()
                if len(raw) > int(os.getenv("MAX_ARCHIVE_TEXT_BYTES", "1048576")):
                    raise ValueError("archive file too large to read")
                text = raw.decode("utf-8", errors="replace")
                content, truncated = truncate(text, max_chars)
                return {"source": source, "path": name, "bytes": len(raw), "truncated": truncated, "content": content}
        raise FileNotFoundError(f"file not found in {source}: {rel}")
archive_reader = ArchiveReader()

def plan_sandbox_commands(goal: str = "verify") -> dict[str, Any]:
    profile = load_profile()
    scripts = profile.get("project", {}).get("main_scripts", {})
    goal_l = (goal or "verify").lower()
    plans = {
        "verify": ["pnpm install --frozen-lockfile", "pnpm run audit:sovereign", "pnpm run test:smoke", "pnpm run build:web"],
        "android": ["pnpm run build:web", "pnpm exec cap sync android", "cd android && chmod +x ./gradlew && ./gradlew assembleDebug"],
        "playwright": ["pnpm exec playwright install --with-deps chromium", "pnpm exec playwright test"],
        "guardrails": ["python3 scripts/patches/apply_toolchain_patch_guardrails.py --repo-root . --check", "python3 -m py_compile scripts/sovereign-backend/app.py"],
    }
    selected = plans.get(goal_l, plans["verify"])
    return {
        "goal": goal,
        "commands": selected,
        "execute": False,
        "note": "This tool only plans commands. A human or CI worker should execute them in the sandbox.",
        "known_package_scripts": scripts,
    }

def make_patch_payload(owner: str, repo: str, path: str, message: str, blocks: list[dict[str, str]], expected_sha: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    allowed_repo(owner, repo)
    if not blocks:
        raise ValueError("blocks required")
    payload: dict[str, Any] = {"owner": owner, "repo": repo, "path": safe_rel(path), "message": message, "blocks": blocks}
    if expected_sha:
        payload["expectedSha"] = expected_sha
    payload["dryRun"] = bool(dry_run)
    return {"worker_url": os.getenv("PATCH_WORKER_URL", DEFAULT_WORKER_URL), "payload": payload, "send": False}

def preview_search_replace(path: str, content: str, blocks: list[dict[str, str]]) -> dict[str, Any]:
    after, report = apply_blocks(content, blocks)
    return {"path": safe_rel(path), "changed": after != content, "block_report": report, "diff": unified_diff(content, after, path)}

def github_read_file(owner: str, repo: str, path: str, ref: str | None = None, max_chars: int = 60000) -> dict[str, Any]:
    allowed_repo(owner, repo)
    data = GitHubClient().read_file(owner, repo, path, ref)
    content, truncated = truncate(data.content, max_chars)
    return {"owner": owner, "repo": repo, "path": safe_rel(path), "ref": ref, "sha": data.sha, "html_url": data.html_url, "bytes": data.size, "truncated": truncated, "content": content}


def _workflow_selector(value: Any) -> str:
    if isinstance(value, bool):
        raise ValueError("workflow_id must be a positive integer or workflow filename")
    if isinstance(value, int):
        if value <= 0:
            raise ValueError("workflow_id must be positive")
        return str(value)
    selector = str(value or "").strip()
    if selector.isdigit():
        if int(selector) <= 0:
            raise ValueError("workflow_id must be positive")
        return selector
    if not _WORKFLOW_FILE_RE.fullmatch(selector):
        raise ValueError("workflow_id must be a safe .yml/.yaml filename or positive integer")
    return selector


def _safe_branch(value: str) -> str:
    branch = str(value or "").strip()
    if (
        not branch
        or len(branch) > 255
        or branch.startswith(("/", "~"))
        or branch.endswith(("/", "."))
        or ".." in branch
        or "//" in branch
        or "@{" in branch
        or any(character.isspace() or character in "\\~^:?*[" for character in branch)
    ):
        raise ValueError("branch is not a safe Git ref")
    return branch


def github_actions_run_evidence(
    owner: str,
    repo: str,
    workflow_id: int | str,
    branch: str = "main",
    run_id: int | None = None,
    previous_fingerprint: str | None = None,
) -> dict[str, Any]:
    allowed_repo(owner, repo)
    selector = _workflow_selector(workflow_id)
    selected_branch = _safe_branch(branch)
    gh = GitHubClient(f"{owner}/{repo}")
    selector_q = urllib.parse.quote(selector, safe="")
    workflow = gh._request(
        "GET",
        f"/repos/{owner}/{repo}/actions/workflows/{selector_q}",
    )
    resolved_workflow_id = int(workflow.get("id") or 0)
    if resolved_workflow_id <= 0:
        raise RuntimeError("GitHub Actions workflow response has no valid id")
    workflow_name = str(workflow.get("name") or "").strip()
    if not workflow_name:
        raise RuntimeError("GitHub Actions workflow response has no name")

    if run_id is None:
        branch_q = urllib.parse.quote(selected_branch, safe="")
        latest = gh._request(
            "GET",
            f"/repos/{owner}/{repo}/actions/workflows/{selector_q}/runs?branch={branch_q}&per_page=1",
        )
        runs = latest.get("workflow_runs") or []
        if not runs:
            raise RuntimeError("No GitHub Actions run found for requested workflow and branch")
        run = runs[0]
    else:
        if isinstance(run_id, bool) or int(run_id) <= 0:
            raise ValueError("run_id must be a positive integer")
        run = gh._request("GET", f"/repos/{owner}/{repo}/actions/runs/{int(run_id)}")

    if int(run.get("workflow_id") or 0) != resolved_workflow_id:
        raise RuntimeError("GitHub Actions run does not belong to the selected workflow")
    if str(run.get("head_branch") or "").strip() != selected_branch:
        raise RuntimeError("GitHub Actions run does not belong to the selected branch")
    resolved_run_id = int(run.get("id") or 0)
    if resolved_run_id <= 0:
        raise RuntimeError("GitHub Actions run response has no valid id")

    branch_head_sha = gh.branch_sha(owner, repo, selected_branch)
    _JOB_PAGE_LIMIT = 100
    _JOB_TOTAL_LIMIT = 250
    all_jobs: list[Any] = []
    page = 1
    while len(all_jobs) < _JOB_TOTAL_LIMIT:
        jobs_response = gh._request(
            "GET",
            f"/repos/{owner}/{repo}/actions/runs/{resolved_run_id}/jobs"
            f"?per_page={_JOB_PAGE_LIMIT}&page={page}",
        )
        page_jobs = jobs_response.get("jobs") or []
        all_jobs.extend(page_jobs)
        if len(page_jobs) < _JOB_PAGE_LIMIT:
            break
        page += 1
    observation: dict[str, Any] = {
        "repository": f"{owner}/{repo}",
        "workflow_id": resolved_workflow_id,
        "workflow_name": workflow_name,
        "workflow_selector": selector,
        "branch": selected_branch,
        "branch_head_sha": branch_head_sha,
        "run_id": resolved_run_id,
        "head_sha": run.get("head_sha"),
        "expected_head_sha": branch_head_sha,
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "jobs": all_jobs,
    }
    if previous_fingerprint:
        observation["previous_fingerprint"] = previous_fingerprint
    return build_ci_evidence_receipt(observation)


def github_apply_search_replace_pr(owner: str, repo: str, path: str, message: str, blocks: list[dict[str, str]], branch_name: str | None = None, title: str | None = None, body: str | None = None, base_branch: str | None = None, expected_sha: str | None = None, confirm: bool = False) -> dict[str, Any]:
    allowed_repo(owner, repo)
    base_branch = base_branch or os.getenv("BASE_BRANCH", "main")
    branch_name = branch_name or f"sovereign/toolchain-{hashlib.sha1((path + message).encode()).hexdigest()[:10]}"
    gh = GitHubClient()
    current = gh.read_file(owner, repo, path, base_branch)
    assert_expected_sha(current.sha, expected_sha)
    after, report = apply_blocks(current.content, blocks)
    diff = unified_diff(current.content, after, path)
    if not confirm:
        return {
            "created": False, "reason": "confirm=True required", "write_action": False,
            "owner": owner, "repo": repo, "path": safe_rel(path), "base_branch": base_branch,
            "base_sha": current.sha, "branch_name": branch_name, "block_report": report, "diff": diff,
        }
    base_sha = gh.branch_sha(owner, repo, base_branch)
    branch = gh.ensure_branch(owner, repo, branch_name, base_sha)
    branch_current = gh.read_file(owner, repo, path, branch_name)
    assert_expected_sha(branch_current.sha, expected_sha or current.sha)
    update = gh.update_file(owner, repo, path, after, message, branch_name, branch_current.sha)
    pr = gh.create_pr(owner, repo, title or message, branch_name, base_branch, body or DEFAULT_PR_BODY, draft=True)
    return {
        "created": True, "write_mode": "full-file-replace-via-draft-pr", "branch": branch,
        "commit": update.get("commit", {}), "draft_pr": pr.get("html_url"), "pr": pr,
        "base_sha": current.sha, "block_report": report, "diff": diff,
    }

def apply_patch_worker(owner: str, repo: str, path: str, message: str, blocks: list[dict[str, str]], expected_sha: str | None = None, confirm: bool = False) -> dict[str, Any]:
    payload = make_patch_payload(owner, repo, path, message, blocks, expected_sha=expected_sha, dry_run=False)["payload"]
    worker_url = os.getenv("PATCH_WORKER_URL", DEFAULT_WORKER_URL)
    if not confirm:
        return {
            "sent": False, "reason": "confirm=True required", "write_action": False,
            "worker_url": worker_url, "payload_preview": {k: v for k, v in payload.items() if k != "blocks"},
            "block_count": len(blocks),
        }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(worker_url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"raw": raw}
    return {"sent": True, "worker_url": worker_url, "response": parsed}

def load_guardrail_blocks() -> list[dict[str, str]]:
    script = script_path("apply_toolchain_patch_guardrails.py")
    ns: dict[str, Any] = {}
    # This file is part of this package. It is loaded only to read literal Block data.
    exec(script.read_text(encoding="utf-8"), ns)
    blocks = ns.get("BLOCKS")
    if not blocks:
        raise RuntimeError("guardrail blocks not found")
    return [{"search": b.search, "replace": b.replace} for b in blocks]

def compile_python_text(content: str, filename: str = "app.py") -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / filename
        path.write_text(content, encoding="utf-8")
        py_compile.compile(str(path), doraise=True)

def apply_backend_guardrails_patch_pr(owner: str = "OuroborosCollective", repo: str = "Sovereign-Studio-ato", base_branch: str = "main", patch_branch: str = DEFAULT_PATCH_BRANCH, target_path: str = DEFAULT_TARGET_PATH, message: str = DEFAULT_COMMIT_MESSAGE, title: str = DEFAULT_COMMIT_MESSAGE, body: str = DEFAULT_PR_BODY, expected_sha: str | None = None, confirm: bool = False) -> dict[str, Any]:
    blocks = load_guardrail_blocks()
    allowed_repo(owner, repo)
    gh = GitHubClient()
    current = gh.read_file(owner, repo, target_path, base_branch)
    assert_expected_sha(current.sha, expected_sha)
    patched, report = apply_blocks(current.content, blocks)
    compile_python_text(patched, Path(target_path).name)
    diff = unified_diff(current.content, patched, target_path)
    if not confirm:
        return {
            "created": False, "reason": "confirm=True required", "write_action": False,
            "owner": owner, "repo": repo, "target_path": safe_rel(target_path), "base_branch": base_branch,
            "patch_branch": patch_branch, "base_sha": current.sha, "blocks": len(blocks),
            "py_compile": "ok", "block_report": report, "diff": diff,
        }
    base_sha = gh.branch_sha(owner, repo, base_branch)
    branch = gh.ensure_branch(owner, repo, patch_branch, base_sha)
    branch_current = gh.read_file(owner, repo, target_path, patch_branch)
    assert_expected_sha(branch_current.sha, expected_sha or current.sha)
    update = gh.update_file(owner, repo, target_path, patched, message, patch_branch, branch_current.sha)
    pr = gh.create_pr(owner, repo, title, patch_branch, base_branch, body, draft=True)
    return {
        "created": True, "write_mode": "full-file-replace-via-github-contents-api-draft-pr",
        "branch": branch, "commit": update.get("commit", {}), "draft_pr": pr.get("html_url"),
        "base_sha": current.sha, "py_compile": "ok", "block_report": report, "diff": diff,
    }

def dispatch_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    args = args or {}
    table = {
        "toolchain_briefing": lambda: briefing(bool(args.get("include_rules", True))),
        "list_archive_files": lambda: archive_reader.list_files(args.get("source", "studio"), args.get("prefix", ""), args.get("glob", "*"), int(args.get("limit", 100))),
        "read_archive_text": lambda: archive_reader.read_text(args["source"], args["path"], int(args.get("max_chars", 20000))),
        "plan_sandbox_commands": lambda: plan_sandbox_commands(args.get("goal", "verify")),
        "sovereign_ci_evidence_receipt": lambda: build_ci_evidence_receipt(args),
        "sovereign_revision_guardian_receipt": lambda: build_revision_guardian_receipt(args),
        "github_actions_run_evidence": lambda: github_actions_run_evidence(
            args["owner"],
            args["repo"],
            args["workflow_id"],
            args.get("branch", "main"),
            args.get("run_id"),
            args.get("previous_fingerprint"),
        ),
        "preview_search_replace": lambda: preview_search_replace(args["path"], args["content"], args["blocks"]),
        "make_patch_payload": lambda: make_patch_payload(args["owner"], args["repo"], args["path"], args["message"], args["blocks"], args.get("expected_sha") or args.get("expectedSha"), bool(args.get("dry_run", False))),
        "github_read_file": lambda: github_read_file(args["owner"], args["repo"], args["path"], args.get("ref"), int(args.get("max_chars", 60000))),
        "github_apply_search_replace_pr": lambda: github_apply_search_replace_pr(args["owner"], args["repo"], args["path"], args["message"], args["blocks"], args.get("branch_name"), args.get("title"), args.get("body"), args.get("base_branch"), args.get("expected_sha") or args.get("expectedSha"), bool(args.get("confirm", False))),
        "apply_patch_worker": lambda: apply_patch_worker(args["owner"], args["repo"], args["path"], args["message"], args["blocks"], args.get("expected_sha") or args.get("expectedSha"), bool(args.get("confirm", False))),
        "apply_backend_guardrails_patch_pr": lambda: apply_backend_guardrails_patch_pr(
            args.get("owner", "OuroborosCollective"),
            args.get("repo", "Sovereign-Studio-ato"),
            args.get("base_branch", "main"),
            args.get("patch_branch", DEFAULT_PATCH_BRANCH),
            args.get("target_path", DEFAULT_TARGET_PATH),
            args.get("message", DEFAULT_COMMIT_MESSAGE),
            args.get("title", DEFAULT_COMMIT_MESSAGE),
            args.get("body", DEFAULT_PR_BODY),
            args.get("expected_sha") or args.get("expectedSha"),
            bool(args.get("confirm", False)),
        ),
    }
    if name not in table:
        raise KeyError(f"Unknown tool: {name}")
    try:
        return {"ok": True, "tool": name, "result": table[name]()}
    except Exception as e:
        return {"ok": False, "tool": name, "error": safe_error(e)}
