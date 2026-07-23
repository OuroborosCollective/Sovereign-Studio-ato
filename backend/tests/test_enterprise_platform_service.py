from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from enterprise_platform.service import EnterprisePlatformService


ADMIN_ID = "11111111-1111-4111-8111-111111111111"
REQUEST_ID = "22222222-2222-4222-8222-222222222222"
SOURCE_REVISION = "a" * 40
IMAGE_DIGEST = "sha256:" + "b" * 64


class QueryDouble:
    """Contract-level DB test double; production probes still execute only against PostgreSQL."""

    def __init__(
        self,
        *,
        freellm_ready: int = 1,
        openrouter_ready: int = 2,
        litellm_active: int = 0,
    ):
        self.freellm_ready = freellm_ready
        self.openrouter_ready = openrouter_ready
        self.litellm_active = litellm_active
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
        if "platform:probe:llm-routing" in statement:
            return {
                "freellm_ready": self.freellm_ready,
                "openrouter_ready": self.openrouter_ready,
                "litellm_active": self.litellm_active,
            }
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


def service(query: QueryDouble) -> EnterprisePlatformService:
    return EnterprisePlatformService(query=query)


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


def test_completion_canary_is_removed_without_provider_or_evidence_call() -> None:
    query = QueryDouble()
    subject = service(query)

    with pytest.raises(ValueError, match="platform_legacy_completion_canary_removed"):
        subject.run_canary(
            request_id=REQUEST_ID,
            actor_id=ADMIN_ID,
            scope="completion",
            model_id="sovereign-fast",
            confirmed=True,
        )

    assert not any("platform:evidence:insert" in item for item in query.calls)


def test_readiness_canary_persists_sha256_receipt_after_exact_readback() -> None:
    query = QueryDouble()
    subject = service(query)

    result = subject.run_canary(
        request_id=REQUEST_ID,
        actor_id=ADMIN_ID,
        scope="readiness",
    )

    assert result["scope"] == "readiness"
    assert result["receipt"]["readbackVerified"] is True
    assert len(result["receipt"]["evidenceSha256"]) == 64
    assert result["evidence"]["secretValuesReturned"] is False
    assert result["evidence"]["runtime"]["sourceRevision"] == SOURCE_REVISION
    assert any("platform:evidence:insert" in item for item in query.calls)


def test_direct_route_probe_exposes_only_direct_counts_and_no_credentials() -> None:
    query = QueryDouble(freellm_ready=3, openrouter_ready=4, litellm_active=0)
    result = service(query)._litellm_probe()

    assert result["status"] == "verified"
    assert result["evidence"] == {
        "freellmReadyRoutes": 3,
        "openrouterReadyRoutes": 4,
        "legacyLiteLlmActiveRoutes": 0,
        "legacyProviderProbePerformed": False,
        "routingPolicy": "direct-freellm-free-and-direct-openrouter-paid-only",
    }
    serialized = str(result).lower()
    assert "api_key" not in serialized
    assert "secret_access_key" not in serialized


def test_active_legacy_litellm_route_blocks_direct_routing_contract() -> None:
    query = QueryDouble(freellm_ready=1, openrouter_ready=2, litellm_active=1)
    result = service(query)._litellm_probe()

    assert result["status"] == "blocked"
    assert result["blocker"] == "legacy_litellm_route_still_active"
    assert result["evidence"]["legacyProviderProbePerformed"] is False


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


