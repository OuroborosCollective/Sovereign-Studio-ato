---
name: sovereign-release-ready-error-family-hunt
description: Run persisted evidence-first release hunts across distinct failure families until the bounded stop condition is proven.
---

Use this skill when the mission asks for a Release-Ready error-family hunt in Sovereign Studio ATO.

## Persisted intake

Before choosing work, require evidence for the current persisted hunt state, latest owner-scoped Agents SDK run, open Draft PR state, relevant GitHub Actions gates, and affected runtime surfaces. Do not infer any of these from UI wording.

## Family selection

Continue the currently active failure family when it has an unresolved reproducible finding or blocker. Otherwise choose the strongest not-yet-checked family from real evidence. After one evidenced nullfind, switch to a different family for the next run.

## Required causal loop

1. Name exactly one failure family.
2. Define a real reproduction and its expected evidence.
3. Separate the causal defect from symptoms and unrelated gates.
4. Recommend only the smallest causal fix in an isolated workspace.
5. Require a regression test through the real path.
6. Require relevant fast, standard, and release gates.
7. Permit at most one Draft PR at a time.
8. Treat only unrelated Android gates as skippable, and record why they are unrelated.
9. Require immutable deployment evidence when a verified backend or MCP fix changes production code.
10. Persist the final family outcome as FINDING, NULLFIND, or BLOCKED.

## Judge output contract

For a release-hunt mission, populate the structured verdict fields:

- `hunt_outcome`: `FINDING`, `NULLFIND`, or `BLOCKED`.
- `error_family`: the single family inspected in this run.
- `next_error_family`: the next distinct family only after an evidenced `NULLFIND`; otherwise empty.
- `nullfind_confirmed`: true only when the required reproduction and relevant gates produced no defect.

A nullfind must not be inferred from missing evidence. A finding resets any termination streak. A blocker neither advances nor resets an already persisted streak unless the supplied persisted state explicitly says so.

## Termination

The overall hunt may stop only when supplied persisted evidence proves three immediately consecutive NULLFIND runs in three different error families. Never calculate or claim this sequence from prose alone. Until that condition is proven, set a concrete next action.

## Task lifecycle truth

Historical recovery tasks remain immutable evidence. They must be displayed as historical and must not be counted as active blockers. Only the task identified by the persisted run as current may expose `isActiveBlocker=true`. Never rewrite old task status merely to make the widget look green.

## Release boundary

The Agents SDK plans, classifies, and judges. Repository writes, tests, PR creation, merge, deployment, rollback, database work, and owner approvals remain bounded Sovereign Operator actions. Never auto-merge and never expose protected values.
