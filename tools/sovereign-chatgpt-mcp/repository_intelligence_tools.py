from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import difflib
import fnmatch
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import subprocess
import time
from typing import Any, Final

import yaml
from mcp.types import ToolAnnotations


READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WORKSPACE_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
TRACKED_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)

_RUNTIME: Any = None
_REGISTERED = False

_MAX_TRACKED_FILES: Final[int] = 30_000
_MAX_INDEX_FILES: Final[int] = 12_000
_MAX_TEXT_BYTES: Final[int] = 800_000
_MAX_RESULT_ITEMS: Final[int] = 50
_VECTOR_DIMENSIONS: Final[int] = 64
_SHA = re.compile(r"^[0-9a-f]{40,64}$")
_IMAGE_DIGEST = re.compile(r"(?:^|@)sha256:[0-9a-f]{64}$")
_ALLOWED_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,159}$")
_ALLOWED_SUBJECT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/ -]{0,127}$")
_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_.:/-]{1,127}")
_SECRET_MARKER = re.compile(
    r"(?:sk-(?:proj-)?[A-Za-z0-9_-]{12,}|github_pat_[A-Za-z0-9_]+|"
    r"gh[pousr]_[A-Za-z0-9_]{20,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|"
    r"Authorization\s*:\s*(?:Bearer\s+)?\S+|(?:api[_-]?key|token|password|secret)\s*[:=]\s*['\"]?[^\s'\"]{12,})",
    re.IGNORECASE,
)
_TEXT_SUFFIXES: Final[frozenset[str]] = frozenset({
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".java", ".kt", ".kts", ".go", ".rs", ".cs", ".c", ".h",
    ".cpp", ".hpp", ".rb", ".php", ".scala", ".swift", ".sql",
    ".graphql", ".sh", ".yml", ".yaml", ".json", ".toml", ".xml",
    ".md", ".css", ".scss", ".txt",
})
_SKIP_PREFIXES: Final[tuple[str, ...]] = (
    ".git/", "node_modules/", "vendor/", "dist/", "build/", "coverage/",
    "target/", ".gradle/", ".next/", ".venv/", "venv/", "__pycache__/",
    "playwright-report/", "test-results/", "android/app/build/", "android/.gradle/",
)
_TOOLCHAIN_COMMANDS: Final[dict[str, tuple[str, ...]]] = {
    "git": ("git", "--version"),
    "python": ("python", "--version"),
    "node": ("node", "--version"),
    "pnpm": ("pnpm", "--version"),
    "docker": ("docker", "--version"),
    "docker-compose": ("docker", "compose", "version", "--short"),
    "psql": ("psql", "--version"),
}
_SCOPABLE_TOOLS: Final[frozenset[str]] = frozenset({
    "repository_intelligence_index_build",
    "repository_hash_bound_replace",
    "repository_hash_bound_restore",
    "deployment_evidence_session_capture",
})


