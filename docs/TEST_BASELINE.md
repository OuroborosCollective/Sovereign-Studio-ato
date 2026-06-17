# Test Baseline

This document records the current test status after the Remote Memory App Bridge integration landed on `main`.

## Current baseline

Reported result after running the full test suite:

- 477 tests passed.
- 19 tests failed.
- Build completed successfully.
- The known failures are pre-existing API-dependent timeout tests and chat-message tests, not introduced by the Remote Memory App Bridge codemod.

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

Runs explicit integration-style Vitest files such as chat/API-adjacent tests, sequential workflow tests and currently flaky chat UI tests. These can require mocks or controlled API setup.

Current integration lane includes:

- `src/**/*.chat.test.ts`
- `src/**/*.integration.test.ts`
- `src/**/*.e2e.test.ts`
- `src/**/*.sequential.test.ts`
- `src/**/ChatSidebar.test.tsx`

### `test:e2e`

Runs the mobile/e2e runner under `sovereign-studio-rn/e2e/run-e2e.ts`.

### `test:all`

Runs the complete Vitest suite with no lane exclusions. Use this for full visibility, not as the only signal for whether a deterministic runtime change is healthy.

## Release-gate interpretation

Runtime and unit tests that do not depend on external services are the primary release gate for local feature work.

External API, mobile/e2e, UI timing, and network-dependent test paths must be tracked separately so they do not hide regressions in deterministic runtime modules.

## Known flaky or external areas

Known areas to inspect before treating the full suite as red because of a new local feature:

- Sequential workflow tests that depend on external APIs or slow network timing.
- Chat-message tests with API timing behavior.
- Chat sidebar UI assertions that currently match multiple badges or empty suggestions differently than expected.
- Mobile/e2e API fallback tests under `sovereign-studio-rn/e2e/**`.

These tests should not be deleted. They should be moved behind an explicit integration/e2e command or given deterministic mocks.

## Rules for future changes

1. Do not mark external API timeout failures as caused by unrelated runtime changes unless the failing diff touches that path.
2. Keep remote-memory runtime tests deterministic and local.
3. Keep gateway contract tests mocked unless a separate integration command intentionally targets the VPS gateway.
4. If a runtime module touches user/contributor data, its tests must verify contributor scoping and shared-pattern preservation.
5. If a test requires a live service, document the required environment variable and keep it out of the default unit test gate.

## Remote Memory gate

The Remote Memory integration should be considered healthy when these local targets pass:

- `externalMemorySync.test.ts`
- `externalMemoryMonitoring.test.ts`
- `remoteMemoryUpdateIntake.test.ts`
- `remoteMemoryGatewayBridge.test.ts`
- `runtimeValidationCoverage.test.ts` if present in the branch

## Next cleanup step

After the lanes are proven in CI, record the exact failing files and error class in this document whenever `test:all` is red.

Long-term cleanup target:

- replace API timeout behavior with deterministic mocks where possible;
- keep live-service tests behind explicit env variables;
- keep mobile/browser e2e in its own job lane;
- never hide real deterministic runtime regressions behind broad skip rules.
