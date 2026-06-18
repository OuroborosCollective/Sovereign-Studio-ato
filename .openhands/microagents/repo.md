# Sovereign Studio V3 — Repository Overview

## Project Description

**Sovereign Studio V3** is a hybrid mobile/desktop application that serves as an autonomous repository architect. It loads real GitHub repository snapshots, converts them into visible, guarded implementation packages, and publishes them as draft pull requests.

**Core principle:** Autonomous-feeling workflows must still pass through visible preview, functional guards, and deliberate user action before any GitHub writes occur.

---

## 🏛 Software Architecture Patterns

### React 19 Patterns

```typescript
// Component Composition Pattern
// ✅ DO: Use composition over inheritance
const Card = ({ children, header, footer }: CardProps) => (
  <div className="card">
    {header && <div className="card-header">{header}</div>}
    <div className="card-body">{children}</div>
    {footer && <div className="card-footer">{footer}</div>}
  </div>
);

// ✅ DO: Use explicit prop types with discriminated unions
type ButtonVariant = 'primary' | 'secondary' | 'danger';
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  loading?: boolean;
}

// ✅ DO: Use the `use` hook for promise resolution (React 19)
const { data, error, isLoading } = use(promise);

// ✅ DO: Use Server Components for data fetching
async function UserProfile({ userId }: { userId: string }) {
  const user = await db.user.findUnique({ where: { id: userId } });
  return <div>{user.name}</div>;
}

// ❌ DON'T: Avoid prop drilling beyond 2 levels — use context or Zustand
// ❌ DON'T: Avoid default exports for better refactoring support
```

### TypeScript Strict Patterns

```typescript
// ✅ DO: Use `satisfies` for type narrowing without widening
const config = {
  apiUrl: 'https://api.example.com',
  timeout: 5000,
} satisfies AppConfig;

// ✅ DO: Use branded types for domain primitives
type UserId = string & { readonly brand: unique symbol };
type RepoId = string & { readonly brand: unique symbol };

function createUserId(id: string): UserId {
  return id as UserId;
}

// ✅ DO: Use discriminated unions for state machines
type AsyncState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: T }
  | { status: 'error'; error: Error };

// ✅ DO: Exhaustive switch statements with never
function handleAction(action: Action): State {
  switch (action.type) {
    case 'SET_USER':
      return { ...state, user: action.user };
    case 'CLEAR_USER':
      return { ...state, user: null };
    default:
      const _exhaustive: never = action;
      throw new Error(`Unhandled action: ${_exhaustive}`);
  }
}

// ✅ DO: Use `infer` for conditional types
type ReturnType<T> = T extends (...args: any[]) => infer R ? R : never;
```

### Vite Build Patterns

```typescript
// vite.config.ts - Optimized for Capacitor
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { capacitorConfig } from './capacitor.config';

export default defineConfig({
  plugins: [react()],
  build: {
    target: 'esnext',
    minify: 'esbuild',
    rollupOptions: {
      output: {
        // Chunk splitting for better caching
        manualChunks: {
          vendor: ['react', 'react-dom'],
          state: ['@reduxjs/toolkit', 'zustand'],
          ai: ['@google/genai', '@google/generative-ai'],
        },
      },
    },
    // Asset inlining for small files
    assetsInlineLimit: 4096,
  },
  server: {
    port: 3000,
    host: '0.0.0.0',
  },
  optimizeDeps: {
    include: ['react', 'react-dom', '@reduxjs/toolkit'],
  },
});
```

### Capacitor 6 Integration Patterns

```typescript
// ✅ DO: Use the official Plugins correctly
import { Capacitor } from '@capacitor/core';
import { Camera, CameraResultType } from '@capacitor/camera';

async function takePhoto(): Promise<string | null> {
  if (!Capacitor.isNativePlatform()) {
    // Fallback for web
    return null;
  }
  
  try {
    const image = await Camera.getPhoto({
      quality: 90,
      allowEditing: true,
      resultType: CameraResultType.DataUrl,
    });
    return image.dataUrl ?? null;
  } catch (error) {
    console.error('Camera error:', error);
    return null;
  }
}

// ✅ DO: Use App Shell pattern for fast initial render
// src/AppShell.tsx
const AppShell = ({ children }: { children: React.ReactNode }) => {
  const [isReady, setIsReady] = useState(false);
  
  useEffect(() => {
    // Initialize Capacitor plugins
    initializePlugins().then(() => setIsReady(true));
  }, []);
  
  if (!isReady) return <SplashScreen />;
  return <>{children}</>;
};

// ✅ DO: Handle deep links properly
import { App } from '@capacitor/app';

App.addListener('appUrlOpen', ({ url }) => {
  // Parse deep link and navigate
  const path = extractPath(url);
  history.push(path);
});
```

