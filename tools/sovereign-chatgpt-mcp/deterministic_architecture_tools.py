from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any, Final, Sequence

from mcp.types import ToolAnnotations

from deterministic_contract import KAPPA_SCALE, replay_verify, transition_preview


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

_MAX_TRACKED_FILES: Final[int] = 30_000
_MAX_TEXT_BYTES: Final[int] = 1_200_000
_MAX_FINDINGS: Final[int] = 240
_TEXT_SUFFIXES: Final[frozenset[str]] = frozenset({
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".sql", ".json", ".jsonl", ".yml", ".yaml", ".toml", ".md",
})
_SKIP_PREFIXES: Final[tuple[str, ...]] = (
    ".git/", "node_modules/", "vendor/", "dist/", "build/", "coverage/",
    "target/", ".gradle/", ".next/", ".venv/", "venv/", "__pycache__/",
    "playwright-report/", "test-results/", "android/app/build/", "android/.gradle/",
)

_RUNTIME: Any = None
_REGISTERED = False


@dataclass(frozen=True, slots=True)
class Finding:
    severity: str
    family: str
    path: str
    line: int
    description: str
    recommendation: str
    surface: str

    def payload(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "family": self.family,
            "path": self.path,
            "line": self.line,
            "description": self.description,
            "recommendation": self.recommendation,
            "surface": self.surface,
            "status": "STATIC_CANDIDATE",
        }


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
        raise RuntimeError("Deterministic architecture tools are not registered")
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


def _is_test(path: str) -> bool:
    lowered = path.casefold()
    return any(marker in lowered for marker in (
        "/tests/", "/test/", "__tests__/", ".test.", ".spec.", "fixture", "e2e/",
    )) or PurePosixPath(path).name.startswith("test_")


def _path_class(path: str) -> str:
    lowered = path.casefold()
    if path.startswith(_SKIP_PREFIXES) or any(marker in lowered for marker in ("generated/", ".min.", "package-lock.json")):
        return "GENERATED"
    if _is_test(path):
        return "TEST_ONLY"
    if any(marker in lowered for marker in ("legacy", "deprecated", "archive", "obsolete")):
        return "LEGACY"
    if any(marker in lowered for marker in ("demo", "example", "prototype", "experiment", "poc/")):
        return "EXPERIMENTAL"
    return "PRODUCTION_CANDIDATE"


def _surface(path: str, text: str) -> str:
    path_class = _path_class(path)
    if path_class != "PRODUCTION_CANDIDATE":
        return path_class
    lowered = path.casefold()
    content = text.casefold()
    if any(marker in lowered for marker in ("migration", "database", "schema", "run_store", "event_store")):
        return "PERSISTED_TRUTH"
    if any(marker in lowered for marker in ("adapter", "bridge", "client", "route", "controller", "broker")):
        return "EFFECT_ADAPTER"
    if any(marker in content for marker in ("requests.", "fetch(", "axios.", "subprocess.", "psycopg", "socket.")):
        return "EFFECT_ADAPTER"
    if any(marker in lowered for marker in ("component", "page", "view", "widget", "screen")):
        return "RUNTIME_PROJECTION"
    if any(marker in lowered for marker in ("runtime", "predictive", "reducer", "evolution", "policy", "kappa")):
        return "PURE_CORE_CANDIDATE"
    return "UNCLASSIFIED_PRODUCTION"


def _bounded_files(repo: Path) -> list[tuple[str, str, str]]:
    output: list[tuple[str, str, str]] = []
    for relative in _tracked_files(repo):
        if relative.startswith(_SKIP_PREFIXES):
            continue
        if PurePosixPath(relative).suffix.casefold() not in _TEXT_SUFFIXES:
            continue
        text = _safe_text(repo / relative)
        if text is not None:
            output.append((relative, text, _surface(relative, text)))
    return output


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


def _sort_findings(findings: Sequence[Finding], limit: int) -> list[dict[str, Any]]:
    severity_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    ordered = sorted(findings, key=lambda item: (
        severity_order.get(item.severity, 9), item.family, item.path, item.line, item.description,
    ))
    return [item.payload() for item in ordered[:max(1, min(int(limit), _MAX_FINDINGS))]]


