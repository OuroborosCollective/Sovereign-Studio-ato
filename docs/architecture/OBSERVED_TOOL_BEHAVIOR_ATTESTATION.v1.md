# Observed Tool Behavior Attestation (OTBA) — v1

> Baseline revision: `4778aede60c471ccf94f536ebe06dbccc4e23349` (issue #1450, OTBA 1/5)
> Status: `IMPLEMENTED_IN_REPOSITORY` / `TESTED_AT_REVISION`
> Scope: deterministic contract and receipt foundation only. No sandbox execution, no registry promotion, no persistence, no LLM decision.

## Prime directive

Runtime creates truth. This lane does **not** create runtime truth on its own. It only lets a
caller deterministically bind a declared tool-behavior contract to an immutable, tamper-sensitive
hash, and convert a real observed behavior set into a manipulation-sensitive receipt whose verdict
is evaluated without an LLM.

A positive `BEHAVIOR_VERIFIED` verdict arises only from real, complete, in-bounds observations
that match the contract identity. It is never inferred from a button, a model answer, an exit code
or telemetry.

## Ownership

| Path | Ownership |
|------|-----------|
| `tools/sovereign-chatgpt-mcp/tool_behavior_contract.py` | canonical contract core |
| `tools/sovereign-chatgpt-mcp/tool_behavior_attestation.py` | canonical receipt + verdict core |
| `tools/sovereign-chatgpt-mcp/tests/test_tool_behavior_contract.py` | contract tests |
| `tools/sovereign-chatgpt-mcp/tests/test_tool_behavior_attestation.py` | receipt + verdict tests |

This lane introduces **no** second registry, queue, memory store, approval system or evidence truth
layer. It does not import or extend any existing evidence/registry surface. Existing architecture
and evidence ownership is unchanged.

## ToolBehaviorContract

`sovereign.tool-behavior-contract.v1`

An immutable, revision- and identity-bound declared tool behavior contract. Fields:

- `schema_version`, `tool_id`, `execution_kind` (`LOCAL_OCI` | `HOST_BROKER` | `REMOTE_MCP`)
- `repository_revision`, `tool_registry_revision` (40-char Git SHA), `image_digest`
- `effect_class` (`READ_ONLY` | `WORKSPACE_WRITE` | `EXTERNAL_WRITE`)
- `allowed_exec`, `allowed_read_paths`, `allowed_write_paths`, `allowed_network_targets`
- `network_required`, `max_wall_time_ms`, `max_memory_bytes`
- `contract_sha256` — derived, never caller-supplied

### Invariants

- `LOCAL_OCI` must bind an `image_digest`; `REMOTE_MCP` must not (a remote server has no local OCI image).
- `READ_ONLY` contracts must not declare `allowed_write_paths`.
- `EXTERNAL_WRITE` contracts must declare `network_required`.
- `network_required` contracts must declare at least one `allowed_network_targets`.
- Resource limits must be non-negative integers; `bool` is explicitly rejected (it is an `int` subclass).
- Paths are NFC-normalized; backslash separators, NUL bytes, `..` traversal and interior empty
  segments are rejected. A single leading `/` (absolute path marker) is allowed.

### Hash formation

`contract_sha256 = sha256(canonical_json(identity_record))`.

`canonical_json` rejects floats, non-string keys, bytes and unknown types; sorts keys; uses
NFC-normalized strings. The hash is computed over the identity record **excluding** the derived
`contract_sha256` itself (a self-referential hash would be circular and trivially spoofable). A
caller-supplied `contract_sha256` is always replaced by the derived value.

## ObservedToolBehaviorReceipt

`sovereign.observed-tool-behavior-receipt.v1`

An immutable, tamper-sensitive receipt over an observed behavior set and verdict.

### Observation hashing

The lane computes observation **hashes** from structured raw observations rather than trusting
caller-supplied hashes. `None` (not collected) and `()` (collected and empty) produce distinct,
well-defined hashes via observation markers, so the verdict can distinguish a violation from a
missing observation.

### Verdict semantics

`evaluate_verdict` returns `(verdict, findings)`. Precedence (highest first):

1. **CONTRADICTED** — identity (authoritative readback hash ≠ contract hash) mismatch.
2. **UNVERIFIED** — a required observation for this execution kind was not collected. A missing
   observation is never a violation: a tool cannot be blamed for behavior that was not seen.
3. **BEHAVIOR_VIOLATION** — an observed value exceeds or contradicts contract bounds (undeclared
   exec/read/write/network target, wall-time/memory exceeded, external effect on a non-external
   contract, or a missing external effect on an `EXTERNAL_WRITE` contract).
4. kind-specific success: `BEHAVIOR_VERIFIED` (LOCAL_OCI/HOST_BROKER) or `REMOTE_PARTIAL` (REMOTE_MCP).

`REMOTE_MCP` can never receive `BEHAVIOR_VERIFIED`: a remote server offers no local
syscall/filesystem fidelity. Its best honest positive outcome is `REMOTE_PARTIAL`. A remote MCP
server is networked by definition, so its network observation is always required.

### Tamper detection

`receipt_sha256 = sha256(canonical_json(receipt_record_without_hash))`. A caller-supplied value is
always replaced by the derived value at construction. Reconstruction via `receipt_from_mapping`
recomputes the hash and **fails closed** if the stored `receiptSha256` disagrees with the
recomputed canonical record. A freshly built receipt is always self-consistent (`verify()` returns
`True`); tamper detection across serialization is enforced at reconstruction.

### Asserted verdict contract

A caller may supply an asserted `verdict` to `build_receipt`. If it does not match the
deterministically evaluated verdict, the receipt fails closed as `CONTRADICTED` and records both
the asserted and evaluated verdicts.

## Secret / payload minimization

Raw secret values, file contents and network payloads are never stored in a receipt. A secret
guard scans every observed string and external-effect field for secret-shaped patterns
(PEM private keys, AWS access key ids, GitHub PATs, OpenAI-style keys, `bearer`/`secret=...`
assignments) and fails closed. Hash fields are validated as strict lowercase SHA-256 so a raw
secret cannot masquerade as a hash.

## What this lane does NOT do

- No sandbox execution, no tool invocation.
- No registry mutation or promotion.
- No persistence, no network I/O, no LLM decision.
- No claim of real runtime attestation. A receipt is only as truthful as the observations a caller
  feeds it; the lane guarantees the receipt is manipulation-sensitive and the verdict is
  deterministic, not that the observations were collected honestly.

## Remaining risks

- Observation honesty is the caller's responsibility. This lane cannot detect a caller that feeds
  fabricated-but-in-bounds observations. Subsequent OTBA lanes (sandbox execution, independent
  readback) must supply the real observations.
- The secret guard is intentionally broad and may produce false positives on benign long strings;
  it fails closed (blocks) rather than risking a real secret landing in a receipt.