### Redux Toolkit Patterns

```typescript
// ✅ DO: Use createSlice for feature slices
import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';

interface UserState {
  entities: Record<string, User>;
  loading: 'idle' | 'pending' | 'succeeded' | 'failed';
  error: string | null;
}

const userSlice = createSlice({
  name: 'users',
  initialState: { entities: {}, loading: 'idle', error: null } as UserState,
  reducers: {
    userAdded: (state, action: PayloadAction<User>) => {
      state.entities[action.payload.id] = action.payload;
    },
    userUpdated: (state, action: PayloadAction<Partial<User> & { id: string }>) => {
      const user = state.entities[action.payload.id];
      if (user) Object.assign(user, action.payload);
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchUser.pending, (state) => {
        state.loading = 'pending';
      })
      .addCase(fetchUser.fulfilled, (state, action) => {
        state.loading = 'succeeded';
        state.entities[action.payload.id] = action.payload;
      });
  },
});

// ✅ DO: Use RTK Query for API caching
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

export const githubApi = createApi({
  reducerPath: 'githubApi',
  baseQuery: fetchBaseQuery({ baseUrl: 'https://api.github.com' }),
  tagTypes: ['Repo', 'File'],
  endpoints: (builder) => ({
    getRepo: builder.query<Repo, string>({
      query: (owner, repo) => `/repos/${owner}/${repo}`,
      providesTags: (result, error, owner, repo) => [
        { type: 'Repo', id: `${owner}/${repo}` }
      ],
    }),
  }),
});
```

### Zustand State Patterns

```typescript
// ✅ DO: Use slices pattern for modular stores
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface AppState {
  theme: 'light' | 'dark';
  sidebarOpen: boolean;
  setTheme: (theme: 'light' | 'dark') => void;
  toggleSidebar: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      theme: 'light',
      sidebarOpen: false,
      setTheme: (theme) => set({ theme }),
      toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
    }),
    { name: 'app-storage' }
  )
);

// ✅ DO: Use subscribeWithSelector for side effects
useStore.subscribe(
  (state) => state.user,
  (user) => {
    if (user) {
      analytics.identify(user.id);
    }
  }
);

// ✅ DO: Combine with Immer for immutable updates
import { immer } from 'zustand/middleware/immer';

interface EditorState {
  content: string;
  selection: { start: number; end: number } | null;
}

export const useEditorStore = create<EditorState>()(
  immer((set) => ({
    content: '',
    selection: null,
    setContent: (content) => set((draft) => { draft.content = content; }),
  }))
);
```

---

## 🏗 GitHub-Centric Architecture Patterns

### Repository Loading Pattern

```typescript
// ✅ DO: Use repository snapshot pattern for offline support
interface RepoSnapshot {
  id: string;
  owner: string;
  repo: string;
  branch: string;
  tree: TreeNode[];
  files: Map<string, FileContent>;
  fetchedAt: Date;
  checksum: string;
}

async function loadRepo(url: string): Promise<RepoSnapshot> {
  const parsed = parseGitHubUrl(url);
  const [owner, repo] = parsed.fullName.split('/');
  
  // Fetch tree structure
  const tree = await github.repos.getContent({
    owner,
    repo,
    path: '',
    ref: parsed.branch,
  });
  
  // Create deterministic snapshot ID
  const checksum = await computeChecksum(tree);
  
  return {
    id: createSnapshotId(owner, repo, parsed.branch, checksum),
    owner,
    repo,
    branch: parsed.branch,
    tree: flattenTree(tree),
    files: new Map(),
    fetchedAt: new Date(),
    checksum,
  };
}

// ✅ DO: Implement diff preview before commit
async function generateDiff(
  original: RepoSnapshot,
  modified: Map<string, FileContent>
): Promise<DiffResult> {
  const diffs: FileDiff[] = [];
  
  for (const [path, content] of modified) {
    const originalContent = original.files.get(path);
    if (originalContent) {
      const diff = diffWords(originalContent.body, content.body);
      diffs.push({ path, diff, type: 'modified' });
    } else {
      diffs.push({ path, diff: null, type: 'added' });
    }
  }
  
  return { files: diffs, summary: summarizeChanges(diffs) };
}
```

