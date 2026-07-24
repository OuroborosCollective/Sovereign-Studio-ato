from __future__ import annotations

from dataclasses import asdict, dataclass
from fnmatch import fnmatch
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Annotated, Any, Final, Literal

from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field


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

Capability = Literal[
    "repository",
    "ci",
    "release",
    "runtime",
    "container",
    "database",
    "migration",
    "llm",
    "agent",
    "billing",
    "backup",
    "observability",
    "configuration",
    "mcp",
    "security",
    "ownership",
    "compliance",
    "learning",
    "android",
    "document",
    "deterministic",
    "maintenance",
    "privacy",
    "performance",
    "topology",
    "queue",
    "supply-chain",
    "authentication",
    "tenant",
]
EffectClass = Literal["read", "workspace-write", "external-write"]
EvidenceStatus = Literal["success", "failure", "pending", "unknown"]
RouteHealth = Literal["healthy", "degraded", "blocked", "unknown"]
QuotaState = Literal["available", "limited", "exhausted", "unknown"]
RunState = Literal[
    "RECEIVED",
    "RUNNING",
    "WAITING_FOR_OWNER",
    "BLOCKED",
    "FAILED_RECOVERABLE",
    "FAILED_FINAL",
    "SUCCEEDED",
    "CANCELLED",
    "UNKNOWN",
]

WorkspaceId = Annotated[str, Field(min_length=1, max_length=160)]
ExactSha = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
OptionalExactSha = Annotated[str, Field(pattern=r"^(?:|[0-9a-f]{40})$")]
BoundedText = Annotated[str, Field(min_length=1, max_length=2000)]
FailureFamily = Annotated[str, Field(pattern=r"^[A-Z0-9][A-Z0-9_:-]{1,159}$")]
Sha256Value = Annotated[str, Field(pattern=r"^(?:|[0-9a-f]{64})$")]
RequiredSha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

_MCP: Any = None
_RUNTIME: Any = None
_DATABASE: Any = None
_BROKER: Any = None
_REGISTERED = False

_SECRET_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|password\s*[:=]|api[_-]?key\s*[:=]|"
    r"authorization\s*:\s*bearer)",
    re.I,
)
_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[a-z0-9][a-z0-9_-]{1,63}")
_CREATE_TABLE_RE: Final[re.Pattern[str]] = re.compile(
    r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:(?P<schema>[A-Za-z_][A-Za-z0-9_]*)\.)?[\"`]?"
    r"(?P<table>[A-Za-z_][A-Za-z0-9_]*)[\"`]?",
    re.I,
)
_HISTORICAL_SCHEMA_OWNERSHIP_PATH: Final[Path] = Path(
    "docs/architecture/POSTGRES_HISTORICAL_SCHEMA_OWNERSHIP.v1.json"
)
_HISTORICAL_SCHEMA_OWNERSHIP_VERSION: Final[str] = "sovereign.postgres-historical-schema-ownership.v1"
_TABLE_IDENTITY_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$")


def _strip_sql_comments(text: str) -> str:
    """Remove SQL comments while preserving quoted strings and line positions."""
    output: list[str] = []
    index = 0
    state = "code"
    length = len(text)

    while index < length:
        current = text[index]
        following = text[index + 1] if index + 1 < length else ""

        if state == "code":
            if current == "-" and following == "-":
                output.extend((" ", " "))
                index += 2
                state = "line-comment"
                continue
            if current == "/" and following == "*":
                output.extend((" ", " "))
                index += 2
                state = "block-comment"
                continue
            if current == "'":
                state = "single-quote"
            elif current == '"':
                state = "double-quote"
            output.append(current)
            index += 1
            continue

        if state == "line-comment":
            if current == "\n":
                output.append("\n")
                state = "code"
            else:
                output.append(" ")
            index += 1
            continue

        if state == "block-comment":
            if current == "*" and following == "/":
                output.extend((" ", " "))
                index += 2
                state = "code"
                continue
            output.append("\n" if current == "\n" else " ")
            index += 1
            continue

        output.append(current)
        if state == "single-quote" and current == "'":
            if following == "'":
                output.append(following)
                index += 2
                continue
            state = "code"
        elif state == "double-quote" and current == '"':
            if following == '"':
                output.append(following)
                index += 2
                continue
            state = "code"
        index += 1

    return "".join(output)


_KEYWORD_INTENT_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (
        "python_keyword_intent",
        re.compile(r"(?:\.lower\(\)|\.casefold\(\)).{0,120}(?:\bin\b|startswith\(|endswith\()", re.I),
    ),
    (
        "javascript_keyword_intent",
        re.compile(r"(?:\.toLowerCase\(\)|\.includes\(|\.startsWith\(|\.endsWith\().{0,160}", re.I),
    ),
)

_PREFIX_CAPABILITIES: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("repository_", ("repository", "ci")),
    ("android_", ("android", "release")),
    ("postgres_", ("database", "migration")),
    ("vector_", ("database", "learning")),
    ("litellm_", ("llm", "billing")),
    ("controller_", ("agent", "runtime")),
    ("a2a_", ("agent", "runtime")),
    ("patchmon_", ("container", "runtime")),
    ("document_", ("document", "runtime")),
    ("deterministic_", ("deterministic", "repository")),
    ("backend_", ("repository", "runtime", "security")),
    ("freemium_", ("billing", "compliance")),
    ("openai_", ("llm", "security")),
    ("owner_", ("security", "ownership")),
    ("mcp_", ("mcp", "runtime")),
    ("vps_", ("container", "runtime")),
    ("managed_compose_", ("container", "configuration")),
    ("deploy_", ("release", "container")),
    ("rollback_", ("release", "container")),
    ("proven_learning_", ("learning", "compliance")),
    ("skill_", ("mcp", "repository")),
    ("tool_", ("mcp",)),
    ("evidence_", ("compliance", "release")),
    ("schema_", ("database", "migration")),
    ("llm_route_", ("llm", "billing", "observability")),
    ("agent_run_", ("agent", "runtime", "observability")),
    ("semantic_intent_", ("security", "mcp", "repository")),
    ("cost_credit_", ("billing", "database")),
    ("backup_restore_", ("backup", "database", "runtime")),
    ("slo_error_", ("observability", "runtime")),
    ("configuration_drift_", ("configuration", "runtime", "container")),
    ("runtime_runbook_", ("runtime", "observability")),
    ("ownership_codeowners_", ("ownership", "security", "repository")),
    ("compliance_evidence_", ("compliance", "release")),
    ("vps_capacity_", ("container", "runtime", "observability", "performance")),
    ("runtime_dependency_", ("runtime", "observability", "container")),
    ("outbox_queue_", ("queue", "database", "runtime")),
    ("scheduled_maintenance_", ("maintenance", "runtime", "release")),
    ("runtime_topology_", ("topology", "container", "configuration")),
    ("postgres_query_", ("database", "performance", "observability")),
    ("data_integrity_", ("database", "deterministic", "compliance")),
    ("data_repair_", ("database", "deterministic")),
    ("vector_memory_", ("database", "learning", "queue")),
    ("memory_poisoning_", ("learning", "security", "compliance")),
    ("learning_pattern_", ("learning", "compliance")),
    ("data_retention_", ("privacy", "compliance", "database")),
    ("multi_tenant_", ("tenant", "security", "privacy")),
    ("mcp_schema_", ("mcp", "configuration")),
    ("mcp_protocol_", ("mcp", "security", "observability")),
    ("tool_permission_", ("mcp", "security")),
    ("dynamic_execution_", ("security", "repository", "runtime")),
    ("skill_capability_", ("mcp", "repository")),
    ("skill_lifecycle_", ("mcp", "compliance")),
    ("skill_regression_", ("mcp", "ci")),
    ("tool_idempotency_", ("mcp", "deterministic", "ci")),
    ("owner_approval_policy_", ("ownership", "security", "compliance")),
    ("secret_lifecycle_", ("security", "compliance")),
    ("secret_literal_", ("security", "repository")),
    ("sbom_provenance_", ("supply-chain", "release", "security")),
    ("dependency_vulnerability_", ("supply-chain", "security", "repository")),
    ("authentication_chaos_", ("authentication", "security", "ci")),
)

