"""Tests for Effect Surface model (SESD 1/5).

These tests verify:
- Node and edge validation
- Canonical SHA determinism
- Effect class partial ordering
- Scope relations
- Environment risk ordering
- Diff computation
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from backend.agent_runtime.effect_surface import (
    # Core classes
    EffectSurfaceNode,
    EffectSurfaceEdge,
    EffectSurfaceSnapshot,
    # Enums
    NodeKind,
    RelationKind,
    EffectClass,
    EffectRelation,
    ScopeRelation,
    EnvironmentKind,
    EnvironmentRelation,
    DiffVerdict,
    # Scopes
    RepositoryScope,
    OrganizationScope,
    PathScope,
    CredentialScope,
    EnvironmentScope,
    EgressScope,
    DatabaseScope,
    RuntimeScope,
    # Functions
    validate_node,
    validate_edge,
    validate_snapshot,
    compare_effect_classes,
    compare_scopes,
    compare_environments,
    compute_diff,
    EffectSurfaceDiff,
    ContractError,
    SCHEMA_VERSION,
)


# ---------------------------------------------------------------------------
# Test Node Validation
# ---------------------------------------------------------------------------

class TestNodeValidation:
    """Test node ID and SHA validation."""

    def test_valid_node(self):
        """Valid node passes validation."""
        node = EffectSurfaceNode(
            node_id="agent:repository-specialist",
            kind=NodeKind.AGENT,
            contract_sha256="a" * 64,
        )
        validate_node(node)  # Should not raise

    def test_invalid_node_id(self):
        """Invalid node ID raises ContractError."""
        node = EffectSurfaceNode(
            node_id="invalid node id!",
            kind=NodeKind.AGENT,
            contract_sha256="a" * 64,
        )
        with pytest.raises(ContractError, match="Invalid node_id"):
            validate_node(node)

    def test_invalid_contract_sha(self):
        """Invalid contract SHA raises ContractError."""
        node = EffectSurfaceNode(
            node_id="agent:test",
            kind=NodeKind.AGENT,
            contract_sha256="not-a-sha256",
        )
        with pytest.raises(ContractError, match="Invalid contract_sha256"):
            validate_node(node)


# ---------------------------------------------------------------------------
# Test Canonical SHA Determinism
# ---------------------------------------------------------------------------

class TestCanonicalSHA:
    """Test deterministic SHA computation."""

    def test_identical_snapshot_same_sha(self):
        """Identical snapshots produce identical SHA."""
        nodes = (
            EffectSurfaceNode(
                node_id="agent:test",
                kind=NodeKind.AGENT,
                contract_sha256="a" * 64,
            ),
        )
        
        snapshot1 = EffectSurfaceSnapshot(
            schema_version=SCHEMA_VERSION,
            repository="test/repo",
            repository_revision="abc123",
            policy_sha256="b" * 64,
            source_contract_hashes=("c" * 64,),
            nodes=nodes,
            edges=(),
            incomplete_sources=(),
        )
        
        snapshot2 = EffectSurfaceSnapshot(
            schema_version=SCHEMA_VERSION,
            repository="test/repo",
            repository_revision="abc123",
            policy_sha256="b" * 64,
            source_contract_hashes=("c" * 64,),
            nodes=nodes,
            edges=(),
            incomplete_sources=(),
        )
        
        assert snapshot1.surface_sha256 == snapshot2.surface_sha256

    def test_different_node_changes_sha(self):
        """Different nodes produce different SHA."""
        nodes1 = (
            EffectSurfaceNode(
                node_id="agent:test1",
                kind=NodeKind.AGENT,
                contract_sha256="a" * 64,
            ),
        )
        nodes2 = (
            EffectSurfaceNode(
                node_id="agent:test2",
                kind=NodeKind.AGENT,
                contract_sha256="a" * 64,
            ),
        )
        
        snapshot1 = EffectSurfaceSnapshot(
            schema_version=SCHEMA_VERSION,
            repository="test/repo",
            repository_revision="abc123",
            policy_sha256="b" * 64,
            source_contract_hashes=("c" * 64,),
            nodes=nodes1,
            edges=(),
            incomplete_sources=(),
        )
        
        snapshot2 = EffectSurfaceSnapshot(
            schema_version=SCHEMA_VERSION,
            repository="test/repo",
            repository_revision="abc123",
            policy_sha256="b" * 64,
            source_contract_hashes=("c" * 64,),
            nodes=nodes2,
            edges=(),
            incomplete_sources=(),
        )
        
        assert snapshot1.surface_sha256 != snapshot2.surface_sha256

    def test_node_order_does_not_affect_sha(self):
        """Node ordering does not affect SHA."""
        nodes1 = (
            EffectSurfaceNode(
                node_id="agent:alpha",
                kind=NodeKind.AGENT,
                contract_sha256="a" * 64,
            ),
            EffectSurfaceNode(
                node_id="agent:beta",
                kind=NodeKind.AGENT,
                contract_sha256="b" * 64,
            ),
        )
        nodes2 = (
            EffectSurfaceNode(
                node_id="agent:beta",
                kind=NodeKind.AGENT,
                contract_sha256="b" * 64,
            ),
            EffectSurfaceNode(
                node_id="agent:alpha",
                kind=NodeKind.AGENT,
                contract_sha256="a" * 64,
            ),
        )
        
        snapshot1 = EffectSurfaceSnapshot(
            schema_version=SCHEMA_VERSION,
            repository="test/repo",
            repository_revision="abc123",
            policy_sha256="c" * 64,
            source_contract_hashes=("d" * 64,),
            nodes=nodes1,
            edges=(),
            incomplete_sources=(),
        )
        
        snapshot2 = EffectSurfaceSnapshot(
            schema_version=SCHEMA_VERSION,
            repository="test/repo",
            repository_revision="abc123",
            policy_sha256="c" * 64,
            source_contract_hashes=("d" * 64,),
            nodes=nodes2,
            edges=(),
            incomplete_sources=(),
        )
        
        assert snapshot1.surface_sha256 == snapshot2.surface_sha256


# ---------------------------------------------------------------------------
# Test Effect Class Partial Ordering
# ---------------------------------------------------------------------------

class TestEffectClassOrdering:
    """Test effect class partial ordering - NOT global ranking."""

    def test_read_to_workspace_write_is_widening(self):
        """READ → WORKSPACE_WRITE is widening (more power)."""
        result = compare_effect_classes(
            EffectClass.READ,
            EffectClass.WORKSPACE_WRITE
        )
        # READ → WORKSPACE_WRITE is expanding effect capability = widening = GREATER
        assert result == EffectRelation.GREATER

    def test_workspace_read_to_workspace_write_is_widening(self):
        """WORKSPACE_READ → WORKSPACE_WRITE is widening."""
        result = compare_effect_classes(
            EffectClass.WORKSPACE_READ,
            EffectClass.WORKSPACE_WRITE
        )
        assert result == EffectRelation.GREATER

    def test_database_read_to_database_write_is_widening(self):
        """DATABASE_READ → DATABASE_WRITE is widening."""
        result = compare_effect_classes(
            EffectClass.DATABASE_READ,
            EffectClass.DATABASE_WRITE
        )
        assert result == EffectRelation.GREATER

    def test_external_write_to_deployment_is_widening(self):
        """EXTERNAL_WRITE → DEPLOYMENT is widening."""
        result = compare_effect_classes(
            EffectClass.EXTERNAL_WRITE,
            EffectClass.DEPLOYMENT
        )
        assert result == EffectRelation.GREATER

    def test_equal_classes(self):
        """Same class returns EQUAL."""
        result = compare_effect_classes(
            EffectClass.READ,
            EffectClass.READ
        )
        assert result == EffectRelation.EQUAL

    def test_widening_direction(self):
        """Widening is detected correctly."""
        result = compare_effect_classes(
            EffectClass.WORKSPACE_WRITE,
            EffectClass.DEPLOYMENT
        )
        # WORKSPACE_WRITE < DEPLOYMENT in the ordering, so going from WORKSPACE_WRITE to DEPLOYMENT
        # is moving to a higher/wider effect class = widening = GREATER
        assert result == EffectRelation.GREATER

    def test_incomparable_without_explicit_relation(self):
        """Incomparable classes return INCOMPARABLE (fail closed)."""
        # DATABASE_WRITE vs EXTERNAL_WRITE - no explicit relation
        result = compare_effect_classes(
            EffectClass.DATABASE_WRITE,
            EffectClass.EXTERNAL_WRITE
        )
        assert result == EffectRelation.INCOMPARABLE

    def test_incomparable_runtime_vs_external(self):
        """RUNTIME_WRITE vs EXTERNAL_WRITE are incomparable."""
        result = compare_effect_classes(
            EffectClass.RUNTIME_WRITE,
            EffectClass.EXTERNAL_WRITE
        )
        assert result == EffectRelation.INCOMPARABLE


# ---------------------------------------------------------------------------
# Test Scope Relations
# ---------------------------------------------------------------------------

class TestScopeRelations:
    """Test typed scope comparison - not string prefix."""

    def test_same_repository_scope(self):
        """Identical repository scopes are SAME."""
        scope1 = RepositoryScope(owner="org", repo="repo")
        scope2 = RepositoryScope(owner="org", repo="repo")
        result = compare_scopes(scope1, scope2)
        assert result == ScopeRelation.SAME

    def test_disjoint_repository_scopes(self):
        """Different repos are DISJOINT."""
        scope1 = RepositoryScope(owner="org1", repo="repo")
        scope2 = RepositoryScope(owner="org2", repo="repo")
        result = compare_scopes(scope1, scope2)
        assert result == ScopeRelation.DISJOINT

    def test_path_scope_narrowing(self):
        """Subset paths are NARROWER."""
        scope1 = PathScope(repository="org/repo", paths=("src/",))
        scope2 = PathScope(repository="org/repo", paths=("src/", "tests/"))
        result = compare_scopes(scope1, scope2)
        assert result == ScopeRelation.NARROWER

    def test_path_scope_wider(self):
        """Superset paths are WIDER."""
        scope1 = PathScope(repository="org/repo", paths=("src/", "tests/"))
        scope2 = PathScope(repository="org/repo", paths=("src/",))
        result = compare_scopes(scope1, scope2)
        assert result == ScopeRelation.WIDER

    def test_different_scope_types_incomparable(self):
        """Different scope types are OVERLAPPING_INCOMPARABLE."""
        scope1 = RepositoryScope(owner="org", repo="repo")
        scope2 = OrganizationScope(organization="org")
        result = compare_scopes(scope1, scope2)
        assert result == ScopeRelation.OVERLAPPING_INCOMPARABLE

    def test_credential_scope_operations(self):
        """Credential scope with different operations."""
        scope1 = CredentialScope(
            provider="github",
            resource="repo",
            operations=("read",)
        )
        scope2 = CredentialScope(
            provider="github",
            resource="repo",
            operations=("read", "write")
        )
        result = compare_scopes(scope1, scope2)
        assert result == ScopeRelation.NARROWER


# ---------------------------------------------------------------------------
# Test Environment Risk Relations
# ---------------------------------------------------------------------------

class TestEnvironmentRelations:
    """Test environment risk ordering - explicit, not lexical."""

    def test_ephemeral_less_risky_than_test(self):
        """EPHEMERAL < TEST."""
        result = compare_environments(
            EnvironmentKind.EPHEMERAL,
            EnvironmentKind.TEST
        )
        assert result == EnvironmentRelation.LESS_RISKY

    def test_test_less_risky_than_staging(self):
        """TEST < STAGING."""
        result = compare_environments(
            EnvironmentKind.TEST,
            EnvironmentKind.STAGING
        )
        assert result == EnvironmentRelation.LESS_RISKY

    def test_staging_less_risky_than_production(self):
        """STAGING < PRODUCTION."""
        result = compare_environments(
            EnvironmentKind.STAGING,
            EnvironmentKind.PRODUCTION
        )
        assert result == EnvironmentRelation.LESS_RISKY

    def test_production_more_risky_than_development(self):
        """PRODUCTION > DEVELOPMENT."""
        result = compare_environments(
            EnvironmentKind.PRODUCTION,
            EnvironmentKind.DEVELOPMENT
        )
        assert result == EnvironmentRelation.MORE_RISKY

    def test_same_environment_equal(self):
        """Same environment is EQUAL."""
        result = compare_environments(
            EnvironmentKind.STAGING,
            EnvironmentKind.STAGING
        )
        assert result == EnvironmentRelation.EQUAL


# ---------------------------------------------------------------------------
# Test Diff Computation
# ---------------------------------------------------------------------------

class TestDiffComputation:
    """Test effect surface diff computation."""

    def test_no_change_no_expansion(self):
        """No changes results in NO_SECURITY_EXPANSION."""
        nodes = (
            EffectSurfaceNode(
                node_id="agent:test",
                kind=NodeKind.AGENT,
                contract_sha256="a" * 64,
            ),
            EffectSurfaceNode(
                node_id="tool:bash",
                kind=NodeKind.TOOL,
                contract_sha256="b" * 64,
            ),
        )
        edge = EffectSurfaceEdge(
            source_id="agent:test",
            target_id="tool:bash",
            effect_class=EffectClass.READ,
            relation_kind=RelationKind.MAY_INVOKE,
            condition_sha256="c" * 64,
        )
        
        snapshot = EffectSurfaceSnapshot(
            schema_version=SCHEMA_VERSION,
            repository="test/repo",
            repository_revision="abc123",
            policy_sha256="d" * 64,
            source_contract_hashes=("e" * 64,),
            nodes=nodes,
            edges=(edge,),
            incomplete_sources=(),
        )
        
        diff = compute_diff(snapshot, snapshot)
        assert diff.verdict == DiffVerdict.NO_SECURITY_EXPANSION

    def test_new_edge_expansion_review(self):
        """New edge triggers EXPANSION_REVIEW_REQUIRED."""
        nodes1 = (
            EffectSurfaceNode(
                node_id="agent:test",
                kind=NodeKind.AGENT,
                contract_sha256="a" * 64,
            ),
            EffectSurfaceNode(
                node_id="tool:bash",
                kind=NodeKind.TOOL,
                contract_sha256="b" * 64,
            ),
            EffectSurfaceNode(
                node_id="tool:github",
                kind=NodeKind.TOOL,
                contract_sha256="f" * 64,
            ),
        )
        # Before has only READ access to bash
        edge1 = EffectSurfaceEdge(
            source_id="agent:test",
            target_id="tool:bash",
            effect_class=EffectClass.READ,
            relation_kind=RelationKind.MAY_INVOKE,
            condition_sha256="c" * 64,
        )
        
        before = EffectSurfaceSnapshot(
            schema_version=SCHEMA_VERSION,
            repository="test/repo",
            repository_revision="abc123",
            policy_sha256="d" * 64,
            source_contract_hashes=("e" * 64,),
            nodes=nodes1,
            edges=(edge1,),
            incomplete_sources=(),
        )
        
        # After adds a NEW edge to github with WRITE - this is expansion
        edge2 = EffectSurfaceEdge(
            source_id="agent:test",
            target_id="tool:github",  # Different target - NEW edge
            effect_class=EffectClass.WORKSPACE_WRITE,
            relation_kind=RelationKind.MAY_INVOKE,
            condition_sha256="c" * 64,
        )
        
        after = EffectSurfaceSnapshot(
            schema_version=SCHEMA_VERSION,
            repository="test/repo",
            repository_revision="abc123",
            policy_sha256="d" * 64,
            source_contract_hashes=("e" * 64,),
            nodes=nodes1,
            edges=(edge1, edge2),
            incomplete_sources=(),
        )
        
        diff = compute_diff(before, after)
        assert diff.verdict == DiffVerdict.EXPANSION_REVIEW_REQUIRED
        assert len(diff.new_edges) == 1


# ---------------------------------------------------------------------------
# Test Fail Closed
# ---------------------------------------------------------------------------

class TestFailClosed:
    """Test fail-closed behavior."""

    def test_duplicate_node_ids_rejected(self):
        """Duplicate node IDs raise ContractError."""
        nodes = (
            EffectSurfaceNode(
                node_id="agent:test",
                kind=NodeKind.AGENT,
                contract_sha256="a" * 64,
            ),
            EffectSurfaceNode(
                node_id="agent:test",  # Duplicate
                kind=NodeKind.TOOL,
                contract_sha256="b" * 64,
            ),
        )
        
        snapshot = EffectSurfaceSnapshot(
            schema_version=SCHEMA_VERSION,
            repository="test/repo",
            repository_revision="abc123",
            policy_sha256="c" * 64,
            source_contract_hashes=("d" * 64,),
            nodes=nodes,
            edges=(),
            incomplete_sources=(),
        )
        
        with pytest.raises(ContractError, match="Duplicate"):
            validate_snapshot(snapshot)

    def test_edge_to_unknown_node_rejected(self):
        """Edge to unknown node raises ContractError."""
        nodes = (
            EffectSurfaceNode(
                node_id="agent:test",
                kind=NodeKind.AGENT,
                contract_sha256="a" * 64,
            ),
        )
        edge = EffectSurfaceEdge(
            source_id="agent:test",
            target_id="tool:nonexistent",  # Unknown
            effect_class=EffectClass.READ,
            relation_kind=RelationKind.MAY_INVOKE,
            condition_sha256="b" * 64,
        )
        
        snapshot = EffectSurfaceSnapshot(
            schema_version=SCHEMA_VERSION,
            repository="test/repo",
            repository_revision="abc123",
            policy_sha256="c" * 64,
            source_contract_hashes=("d" * 64,),
            nodes=nodes,
            edges=(edge,),
            incomplete_sources=(),
        )
        
        with pytest.raises(ContractError, match="unknown target"):
            validate_snapshot(snapshot)

    def test_invalid_schema_version_rejected(self):
        """Invalid schema version raises ContractError."""
        nodes = (
            EffectSurfaceNode(
                node_id="agent:test",
                kind=NodeKind.AGENT,
                contract_sha256="a" * 64,
            ),
        )
        
        snapshot = EffectSurfaceSnapshot(
            schema_version="invalid-schema",
            repository="test/repo",
            repository_revision="abc123",
            policy_sha256="b" * 64,
            source_contract_hashes=("c" * 64,),
            nodes=nodes,
            edges=(),
            incomplete_sources=(),
        )
        
        with pytest.raises(ContractError, match="Invalid schema version"):
            validate_snapshot(snapshot)


# ---------------------------------------------------------------------------
# Test Schema Version
# ---------------------------------------------------------------------------

def test_schema_version():
    """Verify schema version is set correctly."""
    assert SCHEMA_VERSION == "sovereign.effect-surface.v1"


def test_node_kind_enum():
    """Verify all node kinds are defined."""
    assert NodeKind.AGENT.value == "agent"
    assert NodeKind.CAPABILITY.value == "capability"
    assert NodeKind.TOOL.value == "tool"


def test_effect_class_enum():
    """Verify effect classes are defined."""
    assert EffectClass.READ.value == "read"
    assert EffectClass.DEPLOYMENT.value == "deployment"


def test_relation_kind_enum():
    """Verify relation kinds are defined."""
    assert RelationKind.MAY_INVOKE.value == "may_invoke"
    assert RelationKind.AUTHORIZED_BY.value == "authorized_by"
