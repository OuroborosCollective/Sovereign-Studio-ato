from __future__ import annotations

import hashlib

import pytest

from tool_behavior_attestation import (
    ObservedBehavior,
    ObservedToolBehaviorReceipt,
    ToolBehaviorAttestationError,
    build_receipt,
    evaluate_verdict,
    receipt_from_mapping,
)
from tool_behavior_contract import ToolBehaviorContract, canonical_sha256


SHA_A = "a" * 40
SHA_B = "b" * 40
SHA256_A = "a" * 64
SHA256_B = "b" * 64
DIGEST_A = "sha256:" + "a" * 64


def _contract(execution_kind="LOCAL_OCI", effect_class="WORKSPACE_WRITE", **overrides) -> ToolBehaviorContract:
    base = dict(
        schema_version="sovereign.tool-behavior-contract.v1",
        tool_id="tool.canary",
        execution_kind=execution_kind,
        repository_revision=SHA_A,
        tool_registry_revision=SHA_A,
        image_digest=DIGEST_A if execution_kind == "LOCAL_OCI" else None,
        effect_class=effect_class,
        allowed_exec=("/usr/bin/true",),
        allowed_read_paths=("/workspace/repo",),
        allowed_write_paths=("/workspace/repo/out",) if effect_class != "READ_ONLY" else (),
        allowed_network_targets=("registry.example.invalid",),
        network_required=(effect_class == "EXTERNAL_WRITE"),
        max_wall_time_ms=5000,
        max_memory_bytes=256 * 1024 * 1024,
    )
    base.update(overrides)
    return ToolBehaviorContract(**base)


def _observed_ok(**overrides) -> ObservedBehavior:
    base = dict(
        observed_exec=("/usr/bin/true",),
        observed_read_paths=("/workspace/repo",),
        observed_write_paths=("/workspace/repo/out",),
        observed_network_targets=(),
        observed_wall_time_ms=10,
        observed_memory_bytes=1024,
        observed_external_effect=None,
    )
    base.update(overrides)
    return ObservedBehavior(**base)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def test_behavior_verified_for_complete_in_bounds_local_oci() -> None:
    contract = _contract()
    observed = _observed_ok()
    receipt, findings = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=observed,
        authoritative_readback_sha256=contract.contract_sha256,
        trace_artifact_sha256=SHA256_B,
    )
    assert receipt.verdict == "BEHAVIOR_VERIFIED"
    assert findings == ("BEHAVIOR_WITHIN_CONTRACT",)
    assert receipt.verify() is True
    assert receipt.behavior_contract_sha256 == contract.contract_sha256


def test_undeclared_exec_is_behavior_violation() -> None:
    contract = _contract()
    observed = _observed_ok(observed_exec=("/usr/bin/false",))
    receipt, findings = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=observed,
        authoritative_readback_sha256=contract.contract_sha256,
        trace_artifact_sha256=SHA256_B,
    )
    assert receipt.verdict == "BEHAVIOR_VIOLATION"
    assert any(f.startswith("EXEC_NOT_DECLARED") for f in findings)


def test_undeclared_write_path_is_behavior_violation() -> None:
    contract = _contract()
    observed = _observed_ok(observed_write_paths=("/workspace/repo/out", "/workspace/repo/secret",))
    receipt, findings = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=observed,
        authoritative_readback_sha256=contract.contract_sha256,
        trace_artifact_sha256=SHA256_B,
    )
    assert receipt.verdict == "BEHAVIOR_VIOLATION"
    assert any("secret" in f for f in findings)


def test_read_only_contract_write_is_behavior_violation() -> None:
    contract = _contract(effect_class="READ_ONLY")
    observed = _observed_ok(
        observed_write_paths=("/workspace/repo/out",),
        observed_external_effect=None,
    )
    receipt, findings = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=observed,
        authoritative_readback_sha256=contract.contract_sha256,
        trace_artifact_sha256=SHA256_B,
    )
    assert receipt.verdict == "BEHAVIOR_VIOLATION"
    assert any(f.startswith("WRITE_PATH_NOT_DECLARED") for f in findings)


