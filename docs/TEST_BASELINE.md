# Test Baseline

This document records the current test status after the Remote Memory App Bridge integration landed on `main`.

## Current baseline

Reported result after running the full test suite:

- 477 tests passed.
- 19 tests failed.
- Build completed successfully.
- The known failures are pre-existing API-dependent timeout tests and chat-message tests, not introduced by the Remote Memory App Bridge codemod.

## Release-gate interpretation

Runtime and unit tests that do not depend on external services are the primary release gate for local feature work.

External API, mobile/e2e, and network-dependent test paths must be tracked separately so they do not hide regressions in deterministic runtime modules.

## Known flaky or external areas

Known areas to inspect before treating the full suite as red because of a new local feature:

- Sequential workflow tests that depend on external APIs or slow network timing.
- Chat-message tests with API timing behavior.
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

Split the test commands into clear lanes:

- `test:unit` for deterministic local runtime and component tests.
- `test:integration` for tests that need mocked or live API boundaries.
- `test:e2e` for mobile/browser flows.
- `test:all` for the full suite.

Until that split exists, record the exact failing files and error class in this document whenever the full suite is run.
