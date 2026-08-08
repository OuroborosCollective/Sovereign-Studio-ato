"""Unit tests for the Permission Receipt module.

Tests cover:
- PermissionReceipt creation and validation
- Secret redaction
- State transitions
- Attestation hash verification
- ExecutionAttempt creation and validation
- Cross-repository/tenant isolation
"""

import pytest

from backend.agent_runtime.permission_receipt import (
    CapabilityClass,
    EffectSurface,
    ExecutionAttempt,
    ExecutionAttemptFactory,
    PermissionContractError,
    PermissionReceipt,
    PermissionReceiptFactory,
    PermissionState,
    SecretRedactionFilter,
    _canonical_sha256,
)


# ---------------------------------------------------------------------------
# Constants for tests
# ---------------------------------------------------------------------------
_VALID_REVISION = "a" * 40  # Valid 40-char hex SHA
_VALID_OWNER = "test-owner"
_VALID_REPO_OWNER = "test-repo-owner"
_VALID_REPO_NAME = "test-repo"


# ---------------------------------------------------------------------------
# SecretRedactionFilter tests
# ---------------------------------------------------------------------------

class TestSecretRedactionFilter:
    """Tests for secret detection and redaction."""

    def test_contains_secret_bearer_token(self):
        """Bearer tokens should be detected as secrets."""
        assert SecretRedactionFilter.contains_secret("Bearer ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ")

    def test_contains_secret_github_token(self):
        """GitHub tokens should be detected."""
        assert SecretRedactionFilter.contains_secret("ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789012")
        # github_pat format (too short for our pattern, but check Bearer token format)
        assert SecretRedactionFilter.contains_secret("Bearer github_pat_11AAAAShortForm")

    def test_contains_secret_password(self):
        """Password patterns should be detected."""
        assert SecretRedactionFilter.contains_secret("password=mysecretpassword")
        assert SecretRedactionFilter.contains_secret("PASSWD: supersecret")

    def test_contains_secret_api_key(self):
        """API key patterns should be detected."""
        assert SecretRedactionFilter.contains_secret("api_key=sk-1234567890abcdef")
        assert SecretRedactionFilter.contains_secret("APIKEY: ghp_ABCDE")

    def test_contains_secret_aws_key(self):
        """AWS access keys should be detected."""
        assert SecretRedactionFilter.contains_secret("AKIAIOSFODNN7EXAMPLE")

    def test_contains_secret_pem_block(self):
        """PEM private keys should be detected."""
        assert SecretRedactionFilter.contains_secret("-----BEGIN PRIVATE KEY-----")

    def test_contains_secret_jwt(self):
        """JWT tokens should be detected."""
        assert SecretRedactionFilter.contains_secret(
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        )

    def test_contains_secret_safe_text(self):
        """Normal text should not be flagged."""
        assert not SecretRedactionFilter.contains_secret("This is a normal message")
        assert not SecretRedactionFilter.contains_secret("file path: /workspace/project/test.py")
        assert not SecretRedactionFilter.contains_secret("sha256:abc123def456")

    def test_check_and_sanitize_raises_on_secret(self):
        """check_and_sanitize should raise on secret content."""
        with pytest.raises(PermissionContractError, match="secret-shaped content is forbidden"):
            SecretRedactionFilter.check_and_sanitize("api_key=sk-1234567890abcdef")

    def test_check_and_sanitize_passes_clean(self):
        """check_and_sanitize should pass clean text."""
        result = SecretRedactionFilter.check_and_sanitize("normal text content")
        assert result == "normal text content"

    def test_check_payload_dict_with_secrets(self):
        """check_payload should detect secrets in nested dicts."""
        with pytest.raises(PermissionContractError):
            SecretRedactionFilter.check_payload({
                "normal_key": "normal_value",
                "secret_key": "api_key=sk-1234567890abcdef"
            })

    def test_check_payload_dict_clean(self):
        """check_payload should pass clean nested dicts."""
        result = SecretRedactionFilter.check_payload({
            "path": "/workspace/project/test.py",
            "content": "print('hello world')",
        })
        assert result["path"] == "/workspace/project/test.py"


