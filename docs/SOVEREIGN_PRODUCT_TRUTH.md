# Sovereign Product Truth

This document is the product contract that future agents must preserve. If a proposed UI, runtime or agent change conflicts with this file, the change is wrong unless this document is deliberately updated first.

## Non-negotiable rules

| Rule | Reason |
| --- | --- |
| **Default surface is Chat.** | The user converses; Sovereign acts behind the curtain. |
| Only chat timeline, text input, small thinking/status cues and compact lamps are **visible by default**. | Keeps first-time UX calm and focused. |
| Repo, Files, Diff, Workflow, Runtime, Telemetry, Health, Coverage, Memory and Inspector are **inspection surfaces** — opened explicitly, never forced on the user. | Prevents overwhelming dashboards. |
| Repo setup may start from a chat instruction. | Preserves the chat-first paradigm. |
| The UI must **not** become a dashboard, monitor or second control shell. | Truth is produced by runtime, not by UI. |
| Every action must produce a result. | Avoids invisible work and fake progress. |
| Every result must produce state. | State is what allows the next decision to be audited. |
| Every state must allow or block the next action. | Prevents endless “working” loops. |
| No hard percent progress unless it is a real measured runtime metric. | Prevents artificial confidence. |
| No mock, stub or facade in the live path. | Keeps release behavior real. |
| No Plan-only Draft PR. | A Draft PR must contain actionable, reviewable changes. |
| No auto-merge. | The human decides final merge. |
| Secrets and access values must never appear in chat, logs, telemetry, action events, docs, PR bodies or generated files. | Protects users and recordings. |

## Current route truth

Sovereign should feel like one assistant, but internally it routes by capability:

```text
Chat input
→ intent/status/write detection
→ repo gate
→ GitHub access gate for writes
→ capability router
→ worker/model route OR direct patch OR workspace executor OR Draft PR runtime
```

OpenHands is an optional workspace/code executor. It is not the same thing as an LLM/provider route. It may use an LLM, but it works by operating in a repo workspace. It must not become the only path for small file changes.

## GitHub access truth

A format-valid token is not write access. Write access is ready only after real GitHub API validation against the loaded repo.

Valid states must be displayed honestly:

```text
missing/requested → user action needed
validating → wait for API result
ready → GitHub write access is confirmed
invalid/failed → block with reason
```

GitHub-ready must stay ready even if OpenHands is missing. Missing executor capability is a separate blocker.

## Capability truth

Future implementation should follow this split:

| Capability | Use case | Requires |
| --- | --- | --- |
| `free_chat` | explanation, advice, summaries | model route only |
| `local-runtime-answer` | “bist du fertig?”, “warum?”, “andere Route?” | existing runtime state |
| `direct_github_patch` | small README/docs edits | repo + validated GitHub access |
| `workspace-executor` / `openhands` | multi-file code work, tests, build repair | isolated workspace capability |
| `draft-pr-runtime` | publish reviewable changes | validated GitHub access + reviewed diff |

## Drift prevention

Future agents must not:

- create another main shell;
- move truth into UI widgets;
- treat OpenHands as the only write path;
- treat a worker answer as a completed code change;
- use telemetry as proof of release readiness;
- claim CI green when workflow runs or combined statuses are empty;
- close issues for planned work without a committed implementation.

Related guide: [`docs/SOVEREIGN_CAPABILITY_ROUTING.md`](SOVEREIGN_CAPABILITY_ROUTING.md).

*Breaking these rules should fail tests, product-template invariant checks or review.*
