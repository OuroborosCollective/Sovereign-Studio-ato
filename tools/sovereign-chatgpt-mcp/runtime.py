from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from policy import (
    MAX_FILE_BYTES,
    safe_repo_path,
    sha256_bytes,
    validate_branch,
    validate_container,
    validate_patch_blocks,
    validate_workspace_id,
)


@dataclass(frozen=True)
class RuntimeConfig:
    repository: str
    workspace_root: Path
    github_token: str
    allowed_base_branches: tuple[str, ...]
    allowed_containers: tuple[str, ...]
    command_timeout: int

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        repository = os.getenv("SOVEREIGN_MCP_REPOSITORY", "OuroborosCollective/Sovereign-Studio-ato").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise RuntimeError("SOVEREIGN_MCP_REPOSITORY ist ungültig")
        root = Path(os.getenv("SOVEREIGN_MCP_WORKSPACE_ROOT", "/opt/sovereign-chatgpt-tools/workspaces"))
        token = os.getenv("GITHUB_TOKEN", "").strip()
        bases = tuple(x.strip() for x in os.getenv("SOVEREIGN_MCP_ALLOWED_BASE_BRANCHES", "main").split(",") if x.strip())
        containers = tuple(x.strip() for x in os.getenv("SOVEREIGN_MCP_ALLOWED_CONTAINERS", "sovereign-backend").split(",") if x.strip())
        timeout = max(30, min(int(os.getenv("SOVEREIGN_MCP_COMMAND_TIMEOUT", "900")), 3600))
        return cls(repository, root, token, bases, containers, timeout)


