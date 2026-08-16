"""Privacy-minimized Agent Execution Transparency statement (SVET 1/5, Issue #1485).

Derives a canonical, externally exportable transparency statement from an
already-verified internal Sovereign receipt chain. This module owns no effect
truth and no second receipt chain: the statement is a strict projection of
:mod:`agent_runtime.agent_run_receipts`. The internal chain must already have
passed :func:`agent_runtime.agent_run_receipts.verify_agent_run_receipt_chain`
before a statement can be produced.

Privacy / secret safety
-----------------------
The exported statement never carries raw prompts, chain-of-thought, source-code
contents, database rows, access tokens / PATs / API keys, provider answers, full
tool outputs, secrets or PII. Only identity hashes and bounded effect metadata
survive the projection. The raw ``operation_identity`` is hashed before export,
just like ``agent_run_id``, so the internal receipt's free-form string cannot leak
a secret or PII value through a key-safe field. The canonicalization and
secret-safety logic is reused from ``agent_run_receipts`` (``canonical_value`` /
``canonical_sha256``); it is not copied. Any secret-shaped field that attempts to
enter the statement body fails closed via
:class:`agent_runtime.agent_run_receipts.ReceiptContractError`.

Canonicalization
----------------
- UTF-8 NFC, deterministically sorted JSON, no floats / NaN / Infinity.
- SHA-40 / SHA-256 / image-digest fields are strictly validated before mapping.
- Timestamps are metadata only and never enter the statement hash.
- Field ordering does not affect the statement hash (sorted keys).

This lane has no external registration or signature effect.
"""

from __future__ import annotations

from dataclasses import dataclass, fields as dataclass_fields
import hashlib
from typing import Any, Final, Literal, Mapping, Sequence

from agent_runtime.agent_run_receipts import (
    ReceiptContractError,
    _IMAGE_DIGEST,
    _SHA40,
    _SHA64,
    _ZERO_SHA256,
    _normalize_string,
    canonical_sha256,
    verify_agent_run_receipt_chain,
)

STATEMENT_SCHEMA_VERSION: Final[str] = "sovereign.agent-execution-transparency-statement.v1"

# Bounded effect classes admitted by the statement contract. A receipt whose
# observed effect is ``none`` cannot produce a transparency statement, because a
# transparency statement records a material agent effect.
_EFFECT_CLASSES: Final[frozenset[str]] = frozenset({"read", "workspace-write", "external-write"})
_GATE_RESULTS: Final[frozenset[str]] = frozenset({"PASS", "FAIL", "BLOCKED"})

# The set of source fields deliberately excluded from the external projection.
# This is a fixed declaration, not a dynamically discovered redaction list: it
# documents exactly what is never exported, independent of any single receipt.
REDACTED_FIELDS: Final[tuple[str, ...]] = (
    "raw_prompt",
    "chain_of_thought",
    "source_code_content",
    "database_row",
    "access_token",
    "personal_access_token",
    "api_key",
    "provider_response",
    "full_tool_output",
    "file_content",
    "secret",
    "personally_identifiable_information",
)


class TransparencyBlocked(RuntimeError):
    """No transparency statement could be derived from the available evidence.

    Raised whenever the internal receipt chain is invalid, an identity field is
    missing or unverifiable, or a privacy invariant would be violated. Producing
    no statement is always preferred over producing a partial or unsafe one.
    """

    def __init__(self, failure_family: str, detail: str = "") -> None:
        super().__init__(detail or failure_family)
        self.failure_family = failure_family
        self.detail = detail or failure_family