def _architecture_inventory(repo: Path) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    surfaces: Counter[str] = Counter()
    classes: Counter[str] = Counter()
    for path, text, surface in _bounded_files(repo):
        surfaces[surface] += 1
        classes[_path_class(path)] += 1
        if len(entries) < _MAX_FINDINGS:
            entries.append({
                "path": path,
                "surface": surface,
                "pathClass": _path_class(path),
                "language": PurePosixPath(path).suffix.casefold().lstrip(".") or "unknown",
                "bytes": len(text.encode("utf-8")),
            })
    return {
        "schemaVersion": "sovereign.deterministic-architecture-inventory.v1",
        "revision": _git(repo, "rev-parse", "HEAD"),
        "dirty": bool(_git(repo, "status", "--porcelain")),
        "kappaScale": KAPPA_SCALE,
        "surfaceCounts": dict(sorted(surfaces.items())),
        "pathClassCounts": dict(sorted(classes.items())),
        "surfaces": entries,
        "truncated": sum(surfaces.values()) > len(entries),
        "mutationPerformed": False,
        "runtimeSuccessClaimed": False,
        "truthNotice": "Static surface classification is orientation, not proof that a function is pure or active.",
    }


class _PythonVisitor(ast.NodeVisitor):
    def __init__(self, *, path: str, surface: str) -> None:
        self.path = path
        self.surface = surface
        self.findings: list[Finding] = []

    def add(self, node: ast.AST, severity: str, family: str, description: str, recommendation: str) -> None:
        self.findings.append(Finding(
            severity,
            family,
            self.path,
            max(1, int(getattr(node, "lineno", 1) or 1)),
            description,
            recommendation,
            self.surface,
        ))

    def visit_Global(self, node: ast.Global) -> None:
        self.add(
            node,
            "P1",
            "IMPLICIT_MUTABLE_STATE",
            "Python global statement can hide mutable runtime state.",
            "Pass state explicitly through an ARE reducer or isolate it in an effect adapter.",
        )
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, float) and self.surface in {
            "PURE_CORE_CANDIDATE", "PERSISTED_TRUTH", "UNCLASSIFIED_PRODUCTION",
        }:
            self.add(
                node,
                "P1",
                "FLOAT_IN_TRUTH_PATH",
                "Floating-point literal appears in a potential truth path.",
                "Use scaled integers or canonical decimal text at the boundary.",
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = self._name(node.func).casefold()
        rules = (
            (("random.", "secrets.", "os.urandom"), "RANDOMNESS_IN_TRUTH_PATH", "Random source is used.", "Persist entropy as Action evidence or derive a stable digest-based value."),
            (("datetime.now", "datetime.utcnow", "date.today", "time.time", "time.monotonic"), "IMPLICIT_TIME_SOURCE", "System clock is read directly.", "Inject observed time as persisted evidence and keep it out of pure evolution."),
            (("uuid.uuid4", "uuid4"), "NON_DETERMINISTIC_IDENTIFIER", "Random UUID generation is used.", "Use a stable digest-derived ID or a persisted external ID."),
            (("hash",), "PROCESS_LOCAL_HASH", "Python hash() is process-randomized for strings and bytes.", "Use SHA-256 or another versioned stable digest."),
            (("open", "requests.", "httpx.", "urllib.", "subprocess.", "socket."), "EFFECT_INSIDE_LOGIC", "Filesystem, network or process effect appears in source.", "Keep effects outside the pure reducer and return observations as new Actions."),
        )
        for markers, family, description, recommendation in rules:
            if any(name == marker or name.startswith(marker) for marker in markers):
                severity = "P2" if self.surface in {"EFFECT_ADAPTER", "TEST_ONLY", "RUNTIME_PROJECTION"} else "P1"
                self.add(node, severity, family, description, recommendation)
                break
        self.generic_visit(node)

    @staticmethod
    def _name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parts: list[str] = []
            current: ast.AST | None = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return ""


def _python_findings(path: str, text: str, surface: str) -> list[Finding]:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [Finding(
            "P1",
            "PYTHON_PARSE_FAILURE",
            path,
            max(1, int(exc.lineno or 1)),
            "Python source could not be parsed by the MCP interpreter.",
            "Confirm the repository target Python version before changing source.",
            surface,
        )]
    visitor = _PythonVisitor(path=path, surface=surface)
    visitor.visit(tree)
    return visitor.findings


_TEXT_RULES: Final[tuple[tuple[re.Pattern[str], str, str, str], ...]] = (
    (re.compile(r"\bMath\.random\s*\("), "RANDOMNESS_IN_TRUTH_PATH", "Math.random() is process-local entropy.", "Persist entropy as Action evidence or derive a stable digest-based value."),
    (re.compile(r"\bDate\.now\s*\(|\bnew\s+Date\s*\("), "IMPLICIT_TIME_SOURCE", "Wall-clock time is read directly.", "Inject observed time as persisted evidence."),
    (re.compile(r"\bcrypto\.randomUUID\s*\("), "NON_DETERMINISTIC_IDENTIFIER", "A random UUID is generated.", "Use a stable digest-derived ID or a persisted external ID."),
    (re.compile(r"\bset(?:Timeout|Interval)\s*\("), "TIMER_DRIVEN_STATE", "Timer-driven execution can introduce ordering drift.", "Use persisted actions and explicit scheduler evidence for truth transitions."),
    (re.compile(r"\b(?:fetch|axios\.[A-Za-z]+)\s*\("), "EFFECT_INSIDE_LOGIC", "Network effect appears in source.", "Keep the call in an effect adapter and feed its result back as evidence."),
    (re.compile(r"\blocalStorage\.|\bsessionStorage\."), "BROWSER_LOCAL_TRUTH", "Browser storage is referenced.", "Do not use browser-local state as runtime truth."),
)


def _text_findings(path: str, text: str, surface: str) -> list[Finding]:
    output: list[Finding] = []
    for pattern, family, description, recommendation in _TEXT_RULES:
        for match in pattern.finditer(text):
            severity = "P2" if surface in {"EFFECT_ADAPTER", "TEST_ONLY", "RUNTIME_PROJECTION"} else "P1"
            output.append(Finding(
                severity,
                family,
                path,
                _line(text, match.start()),
                description,
                recommendation,
                surface,
            ))
    if surface in {"PURE_CORE_CANDIDATE", "PERSISTED_TRUTH", "UNCLASSIFIED_PRODUCTION"}:
        for match in re.finditer(r"(?<![\w.])-?[0-9]+\.[0-9]+(?![\w.])", text):
            output.append(Finding(
                "P1",
                "FLOAT_IN_TRUTH_PATH",
                path,
                _line(text, match.start()),
                "Decimal numeric literal appears in a potential TypeScript/JavaScript truth path.",
                "Use bigint scaled units or canonical decimal text.",
                surface,
            ))
    return output


def _sql_findings(path: str, text: str, surface: str) -> list[Finding]:
    output: list[Finding] = []
    rules = (
        (re.compile(r"\b(?:RANDOM\s*\(|RAND\s*\(|NEWID\s*\(|UUID\s*\(|GEN_RANDOM_UUID\s*\()", re.I), "P1", "SQL_RANDOMNESS", "SQL uses a random or UUID function.", "Provide a persisted identifier through the Action contract."),
        (re.compile(r"\b(?:CURRENT_TIMESTAMP|CURRENT_DATE|NOW\s*\(|GETDATE\s*\()", re.I), "P1", "SQL_IMPLICIT_TIME", "SQL obtains wall-clock time implicitly.", "Pass observed time explicitly as a parameter."),
        (re.compile(r"\b(?:SERIAL|BIGSERIAL|AUTOINCREMENT|GENERATED\s+.*?\s+AS\s+IDENTITY)\b", re.I | re.S), "P2", "IMPLICIT_DATABASE_ID", "Schema uses an implicit generated sequence ID.", "Use explicit stable IDs for causal truth records or document metadata-only use."),
        (re.compile(r"\bINSERT\s+INTO\s+[A-Za-z_][\w.\"]*\s+VALUES\s*\(", re.I), "P1", "INSERT_WITHOUT_COLUMN_LIST", "INSERT omits an explicit column list.", "Declare every inserted column explicitly."),
    )
    for pattern, severity, family, description, recommendation in rules:
        for match in pattern.finditer(text):
            output.append(Finding(
                severity,
                family,
                path,
                _line(text, match.start()),
                description,
                recommendation,
                surface,
            ))
    for match in re.finditer(r"\bSELECT\b.*?\bLIMIT\s+[0-9]+", text, re.I | re.S):
        if re.search(r"\bORDER\s+BY\b", match.group(0), re.I) is None:
            output.append(Finding(
                "P1",
                "LIMIT_WITHOUT_ORDER_BY",
                path,
                _line(text, match.start()),
                "SELECT ... LIMIT has no explicit ORDER BY in the bounded statement fragment.",
                "Add a stable ORDER BY with a deterministic tie-breaker.",
                surface,
            ))
    return output


def _nondeterminism_scan(repo: Path, max_findings: int) -> dict[str, Any]:
    findings: list[Finding] = []
    scanned = 0
    for path, text, surface in _bounded_files(repo):
        suffix = PurePosixPath(path).suffix.casefold()
        if suffix in {".py", ".pyi"}:
            findings.extend(_python_findings(path, text, surface))
        elif suffix in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}:
            findings.extend(_text_findings(path, text, surface))
        elif suffix == ".sql":
            findings.extend(_sql_findings(path, text, surface))
        scanned += 1
    returned = _sort_findings(findings, max_findings)
    return {
        "schemaVersion": "sovereign.determinism-scan.v1",
        "revision": _git(repo, "rev-parse", "HEAD"),
        "scannedFiles": scanned,
        "findingCount": len(findings),
        "returnedFindingCount": len(returned),
        "countsByFamily": dict(sorted(Counter(item["family"] for item in returned).items())),
        "countsBySeverity": dict(sorted(Counter(item["severity"] for item in returned).items())),
        "findings": returned,
        "truncated": len(findings) > len(returned),
        "mutationPerformed": False,
        "runtimeSuccessClaimed": False,
        "truthNotice": "Static candidates require active-path confirmation; UI, tests and effect adapters can legitimately contain time, randomness or I/O.",
    }


