# MASTER ERROR FAMILIES & CODEFIX HUNTING — Implementation Status Board
**Version:** 2.0  
**Purpose:** Expert-level error family classification, fix patterns, and alpha→beta→release workflows  
**Audience:** Senior engineers, code architects, autonomous agents, debugging experts

---

## 0. EXECUTIVE SUMMARY: ERROR FAMILY TAXONOMY

### Complete Error Family Tree
```
ERROR_FAMILY
├── SYNTAX_ERRORS (Parsing, tokenization)
│   ├── JavaScript/TypeScript syntax violations
│   ├── JSX/TSX markup errors
│   ├── Import/export statement issues
│   └── Operator precedence bugs
├── TYPE_ERRORS (Type system violations)
│   ├── Generic constraint violations
│   ├── Union type narrowing failures
│   ├── Null/undefined propagation
│   ├── Implicit any escapes
│   └── Readonly vs mutable contracts
├── RUNTIME_ERRORS (Execution failures)
│   ├── Null pointer dereference
│   ├── Array bounds violations
│   ├── Missing method/property access
│   ├── Infinite loops / stack overflow
│   └── Memory leaks
├── ASYNC_ERRORS (Promise, callback, async/await)
│   ├── Unhandled promise rejections
│   ├── Callback hell / race conditions
│   ├── Missing await in async context
│   ├── setTimeout/setInterval side effects
│   └── AbortController misuse
├── STATE_ERRORS (State machine violations)
│   ├── Transition from invalid state
│   ├── State desynchronization
│   ├── Lost updates / data races
│   ├── Stale closure captures
│   └── React hook rule violations
├── ARCHITECTURE_ERRORS (Structure violations)
│   ├── Circular dependencies
│   ├── Mixed concerns (UI + business logic)
│   ├── God component anti-pattern
│   ├── Hard-coded secrets
│   └── Missing contract boundaries
├── SECURITY_ERRORS (Security vulnerabilities)
│   ├── Exposed secrets / API keys
│   ├── SQL/NoSQL injection risks
│   ├── XSS vulnerabilities
│   ├── CSRF/CORS misconfigurations
│   └── Authentication bypass
├── PERFORMANCE_ERRORS (Performance degradation)
│   ├── N+1 queries / inefficient loops
│   ├── Memory leaks from event listeners
│   ├── Unnecessary re-renders (React)
│   ├── Blocking main thread
│   └── Large bundle size
├── TEST_ERRORS (Test infrastructure)
│   ├── Flaky/intermittent tests
│   ├── Test isolation violations
│   ├── Mock/stub misconfigurations
│   ├── Missing edge case coverage
│   └── Hard-to-debug test failures
├── DEPLOY_ERRORS (Deployment & infrastructure)
│   ├── Environment variable mismatches
│   ├── Missing build artifacts
│   ├── Database migration failures
│   ├── Rollback/rollforward issues
│   └── Feature flag misconfiguration
└── INTEGRATION_ERRORS (Cross-system failures)
    ├── API contract violations
    ├── GitHub/SDK integration issues
    ├── Worker/serverless execution failures
    ├── R2/storage access denied
    └── Third-party service timeouts
```

---

## 1. MASTER ERROR DIAGNOSTIC FLOW

### 1.1 Error Triage Decision Tree
```
ERROR DETECTED (from any source: test, build, runtime, CI)
    ↓
┌─→ Classify by SOURCE
│   ├── Build-time? → SYNTAX_ERROR or TYPE_ERROR
│   ├── Test-time? → TEST_ERROR (likely) + underlying family
│   ├── Runtime? → RUNTIME_ERROR, ASYNC_ERROR, STATE_ERROR
│   ├── CI/Deploy? → DEPLOY_ERROR
│   └── Production? → Same + SECURITY_ERROR check
│
├─→ Extract CANONICAL_ERROR_MESSAGE
│   ├── Parse stack trace
│   ├── Identify line number(s)
│   ├── Extract variable names involved
│   └── Note error type (TypeError, ReferenceError, etc.)
│
├─→ Determine SEVERITY
│   ├── CRITICAL: Blocks release, security risk, data loss
│   ├── HIGH: Feature broken, test suite fails
│   ├── MEDIUM: Workaround exists, performance degraded
│   └── LOW: Code quality, warnings, type strict
│
├─→ Identify ROOT_CAUSE_PATTERN
│   ├── Is this a KNOWN_PATTERN? (check master list below)
│   ├── Novel error? → Classify new family
│   └── Evidence: log output, test failure, user report
│
├─→ REPAIR_FLOW
│   ├── Small fix? → Direct SEARCH/REPLACE patch
│   ├── Requires tests? → Test-first approach
│   ├── Architecture issue? → Refactor in PR
│   ├── Security? → Emergency protocol
│   └── Deploy issue? → Rollback + post-mortem
│
└─→ VERIFY_RESOLUTION
    ├── Run green gates (type-check, test, audit)
    ├── Regression test on related code
    ├── Deploy to staging if applicable
    └── Approve for release
```

---

## 2. ERROR FAMILY DEEP DIVES WITH EXPERT FIXES

### 2.1 SYNTAX_ERRORS

#### Pattern: Missing Import
```typescript
// ❌ SYMPTOM
"ReferenceError: MyComponent is not defined"
// File: src/features/builder/BuilderContainer.tsx, line 42

// 🔍 DIAGNOSIS
const MyComponent = () => <div>Content</div>;  // Defined here
export default SomeOtherComponent;  // But not exported!

// ✓ EXPERT FIX (SEARCH/REPLACE)
OLD:
export default SomeOtherComponent;

NEW:
export { MyComponent };
export default SomeOtherComponent;

// 🎯 WHY THIS WORKS
// - Named export added alongside default
// - Allows circular import resolution
// - No need to refactor entire module

// ⚠️ PREVENT
// - Add import linting rule: "no-unused-vars"
// - Use IDE import quickfix (Ctrl+.)
// - Annual audit: grep unused exports
```

#### Pattern: JSX Fragment Issues
```typescript
// ❌ SYMPTOM
"SyntaxError: Unexpected token <"
// or: "Element type is invalid, expected string or class..."

// 🔍 ROOT CAUSE (Common in BuilderContainer)
const Component = () => {
  return (
    <div>Item 1</div>
    <div>Item 2</div>  // ← Multiple top-level JSX elements
  );
};

// ✓ EXPERT FIX #1 (Fragment)
OLD:
  return (
    <div>Item 1</div>
    <div>Item 2</div>
  );

NEW:
  return (
    <>
      <div>Item 1</div>
      <div>Item 2</div>
    </>
  );

// ✓ EXPERT FIX #2 (Wrapper div - if styling needed)
OLD:
  return (
    <div>Item 1</div>
    <div>Item 2</div>
  );

NEW:
  return (
    <div className="item-container">
      <div>Item 1</div>
      <div>Item 2</div>
    </div>
  );

// 🎯 CHOICE LOGIC
// Use <> if no styling
// Use <div> if layout/styling required
// Avoid unnecessary wrapper divs (div hell)

// 📊 PERFORMANCE IMPACT
// Fragment: Zero DOM nodes added
// Wrapper: +1 DOM node per component instance
// For large lists: can matter
```

