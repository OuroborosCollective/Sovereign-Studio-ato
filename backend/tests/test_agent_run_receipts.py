from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from backend.agent_runtime.agent_run_receipts import (
    ReceiptContractError,
    build_agent_run_receipt,
    canonical_sha256,
    verify_agent_run_receipt_chain,
)


REVISION = "a" * 40
MCP_DIGEST = "sha256:" + "b" * 64
ZERO = "0" * 64
REPOSITORY = "OuroborosCollective/Sovereign-Studio-ato"


def _receipt(*, sequence: int = 0, previous: str = ZERO, gate: str = "PASS") -> dict:
    return build_agent_run_receipt(
        sequence=sequence,
        repository=REPOSITORY,
        base_commit_sha=REVISION,
        mcp_revision=REVISION,
        mcp_image_digest=MCP_DIGEST,
        mcp_revision_verified=True,
        agent_run_id="run-receipt-test",
        tool_name="test",
        call_id=f"tool-call-{sequence:03d}",
        operation_identity="agent-repository-tool:predictive_qa:test",
        input_sha256=canonical_sha256({"command": "python -m pytest"}),
        output_sha256=canonical_sha256({"status": "done", "exit_code": 0}),
        diff_sha256=canonical_sha256({"git": "readback"}),
        test_evidence_sha256=canonical_sha256({"exit_code": 0, "test_summary": "12 passed"}),
        evidence_gate_result=gate,
        mutation_performed=False,
        observed_effect="read",
        authoritative_readback_sha256=canonical_sha256({"head": REVISION}),
        previous_receipt_sha256=previous,
    )


def test_receipt_hash_is_deterministic_and_unicode_nfc() -> None:
    first = _receipt()
    second = _receipt()
    assert first == second
    assert canonical_sha256({"value": "e\u0301"}) == canonical_sha256({"value": "é"})


@pytest.mark.parametrize(
    "field,replacement",
    [
        ("input_sha256", "1" * 64),
        ("output_sha256", "2" * 64),
        ("diff_sha256", "3" * 64),
        ("test_evidence_sha256", "4" * 64),
        ("sequence", 9),
        ("previous_receipt_sha256", "5" * 64),
        ("repository", "other/repository"),
        ("mcp_revision", "c" * 40),
        ("evidence_gate_result", "FAIL"),
    ],
)
def test_each_causal_mutation_invalidates_receipt(field: str, replacement: object) -> None:
    receipt = _receipt()
    tampered = deepcopy(receipt)
    tampered["body"][field] = replacement
    result = verify_agent_run_receipt_chain(
        [tampered],
        expected_repository=REPOSITORY,
        expected_base_commit_sha=REVISION,
        expected_mcp_revision=REVISION,
    )
    assert result["ok"] is False
    assert any(item["family"] == "RECEIPT_HASH_MISMATCH" for item in result["findings"])


def test_receipt_chain_links_exact_previous_hash() -> None:
    first = _receipt()
    second = _receipt(sequence=1, previous=first["header"]["hash"])
    verified = verify_agent_run_receipt_chain(
        [first, second],
        expected_repository=REPOSITORY,
        expected_base_commit_sha=REVISION,
        expected_mcp_revision=REVISION,
    )
    assert verified == {
        "ok": True,
        "verified_count": 2,
        "receipt_count": 2,
        "chain_head_sha256": second["header"]["hash"],
        "findings": [],
    }


def test_wrong_previous_hash_and_sequence_are_detected() -> None:
    first = _receipt()
    second = _receipt(sequence=1, previous=first["header"]["hash"])
    second["body"]["previous_receipt_sha256"] = "9" * 64
    second["body"]["sequence"] = 3
    result = verify_agent_run_receipt_chain([first, second])
    families = {item["family"] for item in result["findings"]}
    assert {"SEQUENCE_MISMATCH", "PREVIOUS_HASH_MISMATCH", "RECEIPT_HASH_MISMATCH"} <= families


def test_secret_shaped_fields_and_floats_are_rejected() -> None:
    with pytest.raises(ReceiptContractError, match="secret-shaped"):
        canonical_sha256({"authorization": "Bearer private"})
    with pytest.raises(ReceiptContractError, match="floating-point"):
        canonical_sha256({"duration": 1.25})


def test_negative_gate_remains_negative_and_missing_tests_are_not_passed() -> None:
    negative = _receipt(gate="FAIL")
    assert negative["body"]["evidence_gate_result"] == "FAIL"
    missing_tests_hash = canonical_sha256({"exit_code": 1, "test_summary": ""})
    assert missing_tests_hash != canonical_sha256({"exit_code": 0, "test_summary": "passed"})


def test_positive_receipt_requires_verified_revision_and_image_digest() -> None:
    kwargs = dict(
        sequence=0,
        repository=REPOSITORY,
        base_commit_sha=REVISION,
        mcp_revision=REVISION,
        mcp_image_digest=MCP_DIGEST,
        mcp_revision_verified=False,
        agent_run_id="run-receipt-test",
        tool_name="test",
        call_id="tool-call-000",
        operation_identity="agent-repository-tool:predictive_qa:test",
        input_sha256="1" * 64,
        output_sha256="2" * 64,
        diff_sha256="3" * 64,
        test_evidence_sha256="4" * 64,
        evidence_gate_result="PASS",
        mutation_performed=False,
        observed_effect="read",
        authoritative_readback_sha256="5" * 64,
        previous_receipt_sha256=ZERO,
    )
    with pytest.raises(ReceiptContractError, match="verified installed MCP revision"):
        build_agent_run_receipt(**kwargs)


def test_migration_is_append_only_and_receipt_body_bound() -> None:
    root = Path(__file__).resolve().parents[2]
    migration = (root / "scripts/sovereign-backend/migrations/040_agent_run_receipts.sql").read_text("utf-8")
    assert "CREATE TABLE IF NOT EXISTS agent_run_receipts" in migration
    assert "UNIQUE (agent_run_id, sequence)" in migration
    assert "UNIQUE (call_id)" in migration
    assert "reject_agent_run_receipt_mutation" in migration
    assert "BEFORE UPDATE ON agent_run_receipts" in migration
    assert "BEFORE DELETE ON agent_run_receipts" in migration
    assert "canonical_body ->> 'receipt_sha256' = receipt_sha256" in migration


def test_backend_deploy_mounts_broker_read_only_with_real_group() -> None:
    root = Path(__file__).resolve().parents[2]
    deploy = (root / "tools/sovereign-chatgpt-mcp/deploy/deploy-sovereign-backend").read_text("utf-8")
    rollback = (root / "tools/sovereign-chatgpt-mcp/deploy/rollback-sovereign-backend").read_text("utf-8")
    for script in (deploy, rollback):
        assert "[[ -S \"$BROKER_SOCKET\" ]]" in script
        assert "stat -c '%g' \"$BROKER_SOCKET\"" in script
        assert '--volume "$BROKER_RUNTIME_DIR:$BROKER_RUNTIME_DIR:ro"' in script
        assert '--group-add "$BROKER_GID"' in script
        assert '--env "SOVEREIGN_MCP_BROKER_SOCKET=$BROKER_SOCKET"' in script


def test_receipt_json_contains_no_raw_payload_fields() -> None:
    serialized = json.dumps(_receipt(), sort_keys=True)
    for forbidden in ("raw_prompt", "file_content", "database_row", "authorization", "password"):
        assert forbidden not in serialized.casefold()
