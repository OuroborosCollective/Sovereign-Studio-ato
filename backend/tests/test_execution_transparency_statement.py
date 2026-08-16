"""Tests for the privacy-minimized Agent Execution Transparency statement lane.

Covers Issue #1485 (SVET 1/5). The statement must be a strict, privacy-minimized
projection of an already-verified internal receipt chain produced by
``agent_runtime.agent_run_receipts``. No new truth layer, no second chain, no
external registration. These tests exercise the real live-path implementation.
"""

import os
import sys

# Match the proven import style of test_agent_pattern_gateway.py: insert the
# backend directory so both ``agent_runtime`` (flat) and its stdlib-only
# collaborators resolve when pytest is run from the repository root in CI.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from agent_runtime.agent_run_receipts import (  # noqa: E402
    ReceiptContractError,
    build_agent_run_receipt,
)
from agent_runtime.execution_transparency.statement import (  # noqa: E402
    REDACTED_FIELDS,
    STATEMENT_SCHEMA_VERSION,
    AgentExecutionTransparencyStatement,
    TransparencyBlocked,
    build_transparency_statement,
    privacy_minimized_statement,
    statement_body,
    statement_sha256,
)


REVISION = "a" * 40
MCP_REVISION = "c" * 40
IMAGE_DIGEST = "sha256:" + "b" * 64
ZERO_SHA256 = "0" * 64
SHA_A = "1" * 64
SHA_B = "2" * 64
SHA_C = "3" * 64
SHA_D = "4" * 64
SHA_E = "5" * 64
REPO = "OuroborosCollective/Sovereign-Studio-ato"


def _genesis_receipt(**overrides) -> dict:
    """Build one valid genesis receipt with sane, verifiable defaults."""

    defaults = dict(
        sequence=0,
        repository=REPO,
        base_commit_sha=REVISION,
        mcp_revision=MCP_REVISION,
        mcp_image_digest=IMAGE_DIGEST,
        mcp_revision_verified=True,
        agent_run_id="run-1",
        tool_name="apply_patch",
        call_id="call-1",
        operation_identity="apply_patch:src/x.ts",
        input_sha256=SHA_A,
        output_sha256=SHA_B,
        diff_sha256=SHA_C,
        test_evidence_sha256=ZERO_SHA256,
        evidence_gate_result="PASS",
        mutation_performed=True,
        observed_effect="workspace-write",
        authoritative_readback_sha256=SHA_D,
        previous_receipt_sha256=ZERO_SHA256,
    )
    defaults.update(overrides)
    return build_agent_run_receipt(**defaults)


def _next_receipt(prev_receipt: dict, **overrides) -> dict:
    prev_hash = prev_receipt["body"]["receipt_sha256"]
    defaults = dict(
        sequence=1,
        repository=REPO,
        base_commit_sha=REVISION,
        mcp_revision=MCP_REVISION,
        mcp_image_digest=IMAGE_DIGEST,
        mcp_revision_verified=True,
        agent_run_id="run-2",
        tool_name="apply_patch",
        call_id="call-2",
        operation_identity="apply_patch:src/y.ts",
        input_sha256=SHA_E,
        output_sha256=SHA_A,
        diff_sha256=SHA_B,
        test_evidence_sha256=ZERO_SHA256,
        evidence_gate_result="PASS",
        mutation_performed=True,
        observed_effect="workspace-write",
        authoritative_readback_sha256=SHA_C,
        previous_receipt_sha256=prev_hash,
    )
    defaults.update(overrides)
    return build_agent_run_receipt(**defaults)


def _build_ok_chain() -> list[dict]:
    r0 = _genesis_receipt()
    r1 = _next_receipt(r0)
    return [r0, r1]


# --- Happy path ---------------------------------------------------------------


