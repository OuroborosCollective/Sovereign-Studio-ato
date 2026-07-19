from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
from typing import Annotated, Any, Final, Literal, Sequence

import requests
from mcp.types import ToolAnnotations
from pydantic import Field


LOCAL_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
NETWORK_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)

_MAX_TRACKED_FILES: Final[int] = 30_000
_MAX_FILE_BYTES: Final[int] = 1_200_000
_MAX_SCAN_BYTES: Final[int] = 48 * 1024 * 1024
_MAX_EVIDENCE: Final[int] = 200
_SHA_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_SAFE_BRANCH_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
_SECRET_LIKE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:sk-(?:proj-)?[A-Za-z0-9_-]{16,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"gh[pousr]_[A-Za-z0-9_]{20,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)",
    re.I,
)

_TEXT_SUFFIXES: Final[frozenset[str]] = frozenset({
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".kt", ".kts", ".cs", ".fs", ".fsx",
    ".sql", ".proto", ".graphql", ".gql", ".json", ".jsonc", ".toml",
    ".yaml", ".yml", ".xml", ".gradle", ".md", ".sh", ".dockerfile",
})
_SKIP_PREFIXES: Final[tuple[str, ...]] = (
    ".git/", "node_modules/", "vendor/", "dist/", "build/", "coverage/",
    "target/", ".gradle/", ".next/", ".venv/", "venv/", "__pycache__/",
    "playwright-report/", "test-results/", "android/app/build/", "android/.gradle/",
)
_LANGUAGE_SUFFIXES: Final[dict[str, str]] = {
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".py": "python",
    ".pyi": "python",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".cs": "csharp",
    ".fs": "fsharp",
    ".fsx": "fsharp",
    ".sql": "sql",
    ".proto": "protobuf",
    ".graphql": "graphql",
    ".gql": "graphql",
}

_CAPABILITY_MARKERS: Final[dict[str, dict[str, tuple[str, ...]]]] = {
    "frameworks": {
        "fastapi": ("from fastapi", "import fastapi"),
        "django": ("django.", "django==", "django>="),
        "flask": ("from flask", "import flask"),
        "nestjs": ("@nestjs/", "nestfactory"),
        "fastify": ("fastify(", "from 'fastify'", 'from "fastify"'),
        "express": ("express(", "from 'express'", 'from "express"'),
        "spring": ("org.springframework", "@springbootapplication"),
        "aspnet-core": ("microsoft.aspnetcore", "webapplication.createbuilder"),
        "axum": ("axum::", "axum ="),
        "actix-web": ("actix_web", "actix-web"),
        "gin": ("github.com/gin-gonic/gin", "gin.default("),
        "chi": ("github.com/go-chi/chi", "chi.newrouter("),
    },
    "data": {
        "postgresql": (
            "postgresql",
            "postgres://",
            "from 'postgres'",
            'from "postgres"',
            "psycopg",
            "pgx",
            "npgsql",
            "org.postgresql",
        ),
        "mysql": ("mysql", "mariadb"),
        "mongodb": ("mongodb", "mongoose", "pymongo"),
        "redis": ("redis", "ioredis"),
        "sqlite": ("sqlite",),
        "kafka": ("kafka",),
        "rabbitmq": ("rabbitmq", "amqp"),
        "nats": ("nats.io", "nats-py", "nats.js"),
        "object-storage": ("s3client", "boto3", "minio", "r2_storage"),
    },
    "protocols": {
        "rest-openapi": ("openapi", "swagger", "@app.route", "app.get(", "router.get("),
        "graphql": ("graphql", "strawberry", "graphene"),
        "grpc": ("grpc", "service ", "rpc "),
        "websocket": ("websocket", "socket.io", "sse", "eventsource"),
    },
    "security": {
        "oauth-oidc": ("oauth", "openid", "oidc", "pkce"),
        "jwt": ("jsonwebtoken", "pyjwt", "jwks", "jwt."),
        "rbac-abac": ("rbac", "abac", "permission", "authorization policy"),
        "secret-management": ("vault", "secretsmanager", "key vault", "secret manager", "kms"),
        "rate-limiting": ("rate limit", "ratelimit", "throttle"),
        "cors-csrf": ("cors", "csrf", "same-site", "samesite"),
        "tls-mtls": ("mtls", "sslcontext", "tls"),
    },
    "observability": {
        "opentelemetry": ("opentelemetry", "open telemetry"),
        "prometheus": ("prometheus",),
        "structured-logging": ("structlog", "jsonlogger", "pino", "serilog", "logback"),
        "error-monitoring": ("sentry", "rollbar"),
        "tracing": ("traceparent", "span_id", "trace_id"),
    },
    "delivery": {
        "docker": ("dockerfile", "docker compose", "docker-compose"),
        "kubernetes": ("kind: deployment", "kind: statefulset", "apiVersion: apps/".casefold()),
        "helm": ("chart.yaml", "helm"),
        "github-actions": (".github/workflows", "github actions"),
        "terraform": ("terraform", ".tf"),
    },
    "platform": {
        "react-tsx": ("react", ".tsx"),
        "admin-system": ("admin", "user management", "user_management"),
        "metadata-driven": ("json schema", "jsonschema", "metadata-driven", "metadata_driven"),
        "plugin-system": ("plugin", "extension manifest", "capability manifest"),
        "multi-tenancy": ("tenant_id", "tenantid", "multi-tenant", "multitenant"),
        "migrations": ("migration", "alembic", "prisma migrate", "typeorm migration", "flyway", "liquibase"),
        "event-outbox": ("outbox", "event store", "event_store", "domain event"),
        "server-driven-ui": ("server-driven ui", "server_driven_ui", "sdui", "ui schema"),
    },
}

_FOCUS_CATEGORIES: Final[dict[str, frozenset[str]]] = {
    "full": frozenset(_CAPABILITY_MARKERS),
    "api": frozenset({"frameworks", "protocols", "security"}),
    "data": frozenset({"data", "platform", "observability"}),
    "security": frozenset({"security", "delivery", "platform"}),
    "operations": frozenset({"observability", "delivery", "data"}),
    "prototype-modernization": frozenset({"frameworks", "data", "protocols", "security", "platform", "delivery"}),
}

_RUNTIME: Any = None
_BROKER: Any = None
_REGISTERED = False

WorkspaceId = Annotated[str, Field(min_length=1, max_length=160)]
EvidenceLimit = Annotated[int, Field(ge=10, le=_MAX_EVIDENCE)]
BaseBranch = Annotated[
    str,
    Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$"),
]
PullRequestNumber = Annotated[int, Field(ge=0, le=10_000_000)]
OptionalExactSha = Annotated[
    str,
    Field(max_length=40, pattern=r"^(?:[0-9a-fA-F]{40})?$"),
]


@dataclass(frozen=True)
class BackendToolInventoryResult:
    schemaVersion: str
    ok: bool
    status: str
    tools: list[dict[str, Any]]
    workflow: list[str]
    boundaries: dict[str, bool]
    sourceSkills: list[str]


@dataclass(frozen=True)
class BackendArchitectureAssessmentResult:
    schemaVersion: str
    ok: bool
    status: str
    revision: str
    dirty: bool
    focus: str
    scannedFiles: int
    scannedBytes: int
    scanTruncated: bool
    languages: list[dict[str, Any]]
    capabilities: dict[str, list[dict[str, Any]]]
    architectureCandidates: list[dict[str, Any]]
    riskCandidates: list[dict[str, Any]]
    requiredEvidenceGates: list[str]
    mutationPerformed: bool
    runtimeVerified: bool
    secretValuesReturned: bool
    truthNotice: str


@dataclass(frozen=True)
class BackendStackSelectionResult:
    schemaVersion: str
    ok: bool
    status: str
    revision: str
    selectedStack: dict[str, Any]
    candidateScores: list[dict[str, Any]]
    alternatives: list[dict[str, Any]]
    decisiveReasons: list[str]
    assumptions: list[str]
    decisionGates: list[str]
    mutationPerformed: bool
    runtimeVerified: bool
    truthNotice: str


