/**
 * agentWorkRuntime - State machine for agent code/build/PR work.
 *
 * Rule: Runtime state creates truth. UI only displays it.
 * No fake progress, no mocks in live paths, no percentage bars.
 */

export type AgentWorkState =
  | 'idle'
  | 'intent_detected'
  | 'question_required'
  | 'access_required'
  | 'access_validating'
  | 'access_ready'
  | 'executor_starting'
  | 'executor_running'
  | 'branch_created'
  | 'commit_created'
  | 'checks_running'
  | 'draft_pr_ready'
  | 'blocked'
  | 'failed';

export interface AgentWorkEvent {
  readonly id: string;
  readonly state: AgentWorkState;
  readonly label: string;
  readonly detail?: string;
  readonly ts: number;
}

export interface AgentWorkSnapshot {
  readonly traceId: string;
  readonly state: AgentWorkState;
  readonly repoFullName: string | null;
  readonly baseBranch: string | null;
  readonly executorType: 'openhands' | 'cloudflare-worker' | 'github-app' | 'local' | null;
  readonly jobId: string | null;
  readonly branchName: string | null;
  readonly commitSha: string | null;
  readonly draftPrUrl: string | null;
  readonly lastVerifiedAt: number | null;
  readonly blockerReason: string | null;
  readonly events: readonly AgentWorkEvent[];
}

export function createIdleSnapshot(traceId: string): AgentWorkSnapshot {
  return {
    traceId,
    state: 'idle',
    repoFullName: null,
    baseBranch: null,
    executorType: null,
    jobId: null,
    branchName: null,
    commitSha: null,
    draftPrUrl: null,
    lastVerifiedAt: null,
    blockerReason: null,
    events: [],
  };
}

function appendEvent(
  snapshot: AgentWorkSnapshot,
  state: AgentWorkState,
  label: string,
  detail?: string,
): AgentWorkSnapshot {
  const event: AgentWorkEvent = {
    id: `${snapshot.traceId}-${snapshot.events.length}`,
    state,
    label,
    detail,
    ts: Date.now(),
  };
  return { ...snapshot, state, events: [...snapshot.events, event] };
}

export function transitionIntentDetected(
  snapshot: AgentWorkSnapshot,
  repoFullName: string,
  baseBranch: string,
): AgentWorkSnapshot {
  if (snapshot.state !== 'idle') return snapshot;
  return appendEvent(
    { ...snapshot, repoFullName, baseBranch },
    'intent_detected',
    'Auftrag erkannt',
    `Repo: ${repoFullName}`,
  );
}

export function transitionQuestionRequired(
  snapshot: AgentWorkSnapshot,
  question: string,
): AgentWorkSnapshot {
  if (snapshot.state !== 'intent_detected') return snapshot;
  return appendEvent(snapshot, 'question_required', 'Rückfrage erforderlich', question);
}

export function transitionAccessRequired(snapshot: AgentWorkSnapshot): AgentWorkSnapshot {
  const allowed: AgentWorkState[] = ['intent_detected', 'question_required'];
  if (!allowed.includes(snapshot.state)) return snapshot;
  return appendEvent(snapshot, 'access_required', 'GitHub-Zugang erforderlich');
}

export function transitionAccessValidating(snapshot: AgentWorkSnapshot): AgentWorkSnapshot {
  if (snapshot.state !== 'access_required') return snapshot;
  return appendEvent(snapshot, 'access_validating', 'Zugang wird geprüft…');
}

export function transitionAccessReady(snapshot: AgentWorkSnapshot): AgentWorkSnapshot {
  if (snapshot.state !== 'access_validating') return snapshot;
  return appendEvent(snapshot, 'access_ready', 'Zugang bestätigt');
}

export function transitionExecutorStarting(
  snapshot: AgentWorkSnapshot,
  executorType: AgentWorkSnapshot['executorType'],
): AgentWorkSnapshot {
  const allowed: AgentWorkState[] = ['access_ready', 'intent_detected'];
  if (!allowed.includes(snapshot.state)) return snapshot;
  return appendEvent(
    { ...snapshot, executorType },
    'executor_starting',
    'Executor wird gestartet',
    executorType ?? undefined,
  );
}