_SKILL_PROFILES: Final[dict[str, dict[str, Any]]] = {
    "sovereign-mcp-optimal-operation": {
        "priority": "P0",
        "tools": ["sovereign_operating_profile_status", "sovereign_mission_preflight"],
        "purpose": "Persist and technically enforce mission-first, contract-bound and evidence-first operation across sessions and revisions.",
    },
    "sovereign-tool-capability-router": {
        "priority": "P0",
        "tools": ["tool_recommend_for_mission", "operational_skill_inventory"],
        "purpose": "Deterministically rank the smallest eligible Sovottt tool set from structured capabilities and effect boundaries.",
    },
    "sovereign-mcp-toolchain-composer": {
        "priority": "P0",
        "tools": ["mcp_toolchain_contract_inventory", "mcp_toolchain_compile", "mcp_toolchain_validate", "mcp_toolchain_next_step", "mcp_diagnostic_chain_plan"],
        "purpose": "Build and validate bounded MCP toolchain graphs from registered contracts.",
    },
    "sovereign-mcp-registry-verifier": {
        "priority": "P0",
        "tools": ["mcp_tool_contract_registry", "mcp_registry_snapshot_verify"],
        "purpose": "Hash and compare the real FastMCP tool registry, schemas, annotations and expected tool names.",
    },
    "sovereign-evidence-graph-operator": {
        "priority": "P0",
        "tools": ["evidence_graph_build"],
        "purpose": "Bind revision, CI, artifact, deployment and runtime evidence without inferring missing success.",
    },
    "sovereign-schema-ownership-reconciler": {
        "priority": "P0",
        "tools": ["schema_migration_reconcile"],
        "purpose": "Compare migration-owned tables with the live PostgreSQL schema without returning row data.",
    },
    "sovereign-llm-route-sre": {
        "priority": "P0",
        "tools": ["llm_route_reliability_assess"],
        "purpose": "Gate route readiness on model inventory, activation, pricing, health and quota evidence.",
    },
    "sovereign-agent-run-recovery": {
        "priority": "P0",
        "tools": ["agent_run_liveness_assess"],
        "purpose": "Classify resumable, owner-blocked, provider-blocked and terminal agent runs.",
    },
    "sovereign-semantic-intent-boundary-guardian": {
        "priority": "P0",
        "tools": ["semantic_intent_boundary_audit"],
        "purpose": "Find candidate free-language interpretation outside the LLM boundary for human review.",
    },
    "sovereign-cost-credit-settlement-reconciler": {
        "priority": "P0",
        "tools": ["cost_credit_settlement_reconcile"],
        "purpose": "Reconcile integer micros, credits and settlement identity without floating-point billing math.",
    },
    "sovereign-backup-restore-verifier": {
        "priority": "P0",
        "tools": ["backup_restore_evidence_verify"],
        "purpose": "Require checksum-matched restore evidence instead of treating backup creation as recovery proof.",
    },
    "sovereign-slo-error-budget-operator": {
        "priority": "P0",
        "tools": ["slo_error_budget_assess"],
        "purpose": "Calculate availability and latency error-budget state from bounded integer evidence.",
    },
    "sovereign-configuration-drift-operator": {
        "priority": "P0",
        "tools": ["configuration_drift_assess"],
        "purpose": "Compare workspace, expected and installed MCP revision plus bounded configuration markers.",
    },
    "sovereign-mcp-tool-contract-registry": {
        "priority": "P0",
        "tools": ["mcp_tool_contract_registry"],
        "purpose": "Expose the active registry with capability, effect, annotations and canonical schema hashes.",
    },
    "sovereign-runtime-runbook-generator": {
        "priority": "P1",
        "tools": ["runtime_runbook_generate"],
        "purpose": "Produce bounded diagnosis, stop, verification and rollback sequences from real registered tools.",
    },
    "sovereign-ownership-codeowners-guardian": {
        "priority": "P1",
        "tools": ["ownership_codeowners_guard"],
        "purpose": "Map critical changed paths to CODEOWNERS and report uncovered review domains.",
    },
    "sovereign-compliance-evidence-exporter": {
        "priority": "P1",
        "tools": ["compliance_evidence_export"],
        "purpose": "Create a canonical revision-bound evidence export with a deterministic digest and explicit gaps.",
    },
    "sovereign-vps-capacity-resource-pressure": {
        "priority": "P0",
        "tools": ["vps_capacity_resource_pressure_assess"],
        "purpose": "Separate CPU, memory, swap, filesystem, inode, container, queue and pool pressure from software defects.",
    },
    "sovereign-runtime-dependency-health-matrix": {
        "priority": "P0",
        "tools": ["runtime_dependency_health_matrix"],
        "purpose": "Run bounded dependency canaries and map failures to blocked product functions.",
    },
    "sovereign-outbox-queue-liveness": {
        "priority": "P0",
        "tools": ["outbox_queue_liveness_assess"],
        "purpose": "Detect stalled outboxes, retries, dead letters, duplicates and missing worker progress.",
    },
    "sovereign-scheduled-maintenance-coordinator": {
        "priority": "P1",
        "tools": ["scheduled_maintenance_coordinate"],
        "purpose": "Build conflict-free maintenance windows without executing maintenance.",
    },
    "sovereign-runtime-topology-change-auditor": {
        "priority": "P0",
        "tools": ["runtime_topology_change_audit"],
        "purpose": "Compare services, networks, volumes and identities between confirmed revisions.",
    },
    "sovereign-postgres-query-index-performance": {
        "priority": "P0",
        "tools": ["postgres_query_index_performance_assess"],
        "purpose": "Assess bounded query latency, index coverage, locking and pool pressure metadata.",
    },
    "sovereign-data-integrity-invariant-auditor": {
        "priority": "P0",
        "tools": ["data_integrity_invariant_audit"],
        "purpose": "Audit cross-table business invariants from exact aggregate evidence.",
    },
    "sovereign-data-repair-planner": {
        "priority": "P0",
        "tools": ["data_repair_plan_build"],
        "purpose": "Create state-bound, idempotent and bounded historical-data repair plans.",
    },
    "sovereign-vector-memory-consistency": {
        "priority": "P0",
        "tools": ["vector_memory_consistency_assess"],
        "purpose": "Reconcile source hashes, outbox state, vector identities and embedding-model versions.",
    },
    "sovereign-memory-poisoning-provenance-guardian": {
        "priority": "P0",
        "tools": ["memory_poisoning_provenance_guard"],
        "purpose": "Quarantine under-evidenced, expired, conflicting or revision-mismatched learning candidates.",
    },
    "sovereign-learning-pattern-lifecycle": {
        "priority": "P1",
        "tools": ["learning_pattern_lifecycle_preview"],
        "purpose": "Preview versioning, replacement, merge, deprecation and removal of learning patterns.",
    },
    "sovereign-data-retention-privacy": {
        "priority": "P0",
        "tools": ["data_retention_privacy_audit"],
        "purpose": "Audit retention, deletion, pseudonymization, export and tenant-key controls.",
    },
    "sovereign-multi-tenant-isolation-verifier": {
        "priority": "P0",
        "tools": ["multi_tenant_isolation_verify"],
        "purpose": "Gate release on negative isolation tests across data and execution budgets.",
    },
    "sovereign-mcp-schema-compatibility-auditor": {
        "priority": "P0",
        "tools": ["mcp_schema_compatibility_audit"],
        "purpose": "Compare published, repository, adapter and agent-expected MCP schemas.",
    },
    "sovereign-mcp-protocol-conformance-fuzzing": {
        "priority": "P0",
        "tools": ["mcp_protocol_conformance_fuzz_plan"],
        "purpose": "Generate reproducible initialize, listing, error, timeout, payload and disconnect fuzz cases.",
    },
    "sovereign-tool-permission-minimizer": {
        "priority": "P0",
        "tools": ["tool_permission_minimize"],
        "purpose": "Derive least-privilege tool permissions from declared and observed requirements.",
    },
    "sovereign-dynamic-execution-containment-auditor": {
        "priority": "P0",
        "tools": ["dynamic_execution_containment_audit"],
        "purpose": "Classify dynamic code and shell candidates by path and required isolation evidence.",
    },
    "sovereign-skill-capability-coverage-mapper": {
        "priority": "P1",
        "tools": ["skill_capability_coverage_map"],
        "purpose": "Map architecture tasks to live registered tools before adding more skills.",
    },
    "sovereign-skill-lifecycle-deprecation": {
        "priority": "P1",
        "tools": ["skill_lifecycle_deprecation_preview"],
        "purpose": "Preview controlled skill states and block unsafe deprecation with active callers.",
    },
    "sovereign-skill-regression-benchmark": {
        "priority": "P0",
        "tools": ["skill_regression_benchmark"],
        "purpose": "Compare expected tool calls, effects and evidence across MCP updates.",
    },
    "sovereign-tool-idempotency-verifier": {
        "priority": "P0",
        "tools": ["tool_idempotency_verify"],
        "purpose": "Detect duplicated side effects and divergent results across identical retries.",
    },
    "sovereign-owner-approval-policy-engine": {
        "priority": "P0",
        "tools": ["owner_approval_policy_evaluate"],
        "purpose": "Centralize approval requirement, TTL, revision and payload binding decisions.",
    },
    "sovereign-secret-lifecycle-rotation": {
        "priority": "P0",
        "tools": ["secret_lifecycle_rotation_assess"],
        "purpose": "Assess secret-reference age, ownership, rotation intervals and canary freshness without raw values.",
    },
    "sovereign-secret-literal-triage": {
        "priority": "P0",
        "tools": ["secret_literal_triage"],
        "purpose": "Separate secret rotation candidates from tests, placeholders and fingerprints without returning literals.",
    },
    "sovereign-sbom-provenance-image-signing": {
        "priority": "P0",
        "tools": ["sbom_provenance_image_signing_verify"],
        "purpose": "Verify revision labels, immutable digests, SBOM, provenance, signature and attestation evidence.",
    },
    "sovereign-dependency-vulnerability-remediation": {
        "priority": "P0",
        "tools": ["dependency_vulnerability_remediation_plan"],
        "purpose": "Prioritize reachable vulnerabilities and minimal upgrade plans.",
    },
    "sovereign-authentication-chaos-negative-test": {
        "priority": "P0",
        "tools": ["authentication_chaos_negative_test_assess"],
        "purpose": "Gate authentication on negative OAuth, PKCE, passkey, session, replay and concurrency evidence.",
    },
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceRecord(StrictModel):
    kind: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]
    identity: Annotated[str, Field(min_length=1, max_length=240)]
    status: EvidenceStatus
    producer: Annotated[str, Field(min_length=1, max_length=240)]
    revision: OptionalExactSha = ""
    digest: Sha256Value = ""
    related_ids: Annotated[list[str], Field(max_length=24)] = []
    summary: Annotated[str, Field(max_length=500)] = ""


class RouteEvidence(StrictModel):
    alias: Annotated[str, Field(min_length=1, max_length=120)]
    provider_model: Annotated[str, Field(min_length=1, max_length=160)]
    active: bool
    price_verified: bool
    health: RouteHealth
    quota: QuotaState
    last_failure_family: Annotated[str, Field(max_length=160)] = ""


class AgentRunEvidence(StrictModel):
    run_id: Annotated[str, Field(min_length=1, max_length=120)]
    status: RunState
    lease_active: bool = False
    iteration_count: Annotated[int, Field(ge=0, le=100000)] = 0
    max_iterations: Annotated[int, Field(ge=1, le=100000)] = 12
    next_action: Annotated[str, Field(max_length=200)] = ""
    active_blocker: Annotated[str, Field(max_length=240)] = ""
    recoverable: bool = False
    repeated_failure_count: Annotated[int, Field(ge=0, le=100000)] = 0
    provider_route_ready: bool = False


class SettlementEvidence(StrictModel):
    usage_id: Annotated[str, Field(min_length=1, max_length=160)]
    provider_cost_micros: Annotated[int, Field(ge=0, le=10**18)]
    charged_cost_micros: Annotated[int, Field(ge=0, le=10**18)]
    credit_delta_micros: Annotated[int, Field(ge=-(10**18), le=10**18)]
    settlement_status: Literal["pending", "settled", "reversed", "failed"]
    receipt_identity: Annotated[str, Field(max_length=200)] = ""


class BackupRestoreEvidence(StrictModel):
    asset: Annotated[str, Field(min_length=1, max_length=160)]
    backup_digest: RequiredSha256
    restored_digest: Sha256Value = ""
    restore_status: Literal["not-tested", "failed", "passed"]
    integrity_checks: Annotated[list[str], Field(max_length=32)] = []
    isolated_target: bool = False


class SloEvidence(StrictModel):
    service: Annotated[str, Field(min_length=1, max_length=160)]
    objective_ppm: Annotated[int, Field(ge=1, le=1_000_000)]
    total_events: Annotated[int, Field(ge=0, le=10**18)]
    failed_events: Annotated[int, Field(ge=0, le=10**18)]
    latency_objective_ms: Annotated[int, Field(ge=0, le=10**9)] = 0
    observed_p95_ms: Annotated[int, Field(ge=0, le=10**9)] = 0


class RuntimeConfigEvidence(StrictModel):
    installed_revision: OptionalExactSha = ""
    image_digest: Annotated[str, Field(max_length=200)] = ""
    container_healthy: bool = False
    mcp_protocol_ready: bool = False
    broker_ready: bool = False
    source: Annotated[str, Field(min_length=1, max_length=160)] = "supplied-evidence"


