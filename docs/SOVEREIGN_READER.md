# Sovereign Reader: Runtime, Routing & Agent Handoff

This reader is the practical orientation layer for Sovereign Studio ATO. It explains what the current tool actually does, which modules are trusted, and which guardrails must stay intact while future agents add features.

## Current product baseline

Sovereign Studio is an Android-first NoCode/AI service tool with a chat-first workbench.

```text
User talks to Sovereign.
Sovereign operates the control room behind the curtain.
Runtime creates truth.
UI displays truth.
```

The live product path is:

```text
src/App.tsx
→ src/features/product/containers/BuilderContainer.tsx
→ src/features/product/runtime/**
```

`BuilderContainer.tsx` is the central visible work surface: chat timeline, input, thinking/status cues, compact lamps, action stream and tool launcher. Runtime decisions must stay in `src/features/product/runtime/**`.

## Current functional chain

```txt
Chat input / repo setup
↓
Intent + local status detection
↓
Real repository snapshot gate
↓
GitHub access validation gate for write intents
↓
Capability route decision
↓
Worker/model answer OR Direct GitHub Patch OR Workspace/OpenHands Executor OR Draft PR Runtime
↓
Action Stream + active blocker state
↓
Diff / review / Draft PR / workflow watch
```

The important rule: no visible action should pretend that a repository has been analyzed, changed or published until a real runtime result exists.

## Core reader map

| Area | Entry point | Purpose |
| --- | --- | --- |
| Main work surface | `src/features/product/containers/BuilderContainer.tsx` | Central chat workbench and runtime-state display. |
| Chat helpers | `src/features/product/runtime/builderChatHelpers.ts` | Builds chat lines and local status answers. |
| Intent split | `src/features/product/runtime/workerIntentDetector.ts` | Distinguishes worker chat, code/executor/write intents. |
| Action stream | `src/features/product/runtime/sovereignActionStreamRuntime.ts` | Records input, route selection, access checks, blocker and result events. |
| GitHub access state | `src/features/product/runtime/githubAccessRuntime.ts` | Validates GitHub access through format + real API checks. |
| GitHub access UI | `src/features/product/components/GitHubAccessCard.tsx` | Secure access input and status display. |
| Repo loading | `src/features/github/hooks/useGithubRepo.ts` | Loads real GitHub tree entries and handles snapshot restore. |
| GitHub auth utilities | `src/features/github/githubAuthSession.ts` | Builds headers and strips access values from user-visible errors. |
| Draft PR publisher | `src/features/github/githubPackagePublisher.ts` | Creates branch, tree, commit and Draft PR. |
| Generated file review | `src/features/product/runtime/generatedFileReview.ts` | Reviews generated files before publish. |
| Functional guards | `src/features/product/runtime/sovereignFunctionalGuards.ts` | Blocks empty snapshots, forbidden paths and incomplete outputs. |
| Workflow watch | `src/features/product/runtime/workflowWatch.ts` | Reads GitHub commit status/check-runs after Draft PR creation. |
| Product truth | `docs/SOVEREIGN_PRODUCT_TRUTH.md` | Product invariants that prevent dashboard and fake-state drift. |
| Capability routing | `docs/SOVEREIGN_CAPABILITY_ROUTING.md` | Route model for chat, Direct Patch, workspace and Draft PR. |

## Practical capabilities

### 1. Chat-first repo work

The user can load a repo and issue tasks through the chat. The UI must stay calm: chat timeline, input, small state cues and compact lamps by default.

Best practice:

- Keep Repo, Files, Diff, Workflow, Runtime, Telemetry, Health, Coverage, Memory and Inspector as explicit inspection surfaces.
- Do not create a second main shell or busy dashboard.
- Do not move runtime truth into UI-only state.

### 2. Real repo perception

The app can load a repository tree and build a local snapshot from it. The first pass is path/tree based and intentionally cheap.

Best practice:

- Use tree paths for architecture detection first.
- Fetch file contents only when a later step truly needs them.
- Mark restored snapshots as restored/last-known, not fresh truth.

