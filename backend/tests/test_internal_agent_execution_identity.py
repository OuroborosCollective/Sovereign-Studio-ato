from __future__ import annotations

from pathlib import Path

import pytest

import backend.agent_runtime.agent_run_receipts as receipts


REVISION = "a" * 40
DIGEST = "sha256:" + "b" * 64


def test_internal_backend_identity_requires_no_mcp_broker(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", REVISION)
    monkeypatch.setenv("SOVEREIGN_IMAGE_DIGEST", DIGEST)
    monkeypatch.setattr(
        receipts,
        "_broker_call",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("MCP broker must not be called")),
    )

    identity = receipts.read_backend_runtime_identity()

    assert identity.revision == REVISION
    assert identity.image_digest == DIGEST
    assert identity.revision_verified is True
    assert identity.image_digest_verified is True


def test_internal_backend_identity_fails_closed_on_unbound_runtime(monkeypatch) -> None:
    monkeypatch.delenv("SOVEREIGN_SOURCE_REVISION", raising=False)
    monkeypatch.delenv("SOVEREIGN_IMAGE_DIGEST", raising=False)
    with pytest.raises(receipts.ReceiptIdentityBlocked) as error:
        receipts.read_backend_runtime_identity()
    assert error.value.failure_family == "BACKEND_RUNTIME_REVISION_UNVERIFIED"


def test_execution_receipt_names_backend_identity_without_mcp_aliases() -> None:
    receipt = receipts.build_agent_execution_receipt(
        sequence=0,
        repository="OuroborosCollective/Sovereign-Studio-ato",
        base_commit_sha=REVISION,
        execution_runtime_kind="backend",
        execution_revision=REVISION,
        execution_image_digest=DIGEST,
        execution_revision_verified=True,
        execution_image_digest_verified=True,
        agent_run_id="run-internal-runtime",
        tool_name="git-status",
        call_id="tool-call-internal-runtime",
        operation_identity="agent-repository-tool:free_single_agent:git-status",
        input_sha256="1" * 64,
        output_sha256="2" * 64,
        diff_sha256="3" * 64,
        test_evidence_sha256="4" * 64,
        evidence_gate_result="PASS",
        mutation_performed=False,
        observed_effect="read",
        authoritative_readback_sha256="5" * 64,
        previous_receipt_sha256="0" * 64,
    )
    body = receipt["body"]
    assert body["schema_version"] == "sovereign.agent-execution-receipt.v1"
    assert body["execution_runtime_kind"] == "backend"
    assert body["execution_revision"] == REVISION
    assert body["execution_image_digest"] == DIGEST
    assert "mcp_revision" not in body
    assert "mcp_image_digest" not in body


def test_repository_toolplane_is_backend_bound_and_mirrored() -> None:
    root = Path(__file__).resolve().parents[2]
    canonical = (root / "backend/agent_runtime/cognitive_repository_tools.py").read_text("utf-8")
    mirror = (root / "scripts/sovereign-backend/agent_runtime/cognitive_repository_tools.py").read_text("utf-8")
    assert canonical == mirror
    assert "read_backend_runtime_identity" in canonical
    assert "read_mcp_runtime_identity" not in canonical
    assert "SOVEREIGN_MCP_BROKER_SOCKET" not in canonical


def test_runtime_identity_migration_preserves_historical_rows_without_update() -> None:
    root = Path(__file__).resolve().parents[2]
    canonical = (root / "backend/migrations/062_agent_execution_runtime_identity.sql").read_text("utf-8")
    mirror = (root / "scripts/sovereign-backend/migrations/062_agent_execution_runtime_identity.sql").read_text("utf-8")
    assert canonical == mirror
    assert "sovereign.agent-execution-receipt.v1" in canonical
    assert "execution_runtime_kind IN ('backend', 'mcp')" in canonical
    assert "ALTER COLUMN mcp_revision DROP NOT NULL" in canonical
    assert "base_commit_sha ~ '^[0-9a-f]{40}$'" in canonical
    assert "UPDATE agent_run_receipts" not in canonical
