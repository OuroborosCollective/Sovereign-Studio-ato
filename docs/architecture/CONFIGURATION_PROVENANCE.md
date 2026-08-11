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
backend/agent_runtime/configuration/config_source_inventory.py  # inventory runner
backend/tests/test_configuration_provenance.py        # contract tests (30)
backend/tests/test_configuration_provenance_mirror.py # cross-language parity (1)
backend/tests/test_config_source_inventory.py        # inventory runner tests (13)
```

### Deployment mirror (byte-equivalent)
```
scripts/sovereign-backend/agent_runtime/configuration/*  # parity verified (incl. inventory runner)
```

## Non-goals

- No secrets in receipts (redacted identity only).
- No mutable URL-config truth path.
- No replacement of #1119 mutation control.
- No automatic environment promotion.

## Zod-4 pilot assessment

The clean-room core (`src/runtime/config/*`, `backend/agent_runtime/configuration/*`)
deliberately has **no external runtime dependency** such as Zod. This section
records the assessment that gates any future Zod-4 adoption, so the decision is
auditable rather than implicit.

### Current state (as of this revision)

- `zod` is **not** a dependency of the project (no entry in `package.json`,
  no `import` of `zod` anywhere in `src/`).
- The provenance core performs its own deterministic canonicalization
  (`configCanonicalize.ts` / `config_canonicalize.py`) and merge semantics.
  Adding Zod would not remove that contract; it would only add an
  *additional* validation layer on top.
- The TypeScript and Python implementations are byte-identical in
  canonical output and sha256. Introducing a Zod-only schema on the
  TypeScript side would risk a **parity break**: the Python side has no Zod.
  Any Zod-4 adoption must therefore be paired with a Python-side equivalent
  (e.g. `pydantic` or a stdlib dataclass validator), or the schema must be
  expressed in the shared canonical form both sides already honor.

### Conditions for adoption

A Zod-4 pilot is **not approved**. If a future task proposes it, the pilot
must, at minimum, demonstrate:

1. The Zod schema is derived from the **same canonical field list** that
   drives `schema_hash_from_fields`, so cross-language parity is preserved.
2. Receipt hashing is unchanged (byte-identical sha256 before and after).
3. The Zod schema is **opt-in** at the boundary, not in the resolver hot
   path; the resolver remains dependency-free.
4. License review, provenance and pinning per the repository supply-chain
   rules (no `latest`, pinned version + integrity).
5. A Python-side parity validator is added in the same change, or the
   schema is provably the shared canonical form.

### Conclusion

**PLANNED** only. No runtime dependency is added by this work. The clean-room
core remains the truth path; Zod-4 would be a boundary validator, not a
replacement for the canonical merge/receipt contract.

## Config source inventory

Issue #1169 requires that the actual config sources, environment fallbacks
and compose surfaces be inventarized in a machine-checkable form. The
inventory runner lives at:

```
backend/agent_runtime/configuration/config_source_inventory.py
scripts/sovereign-backend/agent_runtime/configuration/config_source_inventory.py  # mirror (byte-identical)
```

It is **stdlib-only and non-mutating**, mirroring the established
`integration_plan_inventory.py` pattern. It produces a schema-versioned JSON
snapshot of:

- every configuration provenance surface (TS, canonical Python, mirror),
- environment-variable fallbacks discovered by statically scanning
  `backend/agent_runtime`, the deployment mirror, and `backend/enterprise_platform`
  for `os.getenv('NAME')` calls,
- compose / deployment surfaces that bind configuration into a container,
- env-example templates that document environment fallbacks,
- guard/build configs (`sovereign.guard.json`, `package.json`, `tsconfig.json`),
- a drift report listing required surfaces that are absent (P1 severity),
- five invariant statements, and
- a `snapshotSha256` that binds the entire snapshot body, so a stale
  committed artifact is detectable.

The committed artifact is at
`docs/architecture/CONFIGURATION_SOURCES_INVENTORY.json`. It is regenerated by:

```bash
python -m agent_runtime.configuration.config_source_inventory --repo-root . --write
```

The runner also exposes `--strict` (exit non-zero on drift) for CI gating.
Tests live at `backend/tests/test_config_source_inventory.py` and verify the
runner against both an empty tree (drift expected) and the real repository
(no drift, required surfaces present, env fallbacks and compose surfaces
discovered).

## Validation

- TypeScript: 36/36 contract tests pass (`vitest run src/runtime/config/`).
- Python: 31/31 contract + cross-environment parity tests pass (`pytest`)
  plus 5/5 mirror-parity tests and 13/13 inventory tests.
- Config source inventory: 19 surfaces, 0 drift on `main`; env fallbacks and
  compose surfaces discovered by static scan.
- Mirror parity: `backend/.../configuration` byte-identical to
  `scripts/sovereign-backend/.../configuration` (now including
  `config_source_inventory.py`).
- `pnpm run type-check`: PASS (6 config files).
- `pnpm run build:web`: PASS.
- Lint: pre-existing repo-wide failure (no `eslint.config` present); unrelated
  to this change.

## Truth class

`IMPLEMENTED_IN_REPOSITORY` + `TESTED_AT_REVISION`. Not `RUNTIME_VERIFIED` —
runtime PatchMon readback wiring is a separate, downstream integration step.

The Zod-4 pilot is `PLANNED` only; no runtime dependency is introduced by
this work.
