# Sovereign Studio V3 — Repository Overview & Agent Pattern Guide

> **⚠️ DISCLAIMER: Pattern Guide — Not a Technology Guarantee**
>
> This file is a **pattern knowledge base for AI agents**. The patterns described here represent architectural best practices and know-how. Before applying any pattern, **always verify**:
> - Check `package.json` for actual dependencies
> - Verify runtime imports in the actual codebase
> - Check existing architecture patterns in `src/`
> - Consult existing tests in `src/**/*.test.ts`
>
> **Do NOT assume listed technologies are installed or used.** Some patterns (e.g., Redux, Zustand, OpenTelemetry) may be aspirational or partially implemented. Always cross-reference with actual project state before deriving new code paths.

---

## Project Description

**Sovereign Studio V3** is a hybrid mobile/desktop application that serves as an autonomous repository architect. It loads real GitHub repository snapshots, converts them into visible, guarded implementation packages, and publishes them as draft pull requests.

**Core principle:** Autonomous-feeling workflows must still pass through visible preview, functional guards, and deliberate user action before any GitHub writes occur.

---

## 🏛 Software Architecture Patterns

### React 19 Patterns with Runtime Intelligence

```typescript
// Component Composition Pattern with Runtime Intelligence
// ✅ DO: Use composition over inheritance
const Card = ({ children, header, footer, runtimeContext }: CardProps & { runtimeContext: RuntimeContext }) => {
  useRuntimeTrack('card-render', { component: 'Card' });
  return (
    <div className="card" data-runtime-id={runtimeContext.componentId}>
      {header && <div className="card-header" data-telemetry="header">{header}</div>}
      <div className="card-body" data-runtime-context="content">{children}</div>
      {footer && <div className="card-footer" data-telemetry="footer">{footer}</div>}
    </div>
  );
};

// ✅ DO: Use explicit prop types with discriminated unions
type ButtonVariant = 'primary' | 'secondary' | 'danger';
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  loading?: boolean;
  telemetry?: TelemetryConfig;
}

// ✅ DO: Use the `use` hook for promise resolution (React 19)
const { data, error, isLoading } = use(promise);

// ✅ DO: Use Server Components for data fetching with runtime intel
async function UserProfile({ userId }: { userId: string }) {
  const startTime = performance.now();
  const user = await db.user.findUnique({ where: { id: userId } });
  trackEvent('server_component_render', { component: 'UserProfile', duration: performance.now() - startTime });
  return <div>{user.name}</div>;
}

// ✅ DO: Use action signals for runtime decision making
interface ActionSignal {
  type: 'navigation' | 'api_call' | 'state_change' | 'ai_request';
  payload: unknown;
  timestamp: number;
  traceId: string;
}

// ❌ DON'T: Avoid prop drilling beyond 2 levels
// ❌ DON'T: Avoid default exports for better refactoring support
```

### TypeScript Strict Patterns with Runtime Validation

```typescript
// ✅ DO: Use `satisfies` for type narrowing without widening
const config = { apiUrl: 'https://api.example.com', timeout: 5000 } satisfies AppConfig;

// ✅ DO: Use branded types for domain primitives with runtime validation
type UserId = string & { readonly brand: unique symbol };
type RepoId = string & { readonly brand: unique symbol };
type PatternId = string & { readonly brand: unique symbol };

function createUserId(id: string): UserId {
  if (!isValidUserIdFormat(id)) throw new RuntimeValidationError('Invalid user ID format', { id, pattern: 'user_id' });
  return id as UserId;
}

// ✅ DO: Use discriminated unions for state machines
type AsyncState<T> =
  | { status: 'idle' }
  | { status: 'loading'; progress?: number }
  | { status: 'success'; data: T; timestamp: number }
  | { status: 'error'; error: Error; retryable: boolean };

// ✅ DO: Exhaustive switch statements with never
function handleAction(action: Action): State {
  switch (action.type) {
    case 'SET_USER': return { ...state, user: action.user };
    case 'CLEAR_USER': return { ...state, user: null };
    default: const _exhaustive: never = action; throw new Error(`Unhandled action: ${_exhaustive}`);
  }
}

// ✅ DO: Runtime type guards with validation logging
function isValidContainerDecision(obj: unknown): obj is ContainerDecision {
  const result = containerDecisionGuard.safeParse(obj);
  if (!result.success) {
    trackEvent('runtime_validation_failed', { schema: 'ContainerDecision', errors: result.error.issues });
    return false;
  }
  return true;
}
```

### Vite Build Patterns with Chunk Intelligence

```typescript
// vite.config.ts - Optimized for Capacitor with runtime chunks
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    target: 'esnext',
    minify: 'esbuild',
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          if (id.includes('node_modules/react')) return 'vendor';
          if (id.includes('@reduxjs/toolkit')) return 'state';
          if (id.includes('@google/genai')) return 'ai';
          if (id.includes('features/product/runtime')) return 'runtime';
        },
      },
    },
    sourcemap: true,
  },
  server: { port: 3000, host: '0.0.0.0' },
  optimizeDeps: { include: ['react', 'react-dom', '@reduxjs/toolkit', 'zustand'] },
});
```

### Capacitor 6 Integration Patterns with Native Intelligence