### Draft PR Pattern

```typescript
// ✅ DO: Always use draft PR for autonomous workflows
interface DraftPRContext {
  owner: string;
  repo: string;
  branch: string;
  title: string;
  body: string;
  changes: FileChange[];
}

async function publishDraftPR(ctx: DraftPRContext): Promise<string> {
  // 1. Create feature branch
  const branch = await github.git.createRef({
    owner: ctx.owner,
    repo: ctx.repo,
    ref: `refs/heads/${ctx.branch}`,
    sha: await github.git.getRef({ owner: ctx.owner, repo: ctx.repo, ref: 'heads/main' }),
  });
  
  // 2. Create commits
  for (const change of ctx.changes) {
    const blob = await github.git.createBlob({
      owner: ctx.owner,
      repo: ctx.repo,
      content: change.content,
      encoding: 'utf-8',
    });
    // ... create tree and commit
  }
  
  // 3. Create draft PR
  const pr = await github.pulls.create({
    owner: ctx.owner,
    repo: ctx.repo,
    title: ctx.title,
    body: ctx.body,
    head: ctx.branch,
    base: 'main',
    draft: true, // Always draft!
  });
  
  return pr.number;
}

// ✅ DO: Implement PR review guardrails
interface ReviewGate {
  checksPass: boolean;
  approvals: number;
  conflicts: boolean;
  CIStatus: 'pending' | 'success' | 'failure';
}

function canMerge(gate: ReviewGate): boolean {
  return (
    gate.checksPass &&
    gate.approvals >= 1 &&
    !gate.conflicts &&
    gate.CIStatus === 'success'
  );
}
```

---

## 🤖 AI Integration Patterns

### Gemini Service Pattern

```typescript
// ✅ DO: Use structured prompts with clear schemas
interface AIGenerationRequest {
  mission: string;
  context: {
    repoSnapshot: RepoSnapshot;
    files: FileContent[];
    language?: string;
  };
  constraints: {
    maxTokens: number;
    temperature: number;
  };
}

async function generateCode(req: AIGenerationRequest): Promise<GeneratedCode> {
  const prompt = buildPrompt(req);
  
  const result = await gemini.generateContent({
    contents: [{ role: 'user', parts: [{ text: prompt }] }],
    generationConfig: {
      maxOutputTokens: req.constraints.maxTokens,
      temperature: req.constraints.temperature,
      responseMimeType: 'application/json',
      responseSchema: GenerationSchema,
    },
  });
  
  return parseGeneratedCode(result);
}

// ✅ DO: Implement retry with exponential backoff
async function withRetry<T>(
  fn: () => Promise<T>,
  maxRetries = 3,
  baseDelay = 1000
): Promise<T> {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fn();
    } catch (error) {
      if (i === maxRetries - 1) throw error;
      await sleep(baseDelay * Math.pow(2, i));
    }
  }
  throw new Error('Unreachable');
}

// ✅ DO: Use streaming for long generations
async function* streamGenerate(
  prompt: string
): AsyncGenerator<string, void, unknown> {
  const stream = await gemini.generateContentStream({
    contents: [{ role: 'user', parts: [{ text: prompt }] }],
  });
  
  for await (const chunk of stream) {
    yield chunk.text;
  }
}
```

### System Grounding Pattern