export function transitionExecutorRunning(
  snapshot: AgentWorkSnapshot,
  jobId: string,
): AgentWorkSnapshot {
  if (snapshot.state !== 'executor_starting') return snapshot;
  if (!jobId || jobId.trim() === '') return snapshot;
  return appendEvent(
    { ...snapshot, jobId, lastVerifiedAt: Date.now() },
    'executor_running',
    'Executor läuft',
    `Job-ID: ${jobId}`,
  );
}

export function transitionBranchCreated(
  snapshot: AgentWorkSnapshot,
  branchName: string,
): AgentWorkSnapshot {
  if (snapshot.state !== 'executor_running') return snapshot;
  if (!branchName || branchName.trim() === '') return snapshot;
  return appendEvent(
    { ...snapshot, branchName, lastVerifiedAt: Date.now() },
    'branch_created',
    'Branch erstellt',
    branchName,
  );
}

export function transitionCommitCreated(
  snapshot: AgentWorkSnapshot,
  commitSha: string,
): AgentWorkSnapshot {
  if (snapshot.state !== 'branch_created') return snapshot;
  if (!commitSha || commitSha.trim() === '') return snapshot;
  return appendEvent(
    { ...snapshot, commitSha, lastVerifiedAt: Date.now() },
    'commit_created',
    'Commit erstellt',
    commitSha.slice(0, 7),
  );
}

export function transitionChecksRunning(snapshot: AgentWorkSnapshot): AgentWorkSnapshot {
  if (snapshot.state !== 'commit_created') return snapshot;
  return appendEvent(snapshot, 'checks_running', 'Checks laufen…');
}

export function transitionDraftPrReady(
  snapshot: AgentWorkSnapshot,
  draftPrUrl: string,
): AgentWorkSnapshot {
  const allowed: AgentWorkState[] = ['commit_created', 'checks_running'];
  if (!allowed.includes(snapshot.state)) return snapshot;
  if (!draftPrUrl || !draftPrUrl.startsWith('http')) return snapshot;
  return appendEvent(
    { ...snapshot, draftPrUrl, lastVerifiedAt: Date.now() },
    'draft_pr_ready',
    'Draft PR bereit',
    draftPrUrl,
  );
}

export function transitionBlocked(
  snapshot: AgentWorkSnapshot,
  reason: string,
): AgentWorkSnapshot {
  return appendEvent(
    { ...snapshot, blockerReason: reason },
    'blocked',
    'Blockiert',
    reason,
  );
}

export function transitionFailed(
  snapshot: AgentWorkSnapshot,
  reason: string,
): AgentWorkSnapshot {
  return appendEvent(
    { ...snapshot, blockerReason: reason },
    'failed',
    'Fehlgeschlagen',
    reason,
  );
}

export function isTerminalState(state: AgentWorkState): boolean {
  return state === 'draft_pr_ready' || state === 'blocked' || state === 'failed';
}

export function isActiveState(state: AgentWorkState): boolean {
  const active: AgentWorkState[] = [
    'executor_starting',
    'executor_running',
    'branch_created',
    'commit_created',
    'checks_running',
  ];
  return active.includes(state);
}

export function labelForState(state: AgentWorkState): string {
  const labels: Record<AgentWorkState, string> = {
    idle: 'Bereit',
    intent_detected: 'Auftrag erkannt',
    question_required: 'Rückfrage',
    access_required: 'Zugang erforderlich',
    access_validating: 'Zugang wird geprüft',
    access_ready: 'Zugang bestätigt',
    executor_starting: 'Executor startet',
    executor_running: 'Executor läuft',
    branch_created: 'Branch erstellt',
    commit_created: 'Commit erstellt',
    checks_running: 'Checks laufen',
    draft_pr_ready: 'Draft PR bereit',
    blocked: 'Blockiert',
    failed: 'Fehlgeschlagen',
  };
  return labels[state] ?? state;
}
