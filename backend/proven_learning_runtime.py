"""Evidence-gated, owner-approved learning-pattern persistence.

The authoritative write path is PostgreSQL/pgvector. Milvus receives the
existing idempotent outbox projection; no second source of truth is created.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import hmac
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Callable
import uuid

from flask import jsonify, request

from agent_runtime.pattern_gateway import PatternLearningResult, persist_pattern_learning_candidate_once
from agent_runtime.pattern_vector_memory import persist_pattern_vector

ConnectionFactory = Callable[[], Any]

_SCHEMA_VERSION = "knowledge-pattern.v1"
_PLAN_SCHEMA_VERSION = "sovereign.proven-learning-plan.v1"
_APPROVAL_TARGET = "proven_learning_confirmation"
_APPROVAL_FILENAME = "proven_learning_confirmation.txt"
_MAX_RECORD_BYTES = 80_000
_OPERATION_TYPES = frozenset({"integration", "fix", "database", "merge"})
_EVIDENCE_SOURCES = frozenset({
    "repository_check",
    "github_actions",
    "runtime_readback",
    "database_readback",
    "migration_readback",
    "merge_result",
})
_REQUIRED_TEXT = ("title", "problem", "solution", "applicability")
_LIST_FIELDS = (
    "triggers",
    "preconditions",
    "invariants",
    "failure_modes",
    "validation",
    "exclusions",
    "tags",
    "supersedes",
)
_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_SECRET_MARKER = re.compile(
    r"(?:sk-(?:proj-)?[A-Za-z0-9_-]{12,}|github_pat_[A-Za-z0-9_]+|"
    r"gh[pousr]_[A-Za-z0-9_]{20,}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----|"
    r"Authorization\s*:\s*(?:Bearer\s+)?\S+)",
    re.IGNORECASE,
)


class ProvenLearningBlocked(RuntimeError):
    def __init__(self, message: str, *, http_status: int = 409, code: str = "PROVEN_LEARNING_BLOCKED") -> None:
        super().__init__(message)
        self.http_status = http_status
        self.code = code


def _clean_text(value: Any, limit: int = 4_000) -> str:
    return " ".join(str(value or "").replace("\x00", "").split())[:limit]


def _clean_list(value: Any, *, lower: bool = False, limit: int = 50) -> list[str]:
    values = value if isinstance(value, list) else ([] if value in (None, "") else [value])
    cleaned = {_clean_text(item, 1_000) for item in values if _clean_text(item, 1_000)}
    if lower:
        cleaned = {item.casefold().replace(" ", "-") for item in cleaned}
    return sorted(cleaned)[:limit]


def _safe_repo_path(value: Any) -> str:
    clean = _clean_text(value, 500).replace("\\", "/")
    path = PurePosixPath(clean)
    if not clean or path.is_absolute() or ".." in path.parts or clean.startswith(".git/"):
        raise ValueError("evidence path is unsafe")
    return path.as_posix()


def _source_ref(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("each source_refs entry must be an object")
    result = {
        key: _clean_text(value.get(key), 500)
        for key in ("repository", "revision", "path", "lines", "license")
    }
    for field in ("repository", "revision", "path", "license"):
        if not result[field]:
            raise ValueError(f"source_refs.{field} is required")
    result["revision"] = result["revision"].casefold()
    if not _HEX_40.fullmatch(result["revision"]):
        raise ValueError("source_refs.revision must be an exact 40-character Git SHA")
    result["path"] = _safe_repo_path(result["path"])
    return result


def _completed_at(value: Any) -> str:
    clean = _clean_text(value, 80)
    if not clean:
        raise ValueError("evidence.completed_at is required")
    try:
        parsed = datetime.fromisoformat(clean.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("evidence.completed_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("evidence.completed_at must include a timezone")
    return parsed.isoformat().replace("+00:00", "Z")


def _evidence_check(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("each evidence check must be an object")
    name = _clean_text(value.get("name"), 160)
    status_value = _clean_text(value.get("status"), 40).casefold()
    source = _clean_text(value.get("source"), 80).casefold()
    evidence_sha256 = _clean_text(value.get("evidence_sha256"), 80).casefold()
    summary = _clean_text(value.get("summary"), 600)
    if not name or status_value != "passed":
        raise ValueError("every evidence check must have a name and status=passed")
    if source not in _EVIDENCE_SOURCES:
        raise ValueError("evidence check source is not allowlisted")
    if not _HEX_64.fullmatch(evidence_sha256):
        raise ValueError("evidence check requires an exact SHA-256 receipt")
    if len(summary) < 8:
        raise ValueError("evidence check summary is too short")
    return {
        "name": name,
        "status": "passed",
        "source": source,
        "evidence_sha256": evidence_sha256,
        "summary": summary,
    }


def _normalize_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("evidence is required")
    operation_type = _clean_text(value.get("operation_type"), 40).casefold()
    outcome = _clean_text(value.get("outcome"), 40).casefold()
    revision = _clean_text(value.get("revision"), 80).casefold()
    if operation_type not in _OPERATION_TYPES:
        raise ValueError("evidence.operation_type is invalid")
    if outcome != "successful":
        raise ValueError("only successful outcomes may become learning patterns")
    if not _HEX_40.fullmatch(revision):
        raise ValueError("evidence.revision must be an exact 40-character Git SHA")
    raw_checks = value.get("checks")
    if not isinstance(raw_checks, list) or not raw_checks or len(raw_checks) > 20:
        raise ValueError("evidence.checks must contain between 1 and 20 receipts")
    checks = sorted(
        (_evidence_check(item) for item in raw_checks),
        key=lambda item: (item["source"], item["name"], item["evidence_sha256"]),
    )
    sources = {item["source"] for item in checks}
    if operation_type in {"integration", "fix"} and not sources.intersection({"repository_check", "github_actions"}):
        raise ValueError("integration/fix evidence requires a repository or GitHub Actions check")
    if operation_type == "database" and not sources.intersection({"database_readback", "migration_readback"}):
        raise ValueError("database evidence requires a database or migration readback")
    if operation_type == "merge" and "merge_result" not in sources:
        raise ValueError("merge evidence requires an exact merge result receipt")
    changed_paths = sorted({_safe_repo_path(item) for item in (value.get("changed_paths") or [])})
    if operation_type in {"integration", "fix", "merge"} and not changed_paths:
        raise ValueError("repository outcomes require at least one changed path")
    return {
        "operation_type": operation_type,
        "outcome": "successful",
        "revision": revision,
        "completed_at": _completed_at(value.get("completed_at")),
        "changed_paths": changed_paths[:100],
        "checks": checks,
    }


def normalize_proven_learning_record(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("record must be an object")
    if len(json.dumps(record, ensure_ascii=False).encode("utf-8")) > _MAX_RECORD_BYTES:
        raise ValueError("record exceeds the bounded size limit")

    normalized: dict[str, Any] = {"schema_version": _SCHEMA_VERSION}
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
    normalized["source_refs"] = sorted(
        (_source_ref(item) for item in refs),
        key=lambda item: (item["repository"], item["revision"], item["path"], item["lines"]),
    )
    try:
        confidence = float(record.get("confidence", 0.0))
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence must be numeric") from exc
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    normalized["confidence"] = round(confidence, 6)
    normalized["evidence"] = _normalize_evidence(record.get("evidence"))

    serialized = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if _SECRET_MARKER.search(serialized):
        raise ValueError("record contains a secret-like marker")
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    normalized["pattern_id"] = f"pattern:{digest[:24]}"
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
    )))[:8_000]
    normalized["content_hash"] = f"sha256:{digest}"
    return normalized


def plan_proven_learning(record: Any) -> dict[str, Any]:
    normalized = normalize_proven_learning_record(record)
    digest = normalized["content_hash"].removeprefix("sha256:")
    return {
        "ok": True,
        "status": "PROVEN_LEARNING_PLAN_READY",
        "schemaVersion": _PLAN_SCHEMA_VERSION,
        "confirmationSha256": digest,
        "record": normalized,
        "databaseAccessed": False,
        "embeddingGenerated": False,
        "ownerApprovalRequired": False,
        "approvalMode": "persisted-owner-policy-or-fresh-owner-approval",
        "protectedValueTransport": "authenticated_owner_ui_only_when-policy-disabled",
    }


def _service_authorized() -> bool:
    expected = os.getenv("SOVEREIGN_OWNER_REQUEST_KEY", "").strip()
    supplied = request.headers.get("X-Sovereign-Owner-Request-Key", "").strip()
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def _approval_path() -> Path:
    root = Path(os.getenv("SOVEREIGN_OWNER_INPUT_ROOT", "/opt/sovereign-owner-managed")).resolve()
    return (root / _APPROVAL_FILENAME).resolve()


def _read_approval_hash() -> str:
    path = _approval_path()
    if path.is_symlink():
        raise ProvenLearningBlocked("Owner confirmation artifact must not be a symlink", code="OWNER_CONFIRMATION_UNSAFE")
    try:
        metadata = path.stat()
    except FileNotFoundError as exc:
        raise ProvenLearningBlocked("Fresh owner confirmation is missing", code="OWNER_CONFIRMATION_REQUIRED") from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077:
        raise ProvenLearningBlocked("Owner confirmation artifact has unsafe ownership or mode", code="OWNER_CONFIRMATION_UNSAFE")
    if metadata.st_size < 64 or metadata.st_size > 80:
        raise ProvenLearningBlocked("Owner confirmation artifact has an invalid size", code="OWNER_CONFIRMATION_INVALID")
    value = path.read_text("utf-8").strip().casefold()
    if not _HEX_64.fullmatch(value):
        raise ProvenLearningBlocked("Owner confirmation must contain the exact plan SHA-256", code="OWNER_CONFIRMATION_INVALID")
    return value


def _remove_approval_hash() -> None:
    path = _approval_path()
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise ProvenLearningBlocked("Stored pattern is safe, but the one-time confirmation could not be removed", http_status=500, code="OWNER_CONFIRMATION_CLEANUP_FAILED") from exc


def _pattern_readback(conn: Any, *, user_id: str, digest: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT c.candidate_id AS "candidateId",
                      (v.candidate_id IS NOT NULL) AS "vectorStored",
                      COALESCE(o.status, '') AS "outboxStatus"
               FROM sovereign_agent_pattern_candidates c
               LEFT JOIN sovereign_agent_pattern_vectors v
                 ON v.candidate_id=c.candidate_id AND v.user_id=c.user_id
               LEFT JOIN vector_index_outbox o
                 ON o.entity_type='agent_pattern' AND o.entity_id=c.candidate_id
               WHERE c.user_id=%s
                 AND c.decision='accepted'
                 AND c.payload->>'contentHash'=%s
               ORDER BY c.created_at ASC
               LIMIT 1""",
            (user_id, digest),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _learning_result(normalized: dict[str, Any], digest: str) -> PatternLearningResult:
    evidence = normalized["evidence"]
    checks = evidence["checks"]
    payload = {
        "jobId": f"proven-{digest[:32]}",
        "source": "sovereign-proven-learning",
        "kind": "solution",
        "mission": normalized["title"],
        "missionSha256": digest,
        "changedFiles": evidence["changed_paths"],
        "diffSummary": f"{normalized['problem']} {normalized['solution']}"[:2_000],
        "testSummary": " | ".join(f"{item['name']}: {item['summary']}" for item in checks)[:2_000],
        "blocker": "",
        "blockerEvidencePassed": False,
        "draftPrReady": True,
        "contentHash": digest,
        "structuredPattern": normalized,
        "embeddingText": normalized["embedding_text"],
    }
    return PatternLearningResult(
        allowed=True,
        decision="accepted",
        kind="solution",
        summary=normalized["title"],
        payload=payload,
        blockers=(),
        predictive_signal="proven_learning_pattern_ready",
        remote_memory_allowed=True,
    )