```typescript
// ✅ DO: Ground AI outputs with verifiable facts
interface GroundedOutput<T> {
  content: T;
  groundingSources: GroundingSource[];
  confidenceScore: number;
}

interface GroundingSource {
  type: 'file' | 'url' | 'fact';
  reference: string;
  verified: boolean;
}

async function groundOutput<T>(
  content: T,
  context: Context
): Promise<GroundedOutput<T>> {
  const sources = await verifySources(content, context);
  const confidence = calculateConfidence(sources);
  
  return {
    content,
    groundingSources: sources,
    confidenceScore: confidence,
  };
}

// ✅ DO: Implement AI response validation
interface ValidationResult {
  valid: boolean;
  errors: ValidationError[];
  suggestions: string[];
}

function validateAIResponse(
  response: GeneratedCode,
  schema: ZodSchema
): ValidationResult {
  const result = schema.safeParse(response);
  
  if (!result.success) {
    return {
      valid: false,
      errors: result.error.issues.map(i => ({
        path: i.path.join('.'),
        message: i.message,
      })),
      suggestions: [],
    };
  }
  
  // Additional semantic validation
  const suggestions = checkCodeQuality(result.data);
  
  return {
    valid: suggestions.length === 0,
    errors: [],
    suggestions,
  };
}

// ✅ DO: Use Constitutional AI principles for self-correction
interface AICorrection {
  original: string;
  critique: string;
  revision: string;
}

async function selfCorrect(
  output: string,
  principles: string[]
): Promise<AICorrection> {
  const critique = await gemini.generateContent(
    `Review this output against these principles:\n${principles.join('\n')}\n\nOutput: ${output}`
  );
  
  const revision = await gemini.generateContent(
    `Revise the output based on this critique:\n${critique}\n\nOriginal: ${output}`
  );
  
  return { original: output, critique, revision };
}
```

---

## 🛡️ Runtime Guard Patterns

### Functional Guards

```typescript
// ✅ DO: Implement defense in depth
interface GuardChain {
  preFlight: Guard[];
  main: Guard[];
  postFlight: Guard[];
}

const guardChain: GuardChain = {
  preFlight: [
    validateRepoSnapshotNotEmpty,
    validateNoForbiddenPaths,
    validateFileSizeLimits,
  ],
  main: [
    validateDiffSafety,
    validateNoSecretsInDiff,
    validateCIWillPass,
  ],
  postFlight: [
    validatePRTitleFormat,
    validatePRDescriptionPresent,
  ],
};

async function runGuards(
  context: GuardContext,
  chain: GuardChain
): Promise<GuardResult> {
  for (const guard of [...chain.preFlight, ...chain.main, ...chain.postFlight]) {
    const result = await guard.check(context);
    if (!result.pass) {
      return {
        pass: false,
        failedGuard: guard.name,
        reason: result.reason,
        remediation: result.remediation,
      };
    }
  }
  return { pass: true };
}

// ✅ DO: Use circuit breaker for external calls
class CircuitBreaker {
  private failures = 0;
  private lastFailure = 0;
  private state: 'closed' | 'open' | 'half-open' = 'closed';
  
  async call<T>(fn: () => Promise<T>): Promise<T> {
    if (this.state === 'open') {
      if (Date.now() - this.lastFailure > 30000) {
        this.state = 'half-open';
      } else {
        throw new Error('Circuit breaker open');
      }
    }
    
    try {
      const result = await fn();
      this.failures = 0;
      this.state = 'closed';
      return result;
    } catch (error) {
      this.failures++;
      this.lastFailure = Date.now();
      if (this.failures >= 5) {
        this.state = 'open';
      }
      throw error;
    }
  }
}
```

### Telemetry Pattern

```typescript
// ✅ DO: Implement structured telemetry
interface TelemetryEvent {
  name: string;
  properties: Record<string, unknown>;
  timestamp: number;
  traceId?: string;
}

function trackEvent(event: TelemetryEvent): void {
  // Send to analytics
  posthog.capture(event.name, {
    ...event.properties,
    timestamp: event.timestamp,
  });
  
  // Also log for debugging
  console.log(`[TELEMETRY] ${event.name}`, event.properties);
}

// ✅ DO: Use OpenTelemetry for distributed tracing
import { trace, context } from '@opentelemetry/api';

const tracer = trace.getTracer('sovereign-studio');

async function tracedOperation<T>(
  name: string,
  fn: () => Promise<T>
): Promise<T> {
  return tracer.startActiveSpan(name, async (span) => {
    try {
      const result = await fn();
      span.setStatus({ code: SpanStatusCode.OK });
      return result;
    } catch (error) {
      span.setStatus({ code: SpanStatusCode.ERROR });
      span.recordException(error as Error);
      throw error;
    } finally {
      span.end();
    }
  });
}
```

---

## 📐 Best Practices for Software Architects

### 1. Code Organization

