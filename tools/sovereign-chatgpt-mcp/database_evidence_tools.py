from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unicodedata
from collections import Counter
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any, Final, Literal

from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, field_validator


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
NETWORK_READ = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)
SAFE_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_ZERO_SHA256: Final[str] = "0" * 64
_MAX_TRACKED_FILES: Final[int] = 30_000
_MAX_TEXT_BYTES: Final[int] = 1_000_000
_MAX_SURFACES: Final[int] = 240
_TEXT_SUFFIXES: Final[frozenset[str]] = frozenset({
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".sql", ".json", ".toml", ".yml", ".yaml", ".md",
})
_SKIP_PREFIXES: Final[tuple[str, ...]] = (
    ".git/", "node_modules/", "vendor/", "dist/", "build/", "coverage/",
    ".venv/", "venv/", "__pycache__/", "android/app/build/", "test-results/",
)
_SECRET_KEY_MARKERS: Final[tuple[str, ...]] = (
    "password", "passwd", "secret", "token", "authorization", "api_key",
    "apikey", "private_key", "client_secret", "cookie",
)
_SECRET_SAFE_BOOLEAN_KEYS: Final[frozenset[str]] = frozenset({
    "secretvaluesreturned",
    "secret_values_returned",
    "secretvaluesexposed",
    "secret_values_exposed",
    "secretsexposed",
    "protectedvaluesreturned",
    "sensitivevaluesincluded",
})

_RUNTIME: Any = None
_DATABASE: Any = None
_BROKER: Any = None
_REGISTERED = False


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StrictToolOutput(StrictModel):
    schemaVersion: str
    ok: bool
    status: str
    failureFamily: str | None
    blocker: str | None
    mutationPerformed: bool
    nextAction: str | None
    evidence: dict[str, Any]
    data: dict[str, Any]
    secretValuesReturned: bool