#### Pattern: Operator Precedence
```typescript
// ❌ SYMPTOM
"Expected boolean but got string" (type error)
// Logic produces unexpected results

// 🔍 ROOT CAUSE
const isValid = value > 10 && type === 'number' || isEmpty;
// Evaluated as: (value > 10 && type === 'number') || isEmpty
// Not what developer intended!

// ✓ EXPERT FIX
OLD:
const isValid = value > 10 && type === 'number' || isEmpty;

NEW:
const isValid = (value > 10 && type === 'number') || isEmpty;

// 🎯 ALWAYS USE PARENS
// Even if order is correct per precedence rules
// Makes intent crystal clear for next maintainer
// Zero performance cost

// 🧪 SAFETY: Add test
test('operator precedence is explicit', () => {
  expect(isValid(15, 'number', false)).toBe(true);
  expect(isValid(5, 'number', false)).toBe(false);
  expect(isValid(15, 'string', false)).toBe(false);
  expect(isValid(5, 'number', true)).toBe(true);
});
```

---

### 2.2 TYPE_ERRORS (Most Common in TypeScript/React Projects)

#### Pattern: Null/Undefined Escape Hatch (THE BIG ONE)
```typescript
// ❌ SYMPTOM
"Cannot read property 'map' of undefined"
// or: "Object is possibly 'undefined'"

// 🔍 ROOT CAUSE (VERY COMMON)
function renderItems(items: Item[] | undefined) {
  return (
    <div>
      {items.map(i => <ItemCard key={i.id} item={i} />)}
      {/* items might be undefined! */}
    </div>
  );
}

// ✓ EXPERT FIX #1 (Guard clause - for conditional render)
OLD:
function renderItems(items: Item[] | undefined) {
  return items.map(i => <ItemCard key={i.id} item={i} />);
}

NEW:
function renderItems(items: Item[] | undefined) {
  if (!items || items.length === 0) {
    return <div>No items found</div>;
  }
  return items.map(i => <ItemCard key={i.id} item={i} />);
}

// ✓ EXPERT FIX #2 (Optional chaining + nullish coalescing)
OLD:
const itemCount = response.data.items.length;  // Crash if nested undefined

NEW:
const itemCount = response.data?.items?.length ?? 0;

// ✓ EXPERT FIX #3 (Type narrowing in TypeScript)
OLD:
function process(value: string | null) {
  console.log(value.toUpperCase());  // TS error: possibly null
}

NEW:
function process(value: string | null) {
  if (value === null) {
    return;
  }
  console.log(value.toUpperCase());  // Now safe
}

// 🎯 PREVENTION (The Real Fix)
// 1. Use strict null checking in tsconfig.json:
{
  "compilerOptions": {
    "strictNullChecks": true
  }
}

// 2. Favor non-null defaults:
interface Response {
  items: Item[];  // NOT Item | undefined
  error?: string; // Only use optional if truly optional
}

// 3. Use discriminated unions:
type Result = 
  | { status: 'success'; data: Item[] }
  | { status: 'error'; error: string };

// 4. Test null paths explicitly:
test('handles null items gracefully', () => {
  expect(renderItems(null)).toContain('No items found');
  expect(renderItems(undefined)).toContain('No items found');
  expect(renderItems([])).toContain('No items found');
});

// 📊 ALPHA→BETA→RELEASE MATURITY
// ALPHA: No null checks, crashes possible
// BETA: Guard clauses added, some edge cases covered
// RELEASE: Strict null checks enforced, discriminated unions, full test coverage
```

#### Pattern: Generic Constraint Violation
```typescript
// ❌ SYMPTOM
"Type 'X' does not satisfy the constraint 'Y'"
// TypeScript strict mode error

// 🔍 ROOT CAUSE (Advanced TypeScript)
// User-defined generic that's too permissive
function useAsync<T>(fn: () => Promise<T>): T {
  // Problem: Returns T directly without handling Promise
  return fn() as T;  // ← Unsafe cast
}

// ✓ EXPERT FIX
OLD:
function useAsync<T>(fn: () => Promise<T>): T {
  return fn() as T;
}

NEW:
interface UseAsyncState<T> {
  state: 'loading' | 'success' | 'error';
  data?: T;
  error?: Error;
}

function useAsync<T>(fn: () => Promise<T>): UseAsyncState<T> {
  const [state, setState] = useState<UseAsyncState<T>>({ state: 'loading' });

  useEffect(() => {
    fn()
      .then(data => setState({ state: 'success', data }))
      .catch(error => setState({ state: 'error', error }));
  }, [fn]);

  return state;
}

// 🎯 KEY INSIGHT
// Generic T must be properly constrained
// Use discriminated union for state + data/error

// 🧪 TEST PATTERN
type TestData = { id: string; name: string };

test('useAsync resolves with correct type', async () => {
  const { state, data } = await useAsync<TestData>(async () => ({
    id: '1',
    name: 'Test',
  }));
  expect(state).toBe('success');
  expect(data?.name).toBe('Test');
});
```

#### Pattern: Implicit Any Escape
```typescript
// ❌ SYMPTOM
"Variable implicitly has an 'any' type"
// TypeScript noImplicitAny violation

// 🔍 ROOT CAUSE
const response = fetch(url);  // fetch returns Promise<Response>, but inferred as 'any'
const data = response.json();

// ✓ EXPERT FIX
OLD:
const response = fetch(url);
const data = response.json();

NEW:
const response: Response = await fetch(url);
const data: unknown = await response.json();

// Or with type assertion:
interface ApiResponse {
  items: Item[];
  total: number;
}

const data = (await response.json()) as ApiResponse;

// 🎯 BEST: Validate at runtime
import { z } from 'zod';

const apiResponseSchema = z.object({
  items: z.array(itemSchema),
  total: z.number(),
});

const data = apiResponseSchema.parse(await response.json());

// 🧪 SAFETY: Type guards
function isApiResponse(data: unknown): data is ApiResponse {
  return (
    typeof data === 'object' &&
    data !== null &&
    'items' in data &&
    'total' in data &&
    Array.isArray(data.items)
  );
}

// ⚠️ ENABLE IN tsconfig.json
{
  "compilerOptions": {
    "noImplicitAny": true,
    "strict": true  // Enables noImplicitAny + several others
  }
}
```

---

### 2.3 RUNTIME_ERRORS

