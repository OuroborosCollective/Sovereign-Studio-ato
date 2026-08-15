"""Tests for the OTBA registry-/install-admission boundary (Issue #1452 / OTBA 3/5).

These tests exercise the real live-path admission module against the real receipt and
contract modules from #1451. No production logic is copied into the tests.
"""

from __future__ import annotations

import pytest

from tool_behavior_admission import (
    ADMIT_ALLOWED,
    ADMIT_BLOCKED,
    ADMIT_REMOTE_PARTIAL,
    FINDING_DRIFT_CANARY_INPUT,
    FINDING_DRIFT_CAPABILITY_CONTRACT,
    FINDING_DRIFT_CONTRACT_HASH,
    FINDING_DRIFT_IMAGE_DIGEST,
    FINDING_DRIFT_REGISTRY_REVISION,
    FINDING_DRIFT_REPO_REVISION,
    FINDING_DRIFT_SANDBOX_TRACER,
    FINDING_NO_RECEIPT,
    FINDING_NOT_VERIFIED,
    FINDING_RECEIPT_TAMPERED,
    FINDING_REMOTE_NOT_LOCAL_FIDELITY,
    REQUIREMENT_POST_OBSERVED_TOOL_BEHAVIOR,
    ReceiptClaimedBindings,
    TIER_ENFORCE_LOCAL_OCI,
    TIER_OBSERVE_ONLY,
    TIER_WARN,
    ToolAdmissionIdentity,
    evaluate_tool_admission,
    requirements_for_tool_install,
)
from tool_behavior_attestation import (
    ObservedBehavior,
    ObservedToolBehaviorReceipt,
    build_receipt,
)
from tool_behavior_contract import ToolBehaviorContract

SHA_A = "a" * 40
SHA_B = "b" * 40
SHA256_A = "a" * 64
SHA256_B = "b" * 64
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


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


def _verified_receipt(**contract_overrides) -> ObservedToolBehaviorReceipt:
    contract = _contract(**contract_overrides)
    receipt, _findings = build_receipt(
        contract=contract,
        canary_input_sha256=SHA256_A,
        observed=_observed_ok(),
        authoritative_readback_sha256=contract.contract_sha256,
        trace_artifact_sha256=SHA256_A,
    )
    return receipt


def _identity_for(receipt: ObservedToolBehaviorReceipt, *, execution_kind="LOCAL_OCI", **overrides) -> ToolAdmissionIdentity:
    base = dict(
        tool_id=receipt.tool_id,
        execution_kind=execution_kind,
        repository_revision=receipt.repository_revision,
        tool_registry_revision=receipt.tool_registry_revision,
        image_digest=receipt.image_digest,
        behavior_contract_sha256=receipt.behavior_contract_sha256,
        canary_input_sha256=receipt.canary_input_sha256,
        capability_contract_sha256="",
        sandbox_tracer_version="",
    )
    base.update(overrides)
    return ToolAdmissionIdentity(**base)


# ---------------------------------------------------------------------------
# requirements_for_tool_install
# ---------------------------------------------------------------------------

class TestRequirementsForToolInstall:
    def test_local_oci_appends_behavior_requirement(self):
        reqs = requirements_for_tool_install(execution_kind="LOCAL_OCI")
        assert REQUIREMENT_POST_OBSERVED_TOOL_BEHAVIOR in reqs
        assert reqs[-1] == REQUIREMENT_POST_OBSERVED_TOOL_BEHAVIOR

    def test_remote_mcp_has_no_behavior_requirement(self):
        reqs = requirements_for_tool_install(execution_kind="REMOTE_MCP")
        assert REQUIREMENT_POST_OBSERVED_TOOL_BEHAVIOR not in reqs

    def test_host_broker_has_no_behavior_requirement(self):
        reqs = requirements_for_tool_install(execution_kind="HOST_BROKER")
        assert REQUIREMENT_POST_OBSERVED_TOOL_BEHAVIOR not in reqs

    def test_invalid_kind_raises(self):
        with pytest.raises(ValueError):
            requirements_for_tool_install(execution_kind="BOGUS")

    def test_kind_is_case_insensitive(self):
        reqs = requirements_for_tool_install(execution_kind="local_oci")
        assert REQUIREMENT_POST_OBSERVED_TOOL_BEHAVIOR in reqs


