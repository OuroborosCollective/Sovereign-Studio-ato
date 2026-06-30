---
name: sovereign-review
description: This skill should be used when reviewing PRs in the Sovereign Studio V3 repository (OuroborosCollective/Sovereign-Studio-ato), specifically for "make PR #XXX review-ready", "fix review blockers", "address review comments", "clean up partial states", "remove unused variables", "verify test coverage", or when a PR has CodeQL warnings, TypeScript errors, or needs quality gate validation before merge.
---

# Sovereign Studio PR Review Skill

This skill provides patterns and procedures for making PRs review-ready in the Sovereign Studio V3 repository. Follow these guidelines to address review blockers efficiently.

## Repository Context

Sovereign Studio V3 is a hybrid mobile/desktop application that serves as an autonomous repository architect. The project uses:
- React 19, TypeScript, Vite for frontend
- Capacitor 6 for mobile
- Zustand for state management
- Vitest for testing
- Draft PR publishing via GitHub REST API

## Prime Directive

```
Build a runtime that produces truth.
Do not build a UI that invents truth.
The UI may only display verified runtime state.
```

## Critical Review Patterns

### 1. Unused Partial States

When CodeQL or static audit reports unused variables in components:

**DO NOT:**
- Create stub UI components that aren't actually rendered
- Add `setX` calls that do nothing visible
- Leave partial state hooks in the codebase

**DO:**
- Remove unused state entirely
- Keep only the logic that has a visible/runtime path
- If functionality isn't ready, remove the state and the setter calls

**Example:**
```typescript
// ❌ BAD - unused state
const [showSlashCommands, setShowSlashCommands] = useState(false);
const [selectedSlashIndex, setSelectedSlashIndex] = useState(0);
// Only setShowSlashCommands is called, but showSlashCommands is never read

// ✅ GOOD - remove unused states
const slashCommands = [
  { cmd: '/analyze', action: 'analyze' },
  { cmd: '/fix', action: 'fix' },
];
// Direct logic, no popup UI state
```

### 2. Intent Detection in Runtime Module

Intent detection logic must be:
- Extracted to a testable runtime module (not inline in components)
- Tested against real production functions
- Not reimplemented in test files

**Required Pattern:**
```
src/features/product/runtime/workerIntentDetector.ts  ← Real module
src/features/product/runtime/workerIntentDetector.test.ts  ← Tests the real module
```

**NOT:**
```
Component.tsx  ← Has inline intent functions
Component.test.ts  ← Reimplements the same logic (duplication)
```

### 3. Worker Retry Runtime Path

Worker retry must use the real runtime path, not DOM manipulation:

**Correct Pattern:**
```typescript
// In BuilderContainer.tsx
const retrySubmit = async (message: string) => {
  if (localRepoLoading || chatResponseBusy || isPublishing) return;
  _processSubmit(message);  // Real runtime action
};

// WorkerBlockerCard wiring
<WorkerBlockerCard
  onRetryWithMessage={(msg) => {
    setWorkerBlocker(null);
    retrySubmit(msg);  // Direct runtime call
  }}
/>
```

**Anti-Patterns (DO NOT USE):**
```typescript
// ❌ BAD - Sets wishText and expects user to resubmit
setWishText(msg);

// ❌ BAD - DOM manipulation
document.querySelector('form').submit();

// ❌ BAD - Incomplete state with no visible UI
const [shareStatus, setShareStatus] = useState('idle');
// setShareStatus called but shareStatus never read
```

### 4. Test Coverage for New Components

Every new component requires tests covering:

| Test Case | Description |
|-----------|-------------|
| Success case | Component renders with valid props |
| Failure case | Component handles error state |
| Invalid input | Component validates input |
| State transitions | Component responds to state changes |
| Guard behavior | Guards prevent invalid actions |

**Minimum expected:**
- `ComponentName.test.tsx` for React components
- `ModuleName.test.ts` for runtime modules

### 5. Quality Gates

Before claiming a PR is review-ready, verify:

```bash
# TypeScript
npx tsc --noEmit

# Tests (specific to changed files)
npx vitest run \
  src/features/product/components/ChatMarkdown.test.tsx \
  src/features/product/components/DraftPrCard.test.tsx \
  src/features/product/components/WorkerBlockerCard.test.tsx

# Static audit (if available)
npm run audit:sovereign

# Build (if environment supports)
npm run build
```

### 6. Git Hygiene

**Check for artifacts before commit:**
```bash
git diff --name-only origin/main...HEAD
# Should NOT contain:
# - android/ directories
# - dist/, build/ output directories
# - node_modules/
# - *.apk, *.aab files
```

**Commit message format:**
```
<type>: <short description>

<optional body with details>
- Change 1
- Change 2

Co-authored-by: openhands <openhands@all-hands.dev>
```

## Common Review Blockers

| Blocker | Solution |
|---------|----------|
| Unused partial states | Remove states without visible UI path |
| Reimplemented test logic | Extract to runtime module, import in tests |
| Fake retry (setWishText) | Use real runtime action: `retrySubmit(msg)` |
| Missing test coverage | Add ComponentName.test.tsx with all test cases |
| Android/build artifacts | Remove from git tracking, exclude in .gitignore |
| CodeQL warnings | Fix or remove the flagged code |

## Task Tracking Pattern

Use task_tracker for complex review fixes:

```
T-1 [STATUS] Description
    └─ Notes on what was done
T-2 [STATUS] Next task
    └─ Pending items
```

Status values: `todo`, `in_progress`, `done`

## References

### Reference Files

- **`references/pr-cleanup-checklist.md`** - Step-by-step cleanup procedure
- **`references/runtime-truth.md`** - Truth sources and anti-patterns

### Example Scripts

- **`scripts/validate-pr.sh`** - Validate PR has no artifacts

## Completion Criteria

Before finishing a review fix:

1. ✅ No unused partial states remain
2. ✅ No CodeQL warnings from new code
3. ✅ TypeScript passes
4. ✅ Tests pass (67+ for full coverage)
5. ✅ No Android/build artifacts
6. ✅ Worker retry uses real runtime path
7. ✅ Intent detection in runtime module (tested)
8. ✅ PR description matches actual state

**DO NOT claim completion while CodeQL/audit still reports issues from this PR.**