@dataclass(frozen=True)
class BackendDeliveryPlanResult:
    schemaVersion: str
    ok: bool
    status: str
    revision: str
    targetOutcome: str
    phases: list[dict[str, Any]]
    crossCuttingContracts: list[str]
    stopConditions: list[str]
    planSha256: str
    mutationPerformed: bool
    runtimeVerified: bool
    truthNotice: str


@dataclass(frozen=True)
class BackendSecurityPlanResult:
    schemaVersion: str
    ok: bool
    status: str
    revision: str
    threatProfile: dict[str, Any]
    observedSecurityEvidence: list[dict[str, Any]]
    threatControls: list[dict[str, Any]]
    priorityControls: list[str]
    verificationGates: list[str]
    candidateGaps: list[str]
    mutationPerformed: bool
    complianceVerified: bool
    secretValuesReturned: bool
    truthNotice: str


@dataclass(frozen=True)
class RepositoryRevisionResolutionResult:
    schemaVersion: str
    ok: bool
    status: str
    repositoryFullName: str | None
    workspaceId: str
    branch: str | None
    worktreeClean: bool
    dirtyEntries: list[str]
    workspaceHeadSha: str | None
    currentBaseBranch: str
    currentBaseHeadSha: str | None
    mergeBaseSha: str | None
    pullRequest: dict[str, Any] | None
    prHeadSha: str | None
    prBaseSha: str | None
    mergedChangeSha: str | None
    baseAdvancedSincePr: bool | None
    ciEvidence: dict[str, Any]
    deployedMcpEvidence: dict[str, Any]
    expectedMatches: dict[str, bool | None]
    revisionConflicts: list[str]
    evidenceGaps: list[str]
    authoritativeNextRevision: str | None
    nextAllowedAction: str
    mutationPerformed: bool
    secretValuesReturned: bool


def _repo(workspace_id: str) -> Path:
    if _RUNTIME is None:
        raise RuntimeError("Enterprise backend tools are not registered")
    return _RUNTIME._repo(workspace_id)


def _git(repo: Path, *args: str, check: bool = True, timeout: int = 90) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if check and completed.returncode != 0:
        raise RuntimeError("bounded git read failed")
    return completed.stdout.strip()


def _resolve_commit(repo: Path, ref: str | None) -> str | None:
    if not ref:
        return None
    value = _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}", check=False)
    return value if _SHA_RE.fullmatch(value) else None


def _tracked_files(repo: Path) -> list[str]:
    files = [line for line in _git(repo, "ls-files").splitlines() if line]
    if len(files) > _MAX_TRACKED_FILES:
        raise ValueError("repository exceeds the bounded tracked-file limit")
    return files


def _is_text_candidate(relative: str) -> bool:
    lowered = relative.casefold()
    if relative.startswith(_SKIP_PREFIXES):
        return False
    name = PurePosixPath(relative).name.casefold()
    suffix = PurePosixPath(relative).suffix.casefold()
    return (
        suffix in _TEXT_SUFFIXES
        or name in {"dockerfile", "makefile", "gemfile", "procfile"}
        or relative.startswith(".github/workflows/")
    ) and not any(marker in lowered for marker in (".min.js", ".min.css", "package-lock.json"))


def _bounded_sources(repo: Path) -> tuple[list[tuple[str, str]], int, bool]:
    output: list[tuple[str, str]] = []
    consumed = 0
    truncated = False
    for relative in _tracked_files(repo):
        if not _is_text_candidate(relative):
            continue
        path = repo / relative
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > _MAX_FILE_BYTES:
            truncated = True
            continue
        if consumed + size > _MAX_SCAN_BYTES:
            truncated = True
            break
        try:
            text = path.read_text("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        consumed += size
        output.append((relative, text))
    return output, consumed, truncated


def _record_evidence(
    evidence: dict[str, dict[str, set[str]]],
    category: str,
    capability: str,
    path: str,
) -> None:
    paths = evidence[category][capability]
    if len(paths) < 24:
        paths.add(_safe_evidence_path(path))


def _safe_evidence_path(path: str) -> str:
    if not _SECRET_LIKE_RE.search(path):
        return path
    fingerprint = hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]
    return f"[redacted-secret-shaped-path:{fingerprint}]"


def _risk(
    output: list[dict[str, Any]],
    seen: set[tuple[str, str]],
    severity: str,
    family: str,
    path: str,
    reason: str,
) -> None:
    safe_path = _safe_evidence_path(path)
    key = (family, safe_path)
    if key in seen or len(output) >= _MAX_EVIDENCE:
        return
    seen.add(key)
    output.append({
        "severity": severity,
        "family": family,
        "path": safe_path,
        "reason": reason,
        "status": "STATIC_CANDIDATE",
    })