# ---------------------------------------------------------------------------
# Happy path: LOCAL_OCI with verified receipt on exact identity -> ALLOWED
# ---------------------------------------------------------------------------

class TestLocalOciAdmitted:
    def test_verified_receipt_on_exact_identity_is_allowed(self):
        receipt = _verified_receipt()
        identity = _identity_for(receipt)
        result = evaluate_tool_admission(
            identity=identity, receipt=receipt, enforcement_tier=TIER_ENFORCE_LOCAL_OCI,
        )
        assert result.verdict == ADMIT_ALLOWED
        assert result.promotion_blocked is False
        assert REQUIREMENT_POST_OBSERVED_TOOL_BEHAVIOR in result.satisfied
        assert result.auto_merge_allowed is False

    def test_allowed_under_each_tier(self):
        receipt = _verified_receipt()
        identity = _identity_for(receipt)
        for tier in (TIER_OBSERVE_ONLY, TIER_WARN, TIER_ENFORCE_LOCAL_OCI):
            result = evaluate_tool_admission(
                identity=identity, receipt=receipt, enforcement_tier=tier,
            )
            assert result.verdict == ADMIT_ALLOWED, tier
            assert result.promotion_blocked is False, tier


# ---------------------------------------------------------------------------
# BLOCKED scenarios under enforce_local_oci
# ---------------------------------------------------------------------------

