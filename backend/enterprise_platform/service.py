"""Evidence-first application service for the Sovereign enterprise admin platform."""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Callable
from typing import Any

from .contracts import (
    SCHEMA_VERSION,
    STATUS_BLOCKED,
    STATUS_DEFINED_NOT_RUN,
    STATUS_DEGRADED,
    STATUS_ISOLATED,
    STATUS_VERIFIED,
    bounded_int,
    bounded_text,
    evidence_sha256,
    normalize_image_digest,
    normalize_source_revision,
    utc_now,
)

QueryFn = Callable[..., Any]
ReadinessFn = Callable[[], dict[str, Any]]
CompletionFn = Callable[[str], dict[str, Any]]

_BOOTED_AT = utc_now()
_RUNTIME_ID = str(uuid.uuid4())


class PlatformEvidenceWriteError(RuntimeError):
    pass


class PlatformCanaryRateLimited(RuntimeError):
    def __init__(self, retry_after_seconds: int):
        super().__init__("platform_canary_rate_limited")
        self.retry_after_seconds = retry_after_seconds


class PlatformModelRejected(ValueError):
    pass


class EnterprisePlatformService:
    """Coordinates bounded probes without turning the admin API into a shell or SQL console."""

    def __init__(
        self,
        *,
        query: QueryFn,
        litellm_readiness: ReadinessFn,
        litellm_completion_canary: CompletionFn,
    ):
        self._query = query
        self._litellm_readiness = litellm_readiness
        self._litellm_completion_canary = litellm_completion_canary

    def runtime_identity(self) -> dict[str, Any]:
        revision, revision_verified = normalize_source_revision(
            os.getenv("SOVEREIGN_SOURCE_REVISION")
        )
        image_digest, digest_verified = normalize_image_digest(
            os.getenv("SOVEREIGN_IMAGE_DIGEST")
        )
        return {
            "runtimeId": _RUNTIME_ID,
            "startedAt": _BOOTED_AT,
            "sourceRevision": revision,
            "sourceRevisionVerified": revision_verified,
            "imageDigest": image_digest,
            "imageDigestVerified": digest_verified,
            "environment": bounded_text(
                os.getenv("SOVEREIGN_RUNTIME_ENVIRONMENT", "production"),
                maximum=40,
            ) or "production",
        }

    def _integration(
        self,
        *,
        integration_id: str,
        label: str,
        status: str,
        required: bool,
        boundary: str,
        evidence: dict[str, Any] | None = None,
        blocker: str | None = None,
        latency_ms: int | None = None,
    ) -> dict[str, Any]:
        return {
            "id": integration_id,
            "label": label,
            "status": status,
            "required": required,
            "boundary": boundary,
            "evidence": evidence or {},
            "blocker": blocker,
            "latencyMs": latency_ms,
            "checkedAt": utc_now(),
        }

    def _postgres_probe(self) -> dict[str, Any]:
        started = time.monotonic()
        try:
            row = self._query(
                """/* platform:probe:postgresql */
                   SELECT current_database() AS database,
                          COALESCE((SELECT MAX(id) FROM schema_migrations), 0) AS migration_id,
                          to_regclass('public.platform_runtime_evidence') IS NOT NULL AS evidence_table""",
                one=True,
            )
            latency = max(0, int((time.monotonic() - started) * 1000))
            evidence_table = bool(row and row.get("evidence_table"))
            return self._integration(
                integration_id="postgresql",
                label="PostgreSQL / Supabase",
                status=STATUS_VERIFIED if row and evidence_table else STATUS_BLOCKED,
                required=True,
                boundary="transactional source of truth",
                evidence={
                    "database": bounded_text((row or {}).get("database"), maximum=80),
                    "latestMigration": bounded_int((row or {}).get("migration_id"), maximum=100_000),
                    "evidenceTablePresent": evidence_table,
                },
                blocker=None if row and evidence_table else "platform_evidence_migration_missing",
                latency_ms=latency,
            )
        except Exception:
            return self._integration(
                integration_id="postgresql",
                label="PostgreSQL / Supabase",
                status=STATUS_BLOCKED,
                required=True,
                boundary="transactional source of truth",
                blocker="postgresql_canary_failed",
                latency_ms=max(0, int((time.monotonic() - started) * 1000)),
            )

    def _pgvector_probe(self) -> dict[str, Any]:
        started = time.monotonic()
        try:
            row = self._query(
                """/* platform:probe:pgvector */
                   SELECT extversion,
                          (SELECT COUNT(*) FROM knowledge_blocks WHERE embedding IS NOT NULL) AS knowledge_vectors,
                          (SELECT COUNT(*) FROM sovereign_agent_pattern_vectors) AS pattern_vectors
                   FROM pg_extension WHERE extname = 'vector'""",
                one=True,
            )
            ok = bool(row and row.get("extversion"))
            return self._integration(
                integration_id="pgvector",
                label="pgvector Memory",
                status=STATUS_VERIFIED if ok else STATUS_BLOCKED,
                required=True,
                boundary="canonical vector persistence",
                evidence={
                    "extensionVersion": bounded_text((row or {}).get("extversion"), maximum=30),
                    "knowledgeVectors": bounded_int((row or {}).get("knowledge_vectors")),
                    "patternVectors": bounded_int((row or {}).get("pattern_vectors")),
                },
                blocker=None if ok else "pgvector_extension_missing",
                latency_ms=max(0, int((time.monotonic() - started) * 1000)),
            )
        except Exception:
            return self._integration(
                integration_id="pgvector",
                label="pgvector Memory",
                status=STATUS_BLOCKED,
                required=True,
                boundary="canonical vector persistence",
                blocker="pgvector_canary_failed",
                latency_ms=max(0, int((time.monotonic() - started) * 1000)),
            )

    def _litellm_probe(self) -> dict[str, Any]:
        started = time.monotonic()
        try:
            result = self._litellm_readiness()
        except Exception:
            result = {"ok": False, "errorCode": "litellm_readiness_exception"}
        ok = bool(result.get("ok"))
        try:
            active_model_ids = sorted(self._active_model_ids())
        except Exception:
            active_model_ids = []
        return self._integration(
            integration_id="litellm",
            label="Private LiteLLM",
            status=STATUS_VERIFIED if ok else STATUS_BLOCKED,
            required=True,
            boundary="only provider routing path; provider keys remain isolated",
            evidence={
                "httpStatus": result.get("httpStatus"),
                "readiness": bounded_text(result.get("status"), maximum=40),
                "database": bounded_text(result.get("db"), maximum=40),
                "activeModelIds": active_model_ids,
            },
            blocker=None if ok else bounded_text(
                result.get("errorCode") or "litellm_not_ready",
                maximum=120,
            ),
            latency_ms=max(0, int((time.monotonic() - started) * 1000)),
        )

    def _agents_probe(self) -> dict[str, Any]:
        started = time.monotonic()
        try:
            row = self._query(
                """/* platform:probe:agents */
                   SELECT COUNT(*) AS total_runs,
                          COUNT(*) FILTER (WHERE status = 'RUNNING') AS running_runs,
                          COUNT(*) FILTER (WHERE status = 'FAILED_RECOVERABLE') AS recoverable_failures,
                          COUNT(*) FILTER (
                              WHERE status IN ('FAILED_RECOVERABLE', 'FAILED_FINAL', 'BLOCKED')
                          ) AS blocked_runs,
                          COUNT(*) FILTER (WHERE status = 'COMPLETED') AS completed_runs,
                          MAX(updated_at) AS latest_update
                   FROM agent_runs""",
                one=True,
            )
            blocked_runs = bounded_int((row or {}).get("blocked_runs"))
            return self._integration(
                integration_id="agents-sdk",
                label="OpenAI Agents SDK",
                status=STATUS_DEGRADED if blocked_runs > 0 else STATUS_VERIFIED,
                required=False,
                boundary="persisted owner-scoped run state",
                evidence={
                    "totalRuns": bounded_int((row or {}).get("total_runs")),
                    "runningRuns": bounded_int((row or {}).get("running_runs")),
                    "recoverableFailures": bounded_int((row or {}).get("recoverable_failures")),
                    "blockedOrFailedRuns": blocked_runs,
                    "completedRuns": bounded_int((row or {}).get("completed_runs")),
                    "latestUpdate": str((row or {}).get("latest_update") or "")[:40] or None,
                },
                blocker="persisted_agent_failures_present" if blocked_runs > 0 else None,
                latency_ms=max(0, int((time.monotonic() - started) * 1000)),
            )
        except Exception:
            return self._integration(
                integration_id="agents-sdk",
                label="OpenAI Agents SDK",
                status=STATUS_BLOCKED,
                required=False,
                boundary="persisted owner-scoped run state",
                blocker="agents_runtime_query_failed",
                latency_ms=max(0, int((time.monotonic() - started) * 1000)),
            )

    def _knowledge_probe(self) -> dict[str, Any]:
        started = time.monotonic()
        try:
            row = self._query(
                """/* platform:probe:knowledge */
                   SELECT COUNT(*) AS sources,
                          COUNT(*) FILTER (WHERE status = 'ready') AS ready_sources,
                          COUNT(*) FILTER (WHERE status IN ('partial', 'blocked')) AS blocked_sources,
                          COALESCE(SUM(chunk_count), 0) AS chunks
                   FROM knowledge_sources""",
                one=True,
            )
            blocked_sources = bounded_int((row or {}).get("blocked_sources"))
            return self._integration(
                integration_id="knowledge",
                label="Knowledge Library",
                status=STATUS_DEGRADED if blocked_sources > 0 else STATUS_VERIFIED,
                required=False,
                boundary="PostgreSQL metadata and pgvector blocks",
                evidence={
                    "sources": bounded_int((row or {}).get("sources")),
                    "readySources": bounded_int((row or {}).get("ready_sources")),
                    "blockedSources": blocked_sources,
                    "chunks": bounded_int((row or {}).get("chunks")),
                },
                blocker="knowledge_sources_blocked" if blocked_sources > 0 else None,
                latency_ms=max(0, int((time.monotonic() - started) * 1000)),
            )
        except Exception:
            return self._integration(
                integration_id="knowledge",
                label="Knowledge Library",
                status=STATUS_BLOCKED,
                required=False,
                boundary="PostgreSQL metadata and pgvector blocks",
                blocker="knowledge_query_failed",
                latency_ms=max(0, int((time.monotonic() - started) * 1000)),
            )

    def _r2_probe(self) -> dict[str, Any]:
        started = time.monotonic()
        configured_names = (
            "R2_ENDPOINT",
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
            "R2_KNOWLEDGE_BUCKET",
            "R2_ARTIFACTS_BUCKET",
        )
        configured = all(bool(os.getenv(name, "").strip()) for name in configured_names)
        try:
            row = self._query(
                """/* platform:probe:r2 */
                   SELECT to_regclass('public.sovereign_objects') IS NOT NULL AS metadata_table,
                          CASE WHEN to_regclass('public.sovereign_objects') IS NOT NULL
                               THEN (SELECT COUNT(*) FROM sovereign_objects)
                               ELSE 0 END AS object_records""",
                one=True,
            )
            table_present = bool(row and row.get("metadata_table"))
        except Exception:
            row = {}
            table_present = False
        status = STATUS_DEFINED_NOT_RUN if configured and table_present else STATUS_BLOCKED
        blocker = (
            "provider_head_canary_not_executed"
            if status == STATUS_DEFINED_NOT_RUN
            else "r2_runtime_not_configured"
        )
        return self._integration(
            integration_id="r2",
            label="Cloudflare R2",
            status=status,
            required=False,
            boundary="private object bytes; PostgreSQL owns metadata",
            evidence={
                "configurationPresent": configured,
                "metadataTablePresent": table_present,
                "objectRecords": bounded_int((row or {}).get("object_records")),
                "credentialValuesReturned": False,
            },
            blocker=blocker,
            latency_ms=max(0, int((time.monotonic() - started) * 1000)),
        )

    def _milvus_probe(self) -> dict[str, Any]:
        started = time.monotonic()
        try:
            row = self._query(
                """/* platform:probe:milvus */
                   SELECT to_regclass('public.vector_index_outbox') IS NOT NULL AS outbox_table,
                          to_regclass('public.knowledge_learning_candidates') IS NOT NULL AS candidate_table""",
                one=True,
            )
            outbox_present = bool(row and row.get("outbox_table"))
            candidate_present = bool(row and row.get("candidate_table"))
        except Exception:
            outbox_present = False
            candidate_present = False
        status = STATUS_DEFINED_NOT_RUN if outbox_present and candidate_present else STATUS_BLOCKED
        return self._integration(
            integration_id="milvus",
            label="Milvus Projection",
            status=status,
            required=False,
            boundary="outbox projection only; pgvector remains canonical",
            evidence={
                "outboxTablePresent": outbox_present,
                "candidateTablePresent": candidate_present,
                "directDatabaseAccess": False,
            },
            blocker=(
                "milvus_consumer_runtime_not_probed"
                if status == STATUS_DEFINED_NOT_RUN
                else "milvus_outbox_migration_missing"
            ),
            latency_ms=max(0, int((time.monotonic() - started) * 1000)),
        )

    def integrations(self) -> list[dict[str, Any]]:
        return [
            self._postgres_probe(),
            self._pgvector_probe(),
            self._litellm_probe(),
            self._agents_probe(),
            self._knowledge_probe(),
            self._r2_probe(),
            self._milvus_probe(),
            self._integration(
                integration_id="patchmon",
                label="PatchMon",
                status=STATUS_ISOLATED,
                required=False,
                boundary="private MCP/host-broker control plane; no backend DB or Docker-socket access",
                evidence={"directBackendConnection": False},
                blocker="inspect_through_patchmon_operator",
            ),
            self._integration(
                integration_id="redis",
                label="Redis",
                status=STATUS_ISOLATED,
                required=False,
                boundary="not a source of truth and not a direct backend dependency",
                evidence={"directBackendConnection": False},
            ),
        ]

    def statistics(self) -> dict[str, Any]:
        try:
            row = self._query(
                """/* platform:statistics */
                   SELECT
                     (SELECT COUNT(*) FROM admin_users) AS users_total,
                     (SELECT COUNT(*) FROM admin_users WHERE is_banned = true) AS users_banned,
                     (SELECT COUNT(*) FROM admin_users WHERE last_active_at >= NOW() - INTERVAL '30 days') AS users_active_30d,
                     (SELECT COUNT(*) FROM agent_runs) AS agent_runs_total,
                     (SELECT COUNT(*) FROM agent_runs WHERE status = 'COMPLETED') AS agent_runs_completed,
                     (SELECT COUNT(*) FROM agent_runs WHERE status IN ('FAILED_RECOVERABLE', 'FAILED_FINAL', 'BLOCKED')) AS agent_runs_blocked,
                     (SELECT COUNT(*) FROM knowledge_sources) AS knowledge_sources,
                     (SELECT COUNT(*) FROM knowledge_blocks WHERE embedding IS NOT NULL) AS knowledge_vectors,
                     (SELECT COUNT(*) FROM llm_routes WHERE disabled = false) AS active_llm_routes,
                     (SELECT COUNT(*) FROM llm_usage_settlements WHERE created_at >= NOW() - INTERVAL '24 hours') AS llm_requests_24h,
                     (SELECT COALESCE(SUM(total_tokens), 0) FROM llm_usage_settlements WHERE created_at >= NOW() - INTERVAL '24 hours') AS llm_tokens_24h,
                     (SELECT COALESCE(SUM(provider_cost_usd), 0) FROM llm_usage_settlements WHERE created_at >= NOW() - INTERVAL '24 hours') AS provider_cost_usd_24h,
                     (SELECT COUNT(*) FROM platform_runtime_evidence) AS evidence_total,
                     (SELECT MAX(observed_at) FROM platform_runtime_evidence) AS latest_evidence_at,
                     (SELECT COALESCE(MAX(id), 0) FROM schema_migrations) AS latest_migration""",
                one=True,
            ) or {}
            return {
                "status": STATUS_VERIFIED,
                "users": {
                    "total": bounded_int(row.get("users_total")),
                    "active30d": bounded_int(row.get("users_active_30d")),
                    "banned": bounded_int(row.get("users_banned")),
                },
                "agents": {
                    "total": bounded_int(row.get("agent_runs_total")),
                    "completed": bounded_int(row.get("agent_runs_completed")),
                    "blockedOrFailed": bounded_int(row.get("agent_runs_blocked")),
                },
                "knowledge": {
                    "sources": bounded_int(row.get("knowledge_sources")),
                    "vectors": bounded_int(row.get("knowledge_vectors")),
                },
                "llm24h": {
                    "requests": bounded_int(row.get("llm_requests_24h")),
                    "tokens": bounded_int(row.get("llm_tokens_24h")),
                    "providerCostUsd": float(row.get("provider_cost_usd_24h") or 0),
                    "activeRoutes": bounded_int(row.get("active_llm_routes")),
                },
                "evidence": {
                    "total": bounded_int(row.get("evidence_total")),
                    "latestAt": str(row.get("latest_evidence_at") or "")[:40] or None,
                },
                "database": {
                    "latestMigration": bounded_int(row.get("latest_migration"), maximum=100_000),
                },
                "calculatedAt": utc_now(),
            }
        except Exception:
            return {
                "status": STATUS_BLOCKED,
                "blocker": "platform_statistics_query_failed",
                "users": None,
                "agents": None,
                "knowledge": None,
                "llm24h": None,
                "evidence": None,
                "database": None,
                "calculatedAt": utc_now(),
            }

    @staticmethod
    def _overall_status(
        integrations: list[dict[str, Any]],
        runtime: dict[str, Any],
        statistics: dict[str, Any] | None = None,
    ) -> str:
        required = [item for item in integrations if item.get("required")]
        if any(item.get("status") == STATUS_BLOCKED for item in required):
            return STATUS_BLOCKED
        if any(
            item.get("status") in {STATUS_DEGRADED, STATUS_DEFINED_NOT_RUN}
            for item in required
        ):
            return STATUS_DEGRADED
        if (
            not runtime.get("sourceRevisionVerified")
            or (statistics is not None and statistics.get("status") != STATUS_VERIFIED)
            or any(
                item.get("status")
                in {STATUS_BLOCKED, STATUS_DEGRADED, STATUS_DEFINED_NOT_RUN}
                for item in integrations
            )
        ):
            return STATUS_DEGRADED
        return STATUS_VERIFIED

    def overview(self) -> dict[str, Any]:
        runtime = self.runtime_identity()
        integrations = self.integrations()
        statistics = self.statistics()
        overall_status = self._overall_status(integrations, runtime, statistics)
        return {
            "ok": overall_status == STATUS_VERIFIED,
            "status": overall_status,
            "schemaVersion": SCHEMA_VERSION,
            "mode": "PROTOTYPE_TO_PLATFORM",
            "runtime": runtime,
            "statistics": statistics,
            "integrations": integrations,
            "generatedAt": utc_now(),
            "truthNotice": "Only live probes are verified. Configured, isolated, or unprobed dependencies remain explicitly non-green.",
        }

    def list_evidence(self, limit: int) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(int(limit), 100))
        rows = self._query(
            """/* platform:evidence:list */
               SELECT id::text, request_id::text AS "requestId",
                      actor_id::text AS "actorId", scope, status,
                      source_revision AS "sourceRevision",
                      runtime_identity::text AS "runtimeIdentity",
                      evidence_sha256 AS "evidenceSha256", evidence,
                      to_char(observed_at, 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') AS "observedAt"
               FROM platform_runtime_evidence
               ORDER BY observed_at DESC
               LIMIT %s""",
            (bounded_limit,),
        )
        return [dict(row) for row in (rows or [])]

    def _active_model_ids(self) -> set[str]:
        rows = self._query(
            """/* platform:models:active */
               SELECT model_id
               FROM llm_routes
               WHERE disabled = false AND provider = 'litellm'
               ORDER BY priority ASC
               LIMIT 100"""
        )
        return {
            bounded_text(row.get("model_id"), maximum=200)
            for row in (rows or [])
            if bounded_text(row.get("model_id"), maximum=200)
        }

    def _enforce_completion_cooldown(self, actor_id: str) -> None:
        row = self._query(
            """/* platform:canary:cooldown */
               SELECT GREATEST(
                   0,
                   CEIL(EXTRACT(EPOCH FROM (
                       MAX(observed_at) + INTERVAL '30 seconds' - NOW()
                   )))
               )::int AS retry_after
               FROM platform_runtime_evidence
               WHERE actor_id = %s::uuid
                 AND scope = 'completion'
                 AND observed_at > NOW() - INTERVAL '30 seconds'""",
            (actor_id,),
            one=True,
        )
        retry_after = bounded_int((row or {}).get("retry_after"), maximum=30)
        if retry_after > 0:
            raise PlatformCanaryRateLimited(retry_after)

    def _persist_evidence(
        self,
        *,
        request_id: str,
        actor_id: str,
        scope: str,
        status: str,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        runtime = self.runtime_identity()
        digest = evidence_sha256(evidence)
        evidence_id = str(uuid.uuid4())
        try:
            row = self._query(
                """/* platform:evidence:insert */
                   INSERT INTO platform_runtime_evidence (
                       id, request_id, actor_id, scope, status,
                       source_revision, runtime_identity,
                       evidence_sha256, evidence
                   )
                   VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s::uuid, %s, %s::jsonb)
                   RETURNING id::text,
                             to_char(observed_at, 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') AS "observedAt" """,
                (
                    evidence_id,
                    request_id,
                    actor_id,
                    scope,
                    status,
                    runtime["sourceRevision"],
                    runtime["runtimeId"],
                    digest,
                    json.dumps(evidence, ensure_ascii=False, sort_keys=True),
                ),
                one=True,
                write=True,
            )
        except Exception as exc:
            raise PlatformEvidenceWriteError("platform_evidence_write_failed") from exc
        if not row or str(row.get("id") or "") != evidence_id:
            raise PlatformEvidenceWriteError("platform_evidence_readback_failed")
        return {
            "id": evidence_id,
            "evidenceSha256": digest,
            "observedAt": row.get("observedAt"),
            "readbackVerified": True,
        }

    def run_canary(
        self,
        *,
        request_id: str,
        actor_id: str,
        scope: str,
        model_id: str | None = None,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        normalized_scope = bounded_text(scope, maximum=30)
        if normalized_scope not in {"readiness", "completion"}:
            raise ValueError("platform_canary_scope_invalid")

        runtime = self.runtime_identity()
        if normalized_scope == "readiness":
            integrations = self.integrations()
            status = self._overall_status(integrations, runtime)
            evidence_payload = {
                "scope": normalized_scope,
                "runtime": runtime,
                "integrations": integrations,
                "completedAt": utc_now(),
                "secretValuesReturned": False,
            }
        else:
            if confirmed is not True:
                raise ValueError("platform_completion_confirmation_required")
            normalized_model = bounded_text(model_id, maximum=200)
            if not normalized_model or normalized_model not in self._active_model_ids():
                raise PlatformModelRejected("platform_completion_model_not_active")
            self._enforce_completion_cooldown(actor_id)
            database = self._postgres_probe()
            try:
                completion = self._litellm_completion_canary(normalized_model)
            except Exception:
                completion = {
                    "ok": False,
                    "health": STATUS_BLOCKED,
                    "blocker": "litellm_completion_exception",
                    "completionVerified": False,
                    "evidence": {},
                }
            completion_ok = bool(
                completion.get("ok")
                and completion.get("completionVerified")
                and database.get("status") == STATUS_VERIFIED
            )
            status = STATUS_VERIFIED if completion_ok else STATUS_BLOCKED
            evidence_payload = {
                "scope": normalized_scope,
                "runtime": runtime,
                "database": database,
                "modelId": normalized_model,
                "completion": {
                    "ok": bool(completion.get("ok")),
                    "health": bounded_text(completion.get("health"), maximum=40),
                    "blocker": bounded_text(completion.get("blocker"), maximum=120) or None,
                    "httpStatus": completion.get("httpStatus"),
                    "responseTimeMs": completion.get("responseTimeMs"),
                    "readinessVerified": bool(completion.get("readinessVerified")),
                    "completionVerified": bool(completion.get("completionVerified")),
                    "evidence": completion.get("evidence") if isinstance(completion.get("evidence"), dict) else {},
                },
                "completedAt": utc_now(),
                "secretValuesReturned": False,
            }

        receipt = self._persist_evidence(
            request_id=request_id,
            actor_id=actor_id,
            scope=normalized_scope,
            status=status,
            evidence=evidence_payload,
        )
        return {
            "ok": status == STATUS_VERIFIED,
            "status": status,
            "schemaVersion": SCHEMA_VERSION,
            "requestId": request_id,
            "scope": normalized_scope,
            "evidence": evidence_payload,
            "receipt": receipt,
        }
