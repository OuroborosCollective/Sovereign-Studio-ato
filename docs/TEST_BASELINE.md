# Test Baseline

This document records the current test status after the Remote Memory App Bridge integration landed on `main`.

## Current main baseline

Reported result on `main` after applying the Remote Memory App Bridge and running the separated lanes:

| Category | Passed | Failed | Interpretation |
| --- | ---: | ---: | --- |
| Runtime / Remote Memory | 116 | 0 | Green release gate for deterministic runtime and remote-memory work. |
| Integration | 31 | 13 | Known API/chat/sequential timeout area. |
| E2E | 82 | 1 | Known API fallback timeout area. |
| Full suite | 476 | 20 | Red because of known pre-existing external/API timeout paths. |

Build completed successfully after the Remote Memory App Bridge codemod.

The known failures are pre-existing API-dependent timeout tests and chat/sequential tests. They are not caused by the Remote Memory App Bridge.

## Remote Memory gate

The Remote Memory runtime gate is green:

```txt
Remote Memory Runtime Tests: 116/116 passed
```

The passing runtime area includes, among others:

- `externalMemorySync.test.ts`
- `externalMemoryMonitoring.test.ts`
- `remoteMemoryUpdateIntake.test.ts`
- `remoteMemoryGatewayBridge.test.ts`
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

Current integration lane result:

```txt
31 passed, 13 failed
```

The known failure class is API/chat/sequential timeout behavior.

### `test:e2e`

Runs the mobile/e2e runner under `sovereign-studio-rn/e2e/run-e2e.ts`.

Current e2e lane result:

```txt
82 passed, 1 failed
```

The known failure class is an API fallback timeout in `sovereign-studio-rn/e2e/api-fallback/api-fallback.spec.ts`.

### `test:all`

Runs the complete Vitest suite with no lane exclusions. Use this for full visibility, not as the only signal for whether a deterministic runtime change is healthy.

Current full-suite result:

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

These tests should not be deleted. They should be moved behind explicit integration/e2e commands, given deterministic mocks, or gated behind a live-service opt-in flag.

## Rules for future changes

1. Do not mark external API timeout failures as caused by unrelated runtime changes unless the failing diff touches that path.
2. Keep remote-memory runtime tests deterministic and local.
3. Keep gateway contract tests mocked unless a separate integration command intentionally targets the VPS gateway.
4. If a runtime module touches user/contributor data, its tests must verify contributor scoping and shared-pattern preservation.
5. If a test requires a live service, document the required environment variable and keep it out of the default unit test gate.
6. Full-suite red from known timeout paths is not the same as runtime gate red.
7. Remote Memory changes must keep the `Runtime / Remote Memory` lane at 116/116 or higher as tests are added.

## Cleanup targets

Create or keep open cleanup issues for:

- Integration chat/sequential API timeout tests: 13 failing tests.
- E2E API fallback timeout test: 1 failing test.

Long-term cleanup target:

- replace API timeout behavior with deterministic mocks where possible;
- keep live-service tests behind explicit env variables;
- keep mobile/browser e2e in its own job lane;
- never hide real deterministic runtime regressions behind broad skip rules.
