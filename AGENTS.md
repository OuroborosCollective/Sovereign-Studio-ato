# Repository Agent Rules

This file is mandatory reading for every agent, model, Copilot session, automation, or human contributor working in this repository.

## Project identity

This repository is `NOCODESTUDIO Sovereign Tool / Sovereign-Studio-ato`.

Do not mix it with Areloria, WASD, MMORPG, ARE logic, or unrelated game paths unless the user explicitly asks for that.

## Prime directive

Build a runtime that produces truth.
Do not build a UI that invents truth.
The UI may only display verified runtime state.

## Causal runtime chain

Every workflow must follow this chain:

1. Action starts.
2. Action produces a result.
3. Result creates or updates state.
4. State allows, blocks, or routes the next action.
5. The next action must be logically derivable from that state.

Do not jump because a button was clicked, a text string is visible, or the UI looks ready.

## Approved truth sources

Use real runtime sources:

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

Do not use DOM text, page text scraping, static percentages, or visual UI state as the source of truth.

## Progress rule

No hard percentage progress.
No fixed maximum step count.
Progress must be a step plan derived from the real runtime flow.

Correct pattern:

```text
currentStep / totalRuntimeSteps - current runtime action
```

The total must come from the planned runtime flow, not from a hardcoded UI list.

## Placeholder mission rule

Default or vague text must never enter `package-build` as-is.

Examples that must be normalized or blocked before package build:

- `README + Update History`
- `Mach weiter`
- `Fehler`
- `Ideen`
- `Plan`
- `Workflow Fehleranalyse + Runtime Check + Test Plan`

The tool must derive a concrete mission from repo analysis or stop in a safe yellow state with a clear next action.

## Draft PR rule

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
A PR containing only `docs/SOVEREIGN_PLAN.md` and generated workflow preview artifacts is not acceptable.

## Sovereign Search/Replace Runner workflow rule

For large files or risky edits, agents must prefer the guarded Search/Replace Runner workflow over blind full-file replacement.

Canonical flow:

1. Read the current file from GitHub and identify exact SEARCH blocks.
2. Create or update a patch file in `scripts/patches/pending/*.json`.
3. The patch file must include `target`, `blocks`, `commit_message`, `pr_title`, and `pr_body`.
4. For non-main integration branches, use `source_ref` and `branch_base_ref` with the exact commit SHA when a branch ref is not resolvable in Actions.
5. Run `Sovereign Search/Replace Runner` with `dry_run=true` first.
6. Only after dry-run validation succeeds, run the same workflow with `dry_run=false`.
7. Inspect the resulting Draft PR and CI before merge.

Patch file shape:

```json
{
  "target": "src/features/product/containers/BuilderContainer.tsx",
  "source_ref": "<branch-or-commit-sha>",
  "branch_base_ref": "<branch-or-commit-sha>",
  "branch": "<target-patch-branch>",
  "expectedSha": "<current-file-blob-sha>",
  "commit_message": "feat(runtime): describe real change",
  "pr_title": "feat(runtime): describe real change",
  "pr_body": "Explain runtime result, validation and user-visible effect.",
  "blocks": [
    {
      "search": "exact existing code",
      "replace": "new code"
    }
  ]
}
```

Runner guardrails:

- max 20 blocks per patch
- each `search` must match exactly once
- max 8 KB per `search` or `replace`
- max 500 KB target file
- optional `expectedSha` blocks stale patches
- dry-run must happen before apply
- workflow uses `secrets.SOVEREIGN_GITHUB_TOKEN`; never put raw tokens into chat, patch files, logs, or code
- runner opens or updates a Draft PR; it must never write directly to `main`

This workflow is the default for `BuilderContainer.tsx`, `App.tsx`, workflow files, and any other large or high-risk file.

## Live-path integrity

No mocks, stubs, facades, fake snapshots, fake success states, or hardcoded green states in the live path.

Test fixtures are allowed only inside tests and must stay clearly separated from production runtime code.

## Runtime validation and tests

Every new runtime route, state transition, guard, memory bridge, repo analysis path, package build path, draft PR path, and workflow repair path needs useful runtime checks and tests.

Minimum expected coverage for new logic:

- success case
- failure case
- invalid input case
- state transition case
- guard behavior case

## Repo Insight rule

Repo Insight is not decoration. It must produce actionable missions from real repo structure, findings, workflow state, telemetry, and memory patterns.

