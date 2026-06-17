# Workflow Repair Planner

The Workflow Repair Planner is the bridge between Workflow Watch and the Sovereign Action Builder.

It exists so the app does not stop at `CI failed`. Instead, it turns failed workflow checks into a focused repair mission that can be reviewed, generated and published through the same guarded Draft PR path.

## Flow

```txt
Draft PR created
↓
Workflow Watch reads commit statuses and check-runs
↓
Failed checks are mapped into repair actions
↓
Repair tab shows mission + likely files
↓
User loads repair mission into Builder
↓
Sovereign package builder runs
↓
Functional guards run
↓
Generated file review runs
↓
Draft PR publishing rules run again
```

## What it does

The planner reads a `WorkflowWatchReport` and creates a `WorkflowRepairPlan`.

It detects:

- failed checks
- pending checks
- access or token errors
- green/no-repair states
- missing workflow data

For failed checks it creates:

- a focused mission text
- one repair action per failing check
- likely file groups to inspect
- severity: `none`, `low`, `medium`, or `high`
- a `blocked` flag when repair should not start yet

## What it does not do

It does not auto-merge.

It does not bypass generated-file review.

It does not claim exact root cause from a check name alone.

It does not edit files directly. It only prepares a focused mission that must still pass through the Sovereign package builder and guards.

## Suggested file mapping

The planner maps failing check text to likely file groups:

| Check text hint | Likely files |
| --- | --- |
| lint / eslint | `src/**/*`, `eslint.config.*`, `package.json` |
| test / vitest / jest | `src/**/*.test.ts`, `src/**/*.test.tsx`, `package.json` |
| build / vite / tsc / type | `tsconfig.json`, `vite.config.*`, `src/**/*` |
| workflow / action / ci | `.github/workflows/*` |
| lockfile / pnpm / npm / install | `package.json`, `pnpm-lock.yaml`, `package-lock.json` |

Fallback is documentation-oriented, because the system should avoid pretending to know a code fix when only weak workflow information is available.

## Safety rules

- Pending checks block repair generation.
- Green checks block repair generation because no repair is needed.
- Failed checks allow repair mission generation.
- Token/access errors can generate docs/runtime repair guidance, not blind code changes.
- All resulting packages must still pass functional guards and generated-file review.

## Related files

```txt
src/features/product/runtime/workflowWatch.ts
src/features/product/runtime/workflowRepairPlan.ts
src/features/product/components/WorkflowWatchPanel.tsx
src/features/product/components/WorkflowRepairPanel.tsx
src/features/product/runtime/workflowRepairPlan.test.ts
src/features/product/runtime/sovereignStructure.test.ts
src/features/product/runtime/runtimeValidationCoverage.ts
```
