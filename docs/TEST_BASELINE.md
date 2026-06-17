# Test Baseline

This document records the current test status after the Remote Memory App Bridge and follow-up product-polish codemods landed on `main`.

## Current main baseline

Latest verified main commit:

```txt
2d36520b2e09f040f5217b520ed8d13c1b74f73e
```

Reported result on `main` after applying Aha memory persistence and timeout stabilizer codemods:

| Category | Passed | Failed | Interpretation |
| --- | ---: | ---: | --- |
| Runtime / Remote Memory | 119 | 0 | Green release gate for deterministic runtime and remote-memory work. |
| TypeScript | 1 | 0 | Type check is clean. |
| Build | 1 | 0 | Build completed successfully in about 455ms. |

Earlier separated-lane baseline before the timeout stabilizer codemod:

| Category | Passed | Failed | Interpretation |
| --- | ---: | ---: | --- |
| Integration | 31 | 13 | Known API/chat/sequential timeout area before stabilization. |
| E2E | 82 | 1 | Known API fallback timeout area before stabilization. |
| Full suite | 476 | 20 | Historical full-suite red from known external/API timeout paths. |

The known timeout areas were not caused by the Remote Memory App Bridge. The current runtime gate is green at 119/119.

## Remote Memory gate

The Remote Memory runtime gate is green:

```txt
Remote Memory Runtime Tests: 119/119 passed
```

The passing runtime area includes, among others:

- `externalMemorySync.test.ts`
- `externalMemoryMonitoring.test.ts`
- `remoteMemoryUpdateIntake.test.ts`
- `remoteMemoryGatewayBridge.test.ts`
- `solutionPatternPersistence.test.ts`
- `runtimeValidationCoverage.test.ts`
- workflow, telemetry, sequential runtime, scan registry, health, and generated-file review runtime tests

Remote Memory can therefore be treated as clean unless a future diff touches its runtime or app bridge code and causes this lane to fail.

## Test lanes

Use separated commands so deterministic local runtime work is not blocked by known external/API timing failures:

```bash
npm run test:unit
npm run test:integration
npm run test:e2e
npm run test:all
```

### `test:unit`

Runs the deterministic local unit/runtime lane and excludes known external/API/e2e/UI-flake paths:

- `**/*.chat.test.ts`
- `**/*.integration.test.ts`
- `**/*.e2e.test.ts`
- `**/*.spec.ts`
- `**/*.sequential.test.ts`
- `**/ChatSidebar.test.tsx`
- `**/e2e/**`
- `**/api-fallback/**`

This is the primary release gate for local runtime feature work.

### `test:integration`

Runs explicit integration-style Vitest files such as chat/API-adjacent tests, sequential workflow tests and currently flaky chat UI tests. These can require deterministic mocks, controlled fake transports, or explicit live-service opt-in.

Last recorded pre-stabilizer integration lane result:

```txt
31 passed, 13 failed
```

Run this lane again after the timeout stabilizer codemod to replace this historical number.

### `test:e2e`

Runs the mobile/e2e runner under `sovereign-studio-rn/e2e/run-e2e.ts`.

Last recorded pre-stabilizer e2e lane result:

```txt
82 passed, 1 failed
```

Run this lane again after the timeout stabilizer codemod to replace this historical number.

### `test:all`

Runs the complete Vitest suite with no lane exclusions. Use this for full visibility, not as the only signal for whether a deterministic runtime change is healthy.

Last recorded pre-stabilizer full-suite result:

```txt
476 passed, 20 failed
```

## Release-gate interpretation

Runtime and unit tests that do not depend on external services are the primary release gate for local feature work.

External API, mobile/e2e, UI timing, and network-dependent test paths must be tracked separately so they do not hide regressions in deterministic runtime modules.

## Known flaky or external areas

Known areas to inspect before treating the full suite as red because of a new local feature:

- Sequential workflow tests that depend on external APIs or slow network timing.
- Chat-message tests with API timing behavior.
- Chat sidebar UI assertions that currently match multiple badges or empty suggestions differently than expected.
- Mobile/e2e API fallback tests under `sovereign-studio-rn/e2e/**`.

These tests should not be removed. They should be moved behind explicit integration/e2e commands, given deterministic mocks, or gated behind a live-service opt-in flag.

## Rules for future changes

1. Do not mark external API timeout failures as caused by unrelated runtime changes unless the failing diff touches that path.
2. Keep remote-memory runtime tests deterministic and local.
3. Keep gateway contract tests mocked unless a separate integration command intentionally targets the VPS gateway.
4. If a runtime module touches user/contributor data, its tests must verify contributor scoping and shared-pattern preservation.
5. If a test requires a live service, document the required environment variable and keep it out of the default unit test gate.
6. Full-suite red from known timeout paths is not the same as runtime gate red.
7. Remote Memory changes must keep the `Runtime / Remote Memory` lane at 119/119 or higher as tests are added.

## Cleanup targets

Keep cleanup issues open until the post-stabilizer integration and e2e lanes are re-run and recorded.

Long-term cleanup target:

- replace API timeout behavior with deterministic mocks where possible;
- keep live-service tests behind explicit env variables;
- keep mobile/browser e2e in its own job lane;
- never hide real deterministic runtime regressions behind broad skip rules.