# ---------------------------------------------------------------------------
# PermissionReceipt creation tests
# ---------------------------------------------------------------------------

class TestPermissionReceiptCreation:
    """Tests for PermissionReceipt factory methods."""

    def test_create_basic_permission_receipt(self):
        """Creating a basic permission receipt should succeed."""
        receipt = PermissionReceiptFactory.create_permission_request(
            owner=_VALID_OWNER,
            repo_owner=_VALID_REPO_OWNER,
            repo_name=_VALID_REPO_NAME,
            workspace_id="workspace-123",
            base_revision=_VALID_REVISION,
            tool_name="file",
            capability_class=CapabilityClass.MUTATE,
            effect_class="workspace_mutation",
            parameters={"path": "test.py", "content": "print('hello')"},
        )

        assert receipt.permission_id.startswith("perm-")
        assert receipt.schema_version == "sovereign.permission-receipt.v1"
        assert receipt.state == PermissionState.REQUESTED
        assert receipt.owner == _VALID_OWNER
        assert receipt.repo_owner == _VALID_REPO_OWNER
        assert receipt.repo_name == _VALID_REPO_NAME
        assert receipt.base_revision == _VALID_REVISION
        assert receipt.tool_name == "file"
        assert receipt.capability_class == CapabilityClass.MUTATE
        assert receipt.effect_class == "workspace_mutation"
        assert receipt.parameters_hash  # Should be computed

    def test_create_readonly_permission(self):
        """Creating a read-only permission should succeed."""
        receipt = PermissionReceiptFactory.create_permission_request(
            owner=_VALID_OWNER,
            repo_owner=_VALID_REPO_OWNER,
            repo_name=_VALID_REPO_NAME,
            base_revision=_VALID_REVISION,
            tool_name="read",
            capability_class=CapabilityClass.INSPECT,
            effect_class="read_only",
            parameters={"path": "README.md"},
        )

        assert receipt.capability_class == CapabilityClass.INSPECT
        assert receipt.effect_class == "read_only"

    def test_create_with_expected_changed_paths(self):
        """Permission should capture expected changed paths."""
        receipt = PermissionReceiptFactory.create_permission_request(
            owner=_VALID_OWNER,
            repo_owner=_VALID_REPO_OWNER,
            repo_name=_VALID_REPO_NAME,
            base_revision=_VALID_REVISION,
            tool_name="file",
            capability_class=CapabilityClass.MUTATE,
            effect_class="workspace_mutation",
            parameters={"path": "test.py", "content": "test"},
            expected_changed_paths=["test.py", "README.md"],
        )

        assert "test.py" in receipt.expected_changed_paths
        assert "README.md" in receipt.expected_changed_paths

    def test_create_with_workflow_binding(self):
        """Permission should capture workflow context."""
        receipt = PermissionReceiptFactory.create_permission_request(
            owner=_VALID_OWNER,
            repo_owner=_VALID_REPO_OWNER,
            repo_name=_VALID_REPO_NAME,
            base_revision=_VALID_REVISION,
            tool_name="file",
            capability_class=CapabilityClass.MUTATE,
            effect_class="workspace_mutation",
            parameters={},
            workflow_id="workflow-123",
            workflow_run_id="run-456",
            step_id="step-789",
        )

        assert receipt.workflow_id == "workflow-123"
        assert receipt.workflow_run_id == "run-456"
        assert receipt.step_id == "step-789"

    def test_create_rejects_empty_owner(self):
        """Empty owner should raise."""
        with pytest.raises(PermissionContractError, match="owner must not be empty"):
            PermissionReceiptFactory.create_permission_request(
                owner="",
                repo_owner=_VALID_REPO_OWNER,
                repo_name=_VALID_REPO_NAME,
                base_revision=_VALID_REVISION,
                tool_name="file",
                capability_class=CapabilityClass.MUTATE,
                effect_class="workspace_mutation",
                parameters={},
            )

    def test_create_rejects_invalid_revision(self):
        """Invalid SHA format should raise."""
        with pytest.raises(PermissionContractError, match="base_revision must be a 40-character"):
            PermissionReceiptFactory.create_permission_request(
                owner=_VALID_OWNER,
                repo_owner=_VALID_REPO_OWNER,
                repo_name=_VALID_REPO_NAME,
                base_revision="invalid-sha",
                tool_name="file",
                capability_class=CapabilityClass.MUTATE,
                effect_class="workspace_mutation",
                parameters={},
            )

    def test_create_rejects_path_traversal_in_repo(self):
        """Path traversal in repo_owner should raise."""
        with pytest.raises(PermissionContractError, match="forbidden characters"):
            PermissionReceiptFactory.create_permission_request(
                owner=_VALID_OWNER,
                repo_owner="../other",
                repo_name=_VALID_REPO_NAME,
                base_revision=_VALID_REVISION,
                tool_name="file",
                capability_class=CapabilityClass.MUTATE,
                effect_class="workspace_mutation",
                parameters={},
            )

    def test_create_rejects_invalid_capability_combination(self):
        """MUTATE with read_only effect should raise."""
        with pytest.raises(PermissionContractError, match="MUTATE capability_class requires"):
            PermissionReceiptFactory.create_permission_request(
                owner=_VALID_OWNER,
                repo_owner=_VALID_REPO_OWNER,
                repo_name=_VALID_REPO_NAME,
                base_revision=_VALID_REVISION,
                tool_name="file",
                capability_class=CapabilityClass.MUTATE,
                effect_class="read_only",
                parameters={},
            )

    def test_create_rejects_invalid_effect_class(self):
        """Invalid effect_class should raise."""
        with pytest.raises(PermissionContractError, match="effect_class must be one of"):
            PermissionReceiptFactory.create_permission_request(
                owner=_VALID_OWNER,
                repo_owner=_VALID_REPO_OWNER,
                repo_name=_VALID_REPO_NAME,
                base_revision=_VALID_REVISION,
                tool_name="file",
                capability_class=CapabilityClass.MUTATE,
                effect_class="invalid_effect",
                parameters={},
            )

    def test_create_rejects_secret_in_parameters(self):
        """Secrets in parameters should raise."""
        with pytest.raises(PermissionContractError, match="secret-shaped content is forbidden"):
            PermissionReceiptFactory.create_permission_request(
                owner=_VALID_OWNER,
                repo_owner=_VALID_REPO_OWNER,
                repo_name=_VALID_REPO_NAME,
                base_revision=_VALID_REVISION,
                tool_name="shell",
                capability_class=CapabilityClass.MUTATE,
                effect_class="external_mutation",
                parameters={"command": "curl https://api.example.com -H 'Authorization: Bearer secret123'"},
            )

    def test_create_with_custom_validity(self):
        """Custom validity seconds should be accepted."""
        receipt = PermissionReceiptFactory.create_permission_request(
            owner=_VALID_OWNER,
            repo_owner=_VALID_REPO_OWNER,
            repo_name=_VALID_REPO_NAME,
            base_revision=_VALID_REVISION,
            tool_name="file",
            capability_class=CapabilityClass.MUTATE,
            effect_class="workspace_mutation",
            parameters={},
            validity_seconds=7200,  # 2 hours
        )

        assert receipt.validity_seconds == 7200

    def test_create_rejects_invalid_validity(self):
        """Invalid validity_seconds should raise."""
        with pytest.raises(PermissionContractError, match="validity_seconds must be between"):
            PermissionReceiptFactory.create_permission_request(
                owner=_VALID_OWNER,
                repo_owner=_VALID_REPO_OWNER,
                repo_name=_VALID_REPO_NAME,
                base_revision=_VALID_REVISION,
                tool_name="file",
                capability_class=CapabilityClass.MUTATE,
                effect_class="workspace_mutation",
                parameters={},
                validity_seconds=-1,
            )