#### Pattern: Null Pointer Dereference (Most Common)
```typescript
// ❌ SYMPTOM
"TypeError: Cannot read property 'x' of undefined"
// Line 347 in BuilderContainer.tsx

// 🔍 ROOT CAUSE (Find with grep)
// Search: .prop or ['prop'] on possibly-null value

const user = getUser();  // Might return null
const email = user.email;  // Crash if user is null

// ✓ EXPERT FIX #1 (Explicit check)
const user = getUser();
const email = user ? user.email : 'unknown@example.com';

// ✓ EXPERT FIX #2 (Optional chaining)
const user = getUser();
const email = user?.email ?? 'unknown@example.com';

// ✓ EXPERT FIX #3 (Narrow type first)
const user = getUser();
if (!user) {
  console.error('User not loaded');
  return null;
}
const email = user.email;  // Now safe

// 🎯 HUNTING STRATEGY
// Command: grep -rn "user\." src/ | grep -v user?
// Find all property accesses on potentially-null objects
// Add type guards systematically

// 📊 SCALE (Large codebase)
// Run automated null-check insertion tool
// Example: ts-null-safety (generates fixes)

// 🧪 REGRESSION TEST
test('handles null user gracefully', () => {
  expect(getEmail(null)).toBe('unknown@example.com');
  expect(getEmail(undefined)).toBe('unknown@example.com');
  expect(getEmail({ email: 'test@example.com' })).toBe('test@example.com');
});
```

#### Pattern: Array Bounds / Out-of-Order Access
```typescript
// ❌ SYMPTOM
"TypeError: Cannot read property '0' of undefined"
// Or incorrect array element returned

// 🔍 ROOT CAUSE
function getFirstItem(items: Item[]) {
  return items[0];  // Crashes if items is empty or undefined
}

// ✓ EXPERT FIX
const getFirstItem = (items: Item[] | null): Item | null => {
  return items && items.length > 0 ? items[0] : null;
};

// 🎯 ADVANCED PATTERN (Discriminated Union)
type GetItemResult =
  | { status: 'success'; item: Item }
  | { status: 'error'; reason: 'empty_array' | 'null_input' };

function getFirstItem(items: Item[] | null): GetItemResult {
  if (!items) return { status: 'error', reason: 'null_input' };
  if (items.length === 0) return { status: 'error', reason: 'empty_array' };
  return { status: 'success', item: items[0] };
}

// 📊 TESTING STRATEGY (Coverage)
test('getFirstItem handles all edge cases', () => {
  expect(getFirstItem(null)).toEqual({ status: 'error', reason: 'null_input' });
  expect(getFirstItem([])).toEqual({ status: 'error', reason: 'empty_array' });
  expect(getFirstItem([item1])).toEqual({ status: 'success', item: item1 });
});
```

#### Pattern: Infinite Loops / Stack Overflow
```typescript
// ❌ SYMPTOM (Hard to find!)
"RangeError: Maximum call stack size exceeded"
// Browser hangs or very slow performance

// 🔍 COMMON CAUSES IN SOVEREIGN STUDIO
// 1. Recursive function without base case
// 2. React component that triggers re-render → state change → re-render
// 3. useEffect without dependency array
// 4. Event listener that triggers same event

// Example 1: Missing base case
function factorial(n: number): number {
  return n * factorial(n - 1);  // ← No base case!
}

// ✓ FIX
function factorial(n: number): number {
  if (n <= 1) return 1;  // Base case
  return n * factorial(n - 1);
}

// Example 2: useEffect infinite loop (VERY COMMON IN REACT)
// ❌ ANTI-PATTERN
useEffect(() => {
  setState(computeState()); // Triggers re-render → useEffect runs again
});  // No dependency array!

// ✓ FIX
useEffect(() => {
  setState(computeState());
}, []);  // Empty deps: runs once on mount

// Or specific deps:
useEffect(() => {
  setState(computeState(deps));
}, [deps]);  // Re-run only when deps change

// Example 3: Event listener causing infinite loop
// ❌ ANTI-PATTERN
element.addEventListener('scroll', () => {
  element.scrollTop = 0;  // Triggers scroll event again!
});

// ✓ FIX (Debounce or guard)
let isScrolling = false;
element.addEventListener('scroll', () => {
  if (!isScrolling) {
    isScrolling = true;
    element.scrollTop = 0;
    setTimeout(() => (isScrolling = false), 100);
  }
});

// 🎯 DETECTION STRATEGY
// Add timeout guards:
function withTimeout<T>(fn: () => T, ms: number = 5000): T {
  const timeoutId = setTimeout(() => {
    throw new Error(`Execution timeout after ${ms}ms`);
  }, ms);
  try {
    return fn();
  } finally {
    clearTimeout(timeoutId);
  }
}

// 🧪 TEST
test('factorial terminates', () => {
  expect(() => withTimeout(() => factorial(5), 100)).not.toThrow();
  expect(factorial(5)).toBe(120);
});
```

---

### 2.4 ASYNC_ERRORS (Promises, Callbacks, Async/Await)

#### Pattern: Unhandled Promise Rejection
```typescript
// ❌ SYMPTOM
"UnhandledPromiseRejectionWarning: Error: API call failed"
// Process exits with code 1

// 🔍 ROOT CAUSE (The #1 async bug)
async function fetchData() {
  const response = await fetch(url);
  return response.json();  // Missing error handler
}

// Called without catch:
fetchData();  // ← Fire and forget, will crash on error

// ✓ EXPERT FIX #1 (try/catch)
async function fetchData() {
  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (error) {
    console.error('Fetch failed:', error);
    throw error;  // Re-throw with context
  }
}

// ✓ EXPERT FIX #2 (Result type pattern - Sovereign style)
type Result<T, E = Error> =
  | { ok: true; value: T }
  | { ok: false; error: E };

async function fetchDataResult(): Promise<Result<ApiData>> {
  try {
    const response = await fetch(url);
    if (!response.ok) {
      return { ok: false, error: new Error(`HTTP ${response.status}`) };
    }
    const data = await response.json();
    return { ok: true, value: data };
  } catch (error) {
    return { ok: false, error: error as Error };
  }
}

// Usage:
const result = await fetchDataResult();
if (result.ok) {
  console.log('Data:', result.value);
} else {
  console.error('Error:', result.error);
}

// 🎯 SOVEREIGN PRINCIPLE
// Never use fire-and-forget unless intentional
// Always provide error boundary

// ✓ EXPERT FIX #3 (Catch handler at call site)
fetchData()
  .then(data => console.log(data))
  .catch(error => {
    console.error('Failed to fetch:', error);
    // Send to error tracking service
    // Update UI with error message
  });

// 🧪 TEST PATTERN
test('handles fetch error gracefully', async () => {
  const result = await fetchDataResult();
  expect(result.ok).toBe(false);
  expect(result.error).toBeInstanceOf(Error);
});

// ⚠️ PREVENTION
// Add linting rule: "no-floating-promises"
// In eslintrc: @typescript-eslint/no-floating-promises: "error"
```

