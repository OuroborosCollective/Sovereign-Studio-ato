from __future__ import annotations

import ast
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any, Final

from mcp.types import ToolAnnotations

from policy import safe_repo_path


READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

_MAX_TRACKED_FILES: Final[int] = 30_000
_MAX_TEXT_BYTES: Final[int] = 1_200_000
_MAX_RESULT_ITEMS: Final[int] = 160
_MAX_NORMALIZE_RECORDS: Final[int] = 100
_ALLOWED_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,159}$")
_TEXT_SUFFIXES = {
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".java", ".kt", ".kts", ".go", ".rs", ".cs", ".c", ".h",
    ".cpp", ".hpp", ".rb", ".php", ".scala", ".swift", ".sql",
    ".graphql", ".sh", ".yml", ".yaml", ".json", ".toml", ".xml",
    ".md", ".css", ".scss",
}
_SKIP_PREFIXES = (
    ".git/", "node_modules/", "vendor/", "dist/", "build/", "coverage/",
    "target/", ".gradle/", ".next/", ".venv/", "venv/", "__pycache__/",
    "playwright-report/", "test-results/", "android/app/build/", "android/.gradle/",
)
_SECRET_MARKER = re.compile(
    r"(?:sk-(?:proj-)?[A-Za-z0-9_-]{12,}|github_pat_[A-Za-z0-9_]+|"
    r"gh[pousr]_[A-Za-z0-9_]{20,}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----|"
    r"Authorization\s*:\s*(?:Bearer\s+)?\S+)",
    re.IGNORECASE,
)
_KNOWLEDGE_PATTERNS: Final[dict[str, re.Pattern[str]]] = {
    "pgvector": re.compile(r"\b(?:pgvector|vector\s*\(|postgres-pgvector)\b", re.I),
    "qdrant": re.compile(r"\bqdrant\b", re.I),
    "milvus": re.compile(r"\bmilvus\b", re.I),
    "pinecone": re.compile(r"\bpinecone\b", re.I),
    "weaviate": re.compile(r"\bweaviate\b", re.I),
    "chroma": re.compile(r"\bchromadb?\b", re.I),
    "faiss": re.compile(r"\bfaiss\b", re.I),
    "redis-vector": re.compile(r"\b(?:redisearch|vectorfield|vector_similarity)\b", re.I),
    "search-knn": re.compile(r"\b(?:opensearch|elasticsearch).{0,80}\b(?:knn|dense_vector)\b", re.I | re.S),
    "embedding-api": re.compile(r"\b(?:embeddings?\.create|/v\d+/embeddings?|embedding[_-]?model)\b", re.I),
    "learning-pattern": re.compile(r"\b(?:solution[_ -]?pattern|learning[_ -]?pattern|pattern[_ -]?(?:store|memory|intake))\b", re.I),
    "knowledge-store": re.compile(r"\b(?:knowledge[_ -]?(?:base|store|library|memory)|remote[_ -]?memory)\b", re.I),
}
_KNOWLEDGE_PATH = re.compile(r"(?:knowledge|vector|embedding|memory|pattern|learn|semantic|rag)", re.I)
_ENDPOINT_HINT = re.compile(r"['\"](/[^'\"]*(?:knowledge|vector|embedding|memory|pattern|learn|semantic|rag)[^'\"]*)['\"]", re.I)
_ENV_NAME = re.compile(r"\b([A-Z][A-Z0-9_]{2,}(?:VECTOR|EMBED|MILVUS|QDRANT|PINECONE|WEAVIATE|KNOWLEDGE|MEMORY|DATABASE)[A-Z0-9_]*)\b")
_ROUTE_PATTERNS = (
    re.compile(r"@(?:app|router|blueprint)\.(get|post|put|patch|delete|route)\(\s*['\"]([^'\"]+)"),
    re.compile(r"\b(?:app|router|server)\.(get|post|put|patch|delete|use)\(\s*['\"]([^'\"]+)"),
    re.compile(r"@(?:(Get|Post|Put|Patch|Delete)Mapping|RequestMapping)\(\s*(?:value\s*=\s*)?['\"]([^'\"]+)"),
)
_JS_IMPORT = re.compile(r"(?:import|export)\s+(?:[^'\"]+?\s+from\s+)?['\"]([^'\"]+)['\"]|require\(\s*['\"]([^'\"]+)['\"]\s*\)")
_JS_SYMBOL = re.compile(
    r"\b(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|class|interface|type|enum)\s+([A-Za-z_$][\w$]*)|"
    r"\b(?:export\s+)?(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"
)
_GENERIC_CALL = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\(")
_CALL_KEYWORDS = {"if", "for", "while", "switch", "catch", "function", "func", "fn", "def"}
_BACKEND_ROUTE_DECORATOR = re.compile(
    r"@(?P<owner>[A-Za-z_][\w.]*)\.(?P<kind>route|api_route|get|post|put|patch|delete)\(\s*"
    r"(?P<quote>['\"])(?P<path>/[^'\"]+)(?P=quote)(?P<tail>[^)]*)\)",
    re.I | re.S,
)
_EXPRESS_ROUTE = re.compile(
    r"\b(?:app|router|server)\.(?P<method>get|post|put|patch|delete)\(\s*"
    r"(?P<quote>['\"`])(?P<path>/[^'\"`]+)(?P=quote)",
    re.I,
)
_CLIENT_METHOD_CALL = re.compile(
    r"\b(?:axios|api|client|http)\.(?P<method>get|post|put|patch|delete)\(\s*"
    r"(?P<quote>['\"`])(?P<path>/api/[^'\"`]+)(?P=quote)",
    re.I,
)
_FETCH_CALL = re.compile(
    r"\bfetch\(\s*(?P<quote>['\"`])(?P<path>/api/[^'\"`]+)(?P=quote)"
    r"(?P<tail>\s*,\s*\{.{0,600}?\})?\s*\)",
    re.I | re.S,
)
_SQL_CREATE_TABLE = re.compile(
    r"\bCREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+"
    r"(?:(?P<schema_quote>[\"`]?)"
    r"(?P<schema>[A-Za-z_][\w]*)(?P=schema_quote)\.)?"
    r"(?P<table_quote>[\"`]?)(?P<table>[A-Za-z_][\w]*)(?P=table_quote)",
    re.I,
)
_INTENT_BOUNDARY_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (
        "javascript_keyword_intent",
        re.compile(
            r"(?:toLowerCase\(\)|casefold\(\)|lower\(\)).{0,160}"
            r"(?:includes|test|search|match)\(.{0,160}"
            r"(?:create|build|implement|fix|repair|deploy|merge|erstelle|baue|repariere)",
            re.I | re.S,
        ),
    ),
    (
        "python_keyword_intent",
        re.compile(
            r"(?:re\.(?:search|match|fullmatch)|\bin\b).{0,180}"
            r"(?:create|build|implement|fix|repair|deploy|merge|erstelle|baue|repariere)"
            r".{0,180}(?:lower|casefold|\btext\b|\bmessage\b|\bprompt\b|\bmission\b)",
            re.I | re.S,
        ),
    ),
)