# ---------------------------------------------------------------------------
# Attestation hash tests
# ---------------------------------------------------------------------------

class TestAttestationHash:
    """Tests for attestation hash computation and verification."""

    def test_attestation_hash_is_deterministic(self):
        """Same inputs should produce same parameters_hash, not attestation_hash.

        The attestation_hash includes permission_id which is unique per receipt.
        The parameters_hash is the same for identical parameters.
        """
        params = {"path": "test.py", "content": "test"}
        
        receipt1 = PermissionReceiptFactory.create_permission_request(
            owner=_VALID_OWNER,
            repo_owner=_VALID_REPO_OWNER,
            repo_name=_VALID_REPO_NAME,
            base_revision=_VALID_REVISION,
            tool_name="file",
            capability_class=CapabilityClass.MUTATE,
            effect_class="workspace_mutation",
            parameters=params,
        )
        
        receipt2 = PermissionReceiptFactory.create_permission_request(
            owner=_VALID_OWNER,
            repo_owner=_VALID_REPO_OWNER,
            repo_name=_VALID_REPO_NAME,
            base_revision=_VALID_REVISION,
            tool_name="file",
            capability_class=CapabilityClass.MUTATE,
            effect_class="workspace_mutation",
            parameters=params,
        )
        
        # Different permission IDs (unique per receipt)
        assert receipt1.permission_id != receipt2.permission_id
        # But parameters hash is the same for identical parameters
        assert receipt1.parameters_hash == receipt2.parameters_hash

    def test_attestation_hash_changes_with_different_params(self):
        """Different parameters should produce different hash."""
        receipt1 = PermissionReceiptFactory.create_permission_request(
            owner=_VALID_OWNER,
            repo_owner=_VALID_REPO_OWNER,
            repo_name=_VALID_REPO_NAME,
            base_revision=_VALID_REVISION,
            tool_name="file",
            capability_class=CapabilityClass.MUTATE,
            effect_class="workspace_mutation",
            parameters={"path": "test1.py"},
        )
        
        receipt2 = PermissionReceiptFactory.create_permission_request(
            owner=_VALID_OWNER,
            repo_owner=_VALID_REPO_OWNER,
            repo_name=_VALID_REPO_NAME,
            base_revision=_VALID_REVISION,
            tool_name="file",
            capability_class=CapabilityClass.MUTATE,
            effect_class="workspace_mutation",
            parameters={"path": "test2.py"},
        )
        
        assert receipt1.attestation_hash != receipt2.attestation_hash

    def test_attestation_hash_changes_with_different_revision(self):
        """Different revision should produce different hash."""
        params = {"path": "test.py"}
        
        receipt1 = PermissionReceiptFactory.create_permission_request(
            owner=_VALID_OWNER,
            repo_owner=_VALID_REPO_OWNER,
            repo_name=_VALID_REPO_NAME,
            base_revision="a" * 40,
            tool_name="file",
            capability_class=CapabilityClass.MUTATE,
            effect_class="workspace_mutation",
            parameters=params,
        )
        
        receipt2 = PermissionReceiptFactory.create_permission_request(
            owner=_VALID_OWNER,
            repo_owner=_VALID_REPO_OWNER,
            repo_name=_VALID_REPO_NAME,
            base_revision="b" * 40,
            tool_name="file",
            capability_class=CapabilityClass.MUTATE,
            effect_class="workspace_mutation",
            parameters=params,
        )
        
        assert receipt1.attestation_hash != receipt2.attestation_hash

    def test_verify_attestation_valid(self):
        """Valid receipt should pass verification."""
        receipt = PermissionReceiptFactory.create_permission_request(
            owner=_VALID_OWNER,
            repo_owner=_VALID_REPO_OWNER,
            repo_name=_VALID_REPO_NAME,
            base_revision=_VALID_REVISION,
            tool_name="file",
            capability_class=CapabilityClass.MUTATE,
            effect_class="workspace_mutation",
            parameters={"path": "test.py"},
        )
        
        assert PermissionReceiptFactory.verify_attestation(receipt) is True

    def test_verify_attestation_fails_on_tamper(self):
        """Tampered receipt should fail verification."""
        receipt = PermissionReceiptFactory.create_permission_request(
            owner=_VALID_OWNER,
            repo_owner=_VALID_REPO_OWNER,
            repo_name=_VALID_REPO_NAME,
            base_revision=_VALID_REVISION,
            tool_name="file",
            capability_class=CapabilityClass.MUTATE,
            effect_class="workspace_mutation",
            parameters={"path": "test.py"},
        )
        
        # Create a copy with different state (simulating tamper)
        tampered = PermissionReceipt(
            permission_id=receipt.permission_id,
            schema_version=receipt.schema_version,
            permission_schema_version=receipt.permission_schema_version,
            owner=receipt.owner,
            tenant_or_org=receipt.tenant_or_org,
            repo_owner=receipt.repo_owner,
            repo_name=receipt.repo_name,
            workspace_id=receipt.workspace_id,
            base_revision="b" * 40,  # Changed!
            head_revision=receipt.head_revision,
            target_revision=receipt.target_revision,
            workflow_id=receipt.workflow_id,
            workflow_run_id=receipt.workflow_run_id,
            step_id=receipt.step_id,
            tool_name=receipt.tool_name,
            capability_class=receipt.capability_class,
            effect_class=receipt.effect_class,
            parameters=receipt.parameters,
            parameters_hash=receipt.parameters_hash,
            expected_changed_paths=receipt.expected_changed_paths,
            expected_effect_surfaces=receipt.expected_effect_surfaces,
            expected_external_effects=receipt.expected_external_effects,
            required_preconditions=receipt.required_preconditions,
            required_readback_kinds=receipt.required_readback_kinds,
            created_at_iso=receipt.created_at_iso,
            validity_seconds=receipt.validity_seconds,
            max_retries=receipt.max_retries,
            approver_identity=receipt.approver_identity,
            approval_source=receipt.approval_source,
            state=receipt.state,
            predecessor_permission_id=receipt.predecessor_permission_id,
            successor_permission_id=receipt.successor_permission_id,
            attestation_hash=receipt.attestation_hash,  # Original hash
        )
        
        assert PermissionReceiptFactory.verify_attestation(tampered) is False