def _assessment_payload(repo: Path, focus: str, max_evidence: int) -> dict[str, Any]:
    if focus not in _FOCUS_CATEGORIES:
        raise ValueError("focus is not supported")
    limit = max(10, min(int(max_evidence), _MAX_EVIDENCE))
    sources, scanned_bytes, truncated = _bounded_sources(repo)
    languages: Counter[str] = Counter()
    evidence: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    risks: list[dict[str, Any]] = []
    risk_seen: set[tuple[str, str]] = set()
    test_paths: set[str] = set()
    workflow_paths: set[str] = set()
    dockerfiles: set[str] = set()
    backend_paths: set[str] = set()
    tsx_paths: set[str] = set()

    for relative, text in sources:
        suffix = PurePosixPath(relative).suffix.casefold()
        language = _LANGUAGE_SUFFIXES.get(suffix)
        if language:
            languages[language] += 1
        lowered_path = relative.casefold()
        lowered = text.casefold()
        haystack = f"{lowered_path}\n{lowered}"
        if suffix == ".tsx":
            tsx_paths.add(relative)
        if any(marker in lowered_path for marker in ("backend/", "server/", "api/", "service/")):
            backend_paths.add(relative)
        if any(marker in lowered_path for marker in ("/tests/", "/test/", "__tests__", ".test.", ".spec.")) or PurePosixPath(relative).name.startswith("test_"):
            test_paths.add(relative)
        if relative.startswith(".github/workflows/"):
            workflow_paths.add(relative)
        if PurePosixPath(relative).name.casefold() == "dockerfile":
            dockerfiles.add(relative)

        for category, capabilities in _CAPABILITY_MARKERS.items():
            for capability, markers in capabilities.items():
                if any(marker.casefold() in haystack for marker in markers):
                    _record_evidence(evidence, category, capability, relative)

        if _SECRET_LIKE_RE.search(relative):
            _risk(
                risks,
                risk_seen,
                "P0",
                "SECRET_LIKE_PATH",
                relative,
                "A tracked path is secret-shaped; rename it and rotate the value without returning it.",
            )
        if _SECRET_LIKE_RE.search(text):
            _risk(
                risks,
                risk_seen,
                "P0",
                "SECRET_LIKE_LITERAL",
                relative,
                "A secret-shaped literal exists; inspect and rotate without returning its value.",
            )
        if re.search(r"\b(?:eval|exec)\s*\(|\bnew\s+Function\s*\(", text):
            _risk(
                risks,
                risk_seen,
                "P1",
                "RUNTIME_CODE_EVALUATION",
                relative,
                "Dynamic code evaluation requires an isolated capability sandbox and must not run in the main backend process.",
            )
        if re.search(r"(?:allow_origins\s*=\s*\[\s*['\"]\*|cors\s*\(\s*\{?\s*origin\s*:\s*['\"]\*)", text, re.I):
            _risk(
                risks,
                risk_seen,
                "P1",
                "WILDCARD_CORS",
                relative,
                "Wildcard browser origins are candidates for an explicit origin allowlist.",
            )
        if re.search(r"(?:verify\s*=\s*False|rejectUnauthorized\s*:\s*false|NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*['\"]?0)", text, re.I):
            _risk(
                risks,
                risk_seen,
                "P0",
                "TLS_VERIFICATION_DISABLED",
                relative,
                "TLS verification appears disabled in a static source candidate.",
            )
        if PurePosixPath(relative).name.casefold() == "dockerfile" and not re.search(r"^\s*USER\s+", text, re.M | re.I):
            _risk(
                risks,
                risk_seen,
                "P2",
                "CONTAINER_USER_NOT_DECLARED",
                relative,
                "The container build has no explicit non-root USER instruction.",
            )

    if tsx_paths and not backend_paths:
        _risk(
            risks,
            risk_seen,
            "P1",
            "FRONTEND_PROTOTYPE_WITHOUT_BACKEND_BOUNDARY",
            sorted(tsx_paths)[0],
            "React/TSX exists but no backend surface was found in the bounded static scan.",
        )
    if evidence.get("data") and not evidence.get("platform", {}).get("migrations"):
        first_data_path = sorted(next(iter(evidence["data"].values())))[0]
        _risk(
            risks,
            risk_seen,
            "P1",
            "DATABASE_WITHOUT_MIGRATION_EVIDENCE",
            first_data_path,
            "A data-store marker exists without a discovered versioned migration marker.",
        )
    if backend_paths and not test_paths:
        _risk(
            risks,
            risk_seen,
            "P1",
            "BACKEND_WITHOUT_TEST_EVIDENCE",
            sorted(backend_paths)[0],
            "Backend candidates exist but the bounded scan found no test path.",
        )
    if backend_paths and not workflow_paths:
        _risk(
            risks,
            risk_seen,
            "P2",
            "BACKEND_WITHOUT_CI_EVIDENCE",
            sorted(backend_paths)[0],
            "Backend candidates exist but no GitHub Actions workflow was discovered.",
        )

    selected_categories = _FOCUS_CATEGORIES[focus]
    capabilities: dict[str, list[dict[str, Any]]] = {}
    for category in sorted(selected_categories):
        values: list[dict[str, Any]] = []
        for capability, paths in sorted(evidence.get(category, {}).items()):
            values.append({
                "name": capability,
                "evidencePaths": sorted(paths),
                "status": "STATIC_EVIDENCE",
            })
        capabilities[category] = values

    architecture_candidates: list[dict[str, Any]] = []
    deployment_units = len(dockerfiles)
    if deployment_units <= 1:
        architecture_candidates.append({
            "style": "modular-monolith-or-single-service",
            "status": "STATIC_CANDIDATE",
            "reason": "The bounded scan found at most one Dockerfile; module and runtime evidence is still required.",
        })
    else:
        architecture_candidates.append({
            "style": "multiple-deployment-units",
            "status": "STATIC_CANDIDATE",
            "reason": f"The bounded scan found {deployment_units} Dockerfiles; this does not prove independently operated microservices.",
        })
    if evidence.get("platform", {}).get("event-outbox") or evidence.get("data", {}).get("kafka"):
        architecture_candidates.append({
            "style": "event-driven-components",
            "status": "STATIC_CANDIDATE",
            "reason": "Outbox/event/broker markers exist; delivery, replay and idempotency need runtime proof.",
        })
    if evidence.get("platform", {}).get("metadata-driven"):
        architecture_candidates.append({
            "style": "metadata-driven-platform",
            "status": "STATIC_CANDIDATE",
            "reason": "Metadata/schema markers exist; executable-code and authorization boundaries require contract review.",
        })

    severity_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    risks.sort(key=lambda item: (severity_order.get(str(item["severity"]), 9), item["family"], item["path"]))
    language_payload = [
        {"name": name, "trackedFileCount": count, "status": "STATIC_EVIDENCE"}
        for name, count in sorted(languages.items(), key=lambda item: (-item[1], item[0]))
    ]
    return {
        "schemaVersion": "sovereign.enterprise-backend-assessment.v1",
        "ok": True,
        "status": "BACKEND_ARCHITECTURE_STATIC_EVIDENCE_READY",
        "revision": _git(repo, "rev-parse", "HEAD"),
        "dirty": bool(_git(repo, "status", "--porcelain=v1", "--untracked-files=normal")),
        "focus": focus,
        "scannedFiles": len(sources),
        "scannedBytes": scanned_bytes,
        "scanTruncated": truncated,
        "languages": language_payload,
        "capabilities": capabilities,
        "architectureCandidates": architecture_candidates,
        "riskCandidates": risks[:limit],
        "requiredEvidenceGates": [
            "confirm active entrypoints and callers",
            "run framework compiler/type checks",
            "run real database and migration contracts",
            "run authentication and tenant-isolation negative tests",
            "run load, pool and backpressure tests from an explicit workload",
            "bind CI, artifact and deployment evidence to the exact revision",
        ],
        "mutationPerformed": False,
        "runtimeVerified": False,
        "secretValuesReturned": False,
        "truthNotice": "Static markers and absences are candidates only; they do not prove runtime activity, security, scale or production readiness.",
    }


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _observed_languages(assessment: dict[str, Any]) -> set[str]:
    return {
        str(item.get("name"))
        for item in assessment.get("languages", [])
        if int(item.get("trackedFileCount") or 0) > 0
    }


_STACK_CANDIDATES: Final[tuple[dict[str, Any], ...]] = (
    {"id": "typescript-nestjs", "language": "typescript", "framework": "NestJS", "base": 50},
    {"id": "typescript-fastify", "language": "typescript", "framework": "Fastify", "base": 50},
    {"id": "go-http", "language": "go", "framework": "chi/net-http", "base": 50},
    {"id": "java-spring", "language": "java", "framework": "Spring Boot", "base": 50},
    {"id": "csharp-aspnet", "language": "csharp", "framework": "ASP.NET Core", "base": 50},
    {"id": "rust-axum", "language": "rust", "framework": "Axum", "base": 50},
    {"id": "python-fastapi", "language": "python", "framework": "FastAPI", "base": 50},
    {"id": "python-django", "language": "python", "framework": "Django", "base": 50},
)


def _score_stack(
    candidate: dict[str, Any],
    *,
    observed: set[str],
    workload: str,
    team_language: str,
    scale: str,
    compliance_required: bool,
    delivery_priority: str,
    existing_stack_policy: str,
) -> tuple[int, list[str]]:
    score = int(candidate["base"])
    reasons: list[str] = []
    language = str(candidate["language"])
    framework = str(candidate["framework"])

    if language in observed:
        boost = {"prefer": 22, "neutral": 9, "replace": 0}[existing_stack_policy]
        score += boost
        if boost:
            reasons.append(f"existing {language} repository evidence +{boost}")
    elif observed and existing_stack_policy == "prefer":
        score -= 9
        reasons.append("new primary runtime would add operating cost -9")

    if team_language not in {"existing", "unspecified"}:
        if language == team_language:
            score += 24
            reasons.append("explicit team-language fit +24")
        else:
            score -= 12
            reasons.append("explicit team-language mismatch -12")

    workload_boosts: dict[str, dict[str, int]] = {
        "general-api": {
            "typescript-nestjs": 10, "typescript-fastify": 11, "go-http": 11,
            "java-spring": 10, "csharp-aspnet": 10, "rust-axum": 7,
            "python-fastapi": 10, "python-django": 7,
        },
        "admin-platform": {
            "typescript-nestjs": 22, "typescript-fastify": 9, "go-http": 5,
            "java-spring": 14, "csharp-aspnet": 14, "rust-axum": 2,
            "python-fastapi": 10, "python-django": 21,
        },
        "realtime": {
            "typescript-nestjs": 12, "typescript-fastify": 18, "go-http": 21,
            "java-spring": 12, "csharp-aspnet": 14, "rust-axum": 17,
            "python-fastapi": 7, "python-django": 2,
        },
        "high-throughput": {
            "typescript-nestjs": 8, "typescript-fastify": 13, "go-http": 23,
            "java-spring": 16, "csharp-aspnet": 15, "rust-axum": 24,
            "python-fastapi": 4, "python-django": 0,
        },
        "security-critical": {
            "typescript-nestjs": 8, "typescript-fastify": 7, "go-http": 14,
            "java-spring": 16, "csharp-aspnet": 16, "rust-axum": 24,
            "python-fastapi": 5, "python-django": 8,
        },
        "data-ai": {
            "typescript-nestjs": 7, "typescript-fastify": 7, "go-http": 5,
            "java-spring": 6, "csharp-aspnet": 5, "rust-axum": 3,
            "python-fastapi": 24, "python-django": 14,
        },
    }
    boost = workload_boosts[workload][str(candidate["id"])]
    score += boost
    reasons.append(f"{workload} workload fit +{boost}")

    if scale in {"large", "extreme"}:
        scale_boost = {"go": 10, "rust": 11, "java": 8, "csharp": 8, "typescript": 4, "python": -3}[language]
        score += scale_boost
        reasons.append(f"{scale} scale profile {scale_boost:+d}")
    if compliance_required:
        compliance_boost = {"java": 8, "csharp": 8, "go": 5, "rust": 6, "typescript": 4, "python": 2}[language]
        score += compliance_boost
        reasons.append(f"compliance ecosystem {compliance_boost:+d}")
    if delivery_priority == "speed":
        delivery_boost = 8 if language in {"typescript", "python"} else -3 if language in {"rust"} else 2
        score += delivery_boost
        reasons.append(f"delivery-speed profile {delivery_boost:+d}")
    elif delivery_priority == "runtime-efficiency":
        efficiency_boost = {"rust": 10, "go": 9, "java": 5, "csharp": 5, "typescript": 1, "python": -5}[language]
        score += efficiency_boost
        reasons.append(f"runtime-efficiency profile {efficiency_boost:+d}")

    if workload == "admin-platform" and framework == "Fastify":
        score -= 4
        reasons.append("more admin/platform conventions must be assembled -4")
    return max(0, min(score, 100)), reasons


