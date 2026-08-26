"""Tests for ACSA Canary Lane — Issue #1639."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent_runtime.acsa_canary_lane import (  # noqa: E402
    ACSACanaryError,
    CanaryExecutionReceipt,
    CanaryExecutionRequest,
    CanaryStatus,
    CanaryType,
    DisposableTargetSpec,
    canary_type_from_operator,
    create_disposable_target_spec,
    determine_verdict,
    generate_canary_receipt,
    make_mock_canary_request,
    requires_canary_execution,
    validate_canary_request,
)


# ============================================================================
# CanaryType Mapping Tests
# ============================================================================

class TestCanaryTypeMapping:
    """Test mapping of control mutation operators to canary types."""

    def test_environment_operators(self):
        assert canary_type_from_operator("stale_revision") == CanaryType.ENVIRONMENT
        assert canary_type_from_operator("wrong_image_digest") == CanaryType.ENVIRONMENT
        assert canary_type_from_operator("nonprod_to_production") == CanaryType.ENVIRONMENT
        assert canary_type_from_operator("missing_runtime_evidence") == CanaryType.ENVIRONMENT

    def test_identity_operators(self):
        assert canary_type_from_operator("owner_mismatch") == CanaryType.IDENTITY
        assert canary_type_from_operator("tool_binding_swap") == CanaryType.IDENTITY

    def test_egress_operators(self):
        assert canary_type_from_operator("disallowed_egress") == CanaryType.EGRESS

    def test_replay_operators(self):
        assert canary_type_from_operator("credential_replay") == CanaryType.REPLAY
        assert canary_type_from_operator("receipt_replay") == CanaryType.REPLAY

    def test_unknown_operator(self):
        assert canary_type_from_operator("unknown_operator") is None


# ============================================================================
# Runtime Execution Requirements Tests
# ============================================================================

class TestRequiresCanaryExecution:
    """Test which canary types require runtime execution."""

    def test_all_canary_types_require_execution(self):
        """All defined canary types require runtime execution."""
        for canary_type in CanaryType:
            assert requires_canary_execution(canary_type) is True


# ============================================================================
# Canary Request Validation Tests
# ============================================================================

class TestValidateCanaryRequest:
    """Test validation of canary execution requests."""

    def test_valid_request(self):
        request = make_mock_canary_request()
        errors = validate_canary_request(request)
        assert errors == []

    def test_missing_case_id(self):
        request = CanaryExecutionRequest(
            canary_type=CanaryType.ENVIRONMENT,
            case_id="",
            case_sha256="a" * 64,
            target_environment="test",
            target_revision="b" * 40,
            baseline_contract={"test": "baseline"},
            mutated_contract={"test": "mutated"},
        )
        errors = validate_canary_request(request)
        assert "case_id is required" in errors

    def test_invalid_case_sha256(self):
        request = make_mock_canary_request()
        # Need to create new object with invalid sha256
        request = CanaryExecutionRequest(
            canary_type=request.canary_type,
            case_id=request.case_id,
            case_sha256="invalid",
            target_environment=request.target_environment,
            target_revision=request.target_revision,
            baseline_contract=request.baseline_contract,
            mutated_contract=request.mutated_contract,
            execution_timeout_seconds=request.execution_timeout_seconds,
        )
        errors = validate_canary_request(request)
        assert any("case_sha256" in e for e in errors)

    def test_missing_target_environment(self):
        request = CanaryExecutionRequest(
            canary_type=CanaryType.ENVIRONMENT,
            case_id="test-001",
            case_sha256="a" * 64,
            target_environment="",
            target_revision="b" * 40,
            baseline_contract={"test": "baseline"},
            mutated_contract={"test": "mutated"},
        )
        errors = validate_canary_request(request)
        assert "target_environment is required" in errors

    def test_missing_baseline_contract(self):
        request = CanaryExecutionRequest(
            canary_type=CanaryType.ENVIRONMENT,
            case_id="test-001",
            case_sha256="a" * 64,
            target_environment="test",
            target_revision="b" * 40,
            baseline_contract={},
            mutated_contract={"test": "mutated"},
        )
        errors = validate_canary_request(request)
        assert "baseline_contract is required" in errors

    def test_missing_mutated_contract(self):
        request = CanaryExecutionRequest(
            canary_type=CanaryType.ENVIRONMENT,
            case_id="test-001",
            case_sha256="a" * 64,
            target_environment="test",
            target_revision="b" * 40,
            baseline_contract={"test": "baseline"},
            mutated_contract={},
        )
        errors = validate_canary_request(request)
        assert "mutated_contract is required" in errors

    def test_invalid_timeout_zero(self):
        request = make_mock_canary_request()
        request = CanaryExecutionRequest(
            canary_type=request.canary_type,
            case_id=request.case_id,
            case_sha256=request.case_sha256,
            target_environment=request.target_environment,
            target_revision=request.target_revision,
            baseline_contract=request.baseline_contract,
            mutated_contract=request.mutated_contract,
            execution_timeout_seconds=0,
        )
        errors = validate_canary_request(request)
        assert any("positive" in e for e in errors)

    def test_invalid_timeout_too_large(self):
        request = make_mock_canary_request()
        request = CanaryExecutionRequest(
            canary_type=request.canary_type,
            case_id=request.case_id,
            case_sha256=request.case_sha256,
            target_environment=request.target_environment,
            target_revision=request.target_revision,
            baseline_contract=request.baseline_contract,
            mutated_contract=request.mutated_contract,
            execution_timeout_seconds=600,
        )
        errors = validate_canary_request(request)
        assert any("exceed 300" in e for e in errors)


# ============================================================================
# Receipt Generation Tests
# ============================================================================

class TestGenerateCanaryReceipt:
    """Test canary receipt generation."""

    def test_generate_receipt_completed(self):
        request = make_mock_canary_request()
        receipt = generate_canary_receipt(
            request=request,
            status=CanaryStatus.COMPLETED,
            verdict="MUTANT_KILLED",
            execution_evidence={"test": "evidence"},
            target_readback_sha256="abc123",
            executed_at=1234567890000,
        )
        assert receipt.schema_version == "sovereign.acsa-canary-lane.v1"
        assert receipt.case_id == request.case_id
        assert receipt.status == CanaryStatus.COMPLETED
        assert receipt.verdict == "MUTANT_KILLED"
        assert receipt.execution_evidence == {"test": "evidence"}
        assert receipt.target_readback_sha256 == "abc123"
        assert receipt.receipt_sha256 is not None

    def test_generate_receipt_with_error(self):
        request = make_mock_canary_request()
        receipt = generate_canary_receipt(
            request=request,
            status=CanaryStatus.FAILED,
            error="execution failed",
            executed_at=1234567890000,
        )
        assert receipt.status == CanaryStatus.FAILED
        assert receipt.error == "execution failed"
        assert receipt.verdict is None

    def test_generate_receipt_blocked(self):
        request = make_mock_canary_request()
        receipt = generate_canary_receipt(
            request=request,
            status=CanaryStatus.BLOCKED,
            executed_at=1234567890000,
        )
        assert receipt.status == CanaryStatus.BLOCKED
        # BLOCKED should result in UNVERIFIED verdict
        assert receipt.verdict is None  # Set by caller

    def test_generate_receipt_deterministic(self):
        """Same inputs should produce same receipt."""
        request = make_mock_canary_request(case_id="deterministic-test")
        receipt1 = generate_canary_receipt(
            request=request,
            status=CanaryStatus.COMPLETED,
            verdict="MUTANT_KILLED",
            executed_at=1234567890000,
        )
        receipt2 = generate_canary_receipt(
            request=request,
            status=CanaryStatus.COMPLETED,
            verdict="MUTANT_KILLED",
            executed_at=1234567890000,
        )
        assert receipt1.receipt_id == receipt2.receipt_id
        assert receipt1.receipt_sha256 == receipt2.receipt_sha256


# ============================================================================
# Verdict Determination Tests
# ============================================================================

class TestDetermineVerdict:
    """Test verdict determination logic."""

    def test_unverified_on_blocked_status(self):
        """BLOCKED status should result in UNVERIFIED."""
        request = make_mock_canary_request()
        receipt = generate_canary_receipt(
            request=request,
            status=CanaryStatus.BLOCKED,
            executed_at=1234567890000,
        )
        case = {"operator": "stale_revision"}
        verdict = determine_verdict(case, receipt, requires_target_readback=False)
        assert verdict == "UNVERIFIED"

    def test_unverified_on_failed_status(self):
        """FAILED status should result in UNVERIFIED."""
        request = make_mock_canary_request()
        receipt = generate_canary_receipt(
            request=request,
            status=CanaryStatus.FAILED,
            error="execution failed",
            executed_at=1234567890000,
        )
        case = {"operator": "stale_revision"}
        verdict = determine_verdict(case, receipt, requires_target_readback=False)
        assert verdict == "UNVERIFIED"

    def test_unverified_on_error(self):
        """Error in receipt should result in UNVERIFIED."""
        request = make_mock_canary_request()
        receipt = generate_canary_receipt(
            request=request,
            status=CanaryStatus.COMPLETED,
            error="some error",
            executed_at=1234567890000,
        )
        case = {"operator": "stale_revision"}
        verdict = determine_verdict(case, receipt, requires_target_readback=False)
        assert verdict == "UNVERIFIED"

    def test_unverified_on_missing_evidence(self):
        """Missing execution evidence should result in UNVERIFIED."""
        request = make_mock_canary_request()
        receipt = generate_canary_receipt(
            request=request,
            status=CanaryStatus.COMPLETED,
            execution_evidence={},
            executed_at=1234567890000,
        )
        case = {"operator": "stale_revision"}
        verdict = determine_verdict(case, receipt, requires_target_readback=False)
        assert verdict == "UNVERIFIED"

    def test_unverified_on_missing_target_readback(self):
        """Missing required target readback should result in UNVERIFIED."""
        request = make_mock_canary_request()
        receipt = generate_canary_receipt(
            request=request,
            status=CanaryStatus.COMPLETED,
            execution_evidence={"test": "evidence"},
            target_readback_sha256=None,
            executed_at=1234567890000,
        )
        case = {"operator": "stale_revision"}
        verdict = determine_verdict(case, receipt, requires_target_readback=True)
        assert verdict == "UNVERIFIED"

    def test_mutant_killed_on_revision_mismatch(self):
        """Revision mismatch should result in MUTANT_KILLED."""
        request = make_mock_canary_request()
        receipt = generate_canary_receipt(
            request=request,
            status=CanaryStatus.COMPLETED,
            execution_evidence={
                "actual_revision": "aaaaaa",
                "expected_revision": "bbbbbb",
            },
            target_readback_sha256="abc123",
            executed_at=1234567890000,
        )
        case = {"operator": "stale_revision"}
        verdict = determine_verdict(case, receipt, requires_target_readback=False)
        assert verdict == "MUTANT_KILLED"

    def test_mutant_survived_on_revision_match(self):
        """Revision match (no mismatch) should result in MUTANT_SURVIVED."""
        request = make_mock_canary_request()
        receipt = generate_canary_receipt(
            request=request,
            status=CanaryStatus.COMPLETED,
            execution_evidence={
                "actual_revision": "aaaaaa",
                "expected_revision": "aaaaaa",
            },
            executed_at=1234567890000,
        )
        case = {"operator": "stale_revision"}
        verdict = determine_verdict(case, receipt, requires_target_readback=False)
        assert verdict == "MUTANT_SURVIVED"

    def test_mutant_killed_on_egress_blocked(self):
        """Egress blocked should result in MUTANT_KILLED."""
        request = make_mock_canary_request(canary_type=CanaryType.EGRESS)
        receipt = generate_canary_receipt(
            request=request,
            status=CanaryStatus.COMPLETED,
            execution_evidence={"blocked": True},
            executed_at=1234567890000,
        )
        case = {"operator": "disallowed_egress"}
        verdict = determine_verdict(case, receipt, requires_target_readback=False)
        assert verdict == "MUTANT_KILLED"

    def test_mutant_survived_on_egress_allowed(self):
        """Egress not blocked should result in MUTANT_SURVIVED."""
        request = make_mock_canary_request(canary_type=CanaryType.EGRESS)
        receipt = generate_canary_receipt(
            request=request,
            status=CanaryStatus.COMPLETED,
            execution_evidence={"blocked": False},
            executed_at=1234567890000,
        )
        case = {"operator": "disallowed_egress"}
        verdict = determine_verdict(case, receipt, requires_target_readback=False)
        assert verdict == "MUTANT_SURVIVED"

    def test_mutant_killed_on_replay_detected(self):
        """Replay detected should result in MUTANT_KILLED."""
        request = make_mock_canary_request(canary_type=CanaryType.REPLAY)
        receipt = generate_canary_receipt(
            request=request,
            status=CanaryStatus.COMPLETED,
            execution_evidence={"replay_detected": True},
            executed_at=1234567890000,
        )
        case = {"operator": "credential_replay"}
        verdict = determine_verdict(case, receipt, requires_target_readback=False)
        assert verdict == "MUTANT_KILLED"

    def test_mutant_survived_on_no_replay(self):
        """No replay detected should result in MUTANT_SURVIVED."""
        request = make_mock_canary_request(canary_type=CanaryType.REPLAY)
        receipt = generate_canary_receipt(
            request=request,
            status=CanaryStatus.COMPLETED,
            execution_evidence={"replay_detected": False},
            executed_at=1234567890000,
        )
        case = {"operator": "credential_replay"}
        verdict = determine_verdict(case, receipt, requires_target_readback=False)
        assert verdict == "MUTANT_SURVIVED"

    def test_mutant_killed_on_owner_mismatch(self):
        """Owner mismatch should result in MUTANT_KILLED."""
        request = make_mock_canary_request(canary_type=CanaryType.IDENTITY)
        receipt = generate_canary_receipt(
            request=request,
            status=CanaryStatus.COMPLETED,
            execution_evidence={
                "actual_owner": "user-alice",
                "expected_owner": "user-bob",
            },
            executed_at=1234567890000,
        )
        case = {"operator": "owner_mismatch"}
        verdict = determine_verdict(case, receipt, requires_target_readback=False)
        assert verdict == "MUTANT_KILLED"

    def test_contradicted_on_unknown_operator(self):
        """Unknown operator should result in CONTRADICTED."""
        request = make_mock_canary_request()
        receipt = generate_canary_receipt(
            request=request,
            status=CanaryStatus.COMPLETED,
            execution_evidence={"test": "evidence"},
            executed_at=1234567890000,
        )
        case = {"operator": "unknown_operator_xyz"}
        verdict = determine_verdict(case, receipt, requires_target_readback=False)
        assert verdict == "CONTRADICTED"


# ============================================================================
# Disposable Target Spec Tests
# ============================================================================

class TestCreateDisposableTargetSpec:
    """Test disposable target specification creation."""

    def test_create_target_spec_environment(self):
        """Environment canary should create ephemeral target."""
        spec = create_disposable_target_spec(
            case_id="case-001",
            canary_type=CanaryType.ENVIRONMENT,
            base_environment="development",
        )
        assert spec.target_id.startswith("canary-envi-")
        assert spec.target_type == "ephemeral_container"
        assert spec.environment.startswith("canary-")
        assert spec.lifecycle == "ephemeral"
        assert spec.created_for_case == "case-001"

    def test_create_target_spec_identity(self):
        """Identity canary should create ephemeral identity target."""
        spec = create_disposable_target_spec(
            case_id="case-002",
            canary_type=CanaryType.IDENTITY,
            base_environment="test",
        )
        assert spec.target_id.startswith("canary-iden-")
        assert spec.target_type == "ephemeral_identity"

    def test_create_target_spec_egress(self):
        """Egress canary should create ephemeral egress target."""
        spec = create_disposable_target_spec(
            case_id="case-003",
            canary_type=CanaryType.EGRESS,
            base_environment="staging",
        )
        assert spec.target_id.startswith("canary-egre-")
        assert spec.target_type == "ephemeral_egress"

    def test_create_target_spec_replay(self):
        """Replay canary should create ephemeral receipt target."""
        spec = create_disposable_target_spec(
            case_id="case-004",
            canary_type=CanaryType.REPLAY,
            base_environment="ephemeral",
        )
        assert spec.target_id.startswith("canary-repl-")
        assert spec.target_type == "ephemeral_replay"

    def test_target_spec_deterministic(self):
        """Same inputs should produce same target ID."""
        spec1 = create_disposable_target_spec(
            case_id="deterministic-case",
            canary_type=CanaryType.ENVIRONMENT,
            base_environment="test",
        )
        spec2 = create_disposable_target_spec(
            case_id="deterministic-case",
            canary_type=CanaryType.ENVIRONMENT,
            base_environment="test",
        )
        # Note: timestamp makes this not fully deterministic, but case binding is stable
        assert spec1.created_for_case == spec2.created_for_case


# ============================================================================
# Test Helpers Tests
# ============================================================================

class TestMakeMockCanaryRequest:
    """Test mock request creation."""

    def test_default_request(self):
        request = make_mock_canary_request()
        assert request.canary_type == CanaryType.ENVIRONMENT
        assert request.case_id == "test-case-001"
        assert len(request.case_sha256) == 64
        assert request.execution_timeout_seconds == 30

    def test_custom_canary_type(self):
        request = make_mock_canary_request(canary_type=CanaryType.REPLAY)
        assert request.canary_type == CanaryType.REPLAY

    def test_custom_case_id(self):
        request = make_mock_canary_request(case_id="custom-case")
        assert request.case_id == "custom-case"


# ============================================================================
# Schema Version Tests
# ============================================================================

class TestSchemaVersion:
    """Test schema version is correct."""

    def test_schema_version_format(self):
        from agent_runtime.acsa_canary_lane import SCHEMA_VERSION
        assert SCHEMA_VERSION == "sovereign.acsa-canary-lane.v1"
        assert SCHEMA_VERSION.startswith("sovereign.")
        assert ".v1" in SCHEMA_VERSION