def test_build_transparency_statement_from_verified_chain():
    chain = _build_ok_chain()
    statement = build_transparency_statement(chain, expected_repository=REPO, expected_revision=REVISION)

    assert isinstance(statement, AgentExecutionTransparencyStatement)
    assert statement.schema_version == STATEMENT_SCHEMA_VERSION
    assert statement.repository == REPO
    assert statement.repository_revision == REVISION
    assert statement.effect_class == "workspace-write"
    assert statement.evidence_gate_result == "PASS"
    # The statement projects the chain head receipt.
    assert statement.internal_receipt_sha256 == chain[-1]["header"]["hash"]
    assert statement.previous_internal_receipt_sha256 == chain[-2]["header"]["hash"]
    # Runtime identity is carried as bounded, verifiable identity, never raw.
    assert statement.runtime_revision == MCP_REVISION
    assert statement.runtime_image_digest == IMAGE_DIGEST
    # agent_run_id is hashed, never exported raw.
    assert statement.agent_run_id_sha256 != "run-2"
    assert len(statement.agent_run_id_sha256) == 64
    assert statement.statement_sha256
    assert len(statement.statement_sha256) == 64


def test_statement_hash_recomputed_matches_stored():
    chain = _build_ok_chain()
    statement = build_transparency_statement(chain, expected_repository=REPO, expected_revision=REVISION)
    assert statement_sha256(statement) == statement.statement_sha256
    # statement_body excludes the hash itself.
    assert "statement_sha256" not in statement_body(statement)


# --- Determinism: identical receipt -> identical statement hash ---------------


def test_identical_receipt_produces_identical_statement_hash():
    chain_a = _build_ok_chain()
    chain_b = _build_ok_chain()
    sa = build_transparency_statement(chain_a, expected_repository=REPO, expected_revision=REVISION)
    sb = build_transparency_statement(chain_b, expected_repository=REPO, expected_revision=REVISION)
    assert sa.statement_sha256 == sb.statement_sha256


# --- Identity/evidence changes change the hash -------------------------------


def test_changed_repository_revision_changes_hash():
    chain = _build_ok_chain()
    base = build_transparency_statement(chain, expected_repository=REPO, expected_revision=REVISION)
    other_revision = ("b" * 39 + "a")  # different 40-hex SHA
    g0 = _genesis_receipt(base_commit_sha=other_revision, mcp_revision=other_revision)
    chain2 = [g0, _next_receipt(g0, base_commit_sha=other_revision, mcp_revision=other_revision)]
    changed = build_transparency_statement(chain2, expected_repository=REPO, expected_revision=other_revision)
    assert base.statement_sha256 != changed.statement_sha256
    assert changed.repository_revision == other_revision


def test_changed_effect_changes_hash():
    chain = _build_ok_chain()
    base = build_transparency_statement(chain, expected_repository=REPO, expected_revision=REVISION)
    g0 = _genesis_receipt(observed_effect="read", mutation_performed=False)
    chain_read = [g0, _next_receipt(g0, observed_effect="read", mutation_performed=False)]
    changed = build_transparency_statement(chain_read, expected_repository=REPO, expected_revision=REVISION)
    assert base.statement_sha256 != changed.statement_sha256
    assert changed.effect_class == "read"


def test_changed_input_output_mutation_readback_each_change_hash():
    chain = _build_ok_chain()
    base = build_transparency_statement(chain, expected_repository=REPO, expected_revision=REVISION)

    def rebuild_head(**head_overrides):
        return build_transparency_statement(
            [chain[0], _next_receipt(chain[0], **head_overrides)],
            expected_repository=REPO, expected_revision=REVISION,
        )

    assert rebuild_head(input_sha256=SHA_B).statement_sha256 != base.statement_sha256
    assert rebuild_head(output_sha256=SHA_C).statement_sha256 != base.statement_sha256
    assert rebuild_head(diff_sha256=SHA_D).statement_sha256 != base.statement_sha256
    assert rebuild_head(authoritative_readback_sha256=SHA_E).statement_sha256 != base.statement_sha256


def test_changed_operation_identity_changes_hash():
    chain = _build_ok_chain()
    base = build_transparency_statement(chain, expected_repository=REPO, expected_revision=REVISION)
    chain_op = [chain[0], _next_receipt(chain[0], operation_identity="apply_patch:src/z.ts")]
    changed = build_transparency_statement(chain_op, expected_repository=REPO, expected_revision=REVISION)
    assert base.statement_sha256 != changed.statement_sha256