#### Pattern: Race Condition / Lost Updates
```typescript
// ❌ SYMPTOM
"Data is inconsistent or lost"
// Two async operations interfere with each other

// 🔍 ROOT CAUSE (VERY COMMON IN SOVEREIGN)
let userData = null;

async function loadUser(id: string) {
  const data = await fetch(`/api/users/${id}`);
  userData = data;  // ← Race: if second call finishes first, overwrites
}

// Called twice with different IDs:
loadUser('user1');  // Takes 100ms
loadUser('user2');  // Takes 50ms
// Result: userData contains user2 data, but component expects user1!

// ✓ EXPERT FIX #1 (Request ID / generation counter)
let userData = null;
let currentRequestId = 0;

async function loadUser(id: string) {
  const requestId = ++currentRequestId;
  const data = await fetch(`/api/users/${id}`);
  
  if (requestId === currentRequestId) {
    // Only update if this is still the latest request
    userData = data;
  }
}

// ✓ EXPERT FIX #2 (AbortController - Modern approach)
let abortController: AbortController | null = null;

async function loadUser(id: string) {
  abortController?.abort();  // Cancel previous request
  abortController = new AbortController();
  
  const response = await fetch(`/api/users/${id}`, {
    signal: abortController.signal
  });
  
  const data = await response.json();
  userData = data;
}

// ✓ EXPERT FIX #3 (React useEffect cleanup pattern)
useEffect(() => {
  let cancelled = false;

  async function load() {
    const response = await fetch(`/api/users/${userId}`);
    const data = await response.json();
    
    if (!cancelled) {
      setUserData(data);
    }
  }

  load();

  return () => {
    cancelled = true;  // Cleanup on unmount
  };
}, [userId]);

// 📊 SCALE: Multiple concurrent requests
// Use a request queue with priorities:
class RequestQueue {
  private queue: Map<string, AbortController> = new Map();

  async request(key: string, fn: (signal: AbortSignal) => Promise<any>) {
    this.cancel(key);  // Cancel previous request with same key
    const controller = new AbortController();
    this.queue.set(key, controller);

    try {
      const result = await fn(controller.signal);
      return result;
    } finally {
      this.queue.delete(key);
    }
  }

  cancel(key: string) {
    this.queue.get(key)?.abort();
    this.queue.delete(key);
  }
}

// 🧪 TEST (Hard to test reliably!)
test('latest request wins', async () => {
  const results: string[] = [];
  
  // Fire requests in order
  const p1 = loadUser('user1').then(() => results.push('user1'));
  const p2 = loadUser('user2').then(() => results.push('user2'));
  
  await Promise.all([p1, p2]);
  
  // Last request should win
  expect(results[results.length - 1]).toBe('user2');
});
```

#### Pattern: Missing Await
```typescript
// ❌ SYMPTOM
"Returned value is Promise, not data"
// Or: "Cannot read property 'x' of Promise"

// 🔍 ROOT CAUSE (Easy to miss!)
async function getData() {
  return await fetch(url).then(r => r.json());
}

async function processData() {
  const data = getData();  // ← Forgot await!
  return data.items;  // Crash: data is Promise, not object
}

// ✓ FIX
async function processData() {
  const data = await getData();  // Added await
  return data.items;
}

// 🎯 DETECTION
// ESLint: @typescript-eslint/no-floating-promises
// TypeScript: Enable strict mode

// 🧪 TEST
test('processData awaits properly', async () => {
  const result = await processData();
  expect(Array.isArray(result)).toBe(true);
});
```

---

### 2.5 STATE_ERRORS (React Hooks, State Management)

#### Pattern: Stale Closure (React Classic)
```typescript
// ❌ SYMPTOM
"Button shows outdated count"
// Event handler uses old state value

// 🔍 ROOT CAUSE (THE BIG ONE IN REACT)
function Counter() {
  const [count, setCount] = useState(0);

  const handleClick = () => {
    setTimeout(() => {
      console.log(count);  // Always logs 0!
    }, 1000);
  };

  return <button onClick={handleClick}>Click me</button>;
}

// Why? handleClick closure captured count=0 on render
// When setTimeout fires, count is still 0 (from closure)

// ✓ EXPERT FIX #1 (useRef for latest value)
function Counter() {
  const [count, setCount] = useState(0);
  const countRef = useRef(count);

  useEffect(() => {
    countRef.current = count;  // Keep ref in sync
  }, [count]);

  const handleClick = () => {
    setTimeout(() => {
      console.log(countRef.current);  // Latest count!
    }, 1000);
  };

  return <button onClick={handleClick}>Click me</button>;
}

// ✓ EXPERT FIX #2 (Functional setState)
const handleClick = () => {
  setCount(prevCount => {
    setTimeout(() => {
      console.log(prevCount);  // Latest count
    }, 1000);
    return prevCount;
  });
};

// ✓ EXPERT FIX #3 (useCallback with deps)
const handleClick = useCallback(() => {
  setTimeout(() => {
    console.log(count);  // Latest!
  }, 1000);
}, [count]);  // Re-create when count changes

// 🎯 SOVEREIGN PATTERN (Recommended)
// Use useCallback + dependency array explicitly

// 🧪 TEST (Tricky!)
test('handleClick uses latest count', async () => {
  const { rerender } = render(<Counter />);
  
  fireEvent.click(screen.getByText('Click me'));
  
  await waitFor(() => {
    expect(console.log).toHaveBeenCalledWith(0);
  });
});
```

#### Pattern: React Hook Rule Violation
```typescript
// ❌ SYMPTOM
"React Hook 'useState' is called conditionally"
// or: "Rules of Hooks violation"

// 🔍 ROOT CAUSE
function Component({ shouldLoad }) {
  if (shouldLoad) {
    const [state, setState] = useState(0);  // ← Conditional!
  }
}

// Why? React tracks hooks by call order
// If condition changes, hook order changes → crash

// ✓ FIX (Move hook call outside condition)
OLD:
function Component({ shouldLoad }) {
  if (shouldLoad) {
    const [state, setState] = useState(0);
  }
}

NEW:
function Component({ shouldLoad }) {
  const [state, setState] = useState(0);  // Always called
  
  if (!shouldLoad) {
    return null;  // Conditional return, not hook
  }
  
  return <div>{state}</div>;
}

// 🧪 ESLint (Automatic detection)
// Use eslint-plugin-react-hooks
// Rules: rules-of-hooks (error)
```