@dataclass(frozen=True, slots=True)
class AgentExecutionTransparencyStatement:
    """Canonical, privacy-minimized projection of one verified agent effect."""

    schema_version: str
    repository: str
    repository_revision: str
    agent_run_id_sha256: str
    internal_receipt_sha256: str
    previous_internal_receipt_sha256: str
    runtime_revision: str | None
    runtime_image_digest: str | None
    operation_identity: str
    effect_class: Literal["read", "workspace-write", "external-write"]
    input_sha256: str
    output_sha256: str
    mutation_sha256: str
    authoritative_readback_sha256: str
    evidence_gate_result: Literal["PASS", "FAIL", "BLOCKED"]
    redacted_fields: tuple[str, ...]
    statement_sha256: str

    def as_canonical_dict(self) -> dict[str, Any]:
        """Return the canonical, JSON-safe projection (without recomputing the hash).

        The returned mapping is already canonicalized and is safe to export. It
        does not include ``statement_sha256`` revalidation; callers needing a
        tamper check should recompute via :func:`statement_sha256`.
        """

        # Preserve declaration order; canonical_sha256 sorts keys regardless.
        result: dict[str, Any] = {}
        for field in dataclass_fields(self):
            value = getattr(self, field.name)
            if isinstance(value, tuple):
                value = list(value)
            result[field.name] = value
        return result


def _require_sha64(value: Any, label: str) -> str:
    digest = str(value or "").strip().lower()
    if not _SHA64.fullmatch(digest):
        raise TransparencyBlocked("IDENTITY_DIGEST_INVALID", f"{label} must be a lowercase SHA-256")
    return digest


def _hash_agent_run_id(agent_run_id: str) -> str:
    """Hash the internal agent run id so the raw id never leaves the boundary."""

    normalized = _normalize_string(str(agent_run_id or "").strip())
    if not normalized:
        raise TransparencyBlocked("AGENT_RUN_ID_MISSING", "agent run id is required for the statement")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _hash_operation_identity(operation_identity: str) -> str:
    """Hash the free-form internal operation identity before public projection.

    ``agent_run_receipts`` deliberately permits ``operation_identity`` as a
    canonical string and its secret guard rejects secret-shaped *keys*, not
    arbitrary string values. Exporting that string verbatim would therefore make
    the privacy claim stronger than the actual contract. The external statement
    keeps only its deterministic SHA-256 identity.
    """

    normalized = _normalize_string(str(operation_identity or "").strip())
    if not normalized:
        raise TransparencyBlocked("OPERATION_IDENTITY_MISSING", "operation identity is required for the statement")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _optional_identity(value: Any, pattern: Any, family: str) -> str | None:
    """Return a normalized, pattern-validated identity, or ``None`` when absent.

    A non-empty value that fails its pattern fails closed. An empty value maps to
    ``None`` (statements for non-positive receipts may legitimately omit runtime
    identity).
    """

    text = str(value or "").strip().lower()
    if not text:
        return None
    if not pattern.fullmatch(text):
        raise TransparencyBlocked(family, f"identity field failed pattern validation: {text[:32]}")
    return text


def statement_body(statement: AgentExecutionTransparencyStatement) -> dict[str, Any]:
    """Canonical mapping over which the statement hash is computed.

    ``statement_sha256`` itself is excluded so the hash is a pure function of the
    statement's content, not of its own digest.
    """

    return {
        "schema_version": statement.schema_version,
        "repository": statement.repository,
        "repository_revision": statement.repository_revision,
        "agent_run_id_sha256": statement.agent_run_id_sha256,
        "internal_receipt_sha256": statement.internal_receipt_sha256,
        "previous_internal_receipt_sha256": statement.previous_internal_receipt_sha256,
        "runtime_revision": statement.runtime_revision,
        "runtime_image_digest": statement.runtime_image_digest,
        "operation_identity": statement.operation_identity,
        "effect_class": statement.effect_class,
        "input_sha256": statement.input_sha256,
        "output_sha256": statement.output_sha256,
        "mutation_sha256": statement.mutation_sha256,
        "authoritative_readback_sha256": statement.authoritative_readback_sha256,
        "evidence_gate_result": statement.evidence_gate_result,
        "redacted_fields": list(statement.redacted_fields),
    }