```typescript
import { Capacitor } from '@capacitor/core';
import { Camera, CameraResultType } from '@capacitor/camera';

interface NativeFeatureConfig {
  enableTelemetry: boolean;
  fallbackToWeb: boolean;
  retryAttempts: number;
}

// ✅ DO: Use the official Plugins with runtime telemetry
async function takePhoto(config: NativeFeatureConfig = { enableTelemetry: true, fallbackToWeb: true, retryAttempts: 3 }): Promise<string | null> {
  const traceId = generateTraceId();
  const startTime = performance.now();

  if (!Capacitor.isNativePlatform()) {
    if (config.enableTelemetry) trackEvent('native_feature_fallback', { feature: 'camera', platform: 'web', traceId });
    return null;
  }

  try {
    const image = await withRetry(() => Camera.getPhoto({ quality: 90, allowEditing: true, resultType: CameraResultType.DataUrl }), config.retryAttempts);
    if (config.enableTelemetry) trackEvent('native_feature_success', { feature: 'camera', duration: performance.now() - startTime, traceId, platform: Capacitor.getPlatform() });
    return image.dataUrl ?? null;
  } catch (error) {
    if (config.enableTelemetry) trackEvent('native_feature_error', { feature: 'camera', error: (error as Error).message, traceId });
    if (config.fallbackToWeb) return null;
    throw error;
  }
}

// ✅ DO: Use App Shell pattern with runtime readiness tracking
const AppShell = ({ children }: { children: React.ReactNode }) => {
  const [isReady, setIsReady] = useState(false);
  const [readiness, setReadiness] = useState<ReadinessState>({ status: 'initializing' });

  useEffect(() => {
    const initializeApp = async () => {
      try {
        trackEvent('app_init_start', { traceId });
        await initializePlugins();
        setReadiness({ status: 'ready', timestamp: Date.now(), traceId });
        trackEvent('app_init_complete', { duration: performance.now(), traceId });
        setIsReady(true);
      } catch (error) {
        setReadiness({ status: 'error', error: (error as Error).message, retryable: true });
        trackEvent('app_init_error', { error: (error as Error).message });
      }
    };
    initializeApp();
  }, []);

  if (!isReady) return <SplashScreen readiness={readiness} />;
  return <RuntimeProvider traceId={readiness.traceId}>{children}</RuntimeProvider>;
};
```

### Redux Toolkit Patterns with Runtime Intelligence

```typescript
import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';

// ✅ DO: Use createSlice with telemetry middleware
interface UserState {
  entities: Record<string, User>;
  loading: 'idle' | 'pending' | 'succeeded' | 'failed';
  lastUpdated: number | null;
  operationTrace: OperationTrace[];
}

const userSlice = createSlice({
  name: 'users',
  initialState: { entities: {}, loading: 'idle', error: null, lastUpdated: null, operationTrace: [] } as UserState,
  reducers: {
    userAdded: {
      reducer: (state, action: PayloadAction<User & { traceId: string }>) => {
        const { traceId, ...user } = action.payload;
        state.entities[user.id] = user;
        state.lastUpdated = Date.now();
        state.operationTrace.push({ operation: 'userAdded', traceId, timestamp: Date.now() });
        trackEvent('state_mutation', { slice: 'users', operation: 'userAdded', entityId: user.id, traceId });
      },
      prepare: (user: User) => ({ payload: { ...user, traceId: generateTraceId() } })
    },
  },
});

// ✅ DO: Use createAsyncThunk with comprehensive telemetry
const fetchUser = createAsyncThunk<User, string, { rejectValue: FetchError }>(
  'users/fetchUser',
  async (userId, { rejectWithValue }) => {
    const traceId = generateTraceId();
    const startTime = performance.now();
    trackAsyncOperation('fetchUser', { userId, traceId }, 'started');
    try {
      const response = await api.getUser(userId);
      trackAsyncOperation('fetchUser', { userId, traceId, duration: performance.now() - startTime, success: true }, 'completed');
      return { ...response, traceId };
    } catch (error) {
      trackAsyncOperation('fetchUser', { userId, traceId, error: (error as Error).message }, 'failed');
      return rejectWithValue({ message: (error as Error).message, userId, traceId, retryable: isRetryableError(error) });
    }
  }
);

// ✅ DO: Use RTK Query with automatic cache telemetry
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

export const githubApi = createApi({
  reducerPath: 'githubApi',
  baseQuery: fetchBaseQuery({ baseUrl: 'https://api.github.com' }),
  tagTypes: ['Repo', 'File', 'User', 'Workflow', 'PR'],
  endpoints: (builder) => ({
    getRepo: builder.query<Repo, { owner: string; repo: string }>({
      query: ({ owner, repo }) => `/repos/${owner}/${repo}`,
      providesTags: (result, error, { owner, repo }) => [{ type: 'Repo', id: `${owner}/${repo}` }],
      onQueryStarted: async ({ owner, repo }, { queryFulfilled }) => {
        const traceId = generateTraceId();
        trackEvent('api_query_started', { endpoint: 'getRepo', owner, repo, traceId });
        try {
          const { data } = await queryFulfied;
          trackEvent('api_query_success', { endpoint: 'getRepo', owner, repo, cached: !!data, traceId });
        } catch (error) {
          trackEvent('api_query_error', { endpoint: 'getRepo', owner, repo, error: (error as Error).message, traceId });
        }
      },
    }),
  }),
});
```

### Zustand State Patterns with Runtime Observability