```
✅ Feature-based structure over type-based
✅ Colocation of related code (components, hooks, utils together)
✅ Shared code in /shared, not duplicated
✅ Clear module boundaries with barrel exports
```

### 2. Error Handling

```typescript
// ✅ DO: Use error boundaries for React errors
class ErrorBoundary extends React.Component<Props, State> {
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }
  
  componentDidCatch(error: Error, info: React.ErrorInfo) {
    logError(error, info.componentStack);
  }
}

// ✅ DO: Use Result types for fallible operations
type Result<T, E = Error> = 
  | { ok: true; value: T }
  | { ok: false; error: E };

function tryCatch<T>(fn: () => T): Result<T> {
  try {
    return { ok: true, value: fn() };
  } catch (error) {
    return { ok: false, error: error as Error };
  }
}
```

### 3. Security

```typescript
// ✅ DO: Never log secrets
// ❌ DON'T: console.log('Token:', token);

// ✅ DO: Use environment variables for secrets
const apiKey = import.meta.env.VITE_API_KEY;

// ✅ DO: Implement CSP headers
const cspDirectives = {
  'default-src': ["'self'"],
  'script-src': ["'self'"],
  'style-src': ["'self'", "'unsafe-inline'"],
  'connect-src': ["'self'", 'https://api.github.com'],
};
```

### 4. Performance

```typescript
// ✅ DO: Use React.memo for expensive components
const ExpensiveList = React.memo<ListProps>(
  ({ items }) => {
    return items.map(item => <ListItem key={item.id} item={item} />);
  },
  (prev, next) => prev.items.length === next.items.length
);

// ✅ DO: Virtualize long lists
import { FixedSizeList } from 'react-window';

function VirtualFileList({ files }: { files: File[] }) {
  return (
    <FixedSizeList
      height={400}
      itemCount={files.length}
      itemSize={32}
      itemData={files}
    >
      {({ index, style }) => (
        <div style={style}>{files[index].name}</div>
      )}
    </FixedSizeList>
  );
}

// ✅ DO: Code split at route level
const RepoBrowser = lazy(() => import('./features/repo/RepoBrowser'));
const CodeEditor = lazy(() => import('./features/editor/CodeEditor'));
```

### 5. Testing

```typescript
// ✅ DO: Test behavior, not implementation
// ❌ DON'T: test('component renders correctly')
// ✅ DO: test('shows error when repo loading fails')

// ✅ DO: Use userEvent over fireEvent
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

test('submits form with user input', async () => {
  render(<RepoForm />);
  
  await userEvent.type(screen.getByLabelText('Repository URL'), 'https://github.com/owner/repo');
  await userEvent.click(screen.getByRole('button', { name: 'Load' }));
  
  expect(screen.getByText('Loading...')).toBeInTheDocument();
});

// ✅ DO: Use contract tests for API integration
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';

const server = setupServer(
  http.get('https://api.github.com/repos/:owner/:repo', ({ params }) => {
    return HttpResponse.json({ id: 1, name: params.repo });
  })
);
```

---

## 🔧 Development Workflow

### Feature Flags

```typescript
// ✅ DO: Use feature flags for gradual rollout
const FEATURES = {
  AI_CODESIGN: import.meta.env.VITE_FEATURE_AI_CODESIGN === 'true',
  NEW_EDITOR: import.meta.env.VITE_FEATURE_NEW_EDITOR === 'true',
};

function CodeEditor() {
  return FEATURES.NEW_EDITOR ? <NewEditor /> : <LegacyEditor />;
}
```

### CI/CD Pipeline

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
      - run: npm ci
      - run: npm run type-check
      - run: npm run test:unit
      - run: npm run audit:sovereign
  
  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm run build:web
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/
```

### Commit Convention

```
feat: add new feature
fix: bug fix
refactor: code refactoring
test: add/update tests
docs: documentation changes
chore: maintenance tasks
perf: performance improvements
```

---

## 📚 Quick Reference Commands

```bash
# Development
npm run dev              # Start dev server
npm run build:web        # Production build

# Quality Gates
npm run type-check       # TypeScript check
npm run lint             # ESLint
npm run audit:sovereign  # Custom static audit
npm run test:unit        # Unit tests only
npm run test:integration # Integration tests
npm run test:run         # All tests

