"""Pure, deterministic Effect Surface contracts for Sovereign Effect-Surface Diff Gate (SESD).

This module defines the canonical Effect-Surface model including nodes, edges, snapshots,
partial ordering of effect classes, and scope relations. It performs no network, database,
filesystem, clock or random access.

Design constraints:
- No network, database, filesystem, clock or random access in this module.
- Partial ordering: explicit relations only, no global ranking.
- Typified scopes: no raw string prefix comparisons.
- Deterministic SHA: canonical JSON, no float/NaN/timestamp in semantic identity.
- Fail closed: unknown nodes, edges, or relations are rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from enum import Enum
from typing import Any, Final, Literal, Mapping, Tuple, Union

# Schema version
SCHEMA_VERSION: Final[str] = "sovereign.effect-surface.v1"

# Validation patterns
_SHA256: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_.:/@-]{1,119}$")


# ---------------------------------------------------------------------------
# Node Kinds
# ---------------------------------------------------------------------------

class NodeKind(str, Enum):
    """Kinds of nodes in the effect surface graph."""
    AGENT = "agent"
    PRINCIPAL = "principal"
    CAPABILITY = "capability"
    TOOL = "tool"
    PERMISSION_CLASS = "permission_class"
    CREDENTIAL_SCOPE = "credential_scope"
    ENVIRONMENT = "environment"
    EGRESS_TARGET = "egress_target"
    MUTATION_FAMILY = "mutation_family"
    TARGET_SCOPE = "target_scope"


# ---------------------------------------------------------------------------
# Edge Relation Kinds
# ---------------------------------------------------------------------------

class RelationKind(str, Enum):
    """Kinds of relations between effect surface nodes."""
    MAY_INVOKE = "may_invoke"
    AUTHORIZED_BY = "authorized_by"
    USES_CREDENTIAL = "uses_credential"
    RUNS_IN = "runs_in"
    MAY_EGRESS_TO = "may_egress_to"
    MAY_MUTATE = "may_mutate"
    TARGETS = "targets"


# ---------------------------------------------------------------------------
# Effect Class (partial ordering)
# ---------------------------------------------------------------------------

class EffectClass(str, Enum):
    """Effect classes with explicit partial ordering semantics.

    IMPORTANT: These are NOT globally ranked. Relations must be defined
    explicitly via EffectRelationPolicy. Unknown relations default to
    INCOMPARABLE or UNKNOWN (fail closed).
    """
    READ = "read"
    WORKSPACE_WRITE = "workspace_write"
    WORKSPACE_READ = "workspace_read"
    DATABASE_WRITE = "database_write"
    DATABASE_READ = "database_read"
    RUNTIME_WRITE = "runtime_write"
    RUNTIME_READ = "runtime_read"
    EXTERNAL_WRITE = "external_write"
    EXTERNAL_READ = "external_read"
    DEPLOYMENT = "deployment"


class EffectRelation(str, Enum):
    """Result of comparing two effect classes."""
    LESS = "less"           # before < after (narrowing)
    EQUAL = "equal"         # no change
    GREATER = "greater"     # before > after (widening)
    INCOMPARABLE = "incomparable"  # no explicit relation defined
    UNKNOWN = "unknown"     # unknown effect class


# ---------------------------------------------------------------------------
# Scope Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RepositoryScope:
    """Repository scope with owner/repo."""
    owner: str
    repo: str

    def canonical_json(self) -> str:
        return json.dumps({"owner": self.owner, "repo": self.repo}, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class OrganizationScope:
    """Organization wildcard scope."""
    organization: str

    def canonical_json(self) -> str:
        return json.dumps({"organization": self.organization}, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class PathScope:
    """Path-specific scope."""
    repository: str
    paths: Tuple[str, ...]

    def canonical_json(self) -> str:
        return json.dumps({"repository": self.repository, "paths": list(self.paths)}, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class CredentialScope:
    """Credential scope with provider/resource/operations."""
    provider: str
    resource: str
    operations: Tuple[str, ...]

    def canonical_json(self) -> str:
        return json.dumps({
            "provider": self.provider,
            "resource": self.resource,
            "operations": list(self.operations)
        }, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class EnvironmentScope:
    """Environment scope with type and kind."""
    environment_id: str
    environment_kind: str  # e.g., "production", "staging", "test", "development"

    def canonical_json(self) -> str:
        return json.dumps({
            "environment_id": self.environment_id,
            "environment_kind": self.environment_kind
        }, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class EgressScope:
    """Network egress scope."""
    protocol: str
    host: str
    port: int

    def canonical_json(self) -> str:
        return json.dumps({
            "protocol": self.protocol,
            "host": self.host,
            "port": self.port
        }, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class DatabaseScope:
    """Database scope."""
    database: str
    schema: str
    tables: Tuple[str, ...]

    def canonical_json(self) -> str:
        return json.dumps({
            "database": self.database,
            "schema": self.schema,
            "tables": list(self.tables)
        }, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class RuntimeScope:
    """Runtime/container scope."""
    service: str
    container: str

    def canonical_json(self) -> str:
        return json.dumps({
            "service": self.service,
            "container": self.container
        }, separators=(",", ":"))


# Union of all scope types
Scope = Union[
    RepositoryScope,
    OrganizationScope,
    PathScope,
    CredentialScope,
    EnvironmentScope,
    EgressScope,
    DatabaseScope,
    RuntimeScope,
]


class ScopeRelation(str, Enum):
    """Result of comparing two scopes."""
    SAME = "same"
    NARROWER = "narrower"
    WIDER = "wider"
    DISJOINT = "disjoint"
    OVERLAPPING_INCOMPARABLE = "overlapping_incomparable"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Environment Risk Relation (explicit ordering)
# ---------------------------------------------------------------------------

class EnvironmentKind(str, Enum):
    """Environment risk kinds - explicit ordering defined separately."""
    EPHEMERAL = "ephemeral"
    TEST = "test"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class EnvironmentRelation(str, Enum):
    """Result of comparing two environments."""
    LESS_RISKY = "less_risky"
    EQUAL = "equal"
    MORE_RISKY = "more_risky"
    DISJOINT = "disjoint"  # e.g., comparing completely different env types
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Core Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class EffectSurfaceNode:
    """A single node in the effect surface graph."""
    node_id: str
    kind: NodeKind
    contract_sha256: str
    metadata: Mapping[str, str] = field(default_factory=dict)

    def canonical_json(self) -> str:
        # Sort keys for deterministic output
        meta = dict(sorted(self.metadata.items())) if self.metadata else {}
        return json.dumps({
            "node_id": self.node_id,
            "kind": self.kind.value,
            "contract_sha256": self.contract_sha256,
            "metadata": meta,
        }, separators=(",", ":"), sort_keys=False)


@dataclass(frozen=True, slots=True)
class EffectSurfaceEdge:
    """A directed edge between two nodes in the effect surface graph."""
    source_id: str
    target_id: str
    effect_class: EffectClass
    relation_kind: RelationKind
    condition_sha256: str
    metadata: Mapping[str, str] = field(default_factory=dict)

    def canonical_json(self) -> str:
        meta = dict(sorted(self.metadata.items())) if self.metadata else {}
        return json.dumps({
            "source_id": self.source_id,
            "target_id": self.target_id,
            "effect_class": self.effect_class.value,
            "relation_kind": self.relation_kind.value,
            "condition_sha256": self.condition_sha256,
            "metadata": meta,
        }, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class EffectSurfaceSnapshot:
    """Complete effect surface snapshot at a specific revision."""
    schema_version: str
    repository: str
    repository_revision: str
    policy_sha256: str
    source_contract_hashes: Tuple[str, ...]
    nodes: Tuple[EffectSurfaceNode, ...]
    edges: Tuple[EffectSurfaceEdge, ...]
    incomplete_sources: Tuple[str, ...]
    surface_sha256: str = ""

    def __post_init__(self):
        # Compute surface_sha256 if not provided
        if not self.surface_sha256:
            object.__setattr__(self, 'surface_sha256', self._compute_sha256())

    def _compute_sha256(self) -> str:
        """Compute deterministic SHA-256 of the surface."""
        # Canonicalize nodes and edges
        nodes_json = json.dumps(
            [n.canonical_json() for n in sorted(self.nodes, key=lambda n: n.node_id)],
            separators=(",", ":")
        )
        edges_json = json.dumps(
            [e.canonical_json() for e in sorted(self.edges, key=lambda e: (e.source_id, e.target_id))],
            separators=(",", ":")
        )
        
        canonical = json.dumps({
            "schema_version": self.schema_version,
            "repository": self.repository,
            "repository_revision": self.repository_revision,
            "policy_sha256": self.policy_sha256,
            "source_contract_hashes": list(self.source_contract_hashes),
            "nodes": json.loads(nodes_json),
            "edges": json.loads(edges_json),
            "incomplete_sources": list(self.incomplete_sources),
        }, separators=(",", ":"))
        
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def canonical_json(self) -> str:
        return json.dumps({
            "schema_version": self.schema_version,
            "repository": self.repository,
            "repository_revision": self.repository_revision,
            "policy_sha256": self.policy_sha256,
            "source_contract_hashes": list(self.source_contract_hashes),
            "nodes": json.loads(json.dumps([n.canonical_json() for n in sorted(self.nodes, key=lambda n: n.node_id)])),
            "edges": json.loads(json.dumps([e.canonical_json() for e in sorted(self.edges, key=lambda e: (e.source_id, e.target_id))])),
            "incomplete_sources": list(self.incomplete_sources),
            "surface_sha256": self.surface_sha256,
        }, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Validation Functions
# ---------------------------------------------------------------------------

class EffectSurfaceError(Exception):
    """Base exception for effect surface errors."""
    pass


class ContractError(EffectSurfaceError):
    """Contract validation error - fail closed."""
    pass


def validate_node_id(node_id: str) -> None:
    """Validate node ID format."""
    if not _IDENTIFIER.match(node_id):
        raise ContractError(f"Invalid node_id format: {node_id}")


def validate_sha256(sha: str, field_name: str = "sha256") -> None:
    """Validate SHA-256 format."""
    if not _SHA256.match(sha):
        raise ContractError(f"Invalid {field_name} format: {sha}")


def validate_node(node: EffectSurfaceNode) -> None:
    """Validate a single node - fail closed on unknown."""
    validate_node_id(node.node_id)
    validate_sha256(node.contract_sha256, "contract_sha256")
    
    # NodeKind validation is automatic via enum


def validate_edge(edge: EffectSurfaceEdge, node_ids: frozenset[str]) -> None:
    """Validate an edge - fail closed on unknown nodes."""
    validate_node_id(edge.source_id)
    validate_node_id(edge.target_id)
    validate_sha256(edge.condition_sha256, "condition_sha256")
    
    # Check nodes exist
    if edge.source_id not in node_ids:
        raise ContractError(f"Edge references unknown source node: {edge.source_id}")
    if edge.target_id not in node_ids:
        raise ContractError(f"Edge references unknown target node: {edge.target_id}")


def validate_snapshot(snapshot: EffectSurfaceSnapshot) -> None:
    """Validate complete snapshot - fail closed."""
    if snapshot.schema_version != SCHEMA_VERSION:
        raise ContractError(f"Invalid schema version: {snapshot.schema_version}")
    
    validate_sha256(snapshot.policy_sha256, "policy_sha256")
    
    # Validate all nodes
    node_ids = frozenset(n.node_id for n in snapshot.nodes)
    for node in snapshot.nodes:
        validate_node(node)
    
    # Check for duplicate node IDs
    if len(node_ids) != len(snapshot.nodes):
        raise ContractError("Duplicate node IDs detected")
    
    # Validate all edges
    for edge in snapshot.edges:
        validate_edge(edge, node_ids)


# ---------------------------------------------------------------------------
# Effect Class Relation Policy (partial ordering)
# ---------------------------------------------------------------------------

# Explicit relations: (before, after) -> relation
# This defines the ONLY valid relations. Everything else is INCOMPARABLE.
_EXPLICIT_EFFECT_RELATIONS: Mapping[tuple[EffectClass, EffectClass], EffectRelation] = {
    # Read ordering - moving from READ to X is widening (GREATER)
    (EffectClass.READ, EffectClass.WORKSPACE_READ): EffectRelation.GREATER,
    (EffectClass.READ, EffectClass.DATABASE_READ): EffectRelation.GREATER,
    (EffectClass.READ, EffectClass.RUNTIME_READ): EffectRelation.GREATER,
    (EffectClass.READ, EffectClass.EXTERNAL_READ): EffectRelation.GREATER,
    (EffectClass.READ, EffectClass.WORKSPACE_WRITE): EffectRelation.GREATER,
    (EffectClass.READ, EffectClass.DATABASE_WRITE): EffectRelation.GREATER,
    (EffectClass.READ, EffectClass.RUNTIME_WRITE): EffectRelation.GREATER,
    (EffectClass.READ, EffectClass.EXTERNAL_WRITE): EffectRelation.GREATER,
    (EffectClass.READ, EffectClass.DEPLOYMENT): EffectRelation.GREATER,
    
    # Workspace ordering
    (EffectClass.WORKSPACE_READ, EffectClass.WORKSPACE_WRITE): EffectRelation.GREATER,
    (EffectClass.WORKSPACE_WRITE, EffectClass.DEPLOYMENT): EffectRelation.GREATER,
    
    # Database ordering
    (EffectClass.DATABASE_READ, EffectClass.DATABASE_WRITE): EffectRelation.GREATER,
    (EffectClass.DATABASE_WRITE, EffectClass.DEPLOYMENT): EffectRelation.GREATER,
    
    # Runtime ordering
    (EffectClass.RUNTIME_READ, EffectClass.RUNTIME_WRITE): EffectRelation.GREATER,
    (EffectClass.RUNTIME_WRITE, EffectClass.DEPLOYMENT): EffectRelation.GREATER,
    
    # External ordering
    (EffectClass.EXTERNAL_READ, EffectClass.EXTERNAL_WRITE): EffectRelation.GREATER,
    (EffectClass.EXTERNAL_WRITE, EffectClass.DEPLOYMENT): EffectRelation.GREATER,
    
    # Reflexive relations
    (EffectClass.READ, EffectClass.READ): EffectRelation.EQUAL,
    (EffectClass.WORKSPACE_READ, EffectClass.WORKSPACE_READ): EffectRelation.EQUAL,
    (EffectClass.WORKSPACE_WRITE, EffectClass.WORKSPACE_WRITE): EffectRelation.EQUAL,
    (EffectClass.DATABASE_READ, EffectClass.DATABASE_READ): EffectRelation.EQUAL,
    (EffectClass.DATABASE_WRITE, EffectClass.DATABASE_WRITE): EffectRelation.EQUAL,
    (EffectClass.RUNTIME_READ, EffectClass.RUNTIME_READ): EffectRelation.EQUAL,
    (EffectClass.RUNTIME_WRITE, EffectClass.RUNTIME_WRITE): EffectRelation.EQUAL,
    (EffectClass.EXTERNAL_READ, EffectClass.EXTERNAL_READ): EffectRelation.EQUAL,
    (EffectClass.EXTERNAL_WRITE, EffectClass.EXTERNAL_WRITE): EffectRelation.EQUAL,
    (EffectClass.DEPLOYMENT, EffectClass.DEPLOYMENT): EffectRelation.EQUAL,
}


def compare_effect_classes(before: EffectClass, after: EffectClass) -> EffectRelation:
    """Compare two effect classes using explicit partial ordering.
    
    Returns:
        LESS: before < after (narrowing)
        EQUAL: no change
        GREATER: before > after (widening)
        INCOMPARABLE: no explicit relation defined
        UNKNOWN: unknown effect class
    
    IMPORTANT: This implements partial ordering. If no explicit relation
    is defined, INCOMPARABLE is returned (fail closed).
    """
    # Check explicit relations in both directions
    key = (before, after)
    if key in _EXPLICIT_EFFECT_RELATIONS:
        return _EXPLICIT_EFFECT_RELATIONS[key]
    
    # Check reverse
    reverse_key = (after, before)
    if reverse_key in _EXPLICIT_EFFECT_RELATIONS:
        reverse = _EXPLICIT_EFFECT_RELATIONS[reverse_key]
        if reverse == EffectRelation.LESS:
            return EffectRelation.GREATER
        if reverse == EffectRelation.GREATER:
            return EffectRelation.LESS
        return reverse
    
    # No explicit relation defined - fail closed
    return EffectRelation.INCOMPARABLE


# ---------------------------------------------------------------------------
# Scope Relations
# ---------------------------------------------------------------------------

def compare_scopes(before: Scope, after: Scope) -> ScopeRelation:
    """Compare two scopes using typed comparison.
    
    Returns:
        SAME: identical scopes
        NARROWER: before is narrower than after
        WIDER: before is wider than after
        DISJOINT: no overlap
        OVERLAPPING_INCOMPARABLE: partial overlap but not directly comparable
        UNKNOWN: unknown scope type
    """
    # Same type comparison
    if type(before) != type(after):
        return ScopeRelation.OVERLAPPING_INCOMPARABLE
    
    if isinstance(before, RepositoryScope):
        if before.owner == after.owner and before.repo == after.repo:
            return ScopeRelation.SAME
        if before.owner == after.owner:
            # Same org, different repo - wider/narrower depends on context
            return ScopeRelation.OVERLAPPING_INCOMPARABLE
        return ScopeRelation.DISJOINT
    
    if isinstance(before, OrganizationScope):
        if before.organization == after.organization:
            return ScopeRelation.SAME
        return ScopeRelation.DISJOINT
    
    if isinstance(before, PathScope):
        before_set = set(before.paths)
        after_set = set(after.paths)
        if before_set == after_set:
            return ScopeRelation.SAME
        if before_set.issubset(after_set):
            return ScopeRelation.NARROWER
        if before_set.issuperset(after_set):
            return ScopeRelation.WIDER
        if before_set.isdisjoint(after_set):
            return ScopeRelation.DISJOINT
        return ScopeRelation.OVERLAPPING_INCOMPARABLE
    
    if isinstance(before, CredentialScope):
        if before.provider == after.provider and before.resource == after.resource:
            before_ops = set(before.operations)
            after_ops = set(after.operations)
            if before_ops == after_ops:
                return ScopeRelation.SAME
            if before_ops.issubset(after_ops):
                return ScopeRelation.NARROWER
            if before_ops.issuperset(after_ops):
                return ScopeRelation.WIDER
            return ScopeRelation.OVERLAPPING_INCOMPARABLE
        return ScopeRelation.DISJOINT
    
    if isinstance(before, EnvironmentScope):
        if before.environment_id == after.environment_id:
            return ScopeRelation.SAME
        # Different environments - check if comparable via risk ordering
        return ScopeRelation.OVERLAPPING_INCOMPARABLE
    
    if isinstance(before, EgressScope):
        if before.protocol == after.protocol and before.host == after.host and before.port == after.port:
            return ScopeRelation.SAME
        # Check for wildcard patterns
        if after.host.startswith("*") or after.host.endswith(before.host):
            return ScopeRelation.WIDER
        if before.host.startswith("*") or before.host.endswith(after.host):
            return ScopeRelation.NARROWER
        return ScopeRelation.DISJOINT
    
    if isinstance(before, DatabaseScope):
        if before.database == after.database and before.schema == after.schema:
            before_tables = set(before.tables)
            after_tables = set(after.tables)
            if before_tables == after_tables:
                return ScopeRelation.SAME
            if before_tables.issubset(after_tables):
                return ScopeRelation.NARROWER
            if before_tables.issuperset(after_tables):
                return ScopeRelation.WIDER
            return ScopeRelation.OVERLAPPING_INCOMPARABLE
        return ScopeRelation.DISJOINT
    
    if isinstance(before, RuntimeScope):
        if before.service == after.service and before.container == after.container:
            return ScopeRelation.SAME
        return ScopeRelation.DISJOINT
    
    return ScopeRelation.UNKNOWN


# ---------------------------------------------------------------------------
# Environment Risk Relations
# ---------------------------------------------------------------------------

# Explicit environment risk ordering
_EXPLICIT_ENV_RELATIONS: Mapping[tuple[EnvironmentKind, EnvironmentKind], EnvironmentRelation] = {
    (EnvironmentKind.EPHEMERAL, EnvironmentKind.TEST): EnvironmentRelation.LESS_RISKY,
    (EnvironmentKind.EPHEMERAL, EnvironmentKind.DEVELOPMENT): EnvironmentRelation.LESS_RISKY,
    (EnvironmentKind.EPHEMERAL, EnvironmentKind.STAGING): EnvironmentRelation.LESS_RISKY,
    (EnvironmentKind.EPHEMERAL, EnvironmentKind.PRODUCTION): EnvironmentRelation.LESS_RISKY,
    (EnvironmentKind.TEST, EnvironmentKind.DEVELOPMENT): EnvironmentRelation.LESS_RISKY,
    (EnvironmentKind.TEST, EnvironmentKind.STAGING): EnvironmentRelation.LESS_RISKY,
    (EnvironmentKind.TEST, EnvironmentKind.PRODUCTION): EnvironmentRelation.LESS_RISKY,
    (EnvironmentKind.DEVELOPMENT, EnvironmentKind.STAGING): EnvironmentRelation.LESS_RISKY,
    (EnvironmentKind.DEVELOPMENT, EnvironmentKind.PRODUCTION): EnvironmentRelation.LESS_RISKY,
    (EnvironmentKind.STAGING, EnvironmentKind.PRODUCTION): EnvironmentRelation.LESS_RISKY,
    
    # Reflexive
    (EnvironmentKind.EPHEMERAL, EnvironmentKind.EPHEMERAL): EnvironmentRelation.EQUAL,
    (EnvironmentKind.TEST, EnvironmentKind.TEST): EnvironmentRelation.EQUAL,
    (EnvironmentKind.DEVELOPMENT, EnvironmentKind.DEVELOPMENT): EnvironmentRelation.EQUAL,
    (EnvironmentKind.STAGING, EnvironmentKind.STAGING): EnvironmentRelation.EQUAL,
    (EnvironmentKind.PRODUCTION, EnvironmentKind.PRODUCTION): EnvironmentRelation.EQUAL,
}


def compare_environments(before: EnvironmentKind, after: EnvironmentKind) -> EnvironmentRelation:
    """Compare two environments using explicit risk ordering."""
    key = (before, after)
    if key in _EXPLICIT_ENV_RELATIONS:
        return _EXPLICIT_ENV_RELATIONS[key]
    
    reverse_key = (after, before)
    if reverse_key in _EXPLICIT_ENV_RELATIONS:
        reverse = _EXPLICIT_ENV_RELATIONS[reverse_key]
        if reverse == EnvironmentRelation.LESS_RISKY:
            return EnvironmentRelation.MORE_RISKY
        if reverse == EnvironmentRelation.MORE_RISKY:
            return EnvironmentRelation.LESS_RISKY
        return reverse
    
    return EnvironmentRelation.UNKNOWN


# ---------------------------------------------------------------------------
# Diff Computation
# ---------------------------------------------------------------------------

class DiffVerdict(str, Enum):
    """Verdict for effect surface diff."""
    NO_SECURITY_EXPANSION = "no_security_expansion"
    EXPANSION_REVIEW_REQUIRED = "expansion_review_required"
    NARROWING_ONLY = "narrowing_only"
    UNVERIFIED_INPUT = "unverified_input"
    CONTRADICTED = "contradicted"
    RUNTIME_CONFIRMATION_REQUIRED = "runtime_confirmation_required"
    RUNTIME_CONFIRMED = "runtime_confirmed"


@dataclass(frozen=True, slots=True)
class EffectSurfaceDiff:
    """Diff between two effect surface snapshots."""
    before_snapshot: EffectSurfaceSnapshot
    after_snapshot: EffectSurfaceSnapshot
    verdict: DiffVerdict
    effect_class_changes: Tuple[EffectRelation, ...]
    scope_changes: Tuple[ScopeRelation, ...]
    environment_changes: Tuple[EnvironmentRelation, ...]
    new_edges: Tuple[EffectSurfaceEdge, ...]
    removed_edges: Tuple[EffectSurfaceEdge, ...]
    diff_sha256: str = ""

    def __post_init__(self):
        if not self.diff_sha256:
            object.__setattr__(self, 'diff_sha256', self._compute_sha256())

    def _compute_sha256(self) -> str:
        canonical = json.dumps({
            "before_surface_sha256": self.before_snapshot.surface_sha256,
            "after_surface_sha256": self.after_snapshot.surface_sha256,
            "verdict": self.verdict.value,
            "effect_class_changes": [e.value for e in self.effect_class_changes],
            "scope_changes": [s.value for s in self.scope_changes],
            "environment_changes": [e.value for e in self.environment_changes],
            "new_edge_count": len(self.new_edges),
            "removed_edge_count": len(self.removed_edges),
        }, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_diff(before: EffectSurfaceSnapshot, after: EffectSurfaceSnapshot) -> EffectSurfaceDiff:
    """Compute diff between two effect surface snapshots."""
    validate_snapshot(before)
    validate_snapshot(after)
    
    # Build edge lookup
    before_edges = {(e.source_id, e.target_id): e for e in before.edges}
    after_edges = {(e.source_id, e.target_id): e for e in after.edges}
    
    # Find new and removed edges
    new_edge_keys = set(after_edges.keys()) - set(before_edges.keys())
    removed_edge_keys = set(before_edges.keys()) - set(after_edges.keys())
    
    new_edges = tuple(after_edges[k] for k in new_edge_keys)
    removed_edges = tuple(before_edges[k] for k in removed_edge_keys)
    
    # Determine verdict
    effect_changes: list[EffectRelation] = []
    has_widening = False
    has_narrowing = False
    
    for new_edge in new_edges:
        # Check effect class changes
        old_edge = before_edges.get((new_edge.source_id, new_edge.target_id))
        if old_edge:
            # Edge exists in both - compare effect classes
            relation = compare_effect_classes(old_edge.effect_class, new_edge.effect_class)
            effect_changes.append(relation)
            if relation == EffectRelation.GREATER:
                has_widening = True
            elif relation == EffectRelation.LESS:
                has_narrowing = True
        else:
            # Brand new edge - this is an expansion (new capability)
            # A new edge to a tool is more powerful than no edge
            has_widening = True
    
    if has_widening:
        verdict = DiffVerdict.EXPANSION_REVIEW_REQUIRED
    elif has_narrowing and not has_widening:
        verdict = DiffVerdict.NARROWING_ONLY
    else:
        verdict = DiffVerdict.NO_SECURITY_EXPANSION
    
    return EffectSurfaceDiff(
        before_snapshot=before,
        after_snapshot=after,
        verdict=verdict,
        effect_class_changes=tuple(effect_changes),
        scope_changes=(),  # Would need scope tracking per edge
        environment_changes=(),
        new_edges=new_edges,
        removed_edges=removed_edges,
    )
