# Configuration Provenance

> Baseline revision: `313bc910` (main, 2026-08-08) · Status: `IMPLEMENTED_IN_REPOSITORY` / `TESTED_AT_REVISION`
> Parent issue: #1169 · Owner boundary: read-only resolution + provenance; mutation stays under #1119.

## Purpose

A revisions-, schema- and source-bound configuration resolution layer for the
Predictive Runtime and related subsystems (ScaNN, Wolfram, safe reflexes). It
produces a **deterministic, reproducible projection** of runtime configuration
together with a redacted public receipt hash that RunEnvelope (#1116) and
PatchMon read back independently.

This is a **read-only resolver**. It never mutates config; all mutation flows
through #1119 (CAS, resource locks, config receipts).

## Resolution order (highest priority last)

```
compiled defaults
→ immutable image manifest
→ revision-bound deployment config
→ environment projection
→ explicitly approved runtime overlay
```

Each source binds:

- `id` — stable source identity
- `kind` — `defaults | image-manifest | deployment | environment | runtime-overlay`
- `revision`/`digest` — revision or immutable image digest
- `contentHash` — canonical content hash
- `schemaHash` — schema version hash
- `priority` — resolution priority (higher wins)

## Merge semantics (deterministic)

Applied in priority order, lowest to highest:

| Value shape | Rule |
|-------------|------|
| Object | deep merge (nested keys merged recursively) |
| Array | replace wholesale (no element-wise merge) |
| `null` | explicit delete — removes the key from the merged result |
| missing key | no effect |
| present key set to object on both | recursive deep merge |

Deep merge is stable regardless of source insertion order: the result depends
only on source priorities and content, not on the order sources were added.

## Fail-closed rules

- **Unknown source kind** → resolution fails; no projection emitted.
- **Remote URL source without pre-bound origin, digest and hash** → fail closed.
- **Bare remote URL** (origin only, no digest/signature) → fail closed.
- A fail-closed state produces `BLOCKED`, never a partial green projection.

Remote configuration is only accepted when bound ahead of time to a concrete
origin, digest and signature/hash. There is no mutable URL-config truth path.

## Receipt and hashing

`computeReceiptHash(receipt)` produces a byte-identical public receipt hash for
identical input across:

- TypeScript (`src/runtime/config/configReceipt.ts`)
- Python (`backend/agent_runtime/configuration/receipt.py`)

Cross-language parity is asserted by
`src/runtime/config/configProvenance.test.ts` (TS) and
`backend/tests/test_configuration_provenance_mirror.py` (Python), which compute
the same canonical fixtures and assert identical hashes.

### Canonicalization contract

`serializeStable(value)` produces a deterministic, key-sorted UTF-8 byte
serialization used as the content hash input. Secrets are projected only as a
redacted identity (`{"__redacted__": "<sha256-prefix>"}`) — never the raw value.

`isRedactedSecret(value)` recognizes the redacted-secret marker shape so the
serializer does not recurse into redacted payloads (which previously caused
unbounded recursion).

## Drift invalidation

`ConfigDriftRecord` captures the prior and current receipt hashes. When they
differ, `isSafeToAdvance(drift)` returns false, blocking:

- new mutations (delegated to #1119 gate), and
- active action plans / run-permission bindings.

Drift never silently continues; it routes the next action to `BLOCKED`.

## PatchMon readback

The resolved receipt exposes the fields PatchMon must read back independently:

- `revision` — the resolved bound revision
- `imageDigest` — immutable image digest (when present)
- `schemaHash` — schema version hash
- `redactedConfigHash` — redacted public config hash (never contains secrets)

A container is considered configured only when PatchMon's independent readback
matches the resolved receipt. Mismatch → `BLOCKED` / `CONTRADICTED`.

## File map

### TypeScript (canonical frontend / runtime)
```
src/runtime/config/configSources.ts         # source contracts, kinds, priority
src/runtime/config/configCanonicalize.ts    # stable serialization, redaction
src/runtime/config/sovereignConfigResolver.ts  # merge + resolve + drift
src/runtime/config/configReceipt.ts         # receipt shape + public hash
src/runtime/config/index.ts                 # public surface
src/runtime/config/configProvenance.test.ts # contract tests (36)
```

### Python (canonical backend)
```
backend/agent_runtime/configuration/config_sources.py
backend/agent_runtime/configuration/config_canonicalize.py
backend/agent_runtime/configuration/resolver.py
backend/agent_runtime/configuration/receipt.py
backend/agent_runtime/configuration/__init__.py
backend/tests/test_configuration_provenance.py        # contract tests (29)
backend/tests/test_configuration_provenance_mirror.py # cross-language parity (1)
```

### Deployment mirror (byte-equivalent)
```
scripts/sovereign-backend/agent_runtime/configuration/*  # parity verified
```

## Non-goals

- No secrets in receipts (redacted identity only).
- No mutable URL-config truth path.
- No replacement of #1119 mutation control.
- No automatic environment promotion.

## Validation

- TypeScript: 36/36 contract tests pass (`vitest run src/runtime/config/`).
- Python: 30/30 contract + parity tests pass (`pytest`).
- Mirror parity: `backend/.../configuration` byte-identical to
  `scripts/sovereign-backend/.../configuration`.
- `pnpm run type-check`: PASS (6 config files).
- `pnpm run build:web`: PASS.
- Lint: pre-existing repo-wide failure (no `eslint.config` present); unrelated
  to this change.

## Truth class

`IMPLEMENTED_IN_REPOSITORY` + `TESTED_AT_REVISION`. Not `RUNTIME_VERIFIED` —
runtime PatchMon readback wiring is a separate, downstream integration step.