def statement_sha256(statement: AgentExecutionTransparencyStatement) -> str:
    """Deterministic SHA-256 over the canonical statement body.

    Reuses ``canonical_sha256`` from ``agent_run_receipts`` so the same
    canonicalization (UTF-8 NFC, sorted keys, no floats, secret-shaped key
    rejection) governs the statement hash. This is also the fail-closed gate:
    any caller that injects a secret-shaped field into the body raises
    :class:`agent_runtime.agent_run_receipts.ReceiptContractError`.
    """

    return canonical_sha256(statement_body(statement))


def privacy_minimized_statement(
    receipt: Mapping[str, Any],
    verdict: Mapping[str, Any],
) -> AgentExecutionTransparencyStatement:
    """Project one verified receipt into a privacy-minimized statement.

    ``receipt`` is the final (chain head) receipt mapping as emitted by
    :func:`agent_runtime.agent_run_receipts.build_agent_run_receipt`, and
    ``verdict`` is the successful result of
    :func:`agent_runtime.agent_run_receipts.verify_agent_run_receipt_chain` for
    the chain ending in ``receipt``. The caller is responsible for having already
    verified the chain; this function re-checks the head identity and applies the
    privacy / effect-readback invariants before producing a statement.
    """

    if not verdict.get("ok"):
        raise TransparencyBlocked("INTERNAL_RECEIPT_CHAIN_INVALID", "internal receipt chain did not verify")

    body = dict(receipt.get("body") or {})
    header = dict(receipt.get("header") or {})
    stored_hash = str(header.get("hash") or "").strip().lower()
    chain_head = str(verdict.get("chain_head_sha256") or "").strip().lower()

    # Re-assert the head identity against the verified verdict. A receipt whose
    # stored hash disagrees with the verified chain head cannot be projected.
    if not _SHA64.fullmatch(stored_hash):
        raise TransparencyBlocked("INTERNAL_RECEIPT_HASH_INVALID", "internal receipt hash is not a SHA-256")
    if stored_hash != chain_head:
        raise TransparencyBlocked("INTERNAL_RECEIPT_HEAD_MISMATCH", "receipt is not the verified chain head")

    repository = _normalize_string(str(body.get("repository") or "").strip())
    if not repository:
        raise TransparencyBlocked("REPOSITORY_MISSING", "receipt repository identity is missing")

    repository_revision = str(body.get("base_commit_sha") or "").strip().lower()
    if not _SHA40.fullmatch(repository_revision):
        raise TransparencyBlocked("REPOSITORY_REVISION_INVALID", "repository revision is not a full Git SHA")

    effect = str(body.get("observed_effect") or "").strip().lower()
    if effect not in _EFFECT_CLASSES:
        # A receipt with effect ``none`` (or any unknown effect) records no
        # material agent effect and therefore cannot yield a transparency
        # statement.
        raise TransparencyBlocked("UNSUPPORTED_EFFECT_FOR_STATEMENT", f"observed effect '{effect}' is not a material effect class")

    gate = str(body.get("evidence_gate_result") or "").strip().upper()
    if gate not in _GATE_RESULTS:
        raise TransparencyBlocked("EVIDENCE_GATE_RESULT_INVALID", f"evidence gate result '{gate}' is not supported")

    input_sha256 = _require_sha64(body.get("input_sha256"), "input_sha256")
    output_sha256 = _require_sha64(body.get("output_sha256"), "output_sha256")
    mutation_sha256 = _require_sha64(body.get("diff_sha256"), "diff_sha256")
    authoritative_readback_sha256 = _require_sha64(body.get("authoritative_readback_sha256"), "authoritative_readback_sha256")
    previous_internal_receipt_sha256 = _require_sha64(body.get("previous_receipt_sha256"), "previous_receipt_sha256")

    runtime_revision = _optional_identity(body.get("mcp_revision"), _SHA40, "RUNTIME_REVISION_INVALID")
    runtime_image_digest = _optional_identity(body.get("mcp_image_digest"), _IMAGE_DIGEST, "RUNTIME_IMAGE_DIGEST_INVALID")

    # Positive external effect requires an authoritative target-system readback
    # that is not the genesis zero anchor. Without it, no positive statement
    # status is produced for the external effect.
    if effect == "external-write" and gate == "PASS":
        if authoritative_readback_sha256 == _ZERO_SHA256:
            raise TransparencyBlocked(
                "AUTHORITATIVE_READBACK_MISSING_FOR_EXTERNAL_EFFECT",
                "positive external-write effect requires a non-zero authoritative readback",
            )
        if runtime_revision is None or runtime_image_digest is None:
            raise TransparencyBlocked(
                "RUNTIME_IDENTITY_MISSING_FOR_POSITIVE_EFFECT",
                "positive effect requires a verified runtime revision and image digest",
            )

    agent_run_id_sha256 = _hash_agent_run_id(body.get("agent_run_id"))
    operation_identity = _hash_operation_identity(body.get("operation_identity"))

    statement = AgentExecutionTransparencyStatement(
        schema_version=STATEMENT_SCHEMA_VERSION,
        repository=repository,
        repository_revision=repository_revision,
        agent_run_id_sha256=agent_run_id_sha256,
        internal_receipt_sha256=stored_hash,
        previous_internal_receipt_sha256=previous_internal_receipt_sha256,
        runtime_revision=runtime_revision,
        runtime_image_digest=runtime_image_digest,
        operation_identity=operation_identity,
        effect_class=effect,  # type: ignore[arg-type]
        input_sha256=input_sha256,
        output_sha256=output_sha256,
        mutation_sha256=mutation_sha256,
        authoritative_readback_sha256=authoritative_readback_sha256,
        evidence_gate_result=gate,  # type: ignore[arg-type]
        redacted_fields=REDACTED_FIELDS,
        statement_sha256="",
    )

    digest = statement_sha256(statement)
    return AgentExecutionTransparencyStatement(
        schema_version=statement.schema_version,
        repository=statement.repository,
        repository_revision=statement.repository_revision,
        agent_run_id_sha256=statement.agent_run_id_sha256,
        internal_receipt_sha256=statement.internal_receipt_sha256,
        previous_internal_receipt_sha256=statement.previous_internal_receipt_sha256,
        runtime_revision=statement.runtime_revision,
        runtime_image_digest=statement.runtime_image_digest,
        operation_identity=statement.operation_identity,
        effect_class=statement.effect_class,
        input_sha256=statement.input_sha256,
        output_sha256=statement.output_sha256,
        mutation_sha256=statement.mutation_sha256,
        authoritative_readback_sha256=statement.authoritative_readback_sha256,
        evidence_gate_result=statement.evidence_gate_result,
        redacted_fields=statement.redacted_fields,
        statement_sha256=digest,
    )


def build_transparency_statement(
    receipt_chain: Sequence[Mapping[str, Any]],
    expected_repository: str,
    expected_revision: str,
) -> AgentExecutionTransparencyStatement:
    """Verify the internal chain, then derive the privacy-minimized statement.

    Implements the issue's mapping rule: the statement may only originate from a
    chain that already passed ``verify_agent_run_receipt_chain`` against the
    expected repository and revision. No LLM decides admission or truth status.
    """

    if not receipt_chain:
        raise TransparencyBlocked("EMPTY_RECEIPT_CHAIN", "at least one receipt is required")

    try:
        verdict = verify_agent_run_receipt_chain(
            receipt_chain,
            expected_repository=expected_repository,
            expected_base_commit_sha=expected_revision,
        )
    except ReceiptContractError as exc:
        raise TransparencyBlocked("INTERNAL_RECEIPT_CHAIN_INVALID", str(exc)) from exc

    if not verdict["ok"]:
        families = sorted({str(item.get("family")) for item in verdict.get("findings") or []})
        raise TransparencyBlocked("INTERNAL_RECEIPT_CHAIN_INVALID", "chain findings: " + ",".join(families))

    return privacy_minimized_statement(receipt_chain[-1], verdict)