class ComplianceControl(StrictModel):
    control_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{1,79}$")]
    description: Annotated[str, Field(min_length=4, max_length=500)]
    required_evidence_kinds: Annotated[list[str], Field(min_length=1, max_length=32)]


@dataclass(frozen=True)
class InventoryResult:
    schemaVersion: str
    ok: bool
    status: str
    skillCount: int
    toolCount: int
    skills: list[dict[str, Any]]
    boundaries: dict[str, Any]
    mutationPerformed: bool
    secretValuesReturned: bool


@dataclass(frozen=True)
class RegistryResult:
    schemaVersion: str
    ok: bool
    status: str
    registrySnapshotSha256: str
    toolCount: int
    tools: list[dict[str, Any]]
    truncated: bool
    mutationPerformed: bool
    runtimeVerified: bool
    secretValuesReturned: bool


@dataclass(frozen=True)
class GenericResult:
    schemaVersion: str
    ok: bool
    status: str
    evidence: dict[str, Any]
    findings: list[dict[str, Any]]
    nextActions: list[str]
    evidenceSha256: str
    mutationPerformed: bool
    runtimeVerified: bool
    secretValuesReturned: bool
    truthNotice: str


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _bounded(value: Any, limit: int = 500) -> str:
    text = str(value or "").strip()
    if _SECRET_RE.search(text):
        return "[REDACTED_SECRET_SHAPED_VALUE]"
    return text[: max(1, int(limit))]


def _scrub(value: Any) -> Any:
    if isinstance(value, str):
        return _bounded(value, max(1, min(len(value), 4000)))
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, tuple):
        return [_scrub(item) for item in value]
    if isinstance(value, dict):
        return {
            _bounded(key, 160): _scrub(item)
            for key, item in value.items()
        }
    return value


def _annotation_payload(annotations: Any) -> dict[str, bool]:
    return {
        "readOnlyHint": bool(getattr(annotations, "readOnlyHint", False)),
        "destructiveHint": bool(getattr(annotations, "destructiveHint", False)),
        "idempotentHint": bool(getattr(annotations, "idempotentHint", False)),
        "openWorldHint": bool(getattr(annotations, "openWorldHint", False)),
    }


def _effect_from_annotations(annotations: dict[str, bool]) -> str:
    if annotations["readOnlyHint"]:
        return "read"
    if annotations["openWorldHint"] or annotations["destructiveHint"]:
        return "external-write"
    return "workspace-write"


def _capabilities_for(name: str, description: str) -> list[str]:
    capabilities: set[str] = set()
    for prefix, values in _PREFIX_CAPABILITIES:
        if name.startswith(prefix):
            capabilities.update(values)
    haystack = f"{name} {description}".casefold()
    token_map = {
        "repository": ("repository", "github", "pull request", "workspace", "codeowners"),
        "ci": ("workflow", "check", "ci", "build", "test"),
        "release": ("release", "deploy", "rollback", "artifact", "image"),
        "runtime": ("runtime", "health", "canary", "container", "runbook"),
        "container": ("docker", "container", "compose", "vps"),
        "database": ("postgres", "database", "sql", "vector"),
        "migration": ("migration", "schema", "table"),
        "llm": ("llm", "model", "provider", "litellm"),
        "agent": ("agent", "controller", "a2a", "swarm"),
        "billing": ("billing", "credit", "cost", "settlement", "payment"),
        "backup": ("backup", "restore", "recovery"),
        "observability": ("slo", "error budget", "trace", "log", "failure"),
        "configuration": ("configuration", "config", "environment", "drift"),
        "mcp": ("mcp", "tool registry", "tool contract", "capability"),
        "security": ("security", "auth", "secret", "policy", "permission"),
        "ownership": ("owner", "codeowners", "approval"),
        "compliance": ("compliance", "audit", "evidence", "control"),
        "learning": ("learning", "memory", "pattern", "knowledge"),
        "android": ("android", "gradle", "apk", "aab"),
        "document": ("document", "pdf", "tika", "gotenberg"),
        "deterministic": ("deterministic", "kappa", "replay", "invariant"),
        "maintenance": ("maintenance", "window", "patchmon", "reindex", "certificate"),
        "privacy": ("privacy", "retention", "pseudonym", "tenant"),
        "performance": ("performance", "latency", "capacity", "pool", "index"),
        "topology": ("topology", "network", "volume", "compose"),
        "queue": ("queue", "outbox", "dead letter", "retry"),
        "supply-chain": ("sbom", "provenance", "signature", "attestation", "vulnerability"),
        "authentication": ("authentication", "oauth", "pkce", "passkey", "session", "token"),
        "tenant": ("tenant", "isolation", "cross-tenant"),
    }
    for capability, markers in token_map.items():
        if any(marker in haystack for marker in markers):
            capabilities.add(capability)
    return sorted(capabilities)


def _tool_catalog(max_tools: int = 500, include_schemas: bool = True) -> tuple[list[dict[str, Any]], bool]:
    if _MCP is None:
        raise RuntimeError("Operational governance tools are not registered")
    raw_tools = list(_MCP._tool_manager.list_tools())
    raw_tools.sort(key=lambda item: str(getattr(item, "name", "")))
    truncated = len(raw_tools) > max_tools
    catalog: list[dict[str, Any]] = []
    for tool in raw_tools[:max_tools]:
        name = _bounded(getattr(tool, "name", ""), 160)
        description = _bounded(getattr(tool, "description", ""), 800)
        annotations = _annotation_payload(getattr(tool, "annotations", None))
        parameters = getattr(tool, "parameters", {}) if include_schemas else {}
        output_schema = getattr(tool, "output_schema", {}) if include_schemas else {}
        contract = {
            "name": name,
            "description": description,
            "capabilities": _capabilities_for(name, description),
            "effect": _effect_from_annotations(annotations),
            "annotations": annotations,
            "parameters": parameters,
            "outputSchema": output_schema,
        }
        contract["contractSha256"] = _sha256(contract)
        catalog.append(contract)
    return catalog, truncated


def _workspace_repo(workspace_id: str) -> Path:
    if _RUNTIME is None:
        raise RuntimeError("Operational governance runtime is not registered")
    return Path(_RUNTIME._repo(workspace_id))


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _generic_result(
    *,
    schema_version: str,
    ok: bool,
    status: str,
    evidence: dict[str, Any],
    findings: list[dict[str, Any]],
    next_actions: list[str],
    runtime_verified: bool,
    truth_notice: str,
) -> GenericResult:
    digest_payload = {
        "schemaVersion": schema_version,
        "status": status,
        "evidence": evidence,
        "findings": findings,
        "nextActions": next_actions,
    }
    return GenericResult(
        schemaVersion=schema_version,
        ok=ok,
        status=status,
        evidence=evidence,
        findings=findings,
        nextActions=next_actions,
        evidenceSha256=_sha256(digest_payload),
        mutationPerformed=False,
        runtimeVerified=runtime_verified,
        secretValuesReturned=False,
        truthNotice=truth_notice,
    )


def operational_skill_inventory() -> InventoryResult:
    """Use this when you need the installed routing, registry and operations skill map before selecting a Sovottt tool."""
    skills = [
        {
            "name": name,
            "priority": profile["priority"],
            "purpose": profile["purpose"],
            "tools": list(profile["tools"]),
            "mutates": False,
        }
        for name, profile in sorted(_SKILL_PROFILES.items())
    ]
    return InventoryResult(
        schemaVersion="sovereign.operational-skill-inventory.v1",
        ok=True,
        status="OPERATIONAL_SKILL_SUITE_READY",
        skillCount=len(skills),
        toolCount=len({tool for profile in _SKILL_PROFILES.values() for tool in profile["tools"]}),
        skills=skills,
        boundaries={
            "naturalLanguageInterpretation": "model_only",
            "runtimeRoutingInput": "structured_capabilities",
            "genericShellAvailable": False,
            "hostMutationPerformed": False,
            "databaseRowDataReturned": False,
            "workspaceChangesEndAtDraftPr": True,
            "autoMerge": False,
            "ownerProtectedValuesAccepted": False,
        },
        mutationPerformed=False,
        secretValuesReturned=False,
    )


def mcp_tool_contract_registry(
    include_schemas: bool = False,
    max_tools: Annotated[int, Field(ge=1, le=1000)] = 500,
) -> RegistryResult:
    """Use this when the active FastMCP tool names, descriptions, annotations, capabilities and contract hashes must be inventoried."""
    catalog, truncated = _tool_catalog(max_tools=max_tools, include_schemas=include_schemas)
    snapshot_payload = [
        {
            "name": item["name"],
            "description": item["description"],
            "capabilities": item["capabilities"],
            "effect": item["effect"],
            "annotations": item["annotations"],
            "parameters": item["parameters"],
            "outputSchema": item["outputSchema"],
        }
        for item in catalog
    ]
    return RegistryResult(
        schemaVersion="sovereign.mcp-tool-contract-registry.v1",
        ok=not truncated,
        status="MCP_TOOL_REGISTRY_READY" if not truncated else "MCP_TOOL_REGISTRY_TRUNCATED",
        registrySnapshotSha256=_sha256(snapshot_payload),
        toolCount=len(catalog),
        tools=catalog,
        truncated=truncated,
        mutationPerformed=False,
        runtimeVerified=True,
        secretValuesReturned=False,
    )


