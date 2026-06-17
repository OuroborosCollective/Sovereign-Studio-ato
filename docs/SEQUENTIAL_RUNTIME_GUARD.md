# Sequential Runtime Guard

The Sequential Runtime Guard prevents Sovereign Studio actions from starting on top of each other.

It exists because Full Auto and manual buttons can otherwise trigger overlapping operations such as package generation, diff loading, Draft PR publishing and workflow watching.

## Rule

```txt
Only one runtime step may be active at a time.
A downstream step may only start when its required prior data exists.
A failed step records failure and blocks confusing follow-up behavior.
The guard validates its own internal state before and after transitions.
```

## Guarded steps

```txt
repo-load
package-build
diff-load
draft-pr-publish
workflow-watch
repair-plan
```

## Required data

| Step | Required data |
| --- | --- |
| `repo-load` | none |
| `package-build` | loaded repo snapshot |
| `diff-load` | loaded repo snapshot + generated package |
| `draft-pr-publish` | loaded repo snapshot + generated package |
| `workflow-watch` | loaded repo snapshot + Draft PR commit SHA |
| `repair-plan` | loaded repo snapshot + Workflow Watch report |

## Self validation

The guard is not trusted just because it is the guard. It validates its own state through:

```txt
validateSequentialRuntimeState
assertSequentialRuntimeStateValid
```

The self-validation checks:

- every known step has a step record
- step records match their step id
- at most one step is `running`
- `activeStep` points to the running step
- no running step exists without `activeStep`
- `activeStep` does not exist without a running record
- history steps are known
- history sequence numbers are strictly increasing
- state sequence matches the latest history event, with warning if not

`canStartSequentialStep`, `startSequentialStep` and `finishSequentialStep` call the self-validation path so a corrupted guard state fails closed instead of silently continuing.

## App integration

The guard is wired into:

```txt
src/App.tsx
```

It wraps:

- Load Repo
- Build Package / Ideen / Fehler
- Load Source Snapshots for Diff
- Draft PR erstellen
- Workflow Watch
- Use Repair Mission in Builder

The app also exposes a `Runtime` tab via:

```txt
src/features/product/components/SequentialRuntimePanel.tsx
```

## Why this matters

Without this layer, Full Auto could accidentally start several asynchronous flows at once. That creates confusing states like:

```txt
package-build running
while draft-pr-publish starts
while workflow-watch starts without a commit SHA
```

The guard prevents that by keeping one active step lock and a transition history.

## What it does not replace

The Sequential Runtime Guard does not replace:

- repo snapshot validation
- functional guards
- generated file review
- diff preview
- GitHub auth session checks
- Draft PR publisher validation
- Workflow Watch

It only enforces runtime order.

## Related files

```txt
src/features/product/runtime/sequentialRuntimeGuard.ts
src/features/product/runtime/sequentialRuntimeGuard.test.ts
src/features/product/components/SequentialRuntimePanel.tsx
src/App.tsx
src/features/product/runtime/runtimeValidationCoverage.ts
src/features/product/runtime/sovereignStructure.test.ts
```
