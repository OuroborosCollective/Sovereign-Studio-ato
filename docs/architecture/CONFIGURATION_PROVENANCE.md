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

## Source inventory (concrete repo surfaces)

The five abstract `ConfigSourceKind`s map onto these concrete surfaces in the
repository (inventoried at revision `313bc910`, 2026-08-08):

| Kind | Concrete surface | Notes |
|------|------------------|-------|
| `compiled-defaults` | Hardcoded defaults inside resolver call sites (no file) | Lowest priority; always present |
| `image-manifest` | Immutable image digest bound at build/deploy time | Bound externally; read back via `imageDigest` |
| `deployment-config` | `.env.example`, `.env.sovereign-toolchain.example` (templates only) | Revision-bound at deploy; no compose file exists in-repo |
| `environment-projection` | `process.env.TOOLCHAIN_API_KEY` (src); build-time `VITE_ADMIN_API_BASE`, `VITE_SOVEREIGN_BACKEND_URL`, `VITE_SOVEREIGN_AGENT_API_URL`, `VITE_GITHUB_OAUTH_CLIENT_ID`, `VITE_OPENHANDS_*`; runtime `GEMINI_API_KEY` | Projected read-only; secrets redacted before receipt |
| `approved-runtime-overlay` | Explicitly approved overlay only | Highest priority; must be pre-bound |

Findings:

- **No `docker-compose*.yml` / `compose*.yml` exists in the repository** at this
  revision. Deployment-config is therefore not sourced from a compose file; it
  is bound from revision-bound env templates and the deploy-time image manifest.
  If a compose surface is introduced later it must be re-inventoried here and
  bound as a `deployment-config` source.
- **Env fallbacks are build-time / runtime projections**, never a mutable truth
  path: `VITE_*` values are baked at frontend build, `process.env.*` runtime
  values are projected read-only into the `environment-projection` source. None
  mutate config directly; all flow through the resolver merge.
- **Secrets** (`GEMINI_API_KEY`, `TOOLCHAIN_API_KEY`, OAuth secrets) never enter
  receipts: they reach the resolver only as a `RedactedSecret`
  (`redactedId` = sha256 prefix), so the inventory lists them by name only.

This inventory is a claim surface: if the concrete surfaces change, this table
must be updated at the same revision so it never contradicts the repo.

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
- `resolvedHash` — redacted resolved-config hash (never contains secrets)
- `receiptHash` — the redacted public config fingerprint both sides must agree on

A container is considered configured only when PatchMon's independent readback
matches the resolved receipt. Mismatch → `BLOCKED` / `CONTRADICTED`.

### Readback verification contract

`verifyConfigReadback(receipt, observation)` (TS) /
`verify_config_readback(receipt, observation)` (Python) performs a fail-closed
audit of an independent PatchMon `ConfigReadbackObservation` against a bound
`ConfigReceipt`. It is the readback side of the #1169 causal chain:
RunEnvelope materializes a receipt, PatchMon independently reads back the
loaded projection, and deviation produces an explicit, routable finding rather
than silent continuation.

Rules, in order:

1. The receipt must self-verify (`verifyReceipt`); a tampered receipt →
   `config_receipt_self_verification_failed` (`accepted=false`,
   `contradicted=false`).
2. For every **bound** (non-empty) field — `revision`, `imageDigest`,
   `schemaHash`, `resolvedHash` — PatchMon must report the same value:
   - mismatch on a populated field → `config_readback_contradicts_receipt`
     (`contradicted=true` — the wrong config is loaded);
   - PatchMon omits a bound field → `config_readback_missing_bound_field`
     (`contradicted=false` — readback incomplete).
3. The redacted `receiptHash` fingerprint must match byte-for-byte when
   PatchMon reports it; if PatchMon omits it, readback is incomplete.

Fields the receipt does not bind (empty on the receipt) are ignored — PatchMon
omitting an unbound field does not block. Either a contradiction or a missing
bound field routes the runtime to `BLOCKED`/`CONTRADICTED` instead of
advancing. No secret material appears in observations or audits by design.