# ---------------------------------------------------------------------------
# State transition tests
# ---------------------------------------------------------------------------

class TestStateTransitions:
    """Tests for permission state transitions."""

    def test_approve_requested_permission(self):
        """REQUESTED permission can be approved."""
        receipt = PermissionReceiptFactory.create_permission_request(
            owner=_VALID_OWNER,
            repo_owner=_VALID_REPO_OWNER,
            repo_name=_VALID_REPO_NAME,
            base_revision=_VALID_REVISION,
            tool_name="file",
            capability_class=CapabilityClass.MUTATE,
            effect_class="workspace_mutation",
            parameters={"path": "test.py"},
        )
        
        assert receipt.state == PermissionState.REQUESTED
        
        approved = PermissionReceiptFactory.approve_permission(
            receipt,
            approver_identity="admin@example.com",
            approval_source="owner",
        )
        
        assert approved.state == PermissionState.APPROVED
        assert approved.approver_identity == "admin@example.com"
        assert approved.attestation_hash == receipt.attestation_hash  # Hash preserved

    def test_approve_non_requested_fails(self):
        """Non-REQUESTED permission cannot be approved."""
        receipt = PermissionReceiptFactory.create_permission_request(
            owner=_VALID_OWNER,
            repo_owner=_VALID_REPO_OWNER,
            repo_name=_VALID_REPO_NAME,
            base_revision=_VALID_REVISION,
            tool_name="file",
            capability_class=CapabilityClass.MUTATE,
            effect_class="workspace_mutation",
            parameters={"path": "test.py"},
        )
        
        approved = PermissionReceiptFactory.approve_permission(
            receipt,
            approver_identity="admin@example.com",
        )
        
        # Try to approve again - should fail
        with pytest.raises(PermissionContractError, match="Cannot approve permission in"):
            PermissionReceiptFactory.approve_permission(
                approved,
                approver_identity="admin2@example.com",
            )