#### Pattern: Infinite useEffect Loop
```typescript
// ❌ SYMPTOM
"Component re-renders infinitely"
// Network tab shows endless API calls

// 🔍 ROOT CAUSE (SO COMMON!)
useEffect(() => {
  fetchData();
});  // Missing dependency array!
// Runs on EVERY render → fetchData → setState → re-render → loop

// ✓ FIX #1 (Empty deps for mount only)
useEffect(() => {
  fetchData();
}, []);  // Runs once

// ✓ FIX #2 (Specific dependencies)
useEffect(() => {
  fetchData(userId);
}, [userId]);  // Runs when userId changes

// ✓ FIX #3 (Object/array deps - use useMemo)
const query = useMemo(() => ({ userId, status }), [userId, status]);

useEffect(() => {
  fetchData(query);
}, [query]);  // Now stable, won't re-run unless values change

// 🎯 RULE
// Always specify dependency array
// Include everything used inside useEffect

// 🧪 TEST
test('useEffect runs once on mount', () => {
  const mockFetch = jest.fn();
  
  const { rerender } = render(
    <Component fetchData={mockFetch} />
  );
  
  expect(mockFetch).toHaveBeenCalledTimes(1);
  
  rerender(<Component fetchData={mockFetch} />);
  expect(mockFetch).toHaveBeenCalledTimes(1);  // Still 1!
});
```

---

### 2.6 ARCHITECTURE_ERRORS

#### Pattern: Circular Dependencies
```typescript
// ❌ SYMPTOM
"Circular dependency detected"
// or: "Cannot read property of undefined" (from circular require)

// 🔍 ROOT CAUSE
// fileA.ts imports fileB.ts
// fileB.ts imports fileA.ts

// fileA.ts
import { functionB } from './fileB';  // ← Circular!
export const functionA = () => functionB();

// fileB.ts
import { functionA } from './fileA';  // ← Back to A!
export const functionB = () => functionA();

// ✓ FIX #1 (Extract shared code)
// shared.ts
export const sharedLogic = () => { /* ... */ };

// fileA.ts
import { sharedLogic } from './shared';
export const functionA = () => sharedLogic();

// fileB.ts
import { sharedLogic } from './shared';
export const functionB = () => sharedLogic();

// ✓ FIX #2 (Dependency injection)
// fileA.ts
export const functionA = (dep: DependencyB) => dep.doSomething();

// fileB.ts
export const functionB = () => { /* standalone */ };

// index.ts (wiring)
const depB = functionB();
functionA(depB);

// 🎯 DETECTION (Automated)
// Use: madge (dependency visualizer)
// madge --circular src/
// Shows all circular deps

// 🧪 TEST
test('no circular dependencies', () => {
  const result = require('madge')('./src');
  expect(result.circular().length).toBe(0);
});
```

#### Pattern: Mixed Concerns (UI + Business Logic)
```typescript
// ❌ SYMPTOM (Sovereign Studio specific)
"BuilderContainer.tsx is 4,682 lines"
// Hard to test, understand, modify

// 🔍 ROOT CAUSE
// Single component has:
// - React hooks (UI state)
// - Business logic (computations)
// - API calls
// - Event handlers
// - Subcomponents
// - Helper functions

// ✓ EXPERT FIX (Separation of Concerns)
// Before: monolithic component
// src/features/product/containers/BuilderContainer.tsx (4,682 lines)

// After: layered architecture
src/
├── features/product/
│   ├── runtime/
│   │   ├── computePackage.ts        (business logic)
│   │   ├── validatePackage.ts       (validation)
│   │   └── generateDiff.ts          (diff logic)
│   ├── hooks/
│   │   ├── usePackageState.ts       (state management)
│   │   ├── useGitHubIntegration.ts  (API calls)
│   │   └── useWorkflowWatch.ts      (polling)
│   ├── components/
│   │   ├── ChatPanel.tsx
│   │   ├── FileEditor.tsx
│   │   ├── StatusDashboard.tsx
│   │   └── HistoryLog.tsx
│   └── containers/
│       └── BuilderContainer.tsx     (< 300 lines, only wiring)

// Benefits:
// - Runtime logic: can be tested without React
// - Hooks: reusable across components
// - Components: pure, easy to test
// - Container: just orchestration

// 🧪 TESTABILITY IMPROVEMENT
// Before: ComponentTest requires mock React, complex setup
// After:
//   - Unit test: computePackage.test.ts (fast, no React)
//   - Hook test: usePackageState.test.ts (with renderHook)
//   - Component test: ChatPanel.test.tsx (isolated component)
//   - Integration test: BuilderContainer.test.tsx (full flow)
```

#### Pattern: Hard-Coded Secrets
```typescript
// ❌ CRITICAL SYMPTOM
// API key, token, or password visible in code
// Especially in public repos!

// 🔍 ROOT CAUSE
const API_KEY = 'sk-proj-abc123xyz789';  // ← EXPOSED!
const CONFIG = {
  apiKey: 'ghp_xyz789...',  // ← GitHub token!
  webhookSecret: 'whsec_...',
};

// ✓ EXPERT FIX #1 (Environment variables)
// .env.local (gitignored)
VITE_API_KEY=sk-proj-abc123xyz789
GITHUB_TOKEN=ghp_xyz789...

// src/config.ts
export const config = {
  apiKey: import.meta.env.VITE_API_KEY,
  githubToken: process.env.GITHUB_TOKEN,  // Node only
};

// ✓ EXPERT FIX #2 (Cloudflare Workers - for server secrets)
// wrangler.toml
[env.production.secrets]
API_KEY = "sk-..."
GITHUB_TOKEN = "ghp_..."

// src/worker.ts
export default {
  fetch: (request, env) => {
    const apiKey = env.API_KEY;  // Secure!
  }
};

// ✓ EXPERT FIX #3 (Secret scanning)
// Add pre-commit hook:
// npm install --save-dev secretlint
// File: .secretlintrc.json
{
  "rules": [
    {
      "id": "@secretlint/secretlint-rule-aws"
    },
    {
      "id": "@secretlint/secretlint-rule-basicauth"
    }
  ]
}

// 🎯 AUDIT (Find existing leaks)
// grep -r "sk-" src/  # OpenAI keys
// grep -r "ghp_" src/ # GitHub tokens
// grep -r "AKIA" src/ # AWS keys

// ⚠️ IF ALREADY LEAKED
// 1. Rotate the secret immediately
// 2. Remove from Git history: git-filter-branch
// 3. Commit removing the secret
// 4. Force push (if private repo)
// 5. Add to .gitignore
// 6. Enable secret scanning on GitHub

// 🧪 TEST (Ensure no secrets in artifacts)
test('no secrets in source code', () => {
  const files = glob.sync('src/**/*.ts');
  for (const file of files) {
    const content = fs.readFileSync(file, 'utf-8');
    expect(content).not.toMatch(/sk-/);
    expect(content).not.toMatch(/ghp_/);
    expect(content).not.toMatch(/AKIA/);
  }
});
```

---

### 2.7 SECURITY_ERRORS