def test_undeclared_network_target_is_behavior_violation() -> None:
    contract = _contract()
    observed = _observed_ok(observed_network_targets=("evil.example.invalid",))
    receipt, findings = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=observed,
        authoritative_readback_sha256=contract.contract_sha256,
        trace_artifact_sha256=SHA256_B,
    )
    assert receipt.verdict == "BEHAVIOR_VIOLATION"
    assert any(f.startswith("NETWORK_TARGET_NOT_DECLARED") for f in findings)


def test_wall_time_exceeded_is_behavior_violation() -> None:
    contract = _contract(max_wall_time_ms=100)
    observed = _observed_ok(observed_wall_time_ms=200)
    receipt, findings = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=observed,
        authoritative_readback_sha256=contract.contract_sha256,
        trace_artifact_sha256=SHA256_B,
    )
    assert receipt.verdict == "BEHAVIOR_VIOLATION"
    assert any(f.startswith("WALL_TIME_EXCEEDED") for f in findings)


def test_memory_exceeded_is_behavior_violation() -> None:
    contract = _contract(max_memory_bytes=100)
    observed = _observed_ok(observed_memory_bytes=200)
    receipt, findings = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=observed,
        authoritative_readback_sha256=contract.contract_sha256,
        trace_artifact_sha256=SHA256_B,
    )
    assert receipt.verdict == "BEHAVIOR_VIOLATION"
    assert any(f.startswith("MEMORY_EXCEEDED") for f in findings)


def test_external_effect_on_non_external_contract_is_violation() -> None:
    contract = _contract(effect_class="WORKSPACE_WRITE")
    observed = _observed_ok(observed_external_effect="POST https://evil.example.invalid")
    receipt, findings = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=observed,
        authoritative_readback_sha256=contract.contract_sha256,
        trace_artifact_sha256=SHA256_B,
    )
    assert receipt.verdict == "BEHAVIOR_VIOLATION"
    assert any(f.startswith("EXTERNAL_EFFECT_NOT_PERMITTED") for f in findings)


def test_external_write_contract_missing_external_effect_is_unverified() -> None:
    contract = _contract(effect_class="EXTERNAL_WRITE", network_required=True)
    observed = ObservedBehavior(
        observed_exec=("/usr/bin/true",),
        observed_read_paths=("/workspace/repo",),
        observed_write_paths=("/workspace/repo/out",),
        observed_network_targets=("registry.example.invalid",),
        observed_wall_time_ms=10,
        observed_memory_bytes=1024,
        observed_external_effect=None,
    )
    receipt, findings = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=observed,
        authoritative_readback_sha256=contract.contract_sha256,
        trace_artifact_sha256=SHA256_B,
    )
    assert receipt.verdict == "BEHAVIOR_VIOLATION"
    assert any(f.startswith("EXTERNAL_EFFECT_MISSING") for f in findings)


def test_external_write_contract_with_effect_verifies() -> None:
    contract = _contract(effect_class="EXTERNAL_WRITE", network_required=True)
    observed = ObservedBehavior(
        observed_exec=("/usr/bin/true",),
        observed_read_paths=("/workspace/repo",),
        observed_write_paths=("/workspace/repo/out",),
        observed_network_targets=("registry.example.invalid",),
        observed_wall_time_ms=10,
        observed_memory_bytes=1024,
        observed_external_effect="POST https://registry.example.invalid/v1/publish",
    )
    receipt, findings = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=observed,
        authoritative_readback_sha256=contract.contract_sha256,
        trace_artifact_sha256=SHA256_B,
    )
    assert receipt.verdict == "BEHAVIOR_VERIFIED"
    assert receipt.external_effect_sha256 == _sha("POST https://registry.example.invalid/v1/publish")