# ---------------------------------------------------------------------------
# ExecutionAttempt tests
# ---------------------------------------------------------------------------

class TestExecutionAttempt:
    """Tests for ExecutionAttempt creation."""

    def test_create_succeeded_unverified(self):
        """Creating SUCCEEDED_UNVERIFIED attempt should succeed."""
        attempt = ExecutionAttemptFactory.create_attempt(
            permission_id="perm-12345678",
            run_id="run-123",
            executor_identity="sovereign-local-runner",
            container_or_runner="container-abc",
            base_revision=_VALID_REVISION,
            observed_head_revision="b" * 40,
            parameters_hash="hash123",
            start_state="RUNNING",
            end_state="COMPLETED",
            exit_status=0,
            output_hash="output-hash-456",
            changed_paths_hash="diff-hash-789",
            patch_hash="patch-hash-abc",
            created_identities=["commit-sha-123"],
            attempted_readbacks=["git_diff", "git_status"],
            successful_readbacks=[],  # None yet
            is_retry=False,
            previous_attempt_id=None,
            retry_classification="none",
            executed_at_iso="2026-08-08T12:00:00Z",
            verdict="SUCCEEDED_UNVERIFIED",
        )
        
        assert attempt.attempt_id.startswith("attempt-")
        assert attempt.verdict == "SUCCEEDED_UNVERIFIED"
        assert attempt.schema_version == "sovereign.permission-receipt.v1"
        assert attempt.created_identities == ("commit-sha-123",)

    def test_create_verified_requires_readbacks(self):
        """VERIFIED verdict requires successful_readbacks."""
        with pytest.raises(PermissionContractError, match="VERIFIED verdict requires"):
            ExecutionAttemptFactory.create_attempt(
                permission_id="perm-12345678",
                run_id="run-123",
                executor_identity="sovereign-local-runner",
                container_or_runner="container-abc",
                base_revision=_VALID_REVISION,
                observed_head_revision="b" * 40,
                parameters_hash="hash123",
                start_state="RUNNING",
                end_state="COMPLETED",
                exit_status=0,
                output_hash="output-hash-456",
                changed_paths_hash="diff-hash-789",
                patch_hash="patch-hash-abc",
                created_identities=["commit-sha-123"],
                attempted_readbacks=["git_diff"],
                successful_readbacks=[],  # Empty!
                is_retry=False,
                previous_attempt_id=None,
                retry_classification="none",
                executed_at_iso="2026-08-08T12:00:00Z",
                verdict="VERIFIED",  # This requires readbacks!
            )

    def test_create_verified_with_readbacks(self):
        """VERIFIED with successful readbacks should succeed."""
        attempt = ExecutionAttemptFactory.create_attempt(
            permission_id="perm-12345678",
            run_id="run-123",
            executor_identity="sovereign-local-runner",
            container_or_runner="container-abc",
            base_revision=_VALID_REVISION,
            observed_head_revision="b" * 40,
            parameters_hash="hash123",
            start_state="RUNNING",
            end_state="COMPLETED",
            exit_status=0,
            output_hash="output-hash-456",
            changed_paths_hash="diff-hash-789",
            patch_hash="patch-hash-abc",
            created_identities=["commit-sha-123"],
            attempted_readbacks=["git_diff", "git_status", "ci_workflow"],
            successful_readbacks=["git_diff", "git_status"],  # Partial success
            is_retry=False,
            previous_attempt_id=None,
            retry_classification="none",
            executed_at_iso="2026-08-08T12:00:00Z",
            verdict="VERIFIED",
        )
        
        assert attempt.verdict == "VERIFIED"
        assert "git_diff" in attempt.successful_readbacks

    def test_create_blocked(self):
        """BLOCKED verdict should succeed."""
        attempt = ExecutionAttemptFactory.create_attempt(
            permission_id="perm-12345678",
            run_id="run-123",
            executor_identity="sovereign-local-runner",
            container_or_runner="container-abc",
            base_revision=_VALID_REVISION,
            observed_head_revision=_VALID_REVISION,
            parameters_hash="hash123",
            start_state="RUNNING",
            end_state="BLOCKED",
            exit_status=1,
            output_hash="output-hash-blocked",
            changed_paths_hash=None,
            patch_hash=None,
            created_identities=[],
            attempted_readbacks=[],
            successful_readbacks=[],
            is_retry=False,
            previous_attempt_id=None,
            retry_classification="none",
            executed_at_iso="2026-08-08T12:00:00Z",
            verdict="BLOCKED",
        )
        
        assert attempt.verdict == "BLOCKED"

    def test_create_invalid_verdict_fails(self):
        """Invalid verdict should raise."""
        with pytest.raises(PermissionContractError, match="verdict must be one of"):
            ExecutionAttemptFactory.create_attempt(
                permission_id="perm-12345678",
                run_id="run-123",
                executor_identity="sovereign-local-runner",
                container_or_runner="container-abc",
                base_revision=_VALID_REVISION,
                observed_head_revision=_VALID_REVISION,
                parameters_hash="hash123",
                start_state="RUNNING",
                end_state="COMPLETED",
                exit_status=0,
                output_hash="output-hash-456",
                changed_paths_hash=None,
                patch_hash=None,
                created_identities=[],
                attempted_readbacks=[],
                successful_readbacks=[],
                is_retry=False,
                previous_attempt_id=None,
                retry_classification="none",
                executed_at_iso="2026-08-08T12:00:00Z",
                verdict="SUCCESS",  # Invalid!
            )


