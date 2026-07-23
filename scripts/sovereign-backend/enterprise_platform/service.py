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

_BOOTED_AT = utc_now()
_RUNTIME_ID = str(uuid.uuid4())


class PlatformEvidenceWriteError(RuntimeError):
    pass


class EnterprisePlatformService:
    """Coordinates bounded probes without turning the admin API into a shell or SQL console."""

    def __init__(self, *, query: QueryFn):
        self._query = query

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
                          to_regclass('public.platform_runtime_evidence') IS NOT NULL AS evidence_table,
                          to_regclass('public.llm_route_attempts') IS NOT NULL AS revolver_attempts,
                          to_regclass('public.llm_route_revolver_state') IS NOT NULL AS revolver_state,
                          to_regclass('public.uq_credit_packages_name') IS NOT NULL AS package_uniqueness,
                          EXISTS (
                              SELECT 1 FROM information_schema.columns
                              WHERE table_schema=current_schema()
                                AND table_name='transactions'
                                AND column_name='provider_tx_id'
                          ) AS transaction_receipts""",
                one=True,
            )
            latency = max(0, int((time.monotonic() - started) * 1000))
            evidence_table = bool(row and row.get("evidence_table"))
            release_schema_ready = bool(
                row
                and evidence_table
                and row.get("revolver_attempts")
                and row.get("revolver_state")
                and row.get("package_uniqueness")
                and row.get("transaction_receipts")
            )
            migration_contract = 27 if release_schema_ready else 25 if evidence_table else 0
            return self._integration(
                integration_id="postgresql",
                label="PostgreSQL / Supabase",
                status=STATUS_VERIFIED if release_schema_ready else STATUS_BLOCKED,
                required=True,
                boundary="transactional source of truth",
                evidence={
                    "database": bounded_text((row or {}).get("database"), maximum=80),
                    "latestMigration": migration_contract,
                    "evidenceTablePresent": evidence_table,
                    "releaseSchemaVerified": release_schema_ready,
                },
                blocker=None if release_schema_ready else "platform_schema_contract_incomplete",
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
        """Report direct route truth; the method name remains API-compatible only."""
        started = time.monotonic()
        try:
            row = self._query(
                """/* platform:probe:llm-routing */
                   SELECT
                     COUNT(*) FILTER (
                       WHERE disabled=false
                         AND lower(COALESCE(runtime_kind, provider))='freellm'
                         AND COALESCE((config->>'canaryVerified')::boolean, false)=true
                     ) AS freellm_ready,
                     COUNT(*) FILTER (
                       WHERE disabled=false
                         AND lower(COALESCE(runtime_kind, provider))='openrouter'
                         AND COALESCE((config->>'canaryVerified')::boolean, false)=true
                     ) AS openrouter_ready,
                     COUNT(*) FILTER (
                       WHERE disabled=false
                         AND lower(COALESCE(runtime_kind, provider))='litellm'
                     ) AS litellm_active
                   FROM llm_routes""",
                one=True,
            ) or {}
        except Exception:
            row = {}
        freellm_ready = bounded_int(row.get("freellm_ready"))
        openrouter_ready = bounded_int(row.get("openrouter_ready"))
        litellm_active = bounded_int(row.get("litellm_active"))
        direct_route_ready = freellm_ready > 0 or openrouter_ready > 0
        routing_ready = direct_route_ready and litellm_active == 0
        blocker = None
        if litellm_active > 0:
            blocker = "legacy_litellm_route_still_active"
        elif not direct_route_ready:
            blocker = "no_verified_direct_llm_route_available"
        return self._integration(
            integration_id="llm-routing",
            label="OpenRouter Paid + FreeLLM direkt",
            status=STATUS_VERIFIED if routing_ready else STATUS_BLOCKED,
            required=True,
            boundary="Paid ausschließlich direkt über OpenRouter; Free ausschließlich direkt über FreeLLM",
            evidence={
                "freellmReadyRoutes": freellm_ready,
                "openrouterReadyRoutes": openrouter_ready,
                "legacyLiteLlmActiveRoutes": litellm_active,
                "legacyProviderProbePerformed": False,
                "routingPolicy": "direct-freellm-free-and-direct-openrouter-paid-only",
            },
            blocker=blocker,
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

    def _milvus_projection_counts(self) -> dict[str, Any]:
        table_state = self._query(
            """/* platform:probe:milvus:tables */
               SELECT to_regclass('public.vector_index_outbox') IS NOT NULL AS outbox_table,
                      to_regclass('public.knowledge_learning_candidates') IS NOT NULL AS candidate_table""",
            one=True,
        ) or {}
        outbox_present = bool(table_state.get("outbox_table"))
        candidate_present = bool(table_state.get("candidate_table"))
        if not outbox_present:
            return {
                "outboxTablePresent": False,
                "candidateTablePresent": candidate_present,
                "total": 0,
                "indexed": 0,
                "pending": 0,
                "syncing": 0,
                "blocked": 0,
                "knowledgeBlocks": 0,
                "agentPatterns": 0,
            }
        row = self._query(
            """/* platform:probe:milvus:counts */
               SELECT COUNT(*) AS total,
                      COUNT(*) FILTER (WHERE status='indexed') AS indexed,
                      COUNT(*) FILTER (WHERE status='pending') AS pending,
                      COUNT(*) FILTER (WHERE status='syncing') AS syncing,
                      COUNT(*) FILTER (WHERE status='blocked') AS blocked,
                      COUNT(*) FILTER (WHERE entity_type='knowledge_block') AS knowledge_blocks,
                      COUNT(*) FILTER (WHERE entity_type='agent_pattern') AS agent_patterns
               FROM vector_index_outbox
               WHERE target_index='milvus'""",
            one=True,
        ) or {}
        return {
            "outboxTablePresent": True,
            "candidateTablePresent": candidate_present,
            "total": bounded_int(row.get("total")),
            "indexed": bounded_int(row.get("indexed")),
            "pending": bounded_int(row.get("pending")),
            "syncing": bounded_int(row.get("syncing")),
            "blocked": bounded_int(row.get("blocked")),
            "knowledgeBlocks": bounded_int(row.get("knowledge_blocks")),
            "agentPatterns": bounded_int(row.get("agent_patterns")),
        }

    def _milvus_probe(self) -> dict[str, Any]:
        started = time.monotonic()
        try:
            counts = self._milvus_projection_counts()
        except Exception:
            counts = {
                "outboxTablePresent": False,
                "candidateTablePresent": False,
                "total": 0,
                "indexed": 0,
                "pending": 0,
                "syncing": 0,
                "blocked": 0,
                "knowledgeBlocks": 0,
                "agentPatterns": 0,
            }
        outbox_present = bool(counts["outboxTablePresent"])
        candidate_present = bool(counts["candidateTablePresent"])
        blocked = bounded_int(counts.get("blocked"))
        pending = bounded_int(counts.get("pending"))
        syncing = bounded_int(counts.get("syncing"))
        if not outbox_present or not candidate_present:
            status = STATUS_BLOCKED
            blocker = "milvus_outbox_migration_missing"
        elif blocked > 0:
            status = STATUS_DEGRADED
            blocker = "milvus_projection_blocked"
        else:
            status = STATUS_DEFINED_NOT_RUN
            blocker = (
                "milvus_projection_pending"
                if pending > 0 or syncing > 0
                else "milvus_collection_readback_not_probed"
            )
        return self._integration(
            integration_id="milvus",
            label="Milvus Projection",
            status=status,
            required=False,
            boundary="outbox projection receipts; pgvector remains canonical",
            evidence={
                **counts,
                "directDatabaseAccess": False,
                "directCollectionReadback": False,
            },
            blocker=blocker,
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
                     CASE
                       WHEN to_regclass('public.llm_route_attempts') IS NOT NULL
                        AND to_regclass('public.llm_route_revolver_state') IS NOT NULL
                        AND to_regclass('public.uq_credit_packages_name') IS NOT NULL
                        AND EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema=current_schema()
                              AND table_name='transactions'
                              AND column_name='provider_tx_id'
                        )
                       THEN 27
                       WHEN to_regclass('public.platform_runtime_evidence') IS NOT NULL
                       THEN 25
                       ELSE 0
                     END AS latest_migration""",
                one=True,
            ) or {}
            try:
                milvus = self._milvus_projection_counts()
            except Exception:
                milvus = {
                    "total": 0,
                    "indexed": 0,
                    "pending": 0,
                    "syncing": 0,
                    "blocked": 0,
                    "knowledgeBlocks": 0,
                    "agentPatterns": 0,
                }
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
                    "pgvectorVectors": bounded_int(row.get("knowledge_vectors")),
                    "milvusProjected": bounded_int(milvus.get("total")),
                    "milvusIndexed": bounded_int(milvus.get("indexed")),
                    "milvusPending": bounded_int(milvus.get("pending")),
                    "milvusSyncing": bounded_int(milvus.get("syncing")),
                    "milvusBlocked": bounded_int(milvus.get("blocked")),
                    "milvusKnowledgeBlocks": bounded_int(milvus.get("knowledgeBlocks")),
                    "milvusAgentPatterns": bounded_int(milvus.get("agentPatterns")),
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
        if normalized_scope == "completion":
            raise ValueError("platform_legacy_completion_canary_removed")
        if normalized_scope != "readiness":
            raise ValueError("platform_canary_scope_invalid")

        runtime = self.runtime_identity()
        integrations = self.integrations()
        status = self._overall_status(integrations, runtime)
        evidence_payload = {
            "scope": normalized_scope,
            "runtime": runtime,
            "integrations": integrations,
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
