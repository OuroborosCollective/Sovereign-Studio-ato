from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
import hashlib
import json
from pathlib import Path
import re
import time
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
EPHEMERAL_CANARY = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)

WorkspaceId = Annotated[str, Field(min_length=1, max_length=160)]
Sha256Value = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
OptionalSha256 = Annotated[str, Field(pattern=r"^(?:|[0-9a-f]{64})$")]
OptionalRevision = Annotated[str, Field(pattern=r"^(?:|[0-9a-f]{40})$")]
BoundedName = Annotated[str, Field(min_length=1, max_length=160)]
BoundedText = Annotated[str, Field(min_length=1, max_length=2000)]
Severity = Literal["P0", "P1", "P2", "P3"]
LifecycleState = Literal["experimental", "active", "restricted", "deprecated", "removed"]

_MCP: Any = None
_RUNTIME: Any = None
_DATABASE: Any = None
_BROKER: Any = None
_REGISTERED = False

_SECRET_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:sk-(?:proj-)?[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"authorization\s*:\s*bearer|password\s*[:=]|api[_-]?key\s*[:=]|private[_-]?key)",
    re.I,
)
_SECRET_LITERAL_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:sk-(?:proj-)?[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"(?i:(?:password|passwd|secret|token|api[_-]?key)\s*[:=]\s*['\"][^'\"]{8,}['\"]))"
)
_DYNAMIC_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("PYTHON_EVAL", re.compile(r"\beval\s*\(")),
    ("PYTHON_EXEC", re.compile(r"\bexec\s*\(")),
    ("PYTHON_DYNAMIC_IMPORT", re.compile(r"\bimportlib\.(?:import_module|__import__)\s*\(")),
    ("PYTHON_SHELL_TRUE", re.compile(r"\b(?:subprocess\.(?:run|Popen|call)|os\.system)\b.{0,180}(?:shell\s*=\s*True|\()")),
    ("JS_FUNCTION_CONSTRUCTOR", re.compile(r"\bnew\s+Function\s*\(")),
    ("JS_EVAL", re.compile(r"\beval\s*\(")),
    ("JS_CHILD_PROCESS", re.compile(r"\b(?:exec|execSync|spawn|spawnSync)\s*\(")),
    ("JS_VM_RUNTIME", re.compile(r"\bvm\.(?:runIn|Script)")),
    ("JS_DYNAMIC_IMPORT", re.compile(r"\bimport\s*\([^)]")),
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CapacityThresholds(StrictModel):
    load_per_cpu_warn_ppm: Annotated[int, Field(ge=100_000, le=5_000_000)] = 900_000
    memory_used_warn_ppm: Annotated[int, Field(ge=100_000, le=1_000_000)] = 850_000
    swap_used_warn_ppm: Annotated[int, Field(ge=0, le=1_000_000)] = 500_000
    disk_used_warn_ppm: Annotated[int, Field(ge=100_000, le=1_000_000)] = 850_000
    inode_used_warn_ppm: Annotated[int, Field(ge=100_000, le=1_000_000)] = 850_000
    queue_length_warn: Annotated[int, Field(ge=1, le=1_000_000)] = 100
    queue_oldest_age_warn_seconds: Annotated[int, Field(ge=1, le=31_536_000)] = 900
    postgres_pool_used_warn_ppm: Annotated[int, Field(ge=100_000, le=1_000_000)] = 850_000


class PostgresPoolEvidence(StrictModel):
    active: Annotated[int, Field(ge=0, le=1_000_000)] = 0
    idle: Annotated[int, Field(ge=0, le=1_000_000)] = 0
    waiting: Annotated[int, Field(ge=0, le=1_000_000)] = 0
    maximum: Annotated[int, Field(ge=0, le=1_000_000)] = 0
    source: Annotated[str, Field(max_length=160)] = "supplied-evidence"


class QueueStreamEvidence(StrictModel):
    name: BoundedName
    pending: Annotated[int, Field(ge=0, le=10**12)]
    oldest_age_seconds: Annotated[int, Field(ge=0, le=10**12)]
    retries: Annotated[int, Field(ge=0, le=10**12)] = 0
    dead_letters: Annotated[int, Field(ge=0, le=10**12)] = 0
    duplicate_identities: Annotated[int, Field(ge=0, le=10**12)] = 0
    processed_delta: Annotated[int, Field(ge=0, le=10**12)] = 0
    observation_window_seconds: Annotated[int, Field(ge=1, le=10**9)] = 300
    worker_ready: bool = True


class MaintenanceTask(StrictModel):
    task_id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._:-]{1,79}$")]
    category: Literal["patchmon", "database", "backup", "reindex", "certificate", "deployment", "other"]
    duration_seconds: Annotated[int, Field(ge=1, le=604_800)]
    earliest_start_epoch: Annotated[int, Field(ge=0, le=10**12)]
    latest_finish_epoch: Annotated[int, Field(ge=1, le=10**12)]
    conflicts_with: Annotated[list[str], Field(max_length=32)] = []
    requires: Annotated[list[str], Field(max_length=32)] = []
    exclusive: bool = False


class TopologySnapshot(StrictModel):
    revision: OptionalRevision = ""
    services: dict[str, dict[str, Any]] = {}
    networks: dict[str, dict[str, Any]] = {}
    volumes: dict[str, dict[str, Any]] = {}


class QueryFamilyEvidence(StrictModel):
    family: BoundedName
    calls: Annotated[int, Field(ge=0, le=10**15)]
    mean_ms: Annotated[int, Field(ge=0, le=10**9)]
    p95_ms: Annotated[int, Field(ge=0, le=10**9)]
    rows_read: Annotated[int, Field(ge=0, le=10**18)] = 0
    rows_returned: Annotated[int, Field(ge=0, le=10**18)] = 0
    sequential_scans: Annotated[int, Field(ge=0, le=10**15)] = 0
    index_scans: Annotated[int, Field(ge=0, le=10**15)] = 0
    lock_wait_ms: Annotated[int, Field(ge=0, le=10**12)] = 0
    plan_hash: OptionalSha256 = ""


class InvariantEvidence(StrictModel):
    invariant_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{1,79}$")]
    description: Annotated[str, Field(min_length=4, max_length=500)]
    expected: Annotated[int, Field(ge=-(10**18), le=10**18)]
    observed: Annotated[int, Field(ge=-(10**18), le=10**18)]
    scope_identity: Annotated[str, Field(min_length=1, max_length=200)]
    revision: OptionalRevision = ""


class RepairCandidate(StrictModel):
    repair_id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._:-]{1,79}$")]
    target: BoundedName
    predicate: Annotated[str, Field(min_length=4, max_length=600)]
    desired_state: dict[str, Any]
    current_identity_hash: Sha256Value
    estimated_rows: Annotated[int, Field(ge=0, le=10**12)]
    reversible: bool = True


class VectorRecordEvidence(StrictModel):
    source_id: BoundedName
    block_id: BoundedName
    source_content_hash: Sha256Value
    vector_content_hash: OptionalSha256 = ""
    embedding_model: Annotated[str, Field(min_length=1, max_length=160)]
    expected_embedding_model: Annotated[str, Field(min_length=1, max_length=160)]
    outbox_state: Literal["missing", "pending", "processing", "completed", "failed"]
    vector_count: Annotated[int, Field(ge=0, le=1000)] = 0
    duplicate_vector_ids: Annotated[int, Field(ge=0, le=1000)] = 0


class LearningCandidateEvidence(StrictModel):
    candidate_id: BoundedName
    source_kind: Annotated[str, Field(min_length=1, max_length=80)]
    source_identity: Annotated[str, Field(min_length=1, max_length=240)]
    revision: OptionalRevision = ""
    test_evidence_count: Annotated[int, Field(ge=0, le=10000)] = 0
    scope: Annotated[str, Field(min_length=1, max_length=240)]
    created_epoch: Annotated[int, Field(ge=0, le=10**12)]
    expires_epoch: Annotated[int, Field(ge=0, le=10**12)] = 0
    conflicts: Annotated[list[str], Field(max_length=64)] = []
    outcome_count: Annotated[int, Field(ge=0, le=10**9)] = 0


class PatternLifecycleRecord(StrictModel):
    pattern_id: BoundedName
    version: Annotated[int, Field(ge=1, le=1_000_000)]
    state: LifecycleState
    content_hash: Sha256Value
    supersedes: Annotated[list[str], Field(max_length=32)] = []
    conflicts: Annotated[list[str], Field(max_length=32)] = []


class RetentionRule(StrictModel):
    dataset: BoundedName
    retention_days: Annotated[int, Field(ge=0, le=36500)]
    deletion_verified: bool = False
    pseudonymization: Literal["none", "partial", "required", "verified"] = "none"
    export_supported: bool = False
    tenant_key_present: bool = False
    legal_hold_supported: bool = False


class IsolationTestResult(StrictModel):
    surface: Literal["user", "project", "repository", "credit", "memory", "agent-run"]
    test_id: BoundedName
    negative_access_denied: bool
    cross_tenant_identifier_redacted: bool
    budget_isolated: bool = True
    evidence_identity: Annotated[str, Field(min_length=1, max_length=240)]


class SchemaSurface(StrictModel):
    version: Annotated[str, Field(min_length=1, max_length=80)]
    tools: dict[str, dict[str, Any]]


class ToolPermissionRequirement(StrictModel):
    tool_name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")]
    declared: Annotated[list[str], Field(max_length=32)] = []
    observed: Annotated[list[str], Field(max_length=32)] = []
    required: Annotated[list[str], Field(max_length=32)] = []


class CapabilityRequirement(StrictModel):
    task_id: BoundedName
    required_capabilities: Annotated[list[str], Field(min_length=1, max_length=24)]


class SkillLifecycleRecord(StrictModel):
    name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,119}$")]
    state: LifecycleState
    replacement: Annotated[str, Field(max_length=120)] = ""
    active_callers: Annotated[int, Field(ge=0, le=10**9)] = 0
    last_success_epoch: Annotated[int, Field(ge=0, le=10**12)] = 0


class SkillTransitionRequest(StrictModel):
    name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,119}$")]
    target_state: LifecycleState


class RegressionMission(StrictModel):
    mission_id: BoundedName
    expected_tools: Annotated[list[str], Field(min_length=1, max_length=32)]
    actual_tools: Annotated[list[str], Field(max_length=32)]
    allowed_effects: Annotated[list[str], Field(min_length=1, max_length=8)]
    observed_effects: Annotated[list[str], Field(max_length=8)]
    required_evidence: Annotated[list[str], Field(max_length=32)] = []
    observed_evidence: Annotated[list[str], Field(max_length=32)] = []