def tool_recommend_for_mission(
    mission_summary: BoundedText,
    required_capabilities: Annotated[list[Capability], Field(min_length=1, max_length=12)],
    allowed_effects: Annotated[list[EffectClass], Field(min_length=1, max_length=3)] = ["read"],
    required_evidence: Annotated[list[str], Field(max_length=12)] = [],
    excluded_tools: Annotated[list[str], Field(max_length=64)] = [],
    max_tools: Annotated[int, Field(ge=1, le=20)] = 8,
) -> GenericResult:
    """Use this when the model has mapped a user mission to structured capabilities and needs the smallest eligible Sovottt tool set."""
    catalog, truncated = _tool_catalog(max_tools=1000, include_schemas=False)
    required = set(required_capabilities)
    allowed = set(allowed_effects)
    excluded = set(excluded_tools)
    evidence_tokens = set(_TOKEN_RE.findall(" ".join(required_evidence).casefold()))
    scored: list[dict[str, Any]] = []
    for item in catalog:
        if item["name"] in excluded or item["name"] == "tool_recommend_for_mission":
            continue
        if item["effect"] not in allowed:
            continue
        capabilities = set(item["capabilities"])
        matched = sorted(required & capabilities)
        if not matched:
            continue
        prefix_capabilities = {
            capability
            for prefix, values in _PREFIX_CAPABILITIES
            if item["name"].startswith(prefix)
            for capability in values
        }
        prefix_matches = sorted(required & prefix_capabilities)
        description_tokens = set(_TOKEN_RE.findall(f"{item['name']} {item['description']}".casefold()))
        evidence_matches = sorted(evidence_tokens & description_tokens)
        score = len(matched) * 100 + len(prefix_matches) * 30 + len(evidence_matches) * 10
        if item["effect"] == "read":
            score += 8
        if item["annotations"]["idempotentHint"]:
            score += 3
        if item["annotations"]["destructiveHint"]:
            score -= 50
        scored.append(
            {
                "name": item["name"],
                "score": score,
                "matchedCapabilities": matched,
                "prefixMatchedCapabilities": prefix_matches,
                "matchedEvidenceTerms": evidence_matches,
                "effect": item["effect"],
                "contractSha256": item["contractSha256"],
                "reason": f"matches {', '.join(matched)} within allowed effect {item['effect']}",
            }
        )
    scored.sort(key=lambda item: (-int(item["score"]), str(item["name"])))
    selected: list[dict[str, Any]] = []
    covered: set[str] = set()
    for candidate in scored:
        new_coverage = set(candidate["matchedCapabilities"]) - covered
        if new_coverage or len(selected) < min(2, max_tools):
            selected.append(candidate)
            covered.update(candidate["matchedCapabilities"])
        if len(selected) >= max_tools or covered >= required:
            break
    missing = sorted(required - covered)
    findings = []
    if missing:
        findings.append(
            {
                "severity": "P1",
                "family": "TOOL_CAPABILITY_COVERAGE_GAP",
                "status": "RUNTIME_REGISTRY_EVIDENCE",
                "missingCapabilities": missing,
            }
        )
    if truncated:
        findings.append(
            {
                "severity": "P1",
                "family": "MCP_TOOL_REGISTRY_TRUNCATED",
                "status": "RUNTIME_REGISTRY_EVIDENCE",
            }
        )
    evidence = {
        "missionSummary": _bounded(mission_summary, 800),
        "requiredCapabilities": sorted(required),
        "allowedEffects": sorted(allowed),
        "selectedTools": selected,
        "coveredCapabilities": sorted(covered),
        "missingCapabilities": missing,
        "registryToolCount": len(catalog),
    }
    return _generic_result(
        schema_version="sovereign.tool-capability-routing.v1",
        ok=not missing and not truncated,
        status="TOOL_ROUTE_READY" if not missing and not truncated else "TOOL_ROUTE_INCOMPLETE",
        evidence=evidence,
        findings=findings,
        next_actions=[
            "load full contracts only for selected tool names",
            "verify exact revision and owner policy before any mutation",
            "record selected tool identities and resulting evidence",
        ],
        runtime_verified=True,
        truth_notice="The model interprets language and supplies structured capabilities. The runtime ranks only currently registered tools and never executes a recommendation automatically.",
    )


def mcp_registry_snapshot_verify(
    expected_snapshot_sha256: Sha256Value = "",
    expected_tool_names: Annotated[list[str], Field(max_length=1000)] = [],
    max_tools: Annotated[int, Field(ge=1, le=1000)] = 500,
) -> GenericResult:
    """Use this when the live MCP registry must be compared with one approved snapshot hash or expected tool-name set."""
    registry = mcp_tool_contract_registry(include_schemas=True, max_tools=max_tools)
    actual_names = sorted(item["name"] for item in registry.tools)
    expected_names = sorted(set(expected_tool_names))
    missing = sorted(set(expected_names) - set(actual_names))
    unexpected = sorted(set(actual_names) - set(expected_names)) if expected_names else []
    hash_mismatch = bool(expected_snapshot_sha256 and expected_snapshot_sha256 != registry.registrySnapshotSha256)
    findings: list[dict[str, Any]] = []
    if hash_mismatch:
        findings.append(
            {
                "severity": "P0",
                "family": "MCP_REGISTRY_SNAPSHOT_MISMATCH",
                "expected": expected_snapshot_sha256,
                "actual": registry.registrySnapshotSha256,
            }
        )
    if missing:
        findings.append(
            {
                "severity": "P0",
                "family": "MCP_REGISTERED_TOOL_MISSING",
                "tools": missing,
            }
        )
    if unexpected:
        findings.append(
            {
                "severity": "P1",
                "family": "MCP_REGISTERED_TOOL_UNEXPECTED",
                "tools": unexpected[:100],
                "truncated": len(unexpected) > 100,
            }
        )
    if registry.truncated:
        findings.append({"severity": "P0", "family": "MCP_TOOL_REGISTRY_TRUNCATED"})
    ok = not findings
    return _generic_result(
        schema_version="sovereign.mcp-registry-snapshot-verification.v1",
        ok=ok,
        status="MCP_REGISTRY_SNAPSHOT_MATCH" if ok else "MCP_REGISTRY_SNAPSHOT_DRIFT",
        evidence={
            "actualSnapshotSha256": registry.registrySnapshotSha256,
            "expectedSnapshotSha256": expected_snapshot_sha256 or None,
            "actualToolCount": registry.toolCount,
            "expectedToolCount": len(expected_names) if expected_names else None,
            "missingTools": missing,
            "unexpectedTools": unexpected,
        },
        findings=findings,
        next_actions=[
            "review the live tool diff before refreshing the ChatGPT app snapshot",
            "publish only backward-compatible or owner-approved contract changes",
            "run MCP initialize and tool-list protocol canaries against the immutable image",
        ],
        runtime_verified=True,
        truth_notice="This verifies the live FastMCP registry inside the running process. It cannot read ChatGPT's frozen workspace snapshot; its approved hash or names must be supplied for comparison.",
    )


def evidence_graph_build(
    revision: ExactSha,
    evidence_records: Annotated[list[EvidenceRecord], Field(min_length=1, max_length=200)],
    required_kinds: Annotated[list[str], Field(min_length=1, max_length=32)],
) -> GenericResult:
    """Use this when repository, CI, artifact, deployment and runtime evidence must be bound to one exact revision."""
    records = [_scrub(record.model_dump(mode="json")) for record in evidence_records]
    identities = {record["identity"] for record in records}
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    findings: list[dict[str, Any]] = []
    for record in records:
        nodes.append(record)
        for related in record["related_ids"]:
            if related in identities:
                edges.append({"from": record["identity"], "to": related, "type": "declared_relation"})
            else:
                findings.append(
                    {
                        "severity": "P1",
                        "family": "EVIDENCE_RELATION_TARGET_MISSING",
                        "identity": record["identity"],
                        "relatedIdentity": related,
                    }
                )
        if record["revision"] and record["revision"] != revision:
            findings.append(
                {
                    "severity": "P0",
                    "family": "EVIDENCE_REVISION_MISMATCH",
                    "identity": record["identity"],
                    "expectedRevision": revision,
                    "actualRevision": record["revision"],
                }
            )
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_kind.setdefault(record["kind"], []).append(record)
    missing_kinds = sorted(set(required_kinds) - set(by_kind))
    for kind in missing_kinds:
        findings.append({"severity": "P0", "family": "REQUIRED_EVIDENCE_KIND_MISSING", "kind": kind})
    for kind in sorted(set(required_kinds) & set(by_kind)):
        if not any(item["status"] == "success" and item["revision"] == revision for item in by_kind[kind]):
            findings.append(
                {
                    "severity": "P0",
                    "family": "REQUIRED_EVIDENCE_KIND_NOT_SUCCESSFUL_FOR_REVISION",
                    "kind": kind,
                }
            )
    release_ready = not any(item["severity"] == "P0" for item in findings)
    evidence = {
        "revision": revision,
        "nodes": nodes,
        "edges": edges,
        "requiredKinds": sorted(set(required_kinds)),
        "missingKinds": missing_kinds,
        "releaseReady": release_ready,
        "graphSha256": _sha256({"revision": revision, "nodes": nodes, "edges": edges}),
    }
    return _generic_result(
        schema_version="sovereign.evidence-graph.v1",
        ok=release_ready,
        status="EVIDENCE_GRAPH_COMPLETE" if release_ready else "EVIDENCE_GRAPH_BLOCKED",
        evidence=evidence,
        findings=findings,
        next_actions=[
            "obtain missing evidence from its authoritative producer",
            "reject evidence bound to a different revision",
            "permit release claims only when every required kind is successful for the exact revision",
        ],
        runtime_verified=False,
        truth_notice="The graph validates supplied evidence identities, statuses, relations and revision binding. It does not independently execute CI, deployment or runtime canaries.",
    )


