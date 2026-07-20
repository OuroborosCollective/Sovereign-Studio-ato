from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
import zipfile
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse
from pathlib import Path, PurePosixPath
from typing import Any

import requests

from policy import (
    BLOCKED_PARTS,
    MAX_FILE_BYTES,
    safe_repo_path,
    sha256_bytes,
    validate_branch,
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

    def _record_check(self, workspace_id: str, key: str, result: dict[str, Any]) -> None:
        metadata = self._read_metadata(workspace_id)
        metadata.setdefault("checks", {})[key] = {
            "ok": bool(result.get("ok")),
            "exit_code": result.get("exit_code"),
            "duration_ms": result.get("duration_ms"),
            "at": int(time.time()),
        }
        self._write_metadata(workspace_id, metadata)

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
        try:
            completed = subprocess.run(
                argv,
                cwd=str(cwd),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout or self.config.command_timeout,
                check=False,
            )
            exit_code = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
        except FileNotFoundError as exc:
            exit_code = 127
            stdout = ""
            stderr = str(exc)
        except subprocess.TimeoutExpired as exc:
            exit_code = 124
            stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            stderr = ((exc.stderr or "") if isinstance(exc.stderr, str) else "") + "\nCommand timed out."
        output_limit = 24_000
        return {
            "argv": argv,
            "exit_code": exit_code,
            "stdout": stdout[-output_limit:],
            "stderr": stderr[-output_limit:],
            "duration_ms": int((time.monotonic() - started) * 1000),
            "ok": exit_code == 0,
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

    @staticmethod
    def _code_server_public_url(value: str) -> str:
        candidate = value.strip().rstrip("/")
        if not candidate:
            raise RuntimeError("SOVEREIGN_CODE_SERVER_PUBLIC_URL ist nicht konfiguriert")
        parsed = urlparse(candidate)
        local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if parsed.scheme not in ({"http", "https"} if local else {"https"}):
            raise ValueError("Code-Server-URL muss außerhalb localhost HTTPS verwenden")
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Code-Server-URL enthält nicht erlaubte Bestandteile")
        return candidate

    def code_server_workspace_descriptor(
        self,
        workspace_id: str,
        *,
        sdcard_enabled: bool = False,
        sdcard_marker_sha256: str = "",
        public_base_url: str = "",
    ) -> dict[str, Any]:
        repo = self._repo(workspace_id)
        metadata = self._read_metadata(workspace_id)
        public_url = self._code_server_public_url(
            public_base_url
            or os.getenv("SOVEREIGN_CODE_SERVER_PUBLIC_URL", "").strip()
            or "http://127.0.0.1:32782"
        )
        editor_path = f"/config/sovereign-workspaces/{workspace_id}/repo"
        marker = sdcard_marker_sha256.strip().lower()
        if sdcard_enabled and not re.fullmatch(r"[0-9a-f]{64}", marker):
            raise ValueError("Aktivierter SD-Karten-Mirror benötigt einen bestätigten SHA-256-Marker")
        storage = {
            "mode": "android_external_storage_mirror" if sdcard_enabled else "server_workspace",
            "sdcardEnabled": bool(sdcard_enabled),
            "directRemoteMountClaimed": False,
            "nativeBridgeRequired": bool(sdcard_enabled),
            "syncMarkerSha256": marker if sdcard_enabled else None,
            "truthBoundary": (
                "External storage is a user-enabled native sync mirror; the VPS never claims direct Android SD-card access."
                if sdcard_enabled
                else "The editor works directly on the isolated server workspace."
            ),
        }
        return {
            "ok": True,
            "status": "CODE_SERVER_WORKSPACE_DESCRIPTOR_READY",
            "workspaceId": workspace_id,
            "repository": metadata.get("repository"),
            "branch": metadata.get("branch"),
            "hostRepoPath": str(repo),
            "editorFolder": editor_path,
            "openUrl": f"{public_url}/?{urlencode({'folder': editor_path})}",
            "storage": storage,
            "credentialsReturned": False,
            "arbitraryHostPathAccepted": False,
            "publicUrlSource": "tool_argument" if public_base_url else "configured_or_loopback_default",
        }

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
        limit = max(1, min(max_results, 200))
        results: list[dict[str, Any]] = []
        if start.is_file():
            candidates = [start]
        else:
            candidates = []
            for current_root, directories, filenames in os.walk(start):
                directories[:] = [name for name in directories if name not in BLOCKED_PARTS and not name.startswith(".env")]
                root_path = Path(current_root)
                candidates.extend(root_path / filename for filename in filenames)
        for candidate in candidates:
            if len(results) >= limit:
                break
            try:
                if candidate.stat().st_size > MAX_FILE_BYTES or candidate.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip", ".jar"}:
                    continue
                text = candidate.read_text("utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                if query in line:
                    results.append({"path": str(candidate.relative_to(repo)), "line": line_no, "text": line[:500]})
                    if len(results) >= limit:
                        break
        return {"query": query, "results": results, "truncated": len(results) >= limit}

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

    def install_dependencies(self, workspace_id: str) -> dict[str, Any]:
        """Refuse Node dependency installation inside the lightweight MCP runtime."""
        self._repo(workspace_id)
        result = {
            "ok": False,
            "status": "REMOTE_CI_REQUIRED",
            "failure_family": "LOCAL_DEPENDENCY_INSTALL_FORBIDDEN",
            "workspace_id": workspace_id,
            "execution_mode": "github_actions",
            "local_process_started": False,
            "blocker": (
                "pnpm install is intentionally disabled in the running MCP container; "
                "dependency resolution and Node builds run only on GitHub Actions runners"
            ),
            "next_action": "publish_workspace_branch_then_use_pr_ci_or_android_standard_validation",
        }
        self._record_check(workspace_id, "dependencies:delegated_to_ci", result)
        return result

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def import_workflow_artifact(
        self,
        workspace_id: str,
        run_id: int,
        artifact_id: int,
        destination: str = ".sovereign-artifacts/android",
    ) -> dict[str, Any]:
        """Download one GitHub Actions artifact into the workspace without exposing credentials."""
        run_number = int(run_id)
        artifact_number = int(artifact_id)
        if run_number < 1 or artifact_number < 1:
            raise ValueError("run_id und artifact_id müssen positiv sein")
        repo = self._repo(workspace_id)
        destination_path = Path(destination)
        if not destination_path.parts or destination_path.parts[0] != ".sovereign-artifacts":
            raise ValueError("Artifact-Ziel muss unter .sovereign-artifacts liegen")
        final_relative = str(destination_path / f"run-{run_number}-artifact-{artifact_number}")
        final_root = safe_repo_path(repo, final_relative, must_exist=False)
        exclude_path = repo / ".git" / "info" / "exclude"
        exclude_marker = "/.sovereign-artifacts/"
        exclude_text = exclude_path.read_text("utf-8") if exclude_path.is_file() else ""
        if exclude_marker not in exclude_text.splitlines():
            exclude_path.parent.mkdir(parents=True, exist_ok=True)
            with exclude_path.open("a", encoding="utf-8") as exclude_file:
                if exclude_text and not exclude_text.endswith("\n"):
                    exclude_file.write("\n")
                exclude_file.write(exclude_marker + "\n")
        headers = {
            "Authorization": f"Bearer {self.config.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        metadata_url = (
            f"https://api.github.com/repos/{self.config.repository}/actions/artifacts/{artifact_number}"
        )
        metadata_response = requests.get(metadata_url, headers=headers, timeout=30)
        if metadata_response.status_code != 200:
            raise RuntimeError(
                f"Artifact-Metadaten konnten nicht gelesen werden: HTTP {metadata_response.status_code}"
            )
        metadata = metadata_response.json()
        workflow_run = metadata.get("workflow_run") if isinstance(metadata, dict) else None
        actual_run_id = int((workflow_run or {}).get("id") or 0)
        if actual_run_id != run_number:
            raise ValueError("Artifact gehört nicht zum bestätigten Workflow-Run")
        if bool(metadata.get("expired")):
            raise RuntimeError("GitHub-Artefakt ist abgelaufen")
        archive_url = str(metadata.get("archive_download_url") or "").strip()
        if not archive_url:
            raise RuntimeError("GitHub lieferte keine Artifact-Download-URL")

        archive_limit = 600 * 1024 * 1024
        extract_limit = 1_200 * 1024 * 1024
        workspace = self._workspace(workspace_id)
        archive_path = workspace / f"artifact-{artifact_number}.zip.part"
        response = requests.get(
            archive_url,
            headers=headers,
            stream=True,
            allow_redirects=True,
            timeout=120,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Artifact-Download fehlgeschlagen: HTTP {response.status_code}")
        downloaded = 0
        try:
            with archive_path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    downloaded += len(chunk)
                    if downloaded > archive_limit:
                        raise ValueError("Artifact-Archiv überschreitet das Größenlimit")
                    handle.write(chunk)

            extracted: list[dict[str, Any]] = []
            seen: set[str] = set()
            total_uncompressed = 0
            final_root.mkdir(parents=True, exist_ok=False)
            with zipfile.ZipFile(archive_path) as archive:
                for info in archive.infolist():
                    member = PurePosixPath(info.filename)
                    if info.is_dir():
                        continue
                    if member.is_absolute() or not member.parts or ".." in member.parts:
                        raise ValueError("Artifact enthält einen unsicheren Pfad")
                    if info.flag_bits & 0x1:
                        raise ValueError("Verschlüsselte Artifact-Dateien sind nicht zulässig")
                    mode = (info.external_attr >> 16) & 0o170000
                    if mode == 0o120000:
                        raise ValueError("Symlinks in Workflow-Artefakten sind nicht zulässig")
                    member_name = member.as_posix()
                    if member_name in seen:
                        raise ValueError("Artifact enthält doppelte Dateipfade")
                    seen.add(member_name)
                    total_uncompressed += int(info.file_size)
                    if total_uncompressed > extract_limit:
                        raise ValueError("Entpacktes Artifact überschreitet das Größenlimit")
                    relative_target = str(Path(final_relative) / Path(*member.parts))
                    target = safe_repo_path(repo, relative_target)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output, length=1024 * 1024)
                    extracted.append(
                        {
                            "path": str(target.relative_to(repo)),
                            "bytes": target.stat().st_size,
                            "sha256": self._sha256_file(target),
                        }
                    )
        except Exception:
            shutil.rmtree(final_root, ignore_errors=True)
            raise
        finally:
            archive_path.unlink(missing_ok=True)

        inspectable = [
            item for item in extracted if Path(str(item["path"])).suffix.lower() in {".apk", ".aab"}
        ]
        return {
            "ok": bool(inspectable),
            "status": "IMPORTED" if inspectable else "INCOMPLETE_EVIDENCE",
            "workspace_id": workspace_id,
            "run_id": run_number,
            "artifact_id": artifact_number,
            "artifact_name": str(metadata.get("name") or ""),
            "downloaded_bytes": downloaded,
            "files": extracted,
            "inspectable_artifacts": inspectable,
            "next_action": (
                "run_android_artifact_inspect_for_each_inspectable_path"
                if inspectable
                else "select_an_artifact_containing_apk_or_aab"
            ),
        }

    def run_check(self, workspace_id: str, check: str, target: str = "") -> dict[str, Any]:
        repo = self._repo(workspace_id)
        remote_node_checks = {"typecheck", "audit", "build_web", "vitest"}
        if check in remote_node_checks:
            if check == "vitest":
                test_path = safe_repo_path(repo, target, must_exist=True)
                key = f"vitest:{test_path.relative_to(repo)}"
            else:
                key = check
            result = {
                "ok": False,
                "status": "REMOTE_CI_REQUIRED",
                "failure_family": "LOCAL_NODE_EXECUTION_FORBIDDEN",
                "check": check,
                "execution_mode": "github_actions",
                "local_process_started": False,
                "blocker": "Node dependency checks are not executed in the running MCP container",
                "next_action": "publish_workspace_branch_and_read_github_actions_check_evidence",
            }
            self._record_check(workspace_id, key, result)
            return result

        allowed: dict[str, list[str]] = {
            "git_diff_check": ["git", "diff", "--check"],
            "backend_compile": ["python3", "-m", "py_compile", "scripts/sovereign-backend/app.py"],
        }
        key = check
        if check == "pytest":
            test_path = safe_repo_path(repo, target, must_exist=True)
            relative = str(test_path.relative_to(repo))
            command = ["python3", "-m", "pytest", relative, "-q"]
            key = f"pytest:{relative}"
        elif check in allowed:
            command = allowed[check]
        else:
            raise ValueError("Check ist nicht freigegeben")
        result = self._run(command, cwd=repo)
        self._record_check(workspace_id, key, result)
        return result

    def _changed_files(self, repo: Path) -> list[str]:
        result = self._run(["git", "status", "--porcelain"], cwd=repo)
        files: list[str] = []
        for line in result["stdout"].splitlines():
            if len(line) >= 4:
                path = line[3:].strip()
                if " -> " in path:
                    path = path.split(" -> ", 1)[1]
                files.append(path)
        return list(dict.fromkeys(files))

    @staticmethod
    def _has_successful_check(checks: dict[str, Any], prefix: str) -> bool:
        return any(key.startswith(prefix) and bool(value.get("ok")) for key, value in checks.items() if isinstance(value, dict))

    def create_draft_pr(self, workspace_id: str, *, title: str, body: str, commit_message: str) -> dict[str, Any]:
        if not title.strip() or not commit_message.strip():
            raise ValueError("PR-Titel und Commit-Nachricht dürfen nicht leer sein")
        repo = self._repo(workspace_id)
        metadata = self._read_metadata(workspace_id)
        branch = validate_branch(metadata["branch"])
        changed = self._changed_files(repo)
        if not changed:
            raise ValueError("Keine Änderungen vorhanden")

        diff_check = self.run_check(workspace_id, "git_diff_check")
        if not diff_check["ok"]:
            raise RuntimeError("git diff --check ist fehlgeschlagen")

        python_files = [path for path in changed if path.endswith(".py")]
        if python_files:
            compile_paths = [str(safe_repo_path(repo, path, must_exist=True).relative_to(repo)) for path in python_files]
            compile_result = self._run(["python3", "-m", "py_compile", *compile_paths], cwd=repo)
            self._record_check(workspace_id, "backend_compile:auto", compile_result)
            if not compile_result["ok"]:
                raise RuntimeError("Python-Compile-Check ist fehlgeschlagen")
            checks = self._read_metadata(workspace_id).get("checks", {})
            if not self._has_successful_check(checks, "pytest:"):
                raise RuntimeError("Pythonänderungen benötigen mindestens einen erfolgreichen gezielten Pytest-Lauf")

        frontend_files = [path for path in changed if path.endswith((".ts", ".tsx", ".js", ".jsx", ".css"))]
        if frontend_files:
            metadata = self._read_metadata(workspace_id)
            metadata["remote_validation"] = {
                "required": True,
                "execution_mode": "github_actions",
                "reason": "frontend_or_node_change",
                "required_checks": ["typecheck", "unit_tests", "web_build"],
                "local_dependency_install_allowed": False,
            }
            self._write_metadata(workspace_id, metadata)

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
        headers = {"Authorization": f"Bearer {self.config.github_token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10"}
        response = requests.post(
            f"https://api.github.com/repos/{self.config.repository}/pulls",
            headers=headers,
            timeout=30,
            json={"title": title[:256], "head": f"{owner}:{branch}", "base": metadata["base_branch"], "body": body, "draft": True},
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Draft-PR konnte nicht erstellt werden: HTTP {response.status_code} {response.text[:1000]}")
        payload = response.json()
        metadata = self._read_metadata(workspace_id)
        metadata["draft_pr"] = {"number": payload["number"], "url": payload["html_url"], "head_sha": payload["head"]["sha"]}
        self._write_metadata(workspace_id, metadata)
        return {
            "draft": True,
            "number": payload["number"],
            "url": payload["html_url"],
            "branch": branch,
            "changed_files": changed,
            "checks": metadata.get("checks", {}),
            "remote_validation": metadata.get("remote_validation", {"required": False}),
        }