```typescript
import { create } from 'zustand';
import { persist, subscribeWithSelector } from 'zustand/middleware';

// ✅ DO: Use slices pattern with comprehensive telemetry
interface AppState {
  theme: 'light' | 'dark';
  sidebarOpen: boolean;
  traceId: string | null;
  setTheme: (theme: 'light' | 'dark') => void;
  toggleSidebar: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    subscribeWithSelector((set, get) => ({
      theme: 'light',
      sidebarOpen: false,
      traceId: null,
      setTheme: (theme) => {
        const prev = get().theme;
        const traceId = generateTraceId();
        set({ theme, traceId });
        trackEvent('state_change', { store: 'app', field: 'theme', from: prev, to: theme, traceId });
      },
      toggleSidebar: () => {
        const prev = get().sidebarOpen;
        const traceId = generateTraceId();
        set(state => ({ sidebarOpen: !state.sidebarOpen, traceId }));
        trackEvent('state_change', { store: 'app', field: 'sidebarOpen', from: prev, to: !prev, traceId });
      },
    })),
    { name: 'app-storage', partialize: (state) => ({ theme: state.theme }) }
  )
);

// ✅ DO: Use Immer middleware with immutable operation tracking
import { immer } from 'zustand/middleware/immer';

interface EditorState {
  content: string;
  selection: { start: number; end: number } | null;
  history: ContentSnapshot[];
  traceId: string | null;
}

export const useEditorStore = create<EditorState>()(
  immer((set, get) => ({
    content: '',
    selection: null,
    history: [],
    traceId: null,
    setContent: (content, traceId = generateTraceId()) => {
      const prev = get().content;
      set((draft) => {
        if (draft.history.length === 0 || draft.content !== content) {
          draft.history.push({ content: draft.content, timestamp: Date.now(), traceId: draft.traceId });
        }
        draft.content = content;
        draft.traceId = traceId;
      });
      trackEvent('editor_content_change', { previousLength: prev.length, newLength: content.length, traceId, diff: computeDiff(prev, content) });
    },
  }))
);
```

---

## 🌐 REST API Patterns with Runtime Intelligence

### API Client Patterns

```typescript
interface ApiClientConfig {
  baseUrl: string;
  timeout: number;
  retries: number;
  telemetry: TelemetryConfig;
}

// ✅ DO: Use typed API client with comprehensive telemetry
class ApiClient {
  constructor(private config: ApiClientConfig) {}

  async get<T>(path: string, options?: RequestOptions): Promise<ApiResponse<T>> {
    const traceId = generateTraceId();
    const startTime = performance.now();
    trackEvent('api_request', { method: 'GET', path, traceId, timestamp: startTime });

    try {
      const response = await this.request<T>({ method: 'GET', path, traceId, ...options });
      trackEvent('api_response', { method: 'GET', path, status: response.status, duration: performance.now() - startTime, traceId, cached: response.cached });
      return response;
    } catch (error) {
      trackEvent('api_error', { method: 'GET', path, error: (error as Error).message, duration: performance.now() - startTime, traceId });
      throw error;
    }
  }
}

// ✅ DO: Implement request deduplication for concurrent calls
const pendingRequests = new Map<string, Promise<unknown>>();

async function deduplicatedRequest<T>(key: string, fn: () => Promise<T>): Promise<T> {
  if (pendingRequests.has(key)) {
    trackEvent('request_deduplicated', { key });
    return pendingRequests.get(key) as Promise<T>;
  }
  const promise = fn().finally(() => pendingRequests.delete(key));
  pendingRequests.set(key, promise);
  return promise;
}

// ✅ DO: Use response caching with TTL
interface CacheEntry<T> { data: T; expiresAt: number; traceId: string; }

class ResponseCache {
  private cache = new Map<string, CacheEntry<unknown>>();

  get<T>(key: string): T | null {
    const entry = this.cache.get(key);
    if (!entry) return null;
    if (Date.now() > entry.expiresAt) { this.cache.delete(key); trackEvent('cache_expired', { key }); return null; }
    trackEvent('cache_hit', { key, ttl: entry.expiresAt - Date.now() });
    return entry.data as T;
  }

  set<T>(key: string, data: T, ttlMs: number, traceId: string): void {
    this.cache.set(key, { data, expiresAt: Date.now() + ttlMs, traceId });
    trackEvent('cache_set', { key, ttl: ttlMs });
  }
}
```

### REST Endpoints Pattern with GitHub API

```typescript
// ✅ DO: Use resource-based endpoint patterns
interface ResourceEndpoints {
  repos: {
    list: (params: ListReposParams) => Promise<Repo[]>;
    get: (owner: string, repo: string) => Promise<Repo>;
    create: (body: CreateRepoBody) => Promise<Repo>;
  };
  contents: {
    get: (owner: string, repo: string, path: string, ref?: string) => Promise<FileContent>;
    create: (owner: string, repo: string, path: string, body: CreateFileBody) => Promise<FileCommit>;
    update: (owner: string, repo: string, path: string, body: UpdateFileBody) => Promise<FileCommit>;
  };
  pulls: {
    list: (owner: string, repo: string, params?: ListPRsParams) => Promise<PR[]>;
    get: (owner: string, repo: string, number: number) => Promise<PR>;
    create: (owner: string, repo: string, body: CreatePRBody) => Promise<PR>;
    update: (owner: string, repo: string, number: number, body: UpdatePRBody) => Promise<PR>;
    merge: (owner: string, repo: string, number: number, body: MergePRBody) => Promise<MergeResult>;
  };
  actions: {
    listWorkflows: (owner: string, repo: string) => Promise<Workflow[]>;
    getWorkflow: (owner: string, repo: string, workflowId: number) => Promise<Workflow>;
    listRuns: (owner: string, repo: string, workflowId: number) => Promise<WorkflowRun[]>;
    getRun: (owner: string, repo: string, runId: number) => Promise<WorkflowRun>;
    rerun: (owner: string, repo: string, runId: number) => Promise<void>;
  };
}

// ✅ DO: Implement GraphQL for complex queries
interface GraphQLClient {
  query<T>(query: string, variables?: Record<string, unknown>): Promise<T>;
  mutate<T>(mutation: string, variables?: Record<string, unknown>): Promise<T>;
}

async function getRepoWithDetails(owner: string, repo: string): Promise<RepoDetails> {
  const query = `
    query GetRepo($owner: String!, $repo: String!) {
      repository(owner: $owner, name: $repo) {
        id name description owner { login avatarUrl }
        defaultBranchRef { name } primaryLanguage { name color }
        stargazerCount forkCount
        issues(first: 5, states: OPEN) { totalCount nodes { title state url } }
        pullRequests(first: 5, states: OPEN) { totalCount nodes { title state url } }
      }
    }
  `;
  return graphqlClient.query<RepoDetails>(query, { owner, repo });
}
```

