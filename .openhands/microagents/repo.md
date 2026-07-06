# Sovereign Studio V3 — Repository Agent Guide

> **⚠️ DISCLAIMER: Pattern Guide — Not a Technology Guarantee**
>
> This file is the **authoritative agent knowledge base** for Sovereign Studio V3. The patterns described represent architectural best practices. Before applying any pattern:
> - Check `package.json` for actual dependencies
> - Verify runtime imports in the actual codebase
> - Check existing architecture patterns in `src/`
> - Consult existing tests in `src/**/*.test.ts`
>
> **Do NOT assume listed technologies are installed or used.** Always cross-reference with actual project state.

---

## 📖 Project Description

**Sovereign Studio V3** is a hybrid mobile/desktop application that serves as an autonomous repository architect. It loads real GitHub repository snapshots, converts them into visible, guarded implementation packages, and publishes them as draft pull requests.

**Core principle:** Autonomous-feeling workflows must still pass through visible preview, functional guards, and deliberate user action before any GitHub writes occur.

**Key value proposition:**
- Loads real GitHub repository trees (not fake snapshots)
- Builds implementation packages from concrete missions
- Uses the "Sovereign brain contract" before accepting AI-generated output
- Runs functional guards against unsafe patterns
- Publishes only through Draft PRs (never directly to main)
- Watches GitHub workflow status and provides repair guidance

---

## 🎯 Critical Repository-Specific Rules

### Prime Directive
```
Build a runtime that produces truth.
Do not build a UI that invents truth.
The UI may only display verified runtime state.
```

### Causal Runtime Chain
Every workflow must follow this chain:
1. Action starts.
2. Action produces a result.
3. Result creates or updates state.
4. State allows, blocks, or routes the next action.
5. The next action must be logically derivable from that state.

**Do NOT jump because a button was clicked, a text string is visible, or the UI looks ready.**

### Approved Truth Sources
Use real runtime sources only:
- `sequentialRuntime`
- `repoSnapshotStatus`
- `repoFiles`
- `scanRegistry`
- `workflowReport`
- `lastPackage`
- `latestGeneratedReview`
- `diffReport`
- `telemetry`
- `solutionPatternStore`
- `remoteMemoryIntake`
- `automationStatus`

**Do NOT use:** DOM text, page text scraping, static percentages, or visual UI state as the source of truth.

### Progress Rule
- No hard percentage progress.
- No fixed maximum step count.
- Progress must be a step plan derived from the real runtime flow.

Correct pattern:
```
currentStep / totalRuntimeSteps - current runtime action
```

### Placeholder Mission Rule
Default or vague text must never enter `package-build` as-is.

Examples that must be normalized or blocked before package build:
- `README + Update History`
- `Mach weiter`
- `Fehler`
- `Ideen`
- `Plan`
- `Workflow Fehleranalyse + Runtime Check + Test Plan`

The tool must derive a concrete mission from repo analysis or stop in a safe yellow state with a clear next action.

### Draft PR Rule
Draft PRs require real execution patches.

Actionable targets include:
- `src/`
- `tests/`
- `android/`
- `scripts/`
- `.github/workflows/`
- real config files
- `README.md`
- real `docs/`

Plan-only output must not count as actionable work.
A PR containing only `docs/SOVEREIGN_PLAN.md` and generated workflow preview artifacts is NOT acceptable.

### Live-Path Integrity
- No mocks, stubs, facades, fake snapshots, fake success states, or hardcoded green states in the live path.
- Test fixtures are allowed only inside tests and must stay clearly separated from production runtime code.

### Error Handling Rule
Failures must route into a repair flow, not into blind retry loops.

A failed action must produce:
1. recorded error result
2. classified state
3. safe next action
4. repair mission or user-visible stop reason

### Required Green Gate
Before finishing any code change, run or explicitly report why you could not run:
```bash
npm run audit:sovereign
npm run type-check
npm run test:run
npm run build
```

Do NOT stop after fixing only the latest touched file if older failures block the product path.

### Protected Product Shape
Protect these product rules:
- left side: GitHub file tree and idea/order input
- center: chat, matrix-style file editor and live status
- right side: history log and plain-language analysis
- free-first routing before optional user keys
- visible fix loop on errors
- user confirmation before writing unless autonomous mode is active

---

## 🔄 Runtime Truth Path

