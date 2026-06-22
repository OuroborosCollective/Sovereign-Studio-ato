# Sovereign Studio Copilot Instructions

Before changing code, read `AGENTS.md` at the repository root.

This project is `NOCODESTUDIO Sovereign Tool / Sovereign-Studio-ato`.
Do not mix it with Areloria, WASD, MMORPG, ARE logic, or unrelated game paths unless explicitly requested.

## Non-negotiable project rules

1. Runtime creates truth. UI only displays it.
2. Every action must produce a result.
3. Every result must create or update state.
4. Every next action must be allowed, blocked, or routed by that state.
5. Do not use DOM text, visual UI state, static percentage progress, or hardcoded progress maps as truth.
6. Do not use a fixed maximum step count. Step totals must come from the planned runtime flow.
7. Do not let placeholder missions enter package-build as-is.
8. No mocks, stubs, facades, fake snapshots, fake success states, or hardcoded green states in the live path.
9. Draft PRs require real execution patches and must not be plan-only.
10. Every new runtime path needs validation and useful tests.

## Required implementation shape

For workflow logic, use this causal chain:

```text
action -> result -> state -> next allowed action -> next result -> next state
```

For progress display, use this shape:

```text
currentStep / plannedRuntimeSteps - current runtime action
```

The UI must receive or derive this from runtime events/state. It must not invent it.

## Placeholder handling

These examples must be normalized into a concrete repo-derived mission or stopped safely before package-build:

- `README + Update History`
- `Mach weiter`
- `Fehler`
- `Ideen`
- `Plan`
- `Workflow Fehleranalyse + Runtime Check + Test Plan`

## Draft PR guard

Allowed actionable output may touch:

- `src/`
- `tests/`
- `android/`
- `scripts/`
- `.github/workflows/`
- config files
- `README.md`
- real `docs/`

`docs/SOVEREIGN_PLAN.md` is plan-only and must not count as actionable output.

## Before claiming success

Verify or report blockers for:

- live-path integration
- runtime checks
- validation
- tests
- no plan-only Draft PR path
- no mock/stub/facade in production code
- understandable UX for non-developers
