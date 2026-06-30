# PR Cleanup Checklist

Use this checklist when fixing review blockers for Sovereign Studio PRs.

## Pre-Flight

1. [ ] Read the review comments to understand all blockers
2. [ ] Identify which files need changes
3. [ ] Plan changes in task tracker

## Phase 1: Unused Partial States

### Step 1: Find Unused States

```bash
grep -n "useState" src/features/product/containers/BuilderContainer.tsx
```

### Step 2: Check Usage

```bash
# For each state variable, check if it's read anywhere
grep -n "variableName\b" src/path/Component.tsx | grep -v "setVariableName"
```

### Step 3: Remove Unused States

**Scenario A: State only has setter calls, never read**
```typescript
// REMOVE: const [showPopup, setShowPopup] = useState(false);
// REMOVE: All setShowPopup(false) calls if popup doesn't exist
```

**Scenario B: State has partial usage (setX called, X never read)**
```typescript
// REMOVE: const [shareStatus, setShareStatus] = useState('idle');
// KEEP: The logic that calls setShareStatus (move inline if needed)
```

### Step 4: Verify No Breakage

```bash
npx tsc --noEmit
```

## Phase 2: Intent Detection Runtime Module

### If intent functions are inline in component:

1. **Extract to runtime module:**
```typescript
// src/features/product/runtime/workerIntentDetector.ts
export function isOpenHandsExecutionIntent(text: string): boolean {
  // production logic here
}
```

2. **Update component imports:**
```typescript
import { isOpenHandsExecutionIntent } from '../runtime/workerIntentDetector';
```

3. **Update tests to import from module:**
```typescript
import { isOpenHandsExecutionIntent } from '../runtime/workerIntentDetector';
```

4. **Delete reimplemented test logic:**
```bash
# Remove functions from Component.test.ts that duplicate runtime module
```

## Phase 3: Worker Retry Path

### Find the retry implementation:

```bash
grep -n "onRetry\|retrySubmit\|_processSubmit" src/features/product/containers/BuilderContainer.tsx
```

### Verify correct pattern:

```typescript
// ✅ CORRECT - real runtime action
const retrySubmit = async (message: string) => {
  if (busyStates) return;
  _processSubmit(message);
};

// ❌ WRONG - fake retry
const handleRetry = () => {
  setWishText(msg);  // User must submit again!
};
```

### Fix WorkerBlockerCard wiring:

```typescript
<WorkerBlockerCard
  onRetryWithMessage={(msg) => {
    setWorkerBlocker(null);
    retrySubmit(msg);  // Direct runtime call
  }}
/>
```

## Phase 4: Test Coverage

### Check existing tests:

```bash
ls src/features/product/components/*.test.tsx
ls src/features/product/runtime/*.test.ts
```

### Add missing tests:

```typescript
// src/features/product/components/ComponentName.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

describe('ComponentName', () => {
  it('renders correctly', () => {
    render(<ComponentName {...props} />);
    expect(screen.getByTestId('component')).toBeTruthy();
  });

  it('handles click', () => {
    const onClick = vi.fn();
    render(<ComponentName onClick={onClick} {...props} />);
    fireEvent.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalled();
  });
});
```

## Phase 5: Quality Gates

Run in order:

```bash
# 1. TypeScript
npx tsc --noEmit

# 2. Tests
npx vitest run \
  src/features/product/components/ChatMarkdown.test.tsx \
  src/features/product/components/DraftPrCard.test.tsx \
  src/features/product/components/WorkerBlockerCard.test.tsx \
  src/features/product/runtime/workerIntentDetector.test.ts \
  src/features/product/runtime/chatExportRuntime.test.ts

# 3. Audit
npm run audit:sovereign

# 4. Build (if supported)
npm run build
```

## Phase 6: Git Hygiene

### Check for artifacts:

```bash
git diff --name-only origin/main...HEAD
```

**Should NOT contain:**
- `android/` directories
- `dist/`, `build/` directories
- `node_modules/`
- `*.apk`, `*.aab`, `*.aar` files
- `.gradle/` files

### If artifacts found:

```bash
git rm -r --cached android/ dist/ build/ 2>/dev/null
# Add exclusion to .gitignore if needed
```

### Commit:

```bash
git add -A
git commit -m "fix: <short description>

- Removed unused partial states
- Fixed worker retry runtime path
- Added missing tests

Co-authored-by: openhands <openhands@all-hands.dev>"
```

## Phase 7: Push and Merge

```bash
# Push to feature branch
git push

# Merge to main (if authorized)
git checkout main
git pull
git merge feature/branch-name --no-edit
git push origin main
```

## Review Sign-Off Checklist

Before marking PR as ready for review:

- [ ] All CodeQL warnings fixed
- [ ] No unused partial states
- [ ] TypeScript passes
- [ ] Tests pass (67+)
- [ ] No artifacts in diff
- [ ] Worker retry is real runtime action
- [ ] Intent detection in runtime module
- [ ] PR description updated with correct test count