class _DuplicateKeyError(ValueError):
    pass


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: yaml.nodes.MappingNode, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise _DuplicateKeyError(f"duplicate key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _git(repo: Path, *args: str, timeout: int = 90) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    return completed.stdout.strip()


def _git_bytes(repo: Path, *args: str, timeout: int = 90) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    return completed.stdout


def _repo(workspace_id: str) -> Path:
    if _RUNTIME is None:
        raise RuntimeError("Repository intelligence tools are not registered")
    return Path(_RUNTIME._repo(workspace_id)).resolve()


def _git_dir(repo: Path) -> Path:
    raw = _git(repo, "rev-parse", "--git-dir")
    path = Path(raw)
    if not path.is_absolute():
        path = repo / path
    return path.resolve()


def _validate_sha(value: str, *, field: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _SHA.fullmatch(normalized):
        raise ValueError(f"{field} must be a full hexadecimal Git object id")
    return normalized


def _require_head(repo: Path, expected_repo_sha: str) -> str:
    expected = _validate_sha(expected_repo_sha, field="expected_repo_sha")
    actual = _git(repo, "rev-parse", "HEAD").lower()
    if actual != expected:
        raise ValueError(f"repository head mismatch: expected {expected}, actual {actual}")
    return actual


def _validate_ref(value: str) -> str:
    ref = str(value or "").strip()
    if not _ALLOWED_REF.fullmatch(ref) or ".." in ref or ref.startswith("/"):
        raise ValueError("source_ref is invalid")
    return ref


def _normalize_relative_path(value: str, *, allow_git_namespace: bool = False) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    if allow_git_namespace and raw.startswith("@git/"):
        tail = raw.removeprefix("@git/")
        if not tail or ".." in PurePosixPath(tail).parts:
            raise ValueError("capability path is invalid")
        return "@git/" + str(PurePosixPath(tail))
    pure = PurePosixPath(raw)
    if not raw or pure.is_absolute() or ".." in pure.parts or raw.startswith(".git/"):
        raise ValueError("repository path must be relative, remain inside the repository, and not target .git")
    return str(pure)


def _safe_file(repo: Path, relative: str, *, must_exist: bool = True) -> Path:
    normalized = _normalize_relative_path(relative)
    candidate = (repo / normalized).resolve(strict=False)
    try:
        candidate.relative_to(repo)
    except ValueError as exc:
        raise ValueError("repository path escapes the workspace") from exc
    if must_exist and not candidate.is_file():
        raise ValueError("repository path is not an existing regular file")
    if candidate.exists() and candidate.is_symlink():
        raise ValueError("symbolic-link targets are not allowed")
    return candidate


def _tracked_files(repo: Path) -> list[str]:
    files = [line for line in _git(repo, "ls-files").splitlines() if line]
    if len(files) > _MAX_TRACKED_FILES:
        raise ValueError("repository exceeds the bounded tracked-file limit")
    return files


def _language(path: str) -> str:
    suffix = PurePosixPath(path).suffix.casefold()
    return {
        ".py": "python", ".pyi": "python", ".ts": "typescript", ".tsx": "typescript-react",
        ".js": "javascript", ".jsx": "javascript-react", ".mjs": "javascript", ".cjs": "javascript",
        ".java": "java", ".kt": "kotlin", ".kts": "kotlin", ".go": "go", ".rs": "rust",
        ".cs": "csharp", ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp",
        ".sql": "sql", ".yml": "yaml", ".yaml": "yaml", ".json": "json", ".md": "markdown",
        ".sh": "shell", ".toml": "toml", ".xml": "xml",
    }.get(suffix, suffix.removeprefix(".") or "text")


def _redact_text(text: str) -> tuple[str, int]:
    output: list[str] = []
    redactions = 0
    for line in text.splitlines():
        if _SECRET_MARKER.search(line):
            output.append("<redacted-secret-line>")
            redactions += 1
        else:
            output.append(line)
    return "\n".join(output), redactions


def _tokens(text: str) -> list[str]:
    return [match.group(0).casefold() for match in _TOKEN.finditer(text)][:20_000]


def _local_embedding(text: str) -> list[float]:
    counts: Counter[int] = Counter()
    for token in _tokens(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=9, person=b"sov-ri-v1").digest()
        index = int.from_bytes(digest[:8], "big") % _VECTOR_DIMENSIONS
        sign = 1 if digest[8] & 1 else -1
        counts[index] += sign
    vector = [float(counts.get(index, 0)) for index in range(_VECTOR_DIMENSIONS)]
    norm = math.sqrt(sum(item * item for item in vector))
    if norm:
        vector = [item / norm for item in vector]
    return vector


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def _index_path(repo: Path) -> Path:
    return _git_dir(repo) / "sovereign-repository-intelligence" / "index.sqlite3"


def _scope_root(repo: Path) -> Path:
    return _git_dir(repo) / "sovereign-capability-scopes"


def _evidence_root(repo: Path) -> Path:
    return _git_dir(repo) / "sovereign-evidence" / "deployment"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _scope_body(manifest: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in manifest.items() if key != "scopeId"}


def _load_scope(
    repo: Path,
    scope_id: str,
    *,
    tool: str,
    effect: str,
    path: str,
    current_head: str,
) -> dict[str, Any]:
    normalized_id = str(scope_id or "").strip().lower()
    if not normalized_id.startswith("sha256:") or not re.fullmatch(r"sha256:[0-9a-f]{64}", normalized_id):
        raise ValueError("capability_scope_id must be a sha256 scope id")
    scope_path = _scope_root(repo) / f"{normalized_id.removeprefix('sha256:')}.json"
    if not scope_path.is_file():
        raise ValueError("capability scope does not exist in this workspace")
    manifest = json.loads(scope_path.read_text("utf-8"))
    canonical = _canonical_json(_scope_body(manifest))
    actual_id = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if actual_id != normalized_id or manifest.get("scopeId") != normalized_id:
        raise ValueError("capability scope integrity check failed")
    if manifest.get("boundRepoSha") != current_head:
        raise ValueError("capability scope is bound to a different repository revision")
    expires = int(manifest.get("expiresAtEpoch") or 0)
    if expires and int(time.time()) > expires:
        raise ValueError("capability scope has expired")
    if tool not in manifest.get("allowedTools", []):
        raise ValueError("capability scope does not allow this tool")
    if effect not in manifest.get("allowedEffects", []):
        raise ValueError("capability scope does not allow this effect")
    allowed_paths = manifest.get("allowedPaths", [])
    if not any(fnmatch.fnmatchcase(path, pattern) for pattern in allowed_paths):
        raise ValueError("capability scope does not allow the target path")
    return manifest


def _file_blob_sha(repo: Path, path: str) -> str:
    return _git(repo, "hash-object", "--", path).lower()


def _atomic_write(path: Path, data: bytes, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    if mode is not None:
        os.chmod(temporary, mode)
    os.replace(temporary, path)


def _bounded_diff(path: str, before: str, after: str) -> str:
    lines = list(difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
        n=3,
    ))
    rendered = "\n".join(lines[:240])
    if len(lines) > 240:
        rendered += "\n... <diff truncated>"
    return rendered[:40_000]


def _run_local(command: list[str], *, timeout: int = 15) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        return {"ok": False, "status": "UNAVAILABLE", "error": type(exc).__name__}
    output = (completed.stdout or completed.stderr or "").strip().splitlines()
    return {
        "ok": completed.returncode == 0,
        "status": "VERIFIED" if completed.returncode == 0 else "COMMAND_FAILED",
        "exitCode": completed.returncode,
        "output": output[0][:300] if output else "",
    }


def _toolchain_snapshot(names: list[str] | None = None) -> dict[str, Any]:
    selected = names or list(_TOOLCHAIN_COMMANDS)
    invalid = sorted(set(selected) - set(_TOOLCHAIN_COMMANDS))
    if invalid:
        raise ValueError(f"unsupported toolchain names: {', '.join(invalid)}")
    tools: list[dict[str, Any]] = []
    for name in selected:
        command = list(_TOOLCHAIN_COMMANDS[name])
        executable_name = command[0]
        executable = shutil.which(executable_name)
        result = _run_local(command)
        executable_sha256 = None
        if executable:
            candidate = Path(executable)
            try:
                if candidate.is_file() and candidate.stat().st_size <= 100_000_000:
                    executable_sha256 = hashlib.sha256(candidate.read_bytes()).hexdigest()
            except OSError:
                executable_sha256 = None
        tools.append({
            "name": name,
            "command": command,
            "available": executable is not None,
            "executable": executable,
            "executableSha256": executable_sha256,
            "versionStatus": result["status"],
            "version": result.get("output", ""),
            "exitCode": result.get("exitCode"),
        })
    return {
        "status": "TOOLCHAIN_VERIFIED" if all(item["available"] and item["versionStatus"] == "VERIFIED" for item in tools) else "TOOLCHAIN_PARTIAL",
        "tools": tools,
        "secretValuesReturned": False,
    }


def _docker_snapshot() -> dict[str, Any]:
    if shutil.which("docker") is None:
        return {
            "status": "DOCKER_UNAVAILABLE",
            "context": None,
            "containers": [],
            "composeProjects": [],
            "mcpRepoDigests": [],
            "secretValuesReturned": False,
        }
    context_result = _run_local(["docker", "context", "show"])
    version_result = _run_local(["docker", "version", "--format", "{{.Server.Version}}"])
    ps_result = _run_local(["docker", "ps", "--format", "{{json .}}"], timeout=25)
    containers: list[dict[str, Any]] = []
    if ps_result.get("ok"):
        completed = subprocess.run(
            ["docker", "ps", "--format", "{{json .}}"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=25,
            check=False,
        )
        for line in completed.stdout.splitlines()[:80]:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            containers.append({
                "id": str(row.get("ID") or "")[:24],
                "name": str(row.get("Names") or "")[:160],
                "image": str(row.get("Image") or "")[:300],
                "status": str(row.get("Status") or "")[:300],
            })
    compose_projects: list[dict[str, Any]] = []
    compose = _run_local(["docker", "compose", "ls", "--format", "json"], timeout=25)
    if compose.get("ok"):
        completed = subprocess.run(
            ["docker", "compose", "ls", "--format", "json"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=25,
            check=False,
        )
        try:
            rows = json.loads(completed.stdout or "[]")
        except json.JSONDecodeError:
            rows = []
        if isinstance(rows, list):
            for row in rows[:50]:
                if isinstance(row, dict):
                    compose_projects.append({
                        "name": str(row.get("Name") or row.get("name") or "")[:160],
                        "status": str(row.get("Status") or row.get("status") or "")[:300],
                        "configFiles": str(row.get("ConfigFiles") or row.get("configFiles") or "")[:500],
                    })
    mcp_digests: list[str] = []
    mcp_container = next((item for item in containers if item["name"] == "sovereign-chatgpt-mcp"), None)
    if mcp_container:
        image_ref = mcp_container["image"]
        completed = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", image_ref],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
        if completed.returncode == 0:
            try:
                values = json.loads(completed.stdout or "[]")
            except json.JSONDecodeError:
                values = []
            if isinstance(values, list):
                mcp_digests = sorted({str(item) for item in values if isinstance(item, str) and _IMAGE_DIGEST.search(item)})
    return {
        "status": "DOCKER_READBACK_READY" if version_result.get("ok") else "DOCKER_DAEMON_UNAVAILABLE",
        "context": context_result.get("output") if context_result.get("ok") else None,
        "serverVersion": version_result.get("output") if version_result.get("ok") else None,
        "containers": containers,
        "composeProjects": compose_projects,
        "mcpRepoDigests": mcp_digests,
        "secretValuesReturned": False,
    }


def _json_load_unique(text: str) -> Any:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise _DuplicateKeyError(f"duplicate key: {key!r}")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=hook)


def _schema_findings(path: str, value: Any) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not isinstance(value, dict):
        return findings
    lowered = path.casefold()
    if path.startswith(".github/workflows/"):
        if not isinstance(value.get("jobs"), dict) or not value.get("jobs"):
            findings.append({"severity": "P1", "family": "WORKFLOW_JOBS_MISSING", "path": path})
    if PurePosixPath(path).name.casefold() in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}:
        if not isinstance(value.get("services"), dict) or not value.get("services"):
            findings.append({"severity": "P1", "family": "COMPOSE_SERVICES_MISSING", "path": path})
    if isinstance(value.get("openapi"), str):
        schemas = (((value.get("components") or {}).get("schemas")) if isinstance(value.get("components"), dict) else {}) or {}
        if isinstance(schemas, dict):
            for name, schema in sorted(schemas.items()):
                if not isinstance(schema, dict):
                    continue
                if schema.get("type") == "object" and "properties" not in schema:
                    findings.append({
                        "severity": "P1",
                        "family": "OPENAPI_OBJECT_PROPERTIES_MISSING",
                        "path": path,
                        "schema": str(name)[:160],
                    })
                required = schema.get("required") or []
                properties = schema.get("properties") or {}
                if isinstance(required, list) and isinstance(properties, dict):
                    missing = sorted(str(item) for item in required if item not in properties)
                    if missing:
                        findings.append({
                            "severity": "P1",
                            "family": "OPENAPI_REQUIRED_PROPERTY_UNDECLARED",
                            "path": path,
                            "schema": str(name)[:160],
                            "missing": missing[:20],
                        })
    if "schema" in lowered and value.get("type") == "object" and "properties" not in value:
        findings.append({"severity": "P2", "family": "JSON_SCHEMA_OBJECT_PROPERTIES_MISSING", "path": path})
    return findings


def _diagnose_schemas(repo: Path, paths: list[str] | None = None) -> dict[str, Any]:
    selected = paths or [
        path for path in _tracked_files(repo)
        if PurePosixPath(path).suffix.casefold() in {".json", ".yml", ".yaml"}
        and not path.startswith(_SKIP_PREFIXES)
    ]
    if len(selected) > 300:
        selected = selected[:300]
        truncated = True
    else:
        truncated = False
    files: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for raw in selected:
        path = _normalize_relative_path(raw)
        candidate = _safe_file(repo, path, must_exist=True)
        if candidate.stat().st_size > _MAX_TEXT_BYTES:
            files.append({"path": path, "status": "SKIPPED_SIZE_LIMIT"})
            continue
        try:
            text = candidate.read_text("utf-8")
            if candidate.suffix.casefold() == ".json":
                value = _json_load_unique(text)
            else:
                value = yaml.load(text, Loader=_UniqueKeyLoader)
        except (UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError, _DuplicateKeyError, ValueError) as exc:
            family = "DUPLICATE_KEY" if isinstance(exc, _DuplicateKeyError) else "SCHEMA_PARSE_ERROR"
            findings.append({"severity": "P1", "family": family, "path": path, "detail": str(exc)[:240]})
            files.append({"path": path, "status": "INVALID"})
            continue
        file_findings = _schema_findings(path, value)
        findings.extend(file_findings)
        files.append({"path": path, "status": "VALID" if not file_findings else "VALID_WITH_FINDINGS"})
    findings.sort(key=lambda item: (item["severity"], item["family"], item["path"]))
    return {
        "status": "SCHEMA_DIAGNOSTICS_FINDINGS" if findings else "SCHEMA_DIAGNOSTICS_CLEAR",
        "filesInspected": len(files),
        "truncated": truncated,
        "files": files[:300],
        "findings": findings[:200],
        "truthNotice": "A clear parse and bounded contract scan is not proof that a workflow, deployment or API is live.",
        "secretValuesReturned": False,
    }


def repository_intelligence_tool_inventory() -> dict[str, Any]:
    """List the repository-intelligence, capability, patch, schema and evidence tools."""
    return {
        "ok": True,
        "status": "REPOSITORY_INTELLIGENCE_TOOLS_READY",
        "tools": [
            {"name": "repository_capability_scope_create", "mutates": True, "surface": "git-private-side-channel"},
            {"name": "repository_intelligence_index_build", "mutates": True, "surface": "git-private-side-channel"},
            {"name": "repository_intelligence_search", "mutates": False, "surface": "repository-index"},
            {"name": "repository_hash_bound_replace", "mutates": True, "surface": "tracked-file"},
            {"name": "repository_hash_bound_restore", "mutates": True, "surface": "tracked-file"},
            {"name": "managed_toolchain_verify", "mutates": False, "surface": "local-toolchain"},
            {"name": "repository_schema_diagnostics", "mutates": False, "surface": "tracked-config"},
            {"name": "deployment_evidence_session_capture", "mutates": True, "surface": "git-private-side-channel"},
            {"name": "sovereign_resource_explorer", "mutates": False, "surface": "repository-runtime-graph"},
            {"name": "repository_context_drift_watch", "mutates": False, "surface": "repository-runtime-readback"},
        ],
        "providerRoutes": [],
        "telemetryEnabled": False,
        "proprietaryBinaryDependency": False,
        "truthBoundary": "The index and deterministic local embedding are discovery side-channels. Git blobs, exact revisions and fresh runtime readbacks remain canonical evidence.",
    }


def repository_capability_scope_create(
    workspace_id: str,
    expected_repo_sha: str,
    subject: str,
    allowed_tools: list[str],
    allowed_paths: list[str],
    expires_at_epoch: int = 0,
    issued_at_epoch: int = 0,
) -> dict[str, Any]:
    """Create one hash-addressed, revision-bound capability scope in the workspace Git directory."""
    repo = _repo(workspace_id)
    head = _require_head(repo, expected_repo_sha)
    normalized_subject = " ".join(str(subject or "").split())
    if not _ALLOWED_SUBJECT.fullmatch(normalized_subject):
        raise ValueError("subject is invalid")
    tools = sorted(set(str(item).strip() for item in allowed_tools if str(item).strip()))
    invalid_tools = sorted(set(tools) - _SCOPABLE_TOOLS)
    if not tools or invalid_tools:
        raise ValueError(f"allowed_tools contains unsupported tools: {', '.join(invalid_tools)}")
    patterns = sorted(set(_normalize_relative_path(item, allow_git_namespace=True) for item in allowed_paths))
    if not patterns:
        raise ValueError("allowed_paths must contain at least one path or pattern")
    now = int(issued_at_epoch or time.time())
    expires = int(expires_at_epoch or 0)
    if expires and expires <= now:
        raise ValueError("expires_at_epoch must be later than issued_at_epoch")
    body = {
        "schemaVersion": "sovereign.capability-scope.v1",
        "subject": normalized_subject,
        "boundRepoSha": head,
        "allowedTools": tools,
        "allowedEffects": ["workspace-write"],
        "allowedPaths": patterns,
        "issuedAtEpoch": now,
        "expiresAtEpoch": expires,
        "telemetryAllowed": False,
        "providerRoutesAllowed": [],
    }
    canonical = _canonical_json(body)
    scope_id = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    manifest = {**body, "scopeId": scope_id}
    target = _scope_root(repo) / f"{scope_id.removeprefix('sha256:')}.json"
    _atomic_write(target, (_canonical_json(manifest) + "\n").encode("utf-8"), mode=0o600)
    return {
        "ok": True,
        "status": "CAPABILITY_SCOPE_CREATED",
        "scopeId": scope_id,
        "subject": normalized_subject,
        "boundRepoSha": head,
        "allowedTools": tools,
        "allowedPaths": patterns,
        "expiresAtEpoch": expires,
        "repositoryWritten": False,
        "gitPrivateSideChannelWritten": True,
        "ownerApprovalClaimed": False,
        "truthNotice": "Scope integrity and revision binding are verified here; owner approval remains enforced independently by the operating profile.",
    }


def repository_intelligence_index_build(
    workspace_id: str,
    expected_repo_sha: str,
    capability_scope_id: str,
    max_files: int = 5_000,
    max_bytes_per_file: int = 250_000,
    local_embedding_mode: str = "deterministic-token-hash-v1",
) -> dict[str, Any]:
    """Build a secret-redacted SQLite FTS5 and deterministic local-embedding index beside Git metadata."""
    repo = _repo(workspace_id)
    head = _require_head(repo, expected_repo_sha)
    index_path = _index_path(repo)
    scope = _load_scope(
        repo,
        capability_scope_id,
        tool="repository_intelligence_index_build",
        effect="workspace-write",
        path="@git/sovereign-repository-intelligence/index.sqlite3",
        current_head=head,
    )
    mode = str(local_embedding_mode or "").strip()
    if mode not in {"none", "deterministic-token-hash-v1"}:
        raise ValueError("local_embedding_mode must be none or deterministic-token-hash-v1")
    file_limit = max(1, min(int(max_files), _MAX_INDEX_FILES))
    byte_limit = max(1_000, min(int(max_bytes_per_file), _MAX_TEXT_BYTES))
    tracked = _tracked_files(repo)
    candidates = [
        path for path in tracked
        if PurePosixPath(path).suffix.casefold() in _TEXT_SUFFIXES
        and not path.startswith(_SKIP_PREFIXES)
    ]
    truncated = len(candidates) > file_limit
    candidates = candidates[:file_limit]
    index_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = index_path.with_suffix(".tmp.sqlite3")
    temporary.unlink(missing_ok=True)
    connection = sqlite3.connect(temporary)
    indexed = 0
    skipped = 0
    redactions = 0
    total_bytes = 0
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute(
            "CREATE TABLE documents (id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, git_blob_sha TEXT NOT NULL, "
            "content_sha256 TEXT NOT NULL, language TEXT NOT NULL, vector_json TEXT NOT NULL)"
        )
        connection.execute("CREATE VIRTUAL TABLE documents_fts USING fts5(path UNINDEXED, content, tokenize='unicode61')")
        for path in candidates:
            candidate = _safe_file(repo, path, must_exist=True)
            try:
                size = candidate.stat().st_size
                if size > byte_limit:
                    skipped += 1
                    continue
                text = candidate.read_text("utf-8")
            except (OSError, UnicodeDecodeError, ValueError):
                skipped += 1
                continue
            redacted, count = _redact_text(text)
            redactions += count
            blob_sha = _file_blob_sha(repo, path)
            content_sha = hashlib.sha256(redacted.encode("utf-8")).hexdigest()
            vector = _local_embedding(redacted) if mode != "none" else []
            cursor = connection.execute(
                "INSERT INTO documents(path, git_blob_sha, content_sha256, language, vector_json) VALUES (?, ?, ?, ?, ?)",
                (path, blob_sha, content_sha, _language(path), _canonical_json(vector)),
            )
            connection.execute(
                "INSERT INTO documents_fts(rowid, path, content) VALUES (?, ?, ?)",
                (cursor.lastrowid, path, redacted),
            )
            indexed += 1
            total_bytes += len(redacted.encode("utf-8"))
        metadata = {
            "schemaVersion": "sovereign.repository-intelligence-index.v1",
            "repoSha": head,
            "fileCount": str(indexed),
            "redactionCount": str(redactions),
            "localEmbeddingMode": mode,
            "vectorDimensions": str(_VECTOR_DIMENSIONS if mode != "none" else 0),
        }
        connection.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", sorted(metadata.items()))
        connection.commit()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise RuntimeError("SQLite integrity check failed")
    finally:
        connection.close()
    os.chmod(temporary, 0o600)
    os.replace(temporary, index_path)
    index_sha = hashlib.sha256(index_path.read_bytes()).hexdigest()
    return {
        "ok": True,
        "status": "REPOSITORY_INTELLIGENCE_INDEX_READY",
        "repoSha": head,
        "scopeId": scope["scopeId"],
        "subject": scope["subject"],
        "indexedFiles": indexed,
        "skippedFiles": skipped,
        "candidateFiles": len(candidates),
        "truncated": truncated,
        "indexedBytes": total_bytes,
        "secretLinesRedacted": redactions,
        "fts": "sqlite-fts5",
        "localEmbeddingMode": mode,
        "localEmbeddingDimensions": _VECTOR_DIMENSIONS if mode != "none" else 0,
        "neuralModelUsed": False,
        "indexSha256": index_sha,
        "repositoryWritten": False,
        "gitPrivateSideChannelWritten": True,
        "truthNotice": "Search acceleration is not canonical repository or runtime truth; every result remains bound to a Git blob and exact repository revision.",
    }


def repository_intelligence_search(
    workspace_id: str,
    query: str,
    expected_repo_sha: str,
    limit: int = 20,
    use_local_embedding: bool = True,
) -> dict[str, Any]:
    """Search the current revision-bound local FTS5 index and rank with deterministic local embeddings."""
    repo = _repo(workspace_id)
    head = _require_head(repo, expected_repo_sha)
    terms = _tokens(str(query or ""))[:24]
    if not terms:
        raise ValueError("query must contain at least one searchable token")
    index_path = _index_path(repo)
    if not index_path.is_file():
        raise ValueError("repository intelligence index is missing")
    connection = sqlite3.connect(f"file:{index_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        metadata = {row["key"]: row["value"] for row in connection.execute("SELECT key, value FROM metadata")}
        if metadata.get("repoSha") != head:
            raise ValueError("repository intelligence index is stale for the current revision")
        expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
        rows = list(connection.execute(
            "SELECT d.path, d.git_blob_sha, d.content_sha256, d.language, d.vector_json, "
            "bm25(documents_fts) AS lexical_rank, snippet(documents_fts, 1, '[', ']', ' … ', 18) AS snippet "
            "FROM documents_fts JOIN documents d ON d.id = documents_fts.rowid "
            "WHERE documents_fts MATCH ? ORDER BY lexical_rank LIMIT ?",
            (expression, min(max(int(limit) * 4, 20), 200)),
        ))
        query_vector = _local_embedding(" ".join(terms)) if use_local_embedding else []
        results: list[dict[str, Any]] = []
        for row in rows:
            lexical_rank = float(row["lexical_rank"] or 0.0)
            lexical_score = 1.0 / (1.0 + max(0.0, lexical_rank))
            vector = json.loads(row["vector_json"] or "[]")
            semantic_score = max(0.0, _cosine(query_vector, vector)) if query_vector and vector else 0.0
            score = lexical_score * (0.7 if query_vector else 1.0) + semantic_score * (0.3 if query_vector else 0.0)
            results.append({
                "path": row["path"],
                "gitBlobSha": row["git_blob_sha"],
                "contentSha256": row["content_sha256"],
                "language": row["language"],
                "lexicalScore": round(lexical_score, 8),
                "localEmbeddingScore": round(semantic_score, 8),
                "combinedScore": round(score, 8),
                "snippet": str(row["snippet"] or "")[:800],
            })
        results.sort(key=lambda item: (-item["combinedScore"], item["path"]))
        bounded = results[:max(1, min(int(limit), _MAX_RESULT_ITEMS))]
    finally:
        connection.close()
    return {
        "ok": True,
        "status": "REPOSITORY_INTELLIGENCE_SEARCH_READY",
        "repoSha": head,
        "queryTokens": terms,
        "resultCount": len(bounded),
        "results": bounded,
        "indexSha256": hashlib.sha256(index_path.read_bytes()).hexdigest(),
        "neuralModelUsed": False,
        "repositoryWritten": False,
        "secretValuesReturned": False,
        "truthNotice": "Results are discovery candidates. Read the returned blob at the bound revision before treating a match as evidence.",
    }


def repository_hash_bound_replace(
    workspace_id: str,
    path: str,
    expected_repo_sha: str,
    expected_blob_sha: str,
    search_text: str,
    replacement_text: str,
    capability_scope_id: str,
    expected_occurrences: int = 1,
) -> dict[str, Any]:
    """Apply one exact search/replace only when repository, blob, scope and occurrence counts all match."""
    repo = _repo(workspace_id)
    head = _require_head(repo, expected_repo_sha)
    normalized_path = _normalize_relative_path(path)
    scope = _load_scope(
        repo,
        capability_scope_id,
        tool="repository_hash_bound_replace",
        effect="workspace-write",
        path=normalized_path,
        current_head=head,
    )
    target = _safe_file(repo, normalized_path, must_exist=True)
    expected_blob = _validate_sha(expected_blob_sha, field="expected_blob_sha")
    before_blob = _file_blob_sha(repo, normalized_path)
    if before_blob != expected_blob:
        raise ValueError(f"blob mismatch: expected {expected_blob}, actual {before_blob}")
    if not search_text or len(search_text) > 200_000 or len(replacement_text) > 400_000:
        raise ValueError("search_text and replacement_text exceed bounded patch limits")
    if _SECRET_MARKER.search(search_text) or _SECRET_MARKER.search(replacement_text):
        raise ValueError("patch arguments contain a secret-like marker")
    before = target.read_text("utf-8")
    occurrences = before.count(search_text)
    required = max(1, min(int(expected_occurrences), 100))
    if occurrences != required:
        raise ValueError(f"search occurrence mismatch: expected {required}, actual {occurrences}")
    after = before.replace(search_text, replacement_text, required)
    mode = stat.S_IMODE(target.stat().st_mode)
    _atomic_write(target, after.encode("utf-8"), mode=mode)
    after_blob = _file_blob_sha(repo, normalized_path)
    return {
        "ok": True,
        "status": "HASH_BOUND_REPLACE_APPLIED",
        "repoSha": head,
        "path": normalized_path,
        "scopeId": scope["scopeId"],
        "subject": scope["subject"],
        "beforeBlobSha": before_blob,
        "afterBlobSha": after_blob,
        "beforeSha256": hashlib.sha256(before.encode("utf-8")).hexdigest(),
        "afterSha256": hashlib.sha256(after.encode("utf-8")).hexdigest(),
        "occurrencesReplaced": required,
        "diff": _bounded_diff(normalized_path, before, after),
        "repositoryWritten": True,
        "committed": False,
        "truthNotice": "The working-tree write is proven by post-write hashing; commit, CI, deployment and runtime success remain separate gates.",
    }


def repository_hash_bound_restore(
    workspace_id: str,
    path: str,
    expected_repo_sha: str,
    expected_current_blob_sha: str,
    source_ref: str,
    expected_source_blob_sha: str,
    capability_scope_id: str,
) -> dict[str, Any]:
    """Restore one file from an exact Git ref only when current and source blob identities are both confirmed."""
    repo = _repo(workspace_id)
    head = _require_head(repo, expected_repo_sha)
    normalized_path = _normalize_relative_path(path)
    scope = _load_scope(
        repo,
        capability_scope_id,
        tool="repository_hash_bound_restore",
        effect="workspace-write",
        path=normalized_path,
        current_head=head,
    )
    target = _safe_file(repo, normalized_path, must_exist=True)
    current_expected = _validate_sha(expected_current_blob_sha, field="expected_current_blob_sha")
    current_blob = _file_blob_sha(repo, normalized_path)
    if current_blob != current_expected:
        raise ValueError(f"current blob mismatch: expected {current_expected}, actual {current_blob}")
    ref = _validate_ref(source_ref)
    source_expected = _validate_sha(expected_source_blob_sha, field="expected_source_blob_sha")
    source_blob = _git(repo, "rev-parse", f"{ref}:{normalized_path}").lower()
    if source_blob != source_expected:
        raise ValueError(f"source blob mismatch: expected {source_expected}, actual {source_blob}")
    before = target.read_text("utf-8")
    source_bytes = _git_bytes(repo, "show", f"{ref}:{normalized_path}")
    source_text = source_bytes.decode("utf-8")
    mode = stat.S_IMODE(target.stat().st_mode)
    _atomic_write(target, source_bytes, mode=mode)
    restored_blob = _file_blob_sha(repo, normalized_path)
    if restored_blob != source_blob:
        raise RuntimeError("post-restore blob readback does not match the source blob")
    return {
        "ok": True,
        "status": "HASH_BOUND_RESTORE_APPLIED",
        "repoSha": head,
        "path": normalized_path,
        "sourceRef": ref,
        "scopeId": scope["scopeId"],
        "subject": scope["subject"],
        "beforeBlobSha": current_blob,
        "restoredBlobSha": restored_blob,
        "diff": _bounded_diff(normalized_path, before, source_text),
        "repositoryWritten": True,
        "committed": False,
        "truthNotice": "The restored working-tree blob matches the confirmed source blob; later repository and runtime gates are not implied.",
    }


def managed_toolchain_verify(
    workspace_id: str,
    expected_repo_sha: str,
    tools: list[str] | None = None,
) -> dict[str, Any]:
    """Verify allowlisted local tool executables, versions and bounded executable digests."""
    repo = _repo(workspace_id)
    head = _require_head(repo, expected_repo_sha)
    snapshot = _toolchain_snapshot(tools)
    return {
        "ok": snapshot["status"] == "TOOLCHAIN_VERIFIED",
        "status": snapshot["status"],
        "repoSha": head,
        "tools": snapshot["tools"],
        "installationPerformed": False,
        "networkAccessPerformed": False,
        "secretValuesReturned": False,
        "truthNotice": "Executable presence and version output do not prove a daemon, account, registry or deployment is healthy.",
    }


def repository_schema_diagnostics(
    workspace_id: str,
    expected_repo_sha: str,
    paths: list[str] | None = None,
) -> dict[str, Any]:
    """Parse bounded YAML/JSON surfaces and report duplicate-key, OpenAPI, workflow and Compose contract findings."""
    repo = _repo(workspace_id)
    head = _require_head(repo, expected_repo_sha)
    result = _diagnose_schemas(repo, paths)
    return {"ok": not result["findings"], "repoSha": head, **result}


def deployment_evidence_session_capture(
    workspace_id: str,
    expected_repo_sha: str,
    capability_scope_id: str,
    expected_image_digest: str = "",
    include_docker: bool = True,
    session_label: str = "",
) -> dict[str, Any]:
    """Capture one revision-bound deployment evidence session into the workspace Git-private evidence area."""
    repo = _repo(workspace_id)
    head = _require_head(repo, expected_repo_sha)
    scope = _load_scope(
        repo,
        capability_scope_id,
        tool="deployment_evidence_session_capture",
        effect="workspace-write",
        path="@git/sovereign-evidence/deployment/session.json",
        current_head=head,
    )
    expected_digest = str(expected_image_digest or "").strip().lower()
    if expected_digest and not _IMAGE_DIGEST.search(expected_digest):
        raise ValueError("expected_image_digest must contain an immutable sha256 digest")
    label = " ".join(str(session_label or "").split())[:120]
    status_lines = [line for line in _git(repo, "status", "--short").splitlines() if line]
    schema = _diagnose_schemas(repo)
    docker = _docker_snapshot() if include_docker else {
        "status": "DOCKER_READBACK_NOT_REQUESTED", "context": None, "containers": [],
        "composeProjects": [], "mcpRepoDigests": [], "secretValuesReturned": False,
    }
    digest_match = None
    if expected_digest:
        digest_match = expected_digest in docker.get("mcpRepoDigests", [])
    evidence = {
        "schemaVersion": "sovereign.deployment-evidence-session.v1",
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "label": label,
        "repoSha": head,
        "branch": _git(repo, "branch", "--show-current"),
        "workingTreeDirty": bool(status_lines),
        "changedPathCount": len(status_lines),
        "changedPaths": [line[3:] if len(line) > 3 else line for line in status_lines[:200]],
        "expectedImageDigest": expected_digest or None,
        "imageDigestMatch": digest_match,
        "toolchain": _toolchain_snapshot(["git", "python", "node", "pnpm", "docker", "docker-compose"]),
        "schemaDiagnostics": {
            "status": schema["status"],
            "filesInspected": schema["filesInspected"],
            "findingCount": len(schema["findings"]),
            "truncated": schema["truncated"],
        },
        "docker": docker,
        "scopeId": scope["scopeId"],
        "subject": scope["subject"],
        "secretValuesReturned": False,
    }
    canonical = _canonical_json(evidence)
    session_id = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    payload = {**evidence, "sessionId": session_id}
    target = _evidence_root(repo) / f"{session_id.removeprefix('sha256:')}.json"
    _atomic_write(target, (_canonical_json(payload) + "\n").encode("utf-8"), mode=0o600)
    return {
        "ok": digest_match is not False,
        "status": "DEPLOYMENT_EVIDENCE_SESSION_CAPTURED" if digest_match is not False else "DEPLOYMENT_EVIDENCE_DIGEST_MISMATCH",
        "sessionId": session_id,
        "repoSha": head,
        "scopeId": scope["scopeId"],
        "evidence": payload,
        "evidenceSha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "repositoryWritten": False,
        "gitPrivateSideChannelWritten": True,
        "truthNotice": "This session records observed evidence and mismatches. It does not convert unavailable probes into success.",
    }


def sovereign_resource_explorer(
    workspace_id: str,
    expected_repo_sha: str,
    include_docker: bool = True,
) -> dict[str, Any]:
    """Build a bounded repository-to-runtime resource graph from current files and optional Docker readbacks."""
    repo = _repo(workspace_id)
    head = _require_head(repo, expected_repo_sha)
    tracked = _tracked_files(repo)
    workflows = sorted(path for path in tracked if path.startswith(".github/workflows/") and PurePosixPath(path).suffix in {".yml", ".yaml"})
    migrations = sorted(path for path in tracked if "/migrations/" in path and PurePosixPath(path).suffix.casefold() == ".sql")
    compose_files = sorted(path for path in tracked if PurePosixPath(path).name.casefold() in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"})
    docker = _docker_snapshot() if include_docker else {
        "status": "DOCKER_READBACK_NOT_REQUESTED", "context": None, "containers": [],
        "composeProjects": [], "mcpRepoDigests": [], "secretValuesReturned": False,
    }
    nodes: list[dict[str, Any]] = [
        {"id": "repo", "kind": "repository", "status": "READ", "evidence": {"headSha": head, "trackedFileCount": len(tracked)}},
        {"id": "ci", "kind": "ci-workflows", "status": "DISCOVERED", "evidence": {"count": len(workflows), "paths": workflows[:80]}},
        {"id": "compose", "kind": "compose-definitions", "status": "DISCOVERED", "evidence": {"count": len(compose_files), "paths": compose_files[:80]}},
        {"id": "database", "kind": "database-contract", "status": "DISCOVERED_NOT_QUERIED", "evidence": {"migrationCount": len(migrations), "paths": migrations[:80]}},
        {"id": "mcp", "kind": "mcp-runtime", "status": "DISCOVERED", "evidence": {"sourcePresent": "tools/sovereign-chatgpt-mcp/launcher.py" in tracked, "repoDigests": docker.get("mcpRepoDigests", [])}},
        {"id": "patchmon", "kind": "patchmon", "status": "DISCOVERED", "evidence": {"sourcePaths": [path for path in tracked if "patchmon" in path.casefold()][:80]}},
        {"id": "docker", "kind": "container-runtime", "status": docker["status"], "evidence": {"context": docker.get("context"), "containerCount": len(docker.get("containers", [])), "composeProjectCount": len(docker.get("composeProjects", []))}},
    ]
    for container in docker.get("containers", [])[:80]:
        nodes.append({"id": f"container:{container['name']}", "kind": "container", "status": container["status"], "evidence": {"image": container["image"], "id": container["id"]}})
    edges = [
        {"from": "repo", "to": "ci", "relation": "defines"},
        {"from": "repo", "to": "compose", "relation": "defines"},
        {"from": "repo", "to": "database", "relation": "declares-migrations"},
        {"from": "repo", "to": "mcp", "relation": "defines"},
        {"from": "repo", "to": "patchmon", "relation": "defines"},
        {"from": "compose", "to": "docker", "relation": "projects-onto"},
    ]
    for container in docker.get("containers", [])[:80]:
        edges.append({"from": "docker", "to": f"container:{container['name']}", "relation": "runs"})
        if container["name"] == "sovereign-chatgpt-mcp":
            edges.append({"from": "mcp", "to": f"container:{container['name']}", "relation": "runtime-instance"})
        if "patchmon" in container["name"].casefold():
            edges.append({"from": "patchmon", "to": f"container:{container['name']}", "relation": "runtime-instance"})
    return {
        "ok": True,
        "status": "RESOURCE_EXPLORER_READY",
        "repoSha": head,
        "nodes": nodes[:180],
        "edges": edges[:240],
        "dockerReadback": docker,
        "databaseRowsRead": False,
        "secretValuesReturned": False,
        "truthNotice": "DISCOVERED means a surface exists. Only nodes carrying fresh runtime evidence may be treated as live.",
    }


def repository_context_drift_watch(
    workspace_id: str,
    expected_repo_sha: str,
    expected_branch: str = "",
    expected_docker_context: str = "",
    expected_compose_projects: list[str] | None = None,
    expected_image_digest: str = "",
) -> dict[str, Any]:
    """Compare expected Git, Docker context, Compose projects and immutable MCP digest with fresh local readbacks."""
    repo = _repo(workspace_id)
    head = _require_head(repo, expected_repo_sha)
    branch = _git(repo, "branch", "--show-current")
    docker_expectation = bool(expected_docker_context or expected_compose_projects or expected_image_digest)
    docker = _docker_snapshot() if docker_expectation else {
        "status": "DOCKER_READBACK_NOT_REQUIRED", "context": None, "containers": [],
        "composeProjects": [], "mcpRepoDigests": [], "secretValuesReturned": False,
    }
    checks: list[dict[str, Any]] = [
        {"name": "repoSha", "expected": head, "actual": head, "status": "MATCH"},
    ]
    if expected_branch:
        checks.append({"name": "branch", "expected": expected_branch, "actual": branch, "status": "MATCH" if branch == expected_branch else "DRIFT"})
    if expected_docker_context:
        actual_context = docker.get("context")
        checks.append({"name": "dockerContext", "expected": expected_docker_context, "actual": actual_context, "status": "MATCH" if actual_context == expected_docker_context else "DRIFT_OR_UNAVAILABLE"})
    if expected_compose_projects is not None:
        expected_projects = sorted(set(str(item) for item in expected_compose_projects))
        actual_projects = sorted({item["name"] for item in docker.get("composeProjects", []) if item.get("name")})
        checks.append({"name": "composeProjects", "expected": expected_projects, "actual": actual_projects, "status": "MATCH" if actual_projects == expected_projects else "DRIFT_OR_UNAVAILABLE"})
    digest = str(expected_image_digest or "").strip().lower()
    if digest:
        if not _IMAGE_DIGEST.search(digest):
            raise ValueError("expected_image_digest must contain an immutable sha256 digest")
        actual_digests = docker.get("mcpRepoDigests", [])
        checks.append({"name": "mcpImageDigest", "expected": digest, "actual": actual_digests, "status": "MATCH" if digest in actual_digests else "DRIFT_OR_UNAVAILABLE"})
    drift = any(item["status"] != "MATCH" for item in checks)
    return {
        "ok": not drift,
        "status": "CONTEXT_DRIFT_DETECTED" if drift else "CONTEXT_READBACK_MATCH",
        "repoSha": head,
        "checks": checks,
        "dockerStatus": docker["status"],
        "mutationPerformed": False,
        "secretValuesReturned": False,
        "truthNotice": "Unavailable evidence is never converted to MATCH when an expectation was supplied.",
    }


def register(mcp: Any, runtime: Any) -> None:
    global _RUNTIME, _REGISTERED
    _RUNTIME = runtime
    if _REGISTERED:
        return
    for tool in (
        repository_intelligence_tool_inventory,
        repository_intelligence_search,
        managed_toolchain_verify,
        repository_schema_diagnostics,
        sovereign_resource_explorer,
        repository_context_drift_watch,
    ):
        mcp.tool(annotations=READ_ONLY)(tool)
    for tool in (
        repository_capability_scope_create,
        repository_intelligence_index_build,
        deployment_evidence_session_capture,
    ):
        mcp.tool(annotations=WORKSPACE_WRITE)(tool)
    for tool in (
        repository_hash_bound_replace,
        repository_hash_bound_restore,
    ):
        mcp.tool(annotations=TRACKED_WRITE)(tool)
    _REGISTERED = True