---

## 🏗 GitHub-Centric Architecture Patterns with Runtime Intelligence

### Repository Loading with Snapshot Intelligence

```typescript
// ✅ DO: Use repository snapshot pattern with comprehensive tracking
interface RepoSnapshot {
  id: string; traceId: string; owner: string; repo: string; branch: string;
  tree: TreeNode[]; files: Map<string, FileContent>; fetchedAt: Date;
  checksum: string; size: number; fileCount: number; telemetry: SnapshotTelemetry;
}

interface SnapshotTelemetry {
  fetchDuration: number; parseDuration: number; validationErrors: string[]; cacheHit: boolean;
}

async function loadRepoWithIntelligence(url: string, options?: LoadRepoOptions): Promise<RepoSnapshot> {
  const traceId = generateTraceId();
  const startTime = performance.now();
  trackEvent('repo_load_started', { url, traceId });

  try {
    const parsed = parseGitHubUrl(url);
    const treeStart = performance.now();
    const tree = await withRetry(() => github.repos.getContent({ owner: parsed.owner, repo: parsed.repo, path: '', ref: parsed.branch }), options?.retries ?? 3);
    const snapshotStart = performance.now();
    const files = await loadAllFiles(parsed, tree);
    const checksum = await computeChecksum(tree);

    const snapshot: RepoSnapshot = {
      id: createSnapshotId(parsed.owner, parsed.repo, parsed.branch, checksum),
      traceId, owner: parsed.owner, repo: parsed.repo, branch: parsed.branch,
      tree: flattenTree(tree), files, fetchedAt: new Date(), checksum,
      size: computeTotalSize(files), fileCount: files.size,
      telemetry: { fetchDuration: performance.now() - treeStart, parseDuration: performance.now() - snapshotStart, validationErrors: validateSnapshot(snapshot), cacheHit: false }
    };

    trackEvent('repo_load_completed', { traceId, fileCount: snapshot.fileCount, size: snapshot.size, duration: performance.now() - startTime });
    return snapshot;
  } catch (error) {
    trackEvent('repo_load_failed', { url, error: (error as Error).message, traceId });
    throw error;
  }
}

// ✅ DO: Implement diff preview with change intelligence
interface DiffIntelligence {
  additions: number; deletions: number; filesChanged: number;
  riskScore: number; detectedPatterns: PatternMatch[]; breakingChanges: BreakingChange[];
}

async function generateDiffIntelligence(original: RepoSnapshot, modified: Map<string, FileContent>): Promise<DiffIntelligence> {
  const traceId = generateTraceId();
  const startTime = performance.now();
  let additions = 0, deletions = 0;
  const detectedPatterns: PatternMatch[] = [];
  const breakingChanges: BreakingChange[] = [];

  for (const [path, content] of modified) {
    const originalContent = original.files.get(path);
    if (originalContent) {
      const diff = computeDiff(originalContent.body, content.body);
      additions += diff.additions;
      deletions += diff.deletions;
      detectedPatterns.push(...detectPatterns(path, diff));
      breakingChanges.push(...detectBreakingChanges(path, diff));
    } else {
      additions += countLines(content.body);
    }
    if (isDangerousPath(path)) trackEvent('dangerous_path_modified', { path, traceId });
  }

  const riskScore = computeRiskScore({ additions, deletions, breakingChanges, detectedPatterns });
  trackEvent('diff_intelligence_computed', { traceId, additions, deletions, riskScore, duration: performance.now() - startTime });
  return { additions, deletions, filesChanged: modified.size, riskScore, detectedPatterns, breakingChanges };
}
```

### Draft PR Pattern with Review Intelligence

```typescript
// ✅ DO: Always use draft PR with comprehensive tracking
interface DraftPRContext {
  owner: string; repo: string; branch: string; title: string; body: string;
  changes: FileChange[]; diffIntelligence: DiffIntelligence; runtimeContext: RuntimeContext;
}

interface PRCreationResult {
  number: number; url: string; traceId: string; checksRequired: string[]; estimatedReviewTime: number;
}

async function publishDraftPRWithIntelligence(ctx: DraftPRContext): Promise<PRCreationResult> {
  const traceId = generateTraceId();
  const startTime = performance.now();
  trackEvent('pr_creation_started', { owner: ctx.owner, repo: ctx.repo, branch: ctx.branch, traceId, riskScore: ctx.diffIntelligence.riskScore });

  try {
    const branchResult = await github.git.createRef({
      owner: ctx.owner, repo: ctx.repo, ref: `refs/heads/${ctx.branch}`,
      sha: await getMainSHA(ctx.owner, ctx.repo),
    });
    trackEvent('branch_created', { branch: ctx.branch, sha: branchResult.object.sha, traceId });

    for (const change of ctx.changes) await createCommit(ctx.owner, ctx.repo, ctx.branch, change, traceId);

    const pr = await github.pulls.create({
      owner: ctx.owner, repo: ctx.repo, title: ctx.title, body: generatePRBody(ctx),
      head: ctx.branch, base: 'main', draft: true,
    });

    trackEvent('pr_created', { number: pr.number, url: pr.html_url, traceId, duration: performance.now() - startTime });
    return { number: pr.number, url: pr.html_url, traceId, checksRequired: determineRequiredChecks(ctx.diffIntelligence), estimatedReviewTime: estimateReviewTime(ctx.diffIntelligence) };
  } catch (error) {
    trackEvent('pr_creation_failed', { error: (error as Error).message, traceId });
    throw error;
  }
}

// ✅ DO: Implement PR review guardrails with intelligence
interface ReviewGateIntelligence {
  checksPass: boolean; approvals: Approval[]; conflicts: boolean;
  CIStatus: CIStatus; riskScore: number; patterns: PatternMatch[]; recommendations: string[];
}

function evaluateReviewGate(pr: PR, checks: CICheck[], diffIntel: DiffIntelligence): ReviewGateIntelligence {
  const approvals = getApprovals(pr);
  const recommendations: string[] = [];

  if (diffIntel.riskScore > 0.7) recommendations.push('High risk changes detected - manual review required');
  if (diffIntel.breakingChanges.length > 0) recommendations.push('Breaking changes present - update notes required');
  if (approvals.length < 1) recommendations.push('At least one approval needed');

  const canMerge = checks.every(c => c.status === 'success') && approvals.length >= 1 && !pr.has_conflicts;

  return { checksPass: canMerge, approvals, conflicts: pr.has_conflicts, CIStatus: aggregateCIStatus(checks), riskScore: diffIntel.riskScore, patterns: diffIntel.detectedPatterns, recommendations };
}
```