class ReceiptHeader(StrictModel):
    algorithm: Literal["sha256"] = "sha256"
    canonicalization: Literal["utf8-nfc-json-sorted-no-floats-v1"] = (
        "utf8-nfc-json-sorted-no-floats-v1"
    )
    hash: str

    @field_validator("hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        normalized = str(value).strip().lower()
        if not _SHA64.fullmatch(normalized):
            raise ValueError("hash must be a 64-character lowercase SHA-256")
        return normalized


class ReceiptBody(StrictModel):
    schema_version: Literal["sovereign.db-evidence-receipt.v1"] = (
        "sovereign.db-evidence-receipt.v1"
    )
    sequence: int = Field(ge=0, le=1_000_000_000)
    revision: str
    producer: Literal["sovottt-mcp"] = "sovottt-mcp"
    operation: Literal[
        "postgres_canary",
        "postgres_schema_inventory",
        "postgres_schema_contract_inventory",
        "vector_database_canary",
        "postgres_migration_preview",
    ]
    operation_identity: str = Field(min_length=1, max_length=300)
    input_sha256: str
    output_sha256: str
    outcome: Literal["success", "failure", "blocked"]
    gate_result: Literal["PASS", "FAIL", "BLOCKED"]
    mutation_performed: bool
    observed_effect: Literal["read", "ephemeral-write", "none"]
    previous_receipt_sha256: str

    @field_validator("revision")
    @classmethod
    def validate_revision(cls, value: str) -> str:
        normalized = str(value).strip().lower()
        if not _SHA40.fullmatch(normalized):
            raise ValueError("revision must be a full 40-character Git SHA")
        return normalized

    @field_validator("input_sha256", "output_sha256", "previous_receipt_sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        normalized = str(value).strip().lower()
        if not _SHA64.fullmatch(normalized):
            raise ValueError("receipt digests must be 64-character lowercase SHA-256 values")
        return normalized


class DatabaseEvidenceReceipt(StrictModel):
    header: ReceiptHeader
    body: ReceiptBody


class ArchitectureSurface(StrictModel):
    path: str
    kind: Literal[
        "migration",
        "database-runtime",
        "database-test",
        "database-config",
        "database-documentation",
    ]
    database_families: list[str]
    path_class: Literal["PRODUCTION_CANDIDATE", "TEST_ONLY", "DOCUMENTATION"]


class SkillInventoryOutput(StrictToolOutput):
    tools: list[dict[str, Any]]
    boundaries: dict[str, Any]
    source_material_use: dict[str, list[str]]


class ArchitectureInventoryOutput(StrictToolOutput):
    revision: str
    dirty: bool
    scanned_file_count: int
    database_families: list[str]
    counts_by_kind: dict[str, int]
    surfaces: list[ArchitectureSurface]
    truncated: bool
    runtime_success_claimed: bool
    truth_notice: str


class EvidenceOperationOutput(StrictToolOutput):
    expected_revision: str
    actual_revision: str | None
    revision_verified: bool
    operation: str
    operation_result: dict[str, Any]
    receipt: DatabaseEvidenceReceipt | None
    runtime_success_claimed: bool
    truth_notice: str


class ReceiptVerificationFinding(StrictModel):
    index: int = Field(ge=0)
    family: Literal[
        "SEQUENCE_MISMATCH",
        "PREVIOUS_HASH_MISMATCH",
        "RECEIPT_HASH_MISMATCH",
        "REVISION_MISMATCH",
        "GENESIS_ANCHOR_MISMATCH",
    ]
    detail: str


class ReceiptVerificationOutput(StrictToolOutput):
    verified_count: int
    receipt_count: int
    chain_head_sha256: str
    findings: list[ReceiptVerificationFinding]
    expected_revision: str | None
    runtime_success_claimed: bool
    truth_notice: str


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
    )
    return completed.stdout.strip()


def _normalize_string(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _canonical_value(value: Any, *, path: str = "$") -> Any:
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        raise ValueError(f"floating-point value is forbidden in canonical evidence at {path}")
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, str):
        return _normalize_string(value)
    if isinstance(value, bytes):
        return {"sha256": hashlib.sha256(value).hexdigest(), "bytes": len(value)}
    if isinstance(value, BaseModel):
        return _canonical_value(value.model_dump(mode="python"), path=path)
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"non-string object key is forbidden in canonical evidence at {path}")
            normalized_key = _normalize_string(key)
            key_folded = normalized_key.casefold()
            if any(marker in key_folded for marker in _SECRET_KEY_MARKERS):
                if key_folded not in _SECRET_SAFE_BOOLEAN_KEYS or not isinstance(item, bool):
                    raise ValueError(f"secret-shaped field is forbidden in canonical evidence at {path}.{normalized_key}")
            normalized[normalized_key] = _canonical_value(item, path=f"{path}.{normalized_key}")
        return normalized
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    raise ValueError(f"unsupported canonical evidence type {type(value).__name__} at {path}")