class TestLocalOciBlocked:
    def test_no_receipt_is_blocked(self):
        identity = _identity_for(_verified_receipt())
        result = evaluate_tool_admission(
            identity=identity, receipt=None, enforcement_tier=TIER_ENFORCE_LOCAL_OCI,
        )
        assert result.verdict == ADMIT_BLOCKED
        assert result.promotion_blocked is True
        assert FINDING_NO_RECEIPT in result.finding_codes
        assert REQUIREMENT_POST_OBSERVED_TOOL_BEHAVIOR in result.missing

    def test_old_image_digest_is_blocked(self):
        receipt = _verified_receipt()
        identity = _identity_for(receipt, image_digest=DIGEST_B)
        result = evaluate_tool_admission(
            identity=identity, receipt=receipt, enforcement_tier=TIER_ENFORCE_LOCAL_OCI,
        )
        assert result.verdict == ADMIT_BLOCKED
        assert result.promotion_blocked is True
        assert FINDING_DRIFT_IMAGE_DIGEST in result.finding_codes

    def test_other_registry_revision_is_blocked(self):
        receipt = _verified_receipt()
        identity = _identity_for(receipt, tool_registry_revision=SHA_B)
        result = evaluate_tool_admission(
            identity=identity, receipt=receipt, enforcement_tier=TIER_ENFORCE_LOCAL_OCI,
        )
        assert result.verdict == ADMIT_BLOCKED
        assert FINDING_DRIFT_REGISTRY_REVISION in result.finding_codes

    def test_other_repository_revision_is_blocked(self):
        receipt = _verified_receipt()
        identity = _identity_for(receipt, repository_revision=SHA_B)
        result = evaluate_tool_admission(
            identity=identity, receipt=receipt, enforcement_tier=TIER_ENFORCE_LOCAL_OCI,
        )
        assert result.verdict == ADMIT_BLOCKED
        assert FINDING_DRIFT_REPO_REVISION in result.finding_codes

    def test_behavior_contract_hash_drift_is_blocked(self):
        receipt = _verified_receipt()
        identity = _identity_for(receipt, behavior_contract_sha256=SHA256_B)
        result = evaluate_tool_admission(
            identity=identity, receipt=receipt, enforcement_tier=TIER_ENFORCE_LOCAL_OCI,
        )
        assert result.verdict == ADMIT_BLOCKED
        assert FINDING_DRIFT_CONTRACT_HASH in result.finding_codes

    def test_canary_input_drift_is_blocked(self):
        receipt = _verified_receipt()
        identity = _identity_for(receipt, canary_input_sha256=SHA256_B)
        result = evaluate_tool_admission(
            identity=identity, receipt=receipt, enforcement_tier=TIER_ENFORCE_LOCAL_OCI,
        )
        assert result.verdict == ADMIT_BLOCKED
        assert FINDING_DRIFT_CANARY_INPUT in result.finding_codes

    def test_capability_contract_drift_is_blocked(self):
        receipt = _verified_receipt()
        identity = _identity_for(receipt, capability_contract_sha256=SHA256_A)
        # receipt claimed a different capability contract
        claimed = ReceiptClaimedBindings(capability_contract_sha256=SHA256_B)
        result = evaluate_tool_admission(
            identity=identity, receipt=receipt, claimed_bindings=claimed,
            enforcement_tier=TIER_ENFORCE_LOCAL_OCI,
        )
        assert result.verdict == ADMIT_BLOCKED
        assert FINDING_DRIFT_CAPABILITY_CONTRACT in result.finding_codes

    def test_capability_contract_missing_claim_is_blocked(self):
        receipt = _verified_receipt()
        # identity requires a capability contract but no claim supplied
        identity = _identity_for(receipt, capability_contract_sha256=SHA256_A)
        result = evaluate_tool_admission(
            identity=identity, receipt=receipt, claimed_bindings=None,
            enforcement_tier=TIER_ENFORCE_LOCAL_OCI,
        )
        assert result.verdict == ADMIT_BLOCKED
        assert FINDING_DRIFT_CAPABILITY_CONTRACT in result.finding_codes

    def test_sandbox_tracer_version_drift_is_blocked(self):
        receipt = _verified_receipt()
        identity = _identity_for(receipt, sandbox_tracer_version="strace/v1.0")
        claimed = ReceiptClaimedBindings(sandbox_tracer_version="strace/v0.9")
        result = evaluate_tool_admission(
            identity=identity, receipt=receipt, claimed_bindings=claimed,
            enforcement_tier=TIER_ENFORCE_LOCAL_OCI,
        )
        assert result.verdict == ADMIT_BLOCKED
        assert FINDING_DRIFT_SANDBOX_TRACER in result.finding_codes

    def test_tampered_receipt_is_blocked(self):
        receipt = _verified_receipt()
        # Tamper: rebuild a receipt then corrupt a field while preserving the old hash.
        tampered = ObservedToolBehaviorReceipt(
            schema_version=receipt.schema_version,
            tool_id=receipt.tool_id,
            repository_revision=SHA_B,  # changed identity, old hash
            tool_registry_revision=receipt.tool_registry_revision,
            image_digest=receipt.image_digest,
            behavior_contract_sha256=receipt.behavior_contract_sha256,
            canary_input_sha256=receipt.canary_input_sha256,
            observed_exec_sha256=receipt.observed_exec_sha256,
            observed_filesystem_sha256=receipt.observed_filesystem_sha256,
            observed_network_sha256=receipt.observed_network_sha256,
            observed_resource_usage_sha256=receipt.observed_resource_usage_sha256,
            external_effect_sha256=receipt.external_effect_sha256,
            authoritative_readback_sha256=receipt.authoritative_readback_sha256,
            trace_artifact_sha256=receipt.trace_artifact_sha256,
            verdict=receipt.verdict,
        )
        # The dataclass recomputes receipt_sha256 in __post_init__, so to simulate a
        # tampered-then-re-hashed receipt that still fails verify(), we override the
        # hash field directly to a wrong value.
        object.__setattr__(tampered, "receipt_sha256", "0" * 64)
        identity = _identity_for(receipt)
        result = evaluate_tool_admission(
            identity=identity, receipt=tampered, enforcement_tier=TIER_ENFORCE_LOCAL_OCI,
        )
        assert result.verdict == ADMIT_BLOCKED
        assert FINDING_RECEIPT_TAMPERED in result.finding_codes


# ---------------------------------------------------------------------------
# Override signals cannot upgrade a BLOCKED verdict
# ---------------------------------------------------------------------------

