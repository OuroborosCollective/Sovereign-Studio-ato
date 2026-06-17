# Sovereign Reader: Tools, Skills & Best Practices

This reader is the practical orientation layer for Sovereign Studio. It explains what the current tool actually does, which modules are trusted, and which guardrails must stay intact while new ideas are integrated.

## Current functional chain

```txt
GitHub Repo URL + optional PAT
↓
Real repository tree loader
↓
Repo Launch Readiness Panel
↓
Repo File Integrity Matrix
↓
Sovereign Action Builder
↓
Brain-gated implementation package
↓
Functional guards
↓
Generated Files Review
↓
Automation Mode policy
↓
Draft PR Publisher
↓
Workflow Watch
↓
Health Dashboard + Runtime Validation Coverage
↓
Telemetry terminal + session memory
```

The important rule is simple: no visible action should pretend that a repository has been analyzed until a real repository snapshot has been loaded. Full Auto can remove extra clicks, but it must not remove system checks.

## Core reader map

| Area | Entry point | Purpose |
| --- | --- | --- |
| Repo loading | `src/features/github/hooks/useGithubRepo.ts` | Loads real GitHub tree entries, handles default branch fallback, private repo PATs and safe snapshot restore. |
| Repo URL parsing | `src/features/github/utils.ts` | Normalizes GitHub repo URLs before API use. |
| Readiness runtime | `src/features/product/runtime/repoLaunchReadiness.ts` | Scores launch readiness and builds risk/checklist/release-state output. |
| File signal mapping | `src/features/product/runtime/repoLaunchReadinessFromFiles.ts` | Converts loaded tree entries into readiness signals. |
| File integrity matrix | `src/features/product/runtime/repoFileIntegrity.ts` | Performs honest path-only risk scoring for repo entries without pretending to scan content. |
| Generated file review | `src/features/product/runtime/generatedFileReview.ts` | Reviews generated files before publish, flags high-risk content/path markers and creates preview metadata. |
| Automation mode policy | `src/features/product/runtime/sovereignAutomationMode.ts` | Decides when Manual, Auto Review or Full Auto Draft PR may run. |
| Workflow watch | `src/features/product/runtime/workflowWatch.ts` | Reads commit status/check-runs after Draft PR creation and prepares repair hints. |
| Health runtime | `src/features/product/runtime/sovereignHealth.ts` | Aggregates repo risk, generated file review, workflow state and telemetry into one health signal. |
| Runtime coverage | `src/features/product/runtime/runtimeValidationCoverage.ts` | Maintains the runtime/test/integration coverage manifest. |
| Telemetry runtime | `src/features/product/runtime/sovereignTelemetry.ts` | Records visible lifecycle events across repo, readiness, package, guards, GitHub, workflow, memory and UI stages. |
| Session memory | `src/features/product/runtime/sovereignSessionMemory.ts` | Saves and restores repo snapshot, mission and preview without storing PATs. |
| Brain package builder | `src/features/product/runtime/sovereignPackageFromRepoFiles.ts` | Turns a mission and repo snapshot into a Sovereign implementation package. |
| Functional guards | `src/features/product/runtime/sovereignFunctionalGuards.ts` | Blocks empty snapshots, duplicate files, forbidden paths and incomplete docs packages. |
| Draft PR publisher | `src/features/github/githubPackagePublisher.ts` | Creates branch, tree, commit and draft pull request through GitHub API. |
| UI shell | `src/App.tsx` | Wires tabbed repo loading, readiness, integrity, action builder, file review, automation mode, workflow watch, health, coverage, telemetry and draft PR creation. |

## Practical skills this tool now has

### 1. Repository perception

The app can load a repository tree and build a practical local snapshot from it. This snapshot is intentionally limited to path, type and size. That keeps the first perception pass cheap, quick and safe.

Best practice:

- Use tree paths for architecture detection first.
- Fetch file contents only when a later step truly needs them.
- Keep private repo access behind an explicit PAT field.
- Never store PAT values in session memory.

### 2. Launch readiness scoring

The readiness runtime checks for documentation, license, tests, workflows, runtime validation, branch-safety hints and open-workload signals. It returns a score, grade, risk register and owner checklist.

Best practice:

- Treat readiness as guidance, not an automatic merge decision.
- Show risks before generating a PR.
- Keep owner checklist items concrete and role-based.

### 3. File integrity matrix

The file integrity layer was inspired by the GitForge-style verification matrix, but hardened for honesty. It is a path-only risk scan until file contents are explicitly fetched.

It can flag:

- secret-looking paths
- generated/build folders
- mock/stub/todo/sample indicators
- very large files
- code/test file hints

Best practice:

- Label confidence clearly as `path-only`.
- Do not call path-only scores content verification.
- Use the matrix to prioritize follow-up scans, not to declare a repo safe.

### 4. Brain-gated package generation

A Sovereign package is not just text. It must contain a five-layer brain result and concrete implementation files. Docs/runtime requests must create the full docs set:

```txt
README.md
docs/UPDATE_HISTORY.md
docs/SOVEREIGN_RUNTIME.md
docs/LAUNCH_READINESS.md
generated/sovereign-product/workflow.ts
```

Best practice:

- No execution patches, no GitHub write.
- Docs requests must touch README or `docs/*`.
- Generated files must be shown in preview before publishing.

### 5. Functional guards

Functional guards are the cement layer. They prevent the app from generating or publishing nonsense.

They currently block:

- empty repo snapshots
- snapshots containing only folders
- duplicate generated file paths
- empty generated file content
- unsafe output paths such as `.env`, `.git/`, `node_modules/`, `dist/`, `build/`
- incomplete docs packages

Best practice:

- Add new tool modules behind guards first, then expose them in UI.
- Never bypass `assertGeneratedPackageReady` in publishing paths.
- Keep runtime checks small and deterministic.

### 6. Generated file review

Generated file review is the final human-readable gate before a Draft PR. It lists each generated file with path, reason, line count, character count, risk level, flags and preview.

It blocks Draft PR creation when high-risk generated files are detected, for example:

- secret markers in generated content
- forbidden-looking output paths
- empty generated files

Best practice:

- Review the `Files` tab before creating a Draft PR.
- Treat workflow/config files as medium-risk and review them manually.
- Do not hide generated content behind only a JSON brain preview.

### 7. Automation modes

The app supports three modes:

```txt
Manual
Auto Review
Full Auto Draft PR
```

Manual mode keeps every step click-driven. Auto Review automatically builds and reviews generated files once repo snapshot and mission are ready. Full Auto Draft PR automatically builds, reviews and publishes a guarded Draft PR when repo snapshot, mission and PAT are ready.

Best practice:

- Full Auto still runs repo snapshot checks, functional guards, generated-file review and workflow watch.
- Full Auto may create a branch, commit and Draft PR.
- Full Auto must not auto-merge or push directly to the default branch.
- Switching back to Manual must stop new automation cycles.
- Identical input snapshots should not be processed repeatedly.

### 8. Workflow watch

Workflow Watch is the post-Draft-PR layer. It reads GitHub commit statuses and check-runs for the created commit SHA. It shows green, pending, red or unknown state and prepares repair ideas when checks fail.

Best practice:

- Watch commit checks after Draft PR creation.
- Treat pending checks as wait state, not failure.
- Use failed check names to generate focused follow-up repair packages.
- Do not claim CI success when GitHub has no check data yet.

### 9. Health dashboard

The Health Dashboard aggregates repo path risks, generated-file review, workflow status and telemetry errors into one simple status.

It shows:

- critical risks
- total issues
- repair signals
- branch delta
- recommendations

Best practice:

- Use Health as an operational overview, not a replacement for tests.
- Red means a blocking signal exists.
- Warning means follow-up review is needed.
- Green only means no blocking signal from currently available local data.

### 10. Runtime validation coverage

Runtime Validation Coverage is the manifest of core runtime modules, their companion tests and UI/integration points. It exists so new logic does not quietly appear without tests.

Best practice:

- Every runtime target needs a test path.
- Every runtime target needs a UI or workflow integration point.
- Coverage can be manifest-healthy even before local tests are executed; actual test commands still need to run in CI/local shell.

### 11. Telemetry terminal

Telemetry is the visible runtime trail. It should answer: what just happened, what stage did it happen in, and did it pass or fail?

Typical events:

```txt
repo:load-start
repo:load-finished
package:build-start
guards:passed
guards:failed
automation:auto-review
automation:full-auto
github:draft-pr-start
github:draft-pr-created
github:draft-pr-failed
workflow:watch-start
workflow:watch-finished
memory:saved
memory:restored
```

Best practice:

- Log lifecycle events, not secrets.
- Keep events short and structured.
- Use telemetry to explain failures before asking the user to retry.

### 12. Session memory

Session memory stores the last useful local state: repo URL, branch, status, repo file snapshot, mission, summary and preview. It intentionally does not store the GitHub PAT.

Best practice:

- Use memory as last-known snapshot, not proof of freshness.
- Mark restored repo state visibly.
- Re-load GitHub when freshness matters.

### 13. Draft PR publishing

The publisher creates a branch, tree, commit and draft pull request. It intentionally does not auto-merge.

Best practice:

