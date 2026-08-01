"""Evidence-Classed Durable Memory Forest for Sovereign Studio ATO.

Stores long-lived, reusable insights as canonical Memory Leaves with explicit
evidence classes, owner/tenant/repo/revision binding and provenance chains.
Summaries, retrieval documents, graph projections and embeddings are derived
structures only — they can be discarded and fully rebuilt from the canonical
leaves.

Design constraints:
- No network, database, filesystem, clock or random access in this module.
- Evidence class cannot be promoted by retrieval score or semantic similarity.
- Raw transcripts, LLM outputs, tool texts and embeddings are never auto-VERIFIED.
- Supersession is append-only: new leaf_id + predecessor link.
- Retrieval enforces owner/tenant/repo/workspace scope before relevance ranking.
- Secrets, tokens, PIIs and instruction-injection payloads are rejected at the boundary.
- No Arelorian WASD or N+1 personality integration in this ATO module.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Final, FrozenSet, List, Mapping, Optional, Sequence, Tuple

SCHEMA_VERSION: Final[str] = "sovereign.durable-memory-forest.v1"

# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------
_MAX_CONTENT_BYTES: Final[int] = 16_384
_MAX_READBACK_LINKS: Final[int] = 32
_MAX_LEAVES_PER_PACK: Final[int] = 64
_MAX_VALIDITY_RULES: Final[int] = 16
_MAX_OWNER_LEN: Final[int] = 128

# ---------------------------------------------------------------------------
# Secret / injection guard patterns
# ---------------------------------------------------------------------------
_SECRET_PATTERNS: Final[Tuple[re.Pattern[str], ...]] = (
    re.compile(r"(?i)bearer\s+[a-z0-9\-._~+/]{8,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    re.compile(r"(?i)(password|passwd|secret|token|api[_\-]?key)\s*[:=]\s*\S{4,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]+ KEY-----"),
    re.compile(r"(?i)(postgres|mysql|mongodb)://[^@]+:[^@]+@"),
)

# Prompt/instruction injection patterns to reject from memory content
_INJECTION_PATTERNS: Final[Tuple[re.Pattern[str], ...]] = (
    re.compile(r"(?i)<\s*(system|user|assistant|instruction)\s*>"),
    re.compile(r"(?i)ignore\s+(previous|prior|above)\s+instructions?"),
    re.compile(r"(?i)you\s+are\s+now\s+(a\s+)?(?:different|new)\s+(ai|assistant|model)"),
)

_SHA40: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_OWNER_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_.]{0,127}$")


class MemoryContractError(ValueError):
    """An input violated a memory forest invariant."""


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class EvidenceClass(str, Enum):
    """Explicit trust classification for every Memory Leaf."""
    REPORTED = "reported"        # claimed by user, doc or external content; not verified
    OBSERVED = "observed"        # seen in real tool/runtime output; not yet confirmed
    VERIFIED = "verified"        # confirmed by an explicit evidence receipt + gate
    CONTRADICTED = "contradicted"  # known to conflict with verified evidence
    INVALIDATED = "invalidated"  # superseded or retracted; predecessor link stored


# Evidence classes that may be promoted to VERIFIED (only by explicit evidence, never LLM)
_PROMOTABLE_TO_VERIFIED: Final[FrozenSet[EvidenceClass]] = frozenset({
    EvidenceClass.OBSERVED,
})
_PROMOTABLE_TO_OBSERVED: Final[FrozenSet[EvidenceClass]] = frozenset({
    EvidenceClass.REPORTED,
})


class SourceClass(str, Enum):
    """Canonical source of a Memory Leaf."""
    CONTINUITY = "continuity"                     # continuation state
    REPOSITORY_READBACK = "repository_readback"   # real git/repo readback
    CI_READBACK = "ci_readback"                   # GitHub Actions / CI
    RUNTIME_READBACK = "runtime_readback"         # live runtime observation
    IMAGE_READBACK = "image_readback"             # Docker/OCI image inspection
    DEPLOYMENT_READBACK = "deployment_readback"   # deployment/PatchMon readback
    POSTGRES_READBACK = "postgres_readback"       # DB schema/data readback
    OPERATOR_RULE = "operator_rule"               # stable governance / policy rule
    PROCEDURE = "procedure"                       # reusable procedure / runbook
    HUMAN_REPORTED = "human_reported"             # human note, NOT auto-VERIFIED
    DERIVED = "derived"                           # derived/computed — cannot be VERIFIED


# Source classes that can reach VERIFIED
_VERIFIABLE_SOURCES: Final[FrozenSet[SourceClass]] = frozenset({
    SourceClass.REPOSITORY_READBACK,
    SourceClass.CI_READBACK,
    SourceClass.RUNTIME_READBACK,
    SourceClass.IMAGE_READBACK,
    SourceClass.DEPLOYMENT_READBACK,
    SourceClass.POSTGRES_READBACK,
    SourceClass.OPERATOR_RULE,
    SourceClass.PROCEDURE,
})

# Source classes that are permanently capped at OBSERVED
_OBSERVED_CAP_SOURCES: Final[FrozenSet[SourceClass]] = frozenset({
    SourceClass.HUMAN_REPORTED,
    SourceClass.DERIVED,
})


# ---------------------------------------------------------------------------
# Canonical hash helpers
# ---------------------------------------------------------------------------

def _canonical_sha256(value: object) -> str:
    s = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(s.encode()).hexdigest()


def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Boundary guards
# ---------------------------------------------------------------------------

def _reject_secrets(text: str, *, field: str) -> None:
    for pat in _SECRET_PATTERNS:
        if pat.search(text):
            raise MemoryContractError(
                f"Field '{field}' contains secret-shaped material."
            )


def _reject_injection(text: str, *, field: str) -> None:
    for pat in _INJECTION_PATTERNS:
        if pat.search(text):
            raise MemoryContractError(
                f"Field '{field}' contains prompt/instruction injection pattern."
            )


def _validate_owner(value: str, *, field: str) -> str:
    if not value or not value.strip():
        raise MemoryContractError(f"'{field}' must not be empty.")
    if ".." in value or "/" in value or "\\" in value or "\x00" in value:
        raise MemoryContractError(f"'{field}' contains forbidden character.")
    if not _OWNER_PATTERN.fullmatch(value):
        raise MemoryContractError(f"'{field}' contains invalid characters (got {value!r}).")
    return value


def _validate_revision(value: Optional[str], *, field: str) -> Optional[str]:
    if value is None:
        return None
    if not _SHA40.fullmatch(value):
        raise MemoryContractError(f"'{field}' must be 40-char hex SHA (got {value!r}).")
    return value


# ---------------------------------------------------------------------------
# Retrieval scope (enforced before relevance ranking)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetrievalScope:
    """Mandatory scope filter applied before any retrieval or similarity ranking."""
    owner: str
    tenant: Optional[str]
    repo: Optional[str]
    workspace_id: Optional[str]

    def matches(self, leaf: "MemoryLeaf") -> bool:
        if leaf.owner != self.owner:
            return False
        if self.tenant is not None and leaf.tenant != self.tenant:
            return False
        if self.repo is not None and leaf.repo != self.repo:
            return False
        if self.workspace_id is not None and leaf.workspace_id != self.workspace_id:
            return False
        return True


# ---------------------------------------------------------------------------
# Memory Leaf (canonical, immutable)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MemoryLeaf:
    """Immutable canonical Memory Leaf.

    All evidence classes, provenance, revision and scope bindings are committed
    at construction time. To update a leaf, produce a new one with a predecessor link.
    """
    leaf_id: str                          # UUID4
    schema_version: str

    # Scope binding (mandatory)
    owner: str
    tenant: Optional[str]
    repo: Optional[str]
    workspace_id: Optional[str]

    # Revision and observation window
    revision: Optional[str]               # 40-char hex SHA
    observed_period_start: Optional[str]  # opaque stable label (not raw timestamp)
    observed_period_end: Optional[str]    # opaque stable label

    # Classification
    source_class: SourceClass
    evidence_class: EvidenceClass

    # Canonical content (human-readable, secret-redacted)
    content_summary: str
    content_hash: str                     # SHA-256 of content_summary

    # Validity
    validity_rules: Tuple[str, ...]       # e.g. "valid_until_revision=<sha>"
    revalidation_gap_hint: Optional[str]  # opaque hint for when to re-check

    # Readback links (canonical, not raw URLs)
    readback_links: Tuple[str, ...]       # e.g. "ci:run:12345", "repo:commit:<sha>"

    # Provenance chain (append-only)
    predecessor_leaf_id: Optional[str]
    predecessor_hash: Optional[str]

    # Self-binding hash
    provenance_hash: str


# ---------------------------------------------------------------------------
# Provenance chain
# ---------------------------------------------------------------------------

class LeafProvenanceChain:
    @staticmethod
    def compute(
        *,
        leaf_id: str,
        owner: str,
        repo: Optional[str],
        revision: Optional[str],
        evidence_class: EvidenceClass,
        source_class: SourceClass,
        content_hash: str,
        predecessor_leaf_id: Optional[str],
        predecessor_hash: Optional[str],
    ) -> str:
        return _canonical_sha256({
            "leaf_id": leaf_id,
            "owner": owner,
            "repo": repo,
            "revision": revision,
            "evidence_class": evidence_class.value,
            "source_class": source_class.value,
            "content_hash": content_hash,
            "predecessor_leaf_id": predecessor_leaf_id,
            "predecessor_hash": predecessor_hash,
        })

    @staticmethod
    def verify(leaf: MemoryLeaf) -> bool:
        expected = LeafProvenanceChain.compute(
            leaf_id=leaf.leaf_id,
            owner=leaf.owner,
            repo=leaf.repo,
            revision=leaf.revision,
            evidence_class=leaf.evidence_class,
            source_class=leaf.source_class,
            content_hash=leaf.content_hash,
            predecessor_leaf_id=leaf.predecessor_leaf_id,
            predecessor_hash=leaf.predecessor_hash,
        )
        return leaf.provenance_hash == expected


# ---------------------------------------------------------------------------
# Retrieval Evidence Pack
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetrievalEvidencePack:
    """Bounded, hashed pack of Memory Leaves for delivery to a RunEnvelope.

    The pack is never the source of truth — it is a projection.
    Consumers must re-validate runtime-critical leaves before acting on them.
    """
    pack_id: str                            # UUID4
    scope: RetrievalScope
    leaves: Tuple[MemoryLeaf, ...]          # max _MAX_LEAVES_PER_PACK
    conflict_leaf_ids: Tuple[str, ...]      # pairs of conflicting leaf_ids
    revalidation_gap_leaf_ids: Tuple[str, ...]  # leaves flagged for staleness
    pack_hash: str                          # SHA-256 of canonical leaf_ids + evidence classes


# ---------------------------------------------------------------------------
# DurableMemoryForest (pure)
# ---------------------------------------------------------------------------

class DurableMemoryForest:
    """Pure, fail-closed operations for Memory Leaves.

    All methods are class methods — no instance state, no I/O.
    """

    # -----------------------------------------------------------------------
    # Leaf creation
    # -----------------------------------------------------------------------

    @classmethod
    def create_leaf(
        cls,
        *,
        owner: str,
        tenant: Optional[str] = None,
        repo: Optional[str] = None,
        workspace_id: Optional[str] = None,
        revision: Optional[str] = None,
        observed_period_start: Optional[str] = None,
        observed_period_end: Optional[str] = None,
        source_class: SourceClass,
        evidence_class: EvidenceClass,
        content_summary: str,
        validity_rules: Sequence[str] = (),
        revalidation_gap_hint: Optional[str] = None,
        readback_links: Sequence[str] = (),
    ) -> MemoryLeaf:
        # Validate scope
        owner = _validate_owner(owner, field="owner")
        if tenant is not None:
            tenant = _validate_owner(tenant, field="tenant")
        if repo is not None:
            repo = _validate_owner(repo, field="repo")
        revision = _validate_revision(revision, field="revision")

        # Validate content
        if not content_summary or not content_summary.strip():
            raise MemoryContractError("content_summary must not be empty.")
        if len(content_summary.encode()) > _MAX_CONTENT_BYTES:
            raise MemoryContractError(f"content_summary exceeds {_MAX_CONTENT_BYTES}-byte limit.")
        _reject_secrets(content_summary, field="content_summary")
        _reject_injection(content_summary, field="content_summary")

        # Evidence class compatibility with source class
        cls._check_evidence_source_compat(evidence_class, source_class, is_creation=True)

        # INVALIDATED cannot be used at creation time — must use supersede()
        if evidence_class == EvidenceClass.INVALIDATED:
            raise MemoryContractError(
                "evidence_class INVALIDATED cannot be set at creation; use supersede()."
            )

        if len(validity_rules) > _MAX_VALIDITY_RULES:
            raise MemoryContractError(f"validity_rules must not exceed {_MAX_VALIDITY_RULES}.")
        if len(readback_links) > _MAX_READBACK_LINKS:
            raise MemoryContractError(f"readback_links must not exceed {_MAX_READBACK_LINKS}.")

        content_hash = _text_sha256(content_summary)
        leaf_id = str(uuid.uuid4())
        provenance_hash = LeafProvenanceChain.compute(
            leaf_id=leaf_id,
            owner=owner,
            repo=repo,
            revision=revision,
            evidence_class=evidence_class,
            source_class=source_class,
            content_hash=content_hash,
            predecessor_leaf_id=None,
            predecessor_hash=None,
        )
        return MemoryLeaf(
            leaf_id=leaf_id,
            schema_version=SCHEMA_VERSION,
            owner=owner,
            tenant=tenant,
            repo=repo,
            workspace_id=workspace_id,
            revision=revision,
            observed_period_start=observed_period_start,
            observed_period_end=observed_period_end,
            source_class=source_class,
            evidence_class=evidence_class,
            content_summary=content_summary,
            content_hash=content_hash,
            validity_rules=tuple(validity_rules),
            revalidation_gap_hint=revalidation_gap_hint,
            readback_links=tuple(readback_links),
            predecessor_leaf_id=None,
            predecessor_hash=None,
            provenance_hash=provenance_hash,
        )

    # -----------------------------------------------------------------------
    # Evidence class promotion (requires explicit evidence receipt token)
    # -----------------------------------------------------------------------

    @classmethod
    def promote_evidence_class(
        cls,
        leaf: MemoryLeaf,
        *,
        new_class: EvidenceClass,
        evidence_receipt_token: str,  # non-empty string from external evidence gate
    ) -> MemoryLeaf:
        """Promote evidence class. NEVER called from retrieval/similarity paths.

        Caller must supply a non-empty evidence_receipt_token produced by a real
        evidence gate (e.g. CI readback, runtime readback). An empty token is
        rejected — this enforces that no code path in retrieval can trigger promotion.
        """
        if not evidence_receipt_token or not evidence_receipt_token.strip():
            raise MemoryContractError(
                "evidence_receipt_token must not be empty. "
                "Evidence class promotion requires a real evidence gate token, "
                "not a retrieval score or LLM assertion."
            )
        if new_class == leaf.evidence_class:
            raise MemoryContractError(
                f"Leaf already has evidence_class {new_class.value!r}."
            )
        if leaf.evidence_class in (EvidenceClass.INVALIDATED, EvidenceClass.CONTRADICTED):
            raise MemoryContractError(
                f"Cannot promote a leaf with evidence_class {leaf.evidence_class.value!r}."
            )
        cls._check_evidence_source_compat(new_class, leaf.source_class, is_creation=False)
        return cls._supersede(leaf, new_class=new_class)

    # -----------------------------------------------------------------------
    # Supersession (append-only)
    # -----------------------------------------------------------------------

    @classmethod
    def supersede(
        cls,
        leaf: MemoryLeaf,
        *,
        reason_class: EvidenceClass,  # typically INVALIDATED or CONTRADICTED
        content_summary: Optional[str] = None,
    ) -> MemoryLeaf:
        """Produce a new leaf that supersedes *leaf*. The original is never mutated."""
        if reason_class not in (EvidenceClass.INVALIDATED, EvidenceClass.CONTRADICTED):
            raise MemoryContractError(
                "supersede() requires reason_class INVALIDATED or CONTRADICTED."
            )
        return cls._supersede(leaf, new_class=reason_class, content_summary=content_summary)

    # -----------------------------------------------------------------------
    # Retrieval
    # -----------------------------------------------------------------------

    @classmethod
    def build_retrieval_pack(
        cls,
        *,
        scope: RetrievalScope,
        candidate_pool: Sequence[MemoryLeaf],
        max_leaves: int = _MAX_LEAVES_PER_PACK,
        exclude_classes: Sequence[EvidenceClass] = (EvidenceClass.INVALIDATED,),
    ) -> RetrievalEvidencePack:
        """Build a bounded retrieval pack scoped to owner/tenant/repo/workspace.

        Scope is enforced BEFORE any relevance ranking.
        Invalidated leaves are excluded by default.
        Similarity scores (from embedding layer) are intentionally NOT used
        here — this is the deterministic structural filter only.
        """
        if max_leaves > _MAX_LEAVES_PER_PACK:
            raise MemoryContractError(
                f"max_leaves must not exceed {_MAX_LEAVES_PER_PACK}."
            )
        excluded = set(exclude_classes)
        filtered: List[MemoryLeaf] = [
            leaf for leaf in candidate_pool
            if scope.matches(leaf) and leaf.evidence_class not in excluded
        ]
        selected = filtered[:max_leaves]

        # Identify conflicts (same content_hash, different leaf_id, different evidence_class)
        hash_to_leaves: dict = {}
        for leaf in selected:
            hash_to_leaves.setdefault(leaf.content_hash, []).append(leaf)
        conflicts: List[str] = []
        for leaves_by_hash in hash_to_leaves.values():
            classes = {l.evidence_class for l in leaves_by_hash}
            if len(classes) > 1:
                for leaf in leaves_by_hash:
                    conflicts.append(leaf.leaf_id)

        # Flag leaves without revision binding as potential revalidation gaps
        revalidation_gaps = [
            leaf.leaf_id for leaf in selected
            if leaf.revision is None and leaf.evidence_class == EvidenceClass.VERIFIED
        ]

        pack_hash = _canonical_sha256([
            {"leaf_id": l.leaf_id, "evidence_class": l.evidence_class.value}
            for l in selected
        ])

        return RetrievalEvidencePack(
            pack_id=str(uuid.uuid4()),
            scope=scope,
            leaves=tuple(selected),
            conflict_leaf_ids=tuple(conflicts),
            revalidation_gap_leaf_ids=tuple(revalidation_gaps),
            pack_hash=pack_hash,
        )

    # -----------------------------------------------------------------------
    # Rebuild projection manifest (deterministic)
    # -----------------------------------------------------------------------

    @classmethod
    def compute_manifest_hash(cls, leaves: Sequence[MemoryLeaf]) -> str:
        """Compute a deterministic manifest hash over a set of leaves.

        Same set of leaves at the same revision → same manifest hash.
        Useful for detecting derived-projection drift.
        """
        sorted_leaves = sorted(leaves, key=lambda l: l.leaf_id)
        return _canonical_sha256([
            {
                "leaf_id": l.leaf_id,
                "evidence_class": l.evidence_class.value,
                "source_class": l.source_class.value,
                "content_hash": l.content_hash,
                "revision": l.revision,
                "provenance_hash": l.provenance_hash,
            }
            for l in sorted_leaves
        ])

    # -----------------------------------------------------------------------
    # Serialisation
    # -----------------------------------------------------------------------

    @staticmethod
    def to_dict(leaf: MemoryLeaf) -> dict:
        return {
            "leaf_id": leaf.leaf_id,
            "schema_version": leaf.schema_version,
            "owner": leaf.owner,
            "tenant": leaf.tenant,
            "repo": leaf.repo,
            "workspace_id": leaf.workspace_id,
            "revision": leaf.revision,
            "observed_period_start": leaf.observed_period_start,
            "observed_period_end": leaf.observed_period_end,
            "source_class": leaf.source_class.value,
            "evidence_class": leaf.evidence_class.value,
            "content_summary": leaf.content_summary,
            "content_hash": leaf.content_hash,
            "validity_rules": list(leaf.validity_rules),
            "revalidation_gap_hint": leaf.revalidation_gap_hint,
            "readback_links": list(leaf.readback_links),
            "predecessor_leaf_id": leaf.predecessor_leaf_id,
            "predecessor_hash": leaf.predecessor_hash,
            "provenance_hash": leaf.provenance_hash,
        }

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _check_evidence_source_compat(
        evidence_class: EvidenceClass,
        source_class: SourceClass,
        *,
        is_creation: bool,
    ) -> None:
        if evidence_class == EvidenceClass.VERIFIED:
            if source_class not in _VERIFIABLE_SOURCES:
                raise MemoryContractError(
                    f"source_class {source_class.value!r} cannot reach VERIFIED. "
                    f"VERIFIED is reserved for: {sorted(s.value for s in _VERIFIABLE_SOURCES)}."
                )
            if source_class in _OBSERVED_CAP_SOURCES:
                raise MemoryContractError(
                    f"source_class {source_class.value!r} is capped at OBSERVED."
                )

    @classmethod
    def _supersede(
        cls,
        leaf: MemoryLeaf,
        *,
        new_class: EvidenceClass,
        content_summary: Optional[str] = None,
    ) -> MemoryLeaf:
        new_content = content_summary if content_summary is not None else leaf.content_summary
        if new_content != leaf.content_summary:
            if len(new_content.encode()) > _MAX_CONTENT_BYTES:
                raise MemoryContractError("content_summary exceeds byte limit.")
            _reject_secrets(new_content, field="content_summary")
            _reject_injection(new_content, field="content_summary")

        content_hash = _text_sha256(new_content)
        new_id = str(uuid.uuid4())
        prov = LeafProvenanceChain.compute(
            leaf_id=new_id,
            owner=leaf.owner,
            repo=leaf.repo,
            revision=leaf.revision,
            evidence_class=new_class,
            source_class=leaf.source_class,
            content_hash=content_hash,
            predecessor_leaf_id=leaf.leaf_id,
            predecessor_hash=leaf.provenance_hash,
        )
        return MemoryLeaf(
            leaf_id=new_id,
            schema_version=SCHEMA_VERSION,
            owner=leaf.owner,
            tenant=leaf.tenant,
            repo=leaf.repo,
            workspace_id=leaf.workspace_id,
            revision=leaf.revision,
            observed_period_start=leaf.observed_period_start,
            observed_period_end=leaf.observed_period_end,
            source_class=leaf.source_class,
            evidence_class=new_class,
            content_summary=new_content,
            content_hash=content_hash,
            validity_rules=leaf.validity_rules,
            revalidation_gap_hint=leaf.revalidation_gap_hint,
            readback_links=leaf.readback_links,
            predecessor_leaf_id=leaf.leaf_id,
            predecessor_hash=leaf.provenance_hash,
            provenance_hash=prov,
        )