#### Pattern: Exposed API Key in Request
```typescript
// ❌ CRITICAL SYMPTOM
// API key visible in network tab or logs

// 🔍 ROOT CAUSE
// Client-side code sends API key directly
const response = await fetch('https://api.example.com/data', {
  headers: {
    'Authorization': `Bearer ${API_KEY}`  // ← Client can see!
  }
});

// ✓ EXPERT FIX #1 (Server-side proxy)
// Client request:
const response = await fetch('/api/proxy/data');

// Server (worker or Node):
export default {
  fetch: async (request, env) => {
    const response = await fetch('https://api.example.com/data', {
      headers: {
        'Authorization': `Bearer ${env.API_KEY}`  // ← Secret safe on server
      }
    });
    return response;
  }
};

// ✓ EXPERT FIX #2 (CloudflareWorker + R2)
// Only expose R2 API on worker, keep secrets in env

// 🎯 FLOW
// Client → Worker (no secrets visible)
// Worker → Third-party API (secrets in env)
// Result → R2 (if caching needed)
// R2 → Client (public read)

// ⚠️ RULE
// NEVER put secrets in client-side code
// Use server/worker as intermediary always
```

---

## 3. IMPLEMENTATION STATUS BOARD

### 3.1 Alpha → Beta → Release Maturity Model

```json
{
  "maturity_stages": {
    "ALPHA": {
      "description": "Proof of concept, high error rate acceptable",
      "error_handling": "Minimal, may crash",
      "testing": "Manual testing only",
      "security": "No security review",
      "performance": "Not optimized",
      "documentation": "Sparse or missing",
      "production_ready": false,
      "examples": [
        "Initial feature branch",
        "New algorithm first draft",
        "Prototype integration"
      ]
    },
    "BETA": {
      "description": "Feature complete, errors identified and partially fixed",
      "error_handling": [
        "Try/catch blocks added",
        "Some edge cases handled",
        "Error messages improved",
        "Not all error families covered"
      ],
      "testing": [
        "Unit tests for happy path",
        "Some integration tests",
        "Manual edge case testing"
      ],
      "security": [
        "Basic review done",
        "No known critical issues",
        "May have non-critical vulnerabilities"
      ],
      "performance": ["Basic optimization done", "No profiling yet"],
      "documentation": [
        "Basic README",
        "Core usage documented",
        "Missing edge cases"
      ],
      "production_ready": false,
      "gates_required": [
        "type-check (green)",
        "test:run >= 60% coverage",
        "no critical security issues"
      ]
    },
    "RELEASE": {
      "description": "Production ready, comprehensive error handling",
      "error_handling": [
        "All error families handled",
        "Graceful degradation",
        "User-friendly error messages",
        "Error tracking configured",
        "Repair flows defined"
      ],
      "testing": [
        "Unit tests >= 80% coverage",
        "Integration tests for main flows",
        "Edge case tests comprehensive",
        "E2E tests for critical paths",
        "Flaky test fixes done"
      ],
      "security": [
        "Full security audit complete",
        "No known vulnerabilities",
        "Secrets never exposed",
        "OWASP top 10 checked",
        "Automated scanning enabled"
      ],
      "performance": [
        "Profiled and optimized",
        "Load tested",
        "Bundle size acceptable",
        "No memory leaks"
      ],
      "documentation": [
        "Complete API docs",
        "Edge cases documented",
        "Troubleshooting guide",
        "Monitoring/alerting setup",
        "Runbooks for failures"
      ],
      "production_ready": true,
      "gates_required": [
        "npm run audit:sovereign (green)",
        "npm run type-check (zero errors)",
        "npm run test:run (green)",
        "npm run build (success)",
        "CI/CD workflow (all green)",
        "Security scan (no critical)",
        "Performance profile (acceptable)",
        "Code review approved"
      ]
    }
  },
  "progression_rules": {
    "alpha_to_beta": [
      "Identify all error families in code",
      "Add error handling for each family",
      "Write unit tests for main paths",
      "Resolve all critical/high severity issues"
    ],
    "beta_to_release": [
      "Achieve 80%+ test coverage",
      "Fix all identified bugs",
      "Optimize performance",
      "Complete security review",
      "Write comprehensive documentation",
      "All green gates passing"
    ]
  }
}
```

### 3.2 Error Family Coverage By Stage

```typescript
// ALPHA: No coverage
interface AlphaCoverage {
  syntaxErrors: false;
  typeErrors: false;
  runtimeErrors: false;
  asyncErrors: false;
  stateErrors: false;
  architectureErrors: false;
  securityErrors: false;
  performanceErrors: false;
  testErrors: false;
  deployErrors: false;
}

// BETA: Partial coverage
interface BetaCoverage {
  syntaxErrors: true;           // Build fails if syntax wrong
  typeErrors: true;             // TypeScript catches some
  runtimeErrors: 'partial';     // Guard clauses added
  asyncErrors: 'partial';       // Some try/catch added
  stateErrors: 'partial';       // Common bugs fixed
  architectureErrors: false;
  securityErrors: 'critical_only'; // Major leaks fixed
  performanceErrors: false;
  testErrors: false;
  deployErrors: false;
}

// RELEASE: Full coverage
interface ReleaseCoverage {
  syntaxErrors: true;           // audit:sovereign checks
  typeErrors: true;             // Strict mode enabled
  runtimeErrors: true;          // All guard clauses
  asyncErrors: true;            // All cases handled
  stateErrors: true;            // All hook rules
  architectureErrors: true;     // Design reviewed
  securityErrors: true;         // Fully audited
  performanceErrors: true;      // Profiled
  testErrors: true;             // 80%+ coverage
  deployErrors: true;           // Runbooks ready
}
```

---

## 4. EXPERT HUNTING STRATEGIES

### 4.1 Finding Hidden Errors (The Detective Work)

#### Strategy: Grep Patterns (Quick Wins)
```bash
# Find unhandled promises
grep -rn "\.then(" src/ | grep -v catch | head -20

# Find ignored errors
grep -rn "// @ts-ignore" src/

# Find any/unknown types (type escape)
grep -rn ": any\|: unknown" src/ | grep -v "unknown:" | head -20

# Find missing error handlers
grep -rn "try {" src/ | while read line; do
  file=$(echo $line | cut -d: -f1)
  linenum=$(echo $line | cut -d: -f2)
  if ! grep -q "catch" <(tail -n +$linenum "$file" | head -50); then
    echo "Possibly missing catch: $line"
  fi
done

# Find infinite loops (recursive without base case)
grep -rn "function.*(" src/ | while read line; do
  func=$(echo $line | grep -oP 'function\s+\K\w+')
  if grep -q "return $func(" src/ && ! grep -q "if.*return" src/; then
    echo "Possible infinite recursion: $line"
  fi
done

# Find hardcoded secrets
grep -rn "sk-\|ghp_\|AKIA\|Bearer\|api[_-]key" src/ | grep -v "test\|mock\|example"

# Find missing null checks
grep -rn "\.[a-zA-Z_]\+(" src/ | grep -v "?\..*(" | grep -v "^\s*//" | head -20

# Find React hook violations
grep -rn "useState\|useEffect\|useCallback" src/ | while read line; do
  # Check if inside if/for/while
  if echo $line | grep -q "if.*\|\bfor.*\|\bwhile.*"; then
    echo "VIOLATION: Hook inside conditional: $line"
  fi
done
```

