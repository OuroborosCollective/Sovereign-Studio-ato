# Configuration Provenance

> Baseline revision: `2f80916` (main, 2026-08-12) · Status: `IMPLEMENTED_IN_REPOSITORY` / `TESTED_AT_REVISION`
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

## Library pilot assessment (Zod-4 / `@mrspartak/config`)

Issue #1169 names `@mrspartak/config` as the reference pilot to vet before
introducing any unvetted central validation dependency, and requires an
explicit Zod-4 compatibility check ("Zod-4-Kompatibilität eines
Library-Piloten geprüft; Nutzung oder clean-room Kern begründet"). This
section records that assessment so the clean-room decision is grounded in
evidence rather than assumed.

### Pilot surface (verified 2026-08-12, `@mrspartak/config@1.0.0`)

- **What it is:** a thin "Config facade for TS" (MIT, single maintainer) with
  three entry points — `fromJSONFile`, `fromObject`, `fromURL` — that read/load
  JSON, merge multiple sources into one object, and validate it against a
  caller-supplied schema.
- **Runtime dependencies:** none. `dependencies` and `peerDependencies` are
  empty; the package does **not** bundle a validator. The caller supplies any
  validator (zod, valibot, myzod, superstruct, yup, or a custom function) and
  the facade merely calls it.
- **Zod pin:** zod appears only as a `devDependency` (`^3.23.8`, i.e. **Zod
  3**) used for the pilot's own test suite. The published artifact never
  imports zod at runtime, so the facade is validator-version-agnostic — but its
  own test matrix targets Zod 3, not Zod 4.

### Zod-4 compatibility

Zod 4 is the current major (`zod@latest` = 4.4.3 on 2026-08-12). Because the
pilot's published artifact carries no zod dependency, adopting it would not
by itself force a Zod-3→4 migration in Sovereign Studio. However, the pilot's
own test/compat surface is declared against Zod 3; a caller choosing zod as
its validator would assume the Zod-4 upgrade/migration burden and risk
separately. This is acceptable for a *validation* concern but is orthogonal
to *provenance*.

### Provenance gap (why the pilot does not satisfy #1169)

The pilot is a load+validate facade. It provides **none** of the provenance
surface #1169 requires:

| #1169 requirement | Pilot support |
|--------------------|---------------|
| Source binding (id / kind / revision / digest / contentHash / schemaHash / priority) | none — sources are file/URL/object paths only |
| Deterministic, priority-ordered merge with stable semantics (object deep-merge, array replace, explicit `null` delete) | merge is unspecified "merge into one object"; no priority, no delete semantics |
| Fail-closed on unknown sources and bare/remote URLs | none — `fromURL` fetches any URL by design |
| Redacted secret identity in projection and receipt | none — no redaction concept |
| Byte-identical redacted receipt hash across TS and Python | none — no receipt, no hash, no Python port |
| Drift invalidation of run/permission bindings | none |
| PatchMon readback of revision / imageDigest / schemaHash / redactedConfigHash | none |

A load+validate library cannot become a provenance truth layer without
reimplementing everything above around it. Adopting it would add an unvetted
single-maintainer dependency for a `read+JSON.parse+merge` convenience that is
already covered by the clean-room core, while leaving the provenance gap
untouched.

### Conclusion: clean-room core, justified

The implementation under `src/runtime/config/**` and
`backend/agent_runtime/configuration/**` is a stdlib-only clean-room core with
no external validation dependency. This is the correct choice because:

1. The provenance requirements (source binding, deterministic merge, redacted
   receipts, cross-language hash parity, drift gating, PatchMon readback)
   exceed the pilot's scope entirely.
2. The pilot would add a dependency without closing the provenance gap, and
   would import its Zod-3 test-matrix as an implicit compatibility surface.
3. Cross-language (TS ↔ Python) byte-identical receipt hashing is a hard
   requirement; a TS-only facade cannot serve it.

No validator library is banned for *separate* runtime-validation use cases,
but it must not become the configuration provenance truth layer or be added as
an unvetted central dependency for it. Zod-4 adoption, if ever needed for
unrelated schema validation, can be evaluated on its own merits without
touching this provenance surface.

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
src/runtime/config/configProvenance.test.ts # contract tests (51)
src/runtime/config/configProvenanceParity.test.ts # cross-language parity (4)
```

### Python (canonical backend)
```
backend/agent_runtime/configuration/config_sources.py
backend/agent_runtime/configuration/config_canonicalize.py
backend/agent_runtime/configuration/resolver.py
backend/agent_runtime/configuration/receipt.py
backend/agent_runtime/configuration/__init__.py
backend/tests/test_configuration_provenance.py            # contract tests (31)
backend/tests/test_configuration_provenance_mirror.py     # cross-language parity (1)
backend/tests/test_configuration_provenance_parity.py     # hash parity (4)
backend/tests/test_configuration_provenance_unicode_parity.py  # unicode parity (2)
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

- TypeScript: 55/55 contract + parity tests pass
  (`vitest run src/runtime/config/`): 51 in `configProvenance.test.ts`, 4 in
  `configProvenanceParity.test.ts`.
- Python: 51/51 contract + parity tests pass
  (`pytest backend/tests/test_configuration_provenance*.py`).
- Mirror parity: `backend/.../configuration` byte-identical to
  `scripts/sovereign-backend/.../configuration`.
- `pnpm run type-check`: PASS (config files unchanged; comment pointer updated).
- `pnpm run build:web`: PASS.
- Lint: pre-existing repo-wide failure (no `eslint.config` present); unrelated
  to this change.

## Truth class

`IMPLEMENTED_IN_REPOSITORY` + `TESTED_AT_REVISION`. Not `RUNTIME_VERIFIED` —
runtime PatchMon readback wiring is a separate, downstream integration step.