def _standing_learning_owner(conn: Any) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT p.owner_admin_id::text AS owner_admin_id
               FROM owner_learning_policies p
               JOIN admin_users a ON a.id=p.owner_admin_id
               WHERE p.auto_accept_useful_unique=TRUE
                 AND a.role IN ('admin','superadmin')
               ORDER BY CASE WHEN a.role='superadmin' THEN 0 ELSE 1 END, p.updated_at DESC
               LIMIT 2"""
        )
        rows = cur.fetchall()
    if len(rows) != 1:
        raise ProvenLearningBlocked(
            "Exactly one active owner learning policy is required for automatic persistence",
            code="OWNER_LEARNING_POLICY_AMBIGUOUS",
        )
    return str(rows[0]["owner_admin_id"])


def apply_proven_learning(
    conn: Any,
    *,
    request_id: str = "",
    confirmation_sha256: str,
    record: Any,
) -> dict[str, Any]:
    selected_request_id = ""
    if str(request_id or "").strip():
        try:
            selected_request_id = str(uuid.UUID(str(request_id or "").strip()))
        except ValueError as exc:
            raise ValueError("request_id is invalid") from exc
    plan = plan_proven_learning(record)
    digest = plan["confirmationSha256"]
    supplied_digest = _clean_text(confirmation_sha256, 80).casefold()
    if not _HEX_64.fullmatch(supplied_digest) or not hmac.compare_digest(digest, supplied_digest):
        raise ProvenLearningBlocked("Apply payload does not match the approved plan", code="PLAN_HASH_MISMATCH")

    approval: dict[str, Any] | None = None
    if selected_request_id:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id::text, target_id, status, owner_admin_id::text AS owner_admin_id,
                          result_code, resolved_at
                   FROM owner_input_requests
                   WHERE id=%s::uuid
                   LIMIT 1""",
                (selected_request_id,),
            )
            row = cur.fetchone()
        if not row:
            raise ProvenLearningBlocked("Owner approval request was not found", http_status=404, code="OWNER_REQUEST_NOT_FOUND")
        approval = dict(row)
        user_id = str(approval.get("owner_admin_id") or "")
        if approval.get("target_id") != _APPROVAL_TARGET or not user_id:
            raise ProvenLearningBlocked("Owner approval is not bound to this learning plan", code="OWNER_REQUEST_MISMATCH")
    else:
        user_id = _standing_learning_owner(conn)

    if approval and approval.get("result_code") == "proven_learning_applied":
        existing = _pattern_readback(conn, user_id=user_id, digest=digest)
        if not existing or not existing["vectorStored"]:
            raise ProvenLearningBlocked("Applied approval has no canonical vector readback", http_status=500, code="PERSISTENCE_READBACK_FAILED")
        _remove_approval_hash()
        return {
            "ok": True,
            "status": "PROVEN_LEARNING_PATTERN_STORED",
            "candidateId": existing["candidateId"],
            "duplicate": True,
            "canonicalStorage": "postgres-pgvector",
            "indexProjection": "milvus-outbox",
            "outboxStatus": existing["outboxStatus"],
            "readbackVerified": True,
            "ownerApprovalConsumed": True,
        }

    if approval:
        if approval.get("status") != "consumed" or approval.get("result_code") != "target_updated":
            raise ProvenLearningBlocked("Fresh authenticated owner approval has not been completed", code="OWNER_CONFIRMATION_REQUIRED")
        with conn.cursor() as cur:
            cur.execute(
                """SELECT EXISTS (
                       SELECT 1 FROM owner_input_requests
                       WHERE id=%s::uuid
                         AND resolved_at >= NOW() - INTERVAL '15 minutes'
                   ) AS fresh""",
                (selected_request_id,),
            )
            freshness = cur.fetchone()
        if not freshness or not bool(freshness["fresh"]):
            raise ProvenLearningBlocked("Owner approval is no longer fresh", code="OWNER_CONFIRMATION_EXPIRED")
        approved_digest = _read_approval_hash()
        if not hmac.compare_digest(approved_digest, digest):
            raise ProvenLearningBlocked("Owner confirmation does not match the exact plan", code="OWNER_CONFIRMATION_MISMATCH")

    result = _learning_result(plan["record"], digest)
    candidate_id, created = persist_pattern_learning_candidate_once(
        conn,
        user_id=user_id,
        result=result,
        commit=False,
    )
    if not candidate_id:
        raise ProvenLearningBlocked("Accepted pattern candidate could not be persisted", http_status=500, code="CANDIDATE_PERSISTENCE_FAILED")
    vector = persist_pattern_vector(
        conn,
        candidate_id=candidate_id,
        user_id=user_id,
        result=result,
        commit=False,
    )
    if not vector.get("stored"):
        raise ProvenLearningBlocked(
            str(vector.get("blocker") or vector.get("reason") or "Canonical vector persistence failed")[:500],
            http_status=503,
            code="VECTOR_PERSISTENCE_BLOCKED",
        )
    readback = _pattern_readback(conn, user_id=user_id, digest=digest)
    if not readback or not readback["vectorStored"]:
        raise ProvenLearningBlocked("Canonical pattern/vector readback failed", http_status=500, code="PERSISTENCE_READBACK_FAILED")

    if approval:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE owner_input_requests
                   SET result_code='proven_learning_applied', consumed_at=COALESCE(consumed_at, NOW())
                   WHERE id=%s::uuid
                     AND target_id=%s
                     AND status='consumed'
                     AND result_code='target_updated'""",
                (selected_request_id, _APPROVAL_TARGET),
            )
            if cur.rowcount != 1:
                conn.rollback()
                raise ProvenLearningBlocked("Owner approval lifecycle changed during apply", code="OWNER_REQUEST_RACE")
    conn.commit()
    if approval:
        _remove_approval_hash()
    return {
        "ok": True,
        "status": "PROVEN_LEARNING_PATTERN_STORED",
        "candidateId": readback["candidateId"],
        "duplicate": not created,
        "canonicalStorage": "postgres-pgvector",
        "indexProjection": "milvus-outbox",
        "outboxStatus": readback["outboxStatus"],
        "embeddingModel": vector.get("embeddingModel"),
        "embeddingProvider": vector.get("provider"),
        "readbackVerified": True,
        "ownerApprovalConsumed": bool(approval),
        "standingOwnerPolicyUsed": not bool(approval),
    }


def register_proven_learning_routes(app: Any, *, get_connection: ConnectionFactory) -> None:
    @app.route("/api/internal/proven-learning/plan", methods=["POST"])
    def internal_proven_learning_plan():
        if not _service_authorized():
            return jsonify({"error": "Nicht autorisiert"}), 401
        try:
            return jsonify(plan_proven_learning((request.get_json(force=True) or {}).get("record"))), 200
        except ValueError as exc:
            return jsonify({"error": str(exc)[:500], "status": "PROVEN_LEARNING_PLAN_BLOCKED"}), 400

    @app.route("/api/internal/proven-learning/apply", methods=["POST"])
    def internal_proven_learning_apply():
        if not _service_authorized():
            return jsonify({"error": "Nicht autorisiert"}), 401
        body = request.get_json(force=True) or {}
        conn = get_connection()
        try:
            result = apply_proven_learning(
                conn,
                request_id=body.get("requestId"),
                confirmation_sha256=body.get("confirmationSha256"),
                record=body.get("record"),
            )
            return jsonify(result), 200
        except ValueError as exc:
            conn.rollback()
            return jsonify({"error": str(exc)[:500], "status": "PROVEN_LEARNING_APPLY_BLOCKED"}), 400
        except ProvenLearningBlocked as exc:
            conn.rollback()
            return jsonify({"error": str(exc)[:500], "status": exc.code}), exc.http_status
        finally:
            conn.close()