_KAPPA_RULES: Final[tuple[tuple[re.Pattern[str], str, str, str], ...]] = (
    (re.compile(r"\bKAPPA(?:_SCALE)?\s*=\s*(?!1_?000_?000n?\b)([0-9_]+n?)"), "KAPPA_SCALE_DRIFT", "Kappa constant differs from 1,000,000.", "Use one versioned scale across all truth paths."),
    (re.compile(r"def\s+to_fixed\s*\([^)]*:\s*float"), "FLOAT_KAPPA_BOUNDARY", "Python Kappa conversion accepts float input.", "Accept canonical decimal text or scaled integers."),
    (re.compile(r"\bround\s*\([^)]*\*\s*KAPPA"), "ROUND_BASED_KAPPA_CONVERSION", "Kappa conversion depends on rounded float input.", "Parse decimal text exactly and use the shared truncation rule."),
    (re.compile(r"Math\.floor\s*\(\s*\([^)]*\*[^)]*\)\s*/\s*KAPPA"), "JS_NUMBER_KAPPA_MULTIPLICATION", "JavaScript number multiplication can exceed safe integers and differs for negative rounding.", "Use bigint and shared truncation-toward-zero semantics."),
    (re.compile(r"\bconst\s+KAPPA(?:_SCALE)?\s*=\s*1_?000_?000\s*;"), "JS_NUMBER_KAPPA_CONSTANT", "Kappa scale is represented as JavaScript number.", "Use 1_000_000n for deterministic arithmetic."),
    (re.compile(r"return\s+value\s*/\s*KAPPA"), "FLOAT_KAPPA_OUTPUT", "Kappa conversion returns floating-point output.", "Return canonical decimal text or keep scaled integers."),
)


