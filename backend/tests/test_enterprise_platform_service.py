from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from enterprise_platform.service import (
    EnterprisePlatformService,
    PlatformCanaryRateLimited,
    PlatformModelRejected,
)


ADMIN_ID = "11111111-1111-4111-8111-111111111111"
REQUEST_ID = "22222222-2222-4222-8222-222222222222"
SOURCE_REVISION = "a" * 40
IMAGE_DIGEST = "sha256:" + "b" * 64


class QueryDouble:
    """Contract-level DB test double; production probes still execute only against PostgreSQL."""

    def __init__(self, *, retry_after: int = 0):
        self.retry_after = retry_after
        self.calls: list[str] = []

    def __call__(
        self,
        statement: str,
        params: tuple[Any, ...] | None = None,
        *,
        one: bool = False,
        write: bool = False,
    ) -> Any:
        self.calls.append(statement)
        if "platform:models:active" in statement:
            return [{"model_id": "sovereign-fast"}, {"model_id": "sovereign-balanced"}]
        if "platform:canary:cooldown" in statement:
            return {"retry_after": self.retry_after}
        if "platform:probe:postgresql" in statement:
            return {
                "database": "sovereign",
                "migration_id": 25,
                "evidence_table": True,
                "revolver_attempts": True,
                "revolver_state": True,
                "package_uniqueness": True,
                "transaction_receipts": True,
            }
        if "platform:probe:milvus:tables" in statement:
            return {"outbox_table": True, "candidate_table": True}
        if "platform:probe:milvus:counts" in statement:
            return {
                "total": 7,
                "indexed": 4,
                "pending": 2,
                "syncing": 1,
                "blocked": 0,
                "knowledge_blocks": 6,
                "agent_patterns": 1,
            }
        if "platform:statistics" in statement:
            return {
                "users_total": 3,
                "users_banned": 0,
                "users_active_30d": 2,
                "agent_runs_total": 5,
                "agent_runs_completed": 4,
                "agent_runs_blocked": 1,
                "knowledge_sources": 9,
                "knowledge_vectors": 400,
                "active_llm_routes": 2,
                "llm_requests_24h": 11,
                "llm_tokens_24h": 1200,
                "provider_cost_usd_24h": 0.25,
                "evidence_total": 6,
                "latest_evidence_at": "2026-07-20T12:00:00Z",
                "latest_migration": 27,
            }
        if "platform:evidence:insert" in statement:
            assert write is True
            assert params is not None
            return {"id": params[0], "observedAt": "2026-07-19T12:00:00.000Z"}
        if "platform:evidence:list" in statement:
            return []
        raise AssertionError("Unexpected SQL contract: " + statement[:100])


@pytest.fixture(autouse=True)
def runtime_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", SOURCE_REVISION)
    monkeypatch.setenv("SOVEREIGN_IMAGE_DIGEST", IMAGE_DIGEST)
    monkeypatch.setenv("SOVEREIGN_RUNTIME_ENVIRONMENT", "test")


def service(query: QueryDouble, completion=None) -> EnterprisePlatformService:
    return EnterprisePlatformService(
        query=query,
        litellm_readiness=lambda: {
            "ok": True,
            "status": "ready",
            "db": "connected",
            "httpStatus": 200,
        },
        litellm_completion_canary=completion
        or (
            lambda model_id: {
                "ok": True,
                "health": "verified",
                "completionVerified": True,
                "readinessVerified": True,
                "httpStatus": 200,
                "responseTimeMs": 12,
                "evidence": {"modelId": model_id, "contentObserved": True},
            }
        ),
    )


def test_runtime_identity_fails_closed_for_unverified_build(monkeypatch: pytest.MonkeyPatch) -> None:
    query = QueryDouble()
    subject = service(query)
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", "main")
    monkeypatch.setenv("SOVEREIGN_IMAGE_DIGEST", "latest")

    identity = subject.runtime_identity()

    assert identity["sourceRevision"] == "unverified"
    assert identity["sourceRevisionVerified"] is False
    assert identity["imageDigest"] == "unverified"
    assert identity["imageDigestVerified"] is False