class OperatorRuntime:
    def __init__(self, config: RuntimeConfig | None = None) -> None:
        self.config = config or RuntimeConfig.from_env()
        self.config.workspace_root.mkdir(parents=True, exist_ok=True)

    def _workspace(self, workspace_id: str) -> Path:
        workspace_id = validate_workspace_id(workspace_id)
        root = self.config.workspace_root.resolve()
        workspace = (root / workspace_id).resolve()
        if root not in workspace.parents:
            raise ValueError("Workspace verlässt den Runtime-Pfad")
        return workspace

    def _repo(self, workspace_id: str) -> Path:
        repo = self._workspace(workspace_id) / "repo"
        if not (repo / ".git").is_dir():
            raise FileNotFoundError("Workspace wurde noch nicht vorbereitet")
        return repo

    def _metadata_path(self, workspace_id: str) -> Path:
        return self._workspace(workspace_id) / "workspace.json"

    def _read_metadata(self, workspace_id: str) -> dict[str, Any]:
        return json.loads(self._metadata_path(workspace_id).read_text("utf-8"))

    def _write_metadata(self, workspace_id: str, data: dict[str, Any]) -> None:
        self._metadata_path(workspace_id).write_text(json.dumps(data, indent=2, sort_keys=True), "utf-8")

    def _askpass(self) -> tuple[str, dict[str, str]]:
        if not self.config.github_token:
            raise RuntimeError("GITHUB_TOKEN ist auf dem MCP-Server nicht konfiguriert")
        directory = tempfile.mkdtemp(prefix="sovereign-askpass-")
        script = Path(directory) / "askpass.sh"
        script.write_text(
            "#!/bin/sh\ncase \"$1\" in *Username*) echo x-access-token ;; *Password*) printf '%s' \"$GITHUB_TOKEN\" ;; esac\n",
            "utf-8",
        )
        script.chmod(0o700)
        env = os.environ.copy()
        env.update({"GIT_ASKPASS": str(script), "GIT_TERMINAL_PROMPT": "0", "GITHUB_TOKEN": self.config.github_token})
        return directory, env

    def _run(self, argv: list[str], *, cwd: Path, timeout: int | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
        started = time.monotonic()
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout or self.config.command_timeout,
            check=False,
        )
        output_limit = 24_000
        return {
            "argv": argv,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-output_limit:],
            "stderr": completed.stderr[-output_limit:],
            "duration_ms": int((time.monotonic() - started) * 1000),
            "ok": completed.returncode == 0,
        }

    def prepare_workspace(self, *, base_branch: str, task_slug: str) -> dict[str, Any]:
        if base_branch not in self.config.allowed_base_branches:
            raise ValueError("Base-Branch ist nicht freigegeben")
        slug = re.sub(r"[^a-z0-9-]+", "-", task_slug.lower()).strip("-")[:40] or "change"
        workspace_id = f"job-{uuid.uuid4().hex[:12]}"
        branch = validate_branch(f"sovereign/chatgpt/{int(time.time())}-{slug}-{uuid.uuid4().hex[:6]}")
        workspace = self._workspace(workspace_id)
        repo = workspace / "repo"
        workspace.mkdir(mode=0o700, parents=True, exist_ok=False)
        askpass_dir, env = self._askpass()
        try:
            clone = self._run(
                ["git", "clone", "--depth", "1", "--branch", base_branch, f"https://github.com/{self.config.repository}.git", str(repo)],
                cwd=workspace,
                env=env,
            )
            if not clone["ok"]:
                shutil.rmtree(workspace, ignore_errors=True)
                raise RuntimeError(f"Git clone fehlgeschlagen: {clone['stderr']}")
            checkout = self._run(["git", "checkout", "-b", branch], cwd=repo)
            if not checkout["ok"]:
                shutil.rmtree(workspace, ignore_errors=True)
                raise RuntimeError(f"Branch-Erstellung fehlgeschlagen: {checkout['stderr']}")
            self._run(["git", "config", "user.name", os.getenv("SOVEREIGN_MCP_GIT_AUTHOR_NAME", "Sovereign ChatGPT Operator")], cwd=repo)
            self._run(["git", "config", "user.email", os.getenv("SOVEREIGN_MCP_GIT_AUTHOR_EMAIL", "sovereign-operator@users.noreply.github.com")], cwd=repo)
        finally:
            shutil.rmtree(askpass_dir, ignore_errors=True)

        metadata = {
            "workspace_id": workspace_id,
            "repository": self.config.repository,
            "base_branch": base_branch,
            "branch": branch,
            "created_at": int(time.time()),
            "checks": {},
        }
        self._write_metadata(workspace_id, metadata)
        return metadata

    def read_file(self, workspace_id: str, path: str, max_bytes: int = MAX_FILE_BYTES) -> dict[str, Any]:
        file_path = safe_repo_path(self._repo(workspace_id), path, must_exist=True)
        data = file_path.read_bytes()
        limit = max(1, min(max_bytes, MAX_FILE_BYTES))
        if len(data) > limit:
            raise ValueError(f"Datei ist größer als {limit} Bytes")
        return {"path": path, "sha256": sha256_bytes(data), "bytes": len(data), "content": data.decode("utf-8")}

    def search_text(self, workspace_id: str, query: str, path: str = ".", max_results: int = 100) -> dict[str, Any]:
        if not query or len(query) > 500:
            raise ValueError("Suchtext fehlt oder ist zu lang")
        repo = self._repo(workspace_id)
        start = repo if path == "." else safe_repo_path(repo, path)
        results: list[dict[str, Any]] = []
        candidates = [start] if start.is_file() else start.rglob("*")
        for candidate in candidates:
            if len(results) >= max(1, min(max_results, 200)):
                break
            if not candidate.is_file() or ".git" in candidate.parts or candidate.stat().st_size > MAX_FILE_BYTES:
                continue
            try:
                text = candidate.read_text("utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                if query in line:
                    results.append({"path": str(candidate.relative_to(repo)), "line": line_no, "text": line[:500]})
                    if len(results) >= max_results:
                        break
        return {"query": query, "results": results, "truncated": len(results) >= max_results}

    def apply_search_replace(self, workspace_id: str, path: str, blocks: list[dict[str, str]], expected_sha256: str = "") -> dict[str, Any]:
        validate_patch_blocks(blocks)
        file_path = safe_repo_path(self._repo(workspace_id), path, must_exist=True)
        original = file_path.read_bytes()
        if len(original) > MAX_FILE_BYTES:
            raise ValueError("Zieldatei ist zu groß")
        actual_sha = sha256_bytes(original)
        if expected_sha256 and expected_sha256 != actual_sha:
            raise ValueError("Datei wurde seit dem Lesen verändert")
        text = original.decode("utf-8")
        for index, block in enumerate(blocks, start=1):
            matches = text.count(block["search"])
            if matches != 1:
                raise ValueError(f"Patch-Block {index} muss exakt einmal treffen, Treffer: {matches}")
            text = text.replace(block["search"], block["replace"], 1)
        file_path.write_text(text, "utf-8")
        return {"path": path, "before_sha256": actual_sha, "after_sha256": sha256_bytes(text.encode()), "blocks": len(blocks)}

    def write_new_file(self, workspace_id: str, path: str, content: str) -> dict[str, Any]:
        file_path = safe_repo_path(self._repo(workspace_id), path, must_exist=False)
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_FILE_BYTES:
            raise ValueError("Neue Datei ist zu groß")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(encoded)
        return {"path": path, "sha256": sha256_bytes(encoded), "bytes": len(encoded)}

    def git_diff(self, workspace_id: str) -> dict[str, Any]:
        repo = self._repo(workspace_id)
        status = self._run(["git", "status", "--short"], cwd=repo)
        diff = self._run(["git", "diff", "--", "."], cwd=repo)
        stat = self._run(["git", "diff", "--stat", "--", "."], cwd=repo)
        return {"status": status["stdout"], "diff": diff["stdout"], "stat": stat["stdout"], "ok": status["ok"] and diff["ok"]}

    def run_check(self, workspace_id: str, check: str, target: str = "") -> dict[str, Any]:
        repo = self._repo(workspace_id)
        allowed: dict[str, list[str]] = {
            "git_diff_check": ["git", "diff", "--check"],
            "backend_compile": ["python3", "-m", "py_compile", "scripts/sovereign-backend/app.py"],
            "typecheck": ["pnpm", "run", "type-check"],
            "audit": ["pnpm", "run", "audit:sovereign"],
            "build_web": ["pnpm", "run", "build:web"],
        }
        if check == "vitest":
            test_path = safe_repo_path(repo, target, must_exist=True)
            command = ["pnpm", "exec", "vitest", "run", str(test_path.relative_to(repo))]
        elif check in allowed:
            command = allowed[check]
        else:
            raise ValueError("Check ist nicht freigegeben")
        result = self._run(command, cwd=repo)
        metadata = self._read_metadata(workspace_id)
        metadata.setdefault("checks", {})[check if check != "vitest" else f"vitest:{target}"] = {
            "ok": result["ok"], "exit_code": result["exit_code"], "duration_ms": result["duration_ms"], "at": int(time.time())
        }
        self._write_metadata(workspace_id, metadata)
        return result

    def _changed_files(self, repo: Path) -> list[str]:
        result = self._run(["git", "status", "--porcelain"], cwd=repo)
        files: list[str] = []
        for line in result["stdout"].splitlines():
            if len(line) >= 4:
                files.append(line[3:].strip())
        return list(dict.fromkeys(files))

    def create_draft_pr(self, workspace_id: str, *, title: str, body: str, commit_message: str) -> dict[str, Any]:
        repo = self._repo(workspace_id)
        metadata = self._read_metadata(workspace_id)
        branch = validate_branch(metadata["branch"])
        changed = self._changed_files(repo)
        if not changed:
            raise ValueError("Keine Änderungen vorhanden")

        diff_check = self.run_check(workspace_id, "git_diff_check")
        if not diff_check["ok"]:
            raise RuntimeError("git diff --check ist fehlgeschlagen")
        if any(path.endswith(".py") for path in changed):
            compile_result = self.run_check(workspace_id, "backend_compile")
            if not compile_result["ok"]:
                raise RuntimeError("Backend-Compile-Check ist fehlgeschlagen")
        if any(path.endswith((".ts", ".tsx")) for path in changed):
            typecheck = self.run_check(workspace_id, "typecheck")
            if not typecheck["ok"]:
                raise RuntimeError("TypeScript-Typecheck ist fehlgeschlagen")

        add = self._run(["git", "add", "--all"], cwd=repo)
        commit = self._run(["git", "commit", "-m", commit_message[:200]], cwd=repo)
        if not add["ok"] or not commit["ok"]:
            raise RuntimeError(f"Commit fehlgeschlagen: {commit['stderr'] or add['stderr']}")
        askpass_dir, env = self._askpass()
        try:
            push = self._run(["git", "push", "--set-upstream", "origin", branch], cwd=repo, env=env)
        finally:
            shutil.rmtree(askpass_dir, ignore_errors=True)
        if not push["ok"]:
            raise RuntimeError(f"Push fehlgeschlagen: {push['stderr']}")

        owner = self.config.repository.split("/", 1)[0]
        headers = {"Authorization": f"Bearer {self.config.github_token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        response = requests.post(
            f"https://api.github.com/repos/{self.config.repository}/pulls",
            headers=headers,
            timeout=30,
            json={"title": title[:256], "head": f"{owner}:{branch}", "base": metadata["base_branch"], "body": body, "draft": True},
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Draft-PR konnte nicht erstellt werden: HTTP {response.status_code} {response.text[:1000]}")
        payload = response.json()
        metadata["draft_pr"] = {"number": payload["number"], "url": payload["html_url"], "head_sha": payload["head"]["sha"]}
        self._write_metadata(workspace_id, metadata)
        return {"draft": True, "number": payload["number"], "url": payload["html_url"], "branch": branch, "changed_files": changed}

    def container_status(self, container: str) -> dict[str, Any]:
        container = validate_container(container, self.config.allowed_containers)
        result = self._run(
            ["docker", "inspect", "--format", "{{json .State}}", container],
            cwd=self.config.workspace_root,
            timeout=30,
        )
        if not result["ok"]:
            return {"ok": False, "container": container, "error": result["stderr"]}
        return {"ok": True, "container": container, "state": json.loads(result["stdout"])}

    def container_logs(self, container: str, tail: int = 200) -> dict[str, Any]:
        container = validate_container(container, self.config.allowed_containers)
        result = self._run(["docker", "logs", "--tail", str(max(1, min(tail, 1000))), container], cwd=self.config.workspace_root, timeout=60)
        return {"ok": result["ok"], "container": container, "stdout": result["stdout"], "stderr": result["stderr"]}
