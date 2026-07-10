# Sovereign Capability Routing

This document prevents a recurring drift: treating one executor, especially Sovereign Agent, as the only way Sovereign can do code work.

Sovereign should feel like one assistant to the user. Internally it must choose the smallest safe capability that can produce the next real result.

## Core rule

```text
Action → Result → State → Next action allowed or blocked
```

The UI does not create the route truth. Runtime does.

## Sovereign Agent is not an LLM route

OpenAI, Cerebras and the Cloudflare Worker path are model or model-proxy routes. They can answer, analyze and propose text/code.

Sovereign Agent is different. It is a workspace/code executor. It may use an LLM, but its value is that it can work with files, a sandbox, command execution, tests, diffs and PR-oriented results.

Therefore:

```text
Worker/model route = thinks and answers.
Sovereign Agent/workspace route = works in a repo workspace.
Direct GitHub Patch route = applies small, validated file changes without a full workspace.
```

Sovereign Agent must remain optional. It must not be the only path after GitHub write access becomes ready.

## Capability types

Proposed runtime type:

```ts
export type SovereignCapability =
  | 'free_chat'
  | 'repo_read'
  | 'code_patch_plan'
  | 'direct_github_patch'
  | 'isolated_workspace'
  | 'test_runner'
  | 'draft_pr'
  | 'workflow_watch'
  | 'memory_search';
```

Proposed route type:

```ts
export type SovereignRoute =
  | 'worker-chat'
  | 'code-llm'
  | 'direct-github-patch'
  | 'workspace-executor'
  | 'sovereign-agent'
  | 'draft-pr-runtime'
  | 'local-runtime-answer';
```

Proposed decision type:

```ts
export interface CapabilityDecision {
  readonly route: SovereignRoute;
  readonly capability: SovereignCapability;
  readonly allowed: boolean;
  readonly reason: string;
  readonly blocker?:
    | 'repo_missing'
    | 'github_access_missing'
    | 'github_access_validating'
    | 'executor_unavailable'
    | 'workspace_required'
    | 'unsupported_intent'
    | 'unsafe_action';
  readonly nextAction:
    | 'ask_user'
    | 'load_repo'
    | 'validate_github_access'
    | 'run_worker'
    | 'run_direct_patch'
    | 'start_workspace'
    | 'start_sovereign-agent'
    | 'create_draft_pr'
    | 'show_blocker';
}
```

## Route matrix

| Intent | Required state | Route | Must not do |
| --- | --- | --- | --- |
| Normal question | none or repo snapshot | `worker-chat` | Start a write workspace. |
| Status question after blocker | existing runtime state | `local-runtime-answer` | Re-call the broken worker blindly. |
| README/docs mini-patch | repo + validated GitHub write | `direct-github-patch` | Require Sovereign Agent by default. |
| Multi-file source change | repo + workspace executor | `workspace-executor` or `sovereign-agent` | Pretend a chat answer changed files. |
| Draft PR | validated GitHub write + reviewed changes | `draft-pr-runtime` | Auto-merge. |
| Workflow failure | workflow report | `workflow_watch` / repair route | Claim green when runs are empty. |

## Current known blocker

After commit `6146e75`, real GitHub access validation works. The next blocker is:

```text
GitHub access ready.
Sovereign Agent not configured.
No file changed.
```

Correct runtime handling:

```text
GitHub ready stays ready.
Sovereign Agent missing becomes executor_unavailable.
Direct GitHub Patch should be checked for small docs/README tasks.
Next action must not be “open GitHub access” when access is already ready.
```

## Direct GitHub Patch route

Use for small, reviewable docs changes first:

```text
README.md
README.*
docs/**/*.md
```

Do not use Direct Patch v1 for:

```text
src/**
android/**
scripts/**
package.json
workflow files
```

Those larger paths require workspace or stronger executor gates.

Minimal flow:

```text
Write intent
→ repo ready?
→ GitHub write ready?
→ target path allowed?
→ file fetched?
→ patch generated?
→ patch validated?
→ diff preview / Draft PR
```

## Workspace Runtime route

Use for real development work:

```text
- multiple files
- source-code changes
- Android changes
- dependency or build repair
- tests required
- complex diagnostics
```

Workspace Runtime must be agent-neutral:

```text
Sovereign Agent Workspace Runtime
  ├─ Sovereign Agent adapter
  ├─ future code-agent adapter
  ├─ test runner adapter
  └─ analysis-only snapshot adapter
```

Every write workspace is per-job isolated. No shared live write folder.

## Local runtime answers

Questions like these should be answered from runtime state:

```text
Bist du fertig?
Warum passiert nichts?
Nutzen wir eine andere Route und nicht Sovereign Agent?
Wo ist der Patch?
```

If the active state is GitHub-ready but executor-blocked, answer:

```text
Nein. GitHub-Zugang ist bereit, aber es wurde noch keine Datei geändert. Die Patch/Draft-PR Route ist blockiert, weil kein passender Schreib-Executor verfügbar ist.
```

Do not send that question to the worker as a fresh LLM call.

## Action Stream requirements

Every route decision must create an action event:

```ts
appendActionEvent({
  kind: 'route_selected',
  route: decision.route,
  label: 'Route gewählt',
  detail: decision.reason,
  state: decision.allowed ? 'running' : 'blocked',
});
```

The action stream should show:

```text
Auftrag empfangen
Intent erkannt
Repo geprüft
GitHub-Zugang geprüft / bereit / fehlt
Route gewählt
Route blockiert / gestartet
Ergebnis oder nächster Blocker
```

## Implementation order

1. Fix write-intent routing after GitHub-ready without Sovereign Agent lock-in.
2. Add Direct GitHub Patch for README/docs.
3. Add Sovereign Capability Router as the central decision function.
4. Add active blocker registry and dedupe repeated route errors.
5. Add agent-neutral Sovereign Workspace Runtime.

Related issues:

```text
#500 Runtime: route write intents after GitHub ready without Sovereign Agent lock-in
#501 Runtime: add Direct GitHub Patch route for small README/docs changes
#502 Runtime: add Sovereign Capability Router for chat, patch, workspace and Draft PR routes
#503 Runtime: design Sovereign Agent Workspace Runtime as agent-neutral isolated executor
#504 UX/Runtime: display active blockers honestly and dedupe repeated route errors
#505 Security/UX: harden GitHub credential handling and Android clipboard guidance
```

## Tests to protect this contract

Future work should add tests around:

```text
sovereignCapabilityRouter.test.ts
directGithubPatchRuntime.test.ts
sovereignWorkspaceRuntime.test.ts
sovereignBlockerRegistry.test.ts
BuilderContainer.test.tsx routing cases
```

The most important assertions:

- Chat questions do not start a write workspace.
- README/docs mini-patches do not require Sovereign Agent when Direct Patch is available.
- GitHub-ready + Sovereign Agent-missing is not a GitHub access blocker.
- Status questions use local runtime state.
- No route decision contains secrets.