# ---------------------------------------------------------------------------
# Cross-tenant isolation tests
# ---------------------------------------------------------------------------

class TestCrossTenantIsolation:
    """Tests for cross-tenant/cross-repo isolation."""

    def test_different_owners_produce_different_hashes(self):
        """Different owners should produce different attestation hashes."""
        receipt1 = PermissionReceiptFactory.create_permission_request(
            owner="owner-alpha",
            repo_owner=_VALID_REPO_OWNER,
            repo_name=_VALID_REPO_NAME,
            base_revision=_VALID_REVISION,
            tool_name="file",
            capability_class=CapabilityClass.MUTATE,
            effect_class="workspace_mutation",
            parameters={"path": "test.py", "content": "test"},
        )
        
        receipt2 = PermissionReceiptFactory.create_permission_request(
            owner="owner-beta",
            repo_owner=_VALID_REPO_OWNER,
            repo_name=_VALID_REPO_NAME,
            base_revision=_VALID_REVISION,
            tool_name="file",
            capability_class=CapabilityClass.MUTATE,
            effect_class="workspace_mutation",
            parameters={"path": "test.py", "content": "test"},
        )
        
        assert receipt1.attestation_hash != receipt2.attestation_hash

    def test_different_repos_produce_different_hashes(self):
        """Different repo_owner/repo_name should produce different hashes."""
        receipt1 = PermissionReceiptFactory.create_permission_request(
            owner=_VALID_OWNER,
            repo_owner="org-alpha",
            repo_name="repo-a",
            base_revision=_VALID_REVISION,
            tool_name="file",
            capability_class=CapabilityClass.MUTATE,
            effect_class="workspace_mutation",
            parameters={"path": "test.py", "content": "test"},
        )
        
        receipt2 = PermissionReceiptFactory.create_permission_request(
            owner=_VALID_OWNER,
            repo_owner="org-alpha",
            repo_name="repo-b",
            base_revision=_VALID_REVISION,
            tool_name="file",
            capability_class=CapabilityClass.MUTATE,
            effect_class="workspace_mutation",
            parameters={"path": "test.py", "content": "test"},
        )
        
        assert receipt1.attestation_hash != receipt2.attestation_hash

    def test_different_tenants_produce_different_hashes(self):
        """Different tenant_or_org should produce different hashes."""
        receipt1 = PermissionReceiptFactory.create_permission_request(
            owner=_VALID_OWNER,
            repo_owner=_VALID_REPO_OWNER,
            repo_name=_VALID_REPO_NAME,
            base_revision=_VALID_REVISION,
            tool_name="file",
            capability_class=CapabilityClass.MUTATE,
            effect_class="workspace_mutation",
            parameters={"path": "test.py", "content": "test"},
            tenant_or_org="tenant-alpha",
        )
        
        receipt2 = PermissionReceiptFactory.create_permission_request(
            owner=_VALID_OWNER,
            repo_owner=_VALID_REPO_OWNER,
            repo_name=_VALID_REPO_NAME,
            base_revision=_VALID_REVISION,
            tool_name="file",
            capability_class=CapabilityClass.MUTATE,
            effect_class="workspace_mutation",
            parameters={"path": "test.py", "content": "test"},
            tenant_or_org="tenant-beta",
        )
        
        assert receipt1.attestation_hash != receipt2.attestation_hash