class IdempotencyObservation(StrictModel):
    tool_name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")]
    request_hash: Sha256Value
    invocation_count: Annotated[int, Field(ge=1, le=1_000_000)]
    unique_side_effect_ids: Annotated[int, Field(ge=0, le=1_000_000)]
    terminal_result_hashes: Annotated[list[Sha256Value], Field(max_length=64)] = []


class ApprovalRule(StrictModel):
    action_pattern: Annotated[str, Field(min_length=1, max_length=160)]
    approval_required: bool
    ttl_seconds: Annotated[int, Field(ge=0, le=31_536_000)] = 900
    bind_revision: bool = True
    bind_payload_hash: bool = True


class ApprovalContext(StrictModel):
    action: BoundedName
    revision: OptionalRevision = ""
    payload_hash: OptionalSha256 = ""
    approval_created_epoch: Annotated[int, Field(ge=0, le=10**12)] = 0
    approved_revision: OptionalRevision = ""
    approved_payload_hash: OptionalSha256 = ""
    approval_status: Literal["missing", "pending", "approved", "expired", "rejected"] = "missing"


class SecretReference(StrictModel):
    secret_id: BoundedName
    owner: BoundedName
    target_system: BoundedName
    created_epoch: Annotated[int, Field(ge=0, le=10**12)]
    rotated_epoch: Annotated[int, Field(ge=0, le=10**12)] = 0
    rotation_interval_days: Annotated[int, Field(ge=1, le=3650)] = 90
    last_canary_epoch: Annotated[int, Field(ge=0, le=10**12)] = 0
    last_canary_ok: bool = False


class SupplyChainEvidence(StrictModel):
    revision: OptionalRevision = ""
    image_digest: Annotated[str, Field(pattern=r"^(?:|sha256:[0-9a-f]{64})$")]
    revision_label: OptionalRevision = ""
    sbom_digest: OptionalSha256 = ""
    provenance_digest: OptionalSha256 = ""
    signature_verified: bool = False
    attestation_verified: bool = False
    dependencies_pinned: bool = False


class VulnerabilityEvidence(StrictModel):
    vulnerability_id: Annotated[str, Field(min_length=3, max_length=80)]
    package: BoundedName
    current_version: Annotated[str, Field(min_length=1, max_length=80)]
    fixed_version: Annotated[str, Field(max_length=80)] = ""
    severity: Literal["critical", "high", "medium", "low", "unknown"]
    reachable_production_path: bool = False
    exploit_prerequisites_met: bool = False
    breaking_upgrade: bool = False


class AuthNegativeTest(StrictModel):
    case: Literal[
        "oauth-state",
        "pkce",
        "passkey",
        "session-expiry",
        "step-up",
        "replay",
        "wrong-audience",
        "revoked-token",
        "parallel-access",
    ]
    test_id: BoundedName
    denied_as_expected: bool
    state_unchanged: bool
    evidence_identity: Annotated[str, Field(min_length=1, max_length=240)]


@dataclass(frozen=True)
class AssuranceResult:
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
        return {_bounded(key, 160): _scrub(item) for key, item in value.items()}
    return value


