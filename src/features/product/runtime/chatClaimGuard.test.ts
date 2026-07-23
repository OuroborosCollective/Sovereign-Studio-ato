import { describe, it, expect } from 'vitest';
import { checkChatClaim, hasAnyWorkClaim } from './chatClaimGuard';
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
} from './agentWorkRuntime';

const TRACE = 'guard-test-001';

function buildFullSnapshot() {
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
  snap = transitionDraftPrReady(snap, 'https://github.com/o/r/pull/44');
  return snap;
}

describe('chatClaimGuard', () => {
  it('allows response with no work claims', () => {
    const snap = createIdleSnapshot(TRACE);
    const result = checkChatClaim('Ich analysiere deinen Code.', snap);
    expect(result.allowed).toBe(true);
    expect(result.violations).toHaveLength(0);
    expect(result.honestFallback).toBeNull();
  });

  it('blocks "PR erstellt" when draftPrUrl is missing', () => {
    const snap = createIdleSnapshot(TRACE);
    const result = checkChatClaim('Der PR erstellt wurde erfolgreich.', snap);
    expect(result.allowed).toBe(false);
    expect(result.violations).toContain('draft_pr_claimed_without_url');
    expect(result.honestFallback).not.toBeNull();
    expect(result.honestFallback).toContain('Draft PR URL');
  });

  it('blocks "Draft PR bereit" when draftPrUrl is missing', () => {
    const snap = createIdleSnapshot(TRACE);
    const result = checkChatClaim('Draft PR bereit für deinen Review.', snap);
    expect(result.allowed).toBe(false);
    expect(result.violations).toContain('draft_pr_claimed_without_url');
  });

  it('allows "PR erstellt" when draftPrUrl is present', () => {
    const snap = buildFullSnapshot();
    const result = checkChatClaim('PR erstellt: https://github.com/o/r/pull/44', snap);
    expect(result.allowed).toBe(true);
  });

  it('blocks "Branch erstellt" when branchName is missing', () => {
    const snap = createIdleSnapshot(TRACE);
    const result = checkChatClaim('Branch erstellt und bereit.', snap);
    expect(result.allowed).toBe(false);
    expect(result.violations).toContain('branch_claimed_without_name');
    expect(result.honestFallback).toContain('Branch-Name');
  });

  it('allows "Branch erstellt" when branchName is present', () => {
    let snap = createIdleSnapshot(TRACE);
    snap = transitionIntentDetected(snap, 'o/r', 'main');
    snap = transitionAccessRequired(snap);
    snap = transitionAccessValidating(snap);
    snap = transitionAccessReady(snap);
    snap = transitionExecutorStarting(snap, 'sovereign-agent');
    snap = transitionExecutorRunning(snap, 'job-abc');
    snap = transitionBranchCreated(snap, 'feature/my-branch');
    const result = checkChatClaim('Branch erstellt: feature/my-branch', snap);
    expect(result.allowed).toBe(true);
  });

  it('blocks "Commit erstellt" when commitSha is missing', () => {
    const snap = createIdleSnapshot(TRACE);
    const result = checkChatClaim('Commit erstellt auf dem Branch.', snap);
    expect(result.allowed).toBe(false);
    expect(result.violations).toContain('commit_claimed_without_sha');
    expect(result.honestFallback).toContain('Commit-SHA');
  });

  it('allows "Commit erstellt" when commitSha is present', () => {
    const snap = buildFullSnapshot();
    const result = checkChatClaim('Commit erstellt mit SHA abc1234', snap);
    expect(result.allowed).toBe(true);
  });

  it('blocks executor claims without jobId', () => {
    const snap = createIdleSnapshot(TRACE);
    const result = checkChatClaim('Executor läuft und verarbeitet deinen Auftrag.', snap);
    expect(result.allowed).toBe(false);
    expect(result.violations).toContain('executor_claimed_without_job');
    expect(result.honestFallback).toContain('kein laufender Job');
  });

  it('blocks Sovereign Agent work claims without jobId', () => {
    const snap = createIdleSnapshot(TRACE);
    const result = checkChatClaim('Sovereign Agent arbeitet an deinem PR.', snap);
    expect(result.allowed).toBe(false);
    expect(result.violations).toContain('executor_claimed_without_job');
  });

  it('reports multiple violations in one response', () => {
    const snap = createIdleSnapshot(TRACE);
    const result = checkChatClaim(
      'Branch erstellt, Commit erstellt, PR erstellt, Executor läuft.',
      snap,
    );
    expect(result.allowed).toBe(false);
    expect(result.violations.length).toBeGreaterThanOrEqual(3);
  });

  it('honest fallback references current state', () => {
    const snap = createIdleSnapshot(TRACE);
    const result = checkChatClaim('PR erstellt.', snap);
    expect(result.honestFallback).toContain('idle');
  });

  it('blocks deployment and live claims without revision, digest and health evidence', () => {
    const snap = createIdleSnapshot(TRACE);
    const result = checkChatClaim('Auf dem VPS installiert und jetzt live verfügbar.', snap);
    expect(result.allowed).toBe(false);
    expect(result.violations).toContain('deployment_claimed_without_revision_digest');
    expect(result.violations).toContain('live_claimed_without_runtime_health');
  });

  it('allows live claims only with complete immutable runtime evidence', () => {
    const snap = createIdleSnapshot(TRACE);
    const result = checkChatClaim('Auf dem VPS installiert und jetzt live verfügbar.', snap, {
      deployedRevision: 'a'.repeat(40),
      imageDigest: `sha256:${'b'.repeat(64)}`,
      runtimeHealthy: true,
    });
    expect(result.allowed).toBe(true);
  });

  it('blocks all-tests claims when skipped checks exist', () => {
    const snap = createIdleSnapshot(TRACE);
    const result = checkChatClaim('Alle Tests bestanden.', snap, { testsPassed: true, skippedTests: 1 });
    expect(result.allowed).toBe(false);
    expect(result.violations).toContain('all_tests_claimed_without_complete_evidence');
  });

  it('hasAnyWorkClaim detects claim patterns', () => {
    expect(hasAnyWorkClaim('PR erstellt.')).toBe(true);
    expect(hasAnyWorkClaim('Branch erstellt.')).toBe(true);
    expect(hasAnyWorkClaim('Executor läuft.')).toBe(true);
    expect(hasAnyWorkClaim('Ich lese deinen Code.')).toBe(false);
  });
});