def test_changed_agent_run_id_changes_hash():
    chain = _build_ok_chain()
    base = build_transparency_statement(chain, expected_repository=REPO, expected_revision=REVISION)
    chain_id = [chain[0], _next_receipt(chain[0], agent_run_id="run-99")]
    changed = build_transparency_statement(chain_id, expected_repository=REPO, expected_revision=REVISION)
    assert base.statement_sha256 != changed.statement_sha256
    # Different raw id -> different hash, but neither exposes the raw id.
    assert changed.agent_run_id_sha256 != base.agent_run_id_sha256
    assert "run-99" not in changed.agent_run_id_sha256


# --- Invalid internal chain -> no statement ----------------------------------


def test_invalid_internal_chain_blocks_statement():
    chain = _build_ok_chain()
    # Tamper with the head body hash, breaking the canonical hash invariant.
    tampered = {
        "header": dict(chain[-1]["header"]),
        "body": {**chain[-1]["body"], "operation_identity": "apply_patch:TAMPERED"},
    }
    try:
        build_transparency_statement([chain[0], tampered], expected_repository=REPO, expected_revision=REVISION)
        raise AssertionError("tampered chain must not produce a statement")
    except TransparencyBlocked as exc:
        assert exc.failure_family == "INTERNAL_RECEIPT_CHAIN_INVALID"


def test_manipulated_internal_receipt_blocks_statement():
    chain = _build_ok_chain()
    # Break the chain link by claiming a wrong previous hash on the head receipt.
    orphan = _next_receipt(chain[0], previous_receipt_sha256="f" * 64)
    try:
        build_transparency_statement([chain[0], orphan], expected_repository=REPO, expected_revision=REVISION)
        raise AssertionError("broken chain link must not produce a statement")
    except TransparencyBlocked as exc:
        assert exc.failure_family == "INTERNAL_RECEIPT_CHAIN_INVALID"


def test_other_repository_revision_blocks_statement():
    chain = _build_ok_chain()
    try:
        build_transparency_statement(chain, expected_repository=REPO, expected_revision="b" * 40)
        raise AssertionError("mismatched revision must not produce a statement")
    except TransparencyBlocked as exc:
        assert exc.failure_family == "INTERNAL_RECEIPT_CHAIN_INVALID"


def test_empty_chain_blocks_statement():
    try:
        build_transparency_statement([], expected_repository=REPO, expected_revision=REVISION)
        raise AssertionError("empty chain must not produce a statement")
    except TransparencyBlocked as exc:
        assert exc.failure_family == "EMPTY_RECEIPT_CHAIN"


# --- Positive external effect requires authoritative readback ----------------


def test_positive_external_write_requires_nonzero_readback():
    chain = _build_ok_chain()
    chain_ext = [chain[0], _next_receipt(chain[0], observed_effect="external-write", authoritative_readback_sha256=ZERO_SHA256)]
    try:
        build_transparency_statement(chain_ext, expected_repository=REPO, expected_revision=REVISION)
        raise AssertionError("positive external effect without readback must not produce a statement")
    except TransparencyBlocked as exc:
        assert exc.failure_family == "AUTHORITATIVE_READBACK_MISSING_FOR_EXTERNAL_EFFECT"


def test_positive_external_write_with_readback_succeeds():
    chain = _build_ok_chain()
    chain_ext = [chain[0], _next_receipt(chain[0], observed_effect="external-write", authoritative_readback_sha256=SHA_E)]
    statement = build_transparency_statement(chain_ext, expected_repository=REPO, expected_revision=REVISION)
    assert statement.effect_class == "external-write"
    assert statement.evidence_gate_result == "PASS"


# --- Effect `none` cannot produce a statement --------------------------------


def test_no_effect_receipt_cannot_produce_statement():
    chain = _build_ok_chain()
    chain_none = [chain[0], _next_receipt(chain[0], observed_effect="none", mutation_performed=False)]
    try:
        build_transparency_statement(chain_none, expected_repository=REPO, expected_revision=REVISION)
        raise AssertionError("effect 'none' must not produce a statement")
    except TransparencyBlocked as exc:
        assert exc.failure_family == "UNSUPPORTED_EFFECT_FOR_STATEMENT"