---

## 🤖 AI Integration Patterns with System Grounding

### Gemini Service Pattern with Comprehensive Telemetry

```typescript
// ✅ DO: Use structured prompts with typed schemas
interface AIGenerationRequest {
  mission: string;
  context: { repoSnapshot: RepoSnapshot; files: FileContent[]; language?: string; constraints?: GenerationConstraints };
  constraints: { maxTokens: number; temperature: number };
  telemetry: RequestTelemetry;
}

interface AIGenerationResult {
  content: GeneratedContent; confidence: number; groundingSources: GroundingSource[];
  tokensUsed: TokenUsage; traceId: string; metadata: GenerationMetadata;
}

async function generateCodeWithGrounding(req: AIGenerationRequest): Promise<AIGenerationResult> {
  const traceId = req.telemetry.traceId || generateTraceId();
  const startTime = performance.now();
  trackEvent('ai_generation_started', { mission: req.mission, language: req.context.language, traceId });

  try {
    const groundedPrompt = buildGroundedPrompt(req);
    const result = await gemini.generateContent({
      contents: [{ role: 'user', parts: [{ text: groundedPrompt.prompt }] }],
      generationConfig: { maxOutputTokens: req.constraints.maxTokens, temperature: req.constraints.temperature, responseMimeType: 'application/json', responseSchema: GeneratedContentSchema },
    });

    const parsed = parseGeneratedContent(result);
    const groundingSources = await verifySources(parsed, req.context);
    const confidence = calculateConfidence(parsed, groundingSources);

    trackEvent('ai_generation_completed', { traceId, confidence, tokensUsed: result.usageMetadata?.totalTokenCount, duration: performance.now() - startTime, grounded: groundingSources.length > 0 });

    return { content: parsed, confidence, groundingSources, tokensUsed: result.usageMetadata ?? { promptTokens: 0, completionTokens: 0 }, traceId, metadata: { model: 'gemini-2.5-pro', promptVersion: groundedPrompt.version, validationLevel: groundingSources.length > 0 ? 'strong' : 'weak' } };
  } catch (error) {
    trackEvent('ai_generation_failed', { error: (error as Error).message, traceId });
    throw error;
  }
}

// ✅ DO: Implement retry with exponential backoff and jitter
async function withRetry<T>(fn: () => Promise<T>, options: RetryOptions = { maxRetries: 3, baseDelay: 1000 }): Promise<T> {
  let lastError: Error;
  for (let i = 0; i < options.maxRetries; i++) {
    try { return await fn(); }
    catch (error) {
      lastError = error as Error;
      if (!isRetryableError(error)) throw error;
      const delay = options.baseDelay * Math.pow(2, i) + Math.random() * 1000;
      trackEvent('ai_retry', { attempt: i + 1, maxRetries: options.maxRetries, delay, error: lastError.message });
      await sleep(delay);
    }
  }
  throw lastError!;
}

// ✅ DO: Use streaming for long generations with progress tracking
async function* streamGenerateWithProgress(prompt: string, onProgress?: (progress: GenerationProgress) => void): AsyncGenerator<string, GenerationStats, unknown> {
  const traceId = generateTraceId();
  const startTime = performance.now();
  let totalTokens = 0;

  const stream = await gemini.generateContentStream({ contents: [{ role: 'user', parts: [{ text: prompt }] }] });
  for await (const chunk of stream) {
    totalTokens += chunk.tokens ?? 0;
    onProgress?.({ tokensGenerated: totalTokens, elapsedMs: performance.now() - startTime, traceId });
    yield chunk.text;
  }

  return { totalTokens, duration: performance.now() - startTime, traceId };
}
```

### System Grounding Pattern

