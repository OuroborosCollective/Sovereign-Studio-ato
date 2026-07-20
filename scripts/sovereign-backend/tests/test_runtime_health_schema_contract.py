from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "scripts" / "sovereign-backend"
sys.path.insert(0, str(BACKEND))

from enterprise_platform.service import EnterprisePlatformService  # noqa: E402


def test_health_contract_uses_release_schema_evidence_not_legacy_ledger_id() -> None:
    app = (BACKEND / "app.py").read_text("utf-8")
    start = app.index('@app.route("/health/ready")')
    end = app.index('@app.route(', start + 1)
    readiness = app[start:end]

    assert "schema_migrations.id" not in readiness
    assert "MAX(id)" not in readiness
    assert "llm_route_revolver_state" in readiness
    assert "llm_route_attempts" in readiness
    assert "uq_credit_packages_name" in readiness
    assert "provider_tx_id" in readiness
    assert "request_fingerprint" in readiness
    assert '"requiredMigrations": [' in readiness
    assert "026_llm_free_route_revolver.sql" in readiness
    assert "027_billing_idempotency_and_package_uniqueness.sql" in readiness
    assert '"sourceRevision": os.getenv("SOVEREIGN_SOURCE_REVISION"' in readiness
    assert '"imageDigest": os.getenv("SOVEREIGN_IMAGE_DIGEST"' in readiness


def test_enterprise_postgres_probe_accepts_production_version_ledger_layout() -> None:
    statements: list[str] = []

    def query(sql: str, **_: object) -> dict[str, object]:
        statements.append(sql)
        return {
            "database": "postgres",
            "evidence_table": True,
            "revolver_attempts": True,
            "revolver_state": True,
            "package_uniqueness": True,
            "transaction_receipts": True,
        }

    service = EnterprisePlatformService(
        query=query,
        litellm_readiness=lambda: {"ok": True},
        litellm_completion_canary=lambda _model: {"ok": True},
    )
    result = service._postgres_probe()

    assert result["status"] == "verified"
    assert result["blocker"] is None
    assert result["evidence"]["latestMigration"] == 27
    assert result["evidence"]["releaseSchemaVerified"] is True
    assert statements
    assert all("schema_migrations" not in statement for statement in statements)
    assert all("MAX(id)" not in statement for statement in statements)


def test_enterprise_postgres_probe_blocks_when_release_schema_is_incomplete() -> None:
    def query(_sql: str, **_: object) -> dict[str, object]:
        return {
            "database": "postgres",
            "evidence_table": True,
            "revolver_attempts": False,
            "revolver_state": False,
            "package_uniqueness": False,
            "transaction_receipts": False,
        }

    service = EnterprisePlatformService(
        query=query,
        litellm_readiness=lambda: {"ok": True},
        litellm_completion_canary=lambda _model: {"ok": True},
    )
    result = service._postgres_probe()

    assert result["status"] == "blocked"
    assert result["blocker"] == "platform_schema_contract_incomplete"
    assert result["evidence"]["releaseSchemaVerified"] is False
