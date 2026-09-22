# Sovereign Runtime

Sovereign Runtime is the truth layer behind the product UI. It keeps repository automation grounded in loaded repo snapshots, explicit access checks, deterministic guards, route decisions, workflow checks and user-reviewable results.

## Core law

```text
Do not build a UI that creates truth.
Build a runtime that creates truth.
The UI may only display that truth.
```

## Truth path

For the vNext control surface, conversation and execution are deliberately separate:

1. Normal composer input is checked by the secure input guard before chat storage or LLM submission.
2. Normal chat goes only to the advisory LLM runtime. It is not classified into an execution intent.
3. A visible `⋯ → Auftrag starten` action on a concrete stored message is the only chat-side execution affordance.
4. That explicit action passes the exact stored message text to the repository-bound execution adapter.
5. The canonical repository route is `POST /api/user/agent/repository/run`; the adapter must not redirect vNext chat through a Swarm route or the retired Live Workspace Monitor.
6. Runtime/job/workspace/evidence readback remains authoritative for execution state.
7. Draft PR publishing and workflow verification remain separate gated operations.
8. UI state is derived from runtime/readback state, not DOM scraping, fake progress or provider prose.

Other product surfaces may retain separate capability-routing contracts, but they are not part of the vNext advisory-chat execution boundary.

## Runtime route categories

| Route | Purpose | Writes files? | Requires GitHub write access? | Requires workspace? |
| --- | --- | ---: | ---: | ---: |
| `local-runtime-answer` | Answer status/blocker questions from existing state | No | No | No |
| `worker-chat` | Normal model response through the worker/provider path | No | No | No |
| `code-llm` | Plan or propose patch text | No direct write | Maybe later | No |
| `direct-github-patch` | Small README/docs file changes | Yes | Yes | No |
| `workspace-executor` | Larger code work with files/tests | Yes | Usually | Yes |
| `sovereign-agent` | Optional workspace/code executor adapter | Yes | Usually | Yes |
| `draft-pr-runtime` | Create branch/commit/Draft PR | Yes | Yes | No/depends on source diff |

Sovereign Agent is not a normal LLM route. It is a workspace executor that can use an LLM. It should be one possible executor behind Sovereign, not the only write path.

## GitHub access gate

A format-valid token is not write access.

The runtime must treat GitHub access as a real state machine:

```text
missing/requested
→ validating
→ ready OR invalid/failed
```

Rules:

- Token input happens only in the secure GitHub access card.
- Tokens are used one-shot for validation/write operations and must never be copied into chat, logs, telemetry or action events.
- The state may store only a masked representation.
- `ready` means the GitHub API confirmed write/push capability for the loaded repo.
- `ready` must not be reset just because Sovereign Agent is missing.
- Sovereign Agent missing is an executor/capability blocker, not a GitHub access blocker.

## Capability Router

Sovereign should route by capability, not by UI button or agent name.

Proposed central decision function:

```ts
const decision = decideSovereignCapabilityRoute({
  text: submittedText,
  repoReady,
  githubAccessState,
  sovereign-agentReady,
  directGitHubPatchReady,
  workspaceReady,
  hasActiveWorkerBlocker,
});
```

The decision must return:

```text
route
capability
allowed/blocker
reason
nextAction
```

This is documented in [`SOVEREIGN_CAPABILITY_ROUTING.md`](SOVEREIGN_CAPABILITY_ROUTING.md).

## Local status answers

Questions like these must be answered locally from runtime state when possible:

```text
Bist du fertig?
Warum passiert nichts?
Wo ist der Patch?
Nutzen wir eine andere Route und nicht Sovereign Agent?
```

They must not blindly call a broken worker route or restart Sovereign Agent.

Examples:

```text
Nein. GitHub-Zugang wird gerade geprüft. Es gibt noch keinen Patch, keinen Diff und keinen Draft PR.
```

```text
Nein. GitHub-Zugang ist bereit, aber es wurde noch keine Datei geändert. Die Patch/Draft-PR Route ist blockiert, weil kein passender Schreib-Executor verfügbar ist.
```

## Direct GitHub Patch

Small README/docs changes should not require a full workspace executor.

Initial safe scope:

```text
README.md
README.*
docs/**/*.md
```

Do not use Direct Patch v1 for `src/**`, `android/**`, workflow files, package manifests or broad refactors. Those require stronger workspace/test gates.

## Workspace Runtime

The long-term workspace design is agent-neutral:

```text
Sovereign Agent Workspace Runtime
  ├─ Sovereign Agent adapter
  ├─ future code-agent adapter
  ├─ test runner adapter
  └─ analysis-only snapshot adapter
```

Every write job gets an isolated workspace. No agent should share a live write folder with another job.

Start a workspace only when the task needs it:

- multi-file changes;
- source-code or Android changes;
- dependency install;
- tests/build commands;
- complex repair;
- Draft PR with real code work.

Do not start a workspace for simple explanation, status answers, log summaries, pattern searches or README/docs mini-patches.

## Brain/file gates

Provider output is untrusted until guards accept it. A response without usable execution patches or reviewable changes is not a release artifact.

A response that touches forbidden paths, duplicates generated output, leaks secrets, creates empty patches or bypasses file review must be rejected before GitHub publishing.

## Action Stream

The Sovereign Action Stream is route-wide. It is not an Sovereign Agent-only stream.

It should include events like:

```text
input_received
repo_context_loaded
intent_detected
route_selected
github_access_required
github_access_validating
github_access_ready
patch_generated
patch_apply_blocked
executor_started
draft_pr_ready
failed
```

Every action event should have a route, label, detail, state and timestamp. It should be displayed inline with the chat, not as a second dashboard.

## Active blockers

Repeated identical blockers should be deduplicated.

Correct state:

```text
Active Blocker: 1
Warnings: 2
Errors: 0
```

Not:

```text
Errors: 3
```

only because the same `Sovereign Agent not configured` blocker appeared three times.

A blocker should expose:

```text
kind
route
label
detail
occurrences
nextAction
```

## Provider policy

Worker/provider output is treated as untrusted input until runtime guards accept it.

Provider/model routes may explain, classify, plan or propose. They do not prove file changes happened. A chat answer is not a patch, not a commit and not a Draft PR.

Provider failures may be recorded for diagnostics, but failed-provider text must not become product documentation or release truth.

## UI/UX runtime-state rule

The UI should show state from these runtime sources:

- repo snapshot readiness;
- GitHub access state;
- explicit execution selection;
- action stream;
- active blockers;
- package/file review state;
- Draft PR publishing state;
- workflow watch report;
- telemetry as side-channel diagnostics only.

The UI must not infer release readiness from button labels, DOM text flicker or generated prompt transcripts.

## Checks

Recommended local and CI checks:

```bash
pnpm run type-check
pnpm run test:unit
pnpm run build:web
pnpm run audit:sovereign
```

If present in the current repo state, also use:

```bash
pnpm run verify
pnpm run test:e2e
pnpm run audit:all
```

Release checks should also include runtime/UX/live-path contract scans, Android debug APK generation and real Android smoke testing.

## Related issues

```text
#500 Route write intents after GitHub ready without Sovereign Agent lock-in
#501 Direct GitHub Patch route for small README/docs changes
#502 Sovereign Capability Router
#503 Sovereign Agent Workspace Runtime
#504 Active blocker dedupe and honest status
#505 Credential handling and Android clipboard guidance
```

## vNext advisory chat boundary

The vNext chat is a conversation surface, not an execution router.

1. Composer input is checked by `secureInputGuard` before the message is stored or sent to the advisory LLM.
2. Normal chat uses the dedicated advisory runtime only. It may explain architecture, discuss runtime readback, or answer questions.
3. The advisory runtime never creates an execution contract, classifies intent, detects execution keywords, or dispatches work.
4. A visible `⋯ → Auftrag starten` action on a concrete stored message is the only UI capability that starts repository execution.
5. That action passes the exact stored message text to the existing repository-bound adapter and its canonical `/api/user/agent/repository/run` endpoint.
6. Runtime/job/workspace/evidence readback remains the source of truth. The chat does not synthesize progress or completion.
7. Swarm execution is not part of the vNext chat lane. The retired Live Workspace Monitor is not part of the vNext chat lane either; existing diagnostic surfaces remain separate.