def test_missing_required_observation_is_unverified_not_violation() -> None:
    contract = _contract()
    observed = ObservedBehavior(
        observed_exec=None,
        observed_read_paths=("/workspace/repo",),
        observed_write_paths=("/workspace/repo/out",),
        observed_network_targets=(),
        observed_wall_time_ms=10,
        observed_memory_bytes=1024,
        observed_external_effect=None,
    )
    receipt, findings = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=observed,
        authoritative_readback_sha256=contract.contract_sha256,
        trace_artifact_sha256=SHA256_B,
    )
    assert receipt.verdict == "UNVERIFIED"
    assert any(f == "MISSING_OBSERVATION:exec" for f in findings)


def test_missing_authoritative_readback_is_unverified() -> None:
    contract = _contract()
    observed = _observed_ok()
    receipt, findings = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=observed,
        authoritative_readback_sha256=None,
        trace_artifact_sha256=SHA256_B,
    )
    assert receipt.verdict == "UNVERIFIED"
    assert any(f == "MISSING_OBSERVATION:authoritative_readback" for f in findings)


def test_authoritative_readback_contract_hash_mismatch_is_contradicted() -> None:
    contract = _contract()
    observed = _observed_ok()
    receipt, findings = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=observed,
        authoritative_readback_sha256="c" * 64,
        trace_artifact_sha256=SHA256_B,
    )
    assert receipt.verdict == "CONTRADICTED"
    assert findings == ("AUTHORITATIVE_READBACK_CONTRACT_HASH_MISMATCH",)


def test_remote_mcp_cannot_be_behavior_verified() -> None:
    contract = _contract(
        execution_kind="REMOTE_MCP",
        effect_class="READ_ONLY",
        network_required=False,
        allowed_network_targets=("api.remote.example.invalid",),
    )
    observed = ObservedBehavior(
        observed_exec=None,
        observed_read_paths=None,
        observed_write_paths=None,
        observed_network_targets=("api.remote.example.invalid",),
        observed_wall_time_ms=None,
        observed_memory_bytes=None,
        observed_external_effect=None,
    )
    receipt, findings = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=observed,
        authoritative_readback_sha256=contract.contract_sha256,
        trace_artifact_sha256=SHA256_B,
    )
    assert receipt.verdict == "REMOTE_PARTIAL"
    assert findings == ("REMOTE_MCP_NO_LOCAL_FIDELITY",)
    assert receipt.verdict != "BEHAVIOR_VERIFIED"


def test_remote_mcp_undeclared_network_target_is_violation() -> None:
    contract = _contract(
        execution_kind="REMOTE_MCP",
        effect_class="READ_ONLY",
        network_required=False,
        allowed_network_targets=("api.remote.example.invalid",),
    )
    observed = ObservedBehavior(
        observed_exec=None,
        observed_read_paths=None,
        observed_write_paths=None,
        observed_network_targets=("evil.example.invalid",),
        observed_wall_time_ms=None,
        observed_memory_bytes=None,
        observed_external_effect=None,
    )
    receipt, findings = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=observed,
        authoritative_readback_sha256=contract.contract_sha256,
        trace_artifact_sha256=SHA256_B,
    )
    assert receipt.verdict == "BEHAVIOR_VIOLATION"
    assert any(f.startswith("NETWORK_TARGET_NOT_DECLARED") for f in findings)


def test_remote_mcp_missing_network_is_unverified() -> None:
    contract = _contract(execution_kind="REMOTE_MCP", effect_class="READ_ONLY", network_required=False)
    observed = ObservedBehavior(
        observed_exec=None,
        observed_read_paths=None,
        observed_write_paths=None,
        observed_network_targets=None,
        observed_wall_time_ms=None,
        observed_memory_bytes=None,
        observed_external_effect=None,
    )
    receipt, findings = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=observed,
        authoritative_readback_sha256=contract.contract_sha256,
        trace_artifact_sha256=SHA256_B,
    )
    assert receipt.verdict == "UNVERIFIED"


