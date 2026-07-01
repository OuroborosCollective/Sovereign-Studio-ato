---
name: AgentWork state machine path to draft_pr_ready
description: transitionDraftPrReady has an input-state allowlist; jumping directly from intent_detected fails silently.
---

`transitionDraftPrReady` guards its input state:
```
const allowed = ['executor_running', 'branch_created', 'commit_created', 'checks_running'];
if (!allowed.includes(snapshot.state)) return snapshot; // silent no-op
```

**Why:** `intent_detected` is NOT on the list. Calling `transitionDraftPrReady` from `intent_detected` returns the snapshot unchanged — state stays `intent_detected`, not `draft_pr_ready`. Tests that skipped the intermediate states produced a hook that never fired its `draft_pr_ready` effect (both effect conditions read false).

**How to apply:** Any test helper that needs a `draft_pr_ready` snapshot must walk the full chain:
```ts
const base    = createIdleSnapshot('trace');
const intent  = transitionIntentDetected(base, 'owner/repo', 'main');
const starting = transitionExecutorStarting(intent, 'openhands');
const running  = transitionExecutorRunning(starting, 'job-test-123'); // jobId required
const ready    = transitionDraftPrReady(running, prUrl);              // prUrl must start with 'http'
```
Also: `transitionDraftPrReady` with `state === 'executor_running'` requires a non-empty `jobId` on the snapshot — `transitionExecutorRunning` sets it automatically.
