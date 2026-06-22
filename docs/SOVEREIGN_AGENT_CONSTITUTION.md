# Sovereign Agent Constitution

This document explains the permanent integration rules for `NOCODESTUDIO Sovereign Tool / Sovereign-Studio-ato`.

Agents must treat this file and root `AGENTS.md` as policy before changing code.

## 1. Runtime truth only

The product must never rely on UI appearance as truth.

Allowed truth sources include runtime state, repo snapshots, package output, guard reports, telemetry, workflow reports, and memory stores.

Disallowed truth sources include DOM text scraping, visual progress bars, hardcoded percentages, and hardcoded UI-only step maps.

## 2. Causal flow

Every internal workflow must be explainable as:

```text
action -> result -> state -> next allowed action
```

If a future action cannot be logically derived from the previous result/state, it must not run.

## 3. Dynamic step plans

Progress is not a percentage.
Progress is the visible representation of the current runtime plan.

The total number of steps must come from the real planned workflow. It may be 3, 4, 5, 7, or any other valid number required by the current flow.

The UI must display the plan; it must not define the plan.

## 4. Placeholder missions

The user should not have to provide developer-perfect text.

When the mission is vague or default text, the tool must use repo analysis, findings, workflow state, telemetry, and memory patterns to derive a concrete mission. If no safe mission can be derived, the system must stop in a yellow state and explain the next safe action.

## 5. Draft PR safety

Draft PR creation is allowed only after real execution patches exist and pass guards.

Plan-only documents and generated preview artifacts are not enough.

## 6. No fake live path

Production runtime code must not contain mocks, stubs, facades, fake success values, fake snapshots, or hardcoded green states.

Mocks and fixtures are allowed only inside tests.

## 7. Repo Insight contract

Repo Insight must be an action engine, not a decorative panel.

Each suggestion should provide:

- title
- reason
- affected files
- expected benefit
- risk
- executable mission

Suggestion buttons must set executable missions.

## 8. Pattern Memory contract

Pattern Memory may guide decisions, but every pattern-derived action must be validated against the current repo state, runtime guards, and tests.

## 9. Repair contract

Failures must not loop blindly.

A failure must produce a recorded error, classify the state, and route to a repair mission or a safe user-visible stop.

## 10. Completion gate

Before work is called complete, verify:

- live-path integration
- runtime checks
- validation
- useful tests
- no hardcoded UI truth
- no mock/stub/facade in production
- no plan-only Draft PR path
- clear non-developer UX

If any item is not satisfied, report the blocker rather than claiming success.