def test_host_broker_does_not_require_filesystem_observations() -> None:
    contract = _contract(
        execution_kind="HOST_BROKER",
        effect_class="WORKSPACE_WRITE",
        image_digest=None,
    )
    observed = ObservedBehavior(
        observed_exec=("/usr/bin/true",),
        observed_read_paths=None,
        observed_write_paths=None,
        observed_network_targets=(),
        observed_wall_time_ms=10,
        observed_memory_bytes=1024,
        observed_external_effect=None,
    )
    receipt, findings = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=observed,
        authoritative_readback_sha256=contract.contract_sha256,
        trace_artifact_sha256=SHA256_B,
    )
    assert receipt.verdict == "BEHAVIOR_VERIFIED"


def test_tampered_receipt_is_detected() -> None:
    contract = _contract()
    observed = _observed_ok(observed_network_targets=("evil.example.invalid",))
    receipt, _ = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=observed,
        authoritative_readback_sha256=contract.contract_sha256,
        trace_artifact_sha256=SHA256_B,
    )
    assert receipt.verdict == "BEHAVIOR_VIOLATION"
    tampered_record = dict(receipt.canonical_record())
    # Claim a positive verdict that the evidence does not support, while keeping
    # the original receipt hash. Reconstruction must fail closed on the tamper.
    tampered_record["verdict"] = "BEHAVIOR_VERIFIED"
    with pytest.raises(ToolBehaviorAttestationError, match="tamper detected"):
        receipt_from_mapping(tampered_record)


def test_receipt_missing_stored_hash_is_rejected() -> None:
    contract = _contract()
    observed = _observed_ok()
    receipt, _ = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=observed,
        authoritative_readback_sha256=contract.contract_sha256,
        trace_artifact_sha256=SHA256_B,
    )
    record = receipt.canonical_record()
    del record["receiptSha256"]
    with pytest.raises(ToolBehaviorAttestationError, match="receiptSha256 is required"):
        receipt_from_mapping(record)


def test_receipt_round_trip_preserves_hash_and_verifies() -> None:
    contract = _contract()
    observed = _observed_ok()
    receipt, _ = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=observed,
        authoritative_readback_sha256=contract.contract_sha256,
        trace_artifact_sha256=SHA256_B,
    )
    record = receipt.canonical_record()
    rebuilt = receipt_from_mapping(record)
    assert rebuilt.receipt_sha256 == receipt.receipt_sha256
    assert rebuilt.verify() is True
    assert rebuilt.canonical_record() == record


def test_unobserved_and_observed_empty_produce_distinct_hashes() -> None:
    contract = _contract()
    observed_none = ObservedBehavior(
        observed_exec=("/usr/bin/true",),
        observed_read_paths=None,
        observed_write_paths=None,
        observed_network_targets=(),
        observed_wall_time_ms=10,
        observed_memory_bytes=1024,
        observed_external_effect=None,
    )
    observed_empty = ObservedBehavior(
        observed_exec=("/usr/bin/true",),
        observed_read_paths=(),
        observed_write_paths=(),
        observed_network_targets=(),
        observed_wall_time_ms=10,
        observed_memory_bytes=1024,
        observed_external_effect=None,
    )
    r_none, _ = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=observed_none,
        authoritative_readback_sha256=contract.contract_sha256,
        trace_artifact_sha256=SHA256_B,
    )
    r_empty, _ = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=observed_empty,
        authoritative_readback_sha256=contract.contract_sha256,
        trace_artifact_sha256=SHA256_B,
    )
    assert r_none.observed_filesystem_sha256 != r_empty.observed_filesystem_sha256
    # empty fs observations are still in-bounds (no read/write beyond declared sets)
    assert r_empty.verdict == "BEHAVIOR_VERIFIED"
    # missing fs observations for LOCAL_OCI is unverified
    assert r_none.verdict == "UNVERIFIED"


def test_raw_secret_in_exec_observation_is_blocked() -> None:
    with pytest.raises(ToolBehaviorAttestationError, match="secret-shaped"):
        ObservedBehavior(
            observed_exec=("ghp_" + "x" * 36,),
            observed_read_paths=None,
            observed_write_paths=None,
            observed_network_targets=None,
            observed_wall_time_ms=None,
            observed_memory_bytes=None,
            observed_external_effect=None,
        )