- Draft PR first, review second, merge later.
- Use deterministic branch names plus nonce/collision fallback.
- Keep PR body useful: architecture, brain summary, generated file list and suggestions.
- Do not log or persist PAT values.

## UI workspaces

The app shell is intentionally split into tabs:

```txt
Repo
Readiness
Integrity
Builder
Files
Workflow
Health
Coverage
Telemetry
```

The Automation Mode control is visible above the workspace tabs so users can switch Manual / Auto Review / Full Auto Draft PR at any time.

## Tool progress rail

The visible workflow is based on this stable rail:

```txt
safe_repo_inspection
task_extraction
readiness_eval
checklist_generation
copywriting
workflow_watch
```

This rail should remain the top-level mental model for users. New internal tools can be added, but they should map back to one of these stages unless the user-facing workflow truly changes.

## Provider and LLM best practices

The LLM side should stay modular and guarded.

Recommended flow:

```txt
LLM Adapter
↓
LLM Revolver Router
↓
Sovereign Brain Contract
↓
Functional Guards
↓
Generated Files Review
↓
Automation Mode policy
↓
Draft PR Publisher
↓
Workflow Watch
↓
Health Dashboard
```

Rules:

- External providers are plugins, not core logic.
- Provider failure should rotate, not crash the whole tool.
- Invalid brain output should be treated as provider failure.
- Local-safe deterministic generation remains the final fallback.
- Never put secret-bearing provider calls directly into reusable UI code without a deliberate boundary.

## GitHub best practices

When writing to GitHub:

1. Parse and validate the repo URL.
2. Resolve the default branch from repo metadata.
3. Resolve base ref and base tree.
4. Create a uniquely named branch.
5. Build a tree from validated generated files.
6. Review generated files.
7. Create a commit.
8. Move the branch ref to the commit.
9. Create a draft PR.
10. Show the PR URL, branch and commit SHA.
11. Watch the created commit checks.
12. Prepare focused repair ideas from failed checks.

Do not push directly to default branch from the UI.

## Testing expectations

Every structural layer should have tests:

| Layer | Test file |
| --- | --- |
| URL parser | `src/features/github/utils.test.ts` |
| Repo file signal mapping | `src/features/product/runtime/repoLaunchReadinessFromFiles.test.ts` |
| Readiness runtime | `src/features/product/runtime/repoLaunchReadiness.test.ts` |
| File integrity runtime | `src/features/product/runtime/repoFileIntegrity.test.ts` |
| Generated file review | `src/features/product/runtime/generatedFileReview.test.ts` |
| Automation mode policy | `src/features/product/runtime/sovereignAutomationMode.test.ts` |
| Workflow watch | `src/features/product/runtime/workflowWatch.test.ts` |
| Health runtime | `src/features/product/runtime/sovereignHealth.test.ts` |
| Runtime coverage manifest | `src/features/product/runtime/runtimeValidationCoverage.test.ts` |
| Telemetry runtime | `src/features/product/runtime/sovereignTelemetry.test.ts` |
| Session memory | `src/features/product/runtime/sovereignSessionMemory.test.ts` |
| Package builder | `src/features/product/runtime/sovereignPackageFromRepoFiles.test.ts` |
| Functional guards | `src/features/product/runtime/sovereignFunctionalGuards.test.ts` |
| Draft PR publisher | `src/features/github/githubPackagePublisher.test.ts` |
| Whole structure | `src/features/product/runtime/sovereignStructure.test.ts` |

Before merging larger changes, run:

```bash
npm run type-check
npm run lint
npm run test:run
npm run build:web
```

## Integration checklist for new gold-egg modules

When a new experimental repo or file arrives, use this checklist:

- Does it improve the top-level rail?
- Can it be ported as a small runtime module?
- Can it be tested without network or secrets?
- Does it need a UI panel or only a backend helper?
- Does it create files? If yes, route through functional guards.
- Does it call GitHub? If yes, route through the publisher pattern.
- Does it call an LLM? If yes, route through adapter + revolver + brain contract.
- Does it risk fake output? If yes, keep only the idea, not the implementation.

## Anti-patterns

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
- claiming runtime coverage from docs alone without test files and CI/local execution

## Current next hardening targets

1. Add content-level source diff preview once file-content fetching exists.
2. Move PAT handling into a safer session-only utility boundary.
3. Add focused repair-package generation from failed Workflow Watch checks.
4. Keep `useProductMagic.ts` and other large hooks thin by routing through small runtime modules.

## Principle

Sovereign Studio should feel autonomous, but behave conservatively. It may generate plans and draft PRs automatically when Full Auto is enabled, but every write path must pass through repo snapshot checks, functional guards, generated-file review, workflow watch and Draft PR publishing rules.