def backend_engineering_tool_inventory() -> BackendToolInventoryResult:
    """Use this when you need the bounded enterprise-backend and exact-revision tool map before starting work."""
    names = (
        "backend_architecture_assess",
        "backend_stack_select",
        "backend_delivery_plan",
        "backend_api_security_plan",
        "repository_revision_resolve",
    )
    return BackendToolInventoryResult(
        schemaVersion="sovereign.enterprise-backend-tool-inventory.v1",
        ok=True,
        status="ENTERPRISE_BACKEND_TOOLS_READY",
        tools=[
            {
                "name": name,
                "mutates": False,
                "sourceSkill": "resolve-repository-revision" if name == "repository_revision_resolve" else "engineer-enterprise-backends",
            }
            for name in names
        ],
        workflow=[
            "resolve exact revision authority",
            "collect bounded static architecture evidence",
            "select and score the smallest fitting stack",
            "produce threat-driven security and delivery contracts",
            "use existing repository mutation tools for approved implementation",
            "re-resolve revision before review, merge and deployment",
        ],
        boundaries={
            "repositoryMutation": False,
            "databaseAccess": False,
            "genericShell": False,
            "arbitraryCodeExecution": False,
            "runtimeSuccessClaimed": False,
            "secretValuesReturned": False,
        },
        sourceSkills=["engineer-enterprise-backends", "resolve-repository-revision"],
    )


def backend_architecture_assess(
    workspace_id: WorkspaceId,
    focus: Literal["full", "api", "data", "security", "operations", "prototype-modernization"] = "full",
    max_evidence: EvidenceLimit = 120,
) -> BackendArchitectureAssessmentResult:
    """Use this when you need a bounded, secret-safe static map of backend architecture, risks, and missing evidence."""
    payload = _assessment_payload(_repo(workspace_id), focus, max_evidence)
    return BackendArchitectureAssessmentResult(**payload)


def backend_stack_select(
    workspace_id: WorkspaceId,
    workload: Literal["general-api", "admin-platform", "realtime", "high-throughput", "security-critical", "data-ai"] = "general-api",
    team_language: Literal["existing", "typescript", "go", "java", "csharp", "rust", "python", "unspecified"] = "existing",
    scale: Literal["small", "medium", "large", "extreme"] = "medium",
    consistency: Literal["strong", "mixed", "eventual"] = "strong",
    data_model: Literal["relational", "document", "mixed"] = "relational",
    deployment_target: Literal["managed-container", "kubernetes", "serverless", "vm"] = "managed-container",
    realtime_required: bool = False,
    compliance_required: bool = False,
    delivery_priority: Literal["balanced", "speed", "runtime-efficiency"] = "balanced",
    existing_stack_policy: Literal["prefer", "neutral", "replace"] = "prefer",
) -> BackendStackSelectionResult:
    """Use this when you need an evidence-scored backend stack recommendation for explicit workload and operating constraints."""
    repo = _repo(workspace_id)
    assessment = _assessment_payload(repo, "full", 80)
    observed = _observed_languages(assessment)
    scored: list[dict[str, Any]] = []
    reasons_by_id: dict[str, list[str]] = {}
    for candidate in _STACK_CANDIDATES:
        score, reasons = _score_stack(
            candidate,
            observed=observed,
            workload=workload,
            team_language=team_language,
            scale=scale,
            compliance_required=compliance_required,
            delivery_priority=delivery_priority,
            existing_stack_policy=existing_stack_policy,
        )
        reasons_by_id[str(candidate["id"])] = reasons
        scored.append({
            "id": candidate["id"],
            "language": candidate["language"],
            "framework": candidate["framework"],
            "score": score,
            "reasons": reasons,
        })
    scored.sort(key=lambda item: (-int(item["score"]), str(item["id"])))
    selected = scored[0]

    if data_model == "document" and consistency == "eventual":
        primary_database = "MongoDB with explicit aggregate boundaries and transaction limits"
    elif data_model == "mixed":
        primary_database = "PostgreSQL with JSONB first; add a document store only after measured query/scale evidence"
    else:
        primary_database = "PostgreSQL with versioned expand-and-contract migrations"

    cache = "Redis as an ephemeral cache/rate counter, never durable truth" if scale in {"large", "extreme"} or realtime_required else "No distributed cache until measured need"
    if workload in {"high-throughput", "realtime"}:
        messaging = "Managed durable queue with outbox/inbox; Kafka only when replay/throughput evidence requires it"
    else:
        messaging = "No broker initially; add a durable queue for proven asynchronous work"
    protocols = ["versioned REST/OpenAPI"]
    if realtime_required or workload == "realtime":
        protocols.append("WebSocket or SSE with reconnect, backpressure and projection versions")
    if workload == "high-throughput":
        protocols.append("gRPC for measured internal service boundaries only")

    architecture = "modular monolith with explicit domain ports and extraction boundaries"
    if scale == "extreme" and workload == "high-throughput":
        architecture = "modular monolith plus measured hot-path extraction gates; no automatic microservice split"
    selected_stack = {
        "language": selected["language"],
        "framework": selected["framework"],
        "architecture": architecture,
        "primaryDatabase": primary_database,
        "cache": cache,
        "messaging": messaging,
        "protocols": protocols,
        "deployment": deployment_target,
        "kubernetesGate": (
            "Use only with existing cluster ownership, policy, observability and rollback maturity."
            if deployment_target == "kubernetes"
            else "Not required by the selected deployment target."
        ),
    }
    assumptions = [
        "Repository observations are static and do not prove active production paths.",
        "No measured latency, throughput, recovery or staffing data was supplied to this deterministic selector.",
        "The existing stack is retained unless explicit constraints outweigh migration and dual-runtime cost.",
    ]
    if not observed:
        assumptions.append("No supported primary backend language was detected in the bounded scan.")
    return BackendStackSelectionResult(
        schemaVersion="sovereign.enterprise-backend-stack-selection.v1",
        ok=True,
        status="BACKEND_STACK_RECOMMENDATION_READY",
        revision=str(assessment["revision"]),
        selectedStack=selected_stack,
        candidateScores=scored,
        alternatives=scored[1:4],
        decisiveReasons=reasons_by_id[str(selected["id"])],
        assumptions=assumptions,
        decisionGates=[
            "confirm team ownership and supported runtime versions",
            "benchmark the representative workload before scale-driven extraction",
            "prove database constraints, indexes, migrations and restore",
            "record an architecture decision with rejected alternatives and reversal cost",
            "validate official framework/security support at implementation time",
        ],
        mutationPerformed=False,
        runtimeVerified=False,
        truthNotice="The score is a deterministic recommendation from declared constraints and static evidence, not a benchmark or production-readiness result.",
    )