_DOMAIN_PATTERNS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("chat_ui", ("src/app.tsx", "src/features/product/containers/", "src/features/product/components/")),
    ("frontend_runtime", ("src/features/product/runtime/", "src/runtime/", "src/predictive/")),
    ("github_toolchain", ("src/features/github/", "src/features/toolchain/")),
    ("agents_sdk", ("backend/agent_runtime/", "scripts/sovereign-backend/agent_runtime/")),
    ("backend", ("backend/", "scripts/sovereign-backend/")),
    ("database", ("scripts/sovereign-backend/migrations/",)),
    ("mcp_broker", ("tools/sovereign-chatgpt-mcp/",)),
    ("widget", ("widget", "tools/sovereign-chatgpt-mcp/server.py")),
    ("ci_release", (".github/workflows/", ".github/actions/")),
    ("android", ("android/", "capacitor", "scripts/copy-dist-to-android")),
    ("deployment", ("deploy/", "dockerfile", "install-on-vps", "docker-compose")),
    ("documentation", ("docs/", "readme.md", "agents.md", "onboarding.md", "tech_debt.md")),
)
_GATES_BY_DOMAIN: Final[dict[str, tuple[str, ...]]] = {
    "chat_ui": ("targeted Vitest", "pnpm run type-check", "pnpm run build:web", "pnpm run audit:sovereign"),
    "frontend_runtime": ("targeted runtime Vitest", "pnpm run type-check", "pnpm run build:web", "pnpm run audit:sovereign"),
    "github_toolchain": ("targeted GitHub/toolchain tests", "pnpm run type-check", "pnpm run audit:sovereign"),
    "agents_sdk": ("cognitive store/route/agent Pytest", "canonical/deployment mirror equality", "real persisted Agents SDK canary"),
    "backend": ("targeted backend Pytest", "Python compile", "backend immutable-image workflow", "VPS route/health readback if deployed"),
    "database": ("migration ordering", "rollback preview", "schema-drift contract", "post-apply readback"),
    "mcp_broker": ("targeted MCP Pytest", "MCP immutable-image workflow", "broker/host-worker boundary canary", "JSON-RPC initialize"),
    "widget": ("typed output schema", "widget metadata/CSP/origin tests", "message source/request binding", "secret transport audit"),
    "ci_release": ("workflow syntax/contract tests", "exact-head workflow conclusions"),
    "android": ("Android fast", "Android standard", "Android release", "APK/AAB artifact inspection", "device/WebView smoke when required"),
    "deployment": ("revision/digest binding", "new runtime identity", "health and capability probe", "known rollback digest"),
    "documentation": ("documentation-to-live-contract drift review",),
}
_FAILURE_FAMILIES_BY_DOMAIN: Final[dict[str, tuple[str, ...]]] = {
    "chat_ui": ("UI_RUNTIME_EVIDENCE_DRIFT", "CHAT_ACTION_STATE_PROJECTION"),
    "frontend_runtime": ("INTENT_ROUTE_RESULT_STATE_CHAIN", "PREDICTIVE_RUNTIME_CONTRADICTION"),
    "github_toolchain": ("REPOSITORY_TOOL_HANDOFF", "DRAFT_PR_EVIDENCE_BINDING"),
    "agents_sdk": ("AGENTS_SDK_RUN_PERSISTENCE", "AGENT_TOOL_SELECTION_AND_EVIDENCE"),
    "backend": ("BACKEND_ROUTE_RUNTIME_CONTRACT", "CANONICAL_DEPLOYMENT_MIRROR_DRIFT"),
    "database": ("MIGRATION_SCHEMA_DRIFT", "PERSISTED_STATE_RETRIEVAL"),
    "mcp_broker": ("MCP_BROKER_PROTOCOL_BOUNDARY", "HOST_COMMAND_QUEUE_BOUNDARY"),
    "widget": ("WIDGET_STRUCTURED_CONTENT_TRUTH", "WIDGET_ORIGIN_AND_REQUEST_BINDING"),
    "ci_release": ("EXACT_HEAD_CI_BINDING", "RELEASE_GATE_RELEVANCE"),
    "android": ("ANDROID_BUILD_RUNTIME_BOUNDARY", "WEBVIEW_ARTIFACT_CONTRACT"),
    "deployment": ("IMMUTABLE_REVISION_DIGEST_BINDING", "DEPLOYMENT_ROLLBACK_READBACK"),
    "documentation": ("DOCUMENTATION_LIVE_CONTRACT_DRIFT",),
}

_REQUIRED_TEXT = ("title", "problem", "solution", "applicability")
_LIST_FIELDS = ("triggers", "preconditions", "invariants", "failure_modes", "validation", "exclusions", "tags", "supersedes")

_RUNTIME: Any = None
_DATABASE: Any = None
_REGISTERED = False


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
    )
    return result.stdout.strip()


def _repo(workspace_id: str) -> Path:
    if _RUNTIME is None:
        raise RuntimeError("Repository skill tools are not registered")
    return _RUNTIME._repo(workspace_id)


def _tracked_files(repo: Path) -> list[str]:
    files = [line for line in _git(repo, "ls-files").splitlines() if line]
    if len(files) > _MAX_TRACKED_FILES:
        raise ValueError("Repository exceeds the bounded tracked-file limit")
    return files


def _safe_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > _MAX_TEXT_BYTES:
            return None
        return path.read_text("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _language(path: str) -> str:
    suffix = PurePosixPath(path).suffix.casefold()
    return {
        ".py": "python", ".pyi": "python", ".ts": "typescript", ".tsx": "typescript-react",
        ".js": "javascript", ".jsx": "javascript-react", ".mjs": "javascript", ".cjs": "javascript",
        ".java": "java", ".kt": "kotlin", ".kts": "kotlin", ".go": "go", ".rs": "rust",
        ".cs": "csharp", ".c": "c", ".h": "c-header", ".cpp": "cpp", ".hpp": "cpp-header",
        ".rb": "ruby", ".php": "php", ".scala": "scala", ".swift": "swift", ".sql": "sql",
        ".graphql": "graphql", ".sh": "shell", ".yml": "yaml", ".yaml": "yaml", ".json": "json",
        ".toml": "toml", ".xml": "xml", ".md": "markdown", ".css": "css", ".scss": "scss",
    }.get(suffix, suffix.lstrip(".") or "unknown")


def _roles(path: str) -> list[str]:
    lowered = path.casefold()
    rules = (
        ("documentation", ("docs/", "readme", ".md")),
        ("test", ("test", ".spec.")),
        ("workflow", (".github/workflows/",)),
        ("frontend", ("src/", "frontend/", "web/")),
        ("backend", ("backend/", "server/", "api/")),
        ("mobile", ("android/", "ios/", "capacitor", "react-native")),
        ("agent", ("agent", "mcp", "llm", "model", "inference")),
        ("persistence", ("migration", "database", "schema", ".sql")),
        ("release", ("deploy", "docker", "workflow", "release", "installer")),
        ("security", ("auth", "security", "secret", "oauth", "permission")),
    )
    found = [role for role, markers in rules if any(marker in lowered for marker in markers)]
    return found or ["source"]


def _path_class(path: str) -> str:
    lowered = path.casefold()
    if any(part in lowered for part in ("node_modules/", "vendor/", "dist/", "build/", "generated/", ".min.")):
        return "GENERATED"
    if any(part in lowered for part in ("test/", "tests/", "__tests__/", ".test.", ".spec.", "fixture", "e2e/")):
        return "TEST_ONLY"
    if any(part in lowered for part in ("legacy", "deprecated", "archive", "obsolete")):
        return "LEGACY"
    if any(part in lowered for part in ("experiment", "prototype", "poc/", "example/", "examples/", "demo/")):
        return "EXPERIMENTAL"
    return "PRODUCTION_CANDIDATE"


def _python_symbols(
    text: str,
) -> tuple[list[dict[str, Any]], list[str], list[str], dict[str, Any] | None]:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [], [], [], {
            "message": str(exc.msg or "invalid syntax")[:240],
            "line": max(0, int(exc.lineno or 0)),
            "offset": max(0, int(exc.offset or 0)),
            "runtimeVersion": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "classification": "PYTHON_GRAMMAR_VERSION_DRIFT_OR_INVALID_SOURCE",
        }
    symbols: list[dict[str, Any]] = []
    imports: list[str] = []
    calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append({"name": node.name, "kind": type(node).__name__, "line": node.lineno})
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append("." * node.level + (node.module or ""))
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)
    return symbols, sorted(set(imports)), sorted(set(calls)), None