def _normalize_schema_expression(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _load_historical_schema_ownership(
    repo: Path,
) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Load only the fixed repository-owned manifest path and reject malformed contracts."""
    repo_root = repo.resolve()
    manifest_path = (repo_root / _HISTORICAL_SCHEMA_OWNERSHIP_PATH).resolve()
    findings: list[dict[str, Any]] = []
    try:
        manifest_path.relative_to(repo_root)
    except ValueError:
        return None, {}, [
            {
                "severity": "P0",
                "family": "DB_HISTORICAL_OWNERSHIP_MANIFEST_PATH_BLOCKED",
                "path": str(_HISTORICAL_SCHEMA_OWNERSHIP_PATH),
            }
        ]
    if not manifest_path.is_file():
        return None, {}, []
    if manifest_path.stat().st_size > 1_000_000:
        return None, {}, [
            {
                "severity": "P0",
                "family": "DB_HISTORICAL_OWNERSHIP_MANIFEST_INVALID",
                "reason": "manifest_too_large",
            }
        ]
    try:
        payload = json.loads(manifest_path.read_text("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, {}, [
            {
                "severity": "P0",
                "family": "DB_HISTORICAL_OWNERSHIP_MANIFEST_INVALID",
                "reason": type(exc).__name__,
            }
        ]
    if not isinstance(payload, dict) or payload.get("schemaVersion") != _HISTORICAL_SCHEMA_OWNERSHIP_VERSION:
        return payload if isinstance(payload, dict) else None, {}, [
            {
                "severity": "P0",
                "family": "DB_HISTORICAL_OWNERSHIP_MANIFEST_SCHEMA_UNSUPPORTED",
                "expected": _HISTORICAL_SCHEMA_OWNERSHIP_VERSION,
                "actual": payload.get("schemaVersion") if isinstance(payload, dict) else None,
            }
        ]
    raw_tables = payload.get("tables")
    if not isinstance(raw_tables, list):
        return payload, {}, [
            {
                "severity": "P0",
                "family": "DB_HISTORICAL_OWNERSHIP_MANIFEST_INVALID",
                "reason": "tables_must_be_an_array",
            }
        ]
    entries: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(raw_tables):
        if not isinstance(raw, dict):
            findings.append(
                {
                    "severity": "P0",
                    "family": "DB_HISTORICAL_OWNERSHIP_MANIFEST_INVALID",
                    "entry": index,
                    "reason": "table_entry_must_be_an_object",
                }
            )
            continue
        table = str(raw.get("table") or "").strip().lower()
        if not _TABLE_IDENTITY_RE.fullmatch(table):
            findings.append(
                {
                    "severity": "P0",
                    "family": "DB_HISTORICAL_OWNERSHIP_MANIFEST_INVALID",
                    "entry": index,
                    "reason": "invalid_table_identity",
                }
            )
            continue
        if table in entries:
            findings.append(
                {
                    "severity": "P0",
                    "family": "DB_HISTORICAL_OWNERSHIP_MANIFEST_INVALID",
                    "table": table,
                    "reason": "duplicate_table_identity",
                }
            )
            continue
        if raw.get("allowAutomaticCreate") is not False:
            findings.append(
                {
                    "severity": "P0",
                    "family": "DB_HISTORICAL_OWNERSHIP_AUTOMATIC_CREATE_FORBIDDEN",
                    "table": table,
                }
            )
            continue
        if not all(isinstance(raw.get(key), list) for key in ("requiredColumns", "requiredConstraints", "requiredIndexes")):
            findings.append(
                {
                    "severity": "P0",
                    "family": "DB_HISTORICAL_OWNERSHIP_MANIFEST_INVALID",
                    "table": table,
                    "reason": "required_contract_arrays_missing",
                }
            )
            continue
        entries[table] = raw
    return payload, entries, findings


def _historical_contract_mismatches(expected: dict[str, Any], actual: dict[str, Any]) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    actual_columns = {
        str(item.get("name") or "").lower(): item
        for item in actual.get("columns", [])
        if isinstance(item, dict) and item.get("name")
    }
    for required in expected.get("requiredColumns", []):
        if not isinstance(required, dict) or not required.get("name"):
            mismatches.append({"kind": "column", "reason": "invalid_manifest_entry"})
            continue
        name = str(required["name"]).lower()
        observed = actual_columns.get(name)
        if observed is None:
            mismatches.append({"kind": "column", "name": name, "reason": "missing"})
            continue
        if _normalize_schema_expression(observed.get("dataType")) != _normalize_schema_expression(required.get("dataType")):
            mismatches.append(
                {
                    "kind": "column",
                    "name": name,
                    "reason": "data_type_mismatch",
                    "expected": required.get("dataType"),
                    "actual": observed.get("dataType"),
                }
            )
        if bool(observed.get("notNull")) != bool(required.get("notNull")):
            mismatches.append(
                {
                    "kind": "column",
                    "name": name,
                    "reason": "nullability_mismatch",
                    "expected": bool(required.get("notNull")),
                    "actual": bool(observed.get("notNull")),
                }
            )
        if "defaultExpression" in required and _normalize_schema_expression(observed.get("defaultExpression")) != _normalize_schema_expression(required.get("defaultExpression")):
            mismatches.append(
                {
                    "kind": "column",
                    "name": name,
                    "reason": "default_mismatch",
                    "expected": required.get("defaultExpression"),
                    "actual": observed.get("defaultExpression"),
                }
            )

    actual_constraints = {
        str(item.get("name") or "").lower(): item
        for item in actual.get("constraints", [])
        if isinstance(item, dict) and item.get("name")
    }
    for required in expected.get("requiredConstraints", []):
        if not isinstance(required, dict) or not required.get("name"):
            mismatches.append({"kind": "constraint", "reason": "invalid_manifest_entry"})
            continue
        name = str(required["name"]).lower()
        observed = actual_constraints.get(name)
        if observed is None:
            mismatches.append({"kind": "constraint", "name": name, "reason": "missing"})
            continue
        if _normalize_schema_expression(observed.get("type")) != _normalize_schema_expression(required.get("type")):
            mismatches.append(
                {
                    "kind": "constraint",
                    "name": name,
                    "reason": "type_mismatch",
                    "expected": required.get("type"),
                    "actual": observed.get("type"),
                }
            )
        if _normalize_schema_expression(observed.get("definition")) != _normalize_schema_expression(required.get("definition")):
            mismatches.append(
                {
                    "kind": "constraint",
                    "name": name,
                    "reason": "definition_mismatch",
                    "expected": required.get("definition"),
                    "actual": observed.get("definition"),
                }
            )

    actual_indexes = {
        str(item.get("name") or "").lower(): item
        for item in actual.get("indexes", [])
        if isinstance(item, dict) and item.get("name")
    }
    for required in expected.get("requiredIndexes", []):
        if not isinstance(required, dict) or not required.get("name"):
            mismatches.append({"kind": "index", "reason": "invalid_manifest_entry"})
            continue
        name = str(required["name"]).lower()
        observed = actual_indexes.get(name)
        if observed is None:
            mismatches.append({"kind": "index", "name": name, "reason": "missing"})
            continue
        for key in ("isUnique", "isPrimary"):
            if bool(observed.get(key)) != bool(required.get(key)):
                mismatches.append(
                    {
                        "kind": "index",
                        "name": name,
                        "reason": f"{key}_mismatch",
                        "expected": bool(required.get(key)),
                        "actual": bool(observed.get(key)),
                    }
                )
        if _normalize_schema_expression(observed.get("definition")) != _normalize_schema_expression(required.get("definition")):
            mismatches.append(
                {
                    "kind": "index",
                    "name": name,
                    "reason": "definition_mismatch",
                    "expected": required.get("definition"),
                    "actual": observed.get("definition"),
                }
            )
    return mismatches


def schema_migration_reconcile(
    workspace_id: WorkspaceId,
    migration_paths: Annotated[list[str], Field(max_length=16)] = ["backend/migrations", "scripts/sovereign-backend/migrations"],
) -> GenericResult:
    """Use this when migration and versioned historical PostgreSQL ownership must be reconciled without reading rows."""
    repo = _workspace_repo(workspace_id)
    static_tables: dict[str, list[str]] = {}
    migration_hashes: dict[str, str] = {}
    scanned_files = 0
    for relative in migration_paths:
        root = (repo / relative).resolve()
        try:
            root.relative_to(repo.resolve())
        except ValueError:
            continue
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.sql"))[:1000]:
            if not path.is_file() or path.stat().st_size > 2_000_000:
                continue
            text = path.read_text("utf-8", errors="replace")
            scanned_files += 1
            relative_path = str(path.relative_to(repo))
            migration_hashes[relative_path] = hashlib.sha256(text.encode("utf-8")).hexdigest()
            ddl_text = _strip_sql_comments(text)
            for match in _CREATE_TABLE_RE.finditer(ddl_text):
                schema = (match.group("schema") or "public").lower()
                table = match.group("table").lower()
                identity = f"{schema}.{table}"
                static_tables.setdefault(identity, []).append(relative_path)
    if _DATABASE is None:
        raise RuntimeError("Database runtime is not registered")
    live = _DATABASE.schema_inventory()
    raw_live_tables = live.get("tables") if isinstance(live, dict) else []
    raw_live_tables = raw_live_tables if isinstance(raw_live_tables, list) else []
    live_tables = {
        f"{str(item.get('table_schema') or 'public').lower()}.{str(item.get('table_name') or '').lower()}"
        for item in raw_live_tables
        if isinstance(item, dict) and item.get("table_name")
    }
    static_names = set(static_tables)
    migration_owned = sorted(static_names & live_tables)
    missing_live = sorted(static_names - live_tables)

    manifest, historical_entries, manifest_findings = _load_historical_schema_ownership(repo)
    findings: list[dict[str, Any]] = list(manifest_findings)
    historical_owned: list[str] = []
    historical_mismatches: list[dict[str, Any]] = []
    historical_missing: list[str] = []
    historical_inventory: dict[str, Any] = {}
    if historical_entries and not manifest_findings:
        overlap = sorted(set(historical_entries) & static_names)
        for table in overlap:
            findings.append(
                {
                    "severity": "P0",
                    "family": "DB_HISTORICAL_OWNERSHIP_CONFLICTS_WITH_MIGRATION_OWNER",
                    "table": table,
                }
            )
        try:
            historical_inventory = _DATABASE.schema_contract_inventory(sorted(historical_entries))
        except Exception as exc:
            historical_inventory = {
                "ok": False,
                "status": "POSTGRES_SCHEMA_CONTRACT_INVENTORY_UNAVAILABLE",
                "errorType": type(exc).__name__,
                "rowDataReturned": False,
            }
            findings.append(
                {
                    "severity": "P0",
                    "family": "DB_HISTORICAL_OWNERSHIP_INVENTORY_UNAVAILABLE",
                    "errorType": type(exc).__name__,
                }
            )
        if historical_inventory.get("rowDataReturned") is not False:
            findings.append(
                {
                    "severity": "P0",
                    "family": "DB_HISTORICAL_OWNERSHIP_ROW_DATA_BOUNDARY_BROKEN",
                }
            )
        actual_by_table = {
            str(item.get("table") or "").lower(): item
            for item in historical_inventory.get("tables", [])
            if isinstance(item, dict) and item.get("table")
        }
        for table, expected in sorted(historical_entries.items()):
            if table not in live_tables or table not in actual_by_table:
                historical_missing.append(table)
                findings.append(
                    {
                        "severity": "P0",
                        "family": "DB_HISTORICAL_OWNERSHIP_TABLE_MISSING",
                        "table": table,
                    }
                )
                continue
            mismatch_items = _historical_contract_mismatches(expected, actual_by_table[table])
            if mismatch_items:
                historical_mismatches.append({"table": table, "mismatches": mismatch_items})
                findings.append(
                    {
                        "severity": "P0",
                        "family": "DB_HISTORICAL_OWNERSHIP_SCHEMA_MISMATCH",
                        "table": table,
                        "mismatchCount": len(mismatch_items),
                    }
                )
                continue
            if table not in overlap:
                historical_owned.append(table)

    unmapped_live = sorted(live_tables - static_names - set(historical_owned))
    duplicate_owners = [
        {
            "table": name,
            "migrationFiles": sorted(set(paths)),
            "contentSha256": sorted({migration_hashes[path] for path in set(paths)}),
        }
        for name, paths in sorted(static_tables.items())
        if len({migration_hashes[path] for path in set(paths)}) > 1
    ]
    byte_equal_mirrors = [
        {"table": name, "migrationFiles": sorted(set(paths)), "byteEqual": True}
        for name, paths in sorted(static_tables.items())
        if len(set(paths)) > 1
        and len({migration_hashes[path] for path in set(paths)}) == 1
    ]
    findings.extend(
        {"severity": "P0", "family": "DB_DRIFT_MISSING_LIVE_TABLE", "table": name}
        for name in missing_live
    )
    findings.extend(
        {"severity": "P1", "family": "DB_DRIFT_UNMAPPED_LIVE_TABLE", "table": name}
        for name in unmapped_live
    )
    findings.extend(
        {"severity": "P1", "family": "MIGRATION_TABLE_MULTIPLE_OWNERS", **item}
        for item in duplicate_owners
    )
    ok = not findings
    manifest_path = str(_HISTORICAL_SCHEMA_OWNERSHIP_PATH)
    return _generic_result(
        schema_version="sovereign.schema-migration-reconciliation.v1",
        ok=ok,
        status="SCHEMA_OWNERSHIP_RECONCILED" if ok else "SCHEMA_OWNERSHIP_DRIFT",
        evidence={
            "workspaceRevision": _git(repo, "rev-parse", "HEAD"),
            "migrationFilesScanned": scanned_files,
            "migrationDefinedTableCount": len(static_names),
            "liveTableCount": len(live_tables),
            "migrationOwnedTables": migration_owned,
            "historicallyOwnedTables": sorted(historical_owned),
            "missingLiveTables": missing_live,
            "historicalOwnershipMissingTables": historical_missing,
            "unmappedLiveTables": unmapped_live,
            "historicalOwnershipMismatches": historical_mismatches,
            "historicalOwnershipManifestPath": manifest_path,
            "historicalOwnershipManifestLoaded": manifest is not None,
            "historicalOwnershipManifestSha256": _sha256(manifest) if manifest is not None else None,
            "historicalOwnershipInventoryStatus": historical_inventory.get("status") if historical_inventory else None,
            "multipleOwners": duplicate_owners,
            "byteEqualMigrationMirrors": byte_equal_mirrors,
            "liveSchemaStatus": live.get("status") if isinstance(live, dict) else "UNKNOWN",
            "rowDataReturned": False,
            "automaticDatabaseMutationPerformed": False,
        },
        findings=findings,
        next_actions=[
            "manually recover a missing or structurally incompatible historical table; never auto-create it",
            "normalize each remaining multiple migration owner in a separate canonical-owner change",
            "repeat reconciliation against the exact installed MCP revision after merge",
        ],
        runtime_verified=True,
        truth_notice="Live names and catalog metadata are read in read-only mode. Historical ownership is accepted only from the fixed repository manifest when the full required structure matches; no rows or migrations are read or mutated.",
    )


def llm_route_reliability_assess(
    routes: Annotated[list[RouteEvidence], Field(min_length=1, max_length=64)],
    required_aliases: Annotated[list[str], Field(min_length=1, max_length=16)],
) -> GenericResult:
    """Use this when LiteLLM aliases need a fail-closed readiness decision from provider inventory, price, health and quota evidence."""
    provider_inventory: dict[str, Any] = {}
    broker_status: dict[str, Any] = {}
    if _BROKER is not None:
        try:
            provider_inventory = _BROKER.call("litellm_provider_model_inventory", {}, timeout=90)
        except Exception as exc:
            provider_inventory = {"ok": False, "status": "PROVIDER_INVENTORY_UNAVAILABLE", "errorType": type(exc).__name__}
        try:
            broker_status = _BROKER.status()
        except Exception as exc:
            broker_status = {"ok": False, "status": "BROKER_STATUS_UNAVAILABLE", "errorType": type(exc).__name__}
    available_models = set(provider_inventory.get("modelIds") or []) if isinstance(provider_inventory, dict) else set()
    route_payload = [_scrub(route.model_dump(mode="json")) for route in routes]
    by_alias = {route["alias"]: route for route in route_payload}
    findings: list[dict[str, Any]] = []
    for alias in required_aliases:
        route = by_alias.get(alias)
        if route is None:
            findings.append({"severity": "P0", "family": "LLM_REQUIRED_ALIAS_MISSING", "alias": alias})
            continue
        if not route["active"]:
            findings.append({"severity": "P0", "family": "LLM_ALIAS_INACTIVE", "alias": alias})
        if not route["price_verified"]:
            findings.append({"severity": "P0", "family": "LLM_ROUTE_PRICE_UNVERIFIED", "alias": alias})
        if route["health"] != "healthy":
            findings.append(
                {"severity": "P0", "family": "LLM_ROUTE_NOT_HEALTHY", "alias": alias, "health": route["health"]}
            )
        if route["quota"] in {"exhausted", "unknown"}:
            findings.append(
                {"severity": "P0", "family": "LLM_ROUTE_QUOTA_NOT_READY", "alias": alias, "quota": route["quota"]}
            )
        if available_models and route["provider_model"] not in available_models:
            findings.append(
                {
                    "severity": "P0",
                    "family": "LLM_PROVIDER_MODEL_NOT_IN_CURRENT_INVENTORY",
                    "alias": alias,
                    "providerModel": route["provider_model"],
                }
            )
    if broker_status.get("status") != "BROKER_READY":
        findings.append(
            {"severity": "P0", "family": "MCP_CONTROL_PLANE_NOT_READY", "status": broker_status.get("status")}
        )
    ok = not findings
    return _generic_result(
        schema_version="sovereign.llm-route-reliability.v1",
        ok=ok,
        status="LLM_ROUTES_READY" if ok else "LLM_ROUTES_BLOCKED",
        evidence={
            "requiredAliases": list(required_aliases),
            "routes": route_payload,
            "providerInventoryStatus": provider_inventory.get("status"),
            "providerInventorySha256": provider_inventory.get("inventorySha256"),
            "providerModelCount": provider_inventory.get("modelCount"),
            "brokerStatus": broker_status.get("status"),
            "secretValuesReturned": False,
        },
        findings=findings,
        next_actions=[
            "activate only aliases whose provider model exists in the current inventory",
            "require verified pricing and a successful health canary before agent execution",
            "use bounded provider backoff when quota or rate-limit evidence is present",
        ],
        runtime_verified=bool(provider_inventory.get("ok") and broker_status.get("status") == "BROKER_READY"),
        truth_notice="Provider model inventory and broker state are read live. Alias activation, pricing, health and quota values are supplied structured evidence and are not mutated here.",
    )


def agent_run_liveness_assess(run: AgentRunEvidence) -> GenericResult:
    """Use this when one persisted agent run needs a deterministic resume, owner-wait, provider-recovery or terminal decision."""
    payload = _scrub(run.model_dump(mode="json"))
    findings: list[dict[str, Any]] = []
    decision = "NO_ACTION"
    if run.status == "WAITING_FOR_OWNER":
        decision = "WAIT_FOR_OWNER"
    elif run.status == "BLOCKED":
        if run.active_blocker and "OWNER" in run.active_blocker.upper():
            decision = "WAIT_FOR_OWNER"
        elif not run.provider_route_ready:
            decision = "RESTORE_PROVIDER_ROUTE_BEFORE_RESUME"
        elif run.iteration_count >= run.max_iterations:
            decision = "STOP_MAX_ITERATIONS_REACHED"
        else:
            decision = "RESUME_ONCE_WITH_NEW_EVIDENCE"
    elif run.status == "FAILED_RECOVERABLE" or run.recoverable:
        decision = "RETRY_WITH_BOUNDED_BACKOFF" if run.provider_route_ready else "RESTORE_PROVIDER_ROUTE_BEFORE_RETRY"
    elif run.status in {"FAILED_FINAL", "SUCCEEDED", "CANCELLED"}:
        decision = "TERMINAL_NO_RESUME"
    elif run.status == "RUNNING":
        decision = "OBSERVE_ACTIVE_LEASE" if run.lease_active else "RECOVER_EXPIRED_OR_MISSING_LEASE"
    elif run.status == "RECEIVED":
        decision = "CLAIM_FOR_FIRST_BOUNDED_ATTEMPT"
    else:
        decision = "REQUIRE_FRESH_CONTROLLER_EVIDENCE"
    if run.iteration_count > run.max_iterations:
        findings.append({"severity": "P0", "family": "AGENT_RUN_ITERATION_INVARIANT_BROKEN"})
    if run.repeated_failure_count >= 3:
        findings.append(
            {
                "severity": "P1",
                "family": "AGENT_RUN_REPEATED_FAILURE_FAMILY",
                "count": run.repeated_failure_count,
            }
        )
    if run.status == "RUNNING" and not run.lease_active:
        findings.append({"severity": "P0", "family": "AGENT_RUN_RUNNING_WITHOUT_ACTIVE_LEASE"})
    ok = decision not in {"STOP_MAX_ITERATIONS_REACHED", "REQUIRE_FRESH_CONTROLLER_EVIDENCE"} and not any(
        item["severity"] == "P0" for item in findings
    )
    return _generic_result(
        schema_version="sovereign.agent-run-liveness.v1",
        ok=ok,
        status="AGENT_RUN_LIVENESS_READY" if ok else "AGENT_RUN_LIVENESS_BLOCKED",
        evidence={"run": payload, "decision": decision},
        findings=findings,
        next_actions=[decision, "append fresh external evidence idempotently", "re-read persisted run state after one bounded action"],
        runtime_verified=False,
        truth_notice="This evaluates supplied persisted run metadata. It does not change run state, claim a lease or call a provider.",
    )


def semantic_intent_boundary_audit(
    workspace_id: WorkspaceId,
    roots: Annotated[list[str], Field(max_length=16)] = ["backend", "scripts/sovereign-backend", "src", "tools/sovereign-chatgpt-mcp"],
    max_findings: Annotated[int, Field(ge=1, le=500)] = 200,
) -> GenericResult:
    """Use this when possible free-language interpretation outside the online LLM boundary must be identified for exact human review."""
    repo = _workspace_repo(workspace_id)
    findings: list[dict[str, Any]] = []
    scanned = 0
    for relative in roots:
        root = (repo / relative).resolve()
        try:
            root.relative_to(repo.resolve())
        except ValueError:
            continue
        if not root.exists():
            continue
        paths = [root] if root.is_file() else sorted(root.rglob("*"))
        for path in paths:
            if len(findings) >= max_findings:
                break
            if not path.is_file() or path.suffix.lower() not in {".py", ".ts", ".tsx", ".js", ".mjs"}:
                continue
            rel = str(path.relative_to(repo))
            lowered = rel.casefold()
            if any(marker in lowered for marker in ("/tests/", ".test.", ".spec.", "/docs/", "node_modules")):
                continue
            if path.stat().st_size > 2_000_000:
                continue
            scanned += 1
            lines = path.read_text("utf-8", errors="replace").splitlines()
            for line_number, line in enumerate(lines, 1):
                for family, pattern in _KEYWORD_INTENT_PATTERNS:
                    if pattern.search(line):
                        findings.append(
                            {
                                "severity": "P1",
                                "family": "SEMANTIC_INTENT_BOUNDARY_CANDIDATE",
                                "patternFamily": family,
                                "path": rel,
                                "line": line_number,
                                "status": "CANDIDATE_REQUIRES_REVIEW",
                                "truthNotice": "Structured enum handling and explicitly marked offline fallback may be valid.",
                            }
                        )
                        break
                if len(findings) >= max_findings:
                    break
    return _generic_result(
        schema_version="sovereign.semantic-intent-boundary-audit.v1",
        ok=not findings,
        status="SEMANTIC_INTENT_BOUNDARY_CLEAR" if not findings else "SEMANTIC_INTENT_BOUNDARY_REVIEW_REQUIRED",
        evidence={
            "workspaceRevision": _git(repo, "rev-parse", "HEAD"),
            "filesScanned": scanned,
            "findingCount": len(findings),
            "truncated": len(findings) >= max_findings,
        },
        findings=findings,
        next_actions=[
            "classify each candidate as structured enum, offline fallback or forbidden language interpretation",
            "move online natural-language understanding to the LLM boundary",
            "retain deterministic runtime checks only for action, policy and state contracts",
        ],
        runtime_verified=False,
        truth_notice="Regex findings are static candidates, not proof of an active violation. Active callers and runtime paths require separate evidence.",
    )


def cost_credit_settlement_reconcile(
    records: Annotated[list[SettlementEvidence], Field(min_length=1, max_length=500)],
    allowed_markup_ppm: Annotated[int, Field(ge=0, le=10_000_000)] = 0,
) -> GenericResult:
    """Use this when provider cost, charged amount, credit ledger delta and settlement identity need integer-only reconciliation."""
    payload = [_scrub(record.model_dump(mode="json")) for record in records]
    findings: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    total_provider = 0
    total_charged = 0
    total_credit_delta = 0
    for record in payload:
        usage_id = record["usage_id"]
        if usage_id in seen_ids:
            findings.append({"severity": "P0", "family": "DUPLICATE_USAGE_SETTLEMENT", "usageId": usage_id})
        seen_ids.add(usage_id)
        provider = int(record["provider_cost_micros"])
        charged = int(record["charged_cost_micros"])
        expected_max = provider + (provider * allowed_markup_ppm // 1_000_000)
        if charged > expected_max:
            findings.append(
                {
                    "severity": "P0",
                    "family": "CHARGED_COST_EXCEEDS_ALLOWED_MARKUP",
                    "usageId": usage_id,
                    "chargedMicros": charged,
                    "allowedMaximumMicros": expected_max,
                }
            )
        if record["settlement_status"] == "settled" and not record["receipt_identity"]:
            findings.append({"severity": "P0", "family": "SETTLED_USAGE_WITHOUT_RECEIPT", "usageId": usage_id})
        if record["settlement_status"] == "settled" and int(record["credit_delta_micros"]) != -charged:
            findings.append(
                {
                    "severity": "P0",
                    "family": "CREDIT_LEDGER_DELTA_MISMATCH",
                    "usageId": usage_id,
                    "expectedDeltaMicros": -charged,
                    "actualDeltaMicros": int(record["credit_delta_micros"]),
                }
            )
        total_provider += provider
        total_charged += charged
        total_credit_delta += int(record["credit_delta_micros"])
    ok = not findings
    return _generic_result(
        schema_version="sovereign.cost-credit-settlement-reconciliation.v1",
        ok=ok,
        status="COST_CREDIT_SETTLEMENT_RECONCILED" if ok else "COST_CREDIT_SETTLEMENT_DRIFT",
        evidence={
            "recordCount": len(payload),
            "allowedMarkupPpm": allowed_markup_ppm,
            "totalProviderCostMicros": total_provider,
            "totalChargedCostMicros": total_charged,
            "totalCreditDeltaMicros": total_credit_delta,
            "integerMathOnly": True,
        },
        findings=findings,
        next_actions=[
            "block entitlement or further execution for unresolved P0 settlement drift",
            "repair by idempotent usage identity rather than creating a second charge",
            "verify receipt, ledger and provider settlement after any correction",
        ],
        runtime_verified=False,
        truth_notice="This reconciles supplied integer evidence only and performs no payment, credit or database mutation.",
    )


def backup_restore_evidence_verify(
    assets: Annotated[list[BackupRestoreEvidence], Field(min_length=1, max_length=100)],
) -> GenericResult:
    """Use this when backup claims must be gated on isolated restore execution, checksum equality and integrity checks."""
    payload = [_scrub(asset.model_dump(mode="json")) for asset in assets]
    findings: list[dict[str, Any]] = []
    for asset in payload:
        if asset["restore_status"] != "passed":
            findings.append(
                {
                    "severity": "P0",
                    "family": "BACKUP_RESTORE_NOT_VERIFIED",
                    "asset": asset["asset"],
                    "restoreStatus": asset["restore_status"],
                }
            )
        if not asset["isolated_target"]:
            findings.append({"severity": "P0", "family": "RESTORE_TARGET_NOT_ISOLATED", "asset": asset["asset"]})
        if not asset["restored_digest"] or asset["backup_digest"] != asset["restored_digest"]:
            findings.append({"severity": "P0", "family": "RESTORE_DIGEST_MISMATCH", "asset": asset["asset"]})
        if not asset["integrity_checks"]:
            findings.append({"severity": "P1", "family": "RESTORE_INTEGRITY_CHECKS_MISSING", "asset": asset["asset"]})
    ok = not any(item["severity"] == "P0" for item in findings)
    return _generic_result(
        schema_version="sovereign.backup-restore-verification.v1",
        ok=ok,
        status="BACKUP_RESTORE_VERIFIED" if ok else "BACKUP_RESTORE_BLOCKED",
        evidence={"assets": payload, "assetCount": len(payload)},
        findings=findings,
        next_actions=[
            "perform a restore canary in an isolated target",
            "compare immutable digests and run asset-specific integrity checks",
            "retain the failed restore evidence and do not label the backup recoverable",
        ],
        runtime_verified=False,
        truth_notice="This verifies supplied restore evidence. It does not create backups or restore production data.",
    )


def slo_error_budget_assess(
    slos: Annotated[list[SloEvidence], Field(min_length=1, max_length=100)],
) -> GenericResult:
    """Use this when availability and latency objectives need deterministic integer error-budget assessment."""
    payload = [_scrub(slo.model_dump(mode="json")) for slo in slos]
    findings: list[dict[str, Any]] = []
    assessments: list[dict[str, Any]] = []
    for slo in payload:
        total = int(slo["total_events"])
        failed = int(slo["failed_events"])
        if failed > total:
            findings.append({"severity": "P0", "family": "SLO_FAILED_EVENTS_EXCEED_TOTAL", "service": slo["service"]})
            observed_ppm = 0
        elif total == 0:
            observed_ppm = 0
            findings.append({"severity": "P1", "family": "SLO_NO_TRAFFIC_EVIDENCE", "service": slo["service"]})
        else:
            observed_ppm = (total - failed) * 1_000_000 // total
        objective_ppm = int(slo["objective_ppm"])
        allowed_failure_ppm = 1_000_000 - objective_ppm
        actual_failure_ppm = 1_000_000 - observed_ppm if total else 0
        remaining_budget_ppm = allowed_failure_ppm - actual_failure_ppm
        latency_met = not slo["latency_objective_ms"] or int(slo["observed_p95_ms"]) <= int(slo["latency_objective_ms"])
        availability_met = total > 0 and observed_ppm >= objective_ppm
        if not availability_met and total > 0:
            findings.append(
                {
                    "severity": "P0",
                    "family": "SLO_AVAILABILITY_BREACHED",
                    "service": slo["service"],
                    "observedPpm": observed_ppm,
                    "objectivePpm": objective_ppm,
                }
            )
        if not latency_met:
            findings.append(
                {
                    "severity": "P0",
                    "family": "SLO_LATENCY_BREACHED",
                    "service": slo["service"],
                    "observedP95Ms": slo["observed_p95_ms"],
                    "objectiveMs": slo["latency_objective_ms"],
                }
            )
        assessments.append(
            {
                "service": slo["service"],
                "observedAvailabilityPpm": observed_ppm,
                "objectivePpm": objective_ppm,
                "remainingErrorBudgetPpm": remaining_budget_ppm,
                "availabilityMet": availability_met,
                "latencyMet": latency_met,
            }
        )
    ok = not any(item["severity"] == "P0" for item in findings)
    return _generic_result(
        schema_version="sovereign.slo-error-budget.v1",
        ok=ok,
        status="SLO_ERROR_BUDGET_HEALTHY" if ok else "SLO_ERROR_BUDGET_BREACHED",
        evidence={"assessments": assessments, "integerMathOnly": True},
        findings=findings,
        next_actions=[
            "pause risky releases while a required SLO has exhausted its budget",
            "correlate the breach with exact revision, deployment and failure-family evidence",
            "resume normal release policy only after the observation window is healthy",
        ],
        runtime_verified=False,
        truth_notice="This computes from supplied counters and latency evidence. It does not collect metrics or claim an observation window that was not provided.",
    )


def configuration_drift_assess(
    workspace_id: WorkspaceId,
    expected_revision: OptionalExactSha = "",
    runtime_evidence: RuntimeConfigEvidence | None = None,
) -> GenericResult:
    """Use this when workspace, expected and installed MCP identity plus bounded runtime health markers must be compared."""
    repo = _workspace_repo(workspace_id)
    workspace_revision = _git(repo, "rev-parse", "HEAD")
    supplied = _scrub(runtime_evidence.model_dump(mode="json")) if runtime_evidence else {}
    live_status: dict[str, Any] = {}
    if _BROKER is not None:
        try:
            live_status = _BROKER.call("mcp_self_update_status", {}, timeout=30)
        except Exception as exc:
            live_status = {"ok": False, "status": "MCP_SELF_UPDATE_STATUS_UNAVAILABLE", "errorType": type(exc).__name__}
    installed_revision = _bounded(live_status.get("revision") or supplied.get("installed_revision"), 40)
    findings: list[dict[str, Any]] = []
    if expected_revision and workspace_revision != expected_revision:
        findings.append(
            {
                "severity": "P0",
                "family": "WORKSPACE_EXPECTED_REVISION_MISMATCH",
                "workspaceRevision": workspace_revision,
                "expectedRevision": expected_revision,
            }
        )
    if expected_revision and installed_revision and installed_revision != expected_revision:
        findings.append(
            {
                "severity": "P0",
                "family": "INSTALLED_EXPECTED_REVISION_MISMATCH",
                "installedRevision": installed_revision,
                "expectedRevision": expected_revision,
            }
        )
    if installed_revision and workspace_revision and installed_revision != workspace_revision:
        findings.append(
            {
                "severity": "P1",
                "family": "WORKSPACE_INSTALLED_REVISION_DRIFT",
                "workspaceRevision": workspace_revision,
                "installedRevision": installed_revision,
            }
        )
    live_protocol_ready = bool(live_status.get("mcp_protocol_ready") or supplied.get("mcp_protocol_ready"))
    live_container_healthy = bool(live_status.get("container_healthy") or supplied.get("container_healthy"))
    live_broker_ready = bool(live_status.get("broker_rpc_ready") or supplied.get("broker_ready"))
    for family, ready in (
        ("MCP_PROTOCOL_NOT_READY", live_protocol_ready),
        ("MCP_CONTAINER_NOT_HEALTHY", live_container_healthy),
        ("MCP_BROKER_NOT_READY", live_broker_ready),
    ):
        if not ready:
            findings.append({"severity": "P0", "family": family})
    ok = not findings
    return _generic_result(
        schema_version="sovereign.configuration-drift.v1",
        ok=ok,
        status="CONFIGURATION_IDENTITY_ALIGNED" if ok else "CONFIGURATION_IDENTITY_DRIFT",
        evidence={
            "workspaceRevision": workspace_revision,
            "expectedRevision": expected_revision or None,
            "installedRevision": installed_revision or None,
            "installedImage": _bounded(live_status.get("image") or supplied.get("image_digest"), 200),
            "containerHealthy": live_container_healthy,
            "mcpProtocolReady": live_protocol_ready,
            "brokerReady": live_broker_ready,
            "liveStatus": _bounded(live_status.get("status"), 120),
        },
        findings=findings,
        next_actions=[
            "resolve the exact authoritative revision before any further change",
            "install only an immutable image carrying the confirmed revision label and digest",
            "verify container health, MCP initialize and broker RPC after replacement",
        ],
        runtime_verified=bool(live_status),
        truth_notice="The workspace revision and available broker self-update status are read directly. Environment values and secrets are never returned.",
    )


def runtime_runbook_generate(
    failure_family: FailureFamily,
    capabilities: Annotated[list[Capability], Field(min_length=1, max_length=10)],
    evidence_summary: BoundedText,
    mutation_allowed: bool = False,
) -> GenericResult:
    """Use this when one exact failure family needs a bounded diagnosis, stop, repair, verification and rollback runbook."""
    allowed_effects: list[EffectClass] = ["read"]
    if mutation_allowed:
        allowed_effects.append("workspace-write")
    route = tool_recommend_for_mission(
        mission_summary=f"Diagnose and contain {failure_family}: {evidence_summary}",
        required_capabilities=capabilities,
        allowed_effects=allowed_effects,
        required_evidence=[failure_family, "revision", "runtime", "verification"],
        max_tools=8,
    )
    selected = route.evidence.get("selectedTools") or []
    tool_names = [item.get("name") for item in selected if isinstance(item, dict)]
    steps = [
        {"phase": "identity", "action": "resolve exact workspace, PR, CI and installed revision", "allowedTools": tool_names},
        {"phase": "diagnosis", "action": "collect bounded evidence for the exact failure family", "allowedTools": tool_names},
        {"phase": "stop", "action": "stop if the failure family changes, revision drifts, owner approval is required or evidence is incomplete", "allowedTools": []},
        {"phase": "repair", "action": "apply the smallest workspace-only repair and add regression coverage", "allowedTools": tool_names if mutation_allowed else []},
        {"phase": "verification", "action": "repeat the original failing check and then adjacent contract gates", "allowedTools": tool_names},
        {"phase": "delivery", "action": "end at one Draft PR; do not merge or deploy automatically", "allowedTools": []},
        {"phase": "rollback", "action": "restore the last confirmed immutable revision or reverse only the exact repair", "allowedTools": []},
    ]
    findings = list(route.findings)
    ok = route.ok
    return _generic_result(
        schema_version="sovereign.runtime-runbook.v1",
        ok=ok,
        status="RUNTIME_RUNBOOK_READY" if ok else "RUNTIME_RUNBOOK_CAPABILITY_GAP",
        evidence={
            "failureFamily": failure_family,
            "evidenceSummary": _bounded(evidence_summary, 1000),
            "mutationAllowed": mutation_allowed,
            "selectedTools": selected,
            "steps": steps,
            "stopConditions": [
                "exact revision cannot be resolved",
                "new failure family appears",
                "owner-protected input is required",
                "a mutation would exceed workspace or Draft-PR boundaries",
                "verification does not reproduce the original green condition",
            ],
        },
        findings=findings,
        next_actions=["execute one phase at a time", "persist evidence after each phase", "never skip the stop conditions"],
        runtime_verified=True,
        truth_notice="The runbook is generated from the live registry and structured capabilities. It does not execute any listed tool or mutation.",
    )


def _codeowners_rules(repo: Path) -> tuple[str, list[tuple[str, list[str]]]]:
    candidates = [repo / ".github" / "CODEOWNERS", repo / "CODEOWNERS", repo / "docs" / "CODEOWNERS"]
    for path in candidates:
        if not path.is_file():
            continue
        rules: list[tuple[str, list[str]]] = []
        for raw_line in path.read_text("utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                rules.append((parts[0], parts[1:]))
        return str(path.relative_to(repo)), rules
    return "", []


def _owners_for_path(path: str, rules: list[tuple[str, list[str]]]) -> list[str]:
    owners: list[str] = []
    normalized = path.lstrip("/")
    for pattern, candidate_owners in rules:
        clean = pattern.lstrip("/")
        matches = fnmatch(normalized, clean) or fnmatch("/" + normalized, pattern)
        if clean.endswith("/") and normalized.startswith(clean):
            matches = True
        if matches:
            owners = list(candidate_owners)
    return owners


def ownership_codeowners_guard(
    workspace_id: WorkspaceId,
    changed_paths: Annotated[list[str], Field(max_length=500)] = [],
) -> GenericResult:
    """Use this when critical changed paths need CODEOWNERS coverage and domain-specific review requirements."""
    repo = _workspace_repo(workspace_id)
    paths = list(changed_paths)
    if not paths:
        diff = _git(repo, "diff", "--name-only", "origin/main...HEAD")
        paths = [line.strip() for line in diff.splitlines() if line.strip()]
    codeowners_path, rules = _codeowners_rules(repo)
    critical_domains = {
        "billing": ("billing", "payment", "credit", "settlement", "llm_cost"),
        "authentication": ("auth", "oauth", "passkey", "security_runtime"),
        "deployment": (".github/workflows", "deploy", "dockerfile", "docker-compose"),
        "learning": ("learning", "memory", "knowledge", "vector"),
        "mcp-control-plane": ("tools/sovereign-chatgpt-mcp", "broker", "command_worker"),
        "database": ("migration", ".sql", "database.py"),
    }
    coverage: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for path in sorted(set(paths)):
        lowered = path.casefold()
        domains = sorted(
            domain for domain, markers in critical_domains.items() if any(marker in lowered for marker in markers)
        )
        owners = _owners_for_path(path, rules)
        coverage.append({"path": path, "domains": domains, "owners": owners})
        if domains and not owners:
            findings.append(
                {
                    "severity": "P0",
                    "family": "CRITICAL_PATH_WITHOUT_CODEOWNER",
                    "path": path,
                    "domains": domains,
                }
            )
    if not codeowners_path:
        findings.append({"severity": "P0", "family": "CODEOWNERS_FILE_MISSING"})
    ok = not findings
    return _generic_result(
        schema_version="sovereign.ownership-codeowners-guard.v1",
        ok=ok,
        status="CODEOWNERS_COVERAGE_READY" if ok else "CODEOWNERS_COVERAGE_BLOCKED",
        evidence={
            "workspaceRevision": _git(repo, "rev-parse", "HEAD"),
            "codeownersPath": codeowners_path or None,
            "changedPathCount": len(paths),
            "coverage": coverage,
        },
        findings=findings,
        next_actions=[
            "assign explicit owners to every critical domain path",
            "require matching review before Billing, Auth, Deployment, Learning, MCP or Database changes leave Draft state",
            "re-run the guard against the exact PR head",
        ],
        runtime_verified=False,
        truth_notice="This parses repository CODEOWNERS rules and changed paths. It does not verify GitHub branch-protection enforcement or reviewer approval state.",
    )


def compliance_evidence_export(
    revision: ExactSha,
    evidence_records: Annotated[list[EvidenceRecord], Field(min_length=1, max_length=500)],
    controls: Annotated[list[ComplianceControl], Field(min_length=1, max_length=100)],
) -> GenericResult:
    """Use this when revision-bound access, approval, deployment, data, payment or learning evidence needs one canonical audit export."""
    records = [_scrub(record.model_dump(mode="json")) for record in evidence_records]
    control_payload = [_scrub(control.model_dump(mode="json")) for control in controls]
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_kind.setdefault(record["kind"], []).append(record)
    control_results: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for control in control_payload:
        missing = []
        failed = []
        for kind in control["required_evidence_kinds"]:
            matches = by_kind.get(kind, [])
            if not matches:
                missing.append(kind)
            elif not any(item["status"] == "success" and item["revision"] == revision for item in matches):
                failed.append(kind)
        status = "satisfied" if not missing and not failed else "not-satisfied"
        control_results.append({**control, "status": status, "missingKinds": missing, "failedKinds": failed})
        if status != "satisfied":
            findings.append(
                {
                    "severity": "P0",
                    "family": "COMPLIANCE_CONTROL_EVIDENCE_INCOMPLETE",
                    "controlId": control["control_id"],
                    "missingKinds": missing,
                    "failedKinds": failed,
                }
            )
    export_payload = {
        "schemaVersion": "sovereign.compliance-evidence-export.v1",
        "revision": revision,
        "controls": control_results,
        "evidence": records,
        "claims": {
            "complianceCertified": False,
            "runtimeIndependentlyVerified": False,
            "secretValuesIncluded": False,
        },
    }
    export_digest = _sha256(export_payload)
    ok = not findings
    return _generic_result(
        schema_version="sovereign.compliance-evidence-export.v1",
        ok=ok,
        status="COMPLIANCE_EVIDENCE_EXPORT_READY" if ok else "COMPLIANCE_EVIDENCE_EXPORT_INCOMPLETE",
        evidence={
            "revision": revision,
            "controlResults": control_results,
            "export": export_payload,
            "exportSha256": export_digest,
            "artifactWritten": False,
        },
        findings=findings,
        next_actions=[
            "obtain missing evidence from authoritative producers",
            "store the canonical payload and digest in an immutable authorized artifact path",
            "do not label the export a certification without an independent audit scope",
        ],
        runtime_verified=False,
        truth_notice="The exporter creates a canonical in-memory payload and digest. It writes no artifact and makes no certification claim.",
    )


def register(mcp: Any, runtime: Any, database: Any, broker: Any) -> None:
    global _MCP, _RUNTIME, _DATABASE, _BROKER, _REGISTERED
    _MCP = mcp
    _RUNTIME = runtime
    _DATABASE = database
    _BROKER = broker
    if _REGISTERED:
        return
    local_tools = (
        operational_skill_inventory,
        mcp_tool_contract_registry,
        tool_recommend_for_mission,
        mcp_registry_snapshot_verify,
        evidence_graph_build,
        agent_run_liveness_assess,
        semantic_intent_boundary_audit,
        cost_credit_settlement_reconcile,
        backup_restore_evidence_verify,
        slo_error_budget_assess,
        runtime_runbook_generate,
        ownership_codeowners_guard,
        compliance_evidence_export,
    )
    network_tools = (
        schema_migration_reconcile,
        llm_route_reliability_assess,
        configuration_drift_assess,
    )
    for tool in local_tools:
        mcp.tool(annotations=LOCAL_READ_ONLY)(tool)
    for tool in network_tools:
        mcp.tool(annotations=NETWORK_READ_ONLY)(tool)
    _REGISTERED = True
