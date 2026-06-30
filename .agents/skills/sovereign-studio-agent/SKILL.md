---
name: sovereign-studio-agent
description: This skill should be used when working on Sovereign Studio V3 (OuroborosCollective/Sovereign-Studio-ato). Activate when the user mentions "apply patch", "apply issue", "implement #issue", "BuilderContainer", "sovereign-studio", "main branch", "run checks", "push to main", or asks to close issues. Provides guidance on patch application workflow, runtime library integration, GitHub API usage for issue management, and the Sovereign product rules.
---

# Sovereign Studio Agent Skill

This skill provides procedural knowledge for working with the Sovereign Studio V3 repository, including patch application, runtime library integration patterns, and GitHub issue management.

## Core Purpose

Execute repository improvements as isolated, tested, verified patches that are pushed to `main` and the corresponding issues are closed via GitHub API.

## Patch Application Workflow

### 1. Analyze the Patch

When a patch bundle (`.zip`) is provided:

1. **Extract the bundle** using Python (avoid `unzip` which may not be available):
   ```bash
   python3 -c "import zipfile; zipfile.ZipFile('patch.zip').extractall('extracted_patch')"
   ```

2. **Read the patch instructions** — typically found in:
   - `APPLY_*.md` files in the root of the extracted bundle
   - `*_EXTERNAL_AGENT_PROMPT.md` alongside the zip

3. **Identify files to replace** — note which files should be:
   - **Replaced entirely**: New version overwrites existing file
   - **Modified in-place**: Only specific sections need changes
   - **Not replaced**: Check if the current `main` already contains required changes

### 2. Verify Prerequisites

Before applying changes:

1. **Pull latest `main`** to ensure you're working on current state:
   ```bash
   git fetch origin main && git pull origin main
   ```

2. **Check if required runtime files exist** on main (not all files need to be created):
   ```bash
   ls src/features/product/runtime/<runtime-file>.ts
   ```

3. **Understand the existing runtime library** — check for related files:
   - `quietInspectorHintPolicy.ts` — unified signal format
   - `runtimeInspectorRuntime.ts` — existing inspector state builder
   - `androidQuickInteractionRuntime.ts` — interaction helpers

### 3. Apply Changes

For each file in the patch:

1. **Compare with existing file** to understand the scope of changes
2. **Make surgical edits** rather than wholesale replacements when possible
3. **Follow local code style** (quote style, import order, etc.)

### 4. Runtime Library Integration

When creating new runtime modules, **integrate with existing patterns**:

1. **Use existing type definitions** where applicable:
   ```typescript
   import { type QuietInspectorSignal, type QuietInspectorLamp, type QuietInspectorTarget } from "./quietInspectorHintPolicy";
   ```

2. **Export conversion helpers** for unified formats:
   ```typescript
   export function toQuietInspectorSignal(signal: MySignal, source: string): QuietInspectorSignal {
     return { id: signal.id, source, lamp: signal.lamp, message: `${signal.label}: ${signal.detail}`, targetTab: signal.targetTab, visible: true, updatedAt: Date.now() };
   }
   ```

3. **Follow the signal contract**:
   - `id`: unique identifier (e.g., `"pat-count"`)
   - `label`: short display label (e.g., `"Pattern Memory"`)
   - `detail`: descriptive text (e.g., `"5 Einträge gespeichert"`)
   - `prompt`: proposed action text for composer fill
   - `lamp`: `"green"` | `"yellow"` | `"red"` for visual state
   - `targetTab`: `"repo"` | `"memory"` | `"runtime"` | etc.

### 5. Required Verification Gates

Before pushing, run ALL checks:

```bash
# Tests
npm test -- --run src/features/product/runtime/<new-runtime>.test.ts \
           src/features/product/containers/BuilderContainer.test.tsx

# TypeScript
npx tsc --noEmit

# Build
npm run build:web

# Static audit
node scripts/sovereign-static-audit.mjs
```

