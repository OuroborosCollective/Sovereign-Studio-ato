---
name: Sovereign execution routing order
description: The correct routing precedence in BuilderContainer._processSubmit, plus key decisions for executor/credit/security handling.
---

## Routing order in `_processSubmit` (enforced, do not reorder)

1. **SecureInputGuard** — blocks secrets before any storage or LLM path
2. **Slash commands** — `/analyze`, `/fix`, `/pr`, `/repo`, `/clear`, `/skills`
3. **Repo URL detection** — loads repo on URL-shaped input
4. **Executor status questions** (guarded) — `isExecutorStatusQuestion()` answers locally, BUT only when `_executorIsActive || !workerBlocker`. If workerBlocker is active AND executor is idle, route falls through to Worker-Diagnose.
5. **Worker blocker** — `workerBlocker && !isWorkerRetryIntent && !isOpenHandsExecutionIntent` → local diagnostic answer, no retry
6. **Execution intent** — `isOpenHandsExecutionIntent || isDelegatedOpenHandsExecutionIntent` → start OpenHands, return. **No credit charged here.**
7. **Credit guard** — `chargeCredits('gemini-2.0-flash', ...)` — only fires for Worker Chat path
8. **PAL route + Worker Chat** — normal LLM message flow

**Why:** OpenHands execution must not be charged as a Worker Chat. Credit guard sits between execution intent routing and Worker Chat to enforce this.

## Security card pattern

- `evaluateInputPolicy()` sets `securityCardPending` state (not chatHistory)
- `SecurityBlockCard` component renders title/text/hint + "GitHub-Zugang öffnen" button
- Button sets `showGitHubAccessOverride` → forces `GitHubAccessCard` visible
- `securityCardPending` bypasses the `chatHistory.length === 0 → WelcomeScreen` condition so card renders even with empty chat
- Token NEVER stored in chatHistory, logs, or LLM prompts

## Immediate AgentWorkTimeline

When execution intent is detected and `!agentDisabled`:
1. Call `setAgentWorkSnapshot(transitionIntentDetected(...))` immediately
2. Then call `startAgentFromText()`
3. Timeline shows `intent_detected` state before `openhandsJob` polling begins

**Why:** Without this, the timeline shows nothing until the external prop `openhandsJob` changes.

## Tests to add later (workflow)

- Spy on `useCreditGuard().chargeCredits` → assert no call for execution intents
- workerBlocker active + executor idle + "warum passiert nichts?" → Worker-Diagnose (not executor-status answer)