```typescript
// ✅ DO: Ground AI outputs with verifiable facts
interface GroundedOutput<T> {
  content: T; groundingSources: GroundingSource[]; confidenceScore: number; validationResult: ValidationResult;
}

interface GroundingSource {
  type: 'file' | 'url' | 'fact' | 'rule'; reference: string; verified: boolean;
  verificationTimestamp: number; evidence?: string;
}

async function groundOutput<T>(content: T, context: GroundingContext): Promise<GroundedOutput<T>> {
  const traceId = generateTraceId();
  const sources = await verifySources(content, context);
  const verifiedSources: GroundingSource[] = [];

  for (const source of sources) {
    const verified = await verifySource(source);
    verifiedSources.push({ ...source, verified, verificationTimestamp: Date.now() });
    trackEvent('source_verified', { type: source.type, reference: source.reference, verified, traceId });
  }

  const verifiedCount = verifiedSources.filter(s => s.verified).length;
  const confidence = verifiedCount / verifiedSources.length;

  return { content, groundingSources: verifiedSources, confidenceScore: confidence, validationResult: { valid: confidence >= 0.7, score: confidence, sourcesVerified: verifiedCount, totalSources: verifiedSources.length } };
}

// ✅ DO: Implement Constitutional AI principles for self-correction
const AI_PRINCIPLES = ['Be accurate and verifiable', 'Prefer explicit over implicit', 'Prefer safe over sorry', 'Prefer reversible over irreversible', 'Prefer minimal over maximal'];

async function selfCorrectWithConstitutionalAI(output: string, context: GroundingContext, principles = AI_PRINCIPLES): Promise<ConstitutionalAICorrection> {
  const traceId = generateTraceId();
  const critiquePrompt = buildCritiquePrompt(output, context, principles);
  const critique = await gemini.generateContent({ contents: [{ role: 'user', parts: [{ text: critiquePrompt }] }], generationConfig: { temperature: 0.3 } });
  trackEvent('ai_critique_completed', { traceId, principles: principles.length });

  const revisionPrompt = buildRevisionPrompt(output, critique, principles);
  const revision = await gemini.generateContent({ contents: [{ role: 'user', parts: [{ text: revisionPrompt }] }], generationConfig: { temperature: 0.2 } });
  trackEvent('ai_revision_completed', { traceId });

  return { original: output, critique, principles, revision, improvementScore: calculateImprovementScore(output, revision) };
}

// ✅ DO: Use structured output validation
interface ValidationResult {
  valid: boolean; errors: ValidationError[]; suggestions: string[]; score: number;
}

function validateAIResponse<T>(response: unknown, schema: ZodSchema<T>, context: ValidationContext): ValidationResult {
  const result = schema.safeParse(response);
  if (!result.success) {
    const errors = result.error.issues.map(i => ({ path: i.path.join('.'), message: i.message, code: i.code }));
    trackEvent('ai_validation_failed', { errors: errors.length, schema: schema.name, traceId: context.traceId });
    return { valid: false, errors, suggestions: [], score: 0 };
  }
  const suggestions = checkCodeQuality(result.data, context);
  trackEvent('ai_validation_passed', { suggestions: suggestions.length, score: 1 - (suggestions.length * 0.1), traceId: context.traceId });
  return { valid: suggestions.length === 0, errors: [], suggestions, score: Math.max(0, 1 - (suggestions.length * 0.1)) };
}
```

---

## 🛡️ Runtime Guard Patterns with Intelligence

### Functional Guards with Defense in Depth

```typescript
// ✅ DO: Implement defense in depth with telemetry
interface GuardChain { preFlight: Guard[]; main: Guard[]; postFlight: Guard[]; }

interface GuardResult {
  pass: boolean; guardName: string; reason?: string; remediation?: string;
  traceId: string; duration: number; riskReduction?: number;
}

const guardChain: GuardChain = {
  preFlight: [
    { name: 'validateRepoSnapshotNotEmpty', check: async (ctx) => {
      const start = performance.now();
      const pass = ctx.snapshot.fileCount > 0;
      return { pass, guardName: 'validateRepoSnapshotNotEmpty', duration: performance.now() - start, reason: pass ? undefined : 'Snapshot is empty', riskReduction: 0.1 };
    }},
    { name: 'validateNoForbiddenPaths', check: async (ctx) => {
      const start = performance.now();
      const forbidden = ctx.changes.filter(c => isForbiddenPath(c.path));
      const pass = forbidden.length === 0;
      return { pass, guardName: 'validateNoForbiddenPaths', duration: performance.now() - start, reason: pass ? undefined : `Forbidden paths: ${forbidden.map(f => f.path).join(', ')}`, remediation: 'Remove or rename forbidden paths', riskReduction: 0.3 };
    }},
  ],
  main: [
    { name: 'validateDiffSafety', check: async (ctx) => {
      const start = performance.now();
      const diffIntel = await generateDiffIntelligence(ctx.snapshot, ctx.changes);
      const pass = diffIntel.riskScore < 0.8;
      return { pass, guardName: 'validateDiffSafety', duration: performance.now() - start, reason: pass ? undefined : `High risk score: ${diffIntel.riskScore}`, riskReduction: 0.4 };
    }},
    { name: 'validateNoSecretsInDiff', check: async (ctx) => {
      const start = performance.now();
      const secrets = detectSecrets(ctx.changes);
      const pass = secrets.length === 0;
      return { pass, guardName: 'validateNoSecretsInDiff', duration: performance.now() - start, reason: pass ? undefined : `Secrets detected: ${secrets.length}`, remediation: 'Remove secrets before committing', riskReduction: 0.5 };
    }},
  ],
  postFlight: [
    { name: 'validatePRTitleFormat', check: async (ctx) => {
      const start = performance.now();
      const valid = isValidPRTitle(ctx.prTitle);
      return { pass: valid, guardName: 'validatePRTitleFormat', duration: performance.now() - start, reason: valid ? undefined : 'Invalid PR title format', riskReduction: 0.01 };
    }},
  ]
};

async function runGuardsWithIntelligence(context: GuardContext, chain: GuardChain): Promise<{ pass: boolean; results: GuardResult[]; totalRiskReduction: number }> {
  const traceId = generateTraceId();
  const results: GuardResult[] = [];
  let totalRiskReduction = 0;

  trackEvent('guard_chain_started', { guardCount: chain.preFlight.length + chain.main.length + chain.postFlight.length, traceId });

  for (const guard of [...chain.preFlight, ...chain.main, ...chain.postFlight]) {
    const result = await guard.check(context);
    result.traceId = traceId;
    results.push(result);
    totalRiskReduction += result.riskReduction ?? 0;
    trackEvent('guard_executed', { guardName: result.guardName, pass: result.pass, duration: result.duration, traceId });

    if (!result.pass) {
      trackEvent('guard_failed', { guardName: result.guardName, reason: result.reason, traceId });
      return { pass: false, results, totalRiskReduction };
    }
  }

  trackEvent('guard_chain_passed', { totalRiskReduction, traceId });
  return { pass: true, results, totalRiskReduction };
}

// ✅ DO: Use circuit breaker for external calls
class CircuitBreaker {
  private failures = 0; private lastFailure = 0; private state: 'closed' | 'open' | 'half-open' = 'closed';

  constructor(private threshold = 5, private timeout = 30000, private name = 'default') {}

  async call<T>(fn: () => Promise<T>): Promise<T> {
    const traceId = generateTraceId();
    if (this.state === 'open') {
      if (Date.now() - this.lastFailure > this.timeout) { trackEvent('circuit_breaker_half_open', { name: this.name, traceId }); this.state = 'half-open'; }
      else { trackEvent('circuit_breaker_rejected', { name: this.name, reason: 'open', traceId }); throw new Error(`Circuit breaker open for ${this.name}`); }
    }
    try {
      const result = await fn();
      this.failures = 0; this.state = 'closed';
      trackEvent('circuit_breaker_success', { name: this.name, traceId });
      return result;
    } catch (error) {
      this.failures++; this.lastFailure = Date.now();
      trackEvent('circuit_breaker_failure', { name: this.name, failures: this.failures, threshold: this.threshold, error: (error as Error).message, traceId });
      if (this.failures >= this.threshold) { this.state = 'open'; trackEvent('circuit_breaker_opened', { name: this.name, traceId }); }
      throw error;
    }
  }
}
```