# ---------------------------------------------------------------------------
# Serialization tests
# ---------------------------------------------------------------------------

class TestSerialization:
    """Tests for dict serialization."""

    def test_permission_receipt_to_dict(self):
        """PermissionReceipt.to_dict should produce JSON-serializable output."""
        receipt = PermissionReceiptFactory.create_permission_request(
            owner=_VALID_OWNER,
            repo_owner=_VALID_REPO_OWNER,
            repo_name=_VALID_REPO_NAME,
            base_revision=_VALID_REVISION,
            tool_name="file",
            capability_class=CapabilityClass.MUTATE,
            effect_class="workspace_mutation",
            parameters={"path": "test.py"},
        )
        
        result = receipt.to_dict()
        
        assert isinstance(result, dict)
        assert result["permission_id"] == receipt.permission_id
        assert result["schema_version"] == receipt.schema_version
        assert result["owner"] == _VALID_OWNER
        assert result["capability_class"] == "mutate"
        assert result["state"] == "requested"

    def test_execution_attempt_to_dict(self):
        """ExecutionAttempt.to_dict should produce JSON-serializable output."""
        attempt = ExecutionAttemptFactory.create_attempt(
            permission_id="perm-12345678",
            run_id="run-123",
            executor_identity="sovereign-local-runner",
            container_or_runner="container-abc",
            base_revision=_VALID_REVISION,
            observed_head_revision=_VALID_REVISION,
            parameters_hash="hash123",
            start_state="RUNNING",
            end_state="COMPLETED",
            exit_status=0,
            output_hash="output-hash-456",
            changed_paths_hash=None,
            patch_hash=None,
            created_identities=[],
            attempted_readbacks=[],
            successful_readbacks=[],
            is_retry=False,
            previous_attempt_id=None,
            retry_classification="none",
            executed_at_iso="2026-08-08T12:00:00Z",
            verdict="SUCCEEDED_UNVERIFIED",
        )
        
        result = attempt.to_dict()
        
        assert isinstance(result, dict)
        assert result["attempt_id"] == attempt.attempt_id
        assert result["verdict"] == "SUCCEEDED_UNVERIFIED"
        assert result["run_id"] == "run-123"