### 3. GitHub access validation

A format-valid access value is not write access. Write access is ready only after GitHub API validation against the loaded repo.

Best practice:

- Use `GitHubAccessCard` for access input.
- Store only masked access state in runtime.
- Never write raw access values to chat, telemetry, action events, docs or generated files.
- If an access value may have been visible in a recording or clipboard history, recommend rotation.

### 4. Capability routing

Sovereign should feel like one assistant, but internally it should route by capability:

```text
free_chat
repo_read
code_patch_plan
direct_github_patch
isolated_workspace
test_runner
draft_pr
workflow_watch
memory_search
```

Best practice:

- Normal questions go to worker/model route.
- Status questions after a blocker are answered locally from runtime state.
- README/docs mini-patches should not require OpenHands.
- Multi-file code work and tests require workspace/OpenHands or a future executor.

### 5. Direct GitHub Patch

The intended Direct Patch route is for small docs changes first:

```text
README.md
README.*
docs/**/*.md
```

Best practice:

- Direct Patch v1 should not touch `src/**`, `android/**`, workflows or package manifests.
- Generate a diff/preview before Draft PR.
- Validate target path, non-empty patch, no secrets and scope.

### 6. Workspace / OpenHands executor

OpenHands is not a normal LLM route. It is a workspace/code executor that can use a model while working with files and commands.

Best practice:

- Treat OpenHands as one optional executor.
- Do not block every small file change just because OpenHands is missing.
- Start a workspace only for tasks that need file/test/build execution.
- Every workspace job must be isolated.

### 7. Local runtime answers

Questions like these should not be blindly sent to a broken worker:

```text
Bist du fertig?
Warum passiert nichts?
Wo ist der Patch?
Nutzen wir eine andere Route und nicht OpenHands?
```

Best practice:

- Answer from last known runtime state.
- Say what is ready, what is blocked and what next action is allowed.
- Never claim a patch or Draft PR exists unless it does.

### 8. Active blockers

Repeated identical blockers must not inflate error counts.

Best practice:

- Track active blockers by route + kind + normalized detail.
- Show occurrences if repeated.
- Keep Errors, Warnings and Active Blockers distinct.
- Next action must match the actual state.

### 9. Generated file review and Draft PR

Draft PR publishing intentionally does not auto-merge.

Best practice:

- Draft PR first, review second, merge later.
- No Plan-only Draft PRs.
- A worker answer is not a file change.
- A generated package is not release-ready until guards and checks pass.

### 10. Workflow watch

Workflow Watch reads GitHub commit statuses/check-runs for produced commits.

Best practice:

- Pending checks are wait state, not failure.
- Empty workflow/combined status from the connector is not green.
- Failed check names should become focused repair guidance.

## Open architecture issues

The current architecture is captured in these issues:

```text
#500 Route write intents after GitHub ready without OpenHands lock-in
#501 Direct GitHub Patch route for README/docs changes
#502 Sovereign Capability Router
#503 Agent-neutral Workspace Runtime
#504 Active blocker dedupe and honest status
#505 Credential handling and Android clipboard guidance
```

Future agents should use these as the route map instead of inventing another surface.

## Verification gates

Recommended checks before merge:

```bash
pnpm run type-check
pnpm run test:unit
pnpm run build:web
pnpm run audit:sovereign
```

If present in the current repo state:

```bash
pnpm run verify
pnpm run test:e2e
pnpm run audit:all
```

Never claim CI green when GitHub workflow runs or combined statuses are empty.

## Large file rule

For large files such as:

```text
src/App.tsx
src/features/product/containers/BuilderContainer.tsx
```

prefer small runtime modules and targeted SEARCH/REPLACE patches. Do not do blind full-file replacement.

## Drift prevention summary

Future agents must not:

- build a new main shell;
- turn inspection panels into the default room;
- make OpenHands the only write path;
- send local status questions to a broken worker;
- treat token format as GitHub write access;
- count the same active blocker as many new errors;
- close issues for planned work without committed code and checks;
- claim release-ready without real build/test/device evidence.
