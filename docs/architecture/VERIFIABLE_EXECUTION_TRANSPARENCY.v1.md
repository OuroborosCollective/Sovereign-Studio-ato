# Verifiable Execution Transparency — Statement v1

Status: `IMPLEMENTED_IN_REPOSITORY` (SVET 1/5, Issue #1485)
Baseline `main`: `046b31d2c3c61e711e5e98cb084129697254bf0d` (issue creation baseline). Re-resolve the current `main` before any mutation.
Truth class of this lane: `IMPLEMENTED_IN_REPOSITORY` until CI verifies it at the exact PR head, then `CI_VERIFIED`. It is never `RUNTIME_VERIFIED` by virtue of the statement existing.

## Purpose

This lane derives a **privacy-minimized, canonical Agent Execution Transparency Statement** from an *already-verified* internal Sovereign receipt chain. It is a read-only projection surface. It owns:

- no effect truth,
- no second internal receipt chain,
- no external registration,
- no signature effect.

The statement is a strict projection of `backend/agent_runtime/agent_run_receipts.py`. Removing this lane must leave the canonical ATO runtime unchanged.

## Ownership reused (not duplicated)

- `backend/agent_runtime/agent_run_receipts.py` — canonical receipts, chain verification, canonicalization and secret-safety logic (`canonical_value`, `canonical_sha256`, `verify_agent_run_receipt_chain`, `build_agent_run_receipt`).
- `backend/agent_runtime/verification_gateway.py` — paid A2A Sovereign Verification Gateway (merged PR #1481). May be *referenced* as additional evidence by a receipt, never *duplicated* into the statement.
- Deployment mirror `scripts/sovereign-backend/agent_runtime/execution_transparency/` is byte-equivalent to the canonical copy; parity is asserted in tests.

No second `AgentRunReceipt` class with divergent truth exists.

## New surface

```text
backend/agent_runtime/execution_transparency/__init__.py
backend/agent_runtime/execution_transparency/statement.py
backend/tests/test_execution_transparency_statement.py
scripts/sovereign-backend/agent_runtime/execution_transparency/__init__.py   (mirror)
scripts/sovereign-backend/agent_runtime/execution_transparency/statement.py   (mirror)
docs/architecture/VERIFIABLE_EXECUTION_TRANSPARENCY.v1.md
```

## Statement contract

```python
@dataclass(frozen=True, slots=True)
class AgentExecutionTransparencyStatement:
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
```

`schema_version` is `sovereign.agent-execution-transparency-statement.v1`.

## Mapping rule

The statement may only originate from a chain that already passed `verify_agent_run_receipt_chain` against the expected repository and revision. No LLM decides admission or truth status.

```python
def build_transparency_statement(receipt_chain, expected_repository, expected_revision):
    verdict = verify_agent_run_receipt_chain(
        receipt_chain,
        expected_repository=expected_repository,
        expected_base_commit_sha=expected_revision,
    )
    if not verdict["ok"]:
        raise TransparencyBlocked("INTERNAL_RECEIPT_CHAIN_INVALID")
    return privacy_minimized_statement(receipt_chain[-1], verdict)
```

`privacy_minimized_statement` then re-asserts the head identity against the verified verdict and applies the privacy / effect-readback invariants before producing a statement.

## Privacy / secret safety

The exported statement never carries:

- raw prompts / chain-of-thought,
- source-code contents,
- database rows,
- access tokens / PATs / API keys,
- provider answers,
- full tool outputs,
- secrets / PII.

The raw `agent_run_id` is hashed (`agent_run_id_sha256`) before export. Only identity hashes and bounded effect metadata survive the projection. Canonicalization and secret-safety logic is **reused** from `agent_run_receipts` (`canonical_value` / `canonical_sha256`), not copied. Any secret-shaped field that attempts to enter the canonical body fails closed via `ReceiptContractError` (the same gate used by receipts). `REDACTED_FIELDS` is a fixed declaration documenting exactly what is never exported.

## Canonicalization

- UTF-8 NFC, deterministically sorted JSON projection, no floats / NaN / Infinity in identity fields.
- SHA-40 / SHA-256 / image-digest fields are strictly pattern-validated before mapping.
- Timestamps are metadata only and never enter the statement hash.
- Field ordering does not affect the statement hash (sorted keys via `canonical_sha256`).
- `statement_sha256` is computed over the canonical body excluding `statement_sha256` itself, so the hash is a pure function of content.

## Effect-readback invariants

- A receipt with observed effect `none` cannot produce a statement (a transparency statement records a material agent effect).
- A positive (`PASS`) external-write effect requires a non-zero `authoritative_readback_sha256` (not the genesis zero anchor) and a verified runtime revision + image digest. Missing readback → no positive statement status (`AUTHORITATIVE_READBACK_MISSING_FOR_EXTERNAL_EFFECT`).
- A `FAIL` / `BLOCKED` receipt may legitimately omit runtime identity and still be projected as a non-positive statement.

## Tests (`backend/tests/test_execution_transparency_statement.py`)

The test exercises the real live-path implementation using the proven flat import style (`sys.path.insert(0, backend)` + `from agent_runtime...`), so it is collectable from the repository root in CI without `PYTHONPATH`. It is registered in both `.github/workflows/ci.yml` (Run Agent Tests gate) and `.github/workflows/sovereign-agent-backend.yml`.

Coverage:

- identical receipt → identical statement hash;
- change in Git-SHA, effect, input/output/mutation/readback, operation identity, agent run id → different hash;
- invalid internal chain → no statement;
- broken chain link → no statement;
- other repository revision → blocked;
- empty chain → blocked;
- positive external effect without authoritative readback → blocked;
- effect `none` → blocked;
- secret-shaped field (api_key, raw_prompt, file_content, database_row, prompt_text, cookie, private_key) → fail closed;
- floats in identity fields → fail closed;
- exported statement carries no raw secrets, raw ids, or contents;
- statement has no registration / signature / external-effect keys (projection only);
- non-positive (BLOCKED) receipt projects without runtime identity.

Mocks are not used for productive statement evidence; only the real receipt builder and chain verifier produce the receipts under test.

## Versioning and migration

- `schema_version` pins the statement semantics. A future incompatible change must bump to `*.v2` and document the migration.
- The statement is additive: existing receipts, the receipt chain, and the verification gateway are unchanged. No migration of stored receipts is required to derive v1 statements.
- Truth-state transitions for this lane: `PLANNED` (issue) → `IMPLEMENTED_IN_REPOSITORY` (this PR) → `CI_VERIFIED` (green at exact PR head). It is not `RUNTIME_VERIFIED` by this lane alone; runtime readback of the underlying receipts (#1308) governs runtime truth.

## External registration / signature effect

None. This lane performs no external registration and applies no signature. It only derives and exports a canonical, privacy-minimized projection.
