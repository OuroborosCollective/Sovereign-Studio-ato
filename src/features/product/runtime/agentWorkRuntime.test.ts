import { describe, it, expect } from 'vitest';
import {
  createIdleSnapshot,
  transitionIntentDetected,
  transitionAccessRequired,
  transitionAccessValidating,
  transitionAccessReady,
  transitionExecutorStarting,
  transitionExecutorRunning,
  transitionBranchCreated,
  transitionCommitCreated,
  transitionChecksRunning,
  transitionDraftPrReady,
  transitionBlocked,
  transitionFailed,
  transitionQuestionRequired,
  isTerminalState,
  isActiveState,
  labelForState,
} from './agentWorkRuntime';

const TRACE = 'test-trace-001';

describe('agentWorkRuntime', () => {
  it('creates idle snapshot with correct defaults', () => {
    const snap = createIdleSnapshot(TRACE);
    expect(snap.state).toBe('idle');
    expect(snap.traceId).toBe(TRACE);
    expect(snap.jobId).toBeNull();
    expect(snap.branchName).toBeNull();
    expect(snap.commitSha).toBeNull();
    expect(snap.draftPrUrl).toBeNull();
    expect(snap.events).toHaveLength(0);
  });

  it('transitions idle → intent_detected with repo info', () => {
    const snap = createIdleSnapshot(TRACE);
    const next = transitionIntentDetected(snap, 'owner/repo', 'main');
    expect(next.state).toBe('intent_detected');
    expect(next.repoFullName).toBe('owner/repo');
    expect(next.baseBranch).toBe('main');
    expect(next.events).toHaveLength(1);
    expect(next.events[0].state).toBe('intent_detected');
  });

  it('does not transition intent_detected from non-idle state', () => {
    const snap = createIdleSnapshot(TRACE);
    const after = transitionIntentDetected(snap, 'owner/repo', 'main');
    const again = transitionIntentDetected(after, 'owner/repo', 'main');
    expect(again.state).toBe('intent_detected');
    expect(again.events).toHaveLength(1);
  });

  it('does not claim intent detection without repo and base-branch evidence', () => {
    const idle = createIdleSnapshot(TRACE);
    expect(transitionIntentDetected(idle, '', 'main')).toBe(idle);
    expect(transitionIntentDetected(idle, 'owner/repo', '   ')).toBe(idle);
  });

  it('transitions through question_required', () => {
    const snap = transitionIntentDetected(createIdleSnapshot(TRACE), 'o/r', 'main');
    const q = transitionQuestionRequired(snap, 'Was soll passieren?');
    expect(q.state).toBe('question_required');
  });

  it('transitions intent_detected → access_required', () => {
    const snap = transitionIntentDetected(createIdleSnapshot(TRACE), 'o/r', 'main');
    const access = transitionAccessRequired(snap);
    expect(access.state).toBe('access_required');
  });

  it('validates access flow: access_required → validating → ready', () => {
    let snap = createIdleSnapshot(TRACE);
    snap = transitionIntentDetected(snap, 'o/r', 'main');
    snap = transitionAccessRequired(snap);
    snap = transitionAccessValidating(snap);
    expect(snap.state).toBe('access_validating');
    snap = transitionAccessReady(snap);
    expect(snap.state).toBe('access_ready');
  });

  it('transitions to executor_starting with type', () => {
    let snap = createIdleSnapshot(TRACE);
    snap = transitionIntentDetected(snap, 'o/r', 'main');
    snap = transitionAccessRequired(snap);
    snap = transitionAccessValidating(snap);
    snap = transitionAccessReady(snap);
    snap = transitionExecutorStarting(snap, 'sovereign-agent');
    expect(snap.state).toBe('executor_starting');
    expect(snap.executorType).toBe('sovereign-agent');
  });

  it('transitions executor_starting → executor_running requires non-empty jobId', () => {
    let snap = createIdleSnapshot(TRACE);
    snap = transitionIntentDetected(snap, 'o/r', 'main');
    snap = transitionAccessRequired(snap);
    snap = transitionAccessValidating(snap);
    snap = transitionAccessReady(snap);
    snap = transitionExecutorStarting(snap, 'sovereign-agent');

    const blank = transitionExecutorRunning(snap, '');
    expect(blank.state).toBe('executor_starting');

    snap = transitionExecutorRunning(snap, 'job-abc-123');
    expect(snap.state).toBe('executor_running');
    expect(snap.jobId).toBe('job-abc-123');
    expect(snap.lastVerifiedAt).not.toBeNull();
  });

  it('transitions executor_running → branch_created requires non-empty branchName', () => {
    let snap = createIdleSnapshot(TRACE);
    snap = transitionIntentDetected(snap, 'o/r', 'main');
    snap = transitionAccessRequired(snap);
    snap = transitionAccessValidating(snap);
    snap = transitionAccessReady(snap);
    snap = transitionExecutorStarting(snap, 'sovereign-agent');
    snap = transitionExecutorRunning(snap, 'job-abc');

    const bad = transitionBranchCreated(snap, '');
    expect(bad.state).toBe('executor_running');

    snap = transitionBranchCreated(snap, 'feature/test');
    expect(snap.state).toBe('branch_created');
    expect(snap.branchName).toBe('feature/test');
  });

  it('transitions branch_created → commit_created requires non-empty sha', () => {
    let snap = createIdleSnapshot(TRACE);
    snap = transitionIntentDetected(snap, 'o/r', 'main');
    snap = transitionAccessRequired(snap);
    snap = transitionAccessValidating(snap);
    snap = transitionAccessReady(snap);
    snap = transitionExecutorStarting(snap, 'sovereign-agent');
    snap = transitionExecutorRunning(snap, 'job-abc');
    snap = transitionBranchCreated(snap, 'feature/test');

    const bad = transitionCommitCreated(snap, '');
    expect(bad.state).toBe('branch_created');

    snap = transitionCommitCreated(snap, 'abc1234');
    expect(snap.state).toBe('commit_created');
    expect(snap.commitSha).toBe('abc1234');
  });

  it('transitions commit_created → checks_running → draft_pr_ready', () => {
    let snap = createIdleSnapshot(TRACE);
    snap = transitionIntentDetected(snap, 'o/r', 'main');
    snap = transitionAccessRequired(snap);
    snap = transitionAccessValidating(snap);
    snap = transitionAccessReady(snap);
    snap = transitionExecutorStarting(snap, 'sovereign-agent');
    snap = transitionExecutorRunning(snap, 'job-abc');
    snap = transitionBranchCreated(snap, 'feature/test');
    snap = transitionCommitCreated(snap, 'abc1234');
    snap = transitionChecksRunning(snap);
    expect(snap.state).toBe('checks_running');

    const bad = transitionDraftPrReady(snap, 'not-a-url');
    expect(bad.state).toBe('checks_running');

    snap = transitionDraftPrReady(snap, 'https://github.com/o/r/pull/1');
    expect(snap.state).toBe('draft_pr_ready');
    expect(snap.draftPrUrl).toBe('https://github.com/o/r/pull/1');
  });

  it('does not finalize a Draft PR from URL evidence alone', () => {
    let snap = createIdleSnapshot(TRACE);
    snap = transitionIntentDetected(snap, 'o/r', 'main');
    snap = transitionExecutorStarting(snap, 'sovereign-agent');
    snap = transitionExecutorRunning(snap, 'job-verified');

    const result = transitionDraftPrReady(snap, 'https://github.com/o/r/pull/7');

    expect(result).toBe(snap);
    expect(result.state).toBe('executor_running');
    expect(result.draftPrUrl).toBeNull();
  });

  it('still blocks draft_pr_ready without a valid URL or active executor truth', () => {
    const idle = createIdleSnapshot(TRACE);
    expect(transitionDraftPrReady(idle, 'https://github.com/o/r/pull/8').state).toBe('idle');

    let snap = transitionIntentDetected(idle, 'o/r', 'main');
    snap = transitionExecutorStarting(snap, 'sovereign-agent');
    expect(transitionDraftPrReady(snap, 'https://github.com/o/r/pull/8').state).toBe('executor_starting');
    snap = transitionExecutorRunning(snap, 'job-verified');
    expect(transitionDraftPrReady(snap, 'not-a-url').state).toBe('executor_running');
  });

  it('accumulates events through full happy path', () => {
    let snap = createIdleSnapshot(TRACE);
    snap = transitionIntentDetected(snap, 'o/r', 'main');
    snap = transitionAccessRequired(snap);
    snap = transitionAccessValidating(snap);
    snap = transitionAccessReady(snap);
    snap = transitionExecutorStarting(snap, 'sovereign-agent');
    snap = transitionExecutorRunning(snap, 'job-x');
    snap = transitionBranchCreated(snap, 'feature/x');
    snap = transitionCommitCreated(snap, 'deadbeef');
    snap = transitionChecksRunning(snap);
    snap = transitionDraftPrReady(snap, 'https://github.com/o/r/pull/99');
    expect(snap.events.length).toBeGreaterThanOrEqual(9);
  });

  it('transitionBlocked preserves reason', () => {
    const snap = transitionBlocked(createIdleSnapshot(TRACE), 'No PAT provided');
    expect(snap.state).toBe('blocked');
    expect(snap.blockerReason).toBe('No PAT provided');
  });

  it('transitionFailed preserves reason', () => {
    const snap = transitionFailed(createIdleSnapshot(TRACE), 'Build error');
    expect(snap.state).toBe('failed');
    expect(snap.blockerReason).toBe('Build error');
  });

  it('keeps terminal truth immutable and rejects empty blocker evidence', () => {
    const blocked = transitionBlocked(createIdleSnapshot(TRACE), 'No PAT provided');
    expect(transitionFailed(blocked, 'later failure')).toBe(blocked);
    expect(transitionBlocked(blocked, '   ')).toBe(blocked);

    const failed = transitionFailed(createIdleSnapshot(TRACE), 'Build error');
    expect(transitionBlocked(failed, 'later blocker')).toBe(failed);
  });

  it('isTerminalState returns correct values', () => {
    expect(isTerminalState('draft_pr_ready')).toBe(true);
    expect(isTerminalState('blocked')).toBe(true);
    expect(isTerminalState('failed')).toBe(true);
    expect(isTerminalState('executor_running')).toBe(false);
    expect(isTerminalState('idle')).toBe(false);
  });

  it('isActiveState returns correct values', () => {
    expect(isActiveState('executor_running')).toBe(true);
    expect(isActiveState('branch_created')).toBe(true);
    expect(isActiveState('checks_running')).toBe(true);
    expect(isActiveState('idle')).toBe(false);
    expect(isActiveState('draft_pr_ready')).toBe(false);
  });

  it('labelForState returns human-readable strings', () => {
    expect(labelForState('idle')).toBe('Bereit');
    expect(labelForState('draft_pr_ready')).toBe('Draft PR bereit');
    expect(labelForState('executor_running')).toBe('Executor läuft');
  });
});