#### Strategy: Type Checking (Strict Mode)
```bash
# Enable strict TypeScript
npm run type-check -- --strict

# Find all implicit any
npm run type-check -- --noImplicitAny

# Generate error report
npm run type-check 2>&1 | tee type-errors.txt

# Count errors by type
grep -o "error TS[0-9]\+:" type-errors.txt | sort | uniq -c | sort -rn
```

#### Strategy: Static Analysis Tools
```bash
# SonarQube (comprehensive)
npm install -D sonarqube-scanner
npx sonar-scanner

# ESLint with plugins
npm install -D \
  @typescript-eslint/eslint-plugin \
  eslint-plugin-react-hooks \
  eslint-plugin-no-only-tests

npm run lint

# Find todo/fixme comments (known issues)
grep -rn "TODO\|FIXME\|HACK\|BUG" src/ | head -20

# Circular dependency check
npm install -D madge
npx madge --circular src/
```

### 4.2 Runtime Debugging (When Tests Miss It)

#### Strategy: Console Logging (Primitive but effective)
```typescript
// Add logging at error boundaries
function riskyOperation(input: any) {
  console.log('🔵 [riskyOperation] Input:', input);
  
  try {
    const result = doSomething(input);
    console.log('🟢 [riskyOperation] Success:', result);
    return result;
  } catch (error) {
    console.error('🔴 [riskyOperation] Error:', error);
    console.error('   Stack:', error instanceof Error ? error.stack : 'N/A');
    throw error;
  }
}

// Structured logging for Sovereign
const log = (level: 'info' | 'warn' | 'error', message: string, data?: any) => {
  const timestamp = new Date().toISOString();
  const entry = { timestamp, level, message, data };
  
  console.log(JSON.stringify(entry));  // Structured for parsing
  
  if (level === 'error') {
    // Send to error tracking
    trackError(entry);
  }
};
```

#### Strategy: Debugger Breakpoints
```typescript
// Use browser DevTools
// File → Editor (F12)
// Add breakpoint: click line number
// Inspect variables on hover
// Step through execution

// Or use node --inspect
node --inspect dist/index.js

// Or in code:
debugger;  // Will pause if DevTools open
```

#### Strategy: Error Tracking Integration
```typescript
// Sentry integration (for production errors)
import * as Sentry from "@sentry/node";

Sentry.init({ dsn: process.env.SENTRY_DSN });

try {
  riskyOperation();
} catch (error) {
  Sentry.captureException(error, {
    contexts: {
      error_context: {
        operation: 'riskyOperation',
        input: { /* sanitized */ },
      }
    }
  });
}

// Result: Error appears in Sentry dashboard with:
// - Full stack trace
// - Breadcrumbs (previous events)
// - Session replay
// - Related errors (grouping)
```

---

## 5. FILE ARCHITECTURE PATTERNS

### 5.1 Sovereign Studio Error-Aware Architecture

```
src/
├── features/
│   └── product/
│       ├── runtime/                    ← BUSINESS LOGIC (testable without React)
│       │   ├── sovereignPackageFromRepoFiles.ts
│       │   ├── sovereignPackageFromRepoFiles.test.ts
│       │   ├── sovereignFunctionalGuards.ts
│       │   ├── sovereignFunctionalGuards.test.ts
│       │   ├── errorClassification.ts         ← NEW: Error family classifiers
│       │   ├── errorRepairFlows.ts            ← NEW: Repair strategies
│       │   └── errorClassification.test.ts
│       │
│       ├── hooks/                      ← REACT STATE & SIDE EFFECTS
│       │   ├── usePackageBuilder.ts
│       │   ├── usePackageBuilder.test.ts
│       │   ├── useErrorHandler.ts             ← NEW: Error boundary logic
│       │   └── useErrorHandler.test.ts
│       │
│       ├── components/                 ← PURE UI COMPONENTS
│       │   ├── PackageEditor.tsx
│       │   ├── PackageEditor.test.tsx
│       │   ├── ErrorBoundary.tsx              ← NEW: Error UI
│       │   ├── ErrorDisplay.tsx
│       │   ├── ErrorDisplay.test.tsx
│       │   └── RepairSuggestion.tsx
│       │
│       ├── containers/                 ← ORCHESTRATION
│       │   └── BuilderContainer.tsx    ← Refactored to <500 lines
│       │
│       └── types/
│           ├── errors.ts              ← NEW: Error type definitions
│           ├── repair.ts              ← NEW: Repair flow types
│           └── index.ts

├── runtime/                            ← SHARED RUNTIME UTILITIES
│   ├── errorFamilyClassifier.ts        ← Error type detection
│   ├── repairEngine.ts                 ← Suggests fixes
│   ├── errorFamilyClassifier.test.ts
│   └── repairEngine.test.ts

├── integrations/
│   └── gpt56/
│       ├── gpt56-client.ts            ← GPT-5.6 integration
│       ├── patternAnalyzer.ts         ← Pattern-based analysis
│       └── patternAnalyzer.test.ts

└── utils/
    ├── errorTracking.ts               ← Sentry integration
    └── errorTracking.test.ts
```

### 5.2 Error Classification Module (NEW)
```typescript
// src/runtime/errorFamilyClassifier.ts

export type ErrorFamily =
  | 'SYNTAX'
  | 'TYPE'
  | 'RUNTIME'
  | 'ASYNC'
  | 'STATE'
  | 'ARCHITECTURE'
  | 'SECURITY'
  | 'PERFORMANCE'
  | 'TEST'
  | 'DEPLOY'
  | 'INTEGRATION'
  | 'UNKNOWN';

export type ErrorSeverity = 'critical' | 'high' | 'medium' | 'low';

export interface ClassifiedError {
  family: ErrorFamily;
  severity: ErrorSeverity;
  message: string;
  stack: string;
  line?: number;
  file?: string;
  context?: Record<string, any>;
  suggestedFamily?: ErrorFamily;  // For debugging classifier itself
}

export function classifyError(error: Error | string): ClassifiedError {
  const message = typeof error === 'string' ? error : error.message;
  const stack = error instanceof Error ? error.stack || '' : '';

  // Rule-based classification
  if (message.match(/Cannot read propert|Cannot access member/)) {
    return {
      family: 'RUNTIME',
      severity: 'high',
      message,
      stack,
      context: { type: 'null_pointer_dereference' }
    };
  }

  if (message.match(/is not a function|is not defined/)) {
    return {
      family: 'RUNTIME',
      severity: 'high',
      message,
      stack,
      context: { type: 'missing_definition' }
    };
  }

  // ... more patterns

  return {
    family: 'UNKNOWN',
    severity: 'medium',
    message,
    stack
  };
}
```