def _ppm(part: int, whole: int) -> int:
    if whole <= 0:
        return 0
    return max(0, min(10_000_000, int(part) * 1_000_000 // int(whole)))


def _result(
    *,
    schema: str,
    ok: bool,
    status: str,
    evidence: dict[str, Any],
    findings: list[dict[str, Any]],
    next_actions: list[str],
    runtime_verified: bool,
    truth_notice: str,
    mutation_performed: bool = False,
) -> AssuranceResult:
    safe_evidence = _scrub(evidence)
    safe_findings = _scrub(findings)
    payload = {
        "schemaVersion": schema,
        "status": status,
        "evidence": safe_evidence,
        "findings": safe_findings,
        "nextActions": next_actions,
    }
    return AssuranceResult(
        schemaVersion=schema,
        ok=ok,
        status=status,
        evidence=safe_evidence,
        findings=safe_findings,
        nextActions=next_actions,
        evidenceSha256=_sha256(payload),
        mutationPerformed=mutation_performed,
        runtimeVerified=runtime_verified,
        secretValuesReturned=False,
        truthNotice=truth_notice,
    )


def _workspace_repo(workspace_id: str) -> Path:
    if _RUNTIME is None:
        raise RuntimeError("Operational assurance runtime is not registered")
    return Path(_RUNTIME._repo(workspace_id))


def operational_assurance_skill_inventory() -> AssuranceResult:
    """Use this when the final operational assurance skill families and their tool identities must be listed without execution."""
    tools = [
        ("16", "sovereign-vps-capacity-resource-pressure", "vps_capacity_resource_pressure_assess"),
        ("17", "sovereign-runtime-dependency-health-matrix", "runtime_dependency_health_matrix"),
        ("18", "sovereign-outbox-queue-liveness", "outbox_queue_liveness_assess"),
        ("19", "sovereign-scheduled-maintenance-coordinator", "scheduled_maintenance_coordinate"),
        ("20", "sovereign-runtime-topology-change-auditor", "runtime_topology_change_audit"),
        ("21", "sovereign-postgres-query-index-performance", "postgres_query_index_performance_assess"),
        ("22", "sovereign-data-integrity-invariant-auditor", "data_integrity_invariant_audit"),
        ("23", "sovereign-data-repair-planner", "data_repair_plan_build"),
        ("24", "sovereign-vector-memory-consistency", "vector_memory_consistency_assess"),
        ("25", "sovereign-memory-poisoning-provenance-guardian", "memory_poisoning_provenance_guard"),
        ("26", "sovereign-learning-pattern-lifecycle", "learning_pattern_lifecycle_preview"),
        ("27", "sovereign-data-retention-privacy", "data_retention_privacy_audit"),
        ("28", "sovereign-multi-tenant-isolation-verifier", "multi_tenant_isolation_verify"),
        ("29", "sovereign-mcp-tool-contract-registry", "mcp_tool_contract_registry"),
        ("30", "sovereign-mcp-schema-compatibility-auditor", "mcp_schema_compatibility_audit"),
        ("31", "sovereign-mcp-protocol-conformance-fuzzing", "mcp_protocol_conformance_fuzz_plan"),
        ("32", "sovereign-tool-permission-minimizer", "tool_permission_minimize"),
        ("33", "sovereign-dynamic-execution-containment-auditor", "dynamic_execution_containment_audit"),
        ("34", "sovereign-skill-capability-coverage-mapper", "skill_capability_coverage_map"),
        ("35", "sovereign-skill-lifecycle-deprecation", "skill_lifecycle_deprecation_preview"),
        ("36", "sovereign-skill-regression-benchmark", "skill_regression_benchmark"),
        ("37", "sovereign-tool-idempotency-verifier", "tool_idempotency_verify"),
        ("38", "sovereign-owner-approval-policy-engine", "owner_approval_policy_evaluate"),
        ("39", "sovereign-secret-lifecycle-rotation", "secret_lifecycle_rotation_assess"),
        ("40", "sovereign-secret-literal-triage", "secret_literal_triage"),
        ("41", "sovereign-sbom-provenance-image-signing", "sbom_provenance_image_signing_verify"),
        ("42", "sovereign-dependency-vulnerability-remediation", "dependency_vulnerability_remediation_plan"),
        ("43", "sovereign-authentication-chaos-negative-test", "authentication_chaos_negative_test_assess"),
    ]
    evidence = {
        "numberedSlots": 28,
        "newTools": 27,
        "existingReusedTools": ["mcp_tool_contract_registry"],
        "uniqueNewSkillFamilies": 27,
        "skills": [
            {"number": number, "name": name, "tool": tool, "mutationByDefault": False}
            for number, name, tool in tools
        ],
        "boundaries": {
            "genericShell": False,
            "arbitrarySql": False,
            "secretValuesAccepted": False,
            "automaticRepair": False,
            "automaticApproval": False,
            "automaticDeprecation": False,
        },
    }
    return _result(
        schema="sovereign.operational-assurance-inventory.v1",
        ok=True,
        status="OPERATIONAL_ASSURANCE_SKILLS_READY",
        evidence=evidence,
        findings=[],
        next_actions=["select the smallest skill matching the current evidence gap"],
        runtime_verified=True,
        truth_notice="Number 29 reuses the already registered MCP Tool Contract Registry; the other numbered capabilities are distinct tools.",
    )


def vps_capacity_resource_pressure_assess(
    thresholds: CapacityThresholds | None = None,
    postgres_pool: PostgresPoolEvidence | None = None,
) -> AssuranceResult:
    """Use this when real host, container, queue and optional PostgreSQL-pool pressure must be separated from software failures."""
    selected = thresholds or CapacityThresholds()
    findings: list[dict[str, Any]] = []
    try:
        snapshot = _BROKER.call("runtime_capacity_snapshot", {}, timeout=90) if _BROKER is not None else {}
    except Exception as exc:
        snapshot = {"ok": False, "status": "CAPACITY_SNAPSHOT_UNAVAILABLE", "errorType": type(exc).__name__}
    host = snapshot.get("host") if isinstance(snapshot, dict) and isinstance(snapshot.get("host"), dict) else {}
    cpu_count = int(host.get("cpuCount") or 0)
    load_1m_milli = int(host.get("load1mMilli") or 0)
    load_per_cpu_ppm = (load_1m_milli * 1000 // cpu_count) if cpu_count else 0
    if not snapshot.get("ok"):
        findings.append({"severity": "P0", "family": "VPS_CAPACITY_SNAPSHOT_UNAVAILABLE"})
    elif load_per_cpu_ppm >= selected.load_per_cpu_warn_ppm:
        findings.append({"severity": "P1", "family": "HOST_CPU_LOAD_PRESSURE", "loadPerCpuPpm": load_per_cpu_ppm})
    memory = host.get("memory") if isinstance(host.get("memory"), dict) else {}
    memory_used_ppm = _ppm(int(memory.get("usedBytes") or 0), int(memory.get("totalBytes") or 0))
    if memory_used_ppm >= selected.memory_used_warn_ppm:
        findings.append({"severity": "P0", "family": "HOST_MEMORY_PRESSURE", "usedPpm": memory_used_ppm})
    swap = host.get("swap") if isinstance(host.get("swap"), dict) else {}
    swap_used_ppm = _ppm(int(swap.get("usedBytes") or 0), int(swap.get("totalBytes") or 0))
    if int(swap.get("totalBytes") or 0) and swap_used_ppm >= selected.swap_used_warn_ppm:
        findings.append({"severity": "P1", "family": "HOST_SWAP_PRESSURE", "usedPpm": swap_used_ppm})
    for filesystem in snapshot.get("filesystems") or []:
        if not isinstance(filesystem, dict):
            continue
        if int(filesystem.get("usedPpm") or 0) >= selected.disk_used_warn_ppm:
            findings.append({"severity": "P0", "family": "FILESYSTEM_CAPACITY_PRESSURE", "path": filesystem.get("path"), "usedPpm": filesystem.get("usedPpm")})
        if int(filesystem.get("inodeUsedPpm") or 0) >= selected.inode_used_warn_ppm:
            findings.append({"severity": "P0", "family": "FILESYSTEM_INODE_PRESSURE", "path": filesystem.get("path"), "usedPpm": filesystem.get("inodeUsedPpm")})
    queue = snapshot.get("hostCommandQueue") if isinstance(snapshot.get("hostCommandQueue"), dict) else {}
    if int(queue.get("pending") or 0) >= selected.queue_length_warn:
        findings.append({"severity": "P1", "family": "HOST_COMMAND_QUEUE_BACKLOG", "pending": queue.get("pending")})
    if int(queue.get("oldestAgeSeconds") or 0) >= selected.queue_oldest_age_warn_seconds:
        findings.append({"severity": "P0", "family": "HOST_COMMAND_QUEUE_STALLED", "oldestAgeSeconds": queue.get("oldestAgeSeconds")})
    oom = [item for item in snapshot.get("containers") or [] if isinstance(item, dict) and item.get("oomKilled")]
    if oom:
        findings.append({"severity": "P0", "family": "CONTAINER_OOM_EVENTS_PRESENT", "containers": [item.get("name") for item in oom]})
    pool_payload = postgres_pool.model_dump(mode="json") if postgres_pool else None
    if postgres_pool and postgres_pool.maximum:
        used_ppm = _ppm(postgres_pool.active + postgres_pool.waiting, postgres_pool.maximum)
        if used_ppm >= selected.postgres_pool_used_warn_ppm or postgres_pool.waiting:
            findings.append({"severity": "P0", "family": "POSTGRES_POOL_PRESSURE", "usedPpm": used_ppm, "waiting": postgres_pool.waiting})
    ok = not any(item["severity"] == "P0" for item in findings)
    return _result(
        schema="sovereign.vps-capacity-resource-pressure.v1",
        ok=ok,
        status="VPS_CAPACITY_HEALTHY" if ok else "VPS_CAPACITY_PRESSURE",
        evidence={
            "snapshot": snapshot,
            "derived": {"loadPerCpuPpm": load_per_cpu_ppm, "memoryUsedPpm": memory_used_ppm, "swapUsedPpm": swap_used_ppm},
            "postgresPool": pool_payload,
            "thresholds": selected.model_dump(mode="json"),
        },
        findings=findings,
        next_actions=["resolve P0 resource pressure before changing application code", "correlate OOM and queue age with exact deployment revision"],
        runtime_verified=bool(snapshot.get("ok")),
        truth_notice="Host and container metrics are read from the private host broker. PostgreSQL pool evidence is optional structured metadata and is never inferred from environment variables.",
    )


def runtime_dependency_health_matrix(
    include_ephemeral_canaries: bool = False,
) -> AssuranceResult:
    """Use this when critical dependency canaries must be mapped to the product functions they block or degrade."""
    def safe(name: str, call: Any) -> dict[str, Any]:
        try:
            value = call()
            return value if isinstance(value, dict) else {"ok": False, "status": f"{name}_INVALID"}
        except Exception as exc:
            return {"ok": False, "status": f"{name}_UNAVAILABLE", "errorType": type(exc).__name__}

    broker = safe("BROKER", lambda: _BROKER.status()) if _BROKER is not None else {"ok": False, "status": "BROKER_UNREGISTERED"}
    postgres = safe("POSTGRES", lambda: _DATABASE.canary()) if _DATABASE is not None else {"ok": False, "status": "DATABASE_UNREGISTERED"}
    pgvector = safe("PGVECTOR", lambda: _DATABASE.vector_canary()) if _DATABASE is not None else {"ok": False, "status": "DATABASE_UNREGISTERED"}
    if _BROKER is not None:
        try:
            capacity_result = vps_capacity_resource_pressure_assess()
            capacity = {
                "ok": capacity_result.ok,
                "status": capacity_result.status,
                "findings": capacity_result.findings,
                "evidence": capacity_result.evidence,
                "runtimeVerified": capacity_result.runtimeVerified,
            }
        except Exception as exc:
            capacity = {
                "ok": False,
                "status": "CAPACITY_ASSESSMENT_UNAVAILABLE",
                "findings": [
                    {
                        "severity": "P0",
                        "family": "VPS_CAPACITY_ASSESSMENT_UNAVAILABLE",
                        "errorType": type(exc).__name__,
                    }
                ],
                "runtimeVerified": False,
            }
    else:
        capacity = {
            "ok": False,
            "status": "BROKER_UNREGISTERED",
            "findings": [
                {"severity": "P0", "family": "VPS_CAPACITY_BROKER_UNREGISTERED"}
            ],
            "runtimeVerified": False,
        }
    backend = safe("BACKEND_CONTAINER", lambda: _BROKER.call("container_status", {"container": "sovereign-backend"}, timeout=30)) if _BROKER is not None else {"ok": False}
    mcp = safe("MCP_CONTAINER", lambda: _BROKER.call("container_status", {"container": "sovereign-chatgpt-mcp"}, timeout=30)) if _BROKER is not None else {"ok": False}
    document = {"ok": None, "status": "NOT_REQUESTED"}
    milvus = {"ok": None, "status": "NOT_REQUESTED"}
    mutation = False
    if include_ephemeral_canaries and _BROKER is not None:
        document = safe("DOCUMENT_PIPELINE", lambda: _BROKER.call("document_pipeline_live_canary", {"marker": "SOVEREIGN_DEPENDENCY_MATRIX_CANARY"}, timeout=120))
        milvus = safe("MILVUS_GATEWAY", lambda: _BROKER.call("memory_gateway_collection_canary", {}, timeout=240))
        mutation = True
    dependencies = [
        {"dependency": "postgresql", "ok": bool(postgres.get("ok")), "status": postgres.get("status"), "blockedFunctions": ["login", "credit verification", "agent runs", "knowledge source truth"]},
        {"dependency": "pgvector", "ok": bool(pgvector.get("ok")), "status": pgvector.get("status"), "blockedFunctions": ["semantic knowledge search", "proven learning lookup"]},
        {"dependency": "mcp-control-plane", "ok": broker.get("status") == "BROKER_READY", "status": broker.get("status"), "blockedFunctions": ["host mutations", "deployments", "self-update", "workflow control"]},
        {"dependency": "backend-container", "ok": bool(backend.get("ok")), "status": backend.get("status"), "blockedFunctions": ["product API", "authentication", "billing", "agents"]},
        {"dependency": "mcp-container", "ok": bool(mcp.get("ok")), "status": mcp.get("status"), "blockedFunctions": ["Sovottt tools", "owner workflows"]},
        {
            "dependency": "host-capacity",
            "ok": bool(capacity.get("ok")),
            "status": capacity.get("status"),
            "blockedFunctions": ["all runtime functions under pressure"],
            "causeFindings": capacity.get("findings") or [],
        },
        {"dependency": "document-pipeline", "ok": document.get("ok"), "status": document.get("status"), "blockedFunctions": ["DOCX to PDF", "PDF marker verification"]},
        {"dependency": "milvus-memory-gateway", "ok": milvus.get("ok"), "status": milvus.get("status"), "blockedFunctions": ["Milvus collection operations", "external vector memory canary"]},
    ]
    findings: list[dict[str, Any]] = []
    for item in dependencies:
        if item["ok"] is not False:
            continue
        finding: dict[str, Any] = {
            "severity": "P0",
            "family": "DEPENDENCY_CANARY_FAILED",
            "dependency": item["dependency"],
            "blockedFunctions": item["blockedFunctions"],
        }
        if item.get("causeFindings"):
            finding["causeFindings"] = item["causeFindings"]
        findings.append(finding)
    unknown = [item["dependency"] for item in dependencies if item["ok"] is None]
    ok = not findings
    return _result(
        schema="sovereign.runtime-dependency-health-matrix.v1",
        ok=ok,
        status="DEPENDENCY_MATRIX_HEALTHY" if ok else "DEPENDENCY_MATRIX_DEGRADED",
        evidence={"dependencies": dependencies, "unknownDependencies": unknown, "raw": {"broker": broker, "postgres": postgres, "pgvector": pgvector, "capacity": capacity, "backend": backend, "mcp": mcp, "document": document, "milvus": milvus}},
        findings=findings,
        next_actions=["stop functions whose authoritative dependency canary failed", "run ephemeral canaries only when their cleanup path is allowed"],
        runtime_verified=True,
        truth_notice="Core broker, container, PostgreSQL, pgvector and host-capacity canaries are executed live. Document and Milvus functional canaries run only when explicitly requested and clean up their temporary artifacts.",
        mutation_performed=mutation,
    )


def outbox_queue_liveness_assess(
    streams: Annotated[list[QueueStreamEvidence], Field(min_length=1, max_length=100)],
    pending_warn: Annotated[int, Field(ge=1, le=10**12)] = 100,
    oldest_age_warn_seconds: Annotated[int, Field(ge=1, le=10**12)] = 900,
) -> AssuranceResult:
    """Use this when outbox, worker queue, retry, dead-letter and idempotency evidence must be evaluated together."""
    payload = [item.model_dump(mode="json") for item in streams]
    findings: list[dict[str, Any]] = []
    for item in payload:
        if not item["worker_ready"] and item["pending"]:
            findings.append({"severity": "P0", "family": "QUEUE_WORKER_NOT_READY", "stream": item["name"]})
        if item["pending"] >= pending_warn and item["processed_delta"] == 0:
            findings.append({"severity": "P0", "family": "QUEUE_NO_FORWARD_PROGRESS", "stream": item["name"], "pending": item["pending"]})
        if item["oldest_age_seconds"] >= oldest_age_warn_seconds:
            findings.append({"severity": "P0", "family": "QUEUE_OLDEST_ITEM_STALE", "stream": item["name"], "ageSeconds": item["oldest_age_seconds"]})
        if item["dead_letters"]:
            findings.append({"severity": "P1", "family": "QUEUE_DEAD_LETTERS_PRESENT", "stream": item["name"], "count": item["dead_letters"]})
        if item["duplicate_identities"]:
            findings.append({"severity": "P0", "family": "QUEUE_IDEMPOTENCY_DUPLICATES", "stream": item["name"], "count": item["duplicate_identities"]})
    ok = not any(item["severity"] == "P0" for item in findings)
    return _result(
        schema="sovereign.outbox-queue-liveness.v1",
        ok=ok,
        status="OUTBOX_QUEUE_LIVE" if ok else "OUTBOX_QUEUE_STALLED",
        evidence={"streams": payload, "thresholds": {"pendingWarn": pending_warn, "oldestAgeWarnSeconds": oldest_age_warn_seconds}},
        findings=findings,
        next_actions=["repair the worker or poison message before replaying the queue", "replay by idempotency identity and verify forward progress"],
        runtime_verified=False,
        truth_notice="This evaluates supplied bounded queue counters. It does not read arbitrary outbox rows or acknowledge messages.",
    )


def scheduled_maintenance_coordinate(
    tasks: Annotated[list[MaintenanceTask], Field(min_length=1, max_length=100)],
    window_start_epoch: Annotated[int, Field(ge=0, le=10**12)],
    window_end_epoch: Annotated[int, Field(ge=1, le=10**12)],
) -> AssuranceResult:
    """Use this when PatchMon, database, backup, reindex, certificate and deployment work needs one conflict-free window plan."""
    if window_end_epoch <= window_start_epoch:
        raise ValueError("window_end_epoch must be greater than window_start_epoch")
    records = sorted((task.model_dump(mode="json") for task in tasks), key=lambda item: (item["earliest_start_epoch"], item["task_id"]))
    scheduled: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    completed: set[str] = set()
    cursor = window_start_epoch
    for task in records:
        missing_requires = sorted(set(task["requires"]) - completed)
        if missing_requires:
            findings.append({"severity": "P0", "family": "MAINTENANCE_PREREQUISITE_UNSCHEDULED", "taskId": task["task_id"], "missing": missing_requires})
            continue
        start = max(cursor, task["earliest_start_epoch"], window_start_epoch)
        finish = start + task["duration_seconds"]
        overlapping_conflicts = [
            existing["taskId"]
            for existing in scheduled
            if existing["taskId"] in task["conflicts_with"]
            and start < existing["finishEpoch"]
            and finish > existing["startEpoch"]
        ]
        if finish > min(task["latest_finish_epoch"], window_end_epoch):
            findings.append({"severity": "P0", "family": "MAINTENANCE_TASK_OUTSIDE_WINDOW", "taskId": task["task_id"]})
            continue
        if overlapping_conflicts:
            findings.append({"severity": "P0", "family": "MAINTENANCE_CONFLICT", "taskId": task["task_id"], "conflicts": overlapping_conflicts})
            continue
        scheduled.append({"taskId": task["task_id"], "category": task["category"], "startEpoch": start, "finishEpoch": finish, "exclusive": task["exclusive"]})
        completed.add(task["task_id"])
        if task["exclusive"] or task["category"] in {"database", "deployment", "reindex"}:
            cursor = finish
    ok = len(scheduled) == len(records) and not findings
    return _result(
        schema="sovereign.scheduled-maintenance-coordination.v1",
        ok=ok,
        status="MAINTENANCE_WINDOW_READY" if ok else "MAINTENANCE_WINDOW_BLOCKED",
        evidence={"window": {"startEpoch": window_start_epoch, "endEpoch": window_end_epoch}, "schedule": scheduled, "unscheduledCount": len(records) - len(scheduled), "planSha256": _sha256(scheduled)},
        findings=findings,
        next_actions=["bind each maintenance execution to this exact plan hash", "stop the window when an unscheduled dependency or runtime failure appears"],
        runtime_verified=False,
        truth_notice="This creates a deterministic plan only. It does not schedule PatchMon, backups, certificates, database work or deployments.",
    )


def runtime_topology_change_audit(before: TopologySnapshot, after: TopologySnapshot) -> AssuranceResult:
    """Use this when Compose services, networks, volumes and service identities must be compared between confirmed revisions."""
    left = before.model_dump(mode="json")
    right = after.model_dump(mode="json")
    findings: list[dict[str, Any]] = []
    changes: dict[str, Any] = {}
    for section in ("services", "networks", "volumes"):
        old = left[section]
        new = right[section]
        added = sorted(set(new) - set(old))
        removed = sorted(set(old) - set(new))
        changed = sorted(name for name in set(old) & set(new) if _sha256(old[name]) != _sha256(new[name]))
        changes[section] = {"added": added, "removed": removed, "changed": changed}
        for name in removed:
            findings.append({"severity": "P0", "family": "RUNTIME_TOPOLOGY_IDENTITY_REMOVED", "section": section, "name": name})
        for name in changed:
            findings.append({"severity": "P1", "family": "RUNTIME_TOPOLOGY_IDENTITY_CHANGED", "section": section, "name": name})
    revision_missing = not left["revision"] or not right["revision"]
    if revision_missing:
        findings.append({"severity": "P0", "family": "TOPOLOGY_REVISION_IDENTITY_MISSING"})
    ok = not any(item["severity"] == "P0" for item in findings)
    return _result(
        schema="sovereign.runtime-topology-change-audit.v1",
        ok=ok,
        status="RUNTIME_TOPOLOGY_COMPATIBLE" if ok else "RUNTIME_TOPOLOGY_REVIEW_REQUIRED",
        evidence={"beforeRevision": left["revision"], "afterRevision": right["revision"], "changes": changes, "beforeSha256": _sha256(left), "afterSha256": _sha256(right)},
        findings=findings,
        next_actions=["review network and volume changes as release-critical code", "verify persistence and rollback before accepting removed identities"],
        runtime_verified=False,
        truth_notice="The auditor compares supplied confirmed topology snapshots; it does not inspect Docker or Compose by itself.",
    )


def postgres_query_index_performance_assess(
    query_families: Annotated[list[QueryFamilyEvidence], Field(min_length=1, max_length=200)],
    pool: PostgresPoolEvidence | None = None,
    p95_warn_ms: Annotated[int, Field(ge=1, le=10**9)] = 500,
    read_amplification_warn: Annotated[int, Field(ge=1, le=10**9)] = 100,
) -> AssuranceResult:
    """Use this when bounded query, index, locking, growth and pool metadata needs a performance-risk decision."""
    records = [item.model_dump(mode="json") for item in query_families]
    findings: list[dict[str, Any]] = []
    for item in records:
        amplification = int(item["rows_read"]) // max(1, int(item["rows_returned"]))
        if item["p95_ms"] >= p95_warn_ms:
            findings.append({"severity": "P1", "family": "POSTGRES_QUERY_P95_SLOW", "queryFamily": item["family"], "p95Ms": item["p95_ms"]})
        if amplification >= read_amplification_warn and item["rows_read"]:
            findings.append({"severity": "P1", "family": "POSTGRES_READ_AMPLIFICATION", "queryFamily": item["family"], "ratio": amplification})
        if item["sequential_scans"] > item["index_scans"] and item["calls"]:
            findings.append({"severity": "P2", "family": "POSTGRES_INDEX_COVERAGE_CANDIDATE", "queryFamily": item["family"]})
        if item["lock_wait_ms"] >= p95_warn_ms:
            findings.append({"severity": "P0", "family": "POSTGRES_LOCK_PRESSURE", "queryFamily": item["family"], "lockWaitMs": item["lock_wait_ms"]})
    pool_payload = pool.model_dump(mode="json") if pool else None
    if pool and pool.maximum:
        pool_ppm = _ppm(pool.active + pool.waiting, pool.maximum)
        if pool.waiting or pool_ppm >= 850_000:
            findings.append({"severity": "P0", "family": "POSTGRES_POOL_PRESSURE", "usedPpm": pool_ppm, "waiting": pool.waiting})
    ok = not any(item["severity"] == "P0" for item in findings)
    return _result(
        schema="sovereign.postgres-query-index-performance.v1",
        ok=ok,
        status="POSTGRES_PERFORMANCE_ACCEPTABLE" if ok else "POSTGRES_PERFORMANCE_BLOCKED",
        evidence={"queryFamilies": records, "pool": pool_payload, "thresholds": {"p95WarnMs": p95_warn_ms, "readAmplificationWarn": read_amplification_warn}},
        findings=findings,
        next_actions=["capture EXPLAIN metadata for the affected query family without row values", "test one minimal index or query change against the same workload evidence"],
        runtime_verified=False,
        truth_notice="Only supplied aggregate metadata is evaluated. SQL text, bind values and result rows are not required or returned.",
    )


def data_integrity_invariant_audit(
    invariants: Annotated[list[InvariantEvidence], Field(min_length=1, max_length=500)],
) -> AssuranceResult:
    """Use this when cross-table business invariants need an exact expected-versus-observed audit without data mutation."""
    records = [item.model_dump(mode="json") for item in invariants]
    findings = [
        {"severity": "P0", "family": "DATA_INTEGRITY_INVARIANT_BROKEN", "invariantId": item["invariant_id"], "scopeIdentity": item["scope_identity"], "expected": item["expected"], "observed": item["observed"], "revision": item["revision"]}
        for item in records
        if item["expected"] != item["observed"]
    ]
    ok = not findings
    return _result(
        schema="sovereign.data-integrity-invariant-audit.v1",
        ok=ok,
        status="DATA_INTEGRITY_VALID" if ok else "DATA_INTEGRITY_VIOLATIONS",
        evidence={"invariants": records, "checked": len(records), "violations": len(findings)},
        findings=findings,
        next_actions=["create a separate state-bound repair plan for each violated scope", "verify the same invariant after repair before clearing the incident"],
        runtime_verified=False,
        truth_notice="The tool compares supplied aggregate invariant values. It neither queries arbitrary rows nor repairs data.",
    )


def data_repair_plan_build(
    candidates: Annotated[list[RepairCandidate], Field(min_length=1, max_length=200)],
    max_rows_per_batch: Annotated[int, Field(ge=1, le=1_000_000)] = 1000,
) -> AssuranceResult:
    """Use this when inconsistent historical data needs an idempotent, bounded and separately confirmable repair plan."""
    records = [item.model_dump(mode="json") for item in candidates]
    plans: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for item in records:
        batches = (item["estimated_rows"] + max_rows_per_batch - 1) // max_rows_per_batch if item["estimated_rows"] else 0
        core = {
            "repairId": item["repair_id"],
            "target": item["target"],
            "predicate": item["predicate"],
            "desiredState": item["desired_state"],
            "preconditionHash": item["current_identity_hash"],
            "estimatedRows": item["estimated_rows"],
            "maxRowsPerBatch": max_rows_per_batch,
            "batches": batches,
            "idempotencyKey": _sha256({"repairId": item["repair_id"], "preconditionHash": item["current_identity_hash"], "desiredState": item["desired_state"]}),
            "reversible": item["reversible"],
        }
        core["confirmationSha256"] = _sha256(core)
        plans.append(core)
        if not item["reversible"]:
            findings.append({"severity": "P1", "family": "DATA_REPAIR_NOT_REVERSIBLE", "repairId": item["repair_id"]})
    return _result(
        schema="sovereign.data-repair-plan.v1",
        ok=True,
        status="DATA_REPAIR_PLAN_READY",
        evidence={"plans": plans, "automaticExecution": False},
        findings=findings,
        next_actions=["re-read the current precondition hash immediately before execution", "apply one bounded batch through a separately authorized mutation tool", "re-run the invariant audit after every batch"],
        runtime_verified=False,
        truth_notice="Plans are deterministic and state-bound but are never executed by this tool.",
    )


def vector_memory_consistency_assess(
    records: Annotated[list[VectorRecordEvidence], Field(min_length=1, max_length=1000)],
) -> AssuranceResult:
    """Use this when PostgreSQL source blocks, outbox state, vector hashes, duplicates and embedding-model versions must be reconciled."""
    payload = [item.model_dump(mode="json") for item in records]
    findings: list[dict[str, Any]] = []
    for item in payload:
        identity = f"{item['source_id']}:{item['block_id']}"
        if item["vector_count"] == 0:
            findings.append({"severity": "P0", "family": "VECTOR_MISSING", "identity": identity})
        if item["vector_count"] > 1 or item["duplicate_vector_ids"]:
            findings.append({"severity": "P0", "family": "VECTOR_DUPLICATE", "identity": identity, "count": item["vector_count"]})
        if item["vector_content_hash"] and item["vector_content_hash"] != item["source_content_hash"]:
            findings.append({"severity": "P0", "family": "VECTOR_CONTENT_HASH_STALE", "identity": identity})
        if item["embedding_model"] != item["expected_embedding_model"]:
            findings.append({"severity": "P1", "family": "VECTOR_EMBEDDING_MODEL_STALE", "identity": identity, "actual": item["embedding_model"], "expected": item["expected_embedding_model"]})
        if item["outbox_state"] in {"missing", "failed"}:
            findings.append({"severity": "P0", "family": "VECTOR_OUTBOX_NOT_DELIVERABLE", "identity": identity, "state": item["outbox_state"]})
    ok = not any(item["severity"] == "P0" for item in findings)
    return _result(
        schema="sovereign.vector-memory-consistency.v1",
        ok=ok,
        status="VECTOR_MEMORY_CONSISTENT" if ok else "VECTOR_MEMORY_DRIFT",
        evidence={"records": payload, "recordCount": len(payload)},
        findings=findings,
        next_actions=["re-enqueue only the exact stale or missing block identities", "delete duplicates by canonical content identity before reindexing", "verify source hash and model version after replay"],
        runtime_verified=False,
        truth_notice="This compares supplied source and vector metadata. It does not read vector values, create embeddings or mutate Milvus.",
    )


def memory_poisoning_provenance_guard(
    candidates: Annotated[list[LearningCandidateEvidence], Field(min_length=1, max_length=500)],
    accepted_source_kinds: Annotated[list[str], Field(min_length=1, max_length=32)],
    current_revision: OptionalRevision = "",
    now_epoch: Annotated[int, Field(ge=0, le=10**12)] = 0,
    minimum_test_evidence: Annotated[int, Field(ge=1, le=1000)] = 1,
    minimum_outcomes: Annotated[int, Field(ge=1, le=1_000_000)] = 1,
) -> AssuranceResult:
    """Use this when learning candidates need provenance, scope, expiry, revision and conflict checks before persistence."""
    current_time = now_epoch or int(time.time())
    accepted = set(accepted_source_kinds)
    payload = [item.model_dump(mode="json") for item in candidates]
    decisions: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for item in payload:
        reasons: list[str] = []
        if item["source_kind"] not in accepted:
            reasons.append("SOURCE_KIND_NOT_ACCEPTED")
        if current_revision and item["revision"] and item["revision"] != current_revision:
            reasons.append("REVISION_MISMATCH")
        if item["test_evidence_count"] < minimum_test_evidence:
            reasons.append("TEST_EVIDENCE_INSUFFICIENT")
        if item["outcome_count"] < minimum_outcomes:
            reasons.append("OUTCOME_COUNT_INSUFFICIENT")
        if item["expires_epoch"] and item["expires_epoch"] <= current_time:
            reasons.append("CANDIDATE_EXPIRED")
        if item["conflicts"]:
            reasons.append("KNOWLEDGE_CONFLICT_PRESENT")
        decision = "quarantine" if reasons else "eligible-for-owner-approval"
        decisions.append({"candidateId": item["candidate_id"], "decision": decision, "reasons": reasons, "scope": item["scope"]})
        if reasons:
            findings.append({"severity": "P0", "family": "LEARNING_CANDIDATE_QUARANTINED", "candidateId": item["candidate_id"], "reasons": reasons})
    ok = not findings
    return _result(
        schema="sovereign.memory-poisoning-provenance-guard.v1",
        ok=ok,
        status="LEARNING_CANDIDATES_ELIGIBLE" if ok else "LEARNING_CANDIDATES_QUARANTINED",
        evidence={"decisions": decisions, "currentRevision": current_revision or None, "nowEpoch": current_time},
        findings=findings,
        next_actions=["persist only after owner approval and exact content hash binding", "keep conflicting or under-evidenced candidates in quarantine"],
        runtime_verified=False,
        truth_notice="Eligibility is not persistence. This tool never writes a learning pattern or overrides an existing one.",
    )


def learning_pattern_lifecycle_preview(
    records: Annotated[list[PatternLifecycleRecord], Field(min_length=1, max_length=500)],
    action: Literal["activate", "restrict", "deprecate", "remove", "merge", "supersede"],
    target_ids: Annotated[list[str], Field(min_length=1, max_length=64)],
) -> AssuranceResult:
    """Use this when learning patterns need a versioned activation, replacement, merge, deprecation or removal preview."""
    by_id = {item.pattern_id: item.model_dump(mode="json") for item in records}
    missing = sorted(set(target_ids) - set(by_id))
    findings: list[dict[str, Any]] = []
    if missing:
        findings.append({"severity": "P0", "family": "PATTERN_LIFECYCLE_TARGET_MISSING", "patterns": missing})
    transitions: list[dict[str, Any]] = []
    target_state = {"activate": "active", "restrict": "restricted", "deprecate": "deprecated", "remove": "removed"}.get(action)
    for target in target_ids:
        record = by_id.get(target)
        if not record:
            continue
        if action in {"merge", "supersede"} and len(target_ids) < 2:
            findings.append({"severity": "P0", "family": "PATTERN_LIFECYCLE_MULTIPLE_TARGETS_REQUIRED", "action": action})
            break
        if action == "remove" and record["state"] not in {"deprecated", "restricted"}:
            findings.append({"severity": "P0", "family": "ACTIVE_PATTERN_REMOVAL_BLOCKED", "patternId": target})
        transitions.append({"patternId": target, "from": record["state"], "to": target_state or action, "currentVersion": record["version"], "nextVersion": record["version"] + 1})
    ok = not findings
    return _result(
        schema="sovereign.learning-pattern-lifecycle-preview.v1",
        ok=ok,
        status="PATTERN_LIFECYCLE_PREVIEW_READY" if ok else "PATTERN_LIFECYCLE_BLOCKED",
        evidence={"action": action, "transitions": transitions, "confirmationSha256": _sha256({"action": action, "transitions": transitions}), "mutationPlanned": False},
        findings=findings,
        next_actions=["resolve active callers and conflicts before deprecation", "persist lifecycle changes only through the owner-approved learning path"],
        runtime_verified=False,
        truth_notice="This is a lifecycle preview. No learning record is activated, merged, replaced or removed.",
    )


def data_retention_privacy_audit(rules: Annotated[list[RetentionRule], Field(min_length=1, max_length=200)]) -> AssuranceResult:
    """Use this when retention, deletion, pseudonymization, export and tenant-separation controls need a bounded privacy audit."""
    payload = [item.model_dump(mode="json") for item in rules]
    findings: list[dict[str, Any]] = []
    for item in payload:
        if item["retention_days"] > 0 and not item["deletion_verified"]:
            findings.append({"severity": "P0", "family": "RETENTION_DELETION_NOT_VERIFIED", "dataset": item["dataset"]})
        if item["pseudonymization"] == "required":
            findings.append({"severity": "P0", "family": "PSEUDONYMIZATION_REQUIRED_NOT_VERIFIED", "dataset": item["dataset"]})
        if not item["export_supported"]:
            findings.append({"severity": "P1", "family": "DATA_EXPORT_NOT_SUPPORTED", "dataset": item["dataset"]})
        if not item["tenant_key_present"]:
            findings.append({"severity": "P0", "family": "RETENTION_TENANT_KEY_MISSING", "dataset": item["dataset"]})
    ok = not any(item["severity"] == "P0" for item in findings)
    return _result(
        schema="sovereign.data-retention-privacy-audit.v1",
        ok=ok,
        status="RETENTION_PRIVACY_READY" if ok else "RETENTION_PRIVACY_GAPS",
        evidence={"rules": payload},
        findings=findings,
        next_actions=["implement deletion canaries before claiming retention enforcement", "bind exports and deletions to tenant identity and audit evidence"],
        runtime_verified=False,
        truth_notice="Policy metadata is audited; no user data is read, exported, pseudonymized or deleted.",
    )


def multi_tenant_isolation_verify(
    tests: Annotated[list[IsolationTestResult], Field(min_length=1, max_length=500)],
    required_surfaces: Annotated[list[str], Field(max_length=16)] = ["user", "project", "repository", "credit", "memory", "agent-run"],
) -> AssuranceResult:
    """Use this when negative tests must prove user, project, repository, credit, memory and agent-run separation."""
    payload = [item.model_dump(mode="json") for item in tests]
    covered = {item["surface"] for item in payload}
    findings: list[dict[str, Any]] = []
    for item in payload:
        if not item["negative_access_denied"]:
            findings.append({"severity": "P0", "family": "CROSS_TENANT_ACCESS_NOT_DENIED", "surface": item["surface"], "testId": item["test_id"]})
        if not item["cross_tenant_identifier_redacted"]:
            findings.append({"severity": "P0", "family": "CROSS_TENANT_IDENTIFIER_LEAK", "surface": item["surface"], "testId": item["test_id"]})
        if item["surface"] == "credit" and not item["budget_isolated"]:
            findings.append({"severity": "P0", "family": "CROSS_TENANT_BUDGET_NOT_ISOLATED", "testId": item["test_id"]})
    missing = sorted(set(required_surfaces) - covered)
    if missing:
        findings.append({"severity": "P0", "family": "TENANT_ISOLATION_SURFACE_UNTESTED", "surfaces": missing})
    ok = not findings
    return _result(
        schema="sovereign.multi-tenant-isolation-verification.v1",
        ok=ok,
        status="MULTI_TENANT_ISOLATION_VERIFIED" if ok else "MULTI_TENANT_ISOLATION_BLOCKED",
        evidence={"tests": payload, "coveredSurfaces": sorted(covered), "missingSurfaces": missing},
        findings=findings,
        next_actions=["block multi-tenant release until every required negative test passes", "repeat tests against the exact deployed revision"],
        runtime_verified=False,
        truth_notice="The verifier evaluates supplied negative-test evidence; it does not impersonate users or access tenant data.",
    )


def mcp_schema_compatibility_audit(
    published: SchemaSurface,
    repository: SchemaSurface,
    backend_adapter: SchemaSurface,
    agent_expected: SchemaSurface,
) -> AssuranceResult:
    """Use this when published MCP, repository, backend-adapter and agent-expected tool schemas must remain compatible."""
    surfaces = {
        "published": published.model_dump(mode="json"),
        "repository": repository.model_dump(mode="json"),
        "backendAdapter": backend_adapter.model_dump(mode="json"),
        "agentExpected": agent_expected.model_dump(mode="json"),
    }
    all_names = sorted(set().union(*(set(surface["tools"]) for surface in surfaces.values())))
    findings: list[dict[str, Any]] = []
    matrix: list[dict[str, Any]] = []
    for name in all_names:
        hashes = {surface_name: _sha256(surface["tools"][name]) if name in surface["tools"] else "" for surface_name, surface in surfaces.items()}
        missing = sorted(surface_name for surface_name, digest in hashes.items() if not digest)
        distinct = sorted(set(digest for digest in hashes.values() if digest))
        compatible = not missing and len(distinct) == 1
        matrix.append({"tool": name, "compatible": compatible, "hashes": hashes, "missingSurfaces": missing})
        if missing:
            findings.append({"severity": "P0", "family": "MCP_SCHEMA_SURFACE_MISSING_TOOL", "tool": name, "surfaces": missing})
        elif len(distinct) > 1:
            findings.append({"severity": "P0", "family": "MCP_SCHEMA_INCOMPATIBLE", "tool": name, "hashes": hashes})
    ok = not findings
    return _result(
        schema="sovereign.mcp-schema-compatibility-audit.v1",
        ok=ok,
        status="MCP_SCHEMAS_COMPATIBLE" if ok else "MCP_SCHEMA_DRIFT",
        evidence={"versions": {name: value["version"] for name, value in surfaces.items()}, "matrix": matrix},
        findings=findings,
        next_actions=["preserve backward-compatible aliases or update every surface atomically", "refresh the ChatGPT MCP snapshot only after compatibility is green"],
        runtime_verified=False,
        truth_notice="Schemas are compared canonically; no tool is invoked and no published connector is changed.",
    )


def mcp_protocol_conformance_fuzz_plan(
    max_payload_bytes: Annotated[int, Field(ge=1024, le=10_000_000)] = 1_000_000,
    timeout_seconds: Annotated[int, Field(ge=1, le=300)] = 30,
) -> AssuranceResult:
    """Use this when MCP initialize, listing, invalid arguments, timeouts, payload limits and disconnects need a reproducible fuzz matrix."""
    tool_count = 0
    if _MCP is not None:
        tool_count = len(list(_MCP._tool_manager.list_tools()))
    cases = [
        {"case": "initialize-valid", "input": "valid protocol version and capabilities", "expected": "initialized"},
        {"case": "initialize-unsupported-version", "input": "unsupported protocol version", "expected": "structured protocol error"},
        {"case": "tools-list", "input": "list tools after initialization", "expected": f"bounded list containing {tool_count} current tools"},
        {"case": "tool-invalid-arguments", "input": "unknown and type-invalid fields", "expected": "schema validation error without tool execution"},
        {"case": "tool-timeout", "input": f"bounded operation exceeding {timeout_seconds}s", "expected": "structured timeout and no duplicate execution"},
        {"case": "payload-limit-minus-one", "inputBytes": max_payload_bytes - 1, "expected": "accepted when schema-valid"},
        {"case": "payload-limit-plus-one", "inputBytes": max_payload_bytes + 1, "expected": "rejected before execution"},
        {"case": "disconnect-mid-request", "input": "client disconnect after request acceptance", "expected": "idempotency identity preserves one execution"},
        {"case": "malformed-json", "input": "invalid UTF-8 or JSON", "expected": "bounded parse error"},
    ]
    return _result(
        schema="sovereign.mcp-protocol-conformance-fuzz-plan.v1",
        ok=True,
        status="MCP_FUZZ_MATRIX_READY",
        evidence={"toolCount": tool_count, "cases": cases, "matrixSha256": _sha256(cases), "executed": False},
        findings=[],
        next_actions=["run this matrix in CI against the immutable image and a real MCP initialize handshake", "persist per-case request, response class and side-effect evidence"],
        runtime_verified=True,
        truth_notice="The live registry count is read, but the network fuzz cases are planned rather than executed by this tool.",
    )


def tool_permission_minimize(
    requirements: Annotated[list[ToolPermissionRequirement], Field(min_length=1, max_length=500)],
) -> AssuranceResult:
    """Use this when each tool's filesystem, database, network and host permissions must be reduced to observed requirements."""
    payload = [item.model_dump(mode="json") for item in requirements]
    findings: list[dict[str, Any]] = []
    recommendations: list[dict[str, Any]] = []
    for item in payload:
        declared = set(item["declared"])
        required = set(item["required"]) | set(item["observed"])
        excess = sorted(declared - required)
        missing = sorted(required - declared)
        recommendations.append({"tool": item["tool_name"], "remove": excess, "add": missing, "minimal": sorted(required)})
        if missing:
            findings.append({"severity": "P0", "family": "TOOL_REQUIRED_PERMISSION_MISSING", "tool": item["tool_name"], "permissions": missing})
        if excess:
            findings.append({"severity": "P1", "family": "TOOL_PERMISSION_OVERBROAD", "tool": item["tool_name"], "permissions": excess})
    ok = not any(item["severity"] == "P0" for item in findings)
    return _result(
        schema="sovereign.tool-permission-minimization.v1",
        ok=ok,
        status="TOOL_PERMISSIONS_MINIMIZED" if not findings else "TOOL_PERMISSION_CHANGES_REQUIRED",
        evidence={"recommendations": recommendations},
        findings=findings,
        next_actions=["apply permission reductions in the deployment policy, not inside tool code", "rerun regression missions after every permission change"],
        runtime_verified=False,
        truth_notice="This computes a least-privilege proposal from supplied declarations and observations. It changes no permissions.",
    )


def dynamic_execution_containment_audit(
    workspace_id: WorkspaceId,
    roots: Annotated[list[str], Field(max_length=16)] = ["backend", "scripts/sovereign-backend", "src", "tools/sovereign-chatgpt-mcp"],
    max_findings: Annotated[int, Field(ge=1, le=1000)] = 300,
) -> AssuranceResult:
    """Use this when eval, dynamic imports, shell execution, generated code and sandbox boundaries must be classified by active path."""
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
            if not path.is_file() or path.suffix.lower() not in {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs"}:
                continue
            rel = str(path.relative_to(repo))
            if "node_modules" in rel or path.stat().st_size > 2_000_000:
                continue
            scanned += 1
            path_class = "test" if any(marker in rel.casefold() for marker in ("/tests/", ".test.", ".spec.", "/fixtures/")) else "production-candidate"
            for line_number, line in enumerate(path.read_text("utf-8", errors="replace").splitlines(), 1):
                for family, pattern in _DYNAMIC_PATTERNS:
                    if pattern.search(line):
                        severity = "P2" if path_class == "test" else "P0"
                        findings.append({"severity": severity, "family": family, "path": rel, "line": line_number, "pathClass": path_class, "status": "CANDIDATE_REQUIRES_CALLER_AND_SANDBOX_REVIEW"})
                        break
                if len(findings) >= max_findings:
                    break
    ok = not any(item["severity"] == "P0" for item in findings)
    return _result(
        schema="sovereign.dynamic-execution-containment-audit.v1",
        ok=ok,
        status="DYNAMIC_EXECUTION_CONTAINED" if ok else "DYNAMIC_EXECUTION_REVIEW_REQUIRED",
        evidence={"filesScanned": scanned, "findingCount": len(findings), "truncated": len(findings) >= max_findings},
        findings=findings,
        next_actions=["prove active callers and isolation level before classifying a production candidate as safe", "replace uncontained dynamic execution with allowlisted deterministic adapters"],
        runtime_verified=False,
        truth_notice="Static matches are candidates, not proof of execution. Runtime caller, sandbox and deployment evidence remain required.",
    )


def skill_capability_coverage_map(
    requirements: Annotated[list[CapabilityRequirement], Field(min_length=1, max_length=200)],
) -> AssuranceResult:
    """Use this when architecture tasks must be mapped to existing registered tools before creating another skill."""
    catalog: list[dict[str, Any]] = []
    if _MCP is not None:
        for tool in _MCP._tool_manager.list_tools():
            text = f"{getattr(tool, 'name', '')} {getattr(tool, 'description', '')}".casefold()
            tokens = sorted(set(re.findall(r"[a-z0-9][a-z0-9_-]{1,63}", text)))
            catalog.append({"name": str(getattr(tool, "name", "")), "tokens": tokens})
    mappings: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for requirement in requirements:
        required = set(item.casefold() for item in requirement.required_capabilities)
        ranked = []
        for tool in catalog:
            matched = sorted(required & set(tool["tokens"]))
            if matched:
                ranked.append({"tool": tool["name"], "matched": matched, "score": len(matched)})
        ranked.sort(key=lambda item: (-item["score"], item["tool"]))
        covered = set(value for item in ranked for value in item["matched"])
        missing = sorted(required - covered)
        mappings.append({"taskId": requirement.task_id, "tools": ranked[:12], "missingCapabilities": missing})
        if missing:
            findings.append({"severity": "P1", "family": "SKILL_CAPABILITY_GAP", "taskId": requirement.task_id, "missingCapabilities": missing})
    ok = not findings
    return _result(
        schema="sovereign.skill-capability-coverage-map.v1",
        ok=ok,
        status="SKILL_COVERAGE_COMPLETE" if ok else "SKILL_COVERAGE_GAPS",
        evidence={"registeredToolCount": len(catalog), "mappings": mappings},
        findings=findings,
        next_actions=["extend the highest-overlap existing skill before creating a new one", "create a new skill only for capabilities missing from every registered tool"],
        runtime_verified=True,
        truth_notice="Coverage is inferred from live registered names and descriptions; execution suitability still requires the exact tool contract.",
    )


def skill_lifecycle_deprecation_preview(
    records: Annotated[list[SkillLifecycleRecord], Field(min_length=1, max_length=500)],
    transitions: Annotated[list[SkillTransitionRequest], Field(min_length=1, max_length=100)],
) -> AssuranceResult:
    """Use this when skills or MCP tools need controlled experimental, active, restricted, deprecated and removed transitions."""
    by_name = {item.name: item.model_dump(mode="json") for item in records}
    allowed = {
        "experimental": {"active", "restricted", "removed"},
        "active": {"restricted", "deprecated"},
        "restricted": {"active", "deprecated", "removed"},
        "deprecated": {"removed", "restricted"},
        "removed": set(),
    }
    previews: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for request in transitions:
        current = by_name.get(request.name)
        if not current:
            findings.append({"severity": "P0", "family": "SKILL_LIFECYCLE_TARGET_MISSING", "skill": request.name})
            continue
        if request.target_state not in allowed[current["state"]]:
            findings.append({"severity": "P0", "family": "SKILL_LIFECYCLE_TRANSITION_INVALID", "skill": request.name, "from": current["state"], "to": request.target_state})
        if request.target_state in {"deprecated", "removed"} and current["active_callers"] and not current["replacement"]:
            findings.append({"severity": "P0", "family": "SKILL_DEPRECATION_WITH_ACTIVE_CALLERS_AND_NO_REPLACEMENT", "skill": request.name, "activeCallers": current["active_callers"]})
        previews.append({"skill": request.name, "from": current["state"], "to": request.target_state, "replacement": current["replacement"], "activeCallers": current["active_callers"]})
    ok = not findings
    return _result(
        schema="sovereign.skill-lifecycle-deprecation-preview.v1",
        ok=ok,
        status="SKILL_LIFECYCLE_PREVIEW_READY" if ok else "SKILL_LIFECYCLE_BLOCKED",
        evidence={"transitions": previews, "confirmationSha256": _sha256(previews), "mutationPerformed": False},
        findings=findings,
        next_actions=["migrate active callers before deprecation or removal", "verify the replacement skill regression benchmark first"],
        runtime_verified=False,
        truth_notice="No skill or MCP tool state is changed by this preview.",
    )


def skill_regression_benchmark(
    missions: Annotated[list[RegressionMission], Field(min_length=1, max_length=500)],
) -> AssuranceResult:
    """Use this when safe missions, expected tool calls, allowed effects and proof conditions must survive an MCP update."""
    payload = [item.model_dump(mode="json") for item in missions]
    findings: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for item in payload:
        missing_tools = sorted(set(item["expected_tools"]) - set(item["actual_tools"]))
        unexpected_tools = sorted(set(item["actual_tools"]) - set(item["expected_tools"]))
        forbidden_effects = sorted(set(item["observed_effects"]) - set(item["allowed_effects"]))
        missing_evidence = sorted(set(item["required_evidence"]) - set(item["observed_evidence"]))
        passed = not missing_tools and not unexpected_tools and not forbidden_effects and not missing_evidence
        results.append({"missionId": item["mission_id"], "passed": passed, "missingTools": missing_tools, "unexpectedTools": unexpected_tools, "forbiddenEffects": forbidden_effects, "missingEvidence": missing_evidence})
        if not passed:
            findings.append({"severity": "P0", "family": "SKILL_REGRESSION_MISSION_FAILED", "missionId": item["mission_id"]})
    ok = not findings
    return _result(
        schema="sovereign.skill-regression-benchmark.v1",
        ok=ok,
        status="SKILL_REGRESSION_GREEN" if ok else "SKILL_REGRESSION_FAILED",
        evidence={"results": results, "missionCount": len(results)},
        findings=findings,
        next_actions=["block MCP self-update when required missions regress", "record the exact image digest and registry hash for every benchmark run"],
        runtime_verified=False,
        truth_notice="The benchmark evaluates supplied mission traces. It does not execute tools or create side effects.",
    )


def tool_idempotency_verify(
    observations: Annotated[list[IdempotencyObservation], Field(min_length=1, max_length=500)],
) -> AssuranceResult:
    """Use this when repeated identical calls must prove they did not duplicate PRs, migrations, payments, deployments or learning patterns."""
    payload = [item.model_dump(mode="json") for item in observations]
    findings: list[dict[str, Any]] = []
    for item in payload:
        if item["invocation_count"] > 1 and item["unique_side_effect_ids"] > 1:
            findings.append({"severity": "P0", "family": "TOOL_IDEMPOTENCY_SIDE_EFFECT_DUPLICATION", "tool": item["tool_name"], "sideEffectIds": item["unique_side_effect_ids"]})
        if len(set(item["terminal_result_hashes"])) > 1:
            findings.append({"severity": "P1", "family": "TOOL_IDEMPOTENCY_RESULT_DIVERGENCE", "tool": item["tool_name"]})
    ok = not any(item["severity"] == "P0" for item in findings)
    return _result(
        schema="sovereign.tool-idempotency-verification.v1",
        ok=ok,
        status="TOOL_IDEMPOTENCY_VERIFIED" if ok else "TOOL_IDEMPOTENCY_BROKEN",
        evidence={"observations": payload},
        findings=findings,
        next_actions=["bind retries to one request hash and persisted side-effect identity", "query the original operation status instead of resubmitting after timeouts"],
        runtime_verified=False,
        truth_notice="This compares supplied invocation identities and outcomes; it never repeats the operation itself.",
    )


def owner_approval_policy_evaluate(
    rules: Annotated[list[ApprovalRule], Field(min_length=1, max_length=200)],
    context: ApprovalContext,
    now_epoch: Annotated[int, Field(ge=0, le=10**12)] = 0,
) -> AssuranceResult:
    """Use this when owner approval requirements, TTL, revision binding and payload binding need one centralized decision."""
    current_time = now_epoch or int(time.time())
    matches = [rule for rule in rules if fnmatch(context.action, rule.action_pattern)]
    findings: list[dict[str, Any]] = []
    if not matches:
        findings.append({"severity": "P0", "family": "OWNER_APPROVAL_POLICY_RULE_MISSING", "action": context.action})
        selected = None
    else:
        matches.sort(key=lambda item: (-len(item.action_pattern), item.action_pattern))
        selected = matches[0]
    decision = "blocked"
    if selected:
        if not selected.approval_required:
            decision = "allowed-without-approval"
        elif context.approval_status != "approved":
            findings.append({"severity": "P0", "family": "OWNER_APPROVAL_NOT_APPROVED", "status": context.approval_status})
        elif selected.ttl_seconds and current_time - context.approval_created_epoch > selected.ttl_seconds:
            findings.append({"severity": "P0", "family": "OWNER_APPROVAL_EXPIRED"})
        elif selected.bind_revision and context.revision != context.approved_revision:
            findings.append({"severity": "P0", "family": "OWNER_APPROVAL_REVISION_MISMATCH"})
        elif selected.bind_payload_hash and context.payload_hash != context.approved_payload_hash:
            findings.append({"severity": "P0", "family": "OWNER_APPROVAL_PAYLOAD_MISMATCH"})
        else:
            decision = "allowed-with-bound-approval"
    ok = decision != "blocked" and not findings
    return _result(
        schema="sovereign.owner-approval-policy-evaluation.v1",
        ok=ok,
        status="OWNER_APPROVAL_POLICY_ALLOWED" if ok else "OWNER_APPROVAL_POLICY_BLOCKED",
        evidence={"action": context.action, "decision": decision, "selectedRule": selected.model_dump(mode="json") if selected else None, "nowEpoch": current_time},
        findings=findings,
        next_actions=["obtain a fresh protected owner approval bound to the exact revision and payload when blocked"],
        runtime_verified=False,
        truth_notice="This policy engine evaluates approval metadata only. It never reads the protected owner value or grants approval itself.",
    )


def secret_lifecycle_rotation_assess(
    references: Annotated[list[SecretReference], Field(min_length=1, max_length=500)],
    now_epoch: Annotated[int, Field(ge=0, le=10**12)] = 0,
    canary_max_age_days: Annotated[int, Field(ge=1, le=3650)] = 30,
) -> AssuranceResult:
    """Use this when secret references, owners, age, rotation interval and last successful canary need lifecycle assessment without raw values."""
    current_time = now_epoch or int(time.time())
    payload = [item.model_dump(mode="json") for item in references]
    findings: list[dict[str, Any]] = []
    assessments: list[dict[str, Any]] = []
    for item in payload:
        baseline = item["rotated_epoch"] or item["created_epoch"]
        age_days = max(0, (current_time - baseline) // 86400)
        canary_age_days = max(0, (current_time - item["last_canary_epoch"]) // 86400) if item["last_canary_epoch"] else None
        due = age_days >= item["rotation_interval_days"]
        canary_stale = not item["last_canary_ok"] or canary_age_days is None or canary_age_days > canary_max_age_days
        assessments.append({"secretId": item["secret_id"], "owner": item["owner"], "targetSystem": item["target_system"], "ageDays": age_days, "rotationDue": due, "canaryAgeDays": canary_age_days, "canaryStale": canary_stale})
        if due:
            findings.append({"severity": "P0", "family": "SECRET_ROTATION_OVERDUE", "secretId": item["secret_id"], "ageDays": age_days})
        if canary_stale:
            findings.append({"severity": "P1", "family": "SECRET_CANARY_STALE_OR_FAILED", "secretId": item["secret_id"]})
    ok = not any(item["severity"] == "P0" for item in findings)
    return _result(
        schema="sovereign.secret-lifecycle-rotation.v1",
        ok=ok,
        status="SECRET_LIFECYCLE_HEALTHY" if ok else "SECRET_ROTATION_REQUIRED",
        evidence={"assessments": assessments, "rawValuesRead": False},
        findings=findings,
        next_actions=["rotate through the protected owner or secret-store flow", "run a target-specific canary before revoking the previous version"],
        runtime_verified=False,
        truth_notice="Only metadata references are accepted. Secret values are never read or returned.",
    )


def secret_literal_triage(
    workspace_id: WorkspaceId,
    roots: Annotated[list[str], Field(max_length=16)] = ["backend", "scripts", "src", "tools", ".github"],
    max_findings: Annotated[int, Field(ge=1, le=1000)] = 300,
) -> AssuranceResult:
    """Use this when secret-shaped literals must be separated into tests, placeholders, fingerprints and rotation candidates."""
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
            if not path.is_file() or path.stat().st_size > 2_000_000:
                continue
            if path.suffix.lower() not in {".py", ".ts", ".tsx", ".js", ".json", ".yml", ".yaml", ".sh", ".env", ".md"}:
                continue
            rel = str(path.relative_to(repo))
            scanned += 1
            lower_path = rel.casefold()
            for line_number, line in enumerate(path.read_text("utf-8", errors="replace").splitlines(), 1):
                match = _SECRET_LITERAL_RE.search(line)
                if not match:
                    continue
                lower_line = line.casefold()
                if any(marker in lower_path for marker in ("/tests/", ".test.", ".spec.", "/fixtures/")) or any(marker in lower_line for marker in ("example", "dummy", "fake", "placeholder", "test-only", "invalid")):
                    classification = "TEST_OR_PLACEHOLDER"
                    severity = "P3"
                elif re.search(r"sha256:[0-9a-f]{64}|[0-9a-f]{40,64}", line, re.I):
                    classification = "FINGERPRINT_OR_DIGEST"
                    severity = "P3"
                else:
                    classification = "ROTATION_CANDIDATE"
                    severity = "P0"
                findings.append({"severity": severity, "family": "SECRET_LITERAL_TRIAGE", "path": rel, "line": line_number, "classification": classification, "literalSha256": hashlib.sha256(match.group(0).encode("utf-8")).hexdigest(), "literalReturned": False})
                if len(findings) >= max_findings:
                    break
    rotation_candidates = sum(1 for item in findings if item["classification"] == "ROTATION_CANDIDATE")
    ok = rotation_candidates == 0
    return _result(
        schema="sovereign.secret-literal-triage.v1",
        ok=ok,
        status="SECRET_LITERAL_TRIAGE_CLEAR" if ok else "SECRET_ROTATION_CANDIDATES_FOUND",
        evidence={"filesScanned": scanned, "findingCount": len(findings), "rotationCandidates": rotation_candidates, "truncated": len(findings) >= max_findings},
        findings=findings,
        next_actions=["confirm real exposure through the secret owner without copying the value", "rotate confirmed credentials and preserve only hash evidence"],
        runtime_verified=False,
        truth_notice="Matched literal contents are never returned; only path, line, classification and literal hash are exposed.",
    )


def sbom_provenance_image_signing_verify(evidence: SupplyChainEvidence) -> AssuranceResult:
    """Use this when SBOM, dependency provenance, image signature, build attestation and revision labels must prove one immutable image."""
    payload = evidence.model_dump(mode="json")
    findings: list[dict[str, Any]] = []
    if not payload["revision"] or payload["revision"] != payload["revision_label"]:
        findings.append({"severity": "P0", "family": "IMAGE_REVISION_LABEL_MISMATCH"})
    if not payload["image_digest"]:
        findings.append({"severity": "P0", "family": "IMAGE_IMMUTABLE_DIGEST_MISSING"})
    if not payload["sbom_digest"]:
        findings.append({"severity": "P0", "family": "SBOM_DIGEST_MISSING"})
    if not payload["provenance_digest"]:
        findings.append({"severity": "P0", "family": "BUILD_PROVENANCE_MISSING"})
    if not payload["signature_verified"]:
        findings.append({"severity": "P0", "family": "IMAGE_SIGNATURE_NOT_VERIFIED"})
    if not payload["attestation_verified"]:
        findings.append({"severity": "P0", "family": "BUILD_ATTESTATION_NOT_VERIFIED"})
    if not payload["dependencies_pinned"]:
        findings.append({"severity": "P1", "family": "DEPENDENCIES_NOT_FULLY_PINNED"})
    ok = not any(item["severity"] == "P0" for item in findings)
    return _result(
        schema="sovereign.sbom-provenance-image-signing.v1",
        ok=ok,
        status="SUPPLY_CHAIN_VERIFIED" if ok else "SUPPLY_CHAIN_EVIDENCE_INCOMPLETE",
        evidence=payload,
        findings=findings,
        next_actions=["publish and verify SBOM, provenance and signature for the exact image digest", "reject mutable tags as deployment evidence"],
        runtime_verified=False,
        truth_notice="This validates supplied verification results and digests. It does not sign an image or contact a registry.",
    )


def dependency_vulnerability_remediation_plan(
    vulnerabilities: Annotated[list[VulnerabilityEvidence], Field(min_length=1, max_length=1000)],
) -> AssuranceResult:
    """Use this when CVEs must be ranked by reachable production paths and converted into minimal upgrade plans."""
    payload = [item.model_dump(mode="json") for item in vulnerabilities]
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}
    plans: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for item in sorted(payload, key=lambda value: (not value["reachable_production_path"], severity_rank[value["severity"]], value["package"])):
        priority = "P0" if item["reachable_production_path"] and item["severity"] in {"critical", "high"} else "P1" if item["reachable_production_path"] else "P2"
        action = "upgrade-to-fixed-version" if item["fixed_version"] else "contain-or-replace-no-fixed-version"
        plans.append({"vulnerabilityId": item["vulnerability_id"], "package": item["package"], "priority": priority, "action": action, "targetVersion": item["fixed_version"] or None, "breakingUpgrade": item["breaking_upgrade"], "requiredGates": ["dependency lock validation", "targeted tests", "build", "reachable-path regression"]})
        if priority == "P0":
            findings.append({"severity": "P0", "family": "REACHABLE_HIGH_SEVERITY_VULNERABILITY", "vulnerabilityId": item["vulnerability_id"], "package": item["package"]})
    ok = not any(item["severity"] == "P0" for item in findings)
    return _result(
        schema="sovereign.dependency-vulnerability-remediation-plan.v1",
        ok=ok,
        status="VULNERABILITY_PLAN_READY" if ok else "REACHABLE_VULNERABILITIES_BLOCK_RELEASE",
        evidence={"plans": plans},
        findings=findings,
        next_actions=["upgrade only reachable vulnerable paths first", "avoid unrelated mass upgrades in the same repair", "verify lockfile, build and focused regressions in GitHub Actions"],
        runtime_verified=False,
        truth_notice="Reachability and vulnerability metadata are supplied evidence. No package installation or upgrade is executed locally.",
    )


def authentication_chaos_negative_test_assess(
    tests: Annotated[list[AuthNegativeTest], Field(min_length=1, max_length=500)],
    required_cases: Annotated[list[str], Field(max_length=16)] = ["oauth-state", "pkce", "passkey", "session-expiry", "step-up", "replay", "wrong-audience", "revoked-token", "parallel-access"],
) -> AssuranceResult:
    """Use this when OAuth, PKCE, passkey, session, step-up, replay, audience, revocation and concurrency negative tests need one release gate."""
    payload = [item.model_dump(mode="json") for item in tests]
    covered = {item["case"] for item in payload}
    findings: list[dict[str, Any]] = []
    for item in payload:
        if not item["denied_as_expected"]:
            findings.append({"severity": "P0", "family": "AUTH_NEGATIVE_TEST_NOT_DENIED", "case": item["case"], "testId": item["test_id"]})
        if not item["state_unchanged"]:
            findings.append({"severity": "P0", "family": "AUTH_NEGATIVE_TEST_MUTATED_STATE", "case": item["case"], "testId": item["test_id"]})
    missing = sorted(set(required_cases) - covered)
    if missing:
        findings.append({"severity": "P0", "family": "AUTH_NEGATIVE_CASE_UNTESTED", "cases": missing})
    ok = not findings
    return _result(
        schema="sovereign.authentication-chaos-negative-test.v1",
        ok=ok,
        status="AUTH_NEGATIVE_TESTS_GREEN" if ok else "AUTH_NEGATIVE_TESTS_BLOCKED",
        evidence={"tests": payload, "coveredCases": sorted(covered), "missingCases": missing},
        findings=findings,
        next_actions=["block release until every required negative case denies access without state mutation", "repeat against the exact deployed revision and configured identity provider"],
        runtime_verified=False,
        truth_notice="This assesses supplied negative-test evidence. It does not generate tokens, replay sessions or contact an identity provider.",
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
        operational_assurance_skill_inventory,
        outbox_queue_liveness_assess,
        scheduled_maintenance_coordinate,
        runtime_topology_change_audit,
        postgres_query_index_performance_assess,
        data_integrity_invariant_audit,
        data_repair_plan_build,
        vector_memory_consistency_assess,
        memory_poisoning_provenance_guard,
        learning_pattern_lifecycle_preview,
        data_retention_privacy_audit,
        multi_tenant_isolation_verify,
        mcp_schema_compatibility_audit,
        mcp_protocol_conformance_fuzz_plan,
        tool_permission_minimize,
        dynamic_execution_containment_audit,
        skill_capability_coverage_map,
        skill_lifecycle_deprecation_preview,
        skill_regression_benchmark,
        tool_idempotency_verify,
        owner_approval_policy_evaluate,
        secret_lifecycle_rotation_assess,
        secret_literal_triage,
        sbom_provenance_image_signing_verify,
        dependency_vulnerability_remediation_plan,
        authentication_chaos_negative_test_assess,
    )
    network_tools = (vps_capacity_resource_pressure_assess,)
    ephemeral_tools = (runtime_dependency_health_matrix,)
    for tool in local_tools:
        mcp.tool(annotations=LOCAL_READ_ONLY)(tool)
    for tool in network_tools:
        mcp.tool(annotations=NETWORK_READ_ONLY)(tool)
    for tool in ephemeral_tools:
        mcp.tool(annotations=EPHEMERAL_CANARY)(tool)
    _REGISTERED = True