def _phase(
    sequence: int,
    name: str,
    outcome: str,
    deliverables: Sequence[str],
    gates: Sequence[str],
    rollback: str,
) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "name": name,
        "outcome": outcome,
        "deliverables": list(deliverables),
        "gates": list(gates),
        "rollback": rollback,
        "status": "PLANNED_NOT_EXECUTED",
    }


def backend_delivery_plan(
    workspace_id: WorkspaceId,
    target_outcome: Literal["greenfield", "prototype-to-platform", "modernize", "secure", "scale", "release"] = "modernize",
    include_multi_tenancy: bool = False,
    include_plugins: bool = False,
    zero_downtime_required: bool = True,
) -> BackendDeliveryPlanResult:
    """Use this when you need an ordered, test-gated backend initialization or modernization roadmap with rollback boundaries."""
    assessment = _assessment_payload(_repo(workspace_id), "full", 100)
    phases: list[dict[str, Any]] = []
    phases.append(_phase(
        1,
        "authority-and-baseline",
        "Pin the exact repository/runtime authority and preserve current behavior.",
        ["revision ledger", "active-entrypoint map", "journey and invariant baseline", "risk register"],
        ["clean isolated workspace", "current CI/runtime state recorded", "no secret values captured"],
        "Discard only the isolated workspace; preserve the authoritative branch and runtime.",
    ))
    if target_outcome == "prototype-to-platform":
        phases.append(_phase(
            len(phases) + 1,
            "extract-tsx-contract",
            "Turn component-local behavior into typed journeys, data and API contracts.",
            ["screen/form/action inventory", "shared schemas", "static CI frontend build", "mock-to-API migration map"],
            ["current UI journeys pass", "no production runtime TSX evaluation", "accessibility baseline"],
            "Keep the previous static frontend artifact and route traffic back to it.",
        ))
    if target_outcome == "greenfield":
        phases.append(_phase(
            len(phases) + 1,
            "initialize-project",
            "Create the smallest operable modular backend skeleton.",
            ["module boundaries", "typed configuration", "health/readiness", "structured logging", "local container profile"],
            ["compiler/type check", "configuration fails closed", "non-root container", "dependency lockfile"],
            "Delete only the new isolated scaffold branch.",
        ))
    phases.append(_phase(
        len(phases) + 1,
        "domain-api-contracts",
        "Define domain invariants and versioned transport contracts before framework code expands.",
        ["domain model", "OpenAPI/GraphQL/protobuf contract", "error taxonomy", "idempotency and compatibility policy"],
        ["schema validation", "consumer contract tests", "invalid-input and conflict tests"],
        "Retain the previous API version and disable the new route registration.",
    ))
    phases.append(_phase(
        len(phases) + 1,
        "identity-policy-and-secrets",
        "Establish server-side identity, authorization and secret boundaries.",
        ["OAuth/OIDC or session design", "RBAC/ABAC policies", "admin separation", "secret-store references", "audit schema"],
        ["allow and deny policy tests", "token claim validation", "secret scan", "safe error tests"],
        "Disable new grants and restore the last compatible policy version.",
    ))
    if include_multi_tenancy:
        phases.append(_phase(
            len(phases) + 1,
            "tenant-isolation",
            "Make tenant scope an enforced data and policy invariant.",
            ["tenancy model ADR", "provision/export/delete flows", "row/schema/database isolation", "noisy-neighbor quotas"],
            ["cross-tenant negative tests", "backup/restore per model", "operator-access audit"],
            "Block tenant provisioning and revert to the previous single-tenant routing boundary.",
        ))
    phases.append(_phase(
        len(phases) + 1,
        "data-and-migrations",
        "Create constrained persistence with observable, restartable migration evidence.",
        ["canonical schema", "indexes/constraints", "repository adapters", "migration ledger", "backup/restore runbook"],
        ["real database integration tests", "migration preview", "upgrade from oldest supported schema", "restore proof"],
        "Use forward repair for irreversible data changes and retain the old application compatibility window.",
    ))
    phases.append(_phase(
        len(phases) + 1,
        "vertical-production-slice",
        "Deliver one complete user journey through API, policy, persistence, projection and telemetry.",
        ["one real route", "transaction boundary", "frontend/admin client", "metrics/traces/logs"],
        ["success/failure/invalid/unauthorized tests", "concurrency and retry tests", "real end-to-end journey"],
        "Feature-flag the new slice off and keep stored data backward compatible.",
    ))
    if target_outcome in {"prototype-to-platform", "modernize", "greenfield"}:
        phases.append(_phase(
            len(phases) + 1,
            "bounded-admin-and-metadata",
            "Add admin/user management and metadata-driven CRUD without executable metadata.",
            ["versioned metadata schema", "allowlisted field/operation registry", "server-driven UI hints", "generated client types"],
            ["object/field/tenant authorization", "query-cost bounds", "metadata compatibility", "audit coverage"],
            "Deactivate the new metadata revision and serve the previous immutable schema version.",
        ))
    if include_plugins:
        phases.append(_phase(
            len(phases) + 1,
            "isolated-extension-host",
            "Support signed, capability-bounded extensions outside the main backend process.",
            ["signed manifest", "host API", "process/container/Wasm sandbox", "resource/egress limits", "kill switch"],
            ["malicious extension tests", "timeout/memory/egress enforcement", "transactional install/rollback"],
            "Disable the extension version and terminate its isolated worker without changing core state.",
        ))
    phases.append(_phase(
        len(phases) + 1,
        "operations-security-and-scale",
        "Prove the service under representative load, failure and security conditions.",
        ["SLOs", "dashboards/alerts", "runbooks", "load model", "SBOM/provenance"],
        ["SAST/dependency/secret/container/IaC scans", "DAST", "load/pool/backpressure", "failure injection", "recovery exercise"],
        "Stop rollout automatically or explicitly at the first SLO/security gate breach.",
    ))
    phases.append(_phase(
        len(phases) + 1,
        "immutable-progressive-release",
        "Promote one immutable artifact and prove the exact running revision.",
        ["signed artifact digest", "migration checksum", "canary policy", "rollback artifact", "release evidence ledger"],
        ["all relevant CI terminal and green", "runtime revision/digest readback", "real business canary", "observation window"],
        "Roll back to the confirmed immutable artifact; do not reverse incompatible data destructively.",
    ))
    if not zero_downtime_required:
        phases[-2]["gates"].append("document the accepted maintenance window and user-visible behavior")

    hash_payload = {
        "revision": assessment["revision"],
        "targetOutcome": target_outcome,
        "phases": phases,
        "multiTenancy": include_multi_tenancy,
        "plugins": include_plugins,
        "zeroDowntime": zero_downtime_required,
    }
    return BackendDeliveryPlanResult(
        schemaVersion="sovereign.enterprise-backend-delivery-plan.v1",
        ok=True,
        status="BACKEND_DELIVERY_PLAN_READY",
        revision=str(assessment["revision"]),
        targetOutcome=target_outcome,
        phases=phases,
        crossCuttingContracts=[
            "typed configuration and validation",
            "least privilege and secret redaction",
            "timeouts, retries, idempotency and backpressure",
            "structured logs, metrics, traces and SLO ownership",
            "versioned APIs/events/migrations and compatibility",
            "exact revision, artifact digest and rollback evidence",
        ],
        stopConditions=[
            "revision authority conflicts",
            "unresolved P0/P1 security or data-integrity finding",
            "migration preview or restore fails",
            "required test/scan is unavailable or failed",
            "runtime canary or SLO disproves readiness",
        ],
        planSha256=_canonical_hash(hash_payload),
        mutationPerformed=False,
        runtimeVerified=False,
        truthNotice="Every phase is PLANNED_NOT_EXECUTED until its real gates pass on the exact revision and environment.",
    )