class TestOverrideSignalsCannotUpgrade:
    def _blocked_identity(self):
        receipt = _verified_receipt()
        # drift the image digest so the receipt is invalid for this identity
        identity = _identity_for(receipt, image_digest=DIGEST_B)
        return receipt, identity

    def test_mcp_initialize_pass_cannot_override_missing_receipt(self):
        receipt, identity = self._blocked_identity()
        result = evaluate_tool_admission(
            identity=identity, receipt=receipt, enforcement_tier=TIER_ENFORCE_LOCAL_OCI,
            mcp_initialize_passed=True,
        )
        assert result.verdict == ADMIT_BLOCKED
        assert result.promotion_blocked is True

    def test_signed_image_cannot_override_violation(self):
        receipt, identity = self._blocked_identity()
        result = evaluate_tool_admission(
            identity=identity, receipt=receipt, enforcement_tier=TIER_ENFORCE_LOCAL_OCI,
            signed_image=True,
        )
        assert result.verdict == ADMIT_BLOCKED
        assert result.promotion_blocked is True

    def test_ui_override_flag_cannot_upgrade_gate(self):
        receipt, identity = self._blocked_identity()
        result = evaluate_tool_admission(
            identity=identity, receipt=receipt, enforcement_tier=TIER_ENFORCE_LOCAL_OCI,
            ui_override_flag=True,
        )
        assert result.verdict == ADMIT_BLOCKED
        assert result.promotion_blocked is True

    def test_all_overrides_combined_cannot_upgrade(self):
        receipt, identity = self._blocked_identity()
        result = evaluate_tool_admission(
            identity=identity, receipt=receipt, enforcement_tier=TIER_ENFORCE_LOCAL_OCI,
            mcp_initialize_passed=True, signed_image=True, ui_override_flag=True,
        )
        assert result.verdict == ADMIT_BLOCKED
        assert result.promotion_blocked is True


# ---------------------------------------------------------------------------
# Remote MCP is REMOTE_PARTIAL, never full local attestation
# ---------------------------------------------------------------------------

class TestRemotePartial:
    def test_remote_mcp_is_remote_partial(self):
        receipt = _verified_receipt(execution_kind="REMOTE_MCP")
        identity = _identity_for(receipt, execution_kind="REMOTE_MCP")
        result = evaluate_tool_admission(
            identity=identity, receipt=receipt, enforcement_tier=TIER_ENFORCE_LOCAL_OCI,
        )
        assert result.verdict == ADMIT_REMOTE_PARTIAL
        assert result.promotion_blocked is False
        assert FINDING_REMOTE_NOT_LOCAL_FIDELITY in result.finding_codes

    def test_remote_mcp_without_receipt_is_remote_partial(self):
        identity = ToolAdmissionIdentity(
            tool_id="tool.remote",
            execution_kind="REMOTE_MCP",
            repository_revision=SHA_A,
            tool_registry_revision=SHA_A,
            image_digest=None,
            behavior_contract_sha256=SHA256_A,
            canary_input_sha256=SHA256_A,
            capability_contract_sha256="",
            sandbox_tracer_version="",
        )
        result = evaluate_tool_admission(
            identity=identity, receipt=None, enforcement_tier=TIER_ENFORCE_LOCAL_OCI,
        )
        assert result.verdict == ADMIT_REMOTE_PARTIAL

    def test_host_broker_is_remote_partial(self):
        identity = ToolAdmissionIdentity(
            tool_id="tool.broker",
            execution_kind="HOST_BROKER",
            repository_revision=SHA_A,
            tool_registry_revision=SHA_A,
            image_digest=None,
            behavior_contract_sha256=SHA256_A,
            canary_input_sha256=SHA256_A,
            capability_contract_sha256="",
            sandbox_tracer_version="",
        )
        result = evaluate_tool_admission(
            identity=identity, receipt=None, enforcement_tier=TIER_ENFORCE_LOCAL_OCI,
        )
        assert result.verdict == ADMIT_REMOTE_PARTIAL


# ---------------------------------------------------------------------------
# Tier semantics: shadow/warn never mutate productive registry
# ---------------------------------------------------------------------------