A suggestion button must set an executable mission, not a generic explanation such as `whyUseful`.

## Pattern Memory rule

Learning patterns may suggest actions, but they never override runtime truth.
A pattern must be validated against current repo state, guards, and tests before it affects output.

## Error handling rule

Failures must route into a repair flow, not into blind retry loops.

A failed action must produce:

1. recorded error result
2. classified state
3. safe next action
4. repair mission or user-visible stop reason

## User-experience rule

The user must not need developer language.
The tool translates vague input such as `Mach weiter` into a safe repo-derived mission or explains the next safe stop in plain language.

## Completion rule

Before claiming work is done, verify:

- the real issue was addressed
- the fix runs in the live path
- tests or validation were added
- no mock/stub/facade entered live code
- no hardcoded UI truth was added
- no plan-only Draft PR path was introduced
- the flow is understandable for a non-developer user

If these checks are not satisfied, report the exact blocker instead of claiming success.

## Required green gate

Before finishing any code change, run or explicitly report why you could not run:

- `pnpm run audit:sovereign`
- `pnpm run type-check`
- `pnpm exec vitest run` (with specific test files)
- `pnpm run build`

Do not stop after fixing only the latest touched file if older failures block the product path.

## Protected product shape

Protect these product rules:

- left side: GitHub file tree and idea/order input
- center: chat, matrix-style file editor and live status
- right side: history log and plain-language analysis
- free-first routing before optional user keys
- visible fix loop on errors
- user confirmation before writing unless autonomous mode is active

## ChatSidebar & Model Selection

The chat interface uses modern ARE-style design with auto-detecting model selection.

### ChatSidebar Component
**Location:** `src/features/product/components/ChatSidebar.tsx`

**Props:**
```typescript
interface ChatSidebarProps {
  chatMessages: ChatMessage[];
  suggestions: Suggestion[];
  isAnalyzing: boolean;
  onSendMessage: (message: string) => void;
  onAcceptSuggestion: (suggestionId: string) => void;
  onDownloadPackage: () => void;
  onClearChat: () => void;
  availableModels?: LlmModelInfo[];      // Auto-detected from adapters
  selectedModel?: string;                  // Currently selected model ID
  onModelChange?: (modelId: string) => void;
}
```

### Kaomoji Thinking Animation 🎉
**DO NOT SIMPLIFY** - The thinking indicator cycles through cute chick emoticons:

```typescript
const THINKING_FRAMES = ['( ^ω^)', '(^_^)', '(^‿^)', '(^o^)', '(^・ω・^)'];
```

- Cycles every 800ms while `isAnalyzing={true}`
- Shows Loader2 spinner + current kaomoji frame
- Preserved for user experience delight

### Model Selection Hook
**Location:** `src/features/product/hooks/useChatModelSelector.ts`

```typescript
import { useChatModelSelector } from '../hooks/useChatModelSelector';

// Extracts available models from LLM adapters
// Prioritizes user-key providers automatically
// Returns: availableModels, selectedModelId, selectedModel, handleModelChange
```

### Chat UI Design Tokens
Uses Sovereign dark/cyan theme:
- Background: `bg-slate-950`, `bg-slate-900/50`
- Borders: `border-cyan-500/20`, `border-cyan-500/30`
- Text: `text-slate-100`, `text-cyan-400`
- Quick actions: pill-style chips with `rounded-full`

## Development Commands & Patterns

### Package Manager
Uses `pnpm` (not npm):
```bash
pnpm install          # Install dependencies
pnpm run dev          # Start dev server (http://localhost:5000)
pnpm run build:web    # Production web build
```

### Quality Gates (required before PR)
```bash
pnpm run type-check           # TypeScript check
pnpm run audit:sovereign      # Custom static audit with NoMock validation
pnpm exec vitest run          # All tests
pnpm run build:web            # Web build
```

### Backend
Python Flask app at `scripts/sovereign-backend/app.py`:
```bash
python3 -m py_compile scripts/sovereign-backend/app.py
```

### Auth Pattern
Backend uses `_get_session_user_id()` to read JWT from HTTP-only cookie. **Never use `X-User-Id` headers** for authentication.

### CORS Pattern
Must use explicit origins list, not `origins="*"`:
```python
CORS(app, origins=CORS_ORIGINS, supports_credentials=True)
```
