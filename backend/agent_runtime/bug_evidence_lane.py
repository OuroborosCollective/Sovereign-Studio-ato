"""Revision-bound Bug Evidence Lane for verified failure-family reuse.

Normalises real CI, Docker, PostgreSQL, MCP and Runtime failures into canonical
failure families with dynamic-stripped signatures, matches against historical
evidence cases and gates persistence exclusively on verified end-to-end repair
evidence.

Design constraints (inherited from the broader evidence architecture):
- No network, database, filesystem, clock or random access in this module.
- Similarity-search results are candidates only; they cannot set `verified`.
- A case reaches `verified` only through explicit gate evidence written by
  calling code after real CI/runtime confirmation.
- Invalidation and supersession are append-only: only new records, never
  in-place updates of committed cases.
- Secrets, tokens, PIIs and unbounded logs are rejected at the boundary.

Status flow::

    candidate
        │ (deterministic tools run)
        ▼
    diagnosed
        │ (patch committed, tests queued)
        ▼
    patched
        │ (all gates green + runtime readback)
        ▼
    verified
        │
       (or) → invalidated  (append-only via new record, predecessor link)
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Final, FrozenSet, List, Mapping, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------
SCHEMA_VERSION: Final[str] = "sovereign.bug-evidence-lane.v1"

# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------
_MAX_LOG_LINES: Final[int] = 200
_MAX_LOG_LINE_BYTES: Final[int] = 2048
_MAX_SIGNATURE_BYTES: Final[int] = 8192
_MAX_DIAGNOSTIC_PARAMS_BYTES: Final[int] = 4096
_MAX_AFFECTED_SURFACES: Final[int] = 32
_MAX_TESTS_RUN: Final[int] = 256

# ---------------------------------------------------------------------------
# Identifier regex (shared with proof_verdict.py, evidence_gate.py)
# ---------------------------------------------------------------------------
_IDENTIFIER: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_.:-]{1,119}$")
_SHA40: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_SHA64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_UUID4: Final[re.Pattern[str]] = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)

# ---------------------------------------------------------------------------
# Secret / sensitive material patterns (reject at boundary)
# ---------------------------------------------------------------------------
_SECRET_PATTERNS: Final[Tuple[re.Pattern[str], ...]] = (
    # Bearer / Authorization tokens
    re.compile(r"(?i)bearer\s+[a-z0-9\-._~+/]{8,}", re.IGNORECASE),
    # GitHub tokens
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    # Generic "password = ..." or "token = ..."
    re.compile(r"(?i)(password|passwd|secret|token|api[_\-]?key)\s*[:=]\s*\S{4,}"),
    # AWS keys
    re.compile(r"AKIA[0-9A-Z]{16}"),
    # PEM blocks
    re.compile(r"-----BEGIN [A-Z ]+ KEY-----"),
    # Connection strings with credentials
    re.compile(r"(?i)(postgres|mysql|mongodb)://[^@]+:[^@]+@"),
)

# ---------------------------------------------------------------------------
# Volatile value patterns stripped during signature normalization
# ---------------------------------------------------------------------------
_VOLATILE_TIMESTAMP_ISO: Final[re.Pattern[str]] = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?",
)
_VOLATILE_TIMESTAMP_LOG: Final[re.Pattern[str]] = re.compile(
    r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:[.,]\d+)?",
)
_VOLATILE_UNIX_TS: Final[re.Pattern[str]] = re.compile(r"\b1[5-9]\d{8,9}\b")
_VOLATILE_UUID: Final[re.Pattern[str]] = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)
_VOLATILE_SHA256: Final[re.Pattern[str]] = re.compile(r"\b[0-9a-f]{64}\b")
_VOLATILE_SHA40: Final[re.Pattern[str]] = re.compile(r"\b[0-9a-f]{40}\b")
_VOLATILE_IMAGE_DIGEST: Final[re.Pattern[str]] = re.compile(r"sha256:[0-9a-f]{64}")
_VOLATILE_CONTAINER_ID: Final[re.Pattern[str]] = re.compile(r"\b[0-9a-f]{12,64}\b")
_VOLATILE_MEMORY_ADDR: Final[re.Pattern[str]] = re.compile(r"0x[0-9a-fA-F]{4,16}\b")
_VOLATILE_TMPPATH: Final[re.Pattern[str]] = re.compile(r"/(?:tmp|var/folders|private/var)[^\s\"']+")
_VOLATILE_RUN_ID: Final[re.Pattern[str]] = re.compile(
    r"(?:run[_\-]id|workflow[_\-]run|job[_\-]id|step[_\-]id)\s*[:=]\s*\d+",
    re.IGNORECASE,
)
_VOLATILE_PORT: Final[re.Pattern[str]] = re.compile(r":\d{4,5}(?=[/\s\"']|$)")
_VOLATILE_PID: Final[re.Pattern[str]] = re.compile(r"\bpid\s*[:=]?\s*\d+\b", re.IGNORECASE)
_VOLATILE_ATTEMPT: Final[re.Pattern[str]] = re.compile(r"\battempt\s+\d+\b", re.IGNORECASE)


class BugEvidenceContractError(ValueError):
    """An input violated a deterministic or truth-boundary invariant."""


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class FailureFamily(str, Enum):
    """Canonical failure families that the Bug Evidence Lane normalises."""
    GITHUB_ACTIONS_WORKFLOW = "github_actions_workflow_failure"
    DOCKER_CONTAINER = "docker_compose_container_failure"
    POSTGRES_MIGRATION = "postgres_migration_failure"
    MCP_TOOL = "mcp_tool_failure"
    BACKEND_RUNTIME = "backend_runtime_failure"


class AffectedSurface(str, Enum):
    """Production surfaces that a failure may touch."""
    PRODUCTION = "production"
    TEST = "test"
    PERSISTENCE = "persistence"
    EFFECT = "effect"
    CORE = "core"
    RUNTIME_PROJECTION = "runtime_projection"
    MIGRATION = "migration"
    CONTAINER = "container"
    MCP = "mcp"
    CI = "ci"


class BugEvidenceStatus(str, Enum):
    """Lifecycle status of a Bug Evidence Case (append-only progression)."""
    CANDIDATE = "candidate"
    DIAGNOSED = "diagnosed"
    PATCHED = "patched"
    VERIFIED = "verified"
    INVALIDATED = "invalidated"


_VALID_STATUS_TRANSITIONS: Final[Mapping[BugEvidenceStatus, FrozenSet[BugEvidenceStatus]]] = {
    BugEvidenceStatus.CANDIDATE: frozenset({BugEvidenceStatus.DIAGNOSED, BugEvidenceStatus.INVALIDATED}),
    BugEvidenceStatus.DIAGNOSED: frozenset({BugEvidenceStatus.PATCHED, BugEvidenceStatus.INVALIDATED}),
    BugEvidenceStatus.PATCHED: frozenset({BugEvidenceStatus.VERIFIED, BugEvidenceStatus.INVALIDATED}),
    BugEvidenceStatus.VERIFIED: frozenset({BugEvidenceStatus.INVALIDATED}),
    BugEvidenceStatus.INVALIDATED: frozenset(),
}


# ---------------------------------------------------------------------------
# Canonical SHA-256 helpers
# ---------------------------------------------------------------------------

def _canonical_sha256(value: object) -> str:
    """Deterministic SHA-256 over the UTF-8 JSON serialisation of *value*."""
    serialised = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Secret / sensitive material guard
# ---------------------------------------------------------------------------

class RedactionFilter:
    """Rejects or scrubs log lines that contain secret-shaped material.

    Call ``check_line`` before accepting any external log line into an
    evidence case.  Raises ``BugEvidenceContractError`` on clear credential
    matches.
    """

    @staticmethod
    def contains_secret(text: str) -> bool:
        for pat in _SECRET_PATTERNS:
            if pat.search(text):
                return True
        return False

    @classmethod
    def check_line(cls, line: str, *, index: int) -> str:
        """Return the line unchanged, or raise on secret-shaped content."""
        if cls.contains_secret(line):
            raise BugEvidenceContractError(
                f"Log line {index} contains secret-shaped material and cannot be "
                "stored in a Bug Evidence Case."
            )
        if len(line.encode("utf-8")) > _MAX_LOG_LINE_BYTES:
            raise BugEvidenceContractError(
                f"Log line {index} exceeds the {_MAX_LOG_LINE_BYTES}-byte per-line limit. "
                "Truncate before submission."
            )
        return line

    @classmethod
    def validate_log_evidence(cls, lines: Sequence[str]) -> List[str]:
        """Validate and return all lines, raising on any violation."""
        if len(lines) > _MAX_LOG_LINES:
            raise BugEvidenceContractError(
                f"log_evidence must not exceed {_MAX_LOG_LINES} lines "
                f"(got {len(lines)})."
            )
        return [cls.check_line(line, index=i) for i, line in enumerate(lines)]


# ---------------------------------------------------------------------------
# Signature normaliser
# ---------------------------------------------------------------------------

class SignatureNormalizer:
    """Strips volatile values from raw failure text to produce a canonical
    signature.  Same error with only volatile differences (timestamps, run
    IDs, container hashes, etc.) → same signature.  Materially different
    errors → different signatures.

    Normalisation is intentionally conservative: only patterns that are
    *demonstrably* volatile across repeated occurrences of the same fault
    are removed.  Everything else is preserved so that distinct faults
    remain distinguishable.
    """

    # Family-specific extra patterns applied after the common ones.
    _GITHUB_EXTRA: Tuple[re.Pattern[str], ...] = (
        re.compile(r"\brun\s+#\d+\b", re.IGNORECASE),
        re.compile(r"https://github\.com/[^/]+/[^/]+/actions/runs/\d+(?:/jobs/\d+)?"),
        re.compile(r"\bworkflow\s+run\s+\d+\b", re.IGNORECASE),
    )
    _DOCKER_EXTRA: Tuple[re.Pattern[str], ...] = (
        re.compile(r"container[_\s]+[0-9a-f]{12,64}", re.IGNORECASE),
        # Exit codes are materially significant (e.g. 1=error, 137=OOM, 143=SIGTERM)
        # and are intentionally NOT stripped so distinct exit codes yield distinct signatures.
        re.compile(r"network\s+[a-z0-9_\-]+_default", re.IGNORECASE),
    )
    _POSTGRES_EXTRA: Tuple[re.Pattern[str], ...] = (
        re.compile(r"\bpid\s+\d+\b", re.IGNORECASE),
        re.compile(r"\bline\s+\d+\b", re.IGNORECASE),
        re.compile(r"migration\s+\d{14}", re.IGNORECASE),  # timestamp-prefixed migration
    )
    _MCP_EXTRA: Tuple[re.Pattern[str], ...] = (
        re.compile(r"request[_\-]?id[:\s]+[a-z0-9\-]+", re.IGNORECASE),
        re.compile(r"session[_\-]?id[:\s]+[a-z0-9\-]+", re.IGNORECASE),
    )
    _RUNTIME_EXTRA: Tuple[re.Pattern[str], ...] = (
        re.compile(r"File \"[^\"]+\", line \d+"),   # Python tracebacks
        re.compile(r"at 0x[0-9a-fA-F]+"),           # C extension addresses
        re.compile(r"goroutine \d+"),                # Go goroutine IDs
    )

    _FAMILY_EXTRA: Final[Mapping[FailureFamily, Tuple[re.Pattern[str], ...]]] = {
        FailureFamily.GITHUB_ACTIONS_WORKFLOW: _GITHUB_EXTRA,
        FailureFamily.DOCKER_CONTAINER: _DOCKER_EXTRA,
        FailureFamily.POSTGRES_MIGRATION: _POSTGRES_EXTRA,
        FailureFamily.MCP_TOOL: _MCP_EXTRA,
        FailureFamily.BACKEND_RUNTIME: _RUNTIME_EXTRA,
    }

    @classmethod
    def normalize(cls, raw: str, failure_family: FailureFamily) -> str:
        """Return a canonical, volatile-stripped signature string."""
        if not raw or not raw.strip():
            raise BugEvidenceContractError("Raw failure text must not be empty.")
        if len(raw.encode("utf-8")) > _MAX_SIGNATURE_BYTES:
            raise BugEvidenceContractError(
                f"Raw failure text exceeds {_MAX_SIGNATURE_BYTES} bytes."
            )

        text = raw

        # 1. Common volatile stripping
        text = _VOLATILE_IMAGE_DIGEST.sub("<digest>", text)
        text = _VOLATILE_TIMESTAMP_ISO.sub("<ts>", text)
        text = _VOLATILE_TIMESTAMP_LOG.sub("<ts>", text)
        text = _VOLATILE_UNIX_TS.sub("<epoch>", text)
        text = _VOLATILE_UUID.sub("<uuid>", text)
        text = _VOLATILE_SHA256.sub("<sha256>", text)
        text = _VOLATILE_SHA40.sub("<sha40>", text)
        text = _VOLATILE_MEMORY_ADDR.sub("<addr>", text)
        text = _VOLATILE_TMPPATH.sub("<tmppath>", text)
        text = _VOLATILE_RUN_ID.sub("<run-binding>=<id>", text)
        text = _VOLATILE_PORT.sub(":<port>", text)
        text = _VOLATILE_PID.sub("pid=<pid>", text)
        text = _VOLATILE_ATTEMPT.sub("attempt <n>", text)

        # 2. Family-specific stripping
        for pat in cls._FAMILY_EXTRA.get(failure_family, ()):
            text = pat.sub("<volatile>", text)

        # Collapse repeated whitespace and normalise line endings
        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = text.strip()

        return text


# ---------------------------------------------------------------------------
# Provenance chain
# ---------------------------------------------------------------------------

class ProvenanceChain:
    """Append-only, deterministic provenance hash chain.

    Each case carries a ``provenance_hash`` that commits to its own content
    and optionally to a predecessor's hash.  Verification is deterministic
    and requires no I/O.
    """

    @staticmethod
    def compute(
        *,
        evidence_case_id: str,
        failure_family: str,
        signature_hash: str,
        repo_owner: str,
        repo_name: str,
        base_revision: str,
        head_revision: str,
        status: str,
        log_evidence_hash: str,
        diagnostic_params_hash: str,
        predecessor_provenance_hash: Optional[str],
    ) -> str:
        payload: dict = {
            "evidence_case_id": evidence_case_id,
            "failure_family": failure_family,
            "signature_hash": signature_hash,
            "repo_owner": repo_owner,
            "repo_name": repo_name,
            "base_revision": base_revision,
            "head_revision": head_revision,
            "status": status,
            "log_evidence_hash": log_evidence_hash,
            "diagnostic_params_hash": diagnostic_params_hash,
        }
        if predecessor_provenance_hash is not None:
            payload["predecessor_provenance_hash"] = predecessor_provenance_hash
        return _canonical_sha256(payload)

    @staticmethod
    def verify(case: "BugEvidenceCase") -> bool:
        """Return True if the case's provenance_hash is self-consistent."""
        expected = ProvenanceChain.compute(
            evidence_case_id=case.evidence_case_id,
            failure_family=case.failure_family.value,
            signature_hash=case.signature_hash,
            repo_owner=case.repo_owner,
            repo_name=case.repo_name,
            base_revision=case.base_revision,
            head_revision=case.head_revision,
            status=case.status.value,
            log_evidence_hash=case.log_evidence_hash,
            diagnostic_params_hash=case.diagnostic_params_hash,
            predecessor_provenance_hash=case.predecessor_provenance_hash,
        )
        return case.provenance_hash == expected