## Zod-4 pilot assessment and clean-room rationale

Issue #1169 requires that Zod-4 compatibility of a library pilot be checked and
that either adoption or a clean-room core be justified. The codebase made the
**clean-room** decision; this section records the assessment that justifies it
and is referenced by `src/runtime/config/index.ts`. The Python mirror
(`backend/agent_runtime/configuration/`) implements the same clean-room core
(stdlib-only `hashlib` + deterministic serialization) without an external
validation dependency, verified by the mirror-parity test.

Assessment (at revision `313bc910`):

- **`zod` is not a dependency.** It is absent from both `package.json`
  (`dependencies` + `devDependencies`, 56 total) and `node_modules`. Adding it
  would introduce a new runtime dependency for a layer whose job is
  deterministic hashing and fail-closed source binding — precisely the
  surface that must stay dependency-light and auditable.
- The provenance layer needs **stable canonical serialization** and
  **content/schema hashing**, not rich runtime validation. The schema contract
  is a `ConfigSchemaDescriptor` (field list) whose `schemaHash` is sha256 of the
  canonicalized descriptor — a stdlib-equivalent operation with no
  validation-library benefit.
- The TS Contract Pilot inventory
  (`docs/architecture/TYPESCRIPT_CONTRACT_PILOT/INVENTORY.md`, issue #1115)
  separately evaluated Zod/Typia for compile-time contract generation at MCP and
  receipt boundaries and remains `PLANNED`. That is the correct home for any
  future Zod adoption; it is deliberately **not** pulled into the read-only
  provenance resolver, which must not gain an unaudited central dependency.
- Zod-4 compatibility was therefore checked by **absence + scope fit**: the
  provenance layer has no call site that would benefit from Zod runtime parsing,
  and adopting it would contradict the agent-rule prohibition on introducing an
  unaudited central dependency into a truth-adjacent layer.

Decision: **clean-room core, no Zod dependency.** The resolver, canonicalizer
and receipt use only the language stdlib (`crypto`/`hashlib`) and deterministic
key-sorted serialization. If a future Zod pilot (#1115) lands and a provenance
call site gains a real validation need, that adoption must be a separately
approved design bound to a revision — not a silent addition here.

## File map

### TypeScript (canonical frontend / runtime)
```
src/runtime/config/configSources.ts         # source contracts, kinds, priority
src/runtime/config/configCanonicalize.ts    # stable serialization, redaction
src/runtime/config/sovereignConfigResolver.ts  # merge + resolve + drift
src/runtime/config/configReceipt.ts         # receipt shape + public hash +
                                            # verifyConfigReadback + readback types
src/runtime/config/index.ts                 # public surface
src/runtime/config/configProvenance.test.ts # contract tests (46)
```

### Python (canonical backend)
```
backend/agent_runtime/configuration/config_sources.py
backend/agent_runtime/configuration/config_canonicalize.py
backend/agent_runtime/configuration/resolver.py
backend/agent_runtime/configuration/receipt.py  # + verify_config_readback + readback types
backend/agent_runtime/configuration/__init__.py
backend/tests/test_configuration_provenance.py        # contract tests (39, incl. readback)
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

- TypeScript: 46/46 contract tests pass (`vitest run src/runtime/config/`),
  including 11 PatchMon readback cases.
- Python: 39/39 contract tests pass + 1 cross-language parity test (40 total)
  (`pytest`), including 11 readback cases.
- Mirror parity: `backend/.../configuration` byte-identical to
  `scripts/sovereign-backend/.../configuration`.
- `pnpm run type-check`: PASS (sharded, 0 deferred).
- `pnpm run build:web`: PASS (Sovereign static audit passed).
- Lint: pre-existing repo-wide failure (no `eslint.config` present); unrelated
  to this change.

## Truth class

`IMPLEMENTED_IN_REPOSITORY` + `TESTED_AT_REVISION`. Not `RUNTIME_VERIFIED` —
runtime PatchMon readback wiring is a separate, downstream integration step.