### Telemetry Pattern with Structured Events

```typescript
// ✅ DO: Implement structured telemetry with trace context
interface TelemetryEvent {
  name: string; properties: Record<string, unknown>; timestamp: number;
  traceId: string; spanId?: string; parentTraceId?: string;
}

interface OperationTrace {
  operation: string; startTime: number; endTime?: number; duration?: number;
  success: boolean; error?: string; children: OperationTrace[];
}

class TelemetryService {
  private traces = new Map<string, OperationTrace>();
  private eventQueue: TelemetryEvent[] = [];

  constructor(private config: TelemetryConfig) {}

  trackEvent(event: TelemetryEvent): void {
    this.eventQueue.push(event);
    if (this.config.logLocally) console.log(`[TELEMETRY] ${event.name}`, { ...event.properties, traceId: event.traceId, timestamp: new Date(event.timestamp).toISOString() });
    if (this.eventQueue.length >= this.config.batchSize) this.flush();
  }

  startTrace(operation: string, traceId?: string): string {
    const id = traceId ?? generateTraceId();
    this.traces.set(id, { operation, startTime: performance.now(), success: true, children: [] });
    this.trackEvent({ name: 'trace_started', properties: { operation }, timestamp: Date.now(), traceId: id });
    return id;
  }

  endTrace(traceId: string, success = true, error?: string): void {
    const trace = this.traces.get(traceId);
    if (!trace) return;
    trace.endTime = performance.now(); trace.duration = trace.endTime - trace.startTime; trace.success = success; trace.error = error;
    this.trackEvent({ name: 'trace_completed', properties: { operation: trace.operation, duration: trace.duration, success, children: trace.children.length }, timestamp: Date.now(), traceId });
    this.traces.delete(traceId);
  }

  async flush(): Promise<void> {
    if (this.eventQueue.length === 0) return;
    const events = [...this.eventQueue]; this.eventQueue = [];
    try { await this.sendToBackend(events); trackEvent({ name: 'telemetry_flushed', properties: { eventCount: events.length }, timestamp: Date.now(), traceId: generateTraceId() }); }
    catch (error) { this.eventQueue.unshift(...events); console.error('Telemetry flush failed:', error); }
  }
}

// ✅ DO: Use OpenTelemetry for distributed tracing
import { trace, SpanStatusCode, SpanKind } from '@opentelemetry/api';

const tracer = trace.getTracer('sovereign-studio', '1.0.0');

function tracedOperation<T>(name: string, fn: () => Promise<T>, options: TraceOptions = {}): Promise<T> {
  return tracer.startActiveSpan(name, { kind: SpanKind.INTERNAL }, async (span) => {
    const startTime = performance.now();
    const traceId = span.spanContext().traceId;
    span.setAttributes({ 'operation.name': name, 'trace.id': traceId, ...options.attributes });
    try {
      const result = await fn();
      span.setStatus({ code: SpanStatusCode.OK });
      span.setAttribute('operation.duration_ms', performance.now() - startTime);
      trackEvent('traced_operation_success', { name, duration: performance.now() - startTime, traceId });
      return result;
    } catch (error) {
      span.setStatus({ code: SpanStatusCode.ERROR, message: (error as Error).message });
      span.recordException(error as Error);
      trackEvent('traced_operation_error', { name, error: (error as Error).message, traceId });
      throw error;
    } finally { span.end(); }
  });
}
```

---

## 📐 Best Practices for Software Architects

### 1. Code Organization with Runtime Awareness

```
✅ Feature-based structure over type-based
✅ Colocation of related code (components, hooks, utils together)
✅ Shared code in /shared, not duplicated
✅ Clear module boundaries with barrel exports
✅ Runtime intelligence co-located with business logic
```

### 2. Error Handling with Recovery Intelligence

```typescript
// ✅ DO: Use error boundaries with recovery telemetry
class ErrorBoundary extends React.Component<Props, State> {
  static getDerivedStateFromError(error: Error) {
    const traceId = generateTraceId();
    trackEvent('error_boundary_triggered', { error: error.message, stack: error.stack, traceId });
    return { hasError: true, error, traceId };
  }
}

// ✅ DO: Use Result types for fallible operations
type Result<T, E = Error> = { ok: true; value: T; traceId: string } | { ok: false; error: E; traceId: string; retryable: boolean };

function tryCatch<T>(fn: () => T, traceId = generateTraceId()): Result<T, Error> {
  try { return { ok: true, value: fn(), traceId }; }
  catch (error) { trackEvent('operation_failed', { error: (error as Error).message, traceId }); return { ok: false, error: error as Error, traceId, retryable: isRetryableError(error) }; }
}
```

