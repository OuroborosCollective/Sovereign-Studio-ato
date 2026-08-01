"""Tests for environment_mcp_execution.py — Issue #1120."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent_runtime.environment_mcp_execution import (  # noqa: E402
    CredentialMode,
    CredentialResolver,
    EgressBlockReason,
    EgressDecision,
    EgressPolicyEngine,
    EnvironmentContractError,
    EnvironmentKind,
    EnvironmentManifest,
    EnvironmentManifestCompiler,
    ExecutionIdentityReceiptBuilder,
    McpInstallationBinder,
    PrincipalResolutionReceipt,
    PrincipalResolver,
    ResolutionMethod,
)

_SHA = "a" * 40
_SHA2 = "b" * 40
_OWNER = "OuroborosCollective"
_REPO = "Sovereign-Studio-ato"
_PUBLIC_IP = "1.1.1.1"


def _make_manifest(
    kind: EnvironmentKind = EnvironmentKind.DEVELOPMENT,
    environment_id: str = "development",
    allowed_egress_hosts: tuple = (),
) -> EnvironmentManifest:
    return EnvironmentManifestCompiler.compile(
        environment_id=environment_id,
        kind=kind,
        repo_owner=_OWNER,
        repo_name=_REPO,
        revision=_SHA,
        network_policy_descriptor={"allow": ["https"]},
        credential_scope_descriptor={"scope": "read"},
        allowed_protocols=("https",),
        allowed_egress_hosts=list(allowed_egress_hosts),
    )


def _make_principal_receipt(
    manifest: EnvironmentManifest | None = None,
) -> PrincipalResolutionReceipt:
    m = manifest or _make_manifest()
    return PrincipalResolver.resolve(
        environment_id=m.environment_id,
        server_resolved_principal_id="user-alice",
        owner_id=_OWNER,
        resolution_method=ResolutionMethod.SERVER_JWT,
        run_id="run-001",
        revision=_SHA,
    )


# ===========================================================================
# EnvironmentManifestCompiler
# ===========================================================================

class TestEnvironmentManifestCompiler:
    def test_compile_development(self):
        m = _make_manifest()
        assert m.kind == EnvironmentKind.DEVELOPMENT
        assert not m.is_production

    def test_compile_production(self):
        m = _make_manifest(kind=EnvironmentKind.PRODUCTION, environment_id="production")
        assert m.is_production

    def test_manifest_hash_self_consistent(self):
        m = _make_manifest()
        assert EnvironmentManifestCompiler.verify(m)

    def test_tampered_kind_breaks_hash(self):
        import dataclasses
        m = _make_manifest()
        tampered = dataclasses.replace(m, kind=EnvironmentKind.PRODUCTION, is_production=True)
        assert not EnvironmentManifestCompiler.verify(tampered)

    def test_empty_environment_id_raises(self):
        with pytest.raises(EnvironmentContractError):
            EnvironmentManifestCompiler.compile(
                environment_id="", kind=EnvironmentKind.DEVELOPMENT,
                repo_owner=_OWNER, repo_name=_REPO,
                network_policy_descriptor={}, credential_scope_descriptor={},
            )

    def test_invalid_environment_id_raises(self):
        with pytest.raises(EnvironmentContractError):
            EnvironmentManifestCompiler.compile(
                environment_id="My Environment!", kind=EnvironmentKind.DEVELOPMENT,
                repo_owner=_OWNER, repo_name=_REPO,
                network_policy_descriptor={}, credential_scope_descriptor={},
            )

    def test_empty_protocols_raises(self):
        with pytest.raises(EnvironmentContractError):
            EnvironmentManifestCompiler.compile(
                environment_id="development", kind=EnvironmentKind.DEVELOPMENT,
                repo_owner=_OWNER, repo_name=_REPO,
                network_policy_descriptor={}, credential_scope_descriptor={},
                allowed_protocols=[],
            )

    def test_path_traversal_owner_raises(self):
        with pytest.raises(EnvironmentContractError):
            EnvironmentManifestCompiler.compile(
                environment_id="development", kind=EnvironmentKind.DEVELOPMENT,
                repo_owner="../evil", repo_name=_REPO,
                network_policy_descriptor={}, credential_scope_descriptor={},
            )

    def test_ephemeral_environment_id(self):
        m = EnvironmentManifestCompiler.compile(
            environment_id="ephemeral/run-001",
            kind=EnvironmentKind.EPHEMERAL,
            repo_owner=_OWNER, repo_name=_REPO,
            revision=_SHA,
            network_policy_descriptor={}, credential_scope_descriptor={},
        )
        assert m.environment_id == "ephemeral/run-001"


# ===========================================================================
# PrincipalResolver
# ===========================================================================

class TestPrincipalResolver:
    def test_resolve_server_jwt(self):
        r = _make_principal_receipt()
        assert r.is_server_resolved
        assert r.principal_id == "user-alice"

    def test_empty_principal_raises(self):
        with pytest.raises(EnvironmentContractError):
            PrincipalResolver.resolve(
                environment_id="development",
                server_resolved_principal_id="",
                owner_id=_OWNER,
                resolution_method=ResolutionMethod.SERVER_JWT,
            )

    def test_client_candidate_stored_separately(self):
        r = PrincipalResolver.resolve(
            environment_id="development",
            server_resolved_principal_id="user-alice",
            owner_id=_OWNER,
            resolution_method=ResolutionMethod.SERVER_JWT,
            run_id="run-001",
            revision=_SHA,
            client_supplied_candidate="attacker-user",
        )
        # Client-supplied candidate stored for audit, but principal_id is server-resolved
        assert r.principal_id == "user-alice"
        assert r.client_supplied_candidate == "attacker-user"

    def test_identical_resolution_is_idempotent(self):
        r1 = _make_principal_receipt()
        r2 = _make_principal_receipt()
        assert r1.receipt_id == r2.receipt_id
        assert r1.receipt_hash == r2.receipt_hash


# ===========================================================================
# CredentialResolver
# ===========================================================================

class TestCredentialResolver:
    def test_basic_direct_credential(self):
        r = CredentialResolver.resolve(
            environment_id="development",
            credential_id="openrouter-dev-key-v1",
            owner_id=_OWNER,
            mode=CredentialMode.DIRECT,
            provider="openrouter",
            scopes=["read", "write"],
            executed_as_principal_id="user-alice",
        )
        assert r.credential_id == "openrouter-dev-key-v1"
        assert r.mode == CredentialMode.DIRECT
        assert not r.is_expired

    def test_no_raw_scopes_in_receipt(self):
        """Raw scopes must not appear in the receipt — only scope_hash."""
        r = CredentialResolver.resolve(
            environment_id="development",
            credential_id="key-v1",
            owner_id=_OWNER,
            mode=CredentialMode.DIRECT,
            provider="github",
            scopes=["repo:write", "pr:merge"],
            executed_as_principal_id="user-alice",
        )
        import json
        d = json.dumps({
            "credential_id": r.credential_id,
            "scope_hash": r.scope_hash,
            "mode": r.mode.value,
        })
        # Raw scopes must not appear
        assert "repo:write" not in d
        assert "pr:merge" not in d
        # But the scope_hash is present
        assert len(r.scope_hash) == 64

    def test_expired_credential_raises(self):
        with pytest.raises(EnvironmentContractError):
            CredentialResolver.resolve(
                environment_id="development",
                credential_id="key-v1",
                owner_id=_OWNER,
                mode=CredentialMode.DIRECT,
                provider="openrouter",
                scopes=["read"],
                executed_as_principal_id="user-alice",
                is_expired=True,
            )

    def test_obo_requires_audience(self):
        with pytest.raises(EnvironmentContractError, match="audience"):
            CredentialResolver.resolve(
                environment_id="development",
                credential_id="key-v1",
                owner_id=_OWNER,
                mode=CredentialMode.ON_BEHALF_OF,
                provider="github",
                scopes=["read"],
                executed_as_principal_id="user-alice",
                audience=None,  # missing
            )

    def test_obo_scope_insufficient_raises(self):
        with pytest.raises(EnvironmentContractError, match="OBO_SCOPE_INSUFFICIENT"):
            CredentialResolver.resolve(
                environment_id="development",
                credential_id="key-v1",
                owner_id=_OWNER,
                mode=CredentialMode.ON_BEHALF_OF,
                provider="github",
                scopes=["read"],
                executed_as_principal_id="user-alice",
                audience="https://api.github.com",
                obo_required_scopes=["write"],  # not in scopes
            )

    def test_obo_with_sufficient_scopes(self):
        r = CredentialResolver.resolve(
            environment_id="development",
            credential_id="key-v1",
            owner_id=_OWNER,
            mode=CredentialMode.ON_BEHALF_OF,
            provider="github",
            scopes=["read", "write"],
            executed_as_principal_id="user-alice",
            audience="https://api.github.com",
            obo_required_scopes=["write"],
        )
        assert r.mode == CredentialMode.ON_BEHALF_OF

    def test_empty_credential_id_raises(self):
        with pytest.raises(EnvironmentContractError):
            CredentialResolver.resolve(
                environment_id="development",
                credential_id="",
                owner_id=_OWNER,
                mode=CredentialMode.DIRECT,
                provider="openrouter",
                scopes=[],
                executed_as_principal_id="user-alice",
            )


# ===========================================================================
# EgressPolicyEngine
# ===========================================================================

class TestEgressPolicyEngine:
    def _dev_manifest(self, hosts=()) -> EnvironmentManifest:
        return _make_manifest(allowed_egress_hosts=hosts)

    def test_allows_public_https(self):
        m = _make_manifest(allowed_egress_hosts=("api.openai.com",))
        r = EgressPolicyEngine.decide(
            environment_manifest=m,
            target_host="api.openai.com",
            protocol="https",
            resolved_ip=_PUBLIC_IP,
        )
        assert r.decision == EgressDecision.ALLOW

    def test_blocks_loopback_hostname(self):
        m = _make_manifest(allowed_egress_hosts=("localhost",))
        r = EgressPolicyEngine.decide(
            environment_manifest=m,
            target_host="localhost",
            protocol="https",
        )
        assert r.decision == EgressDecision.BLOCK
        assert r.block_reason == EgressBlockReason.BLOCKED_HOSTNAME

    def test_blocks_metadata_ip_hostname(self):
        r = EgressPolicyEngine.decide(
            environment_manifest=_make_manifest(),
            target_host="169.254.169.254",
            protocol="https",
        )
        assert r.decision == EgressDecision.BLOCK
        # IP-first check classifies this as METADATA_IP (more specific than BLOCKED_HOSTNAME)
        assert r.block_reason in (EgressBlockReason.METADATA_IP, EgressBlockReason.BLOCKED_HOSTNAME)

    def test_blocks_gcp_metadata_hostname(self):
        r = EgressPolicyEngine.decide(
            environment_manifest=_make_manifest(),
            target_host="metadata.google.internal",
            protocol="https",
        )
        assert r.decision == EgressDecision.BLOCK

    def test_blocks_loopback_resolved_ip(self):
        r = EgressPolicyEngine.decide(
            environment_manifest=_make_manifest(allowed_egress_hosts=("legitimate.example.com",)),
            target_host="legitimate.example.com",
            protocol="https",
            resolved_ip="127.0.0.1",  # DNS rebinding
        )
        assert r.decision == EgressDecision.BLOCK
        assert r.block_reason == EgressBlockReason.LOOPBACK

    def test_blocks_private_network_resolved_ip(self):
        r = EgressPolicyEngine.decide(
            environment_manifest=_make_manifest(allowed_egress_hosts=("internal.example.com",)),
            target_host="internal.example.com",
            protocol="https",
            resolved_ip="10.0.0.1",  # private network
        )
        assert r.decision == EgressDecision.BLOCK
        assert r.block_reason == EgressBlockReason.PRIVATE_NETWORK

    def test_blocks_link_local_resolved_ip(self):
        r = EgressPolicyEngine.decide(
            environment_manifest=_make_manifest(allowed_egress_hosts=("x.example.com",)),
            target_host="x.example.com",
            protocol="https",
            resolved_ip="169.254.169.254",  # link-local metadata
        )
        assert r.decision == EgressDecision.BLOCK

    def test_blocks_rfc1918_192_range(self):
        r = EgressPolicyEngine.decide(
            environment_manifest=_make_manifest(allowed_egress_hosts=("x.example.com",)),
            target_host="x.example.com",
            protocol="https",
            resolved_ip="192.168.1.1",
        )
        assert r.decision == EgressDecision.BLOCK

    def test_blocks_disallowed_protocol(self):
        r = EgressPolicyEngine.decide(
            environment_manifest=_make_manifest(allowed_egress_hosts=("x.example.com",)),
            target_host="x.example.com",
            protocol="ftp",
        )
        assert r.decision == EgressDecision.BLOCK
        assert r.block_reason == EgressBlockReason.PROTOCOL_NOT_ALLOWED

    def test_blocks_prod_host_from_dev(self):
        m = _make_manifest(kind=EnvironmentKind.DEVELOPMENT, environment_id="development")
        r = EgressPolicyEngine.decide(
            environment_manifest=m,
            target_host="api.prod.example.com",
            protocol="https",
        )
        assert r.decision == EgressDecision.BLOCK
        assert r.block_reason == EgressBlockReason.PRODUCTION_TARGET_FROM_NONPROD

    def test_blocks_host_not_in_allowlist(self):
        m = _make_manifest(allowed_egress_hosts=("allowed.example.com",))
        r = EgressPolicyEngine.decide(
            environment_manifest=m,
            target_host="notallowed.example.com",
            protocol="https",
        )
        assert r.decision == EgressDecision.BLOCK
        assert r.block_reason == EgressBlockReason.ENVIRONMENT_POLICY

    def test_subdomain_of_allowlisted_host_allowed(self):
        m = _make_manifest(allowed_egress_hosts=("example.com",))
        r = EgressPolicyEngine.decide(
            environment_manifest=m,
            target_host="api.example.com",
            protocol="https",
            resolved_ip=_PUBLIC_IP,
        )
        assert r.decision == EgressDecision.ALLOW

    def test_receipt_hash_committed(self):
        m = _make_manifest(allowed_egress_hosts=("api.openai.com",))
        r = EgressPolicyEngine.decide(
            environment_manifest=m,
            target_host="api.openai.com",
            protocol="https",
            resolved_ip=_PUBLIC_IP,
        )
        assert len(r.receipt_hash) == 64

    def test_block_receipt_has_reason(self):
        r = EgressPolicyEngine.decide(
            environment_manifest=_make_manifest(),
            target_host="127.0.0.1",
            protocol="https",
        )
        assert r.decision == EgressDecision.BLOCK
        assert r.block_reason is not None


# ===========================================================================
# McpInstallationBinder
# ===========================================================================

class TestMcpInstallationBinder:
    def test_basic_binding(self):
        b = McpInstallationBinder.bind(
            tool_id="sovereign-workspace-executor",
            server_id="mcp-server-v2",
            installation_id="install-001",
            registry_revision=_SHA,
            verified_at_revision=_SHA,
        )
        assert b.tool_id == "sovereign-workspace-executor"
        assert len(b.binding_hash) == 64

    def test_invalid_registry_revision_raises(self):
        with pytest.raises(EnvironmentContractError):
            McpInstallationBinder.bind(
                tool_id="tool",
                server_id="server",
                installation_id="install",
                registry_revision="not-a-sha",
            )

    def test_empty_tool_id_raises(self):
        with pytest.raises(EnvironmentContractError):
            McpInstallationBinder.bind(
                tool_id="",
                server_id="server",
                installation_id="install",
                registry_revision=_SHA,
            )

    def test_different_installations_have_different_hashes(self):
        b1 = McpInstallationBinder.bind(
            tool_id="tool", server_id="server", installation_id="install-A",
            registry_revision=_SHA, verified_at_revision=_SHA,
        )
        b2 = McpInstallationBinder.bind(
            tool_id="tool", server_id="server", installation_id="install-B",
            registry_revision=_SHA, verified_at_revision=_SHA,
        )
        assert b1.binding_hash != b2.binding_hash


# ===========================================================================
# ExecutionIdentityReceiptBuilder
# ===========================================================================

class TestExecutionIdentityReceiptBuilder:
    def _setup(self):
        manifest = _make_manifest(
            kind=EnvironmentKind.DEVELOPMENT,
            allowed_egress_hosts=("api.openai.com",),
        )
        principal = _make_principal_receipt(manifest)
        credential = CredentialResolver.resolve(
            environment_id=manifest.environment_id,
            credential_id="key-v1",
            owner_id=_OWNER,
            mode=CredentialMode.DIRECT,
            provider="openrouter",
            scopes=["read"],
            executed_as_principal_id=principal.principal_id,
        )
        egress = EgressPolicyEngine.decide(
            environment_manifest=manifest,
            target_host="api.openai.com",
            protocol="https",
            resolved_ip=_PUBLIC_IP,
        )
        binding = McpInstallationBinder.bind(
            tool_id="worker-tool",
            server_id="mcp-server",
            installation_id="install-001",
            registry_revision=_SHA,
            verified_at_revision=_SHA,
        )
        return manifest, principal, credential, egress, binding

    def test_build_execution_receipt(self):
        manifest, principal, credential, egress, binding = self._setup()
        r = ExecutionIdentityReceiptBuilder.build(
            run_id="run-001",
            environment_manifest=manifest,
            principal_receipt=principal,
            credential_receipt=credential,
            egress_receipt=egress,
            installation_binding=binding,
        )
        assert r.environment_kind == EnvironmentKind.DEVELOPMENT
        assert r.tool_id == "worker-tool"
        assert len(r.receipt_hash) == 64

    def test_blocked_egress_prevents_receipt(self):
        manifest, principal, credential, _, binding = self._setup()
        blocked_egress = EgressPolicyEngine.decide(
            environment_manifest=manifest,
            target_host="localhost",
            protocol="https",
        )
        with pytest.raises(EnvironmentContractError, match="egress decision"):
            ExecutionIdentityReceiptBuilder.build(
                run_id="run-001",
                environment_manifest=manifest,
                principal_receipt=principal,
                credential_receipt=credential,
                egress_receipt=blocked_egress,
                installation_binding=binding,
            )

    def test_mismatched_environment_raises(self):
        manifest, principal, credential, egress, binding = self._setup()
        other_manifest = _make_manifest(
            kind=EnvironmentKind.PRODUCTION,
            environment_id="production",
            allowed_egress_hosts=("api.openai.com",),
        )
        # principal belongs to "development", other_manifest is "production"
        with pytest.raises(EnvironmentContractError, match="environment_id"):
            ExecutionIdentityReceiptBuilder.build(
                run_id="run-001",
                environment_manifest=other_manifest,
                principal_receipt=principal,  # environment_id = "development"
                credential_receipt=credential,
                egress_receipt=egress,
                installation_binding=binding,
            )


# ===========================================================================
# Cross-environment denial (dev cannot reach production)
# ===========================================================================

class TestCrossEnvironmentDenial:
    def test_dev_cannot_reach_prod_host(self):
        dev = _make_manifest(kind=EnvironmentKind.DEVELOPMENT, environment_id="development")
        r = EgressPolicyEngine.decide(
            environment_manifest=dev,
            target_host="db.prod.internal.example.com",
            protocol="https",
        )
        assert r.decision == EgressDecision.BLOCK
        assert r.block_reason == EgressBlockReason.PRODUCTION_TARGET_FROM_NONPROD

    def test_test_env_cannot_reach_prod_host(self):
        test_m = _make_manifest(kind=EnvironmentKind.TEST, environment_id="test")
        r = EgressPolicyEngine.decide(
            environment_manifest=test_m,
            target_host="api-prod.example.com",
            protocol="https",
        )
        assert r.decision == EgressDecision.BLOCK

    def test_staging_cannot_reach_prod_host(self):
        staging = _make_manifest(kind=EnvironmentKind.STAGING, environment_id="staging")
        r = EgressPolicyEngine.decide(
            environment_manifest=staging,
            target_host="x.production.example.com",
            protocol="https",
        )
        assert r.decision == EgressDecision.BLOCK


# ===========================================================================
# Deterministic identity and tamper resistance
# ===========================================================================

class TestDeterministicIdentityAndTamperResistance:
    def test_manifest_requires_revision(self):
        with pytest.raises(EnvironmentContractError, match="revision is required"):
            EnvironmentManifestCompiler.compile(
                environment_id="development",
                kind=EnvironmentKind.DEVELOPMENT,
                repo_owner=_OWNER,
                repo_name=_REPO,
                network_policy_descriptor={},
                credential_scope_descriptor={},
            )

    def test_principal_receipt_verifies_and_tamper_fails(self):
        import dataclasses
        receipt = _make_principal_receipt()
        assert PrincipalResolver.verify(receipt)
        assert not PrincipalResolver.verify(
            dataclasses.replace(receipt, principal_id="user-mallory")
        )

    def test_credential_receipt_is_deterministic_and_verifiable(self):
        kwargs = dict(
            environment_id="development",
            credential_id="key-v1",
            owner_id=_OWNER,
            mode=CredentialMode.DIRECT,
            provider="openrouter",
            scopes=["read"],
            executed_as_principal_id="user-alice",
        )
        first = CredentialResolver.resolve(**kwargs)
        second = CredentialResolver.resolve(**kwargs)
        assert first.receipt_id == second.receipt_id
        assert CredentialResolver.verify(first)

    def test_allowlisted_hostname_requires_dns_evidence(self):
        receipt = EgressPolicyEngine.decide(
            environment_manifest=_make_manifest(
                allowed_egress_hosts=("api.openai.com",)
            ),
            target_host="api.openai.com",
            protocol="https",
        )
        assert receipt.decision == EgressDecision.BLOCK
        assert receipt.block_reason == EgressBlockReason.DNS_EVIDENCE_REQUIRED

    def test_egress_receipt_commits_resolved_ip_and_tamper_fails(self):
        import dataclasses
        receipt = EgressPolicyEngine.decide(
            environment_manifest=_make_manifest(
                allowed_egress_hosts=("api.openai.com",)
            ),
            target_host="api.openai.com",
            protocol="https",
            resolved_ip=_PUBLIC_IP,
        )
        assert receipt.resolved_ip == _PUBLIC_IP
        assert EgressPolicyEngine.verify(receipt)
        assert not EgressPolicyEngine.verify(
            dataclasses.replace(receipt, resolved_ip="8.8.8.8")
        )

    def test_binding_requires_verified_revision(self):
        with pytest.raises(EnvironmentContractError, match="required"):
            McpInstallationBinder.bind(
                tool_id="tool",
                server_id="server",
                installation_id="install",
                registry_revision=_SHA,
            )

    def test_binding_is_deterministic_and_verifiable(self):
        kwargs = dict(
            tool_id="tool",
            server_id="server",
            installation_id="install",
            registry_revision=_SHA,
            verified_at_revision=_SHA,
        )
        first = McpInstallationBinder.bind(**kwargs)
        second = McpInstallationBinder.bind(**kwargs)
        assert first.binding_id == second.binding_id
        assert McpInstallationBinder.verify(first)

    def test_builder_rejects_owner_mismatch(self):
        manifest = _make_manifest(allowed_egress_hosts=("api.openai.com",))
        principal = _make_principal_receipt(manifest)
        credential = CredentialResolver.resolve(
            environment_id=manifest.environment_id,
            credential_id="key-v1",
            owner_id="DifferentOwner",
            mode=CredentialMode.DIRECT,
            provider="openrouter",
            scopes=["read"],
            executed_as_principal_id=principal.principal_id,
        )
        egress = EgressPolicyEngine.decide(
            environment_manifest=manifest,
            target_host="api.openai.com",
            protocol="https",
            resolved_ip=_PUBLIC_IP,
        )
        binding = McpInstallationBinder.bind(
            tool_id="tool",
            server_id="server",
            installation_id="install",
            registry_revision=_SHA,
            verified_at_revision=_SHA,
        )
        with pytest.raises(EnvironmentContractError, match="credential owner"):
            ExecutionIdentityReceiptBuilder.build(
                run_id="run-001",
                environment_manifest=manifest,
                principal_receipt=principal,
                credential_receipt=credential,
                egress_receipt=egress,
                installation_binding=binding,
            )

    def test_builder_rejects_run_mismatch(self):
        setup = TestExecutionIdentityReceiptBuilder()
        manifest, principal, credential, egress, binding = setup._setup()
        with pytest.raises(EnvironmentContractError, match="run_id"):
            ExecutionIdentityReceiptBuilder.build(
                run_id="run-002",
                environment_manifest=manifest,
                principal_receipt=principal,
                credential_receipt=credential,
                egress_receipt=egress,
                installation_binding=binding,
            )

    def test_builder_rejects_tampered_component_hash(self):
        import dataclasses
        setup = TestExecutionIdentityReceiptBuilder()
        manifest, principal, credential, egress, binding = setup._setup()
        with pytest.raises(EnvironmentContractError, match="egress_receipt"):
            ExecutionIdentityReceiptBuilder.build(
                run_id="run-001",
                environment_manifest=manifest,
                principal_receipt=principal,
                credential_receipt=credential,
                egress_receipt=dataclasses.replace(egress, receipt_hash="0" * 64),
                installation_binding=binding,
            )

    def test_execution_receipt_is_deterministic_and_verifiable(self):
        setup = TestExecutionIdentityReceiptBuilder()
        manifest, principal, credential, egress, binding = setup._setup()
        first = ExecutionIdentityReceiptBuilder.build(
            run_id="run-001",
            environment_manifest=manifest,
            principal_receipt=principal,
            credential_receipt=credential,
            egress_receipt=egress,
            installation_binding=binding,
        )
        second = ExecutionIdentityReceiptBuilder.build(
            run_id="run-001",
            environment_manifest=manifest,
            principal_receipt=principal,
            credential_receipt=credential,
            egress_receipt=egress,
            installation_binding=binding,
        )
        assert first.receipt_id == second.receipt_id
        assert ExecutionIdentityReceiptBuilder.verify(first)


# ===========================================================================
# No I/O in module
# ===========================================================================

class TestNoIO:
    def test_no_file_io(self):
        import inspect
        import agent_runtime.environment_mcp_execution as mod
        src = inspect.getsource(mod)
        assert "open(" not in src

    def test_no_requests(self):
        import inspect
        import agent_runtime.environment_mcp_execution as mod
        src = inspect.getsource(mod)
        assert "import requests" not in src

    def test_no_clock(self):
        import inspect
        import agent_runtime.environment_mcp_execution as mod
        src = inspect.getsource(mod)
        assert "import time" not in src
        assert "import datetime" not in src

    def test_no_db(self):
        import inspect
        import agent_runtime.environment_mcp_execution as mod
        src = inspect.getsource(mod)
        assert "psycopg2" not in src

    def test_ipaddress_allowed(self):
        """ipaddress is stdlib and used for egress IP policy — it is not a network call."""
        import inspect
        import agent_runtime.environment_mcp_execution as mod
        src = inspect.getsource(mod)
        assert "import ipaddress" in src