# --- Privacy / secret safety -------------------------------------------------


def test_secret_shaped_field_fails_closed_on_canonicalization():
    chain = _build_ok_chain()
    statement = build_transparency_statement(chain, expected_repository=REPO, expected_revision=REVISION)
    body = statement_body(statement)
    # Injecting a secret-shaped field into the canonical body must fail closed
    # via the shared canonicalization, exactly as receipts do.
    try:
        statement_sha256(
            AgentExecutionTransparencyStatement(
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
                statement_sha256="",
            )
        )
        # Sanity: a clean statement hashes fine.
        assert statement.statement_sha256
    except ReceiptContractError:
        raise AssertionError("clean statement body unexpectedly rejected")

    poisoned = {**body, "api_key": "sk-leaked"}
    try:
        from agent_runtime.agent_run_receipts import canonical_sha256
        canonical_sha256(poisoned)
        raise AssertionError("secret-shaped field must fail closed")
    except ReceiptContractError:
        pass


def test_raw_prompt_file_content_db_row_fail_closed():
    from agent_runtime.agent_run_receipts import canonical_sha256
    chain = _build_ok_chain()
    statement = build_transparency_statement(chain, expected_repository=REPO, expected_revision=REVISION)
    body = statement_body(statement)
    for forbidden in ("raw_prompt", "file_content", "database_row", "prompt_text", "cookie", "private_key"):
        poisoned = {**body, forbidden: "leaked-content"}
        try:
            canonical_sha256(poisoned)
            raise AssertionError(f"{forbidden} must fail closed")
        except ReceiptContractError:
            continue


def test_exported_statement_carries_no_raw_secrets_or_contents():
    chain = _build_ok_chain()
    statement = build_transparency_statement(chain, expected_repository=REPO, expected_revision=REVISION)
    exported = statement.as_canonical_dict()
    blob = repr(exported)
    # The raw agent run id, tool call ids and any secret-shaped content must
    # never appear in the exported projection.
    assert "run-2" not in blob
    assert "call-2" not in blob
    assert "sk-" not in blob
    # Only identity hashes and bounded metadata are present.
    assert "raw_prompt" not in exported
    assert "file_content" not in exported
    assert "database_row" not in exported
    assert "api_key" not in exported
    # redacted_fields documents what is never exported.
    assert set(REDACTED_FIELDS) <= set(statement.redacted_fields)


def test_no_floats_allowed_in_identity_fields():
    from agent_runtime.agent_run_receipts import canonical_sha256
    chain = _build_ok_chain()
    statement = build_transparency_statement(chain, expected_repository=REPO, expected_revision=REVISION)
    body = statement_body(statement)
    try:
        canonical_sha256({**body, "repository_revision": 1.5})
        raise AssertionError("float in identity field must fail closed")
    except ReceiptContractError:
        pass


# --- Statement is a projection, not a new truth layer ------------------------


def test_statement_does_not_register_or_sign():
    chain = _build_ok_chain()
    statement = build_transparency_statement(chain, expected_repository=REPO, expected_revision=REVISION)
    # The statement carries no registration, signature, or external effect flag.
    exported = statement.as_canonical_dict()
    for forbidden_key in ("signature", "registered", "registry", "external_effect", "attestation"):
        assert forbidden_key not in exported
    # The statement hash is a pure function of the body content.
    assert statement_sha256(statement) == statement.statement_sha256


def test_failed_gate_still_projects_without_runtime_identity_when_absent():
    # A FAIL/BLOCKED receipt with no verified runtime identity can still be
    # projected (as a non-positive statement), because it records a blocked
    # effect rather than a positive one.
    chain = _build_ok_chain()
    chain_fail = [
        chain[0],
        _next_receipt(chain[0], evidence_gate_result="BLOCKED", mcp_revision="", mcp_image_digest="", mcp_revision_verified=False, observed_effect="read", mutation_performed=False),
    ]
    statement = build_transparency_statement(chain_fail, expected_repository=REPO, expected_revision=REVISION)
    assert statement.evidence_gate_result == "BLOCKED"
    assert statement.runtime_revision is None
    assert statement.runtime_image_digest is None
