# Product Rules Reference

This document provides detailed guidance on the Sovereign Studio product rules that must be followed when implementing any feature.

## Prime Directive

```
Build a runtime that produces truth.
Do not build a UI that invents truth.
The UI may only display verified runtime state.
```

## Causal Runtime Chain

Every workflow must follow this chain:

1. **Action starts** — User interaction or external event
2. **Action produces a result** — Runtime execution
3. **Result creates or updates state** — State machine transition
4. **State allows, blocks, or routes the next action** — Guards
5. **The next action must be logically derivable from that state** — No UI jumps

**Do NOT jump because a button was clicked, a text string is visible, or the UI looks ready.**

## Approved Truth Sources

Use only these as sources of truth:

| Source | Purpose |
|--------|---------|
| `sequentialRuntime` | Sequential execution state |
| `repoSnapshotStatus` | Repository loading state |
| `repoFiles` | Loaded file tree |
| `scanRegistry` | Scan results |
| `workflowReport` | CI/CD status |
| `lastPackage` | Generated package |
| `latestGeneratedReview` | Review results |
| `diffReport` | File diffs |
| `telemetry` | Runtime telemetry |
| `solutionPatternStore` | Learned patterns |
| `remoteMemoryIntake` | External memory |
| `automationStatus` | Automation state |

**Do NOT use**: DOM text, page text scraping, static percentages, or visual UI state as the source of truth.

## Progress Rule

No hard percentage progress. No fixed maximum step count.

**Correct pattern:**
```
currentStep / totalRuntimeSteps - current runtime action
```

The total must come from the planned runtime flow, not from a hardcoded UI list.

## Placeholder Mission Rule

Default or vague text must never enter `package-build` as-is.

Examples that must be normalized or blocked before package build:
- `README + Update History`
- `Mach weiter`
- `Fehler`
- `Ideen`
- `Plan`
- `Workflow Fehleranalyse + Runtime Check + Test Plan`

The tool must derive a concrete mission from repo analysis or stop in a safe yellow state with a clear next action.

## Draft PR Rule

Draft PRs require real execution patches.

**Actionable targets:**
- `src/`
- `tests/`
- `android/`
- `scripts/`
- `.github/workflows/`
- Real config files
- `README.md`
- Real `docs/`

**Plan-only output must not count as actionable work.** A PR containing only `docs/SOVEREIGN_PLAN.md` and generated workflow preview artifacts is NOT acceptable.

## Live-Path Integrity

- **No mocks, stubs, facades, fake snapshots, fake success states, or hardcoded green states in the live path**
- Test fixtures are allowed only inside tests and must stay clearly separated from production runtime code

## Error Handling Rule

Failures must route into a repair flow, not into blind retry loops.

A failed action must produce:
1. Recorded error result
2. Classified state
3. Safe next action
4. Repair mission or user-visible stop reason

## User-Experience Rule

The user must not need developer language. The tool translates vague input into a safe repo-derived mission or explains the next safe stop in plain language.

## Completion Rule

Before claiming work is done, verify:

- [ ] The real issue was addressed
- [ ] The fix runs in the live path
- [ ] Tests or validation were added
- [ ] No mock/stub/facade entered live code
- [ ] No hardcoded UI truth was added
- [ ] No plan-only Draft PR path was introduced
- [ ] The flow is understandable for a non-developer user

## Required Green Gate

Before finishing any code change, run or explicitly report why you could not run:

```bash
pnpm run audit:sovereign
pnpm run type-check
pnpm exec vitest run
pnpm run build
```

Do NOT stop after fixing only the latest touched file if older failures block the product path.

## Protected Product Shape

Protect these product rules:
- Left side: GitHub file tree and idea/order input
- Center: Chat, matrix-style file editor and live status
- Right side: History log and plain-language analysis
- Free-first routing before optional user keys
- Visible fix loop on errors
- User confirmation before writing unless autonomous mode is active

## ChatSidebar & Model Selection

The chat interface uses modern ARE-style design with auto-detecting model selection.

### ChatSidebar Component

**Location:** `src/features/product/components/ChatSidebar.tsx`

### Kaomoji Thinking Animation

The thinking indicator cycles through cute chick emoticons:
```typescript
const THINKING_FRAMES = ['( ^ω^)', '(^_^)', '(^‿^)', '(^o^)', '(^・ω・^)'];
```
- Cycles every 800ms while `isAnalyzing={true}`
- Shows Loader2 spinner + current kaomoji frame
- Preserved for user experience delight

### Model Selection Hook

**Location:** `src/features/product/hooks/useChatModelSelector.ts`

Extracts available models from LLM adapters, prioritizes user-key providers automatically.

## Runtime Truth Path

1. Real GitHub repository tree is loaded
2. Repo paths are converted into readiness signals
3. A mission is classified against the loaded snapshot
4. Provider output is normalized into the Sovereign brain contract
5. Generated files are reviewed by functional guards
6. Diff context is loaded when available
7. Draft PR publishing creates a branch, tree, commit and PR
8. Workflow watch reads GitHub Actions status for the produced commit
9. UI/Coach state is derived from runtime state, not DOM scraping

## Brain Gate

Every accepted package must include these layers:
- Perception
- Analysis
- Plan
- Execution
- Learning

A response without usable execution patches is NOT a release artifact. A response that touches forbidden paths, duplicates generated output or bypasses file review must be rejected before GitHub publishing.