def _kappa_audit(repo: Path, max_findings: int) -> dict[str, Any]:
    findings: list[Finding] = []
    surfaces: list[dict[str, Any]] = []
    source_suffixes = {".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
    for path, text, surface in _bounded_files(repo):
        suffix = PurePosixPath(path).suffix.casefold()
        if re.search(r"\b(?:KAPPA|KappaPos|to_fixed|mul_fixed|fixed[-_ ]point)\b", text, re.I):
            if len(surfaces) < _MAX_FINDINGS:
                surfaces.append({
                    "path": path,
                    "surface": surface,
                    "hasBigInt": bool(re.search(r"\b(?:bigint|[0-9_]n)\b", text)),
                    "hasCanonicalDecimalParser": bool(re.search(r"Decimal\s*\(|DecimalString|decimal text", text, re.I)),
                    "hasStableDigest": bool(re.search(r"sha256|SHA-256|fnv1a", text, re.I)),
                })
        if suffix not in source_suffixes:
            continue
        for pattern, family, description, recommendation in _KAPPA_RULES:
            for match in pattern.finditer(text):
                findings.append(Finding(
                    "P1",
                    family,
                    path,
                    _line(text, match.start()),
                    description,
                    recommendation,
                    surface,
                ))
    returned = _sort_findings(findings, max_findings)
    return {
        "schemaVersion": "sovereign.kappa-contract-audit.v1",
        "revision": _git(repo, "rev-parse", "HEAD"),
        "contract": {
            "scale": KAPPA_SCALE,
            "internalRepresentation": "signed arbitrary-precision integer",
            "acceptedBoundaryInputs": ["scaled_integer", "canonical_decimal_string"],
            "forbiddenBoundaryInputs": ["float", "javascript_number_for_scaled_products"],
            "signedDivision": "TRUNCATE_TOWARD_ZERO",
            "canonicalEncoding": "UTF-8 NFC JSON with sorted keys and no floats",
            "stateDigest": "SHA-256 over canonical state without chain metadata",
        },
        "contractSurfaces": surfaces,
        "findingCount": len(findings),
        "findings": returned,
        "truncated": len(findings) > len(returned),
        "mutationPerformed": False,
        "runtimeSuccessClaimed": False,
        "truthNotice": "A matching Kappa constant does not prove arithmetic parity; independent Python and TypeScript replay vectors remain required.",
    }


def _sql_audit(repo: Path, max_findings: int) -> dict[str, Any]:
    findings: list[Finding] = []
    files = 0
    for path, text, surface in _bounded_files(repo):
        if PurePosixPath(path).suffix.casefold() != ".sql":
            continue
        findings.extend(_sql_findings(path, text, surface))
        files += 1
    returned = _sort_findings(findings, max_findings)
    return {
        "schemaVersion": "sovereign.deterministic-sql-audit.v1",
        "revision": _git(repo, "rev-parse", "HEAD"),
        "scannedSqlFiles": files,
        "findingCount": len(findings),
        "findings": returned,
        "truncated": len(findings) > len(returned),
        "requiredTruthColumns": [
            "sequence", "expected_version", "idempotency_key", "action_hash",
            "state_hash", "previous_chain_hash", "chain_hash",
        ],
        "mutationPerformed": False,
        "runtimeSuccessClaimed": False,
        "truthNotice": "Static SQL findings do not prove an active production path; confirm them with route and database evidence.",
    }


def deterministic_tool_inventory() -> dict[str, Any]:
    """List the deterministic Kappa/ARE tools and their read-only boundaries."""
    names = [
        "deterministic_architecture_inventory",
        "deterministic_nondeterminism_scan",
        "deterministic_kappa_contract_audit",
        "deterministic_sql_contract_audit",
        "deterministic_transition_validate",
        "deterministic_replay_verify",
        "deterministic_transformation_plan",
    ]
    return {
        "ok": True,
        "status": "DETERMINISTIC_ARCHITECTURE_TOOLS_READY",
        "kappaScale": KAPPA_SCALE,
        "tools": [{"name": name, "mutates": False} for name in names],
        "boundaries": {
            "repositoryMutation": False,
            "databaseAccess": False,
            "networkAccess": False,
            "runtimeSuccessClaimed": False,
            "secondStateMachineCreated": False,
            "sqliteTruthStoreCreated": False,
        },
        "sourceMaterialUse": {
            "adopted": [
                "Kappa fixed-point arithmetic",
                "Action-Reaction-Evolution pure reducer",
                "state hashing",
                "non-determinism and SQL rule families",
            ],
            "hardened": [
                "arbitrary-precision integer representation",
                "canonical decimal input",
                "Unicode-normalized canonical JSON",
                "signed division parity",
                "hash-chain preview",
                "truth-path-aware classification",
            ],
            "rejected": [
                "demo SQLite as a second truth store",
                "float-first conversion",
                "regex findings as runtime truth",
                "demo entry point as an MCP server",
                "generated cache and database artifacts",
            ],
        },
    }


def deterministic_architecture_inventory(workspace_id: str) -> dict[str, Any]:
    """Classify truth, effect, projection, test and legacy surfaces in an isolated workspace."""
    return _architecture_inventory(_repo(workspace_id))


def deterministic_nondeterminism_scan(
    workspace_id: str,
    max_findings: int = 160,
) -> dict[str, Any]:
    """Find static candidates for randomness, clocks, floats, hidden state and effects."""
    return _nondeterminism_scan(_repo(workspace_id), max_findings)


def deterministic_kappa_contract_audit(
    workspace_id: str,
    max_findings: int = 160,
) -> dict[str, Any]:
    """Audit Kappa scale, float boundaries, bigint use and canonical encoding."""
    return _kappa_audit(_repo(workspace_id), max_findings)


def deterministic_sql_contract_audit(
    workspace_id: str,
    max_findings: int = 160,
) -> dict[str, Any]:
    """Audit SQL ordering, implicit time, generated IDs and idempotency candidates."""
    return _sql_audit(_repo(workspace_id), max_findings)


def deterministic_transition_validate(
    current_state: dict[str, Any],
    action: dict[str, Any],
    transition_table: dict[str, dict[str, str]],
    expected_version: int | None = None,
    expected_state_hash: str = "",
    engine_version: str = "are-v1",
) -> dict[str, Any]:
    """Validate one pure ARE transition and return canonical hash-chain evidence."""
    return transition_preview(
        current_state,
        action,
        transition_table,
        expected_version=expected_version,
        expected_state_hash=expected_state_hash,
        engine_version=engine_version,
    )


def deterministic_replay_verify(
    initial_state: dict[str, Any],
    actions: list[dict[str, Any]],
    transition_table: dict[str, dict[str, str]],
    expected_final_state_hash: str = "",
    engine_version: str = "are-v1",
) -> dict[str, Any]:
    """Replay a bounded ARE sequence with the Python reference contract."""
    return replay_verify(
        initial_state,
        actions,
        transition_table,
        expected_final_state_hash=expected_final_state_hash,
        engine_version=engine_version,
    )


def deterministic_transformation_plan(
    workspace_id: str,
    max_findings: int = 80,
) -> dict[str, Any]:
    """Build a severity-ordered migration plan without editing files."""
    repo = _repo(workspace_id)
    scan = _nondeterminism_scan(repo, max_findings)
    kappa = _kappa_audit(repo, max_findings)
    sql = _sql_audit(repo, max_findings)
    combined = [*scan["findings"], *kappa["findings"], *sql["findings"]]
    unique: dict[tuple[str, str, int, str], dict[str, Any]] = {}
    for item in combined:
        key = (item["family"], item["path"], int(item["line"]), item["description"])
        unique.setdefault(key, item)
    severity_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    ranked = sorted(
        unique.values(),
        key=lambda item: (
            severity_order.get(item["severity"], 9),
            item["family"],
            item["path"],
            item["line"],
        ),
    )[: max(1, min(int(max_findings), _MAX_FINDINGS))]
    return {
        "schemaVersion": "sovereign.deterministic-transformation-plan.v1",
        "revision": _git(repo, "rev-parse", "HEAD"),
        "findingCount": len(unique),
        "rankedCandidates": ranked,
        "phases": [
            {
                "phase": 1,
                "name": "truth-boundary-classification",
                "goal": "Separate pure core, effect adapters, persisted truth and projections.",
            },
            {
                "phase": 2,
                "name": "canonical-kappa-contract",
                "goal": "Use scale 1,000,000 with integer math and cross-runtime vectors.",
            },
            {
                "phase": 3,
                "name": "are-pure-reducers",
                "goal": "Move clocks, randomness, hidden state and effects outside evolution.",
            },
            {
                "phase": 4,
                "name": "truth-chain-and-sql-idempotency",
                "goal": "Bind sequence, version, action, state and prior-chain hashes atomically.",
            },
            {
                "phase": 5,
                "name": "deterministic-orchestration-cost-gates",
                "goal": "Select bounded models, roles and retries from structured intent and evidence.",
            },
        ],
        "mutationPerformed": False,
        "runtimeSuccessClaimed": False,
        "nextAction": "Confirm ranked candidates against active runtime evidence, then change one bounded truth plane per Draft PR.",
    }


def register(mcp: Any, runtime: Any) -> None:
    global _RUNTIME, _REGISTERED
    _RUNTIME = runtime
    if _REGISTERED:
        return
    for tool in (
        deterministic_tool_inventory,
        deterministic_architecture_inventory,
        deterministic_nondeterminism_scan,
        deterministic_kappa_contract_audit,
        deterministic_sql_contract_audit,
        deterministic_transition_validate,
        deterministic_replay_verify,
        deterministic_transformation_plan,
    ):
        mcp.tool(annotations=READ_ONLY)(tool)
    _REGISTERED = True