def backend_api_security_plan(
    workspace_id: WorkspaceId,
    exposure: Literal["private", "partner", "public", "admin"] = "public",
    auth_mode: Literal["session", "oidc", "oauth2", "jwt", "mtls", "mixed", "undecided"] = "undecided",
    data_sensitivity: Literal["low", "moderate", "high", "regulated"] = "moderate",
    multi_tenant: bool = False,
    dynamic_endpoints: bool = False,
    plugin_runtime: bool = False,
) -> BackendSecurityPlanResult:
    """Use this when you need a threat-driven API security contract and verifiable DevSecOps gates for a backend surface."""
    assessment = _assessment_payload(_repo(workspace_id), "security", 100)
    security_evidence = assessment["capabilities"].get("security", [])
    observed_names = {str(item.get("name")) for item in security_evidence}
    threats: list[dict[str, Any]] = [
        {
            "family": "identity-and-token-validation",
            "applicable": True,
            "controls": [
                "validate issuer, audience, signature, algorithm, expiry and not-before",
                "use Authorization Code plus PKCE for interactive OAuth/OIDC clients",
                "use short-lived access and rotation/revocation-aware refresh credentials",
                "separate admin scopes and require step-up authentication for high-impact actions",
            ],
            "verification": ["invalid issuer/audience/signature tests", "expired/revoked token tests", "session fixation and logout tests"],
        },
        {
            "family": "object-field-function-authorization",
            "applicable": True,
            "controls": [
                "deny by default at route, object, field and action boundaries",
                "centralize policy decisions and enforce them server-side",
                "audit privileged and bulk actions with stable actor and reason references",
            ],
            "verification": ["allow/deny matrix", "horizontal and vertical privilege tests", "admin policy regression"],
        },
        {
            "family": "tenant-isolation",
            "applicable": multi_tenant,
            "controls": [
                "bind tenant scope from authenticated server context, never request input",
                "enforce tenant filters/row policies plus backup, export and deletion boundaries",
                "apply per-tenant quotas and operator-access audit",
            ],
            "verification": ["cross-tenant negative integration tests", "tenant restore/export/delete tests", "noisy-neighbor load test"],
        },
        {
            "family": "injection-ssrf-and-parser-abuse",
            "applicable": True,
            "controls": [
                "validate type, length, range, cardinality and cross-field invariants",
                "parameterize values and allowlist dynamic identifiers/filters",
                "bound JSON nesting, decompression, GraphQL complexity and upload archives",
                "allowlist outbound destinations and revalidate redirects/DNS/IP for SSRF-sensitive fetches",
            ],
            "verification": ["fuzz/property tests", "SQL/NoSQL/command injection tests", "SSRF redirect and private-network tests", "parser limit tests"],
        },
        {
            "family": "browser-and-api-boundaries",
            "applicable": exposure in {"public", "partner", "admin"},
            "controls": [
                "explicit CORS origins and methods",
                "Secure HttpOnly SameSite cookies plus CSRF protection when cookie authenticated",
                "CSP and output encoding at admin/frontend surfaces",
                "stable redacted error codes and correlation IDs",
            ],
            "verification": ["CORS preflight tests", "CSRF negative tests", "XSS/error redaction tests"],
        },
        {
            "family": "secrets-cryptography-and-data",
            "applicable": True,
            "controls": [
                "store secrets and root keys in a managed secret store/KMS with least privilege and rotation",
                "use current TLS and managed authenticated encryption for sensitive stored data",
                "hash passwords with an approved adaptive password hash",
                "classify, minimize, retain and delete data explicitly; encrypt and restore-test backups",
            ],
            "verification": ["secret scan", "key rotation exercise", "TLS policy check", "backup restore and deletion proof"],
        },
        {
            "family": "abuse-availability-and-cost",
            "applicable": True,
            "controls": [
                "rate-limit and quota by principal, tenant, route cost and network signal",
                "bound payload, timeout, concurrency, pool and queue depth",
                "use CDN/WAF/network controls for volumetric DDoS",
                "persist scoped idempotency results for retryable mutations",
            ],
            "verification": ["burst/sustained-rate tests", "pool exhaustion and retry-storm tests", "duplicate mutation test", "degraded-mode test"],
        },
        {
            "family": "metadata-driven-endpoints",
            "applicable": dynamic_endpoints,
            "controls": [
                "version and validate metadata against allowlisted types, operations, filters and query cost",
                "compile metadata to an internal plan; never concatenate route code or SQL",
                "enforce object/field/tenant policy and audit on generated operations",
                "treat server-driven UI metadata as non-executable presentation hints",
            ],
            "verification": ["schema compatibility tests", "unknown type/action rejection", "authorization parity with hand-written routes", "query-cost tests"],
        },
        {
            "family": "plugin-isolation-and-supply-chain",
            "applicable": plugin_runtime,
            "controls": [
                "require signed provenance and a declared capability/resource manifest",
                "execute extensions in a separate process, container or Wasm sandbox",
                "limit CPU, memory, time, filesystem and egress; expose a narrow typed host API",
                "provide transactional install/upgrade/rollback and a kill switch",
            ],
            "verification": ["malicious package tests", "egress/filesystem escape tests", "resource exhaustion tests", "rollback proof"],
        },
    ]
    applicable = [item for item in threats if item["applicable"]]
    gaps: list[str] = []
    if auth_mode == "undecided":
        gaps.append("authentication mode and token/session lifecycle are undecided")
    if not ({"oauth-oidc", "jwt"} & observed_names) and exposure in {"public", "partner", "admin"}:
        gaps.append("no static OAuth/OIDC/JWT marker was found; runtime identity remains unverified")
    if multi_tenant and "multi-tenancy" not in {
        str(item.get("name")) for item in assessment["capabilities"].get("platform", [])
    }:
        gaps.append("multi-tenancy requested without static tenant-boundary evidence")
    if dynamic_endpoints and "metadata-driven" not in {
        str(item.get("name")) for item in assessment["capabilities"].get("platform", [])
    }:
        gaps.append("dynamic endpoints requested without a discovered metadata schema contract")
    if plugin_runtime and "plugin-system" not in {
        str(item.get("name")) for item in assessment["capabilities"].get("platform", [])
    }:
        gaps.append("plugin runtime requested without a discovered extension manifest or isolation contract")
    if data_sensitivity in {"high", "regulated"} and "secret-management" not in observed_names:
        gaps.append("high-sensitivity data requested without static managed-secret/KMS evidence")

    priorities = [
        "threat model every trust boundary and data flow",
        "server-side deny-by-default authorization with negative tests",
        "strict ingress validation, bounded work and redacted errors",
        "managed secrets, key rotation, TLS and encrypted recoverable backups",
        "principal/tenant/cost-aware abuse controls plus network-layer DDoS protection",
    ]
    if multi_tenant:
        priorities.insert(2, "make tenant identity an enforced persistence and policy invariant")
    if dynamic_endpoints:
        priorities.append("allowlist and version every metadata-generated operation")
    if plugin_runtime:
        priorities.append("keep extension code outside the main backend process with capabilities and resource limits")

    return BackendSecurityPlanResult(
        schemaVersion="sovereign.enterprise-backend-api-security-plan.v1",
        ok=True,
        status="API_SECURITY_PLAN_READY",
        revision=str(assessment["revision"]),
        threatProfile={
            "exposure": exposure,
            "authMode": auth_mode,
            "dataSensitivity": data_sensitivity,
            "multiTenant": multi_tenant,
            "dynamicEndpoints": dynamic_endpoints,
            "pluginRuntime": plugin_runtime,
        },
        observedSecurityEvidence=security_evidence,
        threatControls=applicable,
        priorityControls=priorities,
        verificationGates=[
            "unit tests for policy, validation and redaction",
            "real identity/database integration and tenant-isolation tests",
            "public/admin API contract and abuse tests",
            "SAST, dependency, secret, container and IaC scans",
            "authenticated DAST in an isolated environment",
            "load, pool, retry, backpressure and recovery tests",
            "audit-log integrity and incident runbook exercise",
        ],
        candidateGaps=gaps,
        mutationPerformed=False,
        complianceVerified=False,
        secretValuesReturned=False,
        truthNotice="This is a threat-driven control plan. Static markers do not prove implementation, compliance or resistance to attack.",
    )