If `sovereign-live-path-scan.mjs` exists:
```bash
node scripts/sovereign-live-path-scan.mjs
```

### 6. Git Commit and Push

1. **Stage only the relevant files** (exclude auto-generated files like `dist/`):
   ```bash
   git add src/features/product/runtime/<file>.ts \
          src/features/product/runtime/<file>.test.ts \
          src/features/product/containers/BuilderContainer.tsx
   ```

2. **Write descriptive commit message**:
   ```
   feat(#ISSUE): Brief description

   - What was added
   - Key behavior
   - Test coverage
   - Integration points

   Co-authored-by: openhands <openhands@all-hands.dev>
   ```

3. **Push to main**:
   ```bash
   git push origin main
   ```

### 7. Close Issues via GitHub API

After successful push, close the corresponding issues:

```bash
# Post comment
curl -s -X POST "https://api.github.com/repos/{owner}/{repo}/issues/{number}/comments" \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"body":"## ✅ Issue Completed\n\nAcceptance criteria verified.\n\n**Implementation:** `COMMIT_SHA`\n\nThis comment was created by an AI agent (OpenHands) on behalf of the repository maintainer."}'

# Close issue
curl -s -X PATCH "https://api.github.com/repos/{owner}/{repo}/issues/{number}" \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"state":"closed","state_reason":"completed"}'
```

## Product Rules (Non-Negotiable)

Always follow these rules when implementing features:

| Rule | Description |
|-------|-------------|
| **No fake truth** | Build/runtime state creates truth; UI only displays it |
| **No percentage progress** | Use step counts or honest descriptions |
| **No mocks in live paths** | Test fixtures only in test files |
| **No auto-execute** | User confirms before writes |
| **Guard haptics** | Always no-op when unsupported |
| **Chat-first default** | No new dashboards or main navigation |
| **393px layout** | Mobile viewport constraint |
| **No hidden metadata** | Copy actions copy only visible text |

## Common Pitfalls and Prevention

### Pitfall 1: Not Pulling Latest Main

**Problem**: Applying patch on stale state causes conflicts or missing dependencies.

**Prevention**: Always run `git pull origin main` before starting work.

### Pitfall 2: Forgetting Runtime Integration

**Problem**: New runtime module exists in isolation, not connected to existing patterns.

**Prevention**: Check `quietInspectorHintPolicy.ts` and related files for existing types and patterns. Always export conversion helpers.

### Pitfall 3: Skipping Tests

**Problem**: Changes appear to work but break existing functionality.

**Prevention**: Run full test suite before pushing. Add tests for new behavior.

### Pitfall 4: Not Closing Issues

**Problem**: Code is pushed but issue remains open, causing confusion.

**Prevention**: Always close issues via GitHub API after successful push.

### Pitfall 5: Overwriting Unchanged Files

**Problem**: Replacing a file that's already correct causes unnecessary diff noise.

**Prevention**: Check current `main` state before replacing. Only replace if patch explicitly requires it.

## File Structure Reference

```
src/features/product/
├── containers/
│   └── BuilderContainer.tsx    # Main chat container, large (~4000 lines)
├── components/
│   ├── RepoTreeExplorer.tsx     # File tree inspector
│   └── DraftPrCard.tsx         # Draft PR display
└── runtime/
    ├── androidQuickInteractionRuntime.ts  # Haptics, clipboard, URL detection
    ├── quietInspectorHintPolicy.ts           # Unified signal format
    ├── runtimeInspectorPanelRuntime.ts      # PAT/ORC/INT signals
    └── devChatWorkerBridge.ts              # Worker communication
```

## Additional Resources

### Reference Files

- **`references/product-rules.md`** — Detailed product rules and examples
- **`references/runtime-patterns.md`** — Runtime library integration patterns
- **`references/git-workflow.md`** — Commit and issue management workflow

### Scripts

- **`scripts/validate-checks.sh`** — Run all required verification gates
