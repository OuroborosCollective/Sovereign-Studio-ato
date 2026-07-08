# Best Practices - Sovereign Studio V3

> **Guidelines for agents working on Sovereign Studio V3**

---

## Testing Best Practices

### 1. Always Wrap Redux Components in Provider

**Rule:** Any component using `useSelector` or `useDispatch` MUST have a Redux Provider wrapper in tests.

```typescript
// ✅ CORRECT
import { Provider } from 'react-redux';
import { store } from '../../store';

function renderWithProviders(ui: React.ReactElement) {
  return render(<Provider store={store}>{ui}</Provider>);
}

it('renders correctly', () => {
  renderWithProviders(<MyComponent />);
});

// ❌ WRONG - Will fail with context error
it('renders correctly', () => {
  render(<MyComponent />);
});
```

### 2. Use `toMatchObject` for Partial Matching

Prefer `toMatchObject` over `toEqual` when:
- Object has dynamic fields
- Object has more fields than you're testing
- Only specific fields matter

```typescript
// ✅ Better
expect(result).toMatchObject({ ok: true, data: expectedData });

// ❌ Fragile - breaks if any new fields added
expect(result).toEqual({ ok: true, data: expectedData, timestamp: expect.anything() });
```

### 3. Mock Global Functions Properly

```typescript
// ✅ Mock before test
beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});
```

---

## TypeScript Best Practices

### 1. Always Use RootState for Selectors

```typescript
// ✅ CORRECT
import type { RootState } from '../../store';
export const selectData = (state: RootState) => state.feature.data;

// ❌ WRONG
export const selectData = (state: { feature: FeatureState }) => state.feature.data;
```

### 2. Export Both Values and Types

```typescript
// ✅ Complete export
export const myFunction = () => { /* ... */ };
export type MyType = { /* ... */ };

// ❌ Incomplete
export const myFunction = () => { /* ... */ };
// Type not exported - breaks consumers
```

### 3. Check Imports Match Exports

Common mistake:
```typescript
// In module
export const COST_CONFIG = { /* ... */ };

// In consumer - WRONG
import { LEGACY_COST_CONFIG } from './config';  // Doesn't exist!

// CORRECT
import { COST_CONFIG } from './config';
```

---

## Git Best Practices

### 1. Descriptive Commit Messages

```bash
# ✅ Good
git commit -m "fix(billing): resolve TypeScript type errors in selectors
- Add RootState import
- Update all selector signatures
- Add missing exports"

# ❌ Bad
git commit -m "fix stuff"
```

### 2. Include Co-authored-by

```bash
git commit -m "fix(module): describe change

Co-authored-by: openhands <openhands@all-hands.dev>"
```

### 3. Group Related Changes

One commit = one logical change:
- ❌ "fix billing AND add new feature AND refactor store"
- ✅ Three separate commits

---

## Code Organization

### 1. Import Order

```typescript
// 1. React / Core
import React from 'react';

// 2. External libraries
import { Provider } from 'react-redux';

// 3. Internal modules
import { store } from '../../store';
import { selectData } from '../slice';

// 4. Types
import type { MyType } from './types';
```

### 2. Test File Co-location

```
src/features/billing/
├── billingSlice.ts          # Source
├── billingSlice.test.ts      # Tests
└── hooks/
    └── useBilling.ts        # Hook
    └── useBilling.test.ts   # Tests
```

---

## Debugging Workflow

### 1. Reproduce Locally First

```bash
# Run specific test
pnpm exec vitest run src/path/to/test.tsx

# Run with verbose output
pnpm exec vitest run src/path/to/test.tsx --reporter=verbose

# Run in watch mode
pnpm exec vitest src/path/to/test.tsx --watch
```

### 2. Check TypeScript Explicitly

```bash
pnpm run type-check 2>&1 | grep -E "error TS" | head -20
```

### 3. Check CI Logs

```bash
# Find failing run
gh run list --repo OuroborosCollective/Sovereign-Studio-ato --limit 5

# Get logs
gh run view <run-id> --log 2>&1 | tail -100
```

---

## Quality Gates

Always run these before committing:

```bash
# 1. Type check
pnpm run type-check

# 2. Tests
pnpm exec vitest run

# 3. Security audit
pnpm run audit:sovereign

# 4. Build
pnpm run build:web
```

---

## Anti-Patterns to Avoid

### ❌ Don't Skip Tests to "Make CI Pass"
Fix the underlying issue instead.

### ❌ Don't Use `any` to Silence Errors
Use proper types or `unknown` with type guards.

### ❌ Don't Bypass Redux Provider in Tests
Components need their context to render correctly.

### ❌ Don't Hardcode Test Data
Use factories or fixtures for consistent test data.

### ❌ Don't Forget to Unstub Globals
Always clean up in `afterEach`.

---

## Documentation

### When to Update Docs
- New patterns discovered
- Common mistakes identified
- Architecture changes
- New tooling added

### Where to Document
- `AGENTS_KNOWLEDGE.md` - Learned patterns, troubleshooting
- `AGENTS_SKILLS.md` - Reusable skill patterns
- `AGENTS_BEST_PRACTICES.md` - Guidelines and rules
- `docs/` - Architecture documentation
- Code comments - Implementation details

---

*Last Updated: 2026-07-08*
