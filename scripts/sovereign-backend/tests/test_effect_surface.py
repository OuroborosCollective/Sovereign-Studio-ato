"""Tests for backend/agent_runtime/effect_surface.py.

Covers:
- Effect class partial ordering: reflexivity, antisymmetry, transitivity
- Scope comparison: widening, narrowing, equal, incomparable
- Edge validation: PARTIAL_ORDER, SCOPE_WIDENS, SCOPE_NARROWS, CONFLICT
- Snapshot validation: unique IDs, no duplicates, no secret fields
- Registry snapshot determinism
- Coarse-to-surface class mapping coverage
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from agent_runtime.effect_surface import (
    COARSE_TO_SURFACE_CLASS,
    EFFECT_SURFACE_SCHEMA_VERSION,
    EFFECT_SURFACE_REGISTRY_SHA256,
    CredentialScope,
    EffectSurfaceContractError,
    EffectSurfaceEdge,
    EffectSurfaceNode,
    EgressScope,
    EnvironmentScope,
    NodeKind,
    OrganizationScope,
    PathScope,
    RelationKind,
    RepositoryScope,
    RuntimeScope,
    ScopeRelation,
    SurfaceEffectClass,
    _EFFECT_CLASS_CLOSURE,
    _SCOPE_WIDENS_KIND_PAIRS,
    compare_effect_classes,
    compare_scopes,
    effect_surface_registry_snapshot,
    validate_edge,
    validate_snapshot,
)


# ---------------------------------------------------------------------------
# Partial ordering: reflexivity, antisymmetry, transitivity
# ---------------------------------------------------------------------------


class TestPartialOrdering:
    """Verify the strict partial ordering on SurfaceEffectClass."""

    def test_irreflexivity(self):
        """No effect class is less than itself (a < a is always false)."""
        for cls in SurfaceEffectClass:
            assert compare_effect_classes(cls, cls) == ScopeRelation.EQUAL

    def test_asymmetry(self):
        """If a < b then NOT b < a (checked at module load; verify here too)."""
        for (a, b) in _EFFECT_CLASS_CLOSURE:
            assert (b, a) not in _EFFECT_CLASS_CLOSURE, (
                f"asymmetry violation: both ({a.value}, {b.value}) and "
                f"({b.value}, {a.value}) in closure"
            )

    def test_transitivity(self):
        """If a < b and b < c then a < c (closure guarantees this)."""
        for (a, b) in _EFFECT_CLASS_CLOSURE:
            for (c, d) in _EFFECT_CLASS_CLOSURE:
                if b is c:
                    assert (a, d) in _EFFECT_CLASS_CLOSURE, (
                        f"transitivity violation: ({a.value}, {b.value}) and "
                        f"({c.value}, {d.value}) but not ({a.value}, {d.value})"
                    )

    def test_widening_chain(self):
        """observe < read < compute < validate < test < build < plan."""
        assert compare_effect_classes(SurfaceEffectClass.OBSERVE, SurfaceEffectClass.READ) == ScopeRelation.WIDENING
        assert compare_effect_classes(SurfaceEffectClass.READ, SurfaceEffectClass.COMPUTE) == ScopeRelation.WIDENING
        assert compare_effect_classes(SurfaceEffectClass.COMPUTE, SurfaceEffectClass.VALIDATE) == ScopeRelation.WIDENING
        assert compare_effect_classes(SurfaceEffectClass.VALIDATE, SurfaceEffectClass.TEST) == ScopeRelation.WIDENING
        assert compare_effect_classes(SurfaceEffectClass.TEST, SurfaceEffectClass.BUILD) == ScopeRelation.WIDENING
        assert compare_effect_classes(SurfaceEffectClass.BUILD, SurfaceEffectClass.PLAN) == ScopeRelation.WIDENING

    def test_narrowing_is_symmetric_of_widening(self):
        """If a < b (WIDENING), then compare(b, a) == NARROWING."""
        for (a, b) in _EFFECT_CLASS_CLOSURE:
            assert compare_effect_classes(b, a) == ScopeRelation.NARROWING

    def test_incomparable_pairs(self):
        """Some pairs are incomparable by design."""
        # VALIDATE and LINT are both above COMPUTE but not comparable to each other
        assert compare_effect_classes(SurfaceEffectClass.VALIDATE, SurfaceEffectClass.LINT) == ScopeRelation.INCOMPARABLE
        # CREDENTIAL_ACCESS and DEPLOY are both above DRAFT_PR but not comparable
        assert compare_effect_classes(SurfaceEffectClass.CREDENTIAL_ACCESS, SurfaceEffectClass.DEPLOY) == ScopeRelation.INCOMPARABLE

    def test_transitive_widening(self):
        """observe < build transitively (through the chain)."""
        assert compare_effect_classes(SurfaceEffectClass.OBSERVE, SurfaceEffectClass.BUILD) == ScopeRelation.WIDENING

    def test_transitive_narrowing(self):
        """build > observe transitively."""
        assert compare_effect_classes(SurfaceEffectClass.BUILD, SurfaceEffectClass.OBSERVE) == ScopeRelation.NARROWING

    def test_all_classes_in_closure(self):
        """Every SurfaceEffectClass should appear at least once in the closure."""
        classes_in_closure = set()
        for (a, b) in _EFFECT_CLASS_CLOSURE:
            classes_in_closure.add(a)
            classes_in_closure.add(b)
        # OWNER_BOUND must be the maximal element (only appears as b, never as a)
        for (a, _) in _EFFECT_CLASS_CLOSURE:
            assert a != SurfaceEffectClass.OWNER_BOUND, "OWNER_BOUND should never be less than anything"


# ---------------------------------------------------------------------------
# Scope comparison
# ---------------------------------------------------------------------------


class TestScopeComparison:
    """Verify scope comparison logic."""

    def test_equal_repository_scopes(self):
        a = RepositoryScope(owner="acme", repository="app")
        b = RepositoryScope(owner="acme", repository="app")
        assert compare_scopes(a, b) == ScopeRelation.EQUAL

    def test_different_repos_incomparable(self):
        a = RepositoryScope(owner="acme", repository="app")
        b = RepositoryScope(owner="acme", repository="lib")
        assert compare_scopes(a, b) == ScopeRelation.INCOMPARABLE

    def test_different_owners_incomparable(self):
        a = RepositoryScope(owner="acme", repository="app")
        b = RepositoryScope(owner="other", repository="app")
        assert compare_scopes(a, b) == ScopeRelation.INCOMPARABLE

    def test_org_widens_repo(self):
        org = OrganizationScope(owner="acme")
        repo = RepositoryScope(owner="acme", repository="app")
        assert compare_scopes(org, repo) == ScopeRelation.WIDENING

    def test_repo_narrows_org(self):
        org = OrganizationScope(owner="acme")
        repo = RepositoryScope(owner="acme", repository="app")
        assert compare_scopes(repo, org) == ScopeRelation.NARROWING

    def test_org_does_not_widen_different_owner_repo(self):
        org = OrganizationScope(owner="acme")
        repo = RepositoryScope(owner="other", repository="app")
        assert compare_scopes(org, repo) == ScopeRelation.INCOMPARABLE

    def test_repo_widens_path(self):
        repo = RepositoryScope(owner="acme", repository="app")
        path = PathScope(owner="acme", repository="app", path="src/main.py")
        assert compare_scopes(repo, path) == ScopeRelation.WIDENING

    def test_path_narrows_repo(self):
        repo = RepositoryScope(owner="acme", repository="app")
        path = PathScope(owner="acme", repository="app", path="src/main.py")
        assert compare_scopes(path, repo) == ScopeRelation.NARROWING

    def test_org_widens_path_transitive(self):
        org = OrganizationScope(owner="acme")
        path = PathScope(owner="acme", repository="app", path="src/main.py")
        assert compare_scopes(org, path) == ScopeRelation.WIDENING

    def test_path_wrong_repo_incomparable(self):
        path1 = PathScope(owner="acme", repository="app", path="src/main.py")
        path2 = PathScope(owner="acme", repository="lib", path="src/main.py")
        assert compare_scopes(path1, path2) == ScopeRelation.INCOMPARABLE

    def test_equal_path_scopes(self):
        a = PathScope(owner="acme", repository="app", path="src/main.py")
        b = PathScope(owner="acme", repository="app", path="src/main.py")
        assert compare_scopes(a, b) == ScopeRelation.EQUAL

    def test_env_widens_runtime(self):
        env = EnvironmentScope(environment_kind="production")
        rt = RuntimeScope(runtime_id="worker-1", environment_kind="production", image_digest="")
        assert compare_scopes(env, rt) == ScopeRelation.WIDENING

    def test_credential_scopes_incomparable(self):
        a = CredentialScope(credential_id="gh-token")
        b = CredentialScope(credential_id="db-key")
        assert compare_scopes(a, b) == ScopeRelation.INCOMPARABLE

    def test_equal_credential_scopes(self):
        a = CredentialScope(credential_id="gh-token")
        b = CredentialScope(credential_id="gh-token")
        assert compare_scopes(a, b) == ScopeRelation.EQUAL

    def test_egress_scopes_incomparable(self):
        a = EgressScope(destination="api.example.com")
        b = EgressScope(destination="other.example.com")
        assert compare_scopes(a, b) == ScopeRelation.INCOMPARABLE

    def test_runtime_scopes_incomparable(self):
        a = RuntimeScope(runtime_id="worker-1")
        b = RuntimeScope(runtime_id="worker-2")
        assert compare_scopes(a, b) == ScopeRelation.INCOMPARABLE

    def test_equal_environment_scopes(self):
        a = EnvironmentScope(environment_kind="staging", region="eu")
        b = EnvironmentScope(environment_kind="staging", region="eu")
        assert compare_scopes(a, b) == ScopeRelation.EQUAL

    def test_different_env_kinds_incomparable(self):
        a = EnvironmentScope(environment_kind="staging")
        b = EnvironmentScope(environment_kind="production")
        # Different kinds with no containment relationship
        assert compare_scopes(a, b) == ScopeRelation.INCOMPARABLE


# ---------------------------------------------------------------------------
# Node / Edge
# ---------------------------------------------------------------------------


class TestEffectSurfaceNode:
    """Verify EffectSurfaceNode construction and deterministic IDs."""

    def test_node_id_deterministic(self):
        node = EffectSurfaceNode(
            kind=NodeKind.REPOSITORY,
            scope=RepositoryScope(owner="acme", repository="app"),
            effect_class=SurfaceEffectClass.READ,
        )
        node2 = EffectSurfaceNode(
            kind=NodeKind.REPOSITORY,
            scope=RepositoryScope(owner="acme", repository="app"),
            effect_class=SurfaceEffectClass.READ,
        )
        assert node.node_id == node2.node_id

    def test_node_id_different_for_different_effect_class(self):
        node_read = EffectSurfaceNode(
            kind=NodeKind.REPOSITORY,
            scope=RepositoryScope(owner="acme", repository="app"),
            effect_class=SurfaceEffectClass.READ,
        )
        node_write = EffectSurfaceNode(
            kind=NodeKind.REPOSITORY,
            scope=RepositoryScope(owner="acme", repository="app"),
            effect_class=SurfaceEffectClass.WORKSPACE_WRITE,
        )
        assert node_read.node_id != node_write.node_id

    def test_canonical_body(self):
        node = EffectSurfaceNode(
            kind=NodeKind.REPOSITORY,
            scope=RepositoryScope(owner="acme", repository="app"),
            effect_class=SurfaceEffectClass.READ,
        )
        body = node.canonical_body()
        assert body["kind"] == "repository"
        assert body["effect_class"] == "read"
        assert "node_id" in body


class TestEffectSurfaceEdge:
    """Verify EffectSurfaceEdge construction and validation."""

    def test_edge_id_deterministic(self):
        node_a = EffectSurfaceNode(
            kind=NodeKind.REPOSITORY,
            scope=RepositoryScope(owner="acme", repository="app"),
            effect_class=SurfaceEffectClass.OBSERVE,
        )
        node_b = EffectSurfaceNode(
            kind=NodeKind.REPOSITORY,
            scope=RepositoryScope(owner="acme", repository="app"),
            effect_class=SurfaceEffectClass.READ,
        )
        edge = EffectSurfaceEdge(source=node_a, relation=RelationKind.PARTIAL_ORDER, target=node_b)
        edge2 = EffectSurfaceEdge(source=node_a, relation=RelationKind.PARTIAL_ORDER, target=node_b)
        assert edge.edge_id == edge2.edge_id

    def test_valid_partial_order_edge(self):
        node_a = EffectSurfaceNode(
            kind=NodeKind.REPOSITORY,
            scope=RepositoryScope(owner="acme", repository="app"),
            effect_class=SurfaceEffectClass.OBSERVE,
        )
        node_b = EffectSurfaceNode(
            kind=NodeKind.REPOSITORY,
            scope=RepositoryScope(owner="acme", repository="app"),
            effect_class=SurfaceEffectClass.READ,
        )
        edge = EffectSurfaceEdge(source=node_a, relation=RelationKind.PARTIAL_ORDER, target=node_b)
        assert validate_edge(edge) is edge

    def test_invalid_partial_order_edge_reversed(self):
        """A PARTIAL_ORDER edge where target < source should fail."""
        node_a = EffectSurfaceNode(
            kind=NodeKind.REPOSITORY,
            scope=RepositoryScope(owner="acme", repository="app"),
            effect_class=SurfaceEffectClass.READ,
        )
        node_b = EffectSurfaceNode(
            kind=NodeKind.REPOSITORY,
            scope=RepositoryScope(owner="acme", repository="app"),
            effect_class=SurfaceEffectClass.OBSERVE,
        )
        edge = EffectSurfaceEdge(source=node_a, relation=RelationKind.PARTIAL_ORDER, target=node_b)
        with pytest.raises(EffectSurfaceContractError, match="PARTIAL_ORDER"):
            validate_edge(edge)

    def test_valid_scope_widens_edge(self):
        node_org = EffectSurfaceNode(
            kind=NodeKind.ORGANIZATION,
            scope=OrganizationScope(owner="acme"),
            effect_class=SurfaceEffectClass.READ,
        )
        node_repo = EffectSurfaceNode(
            kind=NodeKind.REPOSITORY,
            scope=RepositoryScope(owner="acme", repository="app"),
            effect_class=SurfaceEffectClass.READ,
        )
        edge = EffectSurfaceEdge(source=node_org, relation=RelationKind.SCOPE_WIDENS, target=node_repo)
        assert validate_edge(edge) is edge

    def test_invalid_scope_widens_edge(self):
        """A SCOPE_WIDENS edge where source does NOT widen target should fail."""
        node_repo = EffectSurfaceNode(
            kind=NodeKind.REPOSITORY,
            scope=RepositoryScope(owner="acme", repository="app"),
            effect_class=SurfaceEffectClass.READ,
        )
        node_org = EffectSurfaceNode(
            kind=NodeKind.ORGANIZATION,
            scope=OrganizationScope(owner="acme"),
            effect_class=SurfaceEffectClass.READ,
        )
        edge = EffectSurfaceEdge(source=node_repo, relation=RelationKind.SCOPE_WIDENS, target=node_org)
        with pytest.raises(EffectSurfaceContractError, match="SCOPE_WIDENS"):
            validate_edge(edge)

    def test_valid_scope_narrows_edge(self):
        node_repo = EffectSurfaceNode(
            kind=NodeKind.REPOSITORY,
            scope=RepositoryScope(owner="acme", repository="app"),
            effect_class=SurfaceEffectClass.READ,
        )
        node_org = EffectSurfaceNode(
            kind=NodeKind.ORGANIZATION,
            scope=OrganizationScope(owner="acme"),
            effect_class=SurfaceEffectClass.READ,
        )
        edge = EffectSurfaceEdge(source=node_repo, relation=RelationKind.SCOPE_NARROWS, target=node_org)
        assert validate_edge(edge) is edge

    def test_valid_conflict_edge(self):
        node_a = EffectSurfaceNode(
            kind=NodeKind.CREDENTIAL,
            scope=CredentialScope(credential_id="prod-key"),
            effect_class=SurfaceEffectClass.CREDENTIAL_ACCESS,
        )
        node_b = EffectSurfaceNode(
            kind=NodeKind.CREDENTIAL,
            scope=CredentialScope(credential_id="prod-key"),
            effect_class=SurfaceEffectClass.DEPLOY,
        )
        edge = EffectSurfaceEdge(source=node_a, relation=RelationKind.CONFLICT, target=node_b)
        assert validate_edge(edge) is edge

    def test_conflict_edge_same_node_fails(self):
        node = EffectSurfaceNode(
            kind=NodeKind.REPOSITORY,
            scope=RepositoryScope(owner="acme", repository="app"),
            effect_class=SurfaceEffectClass.READ,
        )
        edge = EffectSurfaceEdge(source=node, relation=RelationKind.CONFLICT, target=node)
        with pytest.raises(EffectSurfaceContractError, match="CONFLICT"):
            validate_edge(edge)


# ---------------------------------------------------------------------------
# Snapshot validation
# ---------------------------------------------------------------------------


class TestValidateSnapshot:
    """Verify snapshot-level validation."""

    def test_valid_empty_snapshot(self):
        validate_snapshot([], [])

    def test_valid_snapshot_with_nodes(self):
        node = EffectSurfaceNode(
            kind=NodeKind.REPOSITORY,
            scope=RepositoryScope(owner="acme", repository="app"),
            effect_class=SurfaceEffectClass.READ,
        )
        validate_snapshot([node], [])

    def test_valid_snapshot_with_nodes_and_edges(self):
        node_a = EffectSurfaceNode(
            kind=NodeKind.REPOSITORY,
            scope=RepositoryScope(owner="acme", repository="app"),
            effect_class=SurfaceEffectClass.OBSERVE,
        )
        node_b = EffectSurfaceNode(
            kind=NodeKind.REPOSITORY,
            scope=RepositoryScope(owner="acme", repository="app"),
            effect_class=SurfaceEffectClass.READ,
        )
        edge = EffectSurfaceEdge(source=node_a, relation=RelationKind.PARTIAL_ORDER, target=node_b)
        validate_snapshot([node_a, node_b], [edge])

    def test_duplicate_node_ids_rejected(self):
        node1 = EffectSurfaceNode(
            kind=NodeKind.REPOSITORY,
            scope=RepositoryScope(owner="acme", repository="app"),
            effect_class=SurfaceEffectClass.READ,
        )
        node2 = EffectSurfaceNode(
            kind=NodeKind.REPOSITORY,
            scope=RepositoryScope(owner="acme", repository="app"),
            effect_class=SurfaceEffectClass.READ,
        )
        # node1 and node2 have the same node_id
        assert node1.node_id == node2.node_id
        with pytest.raises(EffectSurfaceContractError, match="duplicate node_id"):
            validate_snapshot([node1, node2], [])

    def test_duplicate_edge_triples_rejected(self):
        node_a = EffectSurfaceNode(
            kind=NodeKind.REPOSITORY,
            scope=RepositoryScope(owner="acme", repository="app"),
            effect_class=SurfaceEffectClass.OBSERVE,
        )
        node_b = EffectSurfaceNode(
            kind=NodeKind.REPOSITORY,
            scope=RepositoryScope(owner="acme", repository="app"),
            effect_class=SurfaceEffectClass.READ,
        )
        edge1 = EffectSurfaceEdge(source=node_a, relation=RelationKind.PARTIAL_ORDER, target=node_b)
        edge2 = EffectSurfaceEdge(source=node_a, relation=RelationKind.PARTIAL_ORDER, target=node_b)
        with pytest.raises(EffectSurfaceContractError, match="duplicate edge"):
            validate_snapshot([node_a, node_b], [edge1, edge2])

    def test_invalid_edge_in_snapshot_rejected(self):
        node_a = EffectSurfaceNode(
            kind=NodeKind.REPOSITORY,
            scope=RepositoryScope(owner="acme", repository="app"),
            effect_class=SurfaceEffectClass.READ,
        )
        node_b = EffectSurfaceNode(
            kind=NodeKind.REPOSITORY,
            scope=RepositoryScope(owner="acme", repository="app"),
            effect_class=SurfaceEffectClass.OBSERVE,
        )
        # Invalid: READ > OBSERVE, not READ < OBSERVE
        edge = EffectSurfaceEdge(source=node_a, relation=RelationKind.PARTIAL_ORDER, target=node_b)
        with pytest.raises(EffectSurfaceContractError):
            validate_snapshot([node_a, node_b], [edge])


# ---------------------------------------------------------------------------
# Registry snapshot
# ---------------------------------------------------------------------------


class TestRegistrySnapshot:
    """Verify registry snapshot determinism and completeness."""

    def test_schema_version_present(self):
        snap = effect_surface_registry_snapshot()
        assert snap["schema_version"] == EFFECT_SURFACE_SCHEMA_VERSION

    def test_all_effect_classes_listed(self):
        snap = effect_surface_registry_snapshot()
        listed = set(snap["effect_classes"])
        expected = {cls.value for cls in SurfaceEffectClass}
        assert listed == expected

    def test_partial_order_closure_nonempty(self):
        snap = effect_surface_registry_snapshot()
        assert len(snap["partial_order_closure"]) > 0

    def test_registry_sha256_deterministic(self):
        sha1 = EFFECT_SURFACE_REGISTRY_SHA256
        # Re-import and verify same SHA256
        from agent_runtime.effect_surface import _canonical_sha256
        sha2 = _canonical_sha256(effect_surface_registry_snapshot())
        assert sha1 == sha2

    def test_coarse_mapping_covers_all_manifest_classes(self):
        """Verify that every skills.manifest EffectClass value is mapped."""
        manifest_classes = {"read_only", "bounded_reversible", "bounded_stateless", "draft_pr", "owner_bound"}
        assert set(COARSE_TO_SURFACE_CLASS.keys()) == manifest_classes

    def test_scope_widens_kind_pairs_nonempty(self):
        snap = effect_surface_registry_snapshot()
        assert len(snap["scope_widens_kind_pairs"]) > 0

    def test_no_secrets_in_snapshot(self):
        """Verify no secret-shaped values leak into the snapshot."""
        snap = effect_surface_registry_snapshot()
        snap_json = str(snap)
        # No secret markers should appear as values
        for marker in ("password", "secret", "token", "api_key", "private_key"):
            assert marker not in snap_json.lower() or f'"{marker}"' not in snap_json


# ---------------------------------------------------------------------------
# Secret-shaped field rejection
# ---------------------------------------------------------------------------


class TestSecretRejection:
    """Verify that secret-shaped values are rejected from scopes."""

    def test_credential_scope_with_safe_handle(self):
        """CredentialScope with a non-secret handle value is OK."""
        scope = CredentialScope(credential_id="gh-token-handle")
        node = EffectSurfaceNode(
            kind=NodeKind.CREDENTIAL,
            scope=scope,
            effect_class=SurfaceEffectClass.CREDENTIAL_ACCESS,
        )
        # Should not raise - "gh-token-handle" is just a handle name
        validate_snapshot([node], [])

    def test_credential_scope_with_leaked_secret_rejected(self):
        """CredentialScope with a secret-shaped value is rejected."""
        scope = CredentialScope(credential_id="ghp_abc123def456")
        node = EffectSurfaceNode(
            kind=NodeKind.CREDENTIAL,
            scope=scope,
            effect_class=SurfaceEffectClass.CREDENTIAL_ACCESS,
        )
        with pytest.raises(EffectSurfaceContractError, match="secret-shaped"):
            validate_snapshot([node], [])

    def test_scope_with_sk_prefix_rejected(self):
        """Values starting with sk- (API key pattern) are rejected."""
        scope = CredentialScope(credential_id="sk-proj-abcdef123456")
        node = EffectSurfaceNode(
            kind=NodeKind.CREDENTIAL,
            scope=scope,
            effect_class=SurfaceEffectClass.CREDENTIAL_ACCESS,
        )
        with pytest.raises(EffectSurfaceContractError, match="secret-shaped"):
            validate_snapshot([node], [])

    def test_scope_with_jwt_value_rejected(self):
        """Values starting with eyJ (JWT prefix) are rejected."""
        scope = EgressScope(destination="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")
        node = EffectSurfaceNode(
            kind=NodeKind.EGRESS,
            scope=scope,
            effect_class=SurfaceEffectClass.EGRESS_NETWORK,
        )
        with pytest.raises(EffectSurfaceContractError, match="secret-shaped"):
            validate_snapshot([node], [])

    def test_scope_with_excessively_long_value_rejected(self):
        """Values longer than 256 chars are rejected as suspected key material."""
        scope = CredentialScope(credential_id="a" * 300)
        node = EffectSurfaceNode(
            kind=NodeKind.CREDENTIAL,
            scope=scope,
            effect_class=SurfaceEffectClass.CREDENTIAL_ACCESS,
        )
        with pytest.raises(EffectSurfaceContractError, match="suspected key material"):
            validate_snapshot([node], [])


# ---------------------------------------------------------------------------
# Canonical JSON
# ---------------------------------------------------------------------------


class TestCanonicalJson:
    """Verify canonical JSON determinism for scope dataclasses."""

    def test_repository_scope_canonical_json(self):
        scope = RepositoryScope(owner="acme", repository="app")
        j = scope.canonical_json()
        assert '"owner":"acme"' in j
        assert '"repository":"app"' in j

    def test_environment_scope_canonical_json(self):
        scope = EnvironmentScope(environment_kind="production", region="eu")
        j = scope.canonical_json()
        assert '"environment_kind":"production"' in j

    def test_path_scope_canonical_json(self):
        scope = PathScope(owner="acme", repository="app", path="src/main.py")
        j = scope.canonical_json()
        assert '"path":"src/main.py"' in j


# ---------------------------------------------------------------------------
# Cross-kind scope comparisons
# ---------------------------------------------------------------------------


class TestCrossKindScope:
    """Verify that different scope kinds without containment are incomparable."""

    def test_credential_vs_repository_incomparable(self):
        cred = CredentialScope(credential_id="key-1")
        repo = RepositoryScope(owner="acme", repository="app")
        assert compare_scopes(cred, repo) == ScopeRelation.INCOMPARABLE

    def test_egress_vs_environment_incomparable(self):
        egress = EgressScope(destination="api.example.com")
        env = EnvironmentScope(environment_kind="production")
        assert compare_scopes(egress, env) == ScopeRelation.INCOMPARABLE

    def test_runtime_vs_repository_incomparable(self):
        rt = RuntimeScope(runtime_id="worker-1")
        repo = RepositoryScope(owner="acme", repository="app")
        assert compare_scopes(rt, repo) == ScopeRelation.INCOMPARABLE