### 3. Security with Runtime Monitoring

```typescript
// ✅ DO: Never log secrets
// ✅ DO: Use environment variables for secrets
const apiKey = import.meta.env.VITE_API_KEY;

// ✅ DO: Monitor for security anomalies
function detectSecurityAnomalies(operation: SecurityOperation): void {
  const { type, userId, resource, action } = operation;
  const key = `${userId}:${resource}`;
  const count = securityMonitor.increment(key);
  if (count > THRESHOLD) {
    trackEvent('security_anomaly_detected', { type, userId, resource, action, count, severity: 'high' });
    alertSecurityTeam(operation);
  }
}
```

### 4. Performance with Runtime Intelligence

```typescript
// ✅ DO: Use React.memo with runtime performance tracking
const ExpensiveList = React.memo<ListProps>(
  ({ items, onItemClick }) => {
    const renderStart = performance.now();
    const result = items.map(item => <ListItem key={item.id} item={item} onClick={() => onItemClick(item)} />);
    trackEvent('expensive_list_render', { itemCount: items.length, duration: performance.now() - renderStart });
    return result;
  },
  (prev, next) => {
    const shouldRerender = prev.items.length !== next.items.length;
    if (shouldRerender) trackEvent('list_rerender_triggered', { prevCount: prev.items.length, nextCount: next.items.length });
    return !shouldRerender;
  }
);

// ✅ DO: Virtualize long lists with lazy loading
function VirtualFileList({ files, onLoadMore }: { files: File[]; onLoadMore: () => void }) {
  return (
    <FixedSizeList height={400} itemCount={files.length} itemSize={32} itemData={files}
      onItemsRendered={({ visibleRowStopIndex }) => { if (visibleRowStopIndex >= files.length - 5) { trackEvent('virtual_list_near_end', { triggerLoadMore: true }); onLoadMore(); } }}>
      {({ index, style }) => <div style={style}>{files[index].name}</div>}
    </FixedSizeList>
  );
}
```

### 5. Testing with Runtime Coverage

```typescript
// ✅ DO: Test behavior, not implementation
test('submits form with user input', async () => {
  const traceId = 'test-trace-id';
  render(<RepoForm traceId={traceId} />);
  await userEvent.type(screen.getByLabelText('Repository URL'), 'https://github.com/owner/repo');
  await userEvent.click(screen.getByRole('button', { name: 'Load' }));
  expect(screen.getByText('Loading...')).toBeInTheDocument();
  expect(mockTrackEvent).toHaveBeenCalledWith(expect.objectContaining({ name: 'repo_load_started', properties: expect.objectContaining({ traceId }) }));
});

// ✅ DO: Test runtime intelligence integration
test('runtime guard tracks all operations', async () => {
  const mockTrackEvent = vi.fn();
  vi.stubGlobal('trackEvent', mockTrackEvent);
  await runGuardsWithIntelligence(testContext, guardChain);
  expect(mockTrackEvent).toHaveBeenCalledWith(expect.objectContaining({ name: 'guard_chain_started' }));
  expect(mockTrackEvent).toHaveBeenCalledWith(expect.objectContaining({ name: 'guard_executed' }));
  expect(mockTrackEvent).toHaveBeenCalledWith(expect.objectContaining({ name: 'guard_chain_passed' }));
});
```

---

## 🔧 Development Workflow

### Feature Flags with Rollout Intelligence

```typescript
const FEATURES = {
  AI_CODESIGN: import.meta.env.VITE_FEATURE_AI_CODESIGN === 'true',
  NEW_EDITOR: import.meta.env.VITE_FEATURE_NEW_EDITOR === 'true',
  RUNTIME_INTELLIGENCE: import.meta.env.VITE_FEATURE_RUNTIME_INTELLIGENCE === 'true',
};

interface FeatureFlagConfig { name: string; enabled: boolean; rolloutPercentage: number; userGroups: string[]; }

function isFeatureEnabled(flag: FeatureFlagConfig, userId: string): boolean {
  if (!flag.enabled) return false;
  const bucket = hashUserId(userId) % 100;
  const enabled = bucket < flag.rolloutPercentage;
  trackEvent('feature_flag_evaluated', { flag: flag.name, userId, enabled, bucket, rolloutPercentage: flag.rolloutPercentage });
  return enabled;
}
```

### CI/CD Pipeline with Quality Gates

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4 with: node-version: '22'
      - run: npm ci
      - run: npm run type-check
      - run: npm run audit:sovereign
      - run: npm run test:unit
      - run: npm run test:integration
      - name: Runtime Intelligence Validation
        run: node scripts/validate-runtime-intelligence.js
  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm run build:web
      - uses: actions/upload-artifact@v4 with: name: dist path: dist/
```

### Commit Convention

```
feat: add new feature (minor)
fix: bug fix (patch)
refactor: code refactoring
test: add/update tests
docs: documentation changes
chore: maintenance tasks
perf: performance improvements
security: security fixes
```

---

## 📚 Quick Reference Commands

```bash
# Development
npm run dev              # Start dev server (http://localhost:3000)
npm run build:web        # Production build

# Quality Gates (sovereign.guard.json)
npm run audit:sovereign  # Custom static audit with NoMock validation
npm run type-check       # TypeScript check
npm run test:unit        # Unit tests only (fast)
npm run test:integration # Integration tests
npm run test:run         # All tests

# Runtime Intelligence
npm run validate:runtime # Validate runtime telemetry integration
npm run validate:guards  # Validate guard chain coverage

# Mobile
npx cap copy             # Copy web to Android
npx cap sync android     # Sync plugins
npx cap open android     # Open in Android Studio
npm run build:android    # Build APK

# Analysis
npm run lint             # ESLint
npm run lint:fix         # Auto-fix ESLint issues
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
| Telemetry | PostHog, OpenTelemetry |