# Mobile
npx cap copy             # Copy web to Android
npx cap sync android     # Sync plugins
npx cap open android     # Open in Android Studio
npm run build:android    # Build APK
```

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Frontend | React 19, TypeScript, Vite |
| Mobile Bridge | Capacitor 6 (Android/iOS) |
| State Management | Redux Toolkit, Zustand |
| AI Integration | Google Gemini SDK |
| Testing | Vitest, React Testing Library |
| Publishing | Draft PR via GitHub REST API |

---

## Project Structure

```
/
├── src/
│   ├── features/           # Feature-based modules
│   │   ├── ai/            # Gemini AI service
│   │   ├── billing/       # Billing/paywall logic
│   │   ├── canvas/        # Canvas/vector editor
│   │   ├── github/        # GitHub API integration
│   │   ├── ouroboros/     # Core workflow engine
│   │   └── product/       # Main product runtime
│   │       ├── runtime/   # Runtime guards & validation
│   │       ├── components/# UI components
│   │       └── brain/     # AI brain contract
│   ├── mobile-workflow-*.ts  # Mobile workflow orchestration
│   └── App.tsx            # Main application shell
├── android/               # Capacitor Android project
├── sovereign-studio-rn/   # React Native components
└── scripts/               # Build & release scripts
```

---

## Key Modules

### 1. GitHub Integration (`src/features/github/`)
- `useGithubRepo.ts` — Loads real GitHub tree entries
- `githubPackagePublisher.ts` — Creates branch/commit and opens draft PR
- `utils.ts` — GitHub URL parsing and normalization

### 2. Runtime Guards (`src/features/product/runtime/`)
- `sovereignRuntime.ts` — Brain-gated implementation packages
- `sovereignFunctionalGuards.ts` — Blocks empty snapshots, duplicate paths, forbidden paths
- `repoLaunchReadiness.ts` — Launch readiness scoring
- `containerDecisionGrammar.ts` — Container decision grammar
- `containerIntelligenceCoverage.ts` — Coverage registry for containers

### 3. Mobile Workflow (`src/`)
- `mobile-workflow-orchestrator.ts` — Workflow state machine
- `mobile-workflow-pattern-rules.ts` — Pattern-based decision rules

---

## How to Run

### Prerequisites
- Node.js >= 22
- npm >= 10
- Android Studio + SDK (for mobile builds)

### Setup & Development

```bash
# Install dependencies
npm install

# Start web dev server (http://localhost:3000)
npm run dev

# Run type checking
npm run type-check

# Run linting
npm run lint

# Run unit tests
npm run test:unit
# or
npm run test:run    # Run all tests including integration
```

### Building

```bash
# Build web app
npm run build:web

# Build Android APK
npm run build:android

# Build release APK (requires keystore credentials)
npm run build:apk

# Full build with Android sync
npm run build
```

---

## Guardrails (sovereign.guard.json)

Before any change is considered complete, the following must pass:

```bash
npm run audit:sovereign   # Static audit
npm run type-check        # TypeScript check
npm run test:run          # All tests
npm run build:web         # Production build
```

**Important:** Do not stop after fixing only the files in the latest change. Fix all failures before calling work done.

---

## Testing

```bash
# Unit tests only
npm run test:unit

# Integration tests
npm run test:integration

# E2E tests
npm run test:e2e

# UI mode
npm run test:ui
```

Key test files:
- `src/features/product/runtime/sovereignFunctionalGuards.test.ts`
- `src/features/product/runtime/repoLaunchReadiness.test.ts`
- `src/features/github/utils.test.ts`
- `src/mobile-workflow-pattern-rules.test.ts`

---

## Product Rules (UI Layout)

The app follows these layout principles:
- **Left:** GitHub file tree + idea/order input
- **Center:** Chat, matrix-style file editor, live status
- **Right:** History log and plain-language analysis
- **Flow:** Free-first routing before optional user keys
- **Errors:** Visible fix loop, user confirmation before writes

---

## Architecture Notes

- Draft PR only — no direct main branch writes
- Functional guards block unauthorized file generation
- Brain-gated packages require AI validation before publishing
- Container intelligence coverage tracks runtime/test/pattern status

---

## Useful Commands

```bash
npx cap copy        # Copy web assets to Android
npx cap sync android # Sync Capacitor plugins
npx cap open android # Open in Android Studio
```