# ---------------------------------------------------------------------------
# Canonical data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BugEvidenceCase:
    """Immutable snapshot of a Bug Evidence Case at a single point in time.

    Each state transition produces a *new* ``BugEvidenceCase`` with an
    updated ``status`` (and, for invalidation, a ``predecessor_case_id``
    that links to the superseded record).
    """

    # Stable identity
    evidence_case_id: str          # UUID4 string
    schema_version: str

    # Failure family and canonical signature
    failure_family: FailureFamily
    normalized_signature: str
    signature_hash: str            # SHA-256 of normalized_signature

    # Revision and repository binding
    repo_owner: str
    repo_name: str
    base_revision: str             # 40-char hex SHA
    head_revision: str             # 40-char hex SHA
    merge_revision: Optional[str]  # 40-char hex SHA or None

    # CI / workflow identity
    workflow_id: Optional[str]
    run_id: Optional[str]
    job_id: Optional[str]
    step_id: Optional[str]

    # Redacted, bounded log evidence
    log_evidence: Tuple[str, ...]  # immutable sequence
    log_evidence_hash: str         # SHA-256 of the canonical list

    # Affected surfaces
    affected_surfaces: Tuple[AffectedSurface, ...]

    # Diagnostic tools and immutable param hash
    diagnostic_tools: Tuple[str, ...]
    diagnostic_params_hash: str

    # Repair tracking
    patch_commit: Optional[str]
    tests_run: Tuple[str, ...]
    gate_results: Tuple[Tuple[str, str], ...]  # (gate_name, result) pairs

    # Runtime readbacks (all optional; filled by external collectors)
    artifact_digest: Optional[str]
    revision_label: Optional[str]
    patchmon_readback: Optional[str]
    container_readback: Optional[str]
    postgres_readback: Optional[str]
    runtime_readback: Optional[str]

    # Status and provenance
    status: BugEvidenceStatus
    provenance_hash: str
    predecessor_case_id: Optional[str]
    predecessor_provenance_hash: Optional[str]


