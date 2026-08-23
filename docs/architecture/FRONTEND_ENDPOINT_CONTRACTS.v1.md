# Sovereign Frontend Endpoint Contracts v1

## Status

Truth class: `IMPLEMENTED_IN_REPOSITORY` only until exact-head CI and browser evidence exist.

This contract covers the canonical React/Vite/Capacitor frontend under `src/` and the backend route surfaces tracked in the same Sovereign Studio ATO repository. It does not turn static source discovery, a browser interception, or a successful HTTP status into production runtime truth.

## Purpose

Every production frontend request must have one deterministic repository answer to all of these questions:

1. Which normalized endpoint path is requested?
2. Which HTTP method is used?
3. Which production frontend file owns the call?
4. Which backend route declaration owns that path and method?
5. Which test surfaces refer to the contract?
6. Is the source active, explicitly non-active, or a static artifact?

The canonical compiler is:

```text
scripts/frontend_endpoint_contracts.py
```

It emits:

```text
.security-reports/sovereign-frontend-endpoints.json
```

Schema:

```text
sovereign.frontend-endpoint-contracts.v1
```

## Causal boundary

```text
frontend source expression
→ normalized path + method
→ repository backend route declaration
→ deterministic binding report
→ Python regression gate
→ TypeScript/type/build gates
→ Playwright browser wiring smoke
→ optional authenticated target runtime probe
```

Each arrow is a different evidence class.

```text
BOUND in the report
!= endpoint reachable in production

Playwright request observed
!= backend implementation verified

HTTP 200
!= authenticated operation authorized

UI success state
!= target effect verified
```

Production claims still require the relevant session, revision, artifact, deployment, database, target-system and PatchMon readbacks.

## Static compiler behavior

The compiler:

- scans production TypeScript, TSX and JavaScript request expressions;
- parses Flask/FastAPI-style Python decorators through Python AST;
- parses bounded Express-style JavaScript route declarations;
- normalizes query strings and dynamic path parameters to `<p>`;
- resolves template literals, helper wrappers and concatenated route expressions;
- derives browser-default `GET` only for real request wrappers whose source contract defaults to `fetch` behavior;
- keeps WebAuthn/data transformers outside the HTTP request class;
- treats `/generated/**` as static artifact retrieval rather than backend runtime;
- inventories explicit non-active surfaces without promoting them to live paths;
- records unit, backend and E2E test references;
- builds a static relative-import graph and rejects active value/dynamic imports into `legacy-unreferenced`, `retired` or `quarantined` endpoint surfaces;
- inventories absolute third-party requests separately as `externalCalls` with host, normalized path, method, source file and active/non-active classification;
- writes a deterministic source-tree hash and report hash;
- performs no network request and reads no credential.

The gate fails closed for:

- an active first-party frontend request with no backend route;
- a path whose backend route exists only under a different HTTP method;
- an active request whose HTTP method cannot be determined;
- malformed report output or an invalid repository revision identity.

## Explicit non-active surfaces

A source file that remains tracked for migration or provenance but is not part of the current production graph must declare one of the bounded markers near the file header:

```text
sovereign-endpoint-surface: legacy-unreferenced
sovereign-endpoint-surface: disabled-launcher
sovereign-endpoint-surface: test-only
sovereign-endpoint-surface: quarantined
sovereign-endpoint-surface: retired
```

A marker is a classification claim, not proof. Review and import-graph evidence must support it. An active runtime value import or dynamic import into a legacy, retired or quarantined surface fails closed. Type-only imports do not create runtime reachability. Removing a marker without restoring a backend contract makes the gate fail.

The retired `sovereign-studio-rn/**` tree is inventoried as `legacy-unreferenced` and is not promoted into the canonical React/Vite/Capacitor request count. The historical direct multi-provider manager, unmounted refactor surfaces, Awareness/Fallback helpers and unused browser-provider adapters are likewise explicitly classified because the current provider truth is the backend-owned OpenRouter paid and FreeLLM/Revolver free architecture. The import graph prevents those files from being silently mounted again.

## External endpoint inventory

Absolute third-party HTTP targets are never silently discarded or mistaken for Flask routes. They are emitted under `externalCalls` and counted separately. An external entry proves only that tracked frontend source contains a request expression. It does not prove consent, CORS reachability, credential availability, provider health, quota, price or successful execution.

An active external request with an unknown HTTP method fails the compiler. Authorization and data-transfer policy remain owned by the relevant canonical runtime and consent boundaries.

## Consent and mutating requests

The endpoint compiler does not grant authority. A mutating call still requires its canonical server-side session, CSRF, step-up, owner-consent, permission, CAS/staleness and target-readback contracts.

The browser smoke intentionally opens the Billing surface without selecting or confirming a purchase. It must observe only:

```text
GET /api/user/agent/jobs
GET /api/billing
GET /api/billing/payment-methods
```

No `POST`, `PATCH` or `DELETE` under `/api/billing` may occur from merely opening the surface. Adapter mocks in this smoke prove frontend request wiring only; they cannot count as a payment, entitlement or backend runtime receipt.

Phantom routes such as `/api/billing/cancel` and `/api/billing/restore` are forbidden unless a separately reviewed provider, persistence, consent and target-readback contract is implemented.

## Test topology

### Deterministic Python regression

```text
python3 -m pytest scripts/tests/test_frontend_endpoint_contracts.py -q
```

Coverage includes:

- template parameters;
- concatenated dynamic routes;
- Blueprint prefixes;
- query normalization;
- method mismatch and missing-route denial;
- external absolute URL separation;
- helper-transformer false-positive denial;
- static artifacts;
- explicit non-active surfaces;
- the complete current repository contract.

### Package gate

```text
pnpm run test:frontend-endpoints
```

This compiles the report with `--check` and runs the Python regressions.

### Browser E2E smoke

```text
pnpm run test:e2e:frontend-endpoints
```

`tests/e2e/frontend-endpoint-contract-smoke.spec.ts`:

- recompiles and validates the exact checked-out report;
- verifies every active first-party request has a matching backend path and method;
- starts the built frontend through the canonical Playwright configuration;
- observes critical runtime request wiring;
- rejects unconsented Billing writes;
- preserves the declaration that network adapters are not production runtime evidence.

The normal `pnpm run test:e2e` command also includes this test.

### CI ownership

- `.github/workflows/sovereign-contract-scan.yml` owns the compiler/regression report and the Runtime/UX/Live-Path contract gate.
- `.github/workflows/e2e-testing.yml` owns the built-browser smoke and Android/web artifact handoff.
- `pnpm run test:release-gate` owns local/CI aggregation before release qualification.
- `pnpm run verify` owns the full repository verification chain.

## Completion classes

Use only the evidence-backed class reached by the exact revision:

```text
IMPLEMENTED_IN_REPOSITORY
TESTED_AT_REVISION
CI_VERIFIED
ARTIFACT_VERIFIED
DEPLOYED_UNVERIFIED
RUNTIME_VERIFIED
BLOCKED
CONTRADICTED
```

A report with `status: pass` is repository contract evidence. It is never, by itself, `RUNTIME_VERIFIED`.