The runtime path is:
1. Real GitHub repository tree is loaded.
2. Repo paths are converted into readiness signals.
3. A mission is classified against the loaded snapshot.
4. Provider output is normalized into the Sovereign brain contract.
5. Generated files are reviewed by functional guards.
6. Diff context is loaded when available.
7. Draft PR publishing creates a branch, tree, commit and PR.
8. Workflow watch reads GitHub Actions status for the produced commit.
9. UI/Coach state is derived from runtime state, not DOM scraping.

---

## 🧠 Brain Gate

Every accepted package must include these layers:
- perception
- analysis
- plan
- execution
- learning

A response without usable execution patches is NOT a release artifact. A response that touches forbidden paths, duplicates generated output or bypasses file review must be rejected before GitHub publishing.

---

## 🚦 Functional Guards

Functional guards prevent the app from generating or publishing unsafe output.

They currently block:
- empty repo snapshots
- snapshots containing only folders
- duplicate generated file paths
- empty generated file content
- unsafe output paths such as `.env`, `.git/`, `node_modules/`, `dist/`, `build/`
- incomplete docs packages

Best practices:
- Add new tool modules behind guards first, then expose them in UI.
- Never bypass `assertGeneratedPackageReady` in publishing paths.
- Keep runtime checks small and deterministic.

---

## 📁 Key Directory Structure

```
src/
├── App.tsx                          # Main app shell
├── features/
│   ├── github/                      # GitHub API integration
│   │   ├── hooks/useGithubRepo.ts   # Repo tree loading
│   │   ├── githubPackagePublisher.ts # Draft PR creation
│   │   └── utils.ts                 # URL parsing
│   ├── product/
│   │   ├── runtime/
│   │   │   ├── sovereignPackageFromRepoFiles.ts  # Package builder
│   │   │   ├── sovereignFunctionalGuards.ts     # Safety guards
│   │   │   ├── repoLaunchReadiness.ts            # Readiness scoring
│   │   │   ├── workflowWatch.ts                  # CI status watching
│   │   │   ├── sovereignTelemetry.ts            # Event tracking
│   │   │   └── sovereignSessionMemory.ts         # State persistence
│   │   ├── brain/
│   │   │   └── sovereignBrainContract.ts         # Brain contract
│   │   └── components/
│   │       └── RepoReadinessPanel.tsx            # Readiness UI
│   ├── ai/
│   │   ├── geminiService.ts                      # Gemini API
│   │   └── providerManager.ts                   # LLM routing
│   └── canvas/                                  # Monaco editor
├── store/                                       # Zustand state
├── runtime/                                     # Runtime intelligence
└── predictive/                                 # Predictive guards
```

---

## 🛠️ Development Commands

```bash
# Setup
pnpm install

# Development
pnpm run dev              # Start dev server (http://localhost:5000)
pnpm run build:web        # Production build

# Quality Gates (required before PR)
pnpm run audit:sovereign  # Custom static audit with NoMock validation
pnpm run type-check       # TypeScript check
pnpm run test:run         # All tests

# Testing
pnpm run test:unit        # Unit tests only (fast)
pnpm run test:integration # Integration tests
pnpm run test:e2e         # E2E tests

# Mobile
pnpm run build            # Build web + sync to Android
npx cap copy             # Copy web to Android
npx cap sync android     # Sync plugins
npx cap open android     # Open in Android Studio

# Linting
pnpm run lint             # ESLint
pnpm run lint:fix         # Auto-fix ESLint issues
```

---

## 📦 Tech Stack

| Component | Technology |
|-----------|------------|
| Frontend | React 19, TypeScript, Vite |
| Mobile Bridge | Capacitor 6 (Android/iOS) |
| State Management | Zustand (primary) |
| AI Integration | Google Gemini SDK |
| Editor | Monaco Editor |
| Testing | Vitest, React Testing Library |
| Publishing | Draft PR via GitHub REST API |

---

## 🎨 Code Patterns

### Component Pattern
```typescript
// ✅ DO: Use composition, telemetry, and runtime IDs
const Card = ({ children, header, footer, runtimeContext }: CardProps) => {
  useRuntimeTrack('card-render', { component: 'Card' });
  return (
    <div className="card" data-runtime-id={runtimeContext.componentId}>
      {header && <div className="card-header">{header}</div>}
      <div className="card-body">{children}</div>
      {footer && <div className="card-footer">{footer}</div>}
    </div>
  );
};

// ❌ DON'T: Default exports
export default Card; // Bad
export { Card }; // Good
```