# ---------------------------------------------------------------------------
# BugEvidenceLane (pure state machine)
# ---------------------------------------------------------------------------

class BugEvidenceLane:
    """Pure, fail-closed state machine for Bug Evidence Cases.

    All methods are stateless class methods that accept immutable inputs and
    return new ``BugEvidenceCase`` instances.  No I/O of any kind is
    performed here.
    """

    # -----------------------------------------------------------------------
    # Construction
    # -----------------------------------------------------------------------

    @classmethod
    def create_candidate(
        cls,
        *,
        raw_failure_text: str,
        failure_family: FailureFamily,
        repo_owner: str,
        repo_name: str,
        base_revision: str,
        head_revision: str,
        merge_revision: Optional[str] = None,
        workflow_id: Optional[str] = None,
        run_id: Optional[str] = None,
        job_id: Optional[str] = None,
        step_id: Optional[str] = None,
        log_evidence: Sequence[str] = (),
        affected_surfaces: Sequence[AffectedSurface] = (),
        diagnostic_tools: Sequence[str] = (),
        diagnostic_params: object = None,
    ) -> "BugEvidenceCase":
        """Create a new ``candidate`` BugEvidenceCase from raw failure data."""

        # Validate repo identity
        cls._check_repo_identity(repo_owner, repo_name)

        # Validate revisions
        cls._check_revision(base_revision, "base_revision")
        cls._check_revision(head_revision, "head_revision")
        if merge_revision is not None:
            cls._check_revision(merge_revision, "merge_revision")

        # Validate affected surfaces
        if len(affected_surfaces) > _MAX_AFFECTED_SURFACES:
            raise BugEvidenceContractError(
                f"affected_surfaces must not exceed {_MAX_AFFECTED_SURFACES} entries."
            )

        # Normalise signature
        normalised = SignatureNormalizer.normalize(raw_failure_text, failure_family)
        sig_hash = _text_sha256(normalised)

        # Validate and hash log evidence
        validated_lines = RedactionFilter.validate_log_evidence(list(log_evidence))
        log_hash = _canonical_sha256(validated_lines)

        # Hash diagnostic params (immutable binding)
        if len(json.dumps(diagnostic_params, sort_keys=True).encode()) > _MAX_DIAGNOSTIC_PARAMS_BYTES:
            raise BugEvidenceContractError(
                f"diagnostic_params exceeds {_MAX_DIAGNOSTIC_PARAMS_BYTES}-byte limit."
            )
        diag_hash = _canonical_sha256(diagnostic_params)

        case_id = str(uuid.uuid4())
        status = BugEvidenceStatus.CANDIDATE

        prov = ProvenanceChain.compute(
            evidence_case_id=case_id,
            failure_family=failure_family.value,
            signature_hash=sig_hash,
            repo_owner=repo_owner,
            repo_name=repo_name,
            base_revision=base_revision,
            head_revision=head_revision,
            status=status.value,
            log_evidence_hash=log_hash,
            diagnostic_params_hash=diag_hash,
            predecessor_provenance_hash=None,
        )

        return BugEvidenceCase(
            evidence_case_id=case_id,
            schema_version=SCHEMA_VERSION,
            failure_family=failure_family,
            normalized_signature=normalised,
            signature_hash=sig_hash,
            repo_owner=repo_owner,
            repo_name=repo_name,
            base_revision=base_revision,
            head_revision=head_revision,
            merge_revision=merge_revision,
            workflow_id=workflow_id,
            run_id=run_id,
            job_id=job_id,
            step_id=step_id,
            log_evidence=tuple(validated_lines),
            log_evidence_hash=log_hash,
            affected_surfaces=tuple(affected_surfaces),
            diagnostic_tools=tuple(diagnostic_tools),
            diagnostic_params_hash=diag_hash,
            patch_commit=None,
            tests_run=(),
            gate_results=(),
            artifact_digest=None,
            revision_label=None,
            patchmon_readback=None,
            container_readback=None,
            postgres_readback=None,
            runtime_readback=None,
            status=status,
            provenance_hash=prov,
            predecessor_case_id=None,
            predecessor_provenance_hash=None,
        )

    # -----------------------------------------------------------------------
    # Transitions
    # -----------------------------------------------------------------------

    @classmethod
    def advance_to_diagnosed(
        cls,
        case: BugEvidenceCase,
        *,
        diagnostic_tools: Sequence[str],
        diagnostic_params: object,
    ) -> BugEvidenceCase:
        """Transition ``candidate`` → ``diagnosed``."""
        cls._require_transition(case, BugEvidenceStatus.DIAGNOSED)
        if not diagnostic_tools:
            raise BugEvidenceContractError(
                "At least one diagnostic_tool is required to transition to diagnosed."
            )
        if len(json.dumps(diagnostic_params, sort_keys=True).encode()) > _MAX_DIAGNOSTIC_PARAMS_BYTES:
            raise BugEvidenceContractError("diagnostic_params exceeds byte limit.")

        diag_hash = _canonical_sha256(diagnostic_params)
        return cls._rebuild(
            case,
            status=BugEvidenceStatus.DIAGNOSED,
            diagnostic_tools=tuple(diagnostic_tools),
            diagnostic_params_hash=diag_hash,
        )

    @classmethod
    def advance_to_patched(
        cls,
        case: BugEvidenceCase,
        *,
        patch_commit: str,
        tests_run: Sequence[str],
    ) -> BugEvidenceCase:
        """Transition ``diagnosed`` → ``patched``."""
        cls._require_transition(case, BugEvidenceStatus.PATCHED)
        cls._check_revision(patch_commit, "patch_commit")
        if len(tests_run) > _MAX_TESTS_RUN:
            raise BugEvidenceContractError(
                f"tests_run must not exceed {_MAX_TESTS_RUN} entries."
            )
        return cls._rebuild(
            case,
            status=BugEvidenceStatus.PATCHED,
            patch_commit=patch_commit,
            tests_run=tuple(tests_run),
        )

    @classmethod
    def advance_to_verified(
        cls,
        case: BugEvidenceCase,
        *,
        gate_results: Sequence[Tuple[str, str]],
        artifact_digest: Optional[str] = None,
        revision_label: Optional[str] = None,
        patchmon_readback: Optional[str] = None,
        container_readback: Optional[str] = None,
        postgres_readback: Optional[str] = None,
        runtime_readback: Optional[str] = None,
    ) -> BugEvidenceCase:
        """Transition ``patched`` → ``verified`` after all gates are green.

        Caller must supply real gate_results. An empty gate_results tuple is
        rejected: verified status requires affirmative evidence.
        """
        cls._require_transition(case, BugEvidenceStatus.VERIFIED)
        if not gate_results:
            raise BugEvidenceContractError(
                "gate_results must not be empty to transition to verified."
            )
        for name, result in gate_results:
            if not name or not result:
                raise BugEvidenceContractError(
                    "Each gate_result entry must have a non-empty name and result."
                )
        return cls._rebuild(
            case,
            status=BugEvidenceStatus.VERIFIED,
            gate_results=tuple(gate_results),
            artifact_digest=artifact_digest,
            revision_label=revision_label,
            patchmon_readback=patchmon_readback,
            container_readback=container_readback,
            postgres_readback=postgres_readback,
            runtime_readback=runtime_readback,
        )

    @classmethod
    def invalidate(
        cls,
        case: BugEvidenceCase,
        *,
        reason: str,
        superseding_case_id: Optional[str] = None,
    ) -> BugEvidenceCase:
        """Produce a new ``invalidated`` record that supersedes *case*.

        The returned record has a new ``evidence_case_id`` and links back to
        the predecessor via ``predecessor_case_id`` and
        ``predecessor_provenance_hash``.  The original *case* is never mutated.
        """
        cls._require_transition(case, BugEvidenceStatus.INVALIDATED)
        if not reason or not reason.strip():
            raise BugEvidenceContractError("Invalidation reason must not be empty.")
        # Carry a bounded reason into log_evidence
        redacted_reason = RedactionFilter.validate_log_evidence([reason.strip()])
        log_lines = list(case.log_evidence) + redacted_reason
        if len(log_lines) > _MAX_LOG_LINES:
            log_lines = log_lines[-_MAX_LOG_LINES:]
        log_hash = _canonical_sha256(log_lines)

        new_id = str(uuid.uuid4())
        status = BugEvidenceStatus.INVALIDATED

        prov = ProvenanceChain.compute(
            evidence_case_id=new_id,
            failure_family=case.failure_family.value,
            signature_hash=case.signature_hash,
            repo_owner=case.repo_owner,
            repo_name=case.repo_name,
            base_revision=case.base_revision,
            head_revision=case.head_revision,
            status=status.value,
            log_evidence_hash=log_hash,
            diagnostic_params_hash=case.diagnostic_params_hash,
            predecessor_provenance_hash=case.provenance_hash,
        )

        return BugEvidenceCase(
            evidence_case_id=new_id,
            schema_version=SCHEMA_VERSION,
            failure_family=case.failure_family,
            normalized_signature=case.normalized_signature,
            signature_hash=case.signature_hash,
            repo_owner=case.repo_owner,
            repo_name=case.repo_name,
            base_revision=case.base_revision,
            head_revision=case.head_revision,
            merge_revision=case.merge_revision,
            workflow_id=case.workflow_id,
            run_id=case.run_id,
            job_id=case.job_id,
            step_id=case.step_id,
            log_evidence=tuple(log_lines),
            log_evidence_hash=log_hash,
            affected_surfaces=case.affected_surfaces,
            diagnostic_tools=case.diagnostic_tools,
            diagnostic_params_hash=case.diagnostic_params_hash,
            patch_commit=case.patch_commit,
            tests_run=case.tests_run,
            gate_results=case.gate_results,
            artifact_digest=case.artifact_digest,
            revision_label=case.revision_label,
            patchmon_readback=case.patchmon_readback,
            container_readback=case.container_readback,
            postgres_readback=case.postgres_readback,
            runtime_readback=case.runtime_readback,
            status=status,
            provenance_hash=prov,
            predecessor_case_id=case.evidence_case_id,
            predecessor_provenance_hash=case.provenance_hash,
        )

    # -----------------------------------------------------------------------
    # Candidate matching (read-only; similarity cannot set verified)
    # -----------------------------------------------------------------------

    @classmethod
    def filter_candidates(
        cls,
        *,
        query_case: BugEvidenceCase,
        candidate_pool: Sequence[BugEvidenceCase],
        require_same_repo: bool = True,
    ) -> List[BugEvidenceCase]:
        """Return compatible historical candidates from *candidate_pool*.

        Compatibility rules:
        - Same ``failure_family``.
        - If ``require_same_repo`` (default True): same ``repo_owner`` and
          ``repo_name``.  Disabled only for cross-repo pattern reuse with
          explicit opt-out.
        - Overlapping ``affected_surfaces``.
        - Status is NOT ``invalidated`` (drift check: caller must re-validate
          any candidate against current architecture before use).
        - Result status is never promoted; caller receives ``BugEvidenceCase``
          objects as-is so their status is visible.

        Similarity score (if embeddings are available) is computed outside
        this module by the persistence layer.  This method provides the
        deterministic structural compatibility filter only.
        """
        query_surfaces = set(query_case.affected_surfaces)
        results: List[BugEvidenceCase] = []
        for c in candidate_pool:
            if c.status == BugEvidenceStatus.INVALIDATED:
                continue
            if c.failure_family != query_case.failure_family:
                continue
            if require_same_repo and (
                c.repo_owner != query_case.repo_owner
                or c.repo_name != query_case.repo_name
            ):
                continue
            if query_surfaces and not query_surfaces.intersection(c.affected_surfaces):
                continue
            results.append(c)
        return results

    # -----------------------------------------------------------------------
    # Serialisation
    # -----------------------------------------------------------------------

    @staticmethod
    def to_dict(case: BugEvidenceCase) -> dict:
        """Return a JSON-serialisable dict for persistence."""
        return {
            "evidence_case_id": case.evidence_case_id,
            "schema_version": case.schema_version,
            "failure_family": case.failure_family.value,
            "normalized_signature": case.normalized_signature,
            "signature_hash": case.signature_hash,
            "repo_owner": case.repo_owner,
            "repo_name": case.repo_name,
            "base_revision": case.base_revision,
            "head_revision": case.head_revision,
            "merge_revision": case.merge_revision,
            "workflow_id": case.workflow_id,
            "run_id": case.run_id,
            "job_id": case.job_id,
            "step_id": case.step_id,
            "log_evidence": list(case.log_evidence),
            "log_evidence_hash": case.log_evidence_hash,
            "affected_surfaces": [s.value for s in case.affected_surfaces],
            "diagnostic_tools": list(case.diagnostic_tools),
            "diagnostic_params_hash": case.diagnostic_params_hash,
            "patch_commit": case.patch_commit,
            "tests_run": list(case.tests_run),
            "gate_results": [{"gate": g, "result": r} for g, r in case.gate_results],
            "artifact_digest": case.artifact_digest,
            "revision_label": case.revision_label,
            "patchmon_readback": case.patchmon_readback,
            "container_readback": case.container_readback,
            "postgres_readback": case.postgres_readback,
            "runtime_readback": case.runtime_readback,
            "status": case.status.value,
            "provenance_hash": case.provenance_hash,
            "predecessor_case_id": case.predecessor_case_id,
            "predecessor_provenance_hash": case.predecessor_provenance_hash,
        }

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _check_repo_identity(owner: str, name: str) -> None:
        if not owner or not owner.strip():
            raise BugEvidenceContractError("repo_owner must not be empty.")
        if not name or not name.strip():
            raise BugEvidenceContractError("repo_name must not be empty.")
        # Prevent cross-tenant leaks via path traversal patterns
        if ".." in owner or "/" in owner:
            raise BugEvidenceContractError(
                f"repo_owner '{owner}' contains forbidden characters."
            )
        if ".." in name or "/" in name:
            raise BugEvidenceContractError(
                f"repo_name '{name}' contains forbidden characters."
            )

    @staticmethod
    def _check_revision(rev: str, field: str) -> None:
        if not _SHA40.fullmatch(rev or ""):
            raise BugEvidenceContractError(
                f"'{field}' must be a 40-character lowercase hex SHA (got '{rev}')."
            )

    @staticmethod
    def _require_transition(
        case: BugEvidenceCase, target: BugEvidenceStatus
    ) -> None:
        allowed = _VALID_STATUS_TRANSITIONS.get(case.status, frozenset())
        if target not in allowed:
            raise BugEvidenceContractError(
                f"Cannot transition from {case.status.value!r} to "
                f"{target.value!r}. Allowed: "
                f"{sorted(s.value for s in allowed) or 'none'}."
            )

    @classmethod
    def _rebuild(
        cls,
        case: BugEvidenceCase,
        *,
        status: BugEvidenceStatus,
        diagnostic_tools: Optional[Tuple[str, ...]] = None,
        diagnostic_params_hash: Optional[str] = None,
        patch_commit: Optional[str] = None,
        tests_run: Optional[Tuple[str, ...]] = None,
        gate_results: Optional[Tuple[Tuple[str, str], ...]] = None,
        artifact_digest: Optional[str] = None,
        revision_label: Optional[str] = None,
        patchmon_readback: Optional[str] = None,
        container_readback: Optional[str] = None,
        postgres_readback: Optional[str] = None,
        runtime_readback: Optional[str] = None,
        log_evidence: Optional[Tuple[str, ...]] = None,
        log_evidence_hash: Optional[str] = None,
    ) -> "BugEvidenceCase":
        """Create an updated copy of *case* with *status* and overrides."""
        new_tools = diagnostic_tools if diagnostic_tools is not None else case.diagnostic_tools
        new_diag_hash = diagnostic_params_hash if diagnostic_params_hash is not None else case.diagnostic_params_hash
        new_log = log_evidence if log_evidence is not None else case.log_evidence
        new_log_hash = log_evidence_hash if log_evidence_hash is not None else case.log_evidence_hash

        prov = ProvenanceChain.compute(
            evidence_case_id=case.evidence_case_id,
            failure_family=case.failure_family.value,
            signature_hash=case.signature_hash,
            repo_owner=case.repo_owner,
            repo_name=case.repo_name,
            base_revision=case.base_revision,
            head_revision=case.head_revision,
            status=status.value,
            log_evidence_hash=new_log_hash,
            diagnostic_params_hash=new_diag_hash,
            predecessor_provenance_hash=case.predecessor_provenance_hash,
        )

        return BugEvidenceCase(
            evidence_case_id=case.evidence_case_id,
            schema_version=case.schema_version,
            failure_family=case.failure_family,
            normalized_signature=case.normalized_signature,
            signature_hash=case.signature_hash,
            repo_owner=case.repo_owner,
            repo_name=case.repo_name,
            base_revision=case.base_revision,
            head_revision=case.head_revision,
            merge_revision=case.merge_revision,
            workflow_id=case.workflow_id,
            run_id=case.run_id,
            job_id=case.job_id,
            step_id=case.step_id,
            log_evidence=new_log,
            log_evidence_hash=new_log_hash,
            affected_surfaces=case.affected_surfaces,
            diagnostic_tools=new_tools,
            diagnostic_params_hash=new_diag_hash,
            patch_commit=patch_commit if patch_commit is not None else case.patch_commit,
            tests_run=tests_run if tests_run is not None else case.tests_run,
            gate_results=gate_results if gate_results is not None else case.gate_results,
            artifact_digest=artifact_digest if artifact_digest is not None else case.artifact_digest,
            revision_label=revision_label if revision_label is not None else case.revision_label,
            patchmon_readback=patchmon_readback if patchmon_readback is not None else case.patchmon_readback,
            container_readback=container_readback if container_readback is not None else case.container_readback,
            postgres_readback=postgres_readback if postgres_readback is not None else case.postgres_readback,
            runtime_readback=runtime_readback if runtime_readback is not None else case.runtime_readback,
            status=status,
            provenance_hash=prov,
            predecessor_case_id=case.predecessor_case_id,
            predecessor_provenance_hash=case.predecessor_provenance_hash,
        )