### 5.3 Repair Engine (NEW)
```typescript
// src/runtime/repairEngine.ts

export interface RepairSuggestion {
  patternId: string;
  title: string;
  explanation: string;
  searchReplace?: { search: string; replace: string };
  requiredTests: string[];
  severity: ErrorSeverity;
}

export async function suggestRepair(
  classified: ClassifiedError,
  codeContext: string
): Promise<RepairSuggestion[]> {
  const suggestions: RepairSuggestion[] = [];

  switch (classified.family) {
    case 'RUNTIME':
      if (classified.context?.type === 'null_pointer_dereference') {
        suggestions.push({
          patternId: 'RUNTIME.2.1',
          title: 'Add null check before property access',
          explanation: 'The code accesses a property on a possibly-null value.',
          searchReplace: {
            search: `const x = obj.property;`,
            replace: `const x = obj?.property ?? defaultValue;`
          },
          requiredTests: ['handles null gracefully'],
          severity: 'high'
        });
      }
      break;

    case 'TYPE':
      suggestions.push({
        patternId: 'TYPE.2.2',
        title: 'Enable strict null checking',
        explanation: 'TypeScript strict mode catches null dereferences.',
        searchReplace: {
          search: '  "strictNullChecks": false',
          replace: '  "strictNullChecks": true'
        },
        requiredTests: ['type-check passes'],
        severity: 'high'
      });
      break;

    // ... more cases
  }

  // Optionally query GPT-5.6 for additional suggestions
  if (process.env.OPENAI_API_KEY) {
    const gptSuggestions = await queryGPT56Repair(classified, codeContext);
    suggestions.push(...gptSuggestions);
  }

  return suggestions.sort((a, b) => {
    const severityMap = { critical: 3, high: 2, medium: 1, low: 0 };
    return severityMap[b.severity] - severityMap[a.severity];
  });
}
```

---

## 6. RARE & DEEP ERROR PATTERNS

### 6.1 The Silent Data Corruption Bug
```typescript
// ❌ SYMPTOMS
// Data inconsistency, wrong values in database, no error thrown

// 🔍 CAUSE (VERY HARD TO FIND!)
// Concurrent mutation of shared object
let sharedState = { count: 0 };

function process1() {
  sharedState.count += 1;
  console.log('P1:', sharedState.count);  // May see P2's changes
}

function process2() {
  sharedState.count += 10;
  console.log('P2:', sharedState.count);
}

// Race:
// P1: read (0) → add 1 → write (1)
// P2: read (0) → add 10 → write (10)  ← Lost P1's update!

// ✓ FIX (Atomic operations)
class Counter {
  private count = 0;
  private lock = false;

  async increment(amount: number) {
    while (this.lock) await new Promise(r => setTimeout(r, 1));
    this.lock = true;
    try {
      this.count += amount;
    } finally {
      this.lock = false;
    }
  }
}

// Or use proper concurrency:
import { Mutex } from 'async-lock';

const counter = new Mutex();
await counter.runExclusive(async () => {
  sharedState.count += 1;
});
```

### 6.2 The Time-Zone Bug
```typescript
// ❌ SYMPTOM
// Dates are off by a few hours in different regions

// 🔍 CAUSE
const date = new Date('2026-07-13 14:30');  // ← Ambiguous!
// JavaScript parses differently in different locales

// ✓ FIX (Always use ISO format)
const date = new Date('2026-07-13T14:30:00Z');  // Explicit UTC
const date2 = new Date('2026-07-13T14:30:00+02:00');  // With offset

// Or use date library:
import { parse, format } from 'date-fns';
const date = parse('2026-07-13 14:30', 'yyyy-MM-dd HH:mm', new Date());
```

### 6.3 The Floating Point Precision Bug
```typescript
// ❌ SYMPTOM
// Calculations are slightly off: 0.1 + 0.2 === 0.30000000000000004

// 🔍 CAUSE
console.log(0.1 + 0.2);  // 0.30000000000000004 (not 0.3!)
// JavaScript uses 64-bit IEEE floating point

// ✓ FIX (For money: use cents/integers)
const amountCents = Math.round(0.1 * 100) + Math.round(0.2 * 100);
const amountDollars = amountCents / 100;

// Or use Decimal library:
import Decimal from 'decimal.js';
const result = new Decimal(0.1).plus(0.2);  // 0.3

// 🧪 TEST
test('floating point arithmetic', () => {
  const cents = Math.round(10) + Math.round(20);
  expect(cents / 100).toBe(0.3);
});
```

### 6.4 The Unicode Normalization Bug
```typescript
// ❌ SYMPTOM
// Same character looks identical but doesn't match in string comparison

// 🔍 CAUSE
const s1 = 'é';     // Single character (U+00E9)
const s2 = 'é';     // e (U+0065) + acute accent (U+0301)
console.log(s1 === s2);  // false! But looks same

// ✓ FIX (Normalize strings)
const normalize = (s: string) => s.normalize('NFC');
console.log(normalize(s1) === normalize(s2));  // true

// For comparisons:
function compareStrings(a: string, b: string): boolean {
  return a.normalize('NFC') === b.normalize('NFC');
}
```

### 6.5 The Module Resolution Order Bug
```typescript
// ❌ SYMPTOM
// Build fails only in CI, works locally
// "Cannot find module" or import cycles

// 🔍 CAUSE
// Local machine: node_modules has package v1.0
// CI machine: package v2.0 (different API)

// ✓ FIX (Lock dependencies)
// Use pnpm-lock.yaml or package-lock.json
// Commit lock file to git

pnpm install  // Uses lock file, reproducible

// Or use monorepo with workspaces:
pnpm -r install  // Installs all workspaces consistently
```

---

## 7. MASTER HUNTING CHECKLIST

```
When assigned an error:

□ TRIAGE PHASE
  □ Get error message (exact, with timestamp)
  □ Get stack trace (full, with line numbers)
  □ Get reproduction steps (exact inputs)
  □ Note environment (browser, Node version, OS)
  □ Check git history (when did it appear?)

□ CLASSIFICATION PHASE
  □ Classify error family (use master taxonomy)
  □ Determine severity (critical/high/medium/low)
  □ Check if it's a known pattern (grep master list)
  □ Document any new patterns found

□ ROOT CAUSE ANALYSIS
  □ Search similar issues in repo
  □ Check related files (imports, dependencies)
  □ Review recent changes to affected code
  □ Check test coverage (is this case tested?)

□ REPAIR PHASE
  □ Write test that reproduces error
  □ Implement fix (following pattern)
  □ Verify test passes
  □ Check for regressions (related code)
  □ Get code review

□ VERIFICATION PHASE
  □ All green gates pass
  □ No new warnings introduced
  □ Performance impact acceptable
  □ Documented in changelog

□ PREVENTION PHASE
  □ Add linting rule (if applicable)
  □ Update documentation
  □ Add to error classification rules
  □ Consider automated detection
```

---

**Status:** Complete master error families + repair patterns  
**Last Updated:** 2026-07-13  
**Next:** Implement remaining repair flows + GPT-5.6 integration