class TestTierSemantics:
    def test_observe_only_does_not_block_promotion(self):
        receipt = _verified_receipt()
        identity = _identity_for(receipt, image_digest=DIGEST_B)  # drifted
        result = evaluate_tool_admission(
            identity=identity, receipt=receipt, enforcement_tier=TIER_OBSERVE_ONLY,
        )
        # honest verdict still BLOCKED, but promotion not gated
        assert result.verdict == ADMIT_BLOCKED
        assert result.promotion_blocked is False

    def test_warn_does_not_block_promotion(self):
        receipt = _verified_receipt()
        identity = _identity_for(receipt, image_digest=DIGEST_B)  # drifted
        result = evaluate_tool_admission(
            identity=identity, receipt=receipt, enforcement_tier=TIER_WARN,
        )
        assert result.verdict == ADMIT_BLOCKED
        assert result.promotion_blocked is False

    def test_enforce_blocks_promotion_on_drift(self):
        receipt = _verified_receipt()
        identity = _identity_for(receipt, image_digest=DIGEST_B)  # drifted
        result = evaluate_tool_admission(
            identity=identity, receipt=receipt, enforcement_tier=TIER_ENFORCE_LOCAL_OCI,
        )
        assert result.verdict == ADMIT_BLOCKED
        assert result.promotion_blocked is True

    def test_observe_only_with_no_receipt_exposes_truth(self):
        identity = _identity_for(_verified_receipt())
        result = evaluate_tool_admission(
            identity=identity, receipt=None, enforcement_tier=TIER_OBSERVE_ONLY,
        )
        assert result.verdict == ADMIT_BLOCKED
        assert FINDING_NO_RECEIPT in result.finding_codes
        assert result.promotion_blocked is False


# ---------------------------------------------------------------------------
# Invariants / fail-closed
# ---------------------------------------------------------------------------

class TestInvariants:
    def test_auto_merge_never_allowed(self):
        receipt = _verified_receipt()
        identity = _identity_for(receipt)
        for tier in (TIER_OBSERVE_ONLY, TIER_WARN, TIER_ENFORCE_LOCAL_OCI):
            result = evaluate_tool_admission(
                identity=identity, receipt=receipt, enforcement_tier=tier,
            )
            assert result.auto_merge_allowed is False, tier

    def test_invalid_tier_raises(self):
        receipt = _verified_receipt()
        identity = _identity_for(receipt)
        with pytest.raises(ValueError):
            evaluate_tool_admission(
                identity=identity, receipt=receipt, enforcement_tier="mandatory",
            )

    def test_invalid_execution_kind_in_identity_raises(self):
        with pytest.raises(ValueError):
            ToolAdmissionIdentity(
                tool_id="tool.x",
                execution_kind="BOGUS",
                repository_revision=SHA_A,
                tool_registry_revision=SHA_A,
                image_digest=None,
                behavior_contract_sha256=SHA256_A,
                canary_input_sha256=SHA256_A,
                capability_contract_sha256="",
                sandbox_tracer_version="",
            )

    def test_receipt_sha256_propagated_on_allowed(self):
        receipt = _verified_receipt()
        identity = _identity_for(receipt)
        result = evaluate_tool_admission(
            identity=identity, receipt=receipt, enforcement_tier=TIER_ENFORCE_LOCAL_OCI,
        )
        assert result.receipt_sha256 == receipt.receipt_sha256
        assert len(result.receipt_sha256) == 64

    def test_receipt_sha256_empty_when_no_receipt(self):
        identity = _identity_for(_verified_receipt())
        result = evaluate_tool_admission(
            identity=identity, receipt=None, enforcement_tier=TIER_ENFORCE_LOCAL_OCI,
        )
        assert result.receipt_sha256 == ""

    def test_pure_module_no_side_effects(self):
        """evaluate_tool_admission must not mutate its inputs (purity / determinism)."""
        receipt = _verified_receipt()
        identity = _identity_for(receipt)
        original_receipt_hash = receipt.receipt_sha256
        evaluate_tool_admission(
            identity=identity, receipt=receipt, enforcement_tier=TIER_ENFORCE_LOCAL_OCI,
        )
        assert receipt.receipt_sha256 == original_receipt_hash