def _js_symbols(text: str) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    symbols = []
    for match in _JS_SYMBOL.finditer(text):
        name = next((group for group in match.groups() if group), "")
        if name:
            symbols.append({"name": name, "kind": "static_symbol_hint", "line": text.count("\n", 0, match.start()) + 1})
    imports = sorted({left or right for left, right in _JS_IMPORT.findall(text)})
    calls = sorted(set(_GENERIC_CALL.findall(text)) - _CALL_KEYWORDS)
    return symbols, imports, calls


def _safe_endpoint(value: str) -> str:
    if _SECRET_MARKER.search(value):
        return "<redacted-endpoint>"
    if "?" in value:
        return value.split("?", 1)[0] + "?<redacted>"
    return value


def _routes(text: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for pattern in _ROUTE_PATTERNS:
        for match in pattern.finditer(text):
            groups = [group for group in match.groups() if group]
            path = next((group for group in groups if group.startswith("/")), groups[-1] if groups else "")
            path = _safe_endpoint(path)
            method = groups[0].upper() if groups and not groups[0].startswith("/") else "UNKNOWN"
            output.append({"method": method, "path": path, "line": text.count("\n", 0, match.start()) + 1})
    return output


def _normalize_contract_path(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    raw = raw.split("?", 1)[0]
    safe = _safe_endpoint(raw)
    if safe == "<redacted-endpoint>":
        return safe
    safe = re.sub(r"\$\{[^}]+\}", "<p>", safe)
    safe = re.sub(r"<[^>]+>", "<p>", safe)
    safe = re.sub(r"\{[^{}\/]+\}", "<p>", safe)
    safe = re.sub(r":([A-Za-z_][A-Za-z0-9_]*)", "<p>", safe)
    safe = re.sub(r"/+", "/", safe)
    if not safe.startswith("/"):
        safe = "/" + safe
    return safe.rstrip("/") or "/"


def _route_methods(kind: str, tail: str) -> list[str]:
    normalized_kind = str(kind or "").strip().lower()
    if normalized_kind not in {"route", "api_route"}:
        return [normalized_kind.upper()]
    methods = re.search(
        r"methods\s*=\s*[\[(]([^\])]+)[\])]",
        str(tail or ""),
        re.I | re.S,
    )
    if methods:
        selected = sorted({item.upper() for item in re.findall(r"['\"]([A-Za-z]+)['\"]", methods.group(1))})
        if selected:
            return selected
    return ["GET"]


def _backend_contracts(repo: Path, files: list[str]) -> list[dict[str, Any]]:
    prefixes = (
        "backend/",
        "scripts/sovereign-backend/",
        "src/server/",
        "server/",
        "cloudflare-worker/",
        "cloudflare-worker-ai-proxy/",
        "tools/",
    )
    contracts: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...], str, int]] = set()
    for relative in files:
        if not relative.startswith(prefixes) or _path_class(relative) == "TEST_ONLY":
            continue
        suffix = PurePosixPath(relative).suffix.casefold()
        if suffix not in {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}:
            continue
        text = _safe_text(repo / relative)
        if text is None:
            continue
        if suffix == ".py":
            for match in _BACKEND_ROUTE_DECORATOR.finditer(text):
                path = _normalize_contract_path(match.group("path"))
                if not path or path == "<redacted-endpoint>":
                    continue
                methods = _route_methods(match.group("kind"), match.group("tail"))
                line = text.count("\n", 0, match.start()) + 1
                key = (path, tuple(methods), relative, line)
                if key in seen:
                    continue
                seen.add(key)
                contracts.append({
                    "path": path,
                    "methods": methods,
                    "file": relative,
                    "line": line,
                    "confidence": "static_decorator",
                })
        else:
            for match in _EXPRESS_ROUTE.finditer(text):
                path = _normalize_contract_path(match.group("path"))
                if not path or path == "<redacted-endpoint>":
                    continue
                line = text.count("\n", 0, match.start()) + 1
                methods = [match.group("method").upper()]
                key = (path, tuple(methods), relative, line)
                if key in seen:
                    continue
                seen.add(key)
                contracts.append({
                    "path": path,
                    "methods": methods,
                    "file": relative,
                    "line": line,
                    "confidence": "static_call",
                })
        if len(contracts) >= _MAX_RESULT_ITEMS:
            break
    return sorted(contracts, key=lambda item: (item["path"], item["methods"], item["file"], item["line"]))


def _frontend_contract_calls(repo: Path, files: list[str]) -> list[dict[str, Any]]:
    prefixes = ("src/", "apps/", "packages/", "sovereign-studio-rn/", "ato-v2/")
    calls: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, int]] = set()
    for relative in files:
        if not relative.startswith(prefixes) or _path_class(relative) == "TEST_ONLY":
            continue
        if "/server/" in relative or relative.startswith("src/server/"):
            continue
        suffix = PurePosixPath(relative).suffix.casefold()
        if suffix not in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}:
            continue
        text = _safe_text(repo / relative)
        if text is None:
            continue
        for match in _CLIENT_METHOD_CALL.finditer(text):
            path = _normalize_contract_path(match.group("path"))
            if not path or path == "<redacted-endpoint>":
                continue
            line = text.count("\n", 0, match.start()) + 1
            method = match.group("method").upper()
            key = (path, method, relative, line)
            if key not in seen:
                seen.add(key)
                calls.append({"path": path, "method": method, "file": relative, "line": line, "confidence": "static_client_call"})
        for match in _FETCH_CALL.finditer(text):
            path = _normalize_contract_path(match.group("path"))
            if not path or path == "<redacted-endpoint>":
                continue
            tail = match.group("tail") or ""
            method_match = re.search(r"\bmethod\s*:\s*['\"]([A-Za-z]+)['\"]", tail, re.I)
            method = method_match.group(1).upper() if method_match else "GET"
            line = text.count("\n", 0, match.start()) + 1
            key = (path, method, relative, line)
            if key not in seen:
                seen.add(key)
                calls.append({"path": path, "method": method, "file": relative, "line": line, "confidence": "static_fetch_call"})
        if len(calls) >= _MAX_RESULT_ITEMS:
            break
    return sorted(calls, key=lambda item: (item["path"], item["method"], item["file"], item["line"]))[:_MAX_RESULT_ITEMS]


def _contract_path_matches(left: str, right: str) -> bool:
    def regex_for(value: str) -> re.Pattern[str]:
        escaped = re.escape(value).replace(re.escape("<p>"), r"[^/]+")
        return re.compile(r"^" + escaped + r"$")

    return bool(regex_for(left).fullmatch(right) or regex_for(right).fullmatch(left))