def test_raw_secret_in_external_effect_is_blocked() -> None:
    with pytest.raises(ToolBehaviorAttestationError, match="secret-shaped"):
        ObservedBehavior(
            observed_exec=None,
            observed_read_paths=None,
            observed_write_paths=None,
            observed_network_targets=None,
            observed_wall_time_ms=None,
            observed_memory_bytes=None,
            observed_external_effect="Bearer " + "x" * 40,
        )


def test_raw_secret_in_read_path_is_blocked() -> None:
    with pytest.raises(ToolBehaviorAttestationError, match="secret-shaped"):
        ObservedBehavior(
            observed_exec=None,
            observed_read_paths=("password=hunter2dontleak",),
            observed_write_paths=None,
            observed_network_targets=None,
            observed_wall_time_ms=None,
            observed_memory_bytes=None,
            observed_external_effect=None,
        )


def test_invalid_sha_in_receipt_field_is_rejected() -> None:
    with pytest.raises(ToolBehaviorAttestationError, match="repository_revision"):
        ObservedToolBehaviorReceipt(
            schema_version="sovereign.observed-tool-behavior-receipt.v1",
            tool_id="tool.canary",
            repository_revision="not-a-sha",
            tool_registry_revision=SHA256_A,
            image_digest=None,
            behavior_contract_sha256=SHA256_A,
            canary_input_sha256=SHA256_A,
            observed_exec_sha256=SHA256_A,
            observed_filesystem_sha256=SHA256_A,
            observed_network_sha256=SHA256_A,
            observed_resource_usage_sha256=SHA256_A,
            external_effect_sha256=None,
            authoritative_readback_sha256=None,
            trace_artifact_sha256=SHA256_A,
            verdict="UNVERIFIED",
        )


def test_asserted_verdict_mismatch_is_contradicted() -> None:
    contract = _contract()
    observed = _observed_ok()
    receipt, findings = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=observed,
        authoritative_readback_sha256=contract.contract_sha256,
        trace_artifact_sha256=SHA256_B,
        verdict="BEHAVIOR_VIOLATION",
    )
    assert receipt.verdict == "CONTRADICTED"
    assert any(f.startswith("ASSERTED_VERDICT") for f in findings)


def test_asserted_verdict_matching_evaluated_is_accepted() -> None:
    contract = _contract()
    observed = _observed_ok()
    receipt, findings = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=observed,
        authoritative_readback_sha256=contract.contract_sha256,
        trace_artifact_sha256=SHA256_B,
        verdict="BEHAVIOR_VERIFIED",
    )
    assert receipt.verdict == "BEHAVIOR_VERIFIED"
    assert receipt.verify() is True


def test_receipt_rejects_unknown_verdict() -> None:
    with pytest.raises(ToolBehaviorAttestationError, match="verdict"):
        ObservedToolBehaviorReceipt(
            schema_version="sovereign.observed-tool-behavior-receipt.v1",
            tool_id="tool.canary",
            repository_revision=SHA256_A,
            tool_registry_revision=SHA256_A,
            image_digest=None,
            behavior_contract_sha256=SHA256_A,
            canary_input_sha256=SHA256_A,
            observed_exec_sha256=SHA256_A,
            observed_filesystem_sha256=SHA256_A,
            observed_network_sha256=SHA256_A,
            observed_resource_usage_sha256=SHA256_A,
            external_effect_sha256=None,
            authoritative_readback_sha256=None,
            trace_artifact_sha256=SHA256_A,
            verdict="SAFE",
        )


def test_evaluate_verdict_directly_returns_violation() -> None:
    contract = _contract()
    observed = _observed_ok(observed_network_targets=("evil.example.invalid",))
    verdict, findings = evaluate_verdict(
        contract=contract,
        observed=observed,
        authoritative_readback_sha256=contract.contract_sha256,
        trace_artifact_sha256=SHA256_B,
    )
    assert verdict == "BEHAVIOR_VIOLATION"
    assert any("evil" in f for f in findings)