def test_overall_status_never_turns_unprobed_or_blocked_truth_green() -> None:
    runtime = {"sourceRevisionVerified": True}
    verified = {"required": True, "status": "verified"}
    unprobed = {"required": False, "status": "defined_not_run"}
    isolated = {"required": False, "status": "isolated"}
    blocked_required = {"required": True, "status": "blocked"}

    assert EnterprisePlatformService._overall_status([verified, isolated], runtime) == "verified"
    assert EnterprisePlatformService._overall_status([verified, unprobed], runtime) == "degraded"
    assert EnterprisePlatformService._overall_status([blocked_required], runtime) == "blocked"
    assert EnterprisePlatformService._overall_status(
        [verified],
        runtime,
        {"status": "blocked"},
    ) == "degraded"


def test_completion_canary_requires_confirmation_before_provider_call() -> None:
    query = QueryDouble()
    invoked: list[str] = []
    subject = service(query, completion=lambda model_id: invoked.append(model_id))

    with pytest.raises(ValueError, match="platform_completion_confirmation_required"):
        subject.run_canary(
            request_id=REQUEST_ID,
            actor_id=ADMIN_ID,
            scope="completion",
            model_id="sovereign-fast",
            confirmed=False,
        )

    assert invoked == []
    assert not any("platform:evidence:insert" in item for item in query.calls)


def test_completion_canary_rejects_non_active_model() -> None:
    query = QueryDouble()
    subject = service(query)

    with pytest.raises(PlatformModelRejected):
        subject.run_canary(
            request_id=REQUEST_ID,
            actor_id=ADMIN_ID,
            scope="completion",
            model_id="unregistered-provider-model",
            confirmed=True,
        )


def test_completion_canary_persists_sha256_receipt_after_exact_readback() -> None:
    query = QueryDouble()
    subject = service(query)

    result = subject.run_canary(
        request_id=REQUEST_ID,
        actor_id=ADMIN_ID,
        scope="completion",
        model_id="sovereign-fast",
        confirmed=True,
    )

    assert result["ok"] is True
    assert result["status"] == "verified"
    assert result["receipt"]["readbackVerified"] is True
    assert len(result["receipt"]["evidenceSha256"]) == 64
    assert result["evidence"]["secretValuesReturned"] is False
    assert result["evidence"]["runtime"]["sourceRevision"] == SOURCE_REVISION
    assert any("platform:evidence:insert" in item for item in query.calls)


def test_completion_canary_enforces_database_backed_cooldown() -> None:
    query = QueryDouble(retry_after=17)
    subject = service(query)

    with pytest.raises(PlatformCanaryRateLimited) as raised:
        subject.run_canary(
            request_id=REQUEST_ID,
            actor_id=ADMIN_ID,
            scope="completion",
            model_id="sovereign-fast",
            confirmed=True,
        )

    assert raised.value.retry_after_seconds == 17


def test_litellm_probe_exposes_only_active_aliases_and_no_credentials() -> None:
    query = QueryDouble()
    result = service(query)._litellm_probe()

    assert result["status"] == "verified"
    assert result["evidence"]["activeModelIds"] == [
        "sovereign-balanced",
        "sovereign-fast",
    ]
    serialized = str(result).lower()
    assert "api_key" not in serialized
    assert "secret_access_key" not in serialized


def test_milvus_projection_counts_are_visible_without_claiming_direct_readback() -> None:
    query = QueryDouble()
    subject = service(query)

    probe = subject._milvus_probe()
    stats = subject.statistics()

    assert probe["status"] == "defined_not_run"
    assert probe["blocker"] == "milvus_projection_pending"
    assert probe["evidence"]["indexed"] == 4
    assert probe["evidence"]["pending"] == 2
    assert probe["evidence"]["syncing"] == 1
    assert probe["evidence"]["directCollectionReadback"] is False
    assert stats["knowledge"] == {
        "sources": 9,
        "vectors": 400,
        "pgvectorVectors": 400,
        "milvusProjected": 7,
        "milvusIndexed": 4,
        "milvusPending": 2,
        "milvusSyncing": 1,
        "milvusBlocked": 0,
        "milvusKnowledgeBlocks": 6,
        "milvusAgentPatterns": 1,
    }