### State Machine Pattern
```typescript
// ✅ DO: Discriminated unions for state
type AsyncState<T> =
  | { status: 'idle' }
  | { status: 'loading'; progress?: number }
  | { status: 'success'; data: T; timestamp: number }
  | { status: 'error'; error: Error; retryable: boolean };

// ✅ DO: Exhaustive switch
function handleAction(action: Action): State {
  switch (action.type) {
    case 'SET_USER': return { ...state, user: action.user };
    case 'CLEAR_USER': return { ...state, user: null };
    default: const _exhaustive: never = action; throw new Error(`Unhandled: ${_exhaustive}`);
  }
}
```

### Result Type Pattern
```typescript
type Result<T, E = Error> = 
  | { ok: true; value: T; traceId: string }
  | { ok: false; error: E; traceId: string; retryable: boolean };

function tryCatch<T>(fn: () => T, traceId = generateTraceId()): Result<T> {
  try { return { ok: true, value: fn(), traceId }; }
  catch (error) { 
    trackEvent('operation_failed', { error: (error as Error).message, traceId });
    return { ok: false, error: error as Error, traceId, retryable: isRetryableError(error) };
  }
}
```

---

## 🔐 Security Rules

1. **Never log secrets** - PAT tokens, API keys, passwords
2. **Use environment variables** for secrets: `import.meta.env.VITE_API_KEY`
3. **PAT handling**: Store only in memory, never persist to session
4. **Input validation**: All GitHub URLs and user input must be validated

---

## 📊 Testing Expectations

Every structural layer should have tests:

| Layer | Test Location |
|-------|---------------|
| URL parser | `src/features/github/utils.test.ts` |
| Readiness runtime | `src/features/product/runtime/repoLaunchReadiness.test.ts` |
| Functional guards | `src/features/product/runtime/sovereignFunctionalGuards.test.ts` |
| Draft PR publisher | `src/features/github/githubPackagePublisher.test.ts` |
| Package builder | `src/features/product/runtime/sovereignPackageFromRepoFiles.test.ts` |
| Session memory | `src/features/product/runtime/sovereignSessionMemory.test.ts` |
| Workflow watch | `src/features/product/runtime/workflowWatch.test.ts` |

Minimum expected coverage for new logic:
- success case
- failure case
- invalid input case
- state transition case
- guard behavior case

---

## 🚫 Anti-Patterns

Avoid these:
- sample files pretending to be a real repository snapshot
- console-only buttons
- provider output pushed directly to GitHub
- docs-only requests that generate only preview artifacts
- hidden auto-merge behavior
- hardcoded secrets or direct secret logging
- broad rewrites of large hooks when a small adapter module is enough
- synthetic purity scores presented as true content scans
- pushing generated files without a reviewable file list
- Full Auto bypassing guard, review or workflow-watch layers
- claiming runtime coverage from docs alone without test files

---

## 📚 Key Documentation Files

| File | Purpose |
|------|---------|
| `docs/SOVEREIGN_READER.md` | Practical map of tools, modules, and best practices |
| `docs/SOVEREIGN_RUNTIME.md` | Runtime truth path, provider guardrails, workflow gates |
| `docs/SOVEREIGN_GUARDRAILS.md` | Functional guard implementation details |
| `AGENTS.md` | Agent rules (master reference) |
| `sovereign.guard.json` | Green gate configuration |

---

## 🤖 Automation Modes

The app supports three modes:
1. **Manual** - Every step is click-driven
2. **Auto Review** - Automatically builds and reviews generated files
3. **Full Auto Draft PR** - Builds, reviews, and publishes a guarded Draft PR

Full Auto rules:
- Still runs repo snapshot checks, functional guards, generated-file review, workflow watch
- Creates branch, commit and Draft PR
- Must NOT auto-merge or push directly to default branch
- Switching back to Manual must stop new automation cycles
- Identical input snapshots should not be processed repeatedly

---

## 📋 Release Gates

A change is NOT release-ready just because a generated package exists. Treat it as a release candidate only after these gates are green:

- TypeScript type check
- Unit tests
- Web build
- Runtime/UX/live-path contract scan
- Security/static audit
- Android debug APK build (if applicable)

---

*This file is auto-generated from repository documentation. Last updated: 2024*
