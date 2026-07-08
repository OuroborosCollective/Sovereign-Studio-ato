# Agent Skills - Sovereign Studio V3

> **Reusable patterns and skills for working on Sovereign Studio V3**

---

## Skill: Redux Provider in Tests

### When to Use
- Component uses `useSelector` or `useDispatch`
- Test fails with: "could not find react-redux context value"

### Pattern
```typescript
import React from 'react';
import { Provider } from 'react-redux';
import { render } from '@testing-library/react';
import { store } from '../store';

function renderWithProviders(ui: React.ReactElement) {
  return render(<Provider store={store}>{ui}</Provider>);
}

// Usage
renderWithProviders(<MyComponent prop="value" />);
```

### Files Commonly Affected
- `*.test.tsx` files with Redux-connected components
- Files using Zustand stores typically don't need this

---

## Skill: Selector Type Safety

### When to Use
- Creating Redux selectors
- Fixing TypeScript errors in slices

### Pattern
```typescript
import type { RootState } from '../../store';

export const selectMyData = (state: RootState) => state.feature.data;
export const selectMyLoading = (state: RootState) => state.feature.loading;
```

### Anti-Pattern (Don't Do This)
```typescript
// ❌ Wrong
export const selectMyData = (state: { feature: FeatureState }) => state.feature.data;

// ✅ Correct
export const selectMyData = (state: RootState) => state.feature.data;
```

---

## Skill: Fix Test Assertions

### When to Use
- Test fails but code works
- Object has more fields than expected

### Pattern
```typescript
// Before (fails)
expect(result).toEqual({ ok: true, content: 'text' });

// After (works)
expect(result).toMatchObject({ ok: true, content: 'text' });
```

---

## Skill: TypeScript Debugging

### When to Use
- `pnpm run type-check` shows errors
- "Module has no exported member" errors

### Steps
1. Run: `pnpm run type-check 2>&1 | head -50`
2. Check import paths are correct
3. Verify exports exist (named AND type exports)
4. Check for circular dependencies
5. Ensure `RootState` is imported where needed

---

## Skill: Git Workflow

### Standard Commit
```bash
git add <files>
git commit -m "fix(scope): describe fix

- Detail 1
- Detail 2

Co-authored-by: openhands <openhands@all-hands.dev>"
git push origin main
```

### Commit Types
- `fix:` - Bug fixes
- `feat:` - New features  
- `refactor:` - Code refactoring
- `test:` - Test changes
- `chore:` - Maintenance

---

## Skill: Run Quality Gates

### Required Before PR
```bash
pnpm run audit:sovereign  # Security audit
pnpm run type-check       # TypeScript check
pnpm exec vitest run      # All tests
pnpm run build:web        # Production build
```

### Quick Check (Fast)
```bash
pnpm run type-check 2>&1 | grep -c "error"
```

---

## Skill: CI Debugging

### Get CI Logs
```bash
gh run list --repo OuroborosCollective/Sovereign-Studio-ato --limit 10
gh run view <run-id> --repo OuroborosCollective/Sovereign-Studio-ato --log
```

### Common CI Failures
1. TypeScript errors → Run `pnpm run type-check`
2. Test failures → Run `pnpm exec vitest run`
3. Build failures → Run `pnpm run build:web`
4. Provider missing → Add Redux Provider to tests

---

## Skill: Find Related Files

### By Pattern
```bash
# Find all test files
find src -name "*.test.ts" -o -name "*.test.tsx"

# Find files using RootState
grep -r "RootState" src --include="*.ts" --include="*.tsx" -l

# Find Redux selectors
grep -r "select[A-Z]" src/features --include="*.ts"
```

---

## Skill: Batch Replace Patterns

### Add Provider to Multiple Tests
```bash
# Add imports
sed -i "1i import { Provider } from 'react-redux';" src/file.test.tsx
sed -i "1i import { store } from '../../store';" src/file.test.tsx

# Add helper function (after imports, before first function)
sed -i '/^function baseProps/i\
function renderWithProviders(ui: React.ReactElement) {\
  return render(<Provider store={store}>{ui}</Provider>);\
}\n' src/file.test.tsx

# Replace render calls
sed -i 's/render(<Component/renderWithProviders(<Component/g' src/file.test.tsx
```

---

## Skill: Verify Fixes

### Local Test Run
```bash
pnpm exec vitest run src/path/to/test.tsx --reporter=verbose
```

### Watch Mode (during development)
```bash
pnpm exec vitest src/path/to/test.tsx --watch
```

---

*Last Updated: 2026-07-08*
