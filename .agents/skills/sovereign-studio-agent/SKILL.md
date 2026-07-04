---
name: sovereign-studio-agent
description: Use this skill when working on Sovereign Studio ATO (OuroborosCollective/Sovereign-Studio-ato). Activate when the user mentions apply patch, implement issue, BuilderContainer, runtime truth, capability router, direct GitHub patch, OpenHands, workspace executor, Draft PR, run checks, push or close issues. Provides guidance on chat-first product rules, runtime library integration, GitHub access safety, branch/Draft PR workflow and issue management.
---

# Sovereign Studio Agent Skill

This skill provides procedural knowledge for working with the Sovereign Studio ATO repository.

The repository is an Android-first NoCode/AI service tool. It is not Areloria/WASD/MMORPG. The product must stay chat-first and runtime-truth-first.

## Core purpose

Execute repository improvements as isolated, tested, verified patches. Prefer branch + Draft PR for non-trivial changes. Do not auto-merge. Do not claim green when checks are not visible.

## Product law

```text
Do not build a UI that creates truth.
Build a runtime that creates truth.
The UI may only display that truth.
```

Always preserve:

- Chat-first default surface.
- Runtime decisions in `src/features/product/runtime/**`.
- `BuilderContainer.tsx` as central visible work surface, not product truth source.
- Repo, Files, Diff, Workflow, Runtime, Telemetry, Health, Coverage, Memory and Inspector as inspection surfaces.
- No fake success.
- No hard percent progress unless it is a real measured metric.
- No mocks, stubs or facades in live paths.
- No Plan-only Draft PR.
- No auto-merge.
- No secrets in chat, logs, telemetry, action events, docs, PR bodies or generated files.

## Current live path

```text
src/App.tsx
→ src/features/product/containers/BuilderContainer.tsx
→ src/features/product/runtime/**
```

`BuilderContainer.tsx` is large. Avoid blind full-file replacement. Prefer new runtime modules and targeted SEARCH/REPLACE patches.

## Capability routing baseline

Do not treat OpenHands as the only write route.

Correct model:

```text
normal question → worker/model route
status question → local runtime answer
README/docs mini-patch → Direct GitHub Patch route
multi-file code/test/build task → workspace executor or OpenHands
Draft PR → Draft PR runtime
```

OpenHands is not a normal LLM route. It is an optional workspace/code executor that may use an LLM. It can work with files and commands. It must not be the only way to change files.

Related docs:

```text
docs/SOVEREIGN_PRODUCT_TRUTH.md
docs/SOVEREIGN_RUNTIME.md
docs/SOVEREIGN_CAPABILITY_ROUTING.md
docs/GITHUB_AUTH_SESSION.md
docs/SOVEREIGN_READER.md
```

## Current architecture issues

Use these issues as the route map:

```text
#500 Route write intents after GitHub ready without OpenHands lock-in
#501 Direct GitHub Patch route for README/docs changes
#502 Sovereign Capability Router
#503 Agent-neutral Workspace Runtime
#504 Active blocker dedupe and honest status
#505 Credential handling and Android clipboard guidance
```

Implement in that order unless the user explicitly changes priority.

## Patch workflow

### 1. Inspect current state

Before editing:

```bash
git fetch origin main
git checkout main
git pull --ff-only origin main
git rev-parse --short HEAD
```

Then inspect the actual target files. Do not rely on old chat summaries.

### 2. Choose safe change mode

For small/new files:

- full-file replacement is acceptable if the whole file is understood.

For large live-path files:

```text
src/App.tsx
src/features/product/containers/BuilderContainer.tsx
```

use targeted SEARCH/REPLACE patches:

```text
DATEI: path/to/file.tsx
<<<<<<< SUCHEN
exact existing code
=======
new code
>>>>>>> ERSETZEN
```

No placeholders. No omissions. No “rest stays unchanged” pseudo-files.

### 3. Runtime first

When adding new logic:

1. Create/extend a runtime module under `src/features/product/runtime/**`.
2. Add tests next to it.
3. Wire the UI to display the runtime state.
4. Keep the UI small and calm.

Examples:

```text
sovereignCapabilityRouter.ts
sovereignCapabilityRouter.test.ts
directGithubPatchRuntime.ts
directGithubPatchRuntime.test.ts
sovereignBlockerRegistry.ts
sovereignBlockerRegistry.test.ts
```

### 4. GitHub access safety

Never treat token format as write access.

Use the GitHub access runtime state:

```text
missing/requested
validating
ready
invalid/failed
```

A write path is allowed only when the runtime has confirmed access through the GitHub API for the loaded repo.

Never place raw access values in:

```text
chat lines
action events
logs
telemetry
session memory
docs
PR body
issue body
```

### 5. Required verification gates

Run relevant checks before pushing or marking work complete:

```bash
pnpm run type-check
pnpm run test:unit
pnpm run build:web
pnpm run audit:sovereign
```

If present:

```bash
pnpm run verify
pnpm run test:e2e
pnpm run audit:all
```

For targeted runtime work, also run the exact tests for the changed files.

If a check cannot run in the environment, say that honestly. Do not replace missing checks with confidence claims.

## Draft PR workflow

For non-trivial changes:

1. Create a branch.
2. Apply focused commits.
3. Run checks.
4. Open a Draft PR.
5. Do not merge unless the user explicitly approves and the required checks are known.

Commit message style:

```text
feat(runtime): add capability router
fix(runtime): route write intent after github ready
fix(security): harden GitHub access handling
```

PR body should include:

```text
Summary
Changed files
Runtime truth/state changes
Tests/checks run
Known unchecked gates
No auto-merge note
```

## Issue management

Do not close issues for planned work.

Close an issue only when:

- implementation is committed;
- acceptance criteria are satisfied;
- relevant tests/checks are run or explicitly reported as unavailable;
- the issue body is not contradicted by the final state.

When closing, add a comment summarizing commit SHA, files changed and checks.

## Common pitfalls

### Pitfall: creating a second main UI

Do not create a new dashboard, wrapper shell or parallel workbench as the live path. New UI belongs inside the existing product surface or as an inspection component.

### Pitfall: OpenHands lock-in

If GitHub access is ready but OpenHands is missing, the blocker is executor capability, not GitHub access. Check Direct GitHub Patch or Workspace Runtime capability next.

### Pitfall: worker answer equals code change

A model answer can explain or propose. It does not mean files changed. File changes require patch/runtime result, diff and review.

### Pitfall: repeated blocker counted as many errors

The same active blocker should be deduplicated with occurrences. Do not inflate `Errors` for repeated identical route blockers.

### Pitfall: empty CI data treated as green

If workflow runs or combined statuses are empty, say no CI truth is visible.

## File structure reference

```text
src/features/product/
├── containers/
│   └── BuilderContainer.tsx          # Main chat workbench, large file
├── components/
│   ├── GitHubAccessCard.tsx          # Secure access UI
│   └── SovereignActionStreamPanel.tsx# Inline action trace
└── runtime/
    ├── builderChatHelpers.ts         # Chat lines and status answers
    ├── githubAccessRuntime.ts        # GitHub access validation state
    ├── workerIntentDetector.ts       # Intent routing helpers
    ├── sovereignActionStreamRuntime.ts
    └── devChatWorkerBridge.ts        # Worker communication
```

## Final response style

Be direct and honest:

```text
Done: committed / PR opened.
Not done: CI not visible / check unavailable / blocked by connector.
Next real step: ...
```

Never say “fertig” when the state is only planned, pushed without checks, or blocked.