def _sql_table_inventory(repo: Path, files: list[str]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for relative in files:
        if PurePosixPath(relative).suffix.casefold() != ".sql" or "migration" not in relative.casefold():
            continue
        text = _safe_text(repo / relative)
        if text is None:
            continue
        for match in _SQL_CREATE_TABLE.finditer(text):
            output.append({
                "schema": match.group("schema") or "public",
                "table": match.group("table"),
                "file": relative,
                "line": text.count("\n", 0, match.start()) + 1,
                "confidence": "static_create_table",
            })
            if len(output) >= _MAX_RESULT_ITEMS:
                return sorted(output, key=lambda item: (item["table"], item["file"], item["line"]))
    return sorted(output, key=lambda item: (item["table"], item["file"], item["line"]))


def _workflow_inventory(repo: Path, files: list[str]) -> list[dict[str, Any]]:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        yaml = None
    output: list[dict[str, Any]] = []
    for relative in files:
        if not relative.startswith(".github/workflows/"):
            continue
        path = repo / relative
        try:
            payload = path.read_bytes()
        except OSError:
            continue
        entry: dict[str, Any] = {
            "path": relative,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "recognizedExtension": path.suffix.casefold() in {".yml", ".yaml"},
            "parserAvailable": yaml is not None,
            "validYaml": None,
            "jobs": [],
        }
        if len(payload) > _MAX_TEXT_BYTES:
            entry["validYaml"] = False
            entry["error"] = "workflow exceeds bounded parser size"
        elif yaml is not None:
            try:
                parsed = yaml.safe_load(payload.decode("utf-8"))
                jobs = parsed.get("jobs") if isinstance(parsed, dict) else None
                entry["validYaml"] = isinstance(parsed, dict) and isinstance(jobs, dict) and bool(jobs)
                entry["jobs"] = sorted(str(name)[:160] for name in jobs)[:100] if isinstance(jobs, dict) else []
                if entry["validYaml"] is False:
                    entry["error"] = "workflow must be a mapping with at least one jobs entry"
            except (UnicodeDecodeError, yaml.YAMLError) as exc:
                entry["validYaml"] = False
                entry["error"] = str(exc).splitlines()[0][:240]
        output.append(entry)
        if len(output) >= _MAX_RESULT_ITEMS:
            break
    return sorted(output, key=lambda item: item["path"])


def _test_inventory(files: list[str]) -> dict[str, Any]:
    families: Counter[str] = Counter()
    examples: defaultdict[str, list[str]] = defaultdict(list)
    for relative in files:
        lowered = relative.casefold()
        family = ""
        if relative.endswith(".py") and (PurePosixPath(relative).name.startswith("test_") or "/tests/" in lowered):
            family = "pytest"
        elif any(marker in lowered for marker in (".test.ts", ".test.tsx", ".test.js", ".test.jsx")):
            family = "vitest_or_jest"
        elif any(marker in lowered for marker in (".spec.ts", ".spec.tsx", ".spec.js", ".spec.jsx")):
            family = "playwright_or_spec"
        elif "/androidtest/" in lowered or "/test/" in lowered and relative.endswith((".kt", ".java")):
            family = "android"
        if not family:
            continue
        families[family] += 1
        if len(examples[family]) < 20:
            examples[family].append(relative)
    return {"counts": dict(sorted(families.items())), "examples": dict(sorted(examples.items()))}


def _mcp_component_inventory(files: list[str]) -> dict[str, list[str]]:
    prefixes = (
        "tools/sovereign-chatgpt-mcp/",
        "backend/agent_runtime/tools/",
        "scripts/sovereign-backend/agent_runtime/tools/",
    )
    output: dict[str, list[str]] = {}
    for prefix in prefixes:
        selected = [path for path in files if path.startswith(prefix) and PurePosixPath(path).suffix.casefold() in {".py", ".ts", ".tsx"}]
        if selected:
            output[prefix.rstrip("/")] = sorted(selected)[:_MAX_RESULT_ITEMS]
    return output


def _llm_boundary_candidates(repo: Path, files: list[str]) -> list[dict[str, Any]]:
    prefixes = (
        "src/runtime/",
        "src/features/product/runtime/",
        "backend/agent_runtime/",
        "scripts/sovereign-backend/agent_runtime/",
        "tools/sovereign-chatgpt-mcp/",
    )
    output: list[dict[str, Any]] = []
    for relative in files:
        if not relative.startswith(prefixes) or _path_class(relative) == "TEST_ONLY":
            continue
        if relative == "tools/sovereign-chatgpt-mcp/repository_skill_tools.py":
            continue
        if PurePosixPath(relative).suffix.casefold() not in {".py", ".ts", ".tsx", ".js", ".jsx"}:
            continue
        text = _safe_text(repo / relative)
        if text is None:
            continue
        for family, pattern in _INTENT_BOUNDARY_PATTERNS:
            for match in pattern.finditer(text):
                output.append({
                    "family": family,
                    "file": relative,
                    "line": text.count("\n", 0, match.start()) + 1,
                    "status": "CANDIDATE_REQUIRES_REVIEW",
                    "truthNotice": "Offline fallback and structured enum handling may be valid.",
                })
                if len(output) >= _MAX_RESULT_ITEMS:
                    return output
    return output


def _mirror_inventory(repo: Path, files: list[str]) -> list[dict[str, Any]]:
    tracked = set(files)
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for source in files:
        target = ""
        if source.startswith("backend/"):
            target = "scripts/sovereign-backend/" + source.removeprefix("backend/")
        elif source.startswith("scripts/sovereign-backend/"):
            target = "backend/" + source.removeprefix("scripts/sovereign-backend/")
        if not target or target not in tracked:
            continue
        pair = tuple(sorted((source, target)))
        if pair in seen:
            continue
        seen.add(pair)
        left, right = pair
        try:
            left_payload = (repo / left).read_bytes()
            right_payload = (repo / right).read_bytes()
        except OSError:
            continue
        output.append({
            "source": left,
            "mirror": right,
            "byteEqual": left_payload == right_payload,
            "sourceSha256": hashlib.sha256(left_payload).hexdigest(),
            "mirrorSha256": hashlib.sha256(right_payload).hexdigest(),
        })
        if len(output) >= _MAX_RESULT_ITEMS:
            break
    return sorted(output, key=lambda item: (item["source"], item["mirror"]))


def _architecture_snapshot(repo: Path) -> dict[str, Any]:
    files = _tracked_files(repo)
    product_map = _scan(repo, include_logic=True)
    payload: dict[str, Any] = {
        "schemaVersion": "sovereign.architecture-snapshot.v1",
        "revision": _git(repo, "rev-parse", "HEAD"),
        "dirty": bool(_git(repo, "status", "--porcelain")),
        "pythonRuntimeVersion": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "backendContracts": _backend_contracts(repo, files),
        "frontendCalls": _frontend_contract_calls(repo, files),
        "sqlTables": _sql_table_inventory(repo, files),
        "workflows": _workflow_inventory(repo, files),
        "tests": _test_inventory(files),
        "mcpComponents": _mcp_component_inventory(files),
        "mirrorPairs": _mirror_inventory(repo, files),
        "llmToolBoundaryCandidates": _llm_boundary_candidates(repo, files),
        "parserFindings": ((product_map.get("logic") or {}).get("parserFindings") or [])[:_MAX_RESULT_ITEMS],
        "knowledgeSummary": product_map.get("summary") or {},
        "knowledgeTechnologies": sorted((product_map.get("knowledgeEvidence") or {}).keys()),
        "truthBoundary": {
            "staticEvidenceOnly": True,
            "runtimeSuccessClaimed": False,
            "liveDatabaseAccessed": False,
            "vpsAccessed": False,
            "requiredLiveTools": [
                "postgres_canary",
                "vector_database_canary",
                "mcp_control_plane_status",
                "vps_container_status",
            ],
        },
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload["snapshotSha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def _architecture_drift_report(repo: Path) -> dict[str, Any]:
    snapshot = _architecture_snapshot(repo)
    findings: list[dict[str, Any]] = []
    backend = snapshot["backendContracts"]
    for call in snapshot["frontendCalls"]:
        path_matches = [item for item in backend if _contract_path_matches(call["path"], item["path"])]
        if not path_matches:
            findings.append({
                "severity": "P1",
                "family": "CONTRACT_DRIFT",
                "status": "STATIC_CANDIDATE",
                "what": f"{call['method']} {call['path']} has no statically discovered backend route",
                "evidence": call,
                "nextEvidence": "Inspect route prefixes, generated routes and live backend before fixing.",
            })
            continue
        supported = sorted({method for item in path_matches for method in item["methods"]})
        if call["method"] not in supported:
            findings.append({
                "severity": "P1",
                "family": "CONTRACT_METHOD_DRIFT",
                "status": "STATIC_CANDIDATE",
                "what": f"{call['path']} exists but does not expose {call['method']} in static evidence",
                "evidence": {"call": call, "backendMethods": supported, "backendRoutes": path_matches[:8]},
                "nextEvidence": "Verify framework prefixes and the real route table before mutation.",
            })
    for workflow in snapshot["workflows"]:
        if workflow.get("recognizedExtension") is False:
            findings.append({
                "severity": "P2",
                "family": "CI_DEAD_CHECK",
                "status": "STATIC_CANDIDATE",
                "what": f"Workflow file has an unsupported extension: {workflow['path']}",
                "evidence": workflow,
            })
        elif workflow.get("validYaml") is False:
            findings.append({
                "severity": "P0",
                "family": "CI_DEAD_CHECK",
                "status": "STATIC_CANDIDATE",
                "what": f"Workflow cannot be parsed as a jobs-bearing YAML mapping: {workflow['path']}",
                "evidence": workflow,
                "nextEvidence": "Run the repository workflow contract and bind the result to the exact head SHA.",
            })
        elif workflow.get("parserAvailable") is False:
            findings.append({
                "severity": "P2",
                "family": "CI_PARSER_UNAVAILABLE",
                "status": "TOOL_LIMITATION",
                "what": f"YAML parser unavailable for {workflow['path']}",
                "evidence": workflow,
            })
    for item in snapshot["llmToolBoundaryCandidates"]:
        findings.append({
            "severity": "P1",
            "family": "LLM_TOOL_BOUNDARY",
            "status": "STATIC_CANDIDATE",
            "what": f"Possible free-language interpretation in {item['file']}:{item['line']}",
            "evidence": item,
            "nextEvidence": "Review whether this is an explicitly marked offline fallback or structured enum handling.",
        })
    for item in snapshot["parserFindings"]:
        findings.append({
            "severity": "P1",
            "family": item.get("classification") or "PYTHON_PARSE_FAILURE",
            "status": "STATIC_CANDIDATE",
            "what": f"Python parser could not parse {item['path']} at line {item.get('line', 0)}",
            "evidence": item,
            "nextEvidence": "Compare repository Python target version with the MCP interpreter before changing source.",
        })
    for pair in snapshot["mirrorPairs"]:
        if pair.get("byteEqual") is False:
            findings.append({
                "severity": "P1",
                "family": "CANONICAL_DEPLOYMENT_MIRROR_DRIFT",
                "status": "STATIC_CANDIDATE",
                "what": f"Mirrored backend files differ: {pair['source']} vs {pair['mirror']}",
                "evidence": pair,
                "nextEvidence": "Identify the canonical producer and run mirror contract tests before synchronization.",
            })
    severity_order = {"P0": 0, "P1": 1, "P2": 2}
    findings.sort(key=lambda item: (severity_order.get(item["severity"], 9), item["family"], item["what"]))
    counts = Counter(item["severity"] for item in findings)
    return {
        "schemaVersion": "sovereign.architecture-drift.v1",
        "snapshotSha256": snapshot["snapshotSha256"],
        "revision": snapshot["revision"],
        "findingCount": len(findings),
        "counts": {severity: counts.get(severity, 0) for severity in ("P0", "P1", "P2")},
        "findings": findings[:_MAX_RESULT_ITEMS],
        "truncated": len(findings) > _MAX_RESULT_ITEMS,
        "persistedOutcome": None,
        "mutationPerformed": False,
        "truthNotice": "Static candidates are not runtime findings. Confirm each with bounded repository, CI, database or VPS evidence.",
    }


def _architecture_runtime_drift_evidence(repo: Path) -> dict[str, Any]:
    snapshot = _architecture_snapshot(repo)
    if _DATABASE is None:
        return {
            "ok": False,
            "status": "POSTGRES_RUNTIME_NOT_REGISTERED",
            "snapshotSha256": snapshot["snapshotSha256"],
            "revision": snapshot["revision"],
            "findings": [],
            "mutationPerformed": False,
            "rowDataReturned": False,
            "secretValuesExposed": False,
        }
    try:
        schema = _DATABASE.schema_inventory()
        vector = _DATABASE.vector_canary()
    except Exception as exc:
        return {
            "ok": False,
            "status": "POSTGRES_RUNTIME_EVIDENCE_BLOCKED",
            "snapshotSha256": snapshot["snapshotSha256"],
            "revision": snapshot["revision"],
            "blocker": type(exc).__name__,
            "findings": [],
            "mutationPerformed": False,
            "rowDataReturned": False,
            "secretValuesExposed": False,
        }
    repository_tables = {
        (str(item.get("schema") or "public"), str(item.get("table") or ""))
        for item in snapshot["sqlTables"]
        if str(item.get("table") or "")
    }
    live_tables = {
        (str(item.get("table_schema") or ""), str(item.get("table_name") or ""))
        for item in (schema.get("tables") if isinstance(schema.get("tables"), list) else [])
        if isinstance(item, dict)
        and str(item.get("table_schema") or "")
        and str(item.get("table_name") or "")
    }
    findings: list[dict[str, Any]] = []
    for table_schema, table_name in sorted(repository_tables - live_tables):
        findings.append({
            "severity": "P1",
            "family": "DB_DRIFT_MISSING_LIVE_TABLE",
            "status": "RUNTIME_EVIDENCE",
            "what": f"Migration-defined table is absent from live schema: {table_schema}.{table_name}",
        })
    for table_schema, table_name in sorted(live_tables - repository_tables):
        findings.append({
            "severity": "P2",
            "family": "DB_DRIFT_UNMAPPED_LIVE_TABLE",
            "status": "RUNTIME_EVIDENCE",
            "what": f"Live table has no statically discovered CREATE TABLE migration: {table_schema}.{table_name}",
            "nextEvidence": "Check bootstrap, extension, Supabase or historical migration ownership before changing schema.",
        })
    if "pgvector" in snapshot.get("knowledgeTechnologies", []) and not vector.get("ok"):
        findings.append({
            "severity": "P1",
            "family": "VECTOR_RUNTIME_DRIFT",
            "status": "RUNTIME_EVIDENCE",
            "what": "Repository references pgvector but the live vector canary did not verify the extension.",
        })
    severity_order = {"P0": 0, "P1": 1, "P2": 2}
    findings.sort(key=lambda item: (severity_order.get(item["severity"], 9), item["family"], item["what"]))
    return {
        "ok": bool(schema.get("ok")),
        "status": "ARCHITECTURE_RUNTIME_DRIFT_EVIDENCE_READY" if schema.get("ok") else "ARCHITECTURE_RUNTIME_DRIFT_EVIDENCE_BLOCKED",
        "snapshotSha256": snapshot["snapshotSha256"],
        "revision": snapshot["revision"],
        "repositoryMigrationTableCount": len(repository_tables),
        "liveTableCount": len(live_tables),
        "schemaInventory": schema,
        "vectorEvidence": vector,
        "findings": findings[:_MAX_RESULT_ITEMS],
        "truncated": len(findings) > _MAX_RESULT_ITEMS,
        "mutationPerformed": False,
        "rowDataReturned": False,
        "secretValuesExposed": False,
        "truthNotice": "Live schema names are runtime evidence; table ownership and intended migrations still require review.",
    }


def _scan(repo: Path, *, include_logic: bool) -> dict[str, Any]:
    files = _tracked_files(repo)
    mapped = 0
    language_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    class_counts: Counter[str] = Counter()
    knowledge_evidence: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    endpoints: list[dict[str, Any]] = []
    env_names: set[str] = set()
    sensitive_locations: list[dict[str, Any]] = []
    sensitive_marker_count = 0
    routes: list[dict[str, Any]] = []
    symbols: list[dict[str, Any]] = []
    parser_findings: list[dict[str, Any]] = []
    import_edges: list[dict[str, Any]] = []
    call_candidates: list[tuple[str, str]] = []
    symbol_locations: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    knowledge_files: list[dict[str, Any]] = []
    tracked = set(files)

    for relative in files:
        if relative.startswith(_SKIP_PREFIXES):
            continue
        suffix = PurePosixPath(relative).suffix.casefold()
        if suffix not in _TEXT_SUFFIXES:
            continue
        text = _safe_text(repo / relative)
        if text is None:
            continue
        mapped += 1
        language = _language(relative)
        language_counts[language] += 1
        file_roles = _roles(relative)
        role_counts.update(file_roles)
        path_class = _path_class(relative)
        class_counts[path_class] += 1
        for line_no, line in enumerate(text.splitlines(), 1):
            if _SECRET_MARKER.search(line):
                sensitive_marker_count += 1
                if len(sensitive_locations) < _MAX_RESULT_ITEMS:
                    sensitive_locations.append({"path": relative, "line": line_no, "valueReturned": False})
        matched_technologies: list[str] = []
        for technology, pattern in _KNOWLEDGE_PATTERNS.items():
            matches = list(pattern.finditer(text))
            if matches:
                matched_technologies.append(technology)
                if len(knowledge_evidence[technology]) < 40:
                    knowledge_evidence[technology].append({
                        "path": relative,
                        "lines": sorted({text.count("\n", 0, match.start()) + 1 for match in matches})[:20],
                    })
        if matched_technologies or _KNOWLEDGE_PATH.search(relative):
            if len(knowledge_files) < _MAX_RESULT_ITEMS:
                knowledge_files.append({
                    "path": relative,
                    "pathClass": path_class,
                    "roles": file_roles,
                    "technologies": matched_technologies,
                })
        for match in _ENDPOINT_HINT.finditer(text):
            endpoint = _safe_endpoint(match.group(1))
            if len(endpoints) < _MAX_RESULT_ITEMS:
                endpoints.append({"path": relative, "line": text.count("\n", 0, match.start()) + 1, "endpoint": endpoint})
        env_names.update(_ENV_NAME.findall(text))
        if not include_logic:
            continue
        file_routes = _routes(text)
        for route in file_routes:
            if len(routes) < _MAX_RESULT_ITEMS:
                routes.append({"file": relative, **route})
        parse_finding: dict[str, Any] | None = None
        if language == "python":
            file_symbols, imports, calls, parse_finding = _python_symbols(text)
        elif language.startswith(("typescript", "javascript")):
            file_symbols, imports, calls = _js_symbols(text)
        else:
            file_symbols, imports, calls = [], [], []
        if parse_finding is not None and len(parser_findings) < _MAX_RESULT_ITEMS:
            parser_findings.append({"path": relative, **parse_finding})
        for symbol in file_symbols:
            symbol_locations[symbol["name"]].append({"file": relative, "line": symbol["line"]})
            if len(symbols) < _MAX_RESULT_ITEMS:
                symbols.append({"file": relative, **symbol})
        for called in calls[:200]:
            if len(call_candidates) < 5_000:
                call_candidates.append((relative, called))
        for imported in imports[:100]:
            if not imported.startswith("."):
                continue
            base = PurePosixPath(relative).parent
            parts: list[str] = []
            for part in (base / imported).parts:
                if part == ".." and parts:
                    parts.pop()
                elif part not in {".", ".."}:
                    parts.append(part)
            root = "/".join(parts)
            candidates = [root, *(root + ext for ext in (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs")), *(root + "/index" + ext for ext in (".ts", ".tsx", ".js", ".jsx"))]
            target = next((candidate for candidate in candidates if candidate in tracked), None)
            if target and len(import_edges) < _MAX_RESULT_ITEMS:
                import_edges.append({"source": relative, "target": target, "confidence": "static"})

    call_edges: list[dict[str, Any]] = []
    for source, called in call_candidates:
        locations = symbol_locations.get(called, [])
        if len(locations) == 1 and len(call_edges) < _MAX_RESULT_ITEMS:
            target = locations[0]
            call_edges.append({
                "source": source,
                "target": target["file"],
                "targetLine": target["line"],
                "symbol": called,
                "confidence": "unique_name_hint",
            })
    package_scripts: dict[str, str] = {}
    for relative in sorted(path for path in tracked if path.endswith("package.json")):
        try:
            payload = json.loads((repo / relative).read_text("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        scripts = payload.get("scripts") if isinstance(payload, dict) else None
        if not isinstance(scripts, dict):
            continue
        for name, command in scripts.items():
            if len(package_scripts) >= _MAX_RESULT_ITEMS:
                break
            package_scripts[f"{relative}:{name}"] = str(command)[:500]

    revision = _git(repo, "rev-parse", "HEAD")
    return {
        "schemaVersion": "sovereign.repository-analysis.v1",
        "repository": str(repo),
        "revision": revision,
        "dirty": bool(_git(repo, "status", "--porcelain")),
        "truthNotice": "Static discovery only; runtime use is not proven.",
        "summary": {
            "trackedFiles": len(files),
            "mappedTextFiles": mapped,
            "languages": dict(language_counts.most_common()),
            "roles": dict(role_counts.most_common()),
            "pathClasses": dict(class_counts.most_common()),
            "knowledgeTechnologies": len(knowledge_evidence),
            "knowledgeEndpointCandidates": len(endpoints),
            "sensitiveMarkerCount": sensitive_marker_count,
        },
        "knowledgeEvidence": dict(sorted(knowledge_evidence.items())),
        "knowledgeEndpointCandidates": endpoints,
        "knowledgeFiles": knowledge_files,
        "environmentVariableNames": sorted(env_names)[:_MAX_RESULT_ITEMS],
        "sensitiveMarkerLocations": sensitive_locations,
        "sensitiveValuesReturned": False,
        "databaseAccessed": False,
        "logic": ({
            "routes": routes,
            "symbols": symbols,
            "importEdges": import_edges,
            "uniqueCallEdges": call_edges,
            "packageScripts": package_scripts,
            "parserFindings": parser_findings,
        } if include_logic else None),
        "limitations": [
            "Static import, symbol and route evidence is not runtime proof.",
            "Dynamic imports, reflection, generated code and dependency injection require separate runtime evidence.",
            "Large and binary files are not deeply parsed.",
        ],
    }


def _safe_ref(value: str, *, field: str) -> str:
    selected = str(value or "").strip()
    if not selected:
        return ""
    if not _ALLOWED_REF.fullmatch(selected) or selected.startswith("-"):
        raise ValueError(f"{field} is not a safe Git ref")
    return selected


def _safe_changed_path(value: str) -> str:
    normalized = str(value or "").strip().replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    pure = PurePosixPath(normalized)
    if not normalized or pure.is_absolute() or ".." in pure.parts or any(part in {".git", ".env", "node_modules"} for part in pure.parts):
        raise ValueError("changed path is unsafe")
    return pure.as_posix()


def _changed_paths(repo: Path, base: str, head: str, paths: list[str]) -> list[str]:
    explicit = sorted({_safe_changed_path(path) for path in paths if str(path or "").strip()})
    if explicit:
        return explicit[:500]
    selected_base = _safe_ref(base, field="base")
    selected_head = _safe_ref(head, field="head") or "HEAD"
    if selected_base:
        return sorted(set(_git(repo, "diff", "--name-only", selected_base, selected_head, "--").splitlines()))[:500]
    working = set(_git(repo, "diff", "--name-only", "--").splitlines())
    working.update(_git(repo, "diff", "--cached", "--name-only", "--").splitlines())
    working.update(_git(repo, "ls-files", "--others", "--exclude-standard").splitlines())
    if working:
        return sorted(working)[:500]
    parents = _git(repo, "rev-list", "--parents", "-n", "1", "HEAD").split()
    if len(parents) > 1:
        return sorted(set(_git(repo, "diff", "--name-only", "HEAD^", "HEAD", "--").splitlines()))[:500]
    return []


def _domains(path: str) -> list[str]:
    lowered = path.casefold()
    found = [domain for domain, patterns in _DOMAIN_PATTERNS if any(pattern in lowered for pattern in patterns)]
    return found or ["unclassified"]


def _mirrors(repo: Path, path: str) -> list[dict[str, Any]]:
    candidates: list[str] = []
    if path.startswith("backend/"):
        relative = path.removeprefix("backend/")
        candidates.append("scripts/sovereign-backend/" + relative)
    elif path.startswith("scripts/sovereign-backend/"):
        relative = path.removeprefix("scripts/sovereign-backend/")
        candidates.append("backend/" + relative)
    if path.startswith("deploy/sovereign-litellm/"):
        candidates.append("tools/sovereign-chatgpt-mcp/templates/sovereign-litellm/" + path.removeprefix("deploy/sovereign-litellm/"))
    elif path.startswith("tools/sovereign-chatgpt-mcp/templates/sovereign-litellm/"):
        candidates.append("deploy/sovereign-litellm/" + path.removeprefix("tools/sovereign-chatgpt-mcp/templates/sovereign-litellm/"))
    source = repo / path
    output = []
    for candidate in candidates:
        target = repo / candidate
        output.append({
            "path": candidate,
            "exists": target.is_file(),
            "byteEqual": bool(source.is_file() and target.is_file() and source.read_bytes() == target.read_bytes()),
        })
    return output


def _impact(repo: Path, *, base: str = "", head: str = "", paths: list[str] | None = None) -> dict[str, Any]:
    changed = _changed_paths(repo, base, head, paths or [])
    entries = []
    all_domains: list[str] = []
    for path in changed:
        domains = _domains(path)
        all_domains.extend(domains)
        entries.append({"path": path, "domains": domains, "mirrors": _mirrors(repo, path)})
    selected_domains = list(dict.fromkeys(all_domains))
    gates = list(dict.fromkeys(gate for domain in selected_domains for gate in _GATES_BY_DOMAIN.get(domain, ())))
    return {
        "schemaVersion": "sovereign.change-impact.v1",
        "headSha": _git(repo, "rev-parse", _safe_ref(head, field="head") or "HEAD"),
        "base": _safe_ref(base, field="base") or None,
        "changedFileCount": len(changed),
        "domains": selected_domains,
        "files": entries,
        "requiredGates": gates,
        "alwaysRequired": [
            "inspect open Draft PRs",
            "inspect unresolved review threads",
            "bind CI conclusions to exact head SHA",
            "check secret-shaped material",
            "separate historical tasks from active blockers",
        ],
        "truthNotice": "Change impact selects evidence to inspect; it does not prove a gate passed.",
    }


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _clean_list(value: Any, *, lower: bool = False) -> list[str]:
    values = value if isinstance(value, list) else ([] if value in (None, "") else [value])
    cleaned = {_clean_text(item) for item in values if _clean_text(item)}
    if lower:
        cleaned = {item.casefold().replace(" ", "-") for item in cleaned}
    return sorted(cleaned)


def _source_ref(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("each source_refs entry must be an object")
    result = {key: _clean_text(value.get(key)) for key in ("repository", "revision", "path", "lines", "license")}
    for field in ("repository", "revision", "path", "license"):
        if not result[field]:
            raise ValueError(f"source_refs.{field} is required")
    return result


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {"schema_version": "knowledge-pattern.v1"}
    for field in _REQUIRED_TEXT:
        normalized[field] = _clean_text(record.get(field))
        if not normalized[field]:
            raise ValueError(f"{field} is required")
    normalized["context"] = _clean_text(record.get("context"))
    for field in _LIST_FIELDS:
        normalized[field] = _clean_list(record.get(field), lower=field == "tags")
    if not normalized["validation"]:
        raise ValueError("validation must contain at least one concrete check")
    refs = record.get("source_refs")
    if not isinstance(refs, list) or not refs:
        raise ValueError("source_refs must contain at least one source")
    normalized["source_refs"] = sorted((_source_ref(item) for item in refs), key=lambda item: (item["repository"], item["revision"], item["path"], item["lines"]))
    try:
        confidence = float(record.get("confidence", 0.0))
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence must be numeric") from exc
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    normalized["confidence"] = round(confidence, 6)
    serialized = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if _SECRET_MARKER.search(serialized):
        raise ValueError("record contains a secret-like marker")
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    pattern_id = _clean_text(record.get("pattern_id")) or f"pattern:{digest[:24]}"
    if _SECRET_MARKER.search(pattern_id):
        raise ValueError("pattern_id contains a secret-like marker")
    normalized["pattern_id"] = pattern_id
    normalized["embedding_text"] = "\n".join(filter(None, (
        f"Title: {normalized['title']}",
        f"Problem: {normalized['problem']}",
        f"Context: {normalized['context']}" if normalized["context"] else "",
        f"Triggers: {'; '.join(normalized['triggers'])}" if normalized["triggers"] else "",
        f"Preconditions: {'; '.join(normalized['preconditions'])}" if normalized["preconditions"] else "",
        f"Solution: {normalized['solution']}",
        f"Invariants: {'; '.join(normalized['invariants'])}" if normalized["invariants"] else "",
        f"Failure modes: {'; '.join(normalized['failure_modes'])}" if normalized["failure_modes"] else "",
        f"Validation: {'; '.join(normalized['validation'])}",
        f"Applicability: {normalized['applicability']}",
        f"Exclusions: {'; '.join(normalized['exclusions'])}" if normalized["exclusions"] else "",
    )))
    normalized["content_hash"] = f"sha256:{digest}"
    if _SECRET_MARKER.search(json.dumps(normalized, ensure_ascii=False, sort_keys=True)):
        raise ValueError("normalized record contains a secret-like marker")
    return normalized


def repository_skill_tool_inventory() -> dict[str, Any]:
    """List the installed repository-analysis skill tools and their mutation boundaries."""
    return {
        "ok": True,
        "status": "REPOSITORY_SKILL_TOOLS_READY",
        "tools": [
            {"name": "repository_knowledge_surface_scan", "sourceSkill": "forge-repository-knowledge", "mutates": False},
            {"name": "repository_product_logic_map", "sourceSkill": "repository-growth-campaign-operator", "mutates": False},
            {"name": "repository_change_impact_manifest", "sourceSkill": "sovereign-truth-chain-operator", "mutates": False},
            {"name": "repository_learning_records_normalize_preview", "sourceSkill": "forge-repository-knowledge", "mutates": False},
            {"name": "repository_release_hunt_manifest", "sourceSkill": "sovereign-release-hunter", "mutates": False},
            {"name": "repository_architecture_snapshot", "sourceSkill": "sovereign-architecture-guardian", "mutates": False},
            {"name": "repository_architecture_drift_report", "sourceSkill": "sovereign-architecture-guardian", "mutates": False},
            {"name": "repository_architecture_runtime_drift_evidence", "sourceSkill": "sovereign-architecture-guardian", "mutates": False},
        ],
        "truthBoundary": "Static maps and ranked candidates are not runtime success. The runtime-drift tool reads schema metadata and vector canaries only; it never returns table rows or mutates PostgreSQL.",
        "databaseAccessed": False,
        "secretsReturned": False,
    }


def repository_knowledge_surface_scan(workspace_id: str) -> dict[str, Any]:
    """Map knowledge, vector, embedding, learning and endpoint surfaces in one isolated workspace."""
    return _scan(_repo(workspace_id), include_logic=False)


def repository_product_logic_map(workspace_id: str) -> dict[str, Any]:
    """Map bounded product roles, routes, symbols and local import edges in one isolated workspace."""
    return _scan(_repo(workspace_id), include_logic=True)


def repository_change_impact_manifest(
    workspace_id: str,
    base: str = "",
    head: str = "",
    paths: list[str] | None = None,
) -> dict[str, Any]:
    """Build a deterministic cross-layer impact and relevant-gate manifest for changed paths."""
    return _impact(_repo(workspace_id), base=base, head=head, paths=paths)


def repository_architecture_snapshot(workspace_id: str) -> dict[str, Any]:
    """Capture one deterministic static architecture snapshot for an isolated workspace."""
    return _architecture_snapshot(_repo(workspace_id))


def repository_architecture_drift_report(workspace_id: str) -> dict[str, Any]:
    """Find bounded static contract, workflow, parser, mirror and LLM/tool-boundary drift candidates."""
    return _architecture_drift_report(_repo(workspace_id))


def repository_architecture_runtime_drift_evidence(workspace_id: str) -> dict[str, Any]:
    """Compare repository migration metadata with bounded live PostgreSQL and vector evidence."""
    return _architecture_runtime_drift_evidence(_repo(workspace_id))


def repository_learning_records_normalize_preview(
    workspace_id: str,
    input_path: str,
    max_records: int = 50,
) -> dict[str, Any]:
    """Normalize a bounded JSON/JSONL pattern dataset without database access or repository writes."""
    repo = _repo(workspace_id)
    path = safe_repo_path(repo, input_path, must_exist=True)
    if path.suffix.casefold() not in {".json", ".jsonl"}:
        raise ValueError("input_path must be JSON or JSONL")
    if path.stat().st_size > 600_000:
        raise ValueError("pattern input exceeds the bounded size limit")
    text = path.read_text("utf-8")
    if path.suffix.casefold() == ".jsonl":
        raw = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        parsed = json.loads(text)
        raw = parsed if isinstance(parsed, list) else parsed.get("records", []) if isinstance(parsed, dict) else []
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise ValueError("input must contain a list of JSON objects")
    limit = max(1, min(int(max_records), _MAX_NORMALIZE_RECORDS))
    if len(raw) > limit:
        raise ValueError(f"input contains more than the allowed {limit} records")
    unique: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    for index, record in enumerate(raw, 1):
        try:
            normalized = _normalize_record(record)
        except ValueError as exc:
            errors.append({"record": index, "error": str(exc)[:240]})
            continue
        unique.setdefault(normalized["content_hash"], normalized)
    ordered = sorted(unique.values(), key=lambda item: (item["pattern_id"], item["content_hash"]))
    return {
        "ok": not errors,
        "status": "NORMALIZATION_PREVIEW_READY" if not errors else "NORMALIZATION_PREVIEW_BLOCKED",
        "inputPath": input_path,
        "inputRecords": len(raw),
        "outputRecords": len(ordered),
        "duplicatesRemoved": len(raw) - len(ordered) - len(errors),
        "errors": errors,
        "records": ordered,
        "databaseAccessed": False,
        "embeddingsGenerated": False,
        "repositoryWritten": False,
        "secretsReturned": False,
    }


def repository_release_hunt_manifest(
    workspace_id: str,
    base: str = "",
    head: str = "",
    paths: list[str] | None = None,
) -> dict[str, Any]:
    """Rank release-hunt failure-family candidates from current repository impact without persisting a hunt result."""
    impact = _impact(_repo(workspace_id), base=base, head=head, paths=paths)
    ranked: list[dict[str, Any]] = []
    seen: set[str] = set()
    for domain in impact["domains"]:
        for family in _FAILURE_FAMILIES_BY_DOMAIN.get(domain, ()):
            if family in seen:
                continue
            seen.add(family)
            ranked.append({
                "failureFamily": family,
                "domain": domain,
                "reason": f"Changed paths intersect the {domain} truth plane.",
                "status": "CANDIDATE_NOT_EXECUTED",
            })
    return {
        "schemaVersion": "sovereign.release-hunt-manifest.v1",
        "headSha": impact["headSha"],
        "impact": impact,
        "rankedFailureFamilies": ranked[:24],
        "persistedOutcome": None,
        "nullfindCounterChanged": False,
        "truthNotice": "This tool ranks candidates only. FINDING, NULLFIND or BLOCKED must come from a persisted real hunt run.",
    }


def register(mcp: Any, runtime: Any, database: Any = None) -> None:
    global _RUNTIME, _DATABASE, _REGISTERED
    _RUNTIME = runtime
    _DATABASE = database
    if _REGISTERED:
        return
    for tool in (
        repository_skill_tool_inventory,
        repository_knowledge_surface_scan,
        repository_product_logic_map,
        repository_change_impact_manifest,
        repository_architecture_snapshot,
        repository_architecture_drift_report,
        repository_architecture_runtime_drift_evidence,
        repository_learning_records_normalize_preview,
        repository_release_hunt_manifest,
    ):
        mcp.tool(annotations=READ_ONLY)(tool)
    _REGISTERED = True
