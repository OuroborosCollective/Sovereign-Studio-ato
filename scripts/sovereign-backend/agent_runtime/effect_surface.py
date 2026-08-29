"""Canonical Effect Surface Model for SESD (Sovereign Effect Scope DAG).

Pure, deterministic contract foundation: Effect-Surface-Nodes/Edges, versioned
partial ordering of Effect Classes, Scope-Widening/Narrowing relations, and the
Scope-Relations contract. NO real mutations, network calls, or side effects.

This module defines the static effect surface that other lanes (mutation evidence,
control mutation, skill runtime) consume to decide whether a proposed action's
effect class and scope are admissible. It is a *contract surface*, not an execution
runtime.

Design constraints:
- No network, database, filesystem, clock or random access in this module.
- Unknown effect classes and relation kinds are blocked with ContractError.
- No dynamic plugin/LLM registry -- static V1 allowlist only.
- Secret-shaped raw fields are never stored in contracts.
- Partial ordering is *strict*: irreflexive, asymmetric, transitive.
- Scope comparison returns exactly one of WIDENING, NARROWING, EQUAL, INCOMPARABLE.
- The registry snapshot is deterministic and secret-free.

Canonical ownership:
    - Execution projection lives in the TypeScript runtime.
    - Effect summary lives in skills/manifest.py (coarse skill-level EffectClass).
    - This module owns the fine-grained SESD surface contract.

Alignment:
    - skills.manifest.EffectClass maps to SurfaceEffectClass via
      COARSE_TO_SURFACE_CLASS mapping (defined below).
    - environment_mcp_execution.EnvironmentKind is referenced, not duplicated.
    - mutation_evidence_layer.MUTATION_FAMILY_IDS inform which effect classes
      require proof envelopes (computed externally, not here).

@module agent_runtime.effect_surface
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, FrozenSet, Final, Mapping, Sequence, Tuple


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------

EFFECT_SURFACE_SCHEMA_VERSION: Final[str] = "sovereign.effect-surface.v1"


# ---------------------------------------------------------------------------
# Contract error
# ---------------------------------------------------------------------------


class EffectSurfaceContractError(ValueError):
    """A contract invariant was violated in the effect surface model."""


# ---------------------------------------------------------------------------
# Internal helpers (defined first because scope dataclasses and registry
# snapshot depend on them)
# ---------------------------------------------------------------------------


def _canonicalize(value: Any) -> Any:
    """Normalize a value for deterministic JSON serialization."""
    if isinstance(value, dict):
        return {k: _canonicalize(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(v) for v in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise EffectSurfaceContractError("floats are forbidden in canonical JSON")
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise EffectSurfaceContractError(f"unsupported type in canonical JSON: {type(value).__name__}")


def _canonical_json(value: Any) -> str:
    """Deterministic JSON serialization (matches provider_neutral_runtime pattern)."""
    return json.dumps(
        _canonicalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _canonical_sha256(value: Any) -> str:
    """Deterministic SHA-256 for canonical JSON."""
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


_SECRET_KEY_MARKERS: Final[tuple[str, ...]] = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "private_key",
    "client_secret",
    "cookie",
    "raw_prompt",
    "prompt_text",
    "file_content",
    "database_row",
    "credential",
    "auth",
)


def _reject_secret_shaped_dict(value: Dict[str, Any], *, path: str = "$") -> None:
    """Recursively reject secret-shaped keys in dicts."""
    for key, item in value.items():
        if isinstance(key, str):
            key_lower = key.lower()
            if any(marker in key_lower for marker in _SECRET_KEY_MARKERS):
                raise EffectSurfaceContractError(
                    f"secret-shaped field '{key}' is forbidden at {path}"
                )
            if isinstance(item, dict):
                _reject_secret_shaped_dict(item, path=f"{path}.{key}")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class NodeKind(str, Enum):
    """Kinds of nodes in the effect surface DAG.

    Each node represents a distinct scope domain that an effect may target.
    """

    REPOSITORY = "repository"
    ORGANIZATION = "organization"
    PATH = "path"
    CREDENTIAL = "credential"
    ENVIRONMENT = "environment"
    EGRESS = "egress"
    RUNTIME = "runtime"


class RelationKind(str, Enum):
    """Kinds of edges in the effect surface DAG.

    PARTIAL_ORDER: a < b in the effect-class strict partial ordering.
    SCOPE_WIDENS:  scope(a) is wider than scope(b) (a covers b).
    SCOPE_NARROWS: scope(a) is narrower than scope(b) (b covers a).
    CONFLICT:      a and b are mutually exclusive in the same scope.
    """

    PARTIAL_ORDER = "partial_order"
    SCOPE_WIDENS = "scope_widens"
    SCOPE_NARROWS = "scope_narrows"
    CONFLICT = "conflict"


class SurfaceEffectClass(str, Enum):
    """Fine-grained effect classes for the SESD surface model.

    These are the *surface-level* effect classes that the effect surface DAG
    reasons about. The coarser skills.manifest.EffectClass maps into these
    via COARSE_TO_SURFACE_CLASS.

    The partial ordering is defined in _EFFECT_CLASS_ORDER_PAIRS. Not all
    pairs are comparable; INCOMPARABLE is a valid and expected result.
    """

    OBSERVE = "observe"
    READ = "read"
    COMPUTE = "compute"
    VALIDATE = "validate"
    LINT = "lint"
    TEST = "test"
    BUILD = "build"
    PLAN = "plan"
    DIFF_PREVIEW = "diff_preview"
    WORKSPACE_WRITE = "workspace_write"
    DIFF_APPLY = "diff_apply"
    DRAFT_PR = "draft_pr"
    CREDENTIAL_ACCESS = "credential_access"
    EGRESS_NETWORK = "egress_network"
    DEPLOY = "deploy"
    MERGE = "merge"
    OWNER_BOUND = "owner_bound"


class ScopeRelation(str, Enum):
    """Result of comparing two scopes.

    WIDENING:  scope_a is strictly wider than scope_b (covers b and more).
    NARROWING: scope_a is strictly narrower than scope_b (b covers a and more).
    EQUAL:     scope_a and scope_b are the same scope.
    INCOMPARABLE: neither scope contains the other.
    """

    WIDENING = "WIDENING"
    NARROWING = "NARROWING"
    EQUAL = "EQUAL"
    INCOMPARABLE = "INCOMPARABLE"


# ---------------------------------------------------------------------------
# Coarse-to-surface class mapping
# ---------------------------------------------------------------------------

# skills.manifest.EffectClass values mapped to one or more SurfaceEffectClass.
# This is a many-to-many mapping: one coarse class may cover multiple surface
# classes, and one surface class may be covered by multiple coarse classes.
COARSE_TO_SURFACE_CLASS: Final[Mapping[str, Tuple[SurfaceEffectClass, ...]]] = {
    "read_only": (
        SurfaceEffectClass.OBSERVE,
        SurfaceEffectClass.READ,
        SurfaceEffectClass.COMPUTE,
        SurfaceEffectClass.VALIDATE,
        SurfaceEffectClass.LINT,
    ),
    "bounded_reversible": (
        SurfaceEffectClass.TEST,
        SurfaceEffectClass.BUILD,
        SurfaceEffectClass.PLAN,
        SurfaceEffectClass.DIFF_PREVIEW,
        SurfaceEffectClass.WORKSPACE_WRITE,
    ),
    "bounded_stateless": (
        SurfaceEffectClass.DIFF_APPLY,
        SurfaceEffectClass.DRAFT_PR,
    ),
    "draft_pr": (
        SurfaceEffectClass.DRAFT_PR,
    ),
    "owner_bound": (
        SurfaceEffectClass.CREDENTIAL_ACCESS,
        SurfaceEffectClass.EGRESS_NETWORK,
        SurfaceEffectClass.DEPLOY,
        SurfaceEffectClass.MERGE,
        SurfaceEffectClass.OWNER_BOUND,
    ),
}


# ---------------------------------------------------------------------------
# Partial ordering table (strict: irreflexive, asymmetric, transitive)
# ---------------------------------------------------------------------------

# Each entry (a, b) means a < b in the strict partial order.
# The transitive closure is computed at module load and cached.
# Not listed pairs are INCOMPARABLE by design.

_EFFECT_CLASS_ORDER_PAIRS: Final[Tuple[Tuple[SurfaceEffectClass, SurfaceEffectClass], ...]] = (
    # Read tier
    (SurfaceEffectClass.OBSERVE, SurfaceEffectClass.READ),
    (SurfaceEffectClass.READ, SurfaceEffectClass.COMPUTE),
    (SurfaceEffectClass.COMPUTE, SurfaceEffectClass.VALIDATE),
    (SurfaceEffectClass.COMPUTE, SurfaceEffectClass.LINT),
    # Test/build tier
    (SurfaceEffectClass.VALIDATE, SurfaceEffectClass.TEST),
    (SurfaceEffectClass.LINT, SurfaceEffectClass.TEST),
    (SurfaceEffectClass.TEST, SurfaceEffectClass.BUILD),
    (SurfaceEffectClass.BUILD, SurfaceEffectClass.PLAN),
    # Plan -> write tier
    (SurfaceEffectClass.PLAN, SurfaceEffectClass.DIFF_PREVIEW),
    (SurfaceEffectClass.PLAN, SurfaceEffectClass.WORKSPACE_WRITE),
    # Write tier
    (SurfaceEffectClass.DIFF_PREVIEW, SurfaceEffectClass.DIFF_APPLY),
    (SurfaceEffectClass.WORKSPACE_WRITE, SurfaceEffectClass.DIFF_APPLY),
    (SurfaceEffectClass.DIFF_APPLY, SurfaceEffectClass.DRAFT_PR),
    # Draft PR -> high-privilege tier
    (SurfaceEffectClass.DRAFT_PR, SurfaceEffectClass.CREDENTIAL_ACCESS),
    (SurfaceEffectClass.DRAFT_PR, SurfaceEffectClass.EGRESS_NETWORK),
    (SurfaceEffectClass.DRAFT_PR, SurfaceEffectClass.DEPLOY),
    (SurfaceEffectClass.CREDENTIAL_ACCESS, SurfaceEffectClass.OWNER_BOUND),
    (SurfaceEffectClass.EGRESS_NETWORK, SurfaceEffectClass.OWNER_BOUND),
    (SurfaceEffectClass.DEPLOY, SurfaceEffectClass.MERGE),
    (SurfaceEffectClass.MERGE, SurfaceEffectClass.OWNER_BOUND),
)


def _build_transitive_closure(
    pairs: Tuple[Tuple[SurfaceEffectClass, SurfaceEffectClass], ...],
) -> FrozenSet[Tuple[SurfaceEffectClass, SurfaceEffectClass]]:
    """Compute the transitive closure of the strict partial ordering.

    Returns the set of all (a, b) where a < b transitively.
    """
    closure: set[Tuple[SurfaceEffectClass, SurfaceEffectClass]] = set(pairs)
    changed = True
    while changed:
        changed = False
        new_pairs: set[Tuple[SurfaceEffectClass, SurfaceEffectClass]] = set()
        for (a, b) in closure:
            for (c, d) in closure:
                if b is c and (a, d) not in closure:
                    new_pairs.add((a, d))
        if new_pairs:
            closure.update(new_pairs)
            changed = True
    return frozenset(closure)


_EFFECT_CLASS_CLOSURE: Final[FrozenSet[Tuple[SurfaceEffectClass, SurfaceEffectClass]]] = (
    _build_transitive_closure(_EFFECT_CLASS_ORDER_PAIRS)
)


def _check_antisymmetry(
    closure: FrozenSet[Tuple[SurfaceEffectClass, SurfaceEffectClass]],
) -> None:
    """Verify the strict partial ordering is asymmetric (no a<b and b<a)."""
    for (a, b) in closure:
        if (b, a) in closure:
            raise EffectSurfaceContractError(
                f"partial ordering violation: both ({a.value}, {b.value}) and "
                f"({b.value}, {a.value}) present"
            )


_check_antisymmetry(_EFFECT_CLASS_CLOSURE)


# ---------------------------------------------------------------------------
# Effect class comparison
# ---------------------------------------------------------------------------


def compare_effect_classes(
    a: SurfaceEffectClass,
    b: SurfaceEffectClass,
) -> ScopeRelation:
    """Compare two effect classes under the strict partial ordering.

    Returns:
        WIDENING:  a < b (a is lower-privilege, b is higher; b widens from a).
        NARROWING: b < a (a is higher-privilege; a narrows from b).
        EQUAL:     a is b.
        INCOMPARABLE: neither a < b nor b < a.
    """
    if a is b:
        return ScopeRelation.EQUAL
    if (a, b) in _EFFECT_CLASS_CLOSURE:
        return ScopeRelation.WIDENING
    if (b, a) in _EFFECT_CLASS_CLOSURE:
        return ScopeRelation.NARROWING
    return ScopeRelation.INCOMPARABLE


# ---------------------------------------------------------------------------
# Scope dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RepositoryScope:
    """Scope for a repository node."""

    owner: str
    repository: str
    revision: str = ""

    def canonical_json(self) -> str:
        return _canonical_json({"owner": self.owner, "repository": self.repository, "revision": self.revision})


@dataclass(frozen=True, slots=True)
class OrganizationScope:
    """Scope for an organization node."""

    owner: str

    def canonical_json(self) -> str:
        return _canonical_json({"owner": self.owner})


@dataclass(frozen=True, slots=True)
class PathScope:
    """Scope for a path node within a repository."""

    owner: str
    repository: str
    path: str

    def canonical_json(self) -> str:
        return _canonical_json({"owner": self.owner, "repository": self.repository, "path": self.path})


@dataclass(frozen=True, slots=True)
class CredentialScope:
    """Scope for a credential node. The credential_id is a non-secret handle."""

    credential_id: str
    environment: str = ""

    def canonical_json(self) -> str:
        return _canonical_json({"credential_id": self.credential_id, "environment": self.environment})


@dataclass(frozen=True, slots=True)
class EnvironmentScope:
    """Scope for an environment node.

    environment_kind aligns with environment_mcp_execution.EnvironmentKind values
    (development, test, staging, production, ephemeral) but is stored as a string
    to avoid a hard import dependency on a runtime module.
    """

    environment_kind: str
    region: str = ""

    def canonical_json(self) -> str:
        return _canonical_json({"environment_kind": self.environment_kind, "region": self.region})


@dataclass(frozen=True, slots=True)
class EgressScope:
    """Scope for a network egress node."""

    destination: str
    protocol: str = ""

    def canonical_json(self) -> str:
        return _canonical_json({"destination": self.destination, "protocol": self.protocol})


@dataclass(frozen=True, slots=True)
class RuntimeScope:
    """Scope for a runtime node."""

    runtime_id: str
    environment_kind: str = ""
    image_digest: str = ""

    def canonical_json(self) -> str:
        return _canonical_json({
            "runtime_id": self.runtime_id,
            "environment_kind": self.environment_kind,
            "image_digest": self.image_digest,
        })


# Type alias for any scope dataclass
ScopeData = RepositoryScope | OrganizationScope | PathScope | CredentialScope | EnvironmentScope | EgressScope | RuntimeScope


# ---------------------------------------------------------------------------
# Scope comparison
# ---------------------------------------------------------------------------

# Widening rules: which node kind scopes wider-than which other node kind scopes.
# (a_kind, b_kind) means a scope of a_kind *may* be wider than b scope of b_kind
# if the containment predicate (defined below) holds.
_SCOPE_WIDENS_KIND_PAIRS: Final[FrozenSet[Tuple[NodeKind, NodeKind]]] = frozenset({
    # Organization contains repositories
    (NodeKind.ORGANIZATION, NodeKind.REPOSITORY),
    # Repository contains paths
    (NodeKind.REPOSITORY, NodeKind.PATH),
    # Organization contains paths (transitive via repository)
    (NodeKind.ORGANIZATION, NodeKind.PATH),
    # Environment contains runtimes
    (NodeKind.ENVIRONMENT, NodeKind.RUNTIME),
})


def _scope_containment(a: ScopeData, b: ScopeData) -> bool | None:
    """Check whether scope a contains scope b.

    Returns True if a contains b, False if definitely not, None if
    the pair cannot be decided by static containment alone.
    """
    a_kind = _scope_kind(a)
    b_kind = _scope_kind(b)

    if a_kind == b_kind:
        return None  # delegate to equality check

    if (a_kind, b_kind) not in _SCOPE_WIDENS_KIND_PAIRS:
        return False

    # Structural containment check
    if isinstance(a, OrganizationScope) and isinstance(b, RepositoryScope):
        return a.owner == b.owner
    if isinstance(a, OrganizationScope) and isinstance(b, PathScope):
        return a.owner == b.owner
    if isinstance(a, RepositoryScope) and isinstance(b, PathScope):
        return a.owner == b.owner and a.repository == b.repository
    if isinstance(a, EnvironmentScope) and isinstance(b, RuntimeScope):
        if b.environment_kind:
            return a.environment_kind == b.environment_kind
        return True  # unspecified environment_kind on runtime means any env contains it

    return False


def compare_scopes(a: ScopeData, b: ScopeData) -> ScopeRelation:
    """Compare two scope dataclass instances.

    Returns:
        WIDENING:  a is strictly wider than b (a contains b, but b does not contain a).
        NARROWING: a is strictly narrower than b (b contains a, but a does not contain b).
        EQUAL:     a and b represent the same scope.
        INCOMPARABLE: neither scope contains the other.
    """
    if a == b:
        return ScopeRelation.EQUAL

    a_contains_b = _scope_containment(a, b)
    b_contains_a = _scope_containment(b, a)

    if a_contains_b is True and b_contains_a is not True:
        return ScopeRelation.WIDENING
    if b_contains_a is True and a_contains_b is not True:
        return ScopeRelation.NARROWING
    if a_contains_b is True and b_contains_a is True:
        # Both contain each other only if equal, which we already checked
        return ScopeRelation.EQUAL
    return ScopeRelation.INCOMPARABLE


def _scope_kind(scope: ScopeData) -> NodeKind:
    """Infer the NodeKind from a scope dataclass instance."""
    if isinstance(scope, RepositoryScope):
        return NodeKind.REPOSITORY
    if isinstance(scope, OrganizationScope):
        return NodeKind.ORGANIZATION
    if isinstance(scope, PathScope):
        return NodeKind.PATH
    if isinstance(scope, CredentialScope):
        return NodeKind.CREDENTIAL
    if isinstance(scope, EnvironmentScope):
        return NodeKind.ENVIRONMENT
    if isinstance(scope, EgressScope):
        return NodeKind.EGRESS
    if isinstance(scope, RuntimeScope):
        return NodeKind.RUNTIME
    raise EffectSurfaceContractError(f"unknown scope type: {type(scope).__name__}")


# ---------------------------------------------------------------------------
# Effect Surface Node / Edge
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EffectSurfaceNode:
    """A node in the effect surface DAG.

    Each node binds a NodeKind, a scope, and an effect class.
    The node_id is a deterministic hash of (kind, scope.canonical_json(), effect_class).
    """

    kind: NodeKind
    scope: ScopeData
    effect_class: SurfaceEffectClass

    @property
    def node_id(self) -> str:
        raw = _canonical_json({
            "kind": self.kind.value,
            "scope": self.scope.canonical_json(),
            "effect_class": self.effect_class.value,
        })
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]

    def canonical_body(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "scope": self.scope.canonical_json(),
            "effect_class": self.effect_class.value,
            "node_id": self.node_id,
        }


@dataclass(frozen=True, slots=True)
class EffectSurfaceEdge:
    """An edge in the effect surface DAG.

    Each edge binds a RelationKind and a source/target node pair.
    The edge_id is a deterministic hash of (source.node_id, relation, target.node_id).
    """

    source: EffectSurfaceNode
    relation: RelationKind
    target: EffectSurfaceNode

    @property
    def edge_id(self) -> str:
        raw = _canonical_json({
            "source": self.source.node_id,
            "relation": self.relation.value,
            "target": self.target.node_id,
        })
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]

    def canonical_body(self) -> Dict[str, Any]:
        return {
            "source": self.source.node_id,
            "relation": self.relation.value,
            "target": self.target.node_id,
            "edge_id": self.edge_id,
        }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _reject_secret_shaped_scope(scope: ScopeData) -> None:
    """Reject scopes where field values look like secrets.

    Checks field *values* (not names) against patterns that indicate leaked
    credentials. A field named 'credential_id' with value 'gh-token' is fine;
    a field with value 'sk-...' or 'ghp_...' is not.
    """
    # Patterns that indicate a value is likely a real secret
    _SECRET_VALUE_PREFIXES: Final[tuple[str, ...]] = (
        "sk-",       # OpenAI / generic API key prefix
        "sk_live_",  # Stripe live key
        "ghp_",      # GitHub personal access token
        "gho_",      # GitHub OAuth token
        "ghu_",      # GitHub user-to-server token
        "ghs_",      # GitHub server-to-server token
        "ghr_",      # GitHub refresh token
        "xoxb-",     # Slack bot token
        "xoxp-",     # Slack user token
        "xoxa-",     # Slack app token
        "AKIA",      # AWS access key ID
        "AIza",      # Google API key
        "eyJ",       # JWT token prefix (base64)
    )

    for f in scope.__dataclass_fields__:
        val = getattr(scope, f)
        if isinstance(val, str) and val:
            if any(val.startswith(prefix) for prefix in _SECRET_VALUE_PREFIXES):
                raise EffectSurfaceContractError(
                    f"secret-shaped value in field '{f}' is forbidden in "
                    f"{type(scope).__name__}: starts with known secret prefix"
                )
            # Also reject values that are excessively long (likely key material)
            if len(val) > 256:
                raise EffectSurfaceContractError(
                    f"field '{f}' in {type(scope).__name__} exceeds 256 chars, "
                    f"suspected key material"
                )


def validate_edge(edge: EffectSurfaceEdge) -> EffectSurfaceEdge:
    """Validate an edge against the effect surface contract.

    Returns the edge if valid, raises EffectSurfaceContractError otherwise.
    """
    if edge.relation == RelationKind.PARTIAL_ORDER:
        rel = compare_effect_classes(edge.source.effect_class, edge.target.effect_class)
        if rel != ScopeRelation.WIDENING:
            raise EffectSurfaceContractError(
                f"PARTIAL_ORDER edge requires source < target, got {rel.value} "
                f"for ({edge.source.effect_class.value}, {edge.target.effect_class.value})"
            )
    elif edge.relation == RelationKind.SCOPE_WIDENS:
        rel = compare_scopes(edge.source.scope, edge.target.scope)
        if rel != ScopeRelation.WIDENING:
            raise EffectSurfaceContractError(
                f"SCOPE_WIDENS edge requires source wider than target, got {rel.value}"
            )
    elif edge.relation == RelationKind.SCOPE_NARROWS:
        rel = compare_scopes(edge.source.scope, edge.target.scope)
        if rel != ScopeRelation.NARROWING:
            raise EffectSurfaceContractError(
                f"SCOPE_NARROWS edge requires source narrower than target, got {rel.value}"
            )
    elif edge.relation == RelationKind.CONFLICT:
        # Conflict edges are valid by definition; the contract only requires
        # that source and target are not the same node.
        if edge.source == edge.target:
            raise EffectSurfaceContractError(
                "CONFLICT edge source and target must be different nodes"
            )
    else:
        raise EffectSurfaceContractError(f"unknown RelationKind: {edge.relation!r}")
    return edge


def validate_snapshot(
    nodes: Sequence[EffectSurfaceNode],
    edges: Sequence[EffectSurfaceEdge],
) -> None:
    """Validate an entire effect surface snapshot.

    Checks:
    - All node_ids are unique.
    - All edge_ids are unique.
    - All edges pass validate_edge.
    - No duplicate edges between the same (source, relation, target).
    - No secret-shaped fields in any scope.
    """
    node_ids: set[str] = set()
    for node in nodes:
        if node.node_id in node_ids:
            raise EffectSurfaceContractError(f"duplicate node_id: {node.node_id}")
        node_ids.add(node.node_id)
        _reject_secret_shaped_scope(node.scope)

    edge_ids: set[str] = set()
    edge_triples: set[Tuple[str, str, str]] = set()
    for edge in edges:
        if edge.edge_id in edge_ids:
            raise EffectSurfaceContractError(f"duplicate edge_id: {edge.edge_id}")
        edge_ids.add(edge.edge_id)
        triple = (edge.source.node_id, edge.relation.value, edge.target.node_id)
        if triple in edge_triples:
            raise EffectSurfaceContractError(
                f"duplicate edge triple: ({triple[0][:12]}…, {triple[1]}, {triple[2][:12]}…)"
            )
        edge_triples.add(triple)
        validate_edge(edge)


# ---------------------------------------------------------------------------
# Registry snapshot
# ---------------------------------------------------------------------------


def effect_surface_registry_snapshot() -> Dict[str, Any]:
    """Return the deterministic, secret-free registry projection.

    Includes:
    - Schema version
    - All effect classes
    - Partial ordering closure
    - Coarse-to-surface class mapping
    - Scope widening kind pairs
    """
    return {
        "schema_version": EFFECT_SURFACE_SCHEMA_VERSION,
        "effect_classes": [cls.value for cls in SurfaceEffectClass],
        "partial_order_closure": [
            {"less": a.value, "greater": b.value}
            for (a, b) in sorted(_EFFECT_CLASS_CLOSURE, key=lambda p: (p[0].value, p[1].value))
        ],
        "coarse_to_surface": {
            k: [cls.value for cls in v]
            for k, v in sorted(COARSE_TO_SURFACE_CLASS.items())
        },
        "scope_widens_kind_pairs": [
            {"wider": a.value, "narrower": b.value}
            for (a, b) in sorted(_SCOPE_WIDENS_KIND_PAIRS, key=lambda p: (p[0].value, p[1].value))
        ],
    }


EFFECT_SURFACE_REGISTRY_SHA256: Final[str] = _canonical_sha256(effect_surface_registry_snapshot())
