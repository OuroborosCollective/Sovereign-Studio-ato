"""Deterministic AST and conservative text rules for the repository janitor."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

SUPPORTED_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs",
    ".sh", ".yml", ".yaml", ".json", ".md", ".toml",
}
SKIP_DIRECTORY_NAMES = {
    ".git", "node_modules", "dist", "build", "coverage", ".next",
    "vendor", "target", "__pycache__", ".pytest_cache", ".mypy_cache",
}
FORBIDDEN_FILE_NAMES = {
    ".env", ".env.local", ".env.production", "id_rsa", "id_dsa",
    "id_ecdsa", "id_ed25519",
}
FORBIDDEN_SUFFIXES = {".pem", ".key", ".p12", ".keystore", ".jks"}
MAX_SCAN_FILES = 500
MAX_FILE_BYTES = 1_000_000
MAX_PATCH_TEXT = 100_000
MAX_DIFF_OUTPUT = 30_000

_CONCRETE_SECRET_PATTERNS = (
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
_LABELED_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(password|token|api[_-]?key|secret)\b\s*=\s*([\"']?)([^\s,;\"'`]+)\2"
)
_LABELED_SECRET_MAPPING = re.compile(
    r"(?i)[\"']?\b(password|token|api[_-]?key|secret)\b[\"']?\s*:\s*([\"']?)([^\s,;\"'`]+)\2"
)
_SECRET_PLACEHOLDER_PREFIXES = (
    "$", "${", "(", "process.env", "import.meta", "os.getenv", "os.environ",
    "env.", "env[", "secrets.", "<", "[", "*", "xxx", "example",
    "replace_with_", "changeme",
)
_SECRET_TYPE_NAMES = {
    "str", "string", "number", "boolean", "bool", "unknown", "any", "object",
    "none", "null", "true", "false", "githubissuehub",
}

_DANGEROUS_REPLACEMENT_PATTERNS = (
    re.compile(r"git\s+push\s+origin\s+main", re.IGNORECASE),
    re.compile(r"allowAutoMerge\s*:\s*true", re.IGNORECASE),
    re.compile(r"allow_auto_merge\s*[=:]\s*true", re.IGNORECASE),
    re.compile(r"shell\s*=\s*True"),
    re.compile(r"AutoAddPolicy\s*\("),
    re.compile(r"rm\s+-rf\s+/"),
    re.compile(r"curl\s+[^\n|]+\|\s*(?:sh|bash)", re.IGNORECASE),
)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_secret_placeholder(candidate: str) -> bool:
    clean = candidate.strip().lower()
    normalized = clean.strip("()[]{}:;,")
    if not normalized or len(normalized) < 8:
        return True
    if normalized in _SECRET_TYPE_NAMES or normalized == "redacted":
        return True
    if clean.startswith(_SECRET_PLACEHOLDER_PREFIXES):
        return True
    if any(marker in clean for marker in (".env.", "os.getenv", "os.environ", "secrets[", "secrets.")):
        return True
    return False


def _secret_like_match(value: str) -> bool:
    if any(pattern.search(value) for pattern in _CONCRETE_SECRET_PATTERNS):
        return True
    for pattern in (_LABELED_SECRET_ASSIGNMENT, _LABELED_SECRET_MAPPING):
        for match in pattern.finditer(value):
            if not _is_secret_placeholder(match.group(3)):
                return True
    return False


def _mask_sensitive(value: str) -> str:
    masked = value
    for pattern in _CONCRETE_SECRET_PATTERNS:
        masked = pattern.sub("[redacted]", masked)

    def replace_assignment(match: re.Match[str]) -> str:
        if _is_secret_placeholder(match.group(3)):
            return match.group(0)
        return f"{match.group(1)}=[redacted]"

    masked = _LABELED_SECRET_ASSIGNMENT.sub(replace_assignment, masked)
    masked = _LABELED_SECRET_MAPPING.sub(replace_assignment, masked)
    return masked[:2_000]


def _line_text(content: str, lineno: int) -> str:
    lines = content.splitlines()
    if lineno < 1 or lineno > len(lines):
        return ""
    return _mask_sensitive(lines[lineno - 1].strip())


def _finding(
    *,
    rule_id: str,
    severity: str,
    path: str,
    line: int,
    message: str,
    evidence: str,
    content_sha256: str,
    suggested_search: str | None = None,
    suggested_replacement: str | None = None,
) -> dict[str, Any]:
    stable = f"{rule_id}:{path}:{line}:{evidence}"
    return {
        "id": hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16],
        "ruleId": rule_id,
        "severity": severity,
        "path": path,
        "line": line,
        "message": message,
        "evidence": _mask_sensitive(evidence),
        "contentSha256": content_sha256,
        "fixAvailable": bool(suggested_search is not None and suggested_replacement is not None),
        "suggestedSearchText": suggested_search,
        "suggestedReplacementText": suggested_replacement,
    }


def _python_call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts: list[str] = [func.attr]
        value = func.value
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if isinstance(value, ast.Name):
            parts.append(value.id)
        return ".".join(reversed(parts))
    return ""


def _scan_python(path: str, content: str, content_sha256: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    try:
        tree = ast.parse(content, filename=path)
    except SyntaxError as exc:
        findings.append(_finding(
            rule_id="PY-SYNTAX-ERROR", severity="critical", path=path,
            line=int(exc.lineno or 1), message="Python source cannot be parsed.",
            evidence=str(exc.msg), content_sha256=content_sha256,
        ))
        return findings

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call_name = _python_call_name(node)
            if call_name in {"eval", "exec", "builtins.eval", "builtins.exec"}:
                findings.append(_finding(
                    rule_id="PY-DYNAMIC-EVAL", severity="high", path=path, line=node.lineno,
                    message="Dynamic eval/exec can turn data into executable code.",
                    evidence=_line_text(content, node.lineno), content_sha256=content_sha256,
                ))
            if call_name in {"os.system", "subprocess.call", "subprocess.Popen", "subprocess.run"}:
                shell_true = any(
                    keyword.arg == "shell" and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True for keyword in node.keywords
                )
                if call_name == "os.system" or shell_true:
                    findings.append(_finding(
                        rule_id="PY-UNSAFE-SHELL", severity="critical", path=path, line=node.lineno,
                        message="Shell execution bypasses the structured command policy.",
                        evidence=_line_text(content, node.lineno), content_sha256=content_sha256,
                    ))
            if call_name in {"os.getenv", "os.environ.get"} and len(node.args) >= 2:
                key, default = node.args[0], node.args[1]
                if (
                    isinstance(key, ast.Constant) and isinstance(key.value, str)
                    and re.search(r"SECRET|TOKEN|PASSWORD|API[_-]?KEY", key.value, re.IGNORECASE)
                    and isinstance(default, ast.Constant) and isinstance(default.value, str)
                    and default.value.strip()
                ):
                    findings.append(_finding(
                        rule_id="PY-HARDCODED-SECRET-DEFAULT", severity="critical", path=path,
                        line=node.lineno,
                        message="Secret-like environment variable has a non-empty source-code default.",
                        evidence=f"{key.value}=[redacted]", content_sha256=content_sha256,
                    ))
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                findings.append(_finding(
                    rule_id="PY-BARE-EXCEPT", severity="medium", path=path, line=node.lineno,
                    message="Bare except hides unrelated failures and weakens runtime evidence.",
                    evidence=_line_text(content, node.lineno), content_sha256=content_sha256,
                ))
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                findings.append(_finding(
                    rule_id="PY-SILENT-EXCEPT", severity="high", path=path, line=node.lineno,
                    message="Exception is swallowed without a blocker, error, or evidence event.",
                    evidence=_line_text(content, node.lineno), content_sha256=content_sha256,
                ))
    return findings


def _scan_text(path: str, content: str, content_sha256: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    rules: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
        ("GIT-DIRECT-MAIN-PUSH", "critical", re.compile(r"git\s+push\s+origin\s+main", re.IGNORECASE),
         "Direct main push bypasses Draft-PR review and evidence gates."),
        ("JS-EXECSYNC", "high", re.compile(r"\bexecSync\s*\("),
         "Synchronous process execution can bypass structured tool policy and freeze the runtime."),
        ("JS-CHILD-PROCESS-EXEC", "high", re.compile(r"\b(?:child_process\.)?exec\s*\("),
         "String-based child-process execution should use an argv allowlist instead."),
        ("PATH-PREFIX-BOUNDARY", "high", re.compile(r"\.resolve\(\).*\.startsWith\(|startswith\s*\(\s*str\s*\("),
         "String-prefix path checks can accept sibling paths with the same prefix."),
        ("JS-EMPTY-CATCH", "medium", re.compile(r"catch\s*(?:\([^)]*\))?\s*\{\s*\}"),
         "Empty catch block erases failure evidence."),
    )
    for lineno, line in enumerate(content.splitlines(), 1):
        for rule_id, severity, pattern, message in rules:
            if not pattern.search(line):
                continue
            suffix = Path(path).suffix.lower()
            if (
                rule_id == "GIT-DIRECT-MAIN-PUSH"
                and suffix in {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
                and not re.search(r"\b(exec|execSync|spawn|run|command)\b", line)
            ):
                continue
            suggested_search = suggested_replacement = None
            if rule_id == "GIT-DIRECT-MAIN-PUSH" and line.strip() == "git push origin main":
                indent = line[: len(line) - len(line.lstrip())]
                suggested_search = line
                suggested_replacement = f'{indent}git push --set-upstream origin "$BRANCH"  # then open a Draft PR'
            findings.append(_finding(
                rule_id=rule_id, severity=severity, path=path, line=lineno,
                message=message, evidence=line.strip(), content_sha256=content_sha256,
                suggested_search=suggested_search, suggested_replacement=suggested_replacement,
            ))
        if "paramiko.AutoAddPolicy()" in line:
            indent = line[: len(line) - len(line.lstrip())]
            findings.append(_finding(
                rule_id="PY-SSH-AUTOADD-HOSTKEY", severity="high", path=path, line=lineno,
                message="Automatically trusting unknown SSH host keys enables machine-in-the-middle attacks.",
                evidence=line.strip(), content_sha256=content_sha256, suggested_search=line,
                suggested_replacement=(
                    f"{indent}client.load_system_host_keys()\n"
                    f"{indent}client.set_missing_host_key_policy(paramiko.RejectPolicy())"
                ),
            ))
        if _secret_like_match(line):
            findings.append(_finding(
                rule_id="SOURCE-SECRET-LIKE-VALUE", severity="critical", path=path, line=lineno,
                message="Secret-like value appears in source text and must be rotated and removed.",
                evidence="[redacted secret-like value]", content_sha256=content_sha256,
            ))
    return findings


def _is_skipped_path(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    return any(part in SKIP_DIRECTORY_NAMES for part in relative.parts)


def _safe_target(root: Path, relative_path: str) -> Path | None:
    candidate_text = str(relative_path or "").strip().replace("\\", "/")
    if not candidate_text or candidate_text.startswith("/"):
        return None
    target = (root / candidate_text).resolve()
    if target != root and root not in target.parents:
        return None
    if _is_skipped_path(target, root):
        return None
    if target.name.lower() in FORBIDDEN_FILE_NAMES or target.suffix.lower() in FORBIDDEN_SUFFIXES:
        return None
    return target


def _iter_source_files(
    root: Path, paths: Iterable[str], max_files: int, *, include_docs: bool = False,
) -> Iterable[Path]:
    requested = [str(value).strip() for value in paths if str(value).strip()]
    seeds: list[Path] = []
    if requested:
        for relative in requested:
            target = _safe_target(root, relative)
            if target is not None and target.exists():
                seeds.append(target)
    else:
        seeds.append(root)
    candidates_by_path: dict[Path, Path] = {}
    for seed in seeds:
        candidates = [seed] if seed.is_file() else seed.rglob("*")
        for candidate in candidates:
            try:
                if candidate.is_symlink():
                    continue
                resolved = candidate.resolve()
            except OSError:
                continue
            if resolved in candidates_by_path or _is_skipped_path(resolved, root):
                continue
            suffix = resolved.suffix.lower()
            if not resolved.is_file() or suffix not in SUPPORTED_EXTENSIONS:
                continue
            if suffix == ".md" and not include_docs and not requested:
                continue
            candidates_by_path[resolved] = resolved
    priority = {
        ".py": 0, ".ts": 0, ".tsx": 0, ".js": 0, ".jsx": 0, ".mjs": 0,
        ".cjs": 0, ".go": 0, ".rs": 0, ".sh": 1, ".yml": 1, ".yaml": 1,
        ".json": 1, ".toml": 1, ".md": 2,
    }
    ordered = sorted(
        candidates_by_path.values(),
        key=lambda item: (priority.get(item.suffix.lower(), 3), item.relative_to(root).as_posix()),
    )
    yield from ordered[:max_files]


def _detect_test_command(root: Path) -> str | None:
    package_json = root / "package.json"
    if package_json.is_file():
        try:
            package = json.loads(package_json.read_text(encoding="utf-8"))
            scripts = package.get("scripts") if isinstance(package, dict) else None
            if isinstance(scripts, dict):
                manager = "pnpm" if (root / "pnpm-lock.yaml").exists() else "yarn" if (root / "yarn.lock").exists() else "npm"
                run = f"{manager} run"
                if "type-check" in scripts and "test" in scripts:
                    return f"{run} type-check && {run} test"
                if "test:all" in scripts:
                    return f"{run} test:all"
                if "test" in scripts:
                    return f"{run} test"
        except (OSError, ValueError, TypeError):
            pass
    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
        return "python -m pytest"
    if (root / "go.mod").exists():
        return "go test ./..."
    if (root / "Cargo.toml").exists():
        return "cargo test"
    return None


def _optional_ollama_explanation(
    _findings: list[dict[str, Any]], _family: str,
) -> tuple[None, str]:
    """Keep model output outside the deterministic scan and patch contract."""
    return None, "Local model explanations are disabled in the repository Janitor runtime."