def _remote_repo_name(url: str) -> str | None:
    for pattern in (
        r"github\.com[/:]([^/]+/[^/]+?)(?:\.git)?$",
        r"git\.chatgpt-team\.site[/:]([^/]+/[^/]+?)(?:\.git)?$",
    ):
        match = re.search(pattern, url)
        if match:
            return match.group(1).removesuffix(".git")
    return None


def _validated_sha(value: str, field: str) -> str:
    normalized = str(value or "").strip().casefold()
    if normalized and not _SHA_RE.fullmatch(normalized):
        raise ValueError(f"{field} must be an exact 40-character commit SHA")
    return normalized


def _github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
        "User-Agent": "sovereign-enterprise-backend-revision-resolver",
    }
    token = str(getattr(getattr(_RUNTIME, "config", None), "github_token", "") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _github_json(url: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        response = requests.get(url, headers=_github_headers(), timeout=30)
    except requests.RequestException:
        return None, "GITHUB_TRANSPORT_FAILED"
    if response.status_code != 200:
        return None, f"GITHUB_HTTP_{response.status_code}"
    try:
        payload = response.json()
    except ValueError:
        return None, "GITHUB_RESPONSE_INVALID"
    return (payload, None) if isinstance(payload, dict) else (None, "GITHUB_RESPONSE_INVALID")


def _fetch_refs(repo: Path, base_branch: str, pr_number: int) -> tuple[bool, str | None]:
    refspecs = [f"+refs/heads/{base_branch}:refs/remotes/origin/{base_branch}"]
    if pr_number:
        refspecs.append(f"+refs/pull/{pr_number}/head:refs/remotes/origin/pull/{pr_number}/head")
    argv = ["git", "-C", str(repo), "fetch", "--no-tags", "origin", *refspecs]
    askpass_dir: str | None = None
    env: dict[str, str] | None = None
    try:
        askpass_factory = getattr(_RUNTIME, "_askpass", None)
        if callable(askpass_factory):
            askpass_dir, env = askpass_factory()
        completed = subprocess.run(
            argv,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
            env=env,
        )
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        return False, "REMOTE_FETCH_FAILED"
    finally:
        if askpass_dir:
            shutil.rmtree(askpass_dir, ignore_errors=True)
    return (True, None) if completed.returncode == 0 else (False, "REMOTE_FETCH_FAILED")


def _ci_evidence(repository: str, sha: str) -> tuple[dict[str, Any], str | None]:
    if not sha:
        return {"status": "NOT_REQUESTED", "headSha": None, "checkCount": 0, "checks": []}, None
    payload, error = _github_json(
        f"https://api.github.com/repos/{repository}/commits/{sha}/check-runs?per_page=100"
    )
    if error or payload is None:
        return {"status": "UNAVAILABLE", "headSha": sha, "checkCount": 0, "checks": []}, error
    raw_checks = payload.get("check_runs") if isinstance(payload.get("check_runs"), list) else []
    checks: list[dict[str, Any]] = []
    terminal = True
    failure = False
    for raw in raw_checks[:100]:
        if not isinstance(raw, dict):
            continue
        status = str(raw.get("status") or "")[:40]
        conclusion = str(raw.get("conclusion") or "")[:40]
        if status != "completed":
            terminal = False
        if conclusion in {"failure", "cancelled", "timed_out", "action_required", "startup_failure"}:
            failure = True
        checks.append({
            "name": _safe_evidence_path(str(raw.get("name") or "")[:160]),
            "status": status,
            "conclusion": conclusion or None,
            "headSha": str(raw.get("head_sha") or sha)[:40],
        })
    if not checks:
        status_name = "NO_CHECKS"
    elif failure:
        status_name = "FAILED"
    elif not terminal:
        status_name = "PENDING"
    else:
        status_name = "TERMINAL_NO_FAILURES"
    return {
        "status": status_name,
        "headSha": sha,
        "checkCount": len(checks),
        "allChecksTerminal": bool(checks) and terminal,
        "failurePresent": failure,
        "checks": checks,
        "relevantChecksGreenClaimed": False,
    }, None


def _deployed_mcp_evidence() -> dict[str, Any]:
    if _BROKER is None:
        return {
            "status": "UNAVAILABLE",
            "revision": None,
            "imageDigest": None,
            "imageReference": None,
            "runtimeIdentity": None,
            "revisionVerified": False,
            "digestVerified": False,
        }
    try:
        payload = _BROKER.call("mcp_self_update_status", {}, timeout=10)
    except Exception:
        payload = {}
    payload = payload if isinstance(payload, dict) else {}
    revision = str(payload.get("revision") or "").strip().casefold()
    revision = revision if _SHA_RE.fullmatch(revision) else None
    image_reference = str(payload.get("image") or "").strip().casefold()
    image_match = re.fullmatch(
        r"(ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+)@(sha256:[0-9a-f]{64})",
        image_reference,
    )
    image_digest = image_match.group(2) if image_match else None
    image_id = str(payload.get("image_id") or "").strip().casefold()
    image_id = image_id if re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) else None
    evidence_sha = str(payload.get("evidence_sha256") or "").strip().casefold()
    evidence_sha = evidence_sha if re.fullmatch(r"[0-9a-f]{64}", evidence_sha) else None
    revision_verified = bool(
        payload.get("ok") is True
        and payload.get("status") == "UPDATED"
        and revision
        and payload.get("revision_verified") is True
    )
    digest_verified = bool(
        image_digest
        and payload.get("image_digest_verified") is True
        and image_id
    )
    result = {
        "status": str(payload.get("status") or "UNAVAILABLE")[:80],
        "revision": revision,
        "imageDigest": image_digest,
        "imageReference": image_reference if image_match else None,
        "runtimeIdentity": {
            "imageId": image_id,
            "evidenceSha256": evidence_sha,
            "kappaPos": payload.get("kappa_pos") if isinstance(payload.get("kappa_pos"), int) else None,
            "updatedAt": payload.get("updated_at") if isinstance(payload.get("updated_at"), int) else None,
            "containerHealthy": payload.get("container_healthy") is True,
            "mcpProtocolReady": payload.get("mcp_protocol_ready") is True,
            "brokerRpcReady": payload.get("broker_rpc_ready") is True,
        },
        "revisionVerified": revision_verified,
        "digestVerified": digest_verified,
    }
    if not image_digest:
        result["digestGap"] = "mcp_self_update_status did not expose a valid immutable running image digest"
    return result


def repository_revision_resolve(
    workspace_id: WorkspaceId,
    base_branch: BaseBranch = "main",
    pr_number: PullRequestNumber = 0,
    expected_workspace_sha: OptionalExactSha = "",
    expected_base_sha: OptionalExactSha = "",
    expected_pr_head_sha: OptionalExactSha = "",
    require_clean: bool = True,
    include_ci: bool = True,
    include_deployed_mcp: bool = True,
) -> RepositoryRevisionResolutionResult:
    """Use this when you need the exact current workspace, fetched base, PR, merge, CI-head, and deployed-MCP revision tuple."""
    if not _SAFE_BRANCH_RE.fullmatch(base_branch) or ".." in base_branch or base_branch.endswith("/"):
        raise ValueError("base_branch is invalid")
    allowed_bases = tuple(getattr(getattr(_RUNTIME, "config", None), "allowed_base_branches", (base_branch,)))
    if allowed_bases and base_branch not in allowed_bases:
        raise ValueError("base_branch is not allowed by the private MCP runtime")
    pr_number = int(pr_number)
    if pr_number < 0 or pr_number > 10_000_000:
        raise ValueError("pr_number is outside the bounded range")
    expected_workspace = _validated_sha(expected_workspace_sha, "expected_workspace_sha")
    expected_base = _validated_sha(expected_base_sha, "expected_base_sha")
    expected_pr_head = _validated_sha(expected_pr_head_sha, "expected_pr_head_sha")

    repo = _repo(workspace_id)
    remote_url = _git(repo, "remote", "get-url", "origin", check=False)
    remote_repository = _remote_repo_name(remote_url)
    configured_repository = str(getattr(getattr(_RUNTIME, "config", None), "repository", "") or "")
    repository = configured_repository or remote_repository or ""
    conflicts: list[str] = []
    gaps: list[str] = []
    if not remote_repository or (configured_repository and remote_repository.casefold() != configured_repository.casefold()):
        conflicts.append("REMOTE_REPOSITORY_MISMATCH")

    fetched, fetch_error = _fetch_refs(repo, base_branch, pr_number)
    if not fetched:
        conflicts.append(fetch_error or "REMOTE_FETCH_FAILED")

    workspace_head = _resolve_commit(repo, "HEAD")
    branch_raw = _git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False) or None
    branch = _safe_evidence_path(branch_raw) if branch_raw else None
    dirty_text = _git(repo, "status", "--porcelain=v1", "--untracked-files=normal")
    raw_dirty_entries = dirty_text.splitlines()[:200] if dirty_text else []
    dirty_entries = [_safe_evidence_path(entry) for entry in raw_dirty_entries]
    base_head = _resolve_commit(repo, f"origin/{base_branch}")
    merge_base = (
        _git(repo, "merge-base", workspace_head, base_head, check=False)
        if workspace_head and base_head
        else ""
    ) or None
    if not workspace_head:
        conflicts.append("WORKSPACE_HEAD_UNRESOLVED")
    if not base_head:
        conflicts.append("BASE_HEAD_UNRESOLVED")
    if require_clean and dirty_entries:
        conflicts.append("WORKTREE_DIRTY")

    pull_request: dict[str, Any] | None = None
    pr_head: str | None = None
    pr_base: str | None = None
    merged_change: str | None = None
    base_advanced: bool | None = None
    pr_state = ""
    if pr_number:
        payload, pr_error = _github_json(f"https://api.github.com/repos/{repository}/pulls/{pr_number}")
        if pr_error or payload is None:
            conflicts.append("GITHUB_PR_READ_FAILED")
            gaps.append(pr_error or "GITHUB_PR_READ_FAILED")
        else:
            head = payload.get("head") if isinstance(payload.get("head"), dict) else {}
            base = payload.get("base") if isinstance(payload.get("base"), dict) else {}
            pr_head_value = str(head.get("sha") or "").casefold()
            pr_base_value = str(base.get("sha") or "").casefold()
            pr_head = pr_head_value if _SHA_RE.fullmatch(pr_head_value) else None
            pr_base = pr_base_value if _SHA_RE.fullmatch(pr_base_value) else None
            merge_value = str(payload.get("merge_commit_sha") or "").casefold()
            merged_change = merge_value if payload.get("merged_at") and _SHA_RE.fullmatch(merge_value) else None
            pr_state = "merged" if payload.get("merged_at") else str(payload.get("state") or "unknown")
            head_ref = str(head.get("ref") or "")[:160]
            base_ref = str(base.get("ref") or "")[:160]
            pull_request = {
                "number": pr_number,
                "state": pr_state,
                "draft": bool(payload.get("draft")),
                "headRef": _safe_evidence_path(head_ref),
                "baseRef": _safe_evidence_path(base_ref),
                "headSha": pr_head,
                "baseSha": pr_base,
                "mergeCommitSha": merged_change,
                "mergedAt": str(payload.get("merged_at") or "")[:80] or None,
                "mergeable": payload.get("mergeable") if isinstance(payload.get("mergeable"), bool) else None,
            }
            if base_ref != base_branch:
                conflicts.append("PR_BASE_BRANCH_MISMATCH")
            fetched_pr_head = _resolve_commit(repo, f"refs/remotes/origin/pull/{pr_number}/head")
            if pr_head and fetched_pr_head != pr_head:
                conflicts.append("FETCHED_PR_HEAD_MISMATCH")
            if pr_state != "merged" and pr_head and workspace_head != pr_head:
                conflicts.append("WORKSPACE_PR_HEAD_MISMATCH")
            if pr_base and base_head:
                base_advanced = pr_base != base_head

    expected_matches: dict[str, bool | None] = {
        "workspace": workspace_head == expected_workspace if expected_workspace else None,
        "base": base_head == expected_base if expected_base else None,
        "prHead": pr_head == expected_pr_head if expected_pr_head else None,
    }
    if expected_matches["workspace"] is False:
        conflicts.append("EXPECTED_WORKSPACE_SHA_MISMATCH")
    if expected_matches["base"] is False:
        conflicts.append("EXPECTED_BASE_SHA_MISMATCH")
    if expected_matches["prHead"] is False:
        conflicts.append("EXPECTED_PR_HEAD_SHA_MISMATCH")

    ci_evidence: dict[str, Any] = {
        "status": "NOT_REQUESTED",
        "headSha": pr_head,
        "checkCount": 0,
        "checks": [],
        "relevantChecksGreenClaimed": False,
    }
    if include_ci and pr_head:
        ci_evidence, ci_error = _ci_evidence(repository, pr_head)
        if ci_error:
            gaps.append(ci_error)
    elif include_ci and not pr_head:
        gaps.append("CI_HEAD_SHA_UNAVAILABLE")

    deployed = _deployed_mcp_evidence() if include_deployed_mcp else {
        "status": "NOT_REQUESTED",
        "revision": None,
        "imageDigest": None,
        "imageReference": None,
        "runtimeIdentity": None,
        "revisionVerified": False,
        "digestVerified": False,
    }
    if include_deployed_mcp and not deployed.get("revisionVerified"):
        gaps.append("DEPLOYED_MCP_REVISION_UNVERIFIED")
    if include_deployed_mcp and not deployed.get("digestVerified"):
        gaps.append("DEPLOYED_MCP_DIGEST_UNAVAILABLE")

    conflicts = sorted(set(conflicts))
    gaps = sorted(set(gaps))
    if conflicts:
        authoritative = None
        next_action = "stop_and_resolve_revision_conflicts"
    elif pr_number and pr_state == "merged":
        authoritative = base_head
        next_action = "start_new_workspace_from_current_base_head"
    elif pr_number:
        authoritative = pr_head
        next_action = "continue_at_exact_pr_head_then_recheck_reviews_and_ci"
    elif branch_raw == base_branch:
        authoritative = base_head
        next_action = "start_or_continue_from_current_base_head"
    else:
        authoritative = workspace_head
        next_action = "continue_on_exact_workspace_head_and_recheck_base_before_merge"

    return RepositoryRevisionResolutionResult(
        schemaVersion="sovereign.repository-revision-resolution.v1",
        ok=not conflicts,
        status="REVISION_RESOLVED" if not conflicts else "REVISION_CONFLICT",
        repositoryFullName=remote_repository,
        workspaceId=workspace_id,
        branch=branch,
        worktreeClean=not dirty_entries,
        dirtyEntries=dirty_entries,
        workspaceHeadSha=workspace_head,
        currentBaseBranch=base_branch,
        currentBaseHeadSha=base_head,
        mergeBaseSha=merge_base,
        pullRequest=pull_request,
        prHeadSha=pr_head,
        prBaseSha=pr_base,
        mergedChangeSha=merged_change,
        baseAdvancedSincePr=base_advanced,
        ciEvidence=ci_evidence,
        deployedMcpEvidence=deployed,
        expectedMatches=expected_matches,
        revisionConflicts=conflicts,
        evidenceGaps=gaps,
        authoritativeNextRevision=authoritative,
        nextAllowedAction=next_action,
        mutationPerformed=False,
        secretValuesReturned=False,
    )


def register(mcp: Any, runtime: Any, broker: Any = None) -> None:
    global _RUNTIME, _BROKER, _REGISTERED
    _RUNTIME = runtime
    _BROKER = broker
    if _REGISTERED:
        return
    for tool in (
        backend_engineering_tool_inventory,
        backend_architecture_assess,
        backend_stack_select,
        backend_delivery_plan,
        backend_api_security_plan,
    ):
        mcp.tool(annotations=LOCAL_READ_ONLY)(tool)
    mcp.tool(annotations=NETWORK_READ_ONLY)(repository_revision_resolve)
    _REGISTERED = True
