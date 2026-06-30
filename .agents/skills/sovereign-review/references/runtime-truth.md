# Runtime Truth Sources

This document defines approved truth sources and anti-patterns for Sovereign Studio V3.

## Prime Directive

```
Build a runtime that produces truth.
Do not build a UI that invents truth.
The UI may only display verified runtime state.
```

## Approved Truth Sources

Use only these as the source of truth:

| Source | Type | Location |
|--------|------|----------|
| `sequentialRuntime` | Runtime state | `src/features/product/runtime/` |
| `repoSnapshotStatus` | GitHub tree | `src/features/github/` |
| `repoFiles` | File paths | `src/features/github/` |
| `scanRegistry` | Security scan | `src/runtime/` |
| `workflowReport` | CI status | `src/features/product/runtime/workflowWatch.ts` |
| `lastPackage` | Package build | `src/features/product/runtime/` |
| `latestGeneratedReview` | Code review | `src/features/product/brain/` |
| `diffReport` | Changes | `src/features/product/runtime/` |
| `telemetry` | Events | `src/features/product/runtime/sovereignTelemetry.ts` |
| `solutionPatternStore` | Patterns | `src/runtime/` |
| `remoteMemoryIntake` | Memory | `src/runtime/` |
| `automationStatus` | Automation | `src/runtime/` |

## DO NOT USE

The following are **NOT** valid truth sources:

- ❌ DOM text scraping
- ❌ Page text elements
- ❌ Static percentages
- ❌ Visual UI state alone
- ❌ Hardcoded success states
- ❌ Mock/stub data in production code

## Causal Runtime Chain

Every workflow must follow this chain:

1. **Action starts** → User click, API call, or event
2. **Action produces result** → API response, state change
3. **Result creates/updates state** → Runtime state mutation
4. **State allows/blocks/routers next action** → Conditional logic
5. **Next action is logically derivable** → No surprise jumps

```
Action → Result → State → Route → Next Action
```

**Anti-patterns:**

```typescript
// ❌ BAD - Jumps because button was clicked
if (buttonClicked) {
  showSuccess();  // No state derivation!
}

// ✅ GOOD - State drives UI
if (submitResult.status === 'success') {
  showSuccess();
}
```

## Intent Detection Pattern

Intent detection must be:
- In a testable runtime module
- Not in component render logic
- Tested against production functions

```typescript
// src/features/product/runtime/workerIntentDetector.ts
export function isOpenHandsExecutionIntent(text: string): boolean {
  const lower = text.toLowerCase();
  return /openhands|draft pr|pr erstellen|push zu|commit|baue|implementiere|fixe|repariere/i.test(lower);
}

export function isWorkerRetryIntent(text: string): boolean {
  const lower = text.toLowerCase();
  return /retry|erneut|nochmal|wiederholen|testen|versuch/i.test(lower);
}

export function isWorkerDiagnosticQuestion(text: string): boolean {
  const lower = text.toLowerCase();
  return /warum|wieso|hilfe|diagnose|was stimmt|fehler|problem/i.test(lower);
}
```

## Worker Retry Pattern

Worker retry must use real runtime path:

```typescript
// In BuilderContainer.tsx

// Helper that calls actual runtime submit
const retrySubmit = async (message: string) => {
  if (localRepoLoading || chatResponseBusy || isPublishing) return;
  _processSubmit(message);
};

// Card wiring
<WorkerBlockerCard
  onRetryWithMessage={(msg) => {
    setWorkerBlocker(null);
    retrySubmit(msg);  // Real action!
  }}
/>
```

**Anti-patterns:**

```typescript
// ❌ BAD - User must manually resubmit
setWishText(msg);

// ❌ BAD - DOM manipulation
document.querySelector('form').submit();

// ❌ BAD - Partial state, no visible UI
const [status, setStatus] = useState('idle');
setStatus('done');  // But 'status' never read!
```

## Progress Rule

No hardcoded progress indicators:

```typescript
// ❌ BAD - Hardcoded percentage
<div>75% complete</div>

// ❌ BAD - Fixed max steps
<div>Step 3 of 5</div>

// ✅ GOOD - Runtime-derived progress
<div>{currentStep} / {totalRuntimeSteps} - {currentAction}</div>
```

## Placeholder Mission Rule

Never accept vague placeholder text:

```typescript
// ❌ BAD - Must normalize or block
const mission = "Plan";  // No!
const mission = "Workflow Fehleranalyse";  // No!

// ✅ GOOD - Derive from repo or stop in safe state
const mission = deriveMissionFromRepo(repoFiles);
if (!mission) {
  return safeYellowState("Need concrete mission");
}
```

## Draft PR Rule

Draft PRs require real execution patches:

**Actionable targets:**
- `src/` - Source code
- `tests/` - Test files
- `android/` - Android native (if needed)
- `scripts/` - Build scripts
- `.github/workflows/` - CI
- Config files
- `README.md`
- `docs/`

**NOT acceptable:**
- Only `docs/SOVEREIGN_PLAN.md`
- Only workflow preview artifacts
- Plan-only output

## Error Handling Rule

Failures must route into repair flow:

```typescript
type ErrorResult = {
  ok: false;
  error: Error;
  traceId: string;
  retryable: boolean;
};

function handleError(result: ErrorResult): State {
  return {
    status: 'error',
    error: result.error,
    retryable: result.retryable,
    repairMission: deriveRepairMission(result),
  };
}
```

**Anti-pattern:**

```typescript
// ❌ BAD - Blind retry loop
while (attempts < 3) {
  try { callAPI(); break; }
  catch { attempts++; }
}
```

## Live-Path Integrity

No mocks, stubs, or fakes in production runtime:

```typescript
// ❌ BAD - Fake snapshot in production
const repoSnapshot = { files: fakeFiles, status: 'success' };

// ❌ BAD - Hardcoded green state
if (something) {
  return { status: 'success', data: [] };  // Fake!
}

// ✅ GOOD - Real state from runtime
const repoSnapshot = await loadRepoSnapshot(url);
```

**Exception:** Test fixtures are allowed in test files only.

## Functional Guards

Guards prevent unsafe output:

| Guard | Blocks |
|-------|--------|
| `assertGeneratedPackageReady` | Empty/incomplete packages |
| `assertRepoSnapshotValid` | Empty repo, folder-only |
| `assertNoUnsafePaths` | `.env`, `.git/`, `node_modules/` |
| `assertUniqueFilePaths` | Duplicate generated paths |

Never bypass guards in publishing paths.

## Testing Requirements

Every new runtime route needs tests:

| Test Case | Description |
|-----------|-------------|
| Success case | Happy path works |
| Failure case | Error handled gracefully |
| Invalid input | Bad input rejected |
| State transition | State machine transitions correctly |
| Guard behavior | Guards block appropriately |

## Completion Verification

Before claiming work is done:

1. ✅ Real issue was addressed
2. ✅ Fix runs in live path
3. ✅ Tests or validation added
4. ✅ No mock/stub/fake in live code
5. ✅ No hardcoded UI truth
6. ✅ No plan-only Draft PR
7. ✅ Flow understandable for non-developer