def _canonical_bytes(value: Any) -> bytes:
    normalized = _canonical_value(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _receipt_hash(body: ReceiptBody) -> str:
    return _sha256(body.model_dump(mode="python"))


def _outcome(result: dict[str, Any]) -> tuple[str, str]:
    status = str(result.get("status") or "").strip().upper()
    if bool(result.get("ok")):
        return "success", "PASS"
    if "BLOCK" in status or "DENIED" in status or "REJECT" in status:
        return "blocked", "BLOCKED"
    return "failure", "FAIL"


def _runtime_revision(expected_revision: str) -> tuple[bool, str | None, dict[str, Any]]:
    expected = str(expected_revision or "").strip().lower()
    if not _SHA40.fullmatch(expected):
        raise ValueError("expected_revision must be a full 40-character Git SHA")
    if _BROKER is None:
        raise RuntimeError("DB evidence tools are not registered")
    status = _BROKER.call("mcp_self_update_status", {}, timeout=30)
    actual = str(status.get("revision") or "").strip().lower()
    verified = bool(
        status.get("ok")
        and status.get("revision_verified")
        and _SHA40.fullmatch(actual)
        and actual == expected
    )
    evidence = {
        "status": str(status.get("status") or "UNKNOWN")[:80],
        "revision": actual if _SHA40.fullmatch(actual) else "",
        "revision_verified": bool(status.get("revision_verified")),
        "image_digest_verified": bool(status.get("image_digest_verified")),
        "mcp_protocol_ready": bool(status.get("mcp_protocol_ready")),
        "broker_rpc_ready": bool(status.get("broker_rpc_ready")),
    }
    return verified, actual if _SHA40.fullmatch(actual) else None, evidence


def _make_receipt(
    *,
    sequence: int,
    revision: str,
    operation: str,
    operation_identity: str,
    input_payload: dict[str, Any],
    output_payload: dict[str, Any],
    result: dict[str, Any],
    observed_effect: str,
    previous_receipt_sha256: str,
) -> DatabaseEvidenceReceipt:
    previous = str(previous_receipt_sha256 or "").strip().lower() or _ZERO_SHA256
    if not _SHA64.fullmatch(previous):
        raise ValueError("previous_receipt_sha256 must be a full lowercase SHA-256")
    if sequence == 0 and previous != _ZERO_SHA256:
        raise ValueError("sequence 0 must use the all-zero genesis anchor")
    if sequence > 0 and previous == _ZERO_SHA256:
        raise ValueError("sequence greater than 0 requires a non-genesis previous receipt hash")
    outcome, gate_result = _outcome(result)
    body = ReceiptBody(
        sequence=sequence,
        revision=revision,
        operation=operation,
        operation_identity=operation_identity,
        input_sha256=_sha256(input_payload),
        output_sha256=_sha256(output_payload),
        outcome=outcome,
        gate_result=gate_result,
        mutation_performed=False,
        observed_effect=observed_effect,
        previous_receipt_sha256=previous,
    )
    return DatabaseEvidenceReceipt(
        header=ReceiptHeader(hash=_receipt_hash(body)),
        body=body,
    )


def _base_output(
    *,
    schema_version: str,
    ok: bool,
    status: str,
    failure_family: str | None = None,
    blocker: str | None = None,
    next_action: str | None = None,
    evidence: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": schema_version,
        "ok": ok,
        "status": status,
        "failureFamily": failure_family,
        "blocker": blocker,
        "mutationPerformed": False,
        "nextAction": next_action,
        "evidence": evidence or {},
        "data": data or {},
        "secretValuesReturned": False,
    }


def database_evidence_skill_inventory() -> SkillInventoryOutput:
    """List the architecture-native DB evidence tools and their enforced truth boundaries."""
    tools = [
        {"name": "database_evidence_skill_inventory", "effect": "read", "runtimeDatabaseAccess": False},
        {"name": "database_evidence_architecture_inventory", "effect": "read", "runtimeDatabaseAccess": False},
        {"name": "postgres_evidence_read", "effect": "network-read", "runtimeDatabaseAccess": True},
        {"name": "postgres_evidence_migration_preview", "effect": "ephemeral-write", "runtimeDatabaseAccess": True},
        {"name": "database_evidence_receipt_verify", "effect": "read", "runtimeDatabaseAccess": False},
    ]
    payload = _base_output(
        schema_version="sovereign.db-evidence-skill-inventory.v1",
        ok=True,
        status="DB_EVIDENCE_SKILL_READY",
        data={"toolCount": len(tools)},
    )
    return SkillInventoryOutput(
        **payload,
        tools=tools,
        boundaries={
            "genericSqlPathAdded": False,
            "postgresTruthPathReused": True,
            "sqliteTruthStoreCreated": False,
            "mockTracerUsed": False,
            "placeholderDatabaseSuccessAllowed": False,
            "envFileContentsRead": False,
            "rawSqlOrRowDataPersistedInReceipt": False,
            "timestampIncludedInCanonicalHash": False,
            "telemetryRequiredForTruth": False,
            "mutatingAdminSqlWrapped": False,
        },
        source_material_use={
            "adopted": [
                "architecture-aware database surface discovery",
                "SHA-256 input and output identities",
                "previous-receipt hash chaining",
                "repository revision binding",
                "machine-readable evidence receipts",
            ],
            "hardened": [
                "real PostgreSQL runtime instead of SQLite-only execution",
                "strict MCP input and output schemas",
                "Unicode-normalized canonical JSON without floats",
                "runtime revision verification before live database access",
                "secret-shaped field rejection",
                "timestamp separation from canonical truth",
            ],
            "rejected": [
                "MockTracer telemetry",
                "simulated PostgreSQL and MySQL success",
                "recursive .env content scanning",
                "process-local in-memory chain as authoritative persistence",
                "no-git-repo fallback presented as evidence",
                "catch-all exception suppression",
            ],
        },
    )


def _database_families(path: str, text: str) -> list[str]:
    lowered = f"{path}\n{text}".casefold()
    families: set[str] = set()
    rules = {
        "postgresql": ("postgres", "psycopg", "asyncpg", "pgvector"),
        "sqlite": ("sqlite", ".db", ".sqlite"),
        "mysql": ("mysql", "mariadb", "pymysql"),
        "mongodb": ("mongodb", "mongo", "pymongo"),
        "redis": ("redis",),
        "milvus": ("milvus",),
    }
    for family, markers in rules.items():
        if any(marker in lowered for marker in markers):
            families.add(family)
    return sorted(families)


def _surface_kind(path: str) -> str | None:
    lowered = path.casefold()
    name = PurePosixPath(path).name.casefold()
    if lowered.endswith(".sql") or "/migrations/" in lowered:
        return "migration"
    if any(marker in lowered for marker in ("/tests/", "/test_", ".test.", ".spec.")):
        if any(marker in lowered for marker in ("database", "postgres", "sql", "migration", "vector")):
            return "database-test"
    if any(marker in name for marker in ("database", "postgres", "sql", "migration")):
        return "database-runtime"
    if name in {"package.json", "pyproject.toml", "requirements.txt", "docker-compose.yml", "docker-compose.yaml"}:
        return "database-config"
    if lowered.endswith(".md") and any(marker in lowered for marker in ("database", "postgres", "migration", "evidence")):
        return "database-documentation"
    return None


def _path_class(path: str, kind: str) -> str:
    if kind == "database-test":
        return "TEST_ONLY"
    if kind == "database-documentation":
        return "DOCUMENTATION"
    return "PRODUCTION_CANDIDATE"


def database_evidence_architecture_inventory(workspace_id: str) -> ArchitectureInventoryOutput:
    """Map bounded database and migration surfaces without reading .env values or claiming runtime success."""
    if _RUNTIME is None:
        raise RuntimeError("DB evidence tools are not registered")
    repo = _RUNTIME._repo(workspace_id)
    revision = _git(repo, "rev-parse", "HEAD").lower()
    tracked = [line for line in _git(repo, "ls-files").splitlines() if line]
    if len(tracked) > _MAX_TRACKED_FILES:
        raise ValueError("repository exceeds the bounded tracked-file limit")
    surfaces: list[ArchitectureSurface] = []
    counts: Counter[str] = Counter()
    families: set[str] = set()
    scanned = 0
    for relative in tracked:
        if relative.startswith(_SKIP_PREFIXES) or PurePosixPath(relative).name.startswith(".env"):
            continue
        kind = _surface_kind(relative)
        suffix = PurePosixPath(relative).suffix.casefold()
        if kind is None and suffix not in _TEXT_SUFFIXES:
            continue
        path = repo / relative
        try:
            if path.stat().st_size > _MAX_TEXT_BYTES:
                continue
            text = path.read_text("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        scanned += 1
        detected = _database_families(relative, text)
        if kind is None and not detected:
            continue
        kind = kind or "database-runtime"
        families.update(detected)
        counts[kind] += 1
        if len(surfaces) < _MAX_SURFACES:
            surfaces.append(
                ArchitectureSurface(
                    path=relative,
                    kind=kind,
                    database_families=detected,
                    path_class=_path_class(relative, kind),
                )
            )
    payload = _base_output(
        schema_version="sovereign.db-evidence-architecture-inventory.v1",
        ok=True,
        status="DB_EVIDENCE_ARCHITECTURE_INVENTORIED",
        evidence={"revision": revision},
        data={"surfaceCount": sum(counts.values())},
    )
    return ArchitectureInventoryOutput(
        **payload,
        revision=revision,
        dirty=bool(_git(repo, "status", "--porcelain")),
        scanned_file_count=scanned,
        database_families=sorted(families),
        counts_by_kind=dict(sorted(counts.items())),
        surfaces=surfaces,
        truncated=sum(counts.values()) > len(surfaces),
        runtime_success_claimed=False,
        truth_notice=(
            "This is bounded static repository evidence. Live PostgreSQL truth requires "
            "postgres_evidence_read or postgres_evidence_migration_preview."
        ),
    )


def _revision_blocked_output(
    *,
    operation: str,
    expected_revision: str,
    actual_revision: str | None,
    revision_evidence: dict[str, Any],
) -> EvidenceOperationOutput:
    payload = _base_output(
        schema_version="sovereign.db-evidence-operation.v1",
        ok=False,
        status="BLOCKED_REVISION_MISMATCH",
        failure_family="MCP_RUNTIME_REVISION_MISMATCH",
        blocker="Live database evidence is blocked until the exact installed MCP revision matches.",
        next_action="verify_mcp_self_update_status_then_retry_with_the_exact_installed_revision",
        evidence={"runtimeRevision": revision_evidence},
    )
    return EvidenceOperationOutput(
        **payload,
        expected_revision=expected_revision,
        actual_revision=actual_revision,
        revision_verified=False,
        operation=operation,
        operation_result={},
        receipt=None,
        runtime_success_claimed=False,
        truth_notice="No database operation was executed because revision binding failed closed.",
    )


def postgres_evidence_read(
    operation: Literal[
        "postgres_canary",
        "postgres_schema_inventory",
        "postgres_schema_contract_inventory",
        "vector_database_canary",
    ],
    expected_revision: str,
    table_names: list[str] | None = None,
    previous_receipt_sha256: str = _ZERO_SHA256,
    sequence: int = 0,
) -> EvidenceOperationOutput:
    """Execute one allowlisted real PostgreSQL read and return a revision-bound deterministic receipt."""
    expected = str(expected_revision).strip().lower()
    verified, actual, revision_evidence = _runtime_revision(expected)
    if not verified or actual is None:
        return _revision_blocked_output(
            operation=operation,
            expected_revision=expected,
            actual_revision=actual,
            revision_evidence=revision_evidence,
        )
    if _DATABASE is None:
        raise RuntimeError("DB evidence tools are not registered")
    names = list(table_names or [])
    if operation != "postgres_schema_contract_inventory" and names:
        raise ValueError("table_names are only valid for postgres_schema_contract_inventory")
    try:
        if operation == "postgres_canary":
            result = _DATABASE.canary()
            identity = "postgres:canary"
        elif operation == "postgres_schema_inventory":
            result = _DATABASE.schema_inventory()
            identity = "postgres:schema-inventory"
        elif operation == "postgres_schema_contract_inventory":
            result = _DATABASE.schema_contract_inventory(names)
            identity = "postgres:schema-contract:" + ",".join(sorted(names))
        else:
            result = _DATABASE.vector_canary()
            identity = "postgres:vector-canary"
    except Exception as exc:
        result = {
            "ok": False,
            "status": "POSTGRES_EVIDENCE_READ_FAILED",
            "failure_family": type(exc).__name__,
            "error_type": type(exc).__name__,
            "secretValuesReturned": False,
        }
    receipt = _make_receipt(
        sequence=sequence,
        revision=actual,
        operation=operation,
        operation_identity=identity[:300],
        input_payload={
            "operation": operation,
            "expected_revision": expected,
            "table_names": sorted(names),
        },
        output_payload=result,
        result=result,
        observed_effect="read",
        previous_receipt_sha256=previous_receipt_sha256,
    )
    ok = bool(result.get("ok"))
    payload = _base_output(
        schema_version="sovereign.db-evidence-operation.v1",
        ok=ok,
        status="POSTGRES_EVIDENCE_CAPTURED" if ok else "POSTGRES_EVIDENCE_CAPTURED_FAILURE",
        failure_family=None if ok else str(result.get("failure_family") or "POSTGRES_OPERATION_FAILED")[:160],
        blocker=None if ok else "The real PostgreSQL operation did not pass.",
        next_action=None if ok else "inspect_the_operation_result_without_reusing_it_as_success_evidence",
        evidence={"runtimeRevision": revision_evidence, "receiptSha256": receipt.header.hash},
        data={"operationResultReturned": True},
    )
    return EvidenceOperationOutput(
        **payload,
        expected_revision=expected,
        actual_revision=actual,
        revision_verified=True,
        operation=operation,
        operation_result=result,
        receipt=receipt,
        runtime_success_claimed=ok,
        truth_notice=(
            "The receipt hashes the exact bounded operation input and returned operation result. "
            "It does not persist raw SQL or arbitrary row data."
        ),
    )


def postgres_evidence_migration_preview(
    workspace_id: str,
    path: str,
    expected_revision: str,
    previous_receipt_sha256: str = _ZERO_SHA256,
    sequence: int = 0,
) -> EvidenceOperationOutput:
    """Run the existing rollback-only preview database path and bind its real result to a receipt."""
    expected = str(expected_revision).strip().lower()
    verified, actual, revision_evidence = _runtime_revision(expected)
    if not verified or actual is None:
        return _revision_blocked_output(
            operation="postgres_migration_preview",
            expected_revision=expected,
            actual_revision=actual,
            revision_evidence=revision_evidence,
        )
    if _DATABASE is None:
        raise RuntimeError("DB evidence tools are not registered")
    try:
        result = _DATABASE.preview_migration(workspace_id, path)
    except Exception as exc:
        result = {
            "ok": False,
            "status": "POSTGRES_MIGRATION_PREVIEW_BLOCKED",
            "failure_family": type(exc).__name__,
            "error_type": type(exc).__name__,
            "rolled_back": True,
            "secretValuesReturned": False,
        }
    migration_sha = str(result.get("sha256") or "").strip().lower()
    identity = f"postgres:migration-preview:{path}"
    if _SHA64.fullmatch(migration_sha):
        identity = f"{identity}:{migration_sha}"
    receipt = _make_receipt(
        sequence=sequence,
        revision=actual,
        operation="postgres_migration_preview",
        operation_identity=identity[:300],
        input_payload={
            "workspace_id": workspace_id,
            "path": path,
            "expected_revision": expected,
            "migration_sha256": migration_sha if _SHA64.fullmatch(migration_sha) else "",
        },
        output_payload=result,
        result=result,
        observed_effect="ephemeral-write",
        previous_receipt_sha256=previous_receipt_sha256,
    )
    ok = bool(result.get("ok")) and bool(result.get("rolled_back"))
    payload = _base_output(
        schema_version="sovereign.db-evidence-operation.v1",
        ok=ok,
        status="POSTGRES_MIGRATION_PREVIEW_EVIDENCE_CAPTURED" if ok else "POSTGRES_MIGRATION_PREVIEW_FAILED",
        failure_family=None if ok else str(result.get("failure_family") or "MIGRATION_PREVIEW_FAILED")[:160],
        blocker=None if ok else "The rollback-only migration preview did not pass.",
        next_action=None if ok else "repair_the_migration_or_preview_environment_then_rerun_the_same_path",
        evidence={"runtimeRevision": revision_evidence, "receiptSha256": receipt.header.hash},
        data={"rolledBack": bool(result.get("rolled_back"))},
    )
    return EvidenceOperationOutput(
        **payload,
        expected_revision=expected,
        actual_revision=actual,
        revision_verified=True,
        operation="postgres_migration_preview",
        operation_result=result,
        receipt=receipt,
        runtime_success_claimed=ok,
        truth_notice=(
            "The existing dedicated preview transaction is authoritative. A PASS requires "
            "the real preview result and an explicit rollback marker."
        ),
    )


def database_evidence_receipt_verify(
    receipts: list[DatabaseEvidenceReceipt],
    expected_revision: str = "",
    expected_start_sequence: int = 0,
    anchor_previous_receipt_sha256: str = _ZERO_SHA256,
) -> ReceiptVerificationOutput:
    """Verify receipt hashes, revision binding, sequence order and the complete previous-hash chain."""
    if not receipts or len(receipts) > 10_000:
        raise ValueError("receipts must contain between 1 and 10,000 entries")
    expected = str(expected_revision or "").strip().lower()
    if expected and not _SHA40.fullmatch(expected):
        raise ValueError("expected_revision must be empty or a full 40-character Git SHA")
    anchor = str(anchor_previous_receipt_sha256 or "").strip().lower()
    if not _SHA64.fullmatch(anchor):
        raise ValueError("anchor_previous_receipt_sha256 must be a full lowercase SHA-256")
    findings: list[ReceiptVerificationFinding] = []
    previous = anchor
    verified_count = 0
    for index, receipt in enumerate(receipts):
        body = receipt.body
        expected_sequence = expected_start_sequence + index
        if body.sequence != expected_sequence:
            findings.append(ReceiptVerificationFinding(
                index=index,
                family="SEQUENCE_MISMATCH",
                detail=f"expected sequence {expected_sequence}, observed {body.sequence}",
            ))
        if index == 0 and body.previous_receipt_sha256 != anchor:
            findings.append(ReceiptVerificationFinding(
                index=index,
                family="GENESIS_ANCHOR_MISMATCH",
                detail="first receipt does not reference the supplied anchor",
            ))
        elif index > 0 and body.previous_receipt_sha256 != previous:
            findings.append(ReceiptVerificationFinding(
                index=index,
                family="PREVIOUS_HASH_MISMATCH",
                detail="receipt does not reference the exact preceding receipt hash",
            ))
        computed = _receipt_hash(body)
        if receipt.header.hash != computed:
            findings.append(ReceiptVerificationFinding(
                index=index,
                family="RECEIPT_HASH_MISMATCH",
                detail="stored receipt hash differs from canonical body hash",
            ))
        if expected and body.revision != expected:
            findings.append(ReceiptVerificationFinding(
                index=index,
                family="REVISION_MISMATCH",
                detail=f"expected revision {expected}, observed {body.revision}",
            ))
        if not any(item.index == index for item in findings):
            verified_count += 1
        previous = receipt.header.hash
    ok = not findings
    payload = _base_output(
        schema_version="sovereign.db-evidence-receipt-verification.v1",
        ok=ok,
        status="DB_EVIDENCE_CHAIN_VERIFIED" if ok else "DB_EVIDENCE_CHAIN_INVALID",
        failure_family=None if ok else "DB_EVIDENCE_CHAIN_MISMATCH",
        blocker=None if ok else "One or more receipt-chain invariants failed.",
        next_action=None if ok else "discard_the_unverified_claim_and_rebuild_from_authoritative_operation_evidence",
        evidence={"chainHeadSha256": previous},
        data={"receiptCount": len(receipts), "verifiedCount": verified_count},
    )
    return ReceiptVerificationOutput(
        **payload,
        verified_count=verified_count,
        receipt_count=len(receipts),
        chain_head_sha256=previous,
        findings=findings,
        expected_revision=expected or None,
        runtime_success_claimed=False,
        truth_notice=(
            "Verification proves internal receipt integrity and revision binding only. "
            "Runtime truth still depends on the authoritative producer of each receipt."
        ),
    )


def register(mcp: Any, runtime: Any, database: Any, broker: Any) -> None:
    global _RUNTIME, _DATABASE, _BROKER, _REGISTERED
    _RUNTIME = runtime
    _DATABASE = database
    _BROKER = broker
    if _REGISTERED:
        return
    mcp.tool(annotations=READ_ONLY)(database_evidence_skill_inventory)
    mcp.tool(annotations=READ_ONLY)(database_evidence_architecture_inventory)
    mcp.tool(annotations=NETWORK_READ)(postgres_evidence_read)
    mcp.tool(annotations=SAFE_WRITE)(postgres_evidence_migration_preview)
    mcp.tool(annotations=READ_ONLY)(database_evidence_receipt_verify)
    _REGISTERED = True
